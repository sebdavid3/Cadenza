"""El símbolo del compás no entra en el OMR-NED medido (ADR-0044 §1, #236).

La verdad importada guarda C y ¢ desde #236 y HOMR no los escribe nunca: si la exportación con
que se mide los escribiera, musicdiff contaría la diferencia y el OMR-NED dejaría de ser
comparable con el medido antes. Las mediciones exportan sin el símbolo
(`without_time_symbols`); la descarga del usuario sí lo lleva.
"""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest
from cadenza.domain import Event, EventKind, Measure, Part, ScoreIR, Staff, TimeSignature
from cadenza.interchange import score_ir_to_musicxml
from cadenza.learning import time_symbol_agreement, without_time_symbols

COMMON = TimeSignature(4, 4, "common")
FOUR = TimeSignature(4, 4)


def _score(signature: TimeSignature, pitches: tuple[str, ...] = ("C5", "D5")) -> ScoreIR:
    measures = tuple(
        Measure(
            number=n,
            events=tuple(
                Event(kind=EventKind.NOTE, pitch=p, duration_beats=Fraction(2)) for p in pitches
            ),
            time_signature=signature,
        )
        for n in (1, 2)
    )
    return ScoreIR(parts=(Part(id="p", staves=(Staff(id="s", measures=measures),)),))


def _measured(score: ScoreIR, path: Path) -> Path:
    path.write_text(score_ir_to_musicxml(without_time_symbols(score)), encoding="utf-8")
    return path


def test_without_time_symbols_keeps_everything_else() -> None:
    stripped = without_time_symbols(_score(COMMON))
    assert stripped.to_primitive() == _score(FOUR).to_primitive()
    # Sin símbolos, la misma partitura (no se copia).
    plain = _score(FOUR)
    assert without_time_symbols(plain) is plain
    # La exportación de usuario sí lo lleva.
    assert 'symbol="common"' in score_ir_to_musicxml(_score(COMMON))
    assert "symbol=" not in score_ir_to_musicxml(without_time_symbols(_score(COMMON)))


def test_two_scores_that_only_differ_in_the_symbol_have_omr_ned_zero(tmp_path: Path) -> None:
    pytest.importorskip("musicdiff")
    from cadenza.learning import omr_ned_pair

    truth = _measured(_score(COMMON), tmp_path / "truth.musicxml")
    predicted = _measured(_score(FOUR), tmp_path / "pred.musicxml")
    assert omr_ned_pair(predicted, truth).omr_ned == 0.0


def test_omr_ned_with_c_is_the_one_measured_before_236(tmp_path: Path) -> None:
    """Antes de #236 la verdad con C se exportaba como 4/4: el OMR-NED medido es el mismo."""
    pytest.importorskip("musicdiff")
    from cadenza.learning import omr_ned_pair

    predicted = _measured(_score(FOUR, ("C5", "E5")), tmp_path / "pred.musicxml")
    with_c = omr_ned_pair(predicted, _measured(_score(COMMON), tmp_path / "c.musicxml"))
    before = tmp_path / "antes.musicxml"
    before.write_text(score_ir_to_musicxml(_score(FOUR)), encoding="utf-8")
    assert with_c.omr_ned > 0
    assert with_c.omr_ned == omr_ned_pair(predicted, before).omr_ned


def test_time_symbol_agreement_counts_measures_apart() -> None:
    truth = _score(COMMON)
    second = replace(truth.parts[0].staves[0].measures[1], time_signature=FOUR)
    mixed = replace(
        truth,
        parts=(
            replace(
                truth.parts[0],
                staves=(
                    replace(
                        truth.parts[0].staves[0],
                        measures=(truth.parts[0].staves[0].measures[0], second),
                    ),
                ),
            ),
        ),
    )
    assert time_symbol_agreement(_score(FOUR), truth) == {"correct": 0, "wrong": 2}
    assert time_symbol_agreement(mixed, truth) == {"correct": 1, "wrong": 1}
    assert time_symbol_agreement(truth, truth) == {"correct": 2, "wrong": 0}
    # Sin símbolo en ninguno de los dos, no es un acierto del símbolo: no se cuenta.
    assert time_symbol_agreement(_score(FOUR), _score(FOUR)) == {"correct": 0, "wrong": 0}


def test_exp_14_exports_without_the_symbol(tmp_path: Path) -> None:
    from cadenza.interchange import Music21ScoreExporter

    from ml.experiments import exp_14_suggestion_layer as exp_14

    path = exp_14._export(_score(COMMON), tmp_path / "truth.musicxml", Music21ScoreExporter())
    assert "symbol=" not in path.read_text(encoding="utf-8")
