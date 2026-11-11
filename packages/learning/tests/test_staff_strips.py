"""Cada pentagrama de la foto con sus compases (#403, ADR-0067).

Las cajas son las que dio HOMR 0.7.0 en la prueba del 2026-11-11 sobre `TS-04` del banco (voz y
piano, dos sistemas de tres compases), en una foto de 2745 x 1380 que HOMR redujo a 1920 x 965 sin
recortar el papel.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any

import pytest
from cadenza.domain import Event, EventKind, Measure, Part, ScoreIR, Staff, Tie
from cadenza.learning.staff_strips import StripError, event_token, plan_strips, strip_sequence

PHOTO = (2745, 1380)

PAIRED = [
    (False, 0.5, 0.0963, 0.8542, 0.0673),
    (True, 0.4974, 0.3367, 0.8490, 0.2292),
    (False, 0.4948, 0.5935, 0.8542, 0.0686),
    (True, 0.4948, 0.8437, 0.8542, 0.2329),
]
ALONE = [
    (False, 0.5, 0.0963, 0.8542, 0.0673),
    (False, 0.5, 0.2543, 0.8542, 0.0646),
    (False, 0.4974, 0.4187, 0.8490, 0.0651),
    (False, 0.4948, 0.5935, 0.8542, 0.0686),
    (False, 0.4948, 0.7574, 0.8542, 0.0634),
    (False, 0.4948, 0.9291, 0.8542, 0.0650),
]


def _reading(
    mode: str, boxes: list[tuple[bool, float, float, float, float]], **extra: Any
) -> dict[str, Any]:
    return {
        "mode": mode,
        "image_shape": [965, 1920],
        "source_shape": [1380, 2745],
        "autocrop": None,
        # Desordenadas: el emparejamiento las ordena de arriba abajo.
        "staves": [
            {"grand": g, "cx": cx, "cy": cy, "w": w, "h": h} for g, cx, cy, w, h in reversed(boxes)
        ],
        **extra,
    }


def _note(pitch: str, beats: str = "1", **extra: Any) -> Event:
    return Event(kind=EventKind.NOTE, pitch=pitch, duration_beats=Fraction(beats), **extra)


def _score() -> ScoreIR:
    def staff(name: str, pitch: str) -> Staff:
        return Staff(
            id=name,
            measures=tuple(Measure(number=n, events=(_note(pitch, "4"),)) for n in range(1, 7)),
        )

    return ScoreIR(
        parts=(
            Part(id="voz", staves=(staff("voz-0", "F4"),)),
            Part(id="piano", staves=(staff("piano-0", "D4"), staff("piano-1", "B2"))),
        )
    )


def _capture(*readings: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {"systems": ["1", "4"], "readings": list(readings), "preprocessed": False, **extra}


def test_each_staff_of_each_system_gets_its_strip_and_its_measures() -> None:
    strips = plan_strips(
        _capture(_reading("paired", PAIRED), _reading("alone", ALONE)), _score(), PHOTO
    )
    assert [(s.system, s.measures, s.staves, s.reading) for s in strips] == [
        (1, (1, 2, 3), ((0, 0),), "alone"),
        (1, (1, 2, 3), ((1, 0),), "alone"),
        (1, (1, 2, 3), ((1, 1),), "alone"),
        (2, (4, 5, 6), ((0, 0),), "alone"),
        (2, (4, 5, 6), ((1, 0),), "alone"),
        (2, (4, 5, 6), ((1, 1),), "alone"),
    ]
    # La voz del sistema 1: de x 186 a 2559 y hasta la mitad del hueco con la mano derecha.
    assert strips[0].box == (186, 24, 2559, 242)
    assert strips[1].box[1] == strips[0].box[3]
    assert strips[-1].box[3] == 1380


def test_the_paired_reading_gives_the_piano_as_one_strip() -> None:
    strips = plan_strips(_capture(_reading("paired", PAIRED)), _score(), PHOTO)
    assert [(s.system, s.staves) for s in strips] == [
        (1, ((0, 0),)),
        (1, ((1, 0), (1, 1))),
        (2, ((0, 0),)),
        (2, ((1, 0), (1, 1))),
    ]


def test_the_paper_crop_moves_the_boxes_into_the_photo() -> None:
    plain = plan_strips(_capture(_reading("alone", ALONE)), _score(), PHOTO)
    # El mismo papel, recortado a 100 px de la izquierda y 50 de arriba de una foto mayor.
    cropped = _reading("alone", ALONE, source_shape=[1480, 2945], autocrop=[100, 50, 2745, 1380])
    moved = plan_strips(_capture(cropped), _score(), (2945, 1480))
    for a, b in zip(plain, moved, strict=True):
        assert b.box[0] - a.box[0] == pytest.approx(100, abs=1)
        assert b.box[1] - a.box[1] == pytest.approx(50, abs=1)


def test_boxes_that_do_not_match_the_score_are_refused_with_the_reason() -> None:
    with pytest.raises(StripError, match="2 sistemas de 3 pentagramas"):
        plan_strips(_capture(_reading("alone", ALONE[:5])), _score(), PHOTO)
    with pytest.raises(StripError, match="preprocesada"):
        plan_strips(_capture(_reading("alone", ALONE), preprocessed=True), _score(), PHOTO)
    with pytest.raises(StripError, match="compás 9"):
        plan_strips({**_capture(_reading("alone", ALONE)), "systems": ["1", "9"]}, _score(), PHOTO)


def test_without_systems_the_whole_page_is_one_system() -> None:
    one = [(False, 0.5, 0.3, 0.8, 0.1), (False, 0.5, 0.6, 0.8, 0.1), (False, 0.5, 0.9, 0.8, 0.1)]
    strips = plan_strips({"readings": [_reading("alone", one)]}, _score(), PHOTO)
    assert {s.measures for s in strips} == {(1, 2, 3, 4, 5, 6)}


def test_event_tokens_and_the_sequence_of_a_strip() -> None:
    assert event_token(_note("F4", "3/4")) == "F4:3/4"
    assert event_token(_note("A4", "0")) == "A4:0"
    assert event_token(_note("G4", "1", is_chord=True, tie=Tie.START)) == "+G4:1~"
    assert event_token(Event(kind=EventKind.REST, duration_beats=Fraction(1))) == "r:1"
    assert event_token(Event(kind=EventKind.REST, duration_beats=Fraction(2), hidden=True)) == "_:2"

    strips = plan_strips(_capture(_reading("paired", PAIRED)), _score(), PHOTO)
    assert strip_sequence(_score(), strips[0]) == "c1: F4:4 | c2: F4:4 | c3: F4:4"
    assert strip_sequence(_score(), strips[1]).count("||") == 1
