"""Pruebas de exportación a MusicXML y MIDI en packages/interchange (Issue #12, ADR-0010)."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from cadenza.application import ScoreExporter
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
from cadenza.interchange import (
    Music21ScoreExporter,
    read_score,
)
from music21 import midi


def _sample_monophonic_score() -> ScoreIR:
    return ScoreIR(
        parts=(
            Part(
                id="P1",
                staves=(
                    Staff(
                        id="staff-1",
                        measures=(
                            Measure(
                                number=1,
                                clef=Clef(sign="G", line=2),
                                key_signature=KeySignature(fifths=0, mode="major"),
                                time_signature=TimeSignature(beats=4, beat_type=4),
                                events=(
                                    Event(
                                        kind=EventKind.NOTE,
                                        voice=0,
                                        pitch="C4",
                                        duration_beats=Fraction(1),
                                    ),
                                    Event(
                                        kind=EventKind.NOTE,
                                        voice=0,
                                        pitch="D4",
                                        duration_beats=Fraction(1),
                                    ),
                                    Event(
                                        kind=EventKind.NOTE,
                                        voice=0,
                                        pitch="E4",
                                        duration_beats=Fraction(1),
                                    ),
                                    Event(
                                        kind=EventKind.NOTE,
                                        voice=0,
                                        pitch="G4",
                                        duration_beats=Fraction(1),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
    )


def _sample_piano_score() -> ScoreIR:
    return ScoreIR(
        parts=(
            Part(
                id="Piano",
                staves=(
                    Staff(
                        id="staff-treble",
                        measures=(
                            Measure(
                                number=1,
                                clef=Clef(sign="G", line=2),
                                time_signature=TimeSignature(beats=4, beat_type=4),
                                events=(
                                    Event(
                                        kind=EventKind.NOTE,
                                        voice=0,
                                        pitch="C5",
                                        duration_beats=Fraction(4),
                                    ),
                                ),
                            ),
                        ),
                    ),
                    Staff(
                        id="staff-bass",
                        measures=(
                            Measure(
                                number=1,
                                clef=Clef(sign="F", line=4),
                                time_signature=TimeSignature(beats=4, beat_type=4),
                                events=(
                                    Event(
                                        kind=EventKind.NOTE,
                                        voice=0,
                                        pitch="C3",
                                        duration_beats=Fraction(4),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
    )


def test_music21_score_exporter_implements_interface() -> None:
    exporter = Music21ScoreExporter()
    assert isinstance(exporter, ScoreExporter)


def test_musicxml_export_roundtrip_equivalence(tmp_path: Path) -> None:
    score = _sample_monophonic_score()
    exporter = Music21ScoreExporter()

    # 1. Exportar a MusicXML
    xml_content = exporter.to_musicxml(score)
    assert "<?xml" in xml_content
    assert "<score-partwise" in xml_content

    # 2. Guardar en disco temporal y re-leer con read_score
    xml_path = tmp_path / "exported.musicxml"
    xml_path.write_text(xml_content, encoding="utf-8")
    reloaded_score = read_score(xml_path)

    # 3. Verificar equivalencia
    assert len(reloaded_score.parts) == len(score.parts)
    orig_measure = score.parts[0].staves[0].measures[0]
    reloaded_measure = reloaded_score.parts[0].staves[0].measures[0]
    assert reloaded_measure.number == orig_measure.number
    assert reloaded_measure.time_signature == orig_measure.time_signature
    assert reloaded_measure.clef == orig_measure.clef

    orig_pitches = [e.pitch for e in orig_measure.events]
    reloaded_pitches = [e.pitch for e in reloaded_measure.events]
    assert reloaded_pitches == orig_pitches

    orig_durs = [e.duration_beats for e in orig_measure.events]
    reloaded_durs = [e.duration_beats for e in reloaded_measure.events]
    assert reloaded_durs == orig_durs


def test_midi_export_and_inspection() -> None:
    score = _sample_monophonic_score()
    exporter = Music21ScoreExporter()

    # 1. Exportar a MIDI
    midi_bytes = exporter.to_midi(score)
    assert isinstance(midi_bytes, bytes)
    # Encabezado estándar MIDI (Header chunk 'MThd')
    assert midi_bytes.startswith(b"MThd")

    # 2. Abrir el archivo MIDI con music21 y verificar su contenido musical
    mf = midi.MidiFile()
    mf.readstr(midi_bytes)
    stream_from_midi = midi.translate.midiFileToStream(mf)

    notes = list(stream_from_midi.recurse().notes)
    assert len(notes) == 4
    extracted_pitches = [n.nameWithOctave for n in notes]
    assert extracted_pitches == ["C4", "D4", "E4", "G4"]


def test_piano_export_musicxml_and_midi(tmp_path: Path) -> None:
    score = _sample_piano_score()
    exporter = Music21ScoreExporter()

    # MusicXML piano
    xml_text = exporter.to_musicxml(score)
    assert "<part" in xml_text

    xml_path = tmp_path / "piano.musicxml"
    xml_path.write_text(xml_text, encoding="utf-8")
    reloaded_piano = read_score(xml_path)
    assert len(reloaded_piano.parts) == 1
    assert len(reloaded_piano.parts[0].staves) == 2

    # MIDI piano
    midi_bytes = exporter.to_midi(score)
    assert midi_bytes.startswith(b"MThd")
    mf = midi.MidiFile()
    mf.readstr(midi_bytes)
    stream_piano = midi.translate.midiFileToStream(mf)
    notes = list(stream_piano.recurse().notes)
    # Debe contener C5 y C3
    pitches = {n.nameWithOctave for n in notes}
    assert "C5" in pitches
    assert "C3" in pitches
