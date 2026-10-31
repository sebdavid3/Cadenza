"""Un corpus de correcciones sintético y pequeño para probar la capa de sugerencias.

Cada «obra» tiene dos incipits en Fa mayor. Lo que HOMR «lee» mal sigue un patrón que la capa
puede aprender: un Si natural que casi siempre es Si bemol (las reglas no lo ven) y, en
algunos incipits, una negra leída como corchea (measure.balance lo ve y ofrece candidatos).
"""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path
from typing import Any

from cadenza.domain import (
    Clef,
    Event,
    EventKind,
    KeySignature,
    Measure,
    Part,
    ScoreIR,
    Staff,
    TimeSignature,
)
from cadenza.learning import assign_split, build_correction_records, primus_work_id

SPLIT_SEED = 11


def _note(pitch: str, beats: str = "1") -> Event:
    return Event(kind=EventKind.NOTE, pitch=pitch, duration_beats=Fraction(beats))


def _score(*measures: tuple[Event, ...]) -> ScoreIR:
    built = tuple(
        Measure(
            number=index + 1,
            events=events,
            time_signature=TimeSignature(4, 4),
            clef=Clef.treble() if index == 0 else None,
            key_signature=KeySignature(fifths=-1) if index == 0 else None,
        )
        for index, events in enumerate(measures)
    )
    return ScoreIR(parts=(Part(id="P1", staves=(Staff(id="P1-S1", measures=built),)),))


def incipit_pair(work: int, index: int) -> tuple[ScoreIR, ScoreIR]:
    """(leído, verdad) de un incipit: el patrón depende de `work` y de `index`."""
    case = (work * 2 + index) % 10
    truth_b = "B4" if case in (7, 8) else "Bb4"
    read_b = "Bb4" if case == 9 else "B4"
    eighth = (work + index) % 3 == 0
    truth = _score(
        (_note("F4"), _note("G4"), _note("A4"), _note(truth_b)),
        (_note("C5"), _note("D5"), _note("E5"), _note("F5")),
    )
    read = _score(
        (_note("F4"), _note("G4"), _note("A4"), _note(read_b)),
        (_note("C5"), _note("D5"), _note("E5", "1/2" if eighth else "1"), _note("F5")),
    )
    return read, truth


def incipit_id(work: int, index: int) -> str:
    return f"{100000 + work:09d}-1_1_{index + 1}"


def corpus_records(works: int = 60) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for work in range(works):
        for index in range(2):
            identifier = incipit_id(work, index)
            read, truth = incipit_pair(work, index)
            split = assign_split(primus_work_id(identifier), seed=SPLIT_SEED)
            records.extend(
                build_correction_records(
                    read, truth, incipit_id=identifier, split=split, verified=True
                )
            )
    return records


def write_corpus(path: Path, works: int = 60) -> Path:
    path.write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in corpus_records(works)),
        encoding="utf-8",
    )
    return path


def small_config(path: Path) -> Path:
    """La configuración del repositorio con umbrales de apoyo y alarmas para un corpus pequeño."""
    repo_config = Path(__file__).resolve().parents[3] / "configs" / "learning" / "suggestions.json"
    raw = json.loads(repo_config.read_text(encoding="utf-8"))
    raw.update({"min_support": 3, "min_alarms": 5, "alpha": 1.0})
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path
