"""`read_score` registra los lectores de converter21 una sola vez (#421).

Antes, cada llamada los volvía a registrar: la lista de lectores de music21 crecía tres entradas
por partitura leída y cada lectura la recorría entera, así que un experimento que lee miles de
partituras (`exp_12`, `exp_18`) se frenaba sin límite: las mismas 100 lecturas tardaban 1 s en
un proceso nuevo y casi 6 s tras leer otras 200.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from cadenza.interchange import read_score
from music21 import converter

MEI = Path(__file__).parent / "fixtures" / "multirest.mei"


def _readers() -> int:
    return len(converter.Converter().subConvertersList())


def test_reading_many_scores_does_not_register_the_readers_again() -> None:
    pytest.importorskip("converter21")
    read_score(MEI)
    registered = _readers()
    for _ in range(5):
        read_score(MEI)
    assert _readers() == registered
