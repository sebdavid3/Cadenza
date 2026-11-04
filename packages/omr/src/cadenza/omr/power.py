"""Control de limitación de energía (Power Throttling / EcoQoS) del proceso (#106).

En Windows 11 con procesadores de arquitectura híbrida (Intel 12.ª gen o superior),
el sistema operativo confina los procesos en segundo plano a los núcleos de
eficiencia (E-cores) mediante EcoQoS / Power Throttling. En tareas de inferencia
intensiva como HOMR en CPU, esto reduce el rendimiento hasta ~10 veces (de ~8 s
a ~85 s por página de 8 pentagramas).

ADR-0015 / Issue #106: renuncia explícita del proceso a la limitación de energía
mediante `SetProcessInformation(ProcessPowerThrottling)`.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes
from typing import Literal

logger = logging.getLogger("cadenza.omr.power")

PROCESS_POWER_THROTTLING: int = 4
PROCESS_POWER_THROTTLING_CURRENT_VERSION: int = 1
PROCESS_POWER_THROTTLING_EXECUTION_SPEED: int = 0x1


class PowerThrottlingState(ctypes.Structure):
    """Estructura POWER_THROTTLING_PROCESS_STATE de la API de Windows."""

    _fields_ = [
        ("Version", wintypes.ULONG),
        ("ControlMask", wintypes.ULONG),
        ("StateMask", wintypes.ULONG),
    ]


PowerThrottlingMode = Literal["disabled", "forced", "system"]


def set_power_throttling(mode: PowerThrottlingMode = "disabled") -> bool:
    """Configura la limitación de energía del proceso en Windows.

    - "disabled": desactiva la limitación de energía (StateMask = 0).
    - "forced": fuerza la limitación de energía (StateMask = 0x1) para controles/benchmarks.
    - "system": no modifica la configuración del sistema (retorna True sin alterar nada).

    Retorna True si la llamada se aplicó correctamente; False si no está en Windows o si falló.
    No lanza excepciones ante fallos de la API del sistema operativo.
    """
    if mode == "system":
        return True

    if sys.platform != "win32":
        return False

    try:
        win_dll = getattr(ctypes, "WinDLL", None)
        if win_dll is None:
            return False

        kernel32 = win_dll("kernel32", use_last_error=True)
        get_current_process = kernel32.GetCurrentProcess
        get_current_process.restype = wintypes.HANDLE

        set_proc_info = kernel32.SetProcessInformation
        set_proc_info.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        set_proc_info.restype = wintypes.BOOL

        state_mask = 0x1 if mode == "forced" else 0
        state = PowerThrottlingState(
            Version=PROCESS_POWER_THROTTLING_CURRENT_VERSION,
            ControlMask=PROCESS_POWER_THROTTLING_EXECUTION_SPEED,
            StateMask=state_mask,
        )

        success = bool(
            set_proc_info(
                get_current_process(),
                PROCESS_POWER_THROTTLING,
                ctypes.byref(state),
                ctypes.sizeof(state),
            )
        )
        if not success:
            err = ctypes.get_last_error()
            logger.warning("No se pudo configurar Power Throttling en Windows (error=%s)", err)
        return success
    except Exception as exc:
        logger.warning("Fallo al intentar configurar Power Throttling: %s", exc)
        return False


def disable_power_throttling() -> bool:
    """Desactiva la limitación de energía (Power Throttling) del proceso en Windows."""
    return set_power_throttling("disabled")
