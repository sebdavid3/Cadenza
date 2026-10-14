"""Tests unitarios para la desactivación de limitación de energía de Windows (#106).

Verifica la renuncia a EcoQoS mediante SetProcessInformation sobre una API
de Windows falseada (éxito, fallo, excepción) y en plataformas no Windows.
"""

from __future__ import annotations

import ctypes
import sys
from typing import Any
from unittest.mock import MagicMock

import pytest
from cadenza.omr.power import (
    PROCESS_POWER_THROTTLING,
    PROCESS_POWER_THROTTLING_CURRENT_VERSION,
    PROCESS_POWER_THROTTLING_EXECUTION_SPEED,
    PowerThrottlingState,
    disable_power_throttling,
    set_power_throttling,
)


def test_power_throttling_non_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """En plataformas que no sean Windows no hace nada y devuelve False."""
    monkeypatch.setattr(sys, "platform", "linux")
    assert disable_power_throttling() is False
    assert set_power_throttling("forced") is False
    assert set_power_throttling("system") is True


def test_power_throttling_windows_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """En Windows, una llamada exitosa a SetProcessInformation retorna True."""
    monkeypatch.setattr(sys, "platform", "win32")

    mock_kernel32 = MagicMock()
    mock_kernel32.GetCurrentProcess.return_value = 42
    mock_kernel32.SetProcessInformation.return_value = 1

    monkeypatch.setattr(ctypes, "WinDLL", lambda _name, **_kwargs: mock_kernel32, raising=False)

    result = disable_power_throttling()
    assert result is True
    assert mock_kernel32.SetProcessInformation.called
    call_args = mock_kernel32.SetProcessInformation.call_args[0]
    assert call_args[0] == 42
    assert call_args[1] == PROCESS_POWER_THROTTLING


def test_power_throttling_windows_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """En Windows, si SetProcessInformation retorna 0 (fallo), devuelve False sin lanzar."""
    monkeypatch.setattr(sys, "platform", "win32")

    mock_kernel32 = MagicMock()
    mock_kernel32.GetCurrentProcess.return_value = 42
    mock_kernel32.SetProcessInformation.return_value = 0

    monkeypatch.setattr(ctypes, "WinDLL", lambda _name, **_kwargs: mock_kernel32, raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 87, raising=False)

    assert disable_power_throttling() is False


def test_power_throttling_windows_exception_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si ocurre una excepción del sistema (p.ej. OSError o AttributeError), no lanza."""
    monkeypatch.setattr(sys, "platform", "win32")

    def _raise_error(*_args: object, **_kwargs: object) -> None:
        raise OSError("WinDLL missing function")

    monkeypatch.setattr(ctypes, "WinDLL", _raise_error, raising=False)

    assert disable_power_throttling() is False


def test_power_throttling_forced_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """El modo 'forced' pasa StateMask = 0x1."""
    monkeypatch.setattr(sys, "platform", "win32")

    mock_kernel32 = MagicMock()
    mock_kernel32.GetCurrentProcess.return_value = 42
    captured_state: list[PowerThrottlingState] = []

    def _fake_set_info(handle: object, info_class: int, ptr: Any, size: int) -> int:
        nonlocal captured_state
        state_ptr = ctypes.cast(ptr, ctypes.POINTER(PowerThrottlingState))
        captured_state.append(
            PowerThrottlingState(
                Version=state_ptr.contents.Version,
                ControlMask=state_ptr.contents.ControlMask,
                StateMask=state_ptr.contents.StateMask,
            )
        )
        return 1

    mock_kernel32.SetProcessInformation.side_effect = _fake_set_info
    monkeypatch.setattr(ctypes, "WinDLL", lambda _name, **_kwargs: mock_kernel32, raising=False)

    assert set_power_throttling("forced") is True
    assert len(captured_state) == 1
    assert captured_state[0].Version == PROCESS_POWER_THROTTLING_CURRENT_VERSION
    assert captured_state[0].ControlMask == PROCESS_POWER_THROTTLING_EXECUTION_SPEED
    assert captured_state[0].StateMask == 0x1


@pytest.mark.skipif(sys.platform != "win32", reason="Prueba real exclusiva de Windows")
def test_real_windows_call_returns_bool() -> None:
    """Sobre el sistema Windows real devuelve bool sin lanzar excepción."""
    result = disable_power_throttling()
    assert isinstance(result, bool)
