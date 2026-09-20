"""Pruebas de `TimeSignature` y su integración en `Measure`."""

from __future__ import annotations

from fractions import Fraction

import pytest
from cadenza.domain import Event, EventKind, Measure, TimeSignature


def test_quarter_length_common_meters() -> None:
    assert TimeSignature(4, 4).quarter_length == Fraction(4)
    assert TimeSignature(3, 4).quarter_length == Fraction(3)
    assert TimeSignature(6, 8).quarter_length == Fraction(3)
    assert TimeSignature(2, 2).quarter_length == Fraction(4)


def test_roundtrip() -> None:
    signature = TimeSignature(7, 8)
    assert TimeSignature.from_primitive(signature.to_primitive()) == signature


@pytest.mark.parametrize("beats, beat_type", [(0, 4), (-1, 4), (4, 0), (4, 3), (4, -8)])
def test_invalid_meters(beats: int, beat_type: int) -> None:
    with pytest.raises(ValueError, match="must be"):
        TimeSignature(beats, beat_type)


def test_measure_roundtrip_with_meter() -> None:
    measure = Measure(
        number=1,
        events=(Event(kind=EventKind.NOTE, voice=0, pitch="C4", duration_beats=Fraction(1)),),
        time_signature=TimeSignature(4, 4),
    )
    restored = Measure.from_primitive(measure.to_primitive())
    assert restored == measure
    assert restored.time_signature == TimeSignature(4, 4)


def test_measure_roundtrip_without_meter_is_backward_compatible() -> None:
    # Un primitivo de Fase 0/1 sin la clave "time_signature" debe seguir cargando.
    primitive = {"number": 1, "events": []}
    measure = Measure.from_primitive(primitive)
    assert measure.time_signature is None
