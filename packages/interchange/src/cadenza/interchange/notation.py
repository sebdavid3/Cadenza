"""Puente canónico de notación: MusicXML/MEI/**kern ↔ `ScoreIR` (music21).

Esta es la única frontera de parseo/serialización simbólica del sistema. El
dominio permanece puro: `music21` solo vive aquí. El alcance cubierto es el
corpus objetivo (monofónico y piano simple); la notación muy densa (orquesta,
manuscritos históricos) queda fuera.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Any

from cadenza.domain import Event, EventKind, Measure, Part, ScoreIR, Staff, TimeSignature
from music21 import chord, converter, meter, musicxml, note, stream

_MAX_DENOMINATOR = 1000


class InterchangeError(ValueError):
    """No se pudo interpretar o serializar una partitura."""


def _register_converters() -> None:
    """Registra los importadores de MEI/**kern de converter21 si está instalado."""

    try:
        import converter21
    except ImportError:  # pragma: no cover - depende del extra opcional
        return
    converter21.register()  # pragma: no cover - depende del extra opcional


def _pitch_name(element: Any) -> str | None:
    """Nombre de altura normalizado al vocabulario del dominio (``Eb4``)."""

    pitch = getattr(element, "pitch", None)
    if pitch is None:
        return None
    return str(pitch.nameWithOctave).replace("-", "b")


def _duration(element: Any) -> Fraction | None:
    quarter_length = getattr(element, "quarterLength", None)
    if quarter_length is None:
        return None
    return Fraction(quarter_length).limit_denominator(_MAX_DENOMINATOR)


def _events_from_measure(measure: Any) -> list[Event]:
    events: list[Event] = []
    voices = list(getattr(measure, "voices", ()))
    if voices:
        for voice_index, voice in enumerate(voices):
            events.extend(_events_from_elements(voice.notesAndRests, voice_index))
    else:
        events.extend(_events_from_elements(measure.notesAndRests, 0))
    return events


def _events_from_elements(elements: Any, voice: int) -> list[Event]:
    events: list[Event] = []
    for element in elements:
        if isinstance(element, chord.Chord):
            for chord_note in element.notes:
                events.append(_note_event(chord_note, element, voice))
        else:
            events.append(_note_event(element, element, voice))
    return events


def _note_event(pitch_source: Any, duration_source: Any, voice: int) -> Event:
    is_rest = isinstance(pitch_source, note.Rest)
    return Event(
        kind=EventKind.REST if is_rest else EventKind.NOTE,
        voice=voice,
        pitch=None if is_rest else _pitch_name(pitch_source),
        duration_beats=_duration(duration_source),
    )


def _measure_signature(measure: Any) -> TimeSignature | None:
    signature = measure.timeSignature
    if signature is None:
        signature = measure.getContextByClass(meter.TimeSignature)
    if signature is None:
        return None
    return TimeSignature(int(signature.numerator), int(signature.denominator))


def _measures(part: Any) -> tuple[Measure, ...]:
    found = list(part.getElementsByClass(stream.Measure))
    measures: list[Measure] = []
    for position, measure in enumerate(found, start=1):
        number = measure.number if isinstance(measure.number, int) else position
        measures.append(
            Measure(
                number=number,
                events=tuple(_events_from_measure(measure)),
                time_signature=_measure_signature(measure),
            )
        )
    return tuple(measures)


def music21_stream_to_score_ir(parsed: Any) -> ScoreIR:
    """Convierte un `music21` `Stream`/`Score`/`Part` en un `ScoreIR` neutral."""

    if isinstance(parsed, stream.Opus):
        if not parsed.scores:
            return ScoreIR(parts=())
        parsed = parsed.scores[0]

    raw_parts = list(parsed.parts) if isinstance(parsed, stream.Score) else [parsed]
    parts: list[Part] = []
    for part_index, raw_part in enumerate(raw_parts):
        # Identificador determinista derivado del índice: la identidad lógica del
        # dominio usa índices (Anchor), no los ids corruptibles de la fuente.
        staff = Staff(id=f"part-{part_index}-staff-0", measures=_measures(raw_part))
        parts.append(Part(id=f"part-{part_index}", staves=(staff,)))
    return ScoreIR(parts=tuple(parts))


def musicxml_to_score_ir(xml_text: str) -> ScoreIR:
    """Convierte un documento MusicXML en un `ScoreIR` neutral."""

    try:
        parsed = converter.parseData(xml_text, format="musicxml")
    except Exception as exc:  # pragma: no cover - mensaje accionable
        raise InterchangeError(f"MusicXML no interpretable: {exc}") from exc
    return music21_stream_to_score_ir(parsed)


def read_score(path: Path) -> ScoreIR:
    """Lee cualquier formato soportado por music21 (MusicXML, MEI, **kern)."""

    _register_converters()
    if not path.is_file():
        raise FileNotFoundError(f"score not found: {path}")
    try:
        parsed = converter.parse(str(path))
    except Exception as exc:  # pragma: no cover - mensaje accionable
        raise InterchangeError(f"partitura no interpretable: {path}: {exc}") from exc
    return music21_stream_to_score_ir(parsed)


def _to_music21_pitch(pitch: str) -> str:
    """Traduce la altura del dominio (``Eb4``) al vocabulario de music21 (``E-4``)."""

    return pitch.replace("b", "-")


def _build_measure(measure: Measure) -> Any:
    built = stream.Measure(number=measure.number)
    if measure.time_signature is not None:
        signature = measure.time_signature
        built.insert(0, meter.TimeSignature(f"{signature.beats}/{signature.beat_type}"))
    offset = 0.0
    for event in measure.events:
        duration = float(event.duration_beats) if event.duration_beats is not None else 1.0
        if event.kind is EventKind.REST or event.pitch is None:
            element: Any = note.Rest()
        else:
            element = note.Note(_to_music21_pitch(event.pitch))
        element.duration.quarterLength = duration
        built.insert(offset, element)
        offset += duration
    return built


def score_ir_to_musicxml(score: ScoreIR) -> str:
    """Serializa un `ScoreIR` a MusicXML (base para la exportación, D11)."""

    out = stream.Score()
    for part_index, part in enumerate(score.parts):
        built_part = stream.Part(id=part.id or f"P{part_index + 1}")
        for staff in part.staves:
            for measure in staff.measures:
                built_part.append(_build_measure(measure))
        out.insert(0, built_part)
    exported: bytes = musicxml.m21ToXml.GeneralObjectExporter(out).parse()
    return exported.decode("utf-8")
