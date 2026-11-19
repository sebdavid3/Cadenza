"""La opción del permiso de uso de los datos, la misma en todos los comandos (#422, ADR-0065).

Por defecto entran las cuentas del registro con el permiso vigente; `--exclude-self-registered`
las deja todas fuera (`cadenza.learning.consent`). La opción de antes,
`--include-self-registered`, se retiró en #422: lo que pedía es ahora lo de por defecto. Darla
falla y dice qué hacer, en lugar de no hacer nada: en `ml build-dataset` metía también las
cuentas sin el permiso, así que una receta vieja no daría lo que esperaba quien la escribió.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Any

EXCLUDE_HELP = (
    "Dejar fuera las cuentas del registro público, también las que tienen el permiso de uso de"
    " los datos vigente (por defecto entran; las que no lo tienen quedan siempre fuera)."
)

RETIRED = (
    "--include-self-registered ya no existe (#422): las cuentas del registro con el permiso de"
    " uso de los datos vigente entran por defecto, y las que no lo tienen quedan siempre fuera."
    " Para dejarlas todas fuera, --exclude-self-registered."
)


class _RetiredOption(argparse.Action):
    """Una opción retirada: no sale en la ayuda y, si se da, el comando falla con `RETIRED`."""

    def __init__(self, option_strings: Sequence[str], dest: str, **kwargs: Any) -> None:
        super().__init__(
            option_strings, dest, nargs=0, default=argparse.SUPPRESS, help=argparse.SUPPRESS
        )

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        parser.error(RETIRED)


def add_consent_options(parser: argparse.ArgumentParser) -> None:
    """`--exclude-self-registered`, y la opción retirada que lo explica si alguien la da."""
    parser.add_argument("--exclude-self-registered", action="store_true", help=EXCLUDE_HELP)
    parser.add_argument("--include-self-registered", action=_RetiredOption)
