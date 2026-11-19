"""Qué sesiones entran en los datos según el permiso de uso de los datos (#422, ADR-0065).

Decisión del responsable del 2026-11-19: las transcripciones de todas las cuentas con el permiso
vigente entran por defecto en las exportaciones y los datasets. Es la misma regla en todos los
comandos de `ml` que leen la base (`export-pairs`, `export-tables`, `export-staves`,
`build-dataset` y `suggestions build-dataset`):

- las cuentas que no vienen del registro público (las del equipo y las del estudio, anteriores a
  ADR-0070) entran: no se les pidió este permiso;
- las del registro entran si tienen el permiso del texto vigente (`has_current_data_consent`), y
  ninguna con `exclude_self_registered` (`--exclude-self-registered`);
- las del registro sin el permiso vigente (nunca lo dieron, lo retiraron o lo dieron para otro
  texto) quedan siempre fuera, también con opciones. De estas y de las que deja fuera la opción
  solo se cuenta cuántas sesiones son (`ConsentTally`), sin su identificador;
- una sesión cuya cuenta no está queda fuera con su motivo (`NO_OWNER`): no se sabe si tiene el
  permiso.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from cadenza.application import DATA_CONSENT_VERSION, User, has_current_data_consent
from cadenza.application.ports import SessionData, UserRepository

NO_OWNER = "sin la cuenta de su dueño"
WITHOUT_CURRENT_CONSENT = "cuenta del registro sin el permiso de uso de los datos vigente"
EXCLUDED_BY_OPTION = "cuenta del registro, fuera con --exclude-self-registered"


@dataclass
class ConsentTally:
    """Cuántas sesiones deja fuera el permiso: solo el número, sin sus identificadores."""

    without_current_consent: int = 0
    excluded_by_option: int = 0

    def to_primitive(self) -> dict[str, Any]:
        """El bloque `consent` de `run_info.json`, el mismo en todas las exportaciones."""
        return {
            "version": DATA_CONSENT_VERSION,
            "sessions_without_current_consent": self.without_current_consent,
            "sessions_excluded_by_option": self.excluded_by_option,
        }


def consent_refusal(owner: User, *, exclude_self_registered: bool) -> str | None:
    """Por qué el permiso deja fuera las sesiones de `owner`, o None si entran."""
    if not owner.self_registered:
        return None
    if not has_current_data_consent(owner):
        return WITHOUT_CURRENT_CONSENT
    if exclude_self_registered:
        return EXCLUDED_BY_OPTION
    return None


def filter_by_consent(
    sessions: Iterable[SessionData],
    user_repository: UserRepository,
    *,
    exclude_self_registered: bool,
    tally: ConsentTally | None = None,
) -> tuple[list[SessionData], dict[str, str]]:
    """Las sesiones que entran según el permiso, en su orden, y las que quedan fuera porque su
    cuenta no está, con su motivo. Las que deja fuera el permiso o la opción no salen en
    ninguna de las dos: solo se suman a `tally`."""
    counted = ConsentTally() if tally is None else tally
    entering: list[SessionData] = []
    left_out: dict[str, str] = {}
    for session in sessions:
        owner = user_repository.get(session.owner_id)
        if owner is None:
            left_out[session.id] = NO_OWNER
            continue
        refusal = consent_refusal(owner, exclude_self_registered=exclude_self_registered)
        if refusal is None:
            entering.append(session)
        elif refusal == WITHOUT_CURRENT_CONSENT:
            counted.without_current_consent += 1
        else:
            counted.excluded_by_option += 1
    return entering, left_out
