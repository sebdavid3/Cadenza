"""Tests del experimento de latencia de una edición (#275).

El experimento mide la API real en el proceso. Aquí se comprueba el arnés con pocas
repeticiones y un reloj que avanza un milisegundo por lectura: cada duración del resumen sale
del reloj, no de una cifra escrita a mano, y la salida va a un directorio temporal, nunca a
`results/` (CLAUDE.md §8).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ml.experiments import exp_13_edit_latency as exp_13


class _TickClock:
    """Reloj que avanza 1 ms en cada lectura: una petición dura exactamente 1 ms."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 0.001
        return self.now


def test_tile_score_numbers_the_copies_and_declares_the_signatures_once() -> None:
    incipit = exp_13.load_incipit()
    source = incipit.parts[0].staves[0].measures

    page = exp_13.tile_score(incipit, 10)
    measures = page.parts[0].staves[0].measures

    assert [m.number for m in measures] == list(range(1, 11))
    assert measures[len(source)].events == source[0].events
    assert measures[0].time_signature is not None
    assert all(m.time_signature is None for m in measures[len(source) :])
    assert all(m.clef is None and m.key_signature is None for m in measures[len(source) :])


def test_tile_score_rejects_an_empty_page() -> None:
    with pytest.raises(ValueError):
        exp_13.tile_score(exp_13.load_incipit(), 0)


def test_missing_incipit_fails_instead_of_inventing_a_score(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        exp_13.load_incipit(tmp_path / "no-existe.musicxml")


def test_planner_alternates_each_note_between_two_valid_pitches() -> None:
    planner = exp_13.EditPlanner(exp_13.load_incipit())
    notes = len(exp_13.note_targets(exp_13.load_incipit()))

    first = [planner.next_edit() for _ in range(notes)]
    second = [planner.next_edit() for _ in range(notes)]

    assert [anchor for anchor, _ in first] == [anchor for anchor, _ in second]
    for (_, before), (_, after) in zip(first, second, strict=True):
        assert {before, after} == {"C5", "D5"}


def test_parse_server_timing_reads_each_stage_duration() -> None:
    header = 'db;dur=1.5, materialize;dur=2;desc="x", export;dur=20.25, total'

    assert exp_13.parse_server_timing(header) == {
        "db": 1.5,
        "materialize": 2.0,
        "export": 20.25,
    }
    assert exp_13.parse_server_timing(None) == {}


def test_latency_stats_of_known_samples() -> None:
    stats = exp_13.latency_stats([1.0, 2.0, 3.0, 4.0])

    assert stats == {
        "count": 4,
        "mean_ms": 2.5,
        "median_ms": 2.5,
        "p95_ms": 3.85,
        "min_ms": 1.0,
        "max_ms": 4.0,
    }
    assert exp_13.latency_stats([]) == {"count": 0}


def test_run_measures_both_flows_with_the_clock_and_writes_only_to_output(
    tmp_path: Path,
) -> None:
    summary = exp_13.run_experiment(
        output_dir=tmp_path,
        sizes=("incipit",),
        edit_counts=(0, 3),
        runs=2,
        label="prueba",
        clock=_TickClock(),
    )

    assert summary["simulated"] is False
    written = json.loads((tmp_path / exp_13.SUMMARY_FILENAME).read_text(encoding="utf-8"))
    assert written == summary
    run_info = json.loads((tmp_path / exp_13.RUN_INFO_FILENAME).read_text(encoding="utf-8"))
    assert run_info["experiment"] == exp_13.EXPERIMENT
    assert run_info["label"] == "prueba"

    five = summary["configurations"]["incipit/3_edits/five_requests"]
    assert five["available"] is True
    assert five["requests_per_edit"] == 5
    assert [s["prior_edits"] for s in five["samples"]] == [4, 5]
    # Cada petición lee el reloj dos veces (1 ms) y el ciclo, dos más: 5 peticiones = 11 ms.
    assert [s["total_ms"] for s in five["samples"]] == pytest.approx([11.0, 11.0])
    assert all(r["ms"] == pytest.approx(1.0) for s in five["samples"] for r in s["requests"])

    single = summary["configurations"]["incipit/3_edits/single_trip"]
    assert single["available"] is True
    assert single["requests_per_edit"] == 1
    assert [s["total_ms"] for s in single["samples"]] == pytest.approx([3.0, 3.0])
    # La API dice en qué se le fue el tiempo, por etapas.
    stages = single["server_timing_stats"]
    assert {"db", "materialize", "export", "serialize"} <= set(stages)


def test_unknown_flow_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        exp_13.run_experiment(output_dir=tmp_path, flows=("tres_viajes",), runs=1)
