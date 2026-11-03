"""Pruebas de `exp_15`: HOMR sobre el conjunto de referencia (#234, ADR-0056).

Las comparaciones se prueban con partituras hechas a mano; la ejecución completa, con un
mundo en un directorio temporal (PDF de mentira con su imagen ya rasterizada, verdad en
MusicXML y un motor que devuelve una lectura fija). Nada se escribe en `results/` ni en `data/`.
"""

from __future__ import annotations

import csv
import itertools
import json
import zipfile
from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from cadenza.domain import (
    Event,
    EventKind,
    KeySignature,
    Measure,
    Part,
    ScoreIR,
    Staff,
    TimeSignature,
)
from cadenza.interchange import score_ir_to_musicxml

from ml.experiments import common
from ml.experiments import exp_15_reference_set as exp_15
from ml.experiments.common import sha256_of_file

C = TimeSignature(4, 4, "common")
CUT = TimeSignature(2, 2, "cut")
FOUR = TimeSignature(4, 4)
TWO = TimeSignature(2, 2)
THREE = TimeSignature(3, 4)


def _quarters(count: int) -> tuple[Event, ...]:
    return tuple(
        Event(kind=EventKind.NOTE, pitch="C5", duration_beats=Fraction(1)) for _ in range(count)
    )


def _triplets(count: int) -> tuple[Event, ...]:
    return tuple(
        Event(kind=EventKind.NOTE, pitch="C5", duration_beats=Fraction(1, 3)) for _ in range(count)
    )


def _measure(
    number: int,
    time: TimeSignature | None,
    key: int | None = None,
    events: tuple[Event, ...] | None = None,
) -> Measure:
    beats = 4 if time is None else time.beats * 4 // time.beat_type
    return Measure(
        number=number,
        events=_quarters(beats) if events is None else events,
        time_signature=time,
        key_signature=None if key is None else KeySignature(key),
    )


def _score(*staves: Sequence[Measure]) -> ScoreIR:
    return ScoreIR(
        parts=tuple(
            Part(id=f"p{i}", staves=(Staff(id=f"s{i}", measures=tuple(staff)),))
            for i, staff in enumerate(staves)
        )
    )


# ---------------------------------------------------------------------------- alineación


def test_map_index_is_proportional_and_keeps_the_ends() -> None:
    assert [exp_15.map_index(p, 5, 5) for p in range(5)] == [0, 1, 2, 3, 4]
    assert exp_15.map_index(0, 22, 23) == 0
    assert exp_15.map_index(21, 22, 23) == 22
    assert exp_15.map_index(10, 22, 23) == 10
    assert exp_15.map_index(3, 1, 7) == 0
    with pytest.raises(ValueError):
        exp_15.map_index(0, 3, 0)


# ---------------------------------------------------------------------------- compás


def test_a_cut_segment_read_with_numbers_has_the_right_meter_and_the_wrong_symbol() -> None:
    truth = [_measure(1, THREE), _measure(2, THREE), _measure(3, CUT), _measure(4, CUT)]
    read = [_measure(1, THREE), _measure(2, THREE), _measure(3, TWO), _measure(4, TWO)]

    result = exp_15.compare_time(truth, [0, 1, 2, 3], [read], tolerance=1)
    counts = result["counts"]

    assert [s["label"] for s in result["truth_segments"]] == ["3/4", "¢"]
    assert counts["segments_page_start"] == 1
    assert counts["segments_page_start_notation_correct"] == 1
    assert counts["segments_mid_page"] == 1
    assert counts["segments_mid_page_detected"] == 1
    assert counts["segments_mid_page_meter_correct"] == 1
    assert counts.get("segments_mid_page_notation_correct", 0) == 0
    assert counts["printed_measures"] == 4
    assert counts["printed_measures_meter_correct"] == 4
    assert counts["printed_measures_notation_correct"] == 2
    assert counts.get("spurious_changes", 0) == 0
    # El símbolo, con `time_symbol_agreement`: los dos compases de ¢ leídos con números.
    assert result["symbol_agreement"] == {"correct": 0, "wrong": 2}
    assert result["changes"][1]["truth"] == "¢" and result["changes"][1]["read"] == "2/2"


def test_a_segment_that_began_on_an_earlier_page_is_counted_apart() -> None:
    truth = [_measure(1, C), _measure(2, C), _measure(3, C), _measure(4, THREE)]
    read = [_measure(1, None), _measure(2, None), _measure(3, THREE)]

    result = exp_15.compare_time(truth, [1, 2, 3], [read], tolerance=1)
    counts = result["counts"]

    assert result["inherited_measures_per_staff"] == 2
    assert counts["inherited_measures"] == 2
    assert counts["inherited_measures_missing"] == 2
    assert counts["segments_mid_page_notation_correct"] == 1
    assert counts.get("segments_page_start", 0) == 0
    assert result["symbol_agreement"] == {"correct": 0, "wrong": 0}


def test_a_courtesy_signature_at_the_end_is_not_a_spurious_change() -> None:
    truth = [_measure(1, FOUR), _measure(2, FOUR), _measure(3, FOUR), _measure(4, THREE)]
    # HOMR lee la indicación de cortesía del final como un compás más, con el cambio.
    read = [_measure(1, FOUR), _measure(2, FOUR), _measure(3, FOUR), _measure(4, THREE, events=())]

    result = exp_15.compare_time(truth, [0, 1, 2], [read], tolerance=1)

    assert result["courtesy_after_page"] == "3/4"
    assert result["counts"]["courtesy_changes_read"] == 1
    assert result["counts"]["courtesy_changes_meter_correct"] == 1
    assert result["counts"]["empty_measures_dropped"] == 1
    assert result["counts"].get("spurious_changes", 0) == 0
    # El compás vacío no cuenta al alinear: los tres compases de la página, bien leídos.
    assert result["counts"]["printed_measures_meter_correct"] == 3
    assert result["read_staves"][0]["measures"] == 3


def test_a_courtesy_read_with_another_meter_is_read_but_wrong() -> None:
    truth = [_measure(1, FOUR), _measure(2, FOUR), _measure(3, THREE)]
    read = [_measure(1, FOUR), _measure(2, FOUR), _measure(3, TWO, events=())]

    counts = exp_15.compare_time(truth, [0, 1], [read], tolerance=1)["counts"]

    assert counts["courtesy_changes_read"] == 1
    assert counts.get("courtesy_changes_meter_correct", 0) == 0


def test_a_courtesy_without_a_change_after_the_page_is_spurious() -> None:
    truth = [_measure(1, FOUR), _measure(2, FOUR), _measure(3, FOUR)]
    read = [_measure(1, FOUR), _measure(2, FOUR), _measure(3, THREE, 2, events=())]

    time = exp_15.compare_time(truth, [0, 1], [read], tolerance=1)["counts"]
    keys = exp_15.compare_keys(truth, [0, 1], [read], tolerance=1)["counts"]

    assert time["spurious_courtesy_changes"] == 1
    assert time.get("courtesy_changes", 0) == 0
    assert keys["spurious_courtesy_changes"] == 1


def test_an_empty_courtesy_measure_mid_page_gives_its_key_to_the_next_one() -> None:
    staff = [
        _measure(1, THREE, -5),
        _measure(2, TWO, 3, events=()),
        _measure(3, TWO),
        _measure(4, TWO),
    ]

    prepared = exp_15.prepare_read_staves([staff])[0]

    assert [m.number for m in prepared.measures] == [1, 3, 4]
    assert prepared.trailing is None and prepared.dropped == 1
    assert exp_15.effective_keys(prepared.measures) == [-5, 3, 3]

    truth = [_measure(1, THREE, -5), _measure(2, CUT, 3), _measure(3, CUT)]
    keys = exp_15.compare_keys(truth, [0, 1, 2], [staff], tolerance=0)["counts"]
    time = exp_15.compare_time(truth, [0, 1, 2], [staff], tolerance=0)["counts"]
    assert keys["changes_correct"] == 1 and keys["measures_correct"] == 3
    assert time["segments_mid_page_meter_correct"] == 1


def test_only_a_measure_empty_in_every_staff_is_a_courtesy_measure() -> None:
    upper = [_measure(1, FOUR), _measure(2, FOUR), _measure(3, FOUR, events=())]
    lower = [_measure(1, FOUR, events=()), _measure(2, FOUR), _measure(3, FOUR, events=())]

    prepared = exp_15.prepare_read_staves([upper, lower])

    assert [len(staff.measures) for staff in prepared] == [2, 2]
    assert [staff.dropped for staff in prepared] == [1, 1]
    assert prepared[1].measures[0].events == ()
    assert exp_15.courtesy_columns([upper, lower]) == {2}


def test_a_key_courtesy_is_checked_against_the_next_page() -> None:
    truth = [_measure(1, FOUR, 3), _measure(2, FOUR), _measure(3, FOUR, -5)]
    right = [_measure(1, FOUR, 3), _measure(2, FOUR), _measure(3, FOUR, -5, events=())]
    wrong = [_measure(1, FOUR, 3), _measure(2, FOUR), _measure(3, FOUR, -4, events=())]

    result = exp_15.compare_keys(truth, [0, 1], [right, wrong], tolerance=1)

    assert result["courtesy_after_page"] == -5
    assert result["counts"]["courtesy_changes_read"] == 2
    assert result["counts"]["courtesy_changes_correct"] == 1


def test_a_change_read_far_from_any_change_of_the_truth_is_spurious() -> None:
    truth = [_measure(n, FOUR) for n in range(1, 7)]
    read = [_measure(1, FOUR), _measure(2, FOUR), _measure(3, FOUR)] + [
        _measure(n, THREE) for n in range(4, 7)
    ]

    result = exp_15.compare_time(truth, list(range(6)), [read], tolerance=1)

    assert result["counts"]["spurious_changes"] == 1
    assert result["read_staves"][0]["spurious_changes"] == [3]
    assert result["counts"]["printed_measures_meter_correct"] == 3


def test_a_change_read_beyond_the_tolerance_is_not_detected() -> None:
    truth = [_measure(n, FOUR if n < 3 else THREE) for n in range(1, 7)]
    read = [_measure(n, FOUR if n < 6 else THREE) for n in range(1, 7)]

    counts = exp_15.compare_time(truth, list(range(6)), [read], tolerance=1)["counts"]
    assert counts.get("segments_mid_page_detected", 0) == 0
    counts = exp_15.compare_time(truth, list(range(6)), [read], tolerance=3)["counts"]
    assert counts["segments_mid_page_detected"] == 1


def test_each_read_staff_is_compared() -> None:
    truth = [_measure(1, C), _measure(2, C)]
    good = [_measure(1, C), _measure(2, C)]
    plain = [_measure(1, FOUR), _measure(2, FOUR)]

    result = exp_15.compare_time(truth, [0, 1], [good, plain], tolerance=1)

    assert result["counts"]["segments_page_start"] == 2
    assert result["counts"]["segments_page_start_notation_correct"] == 1
    assert result["symbol_agreement"] == {"correct": 2, "wrong": 2}


# ---------------------------------------------------------------------------- armadura


def test_keys_at_the_page_start_at_each_change_and_per_measure() -> None:
    truth = [_measure(1, THREE, -5), _measure(2, THREE), _measure(3, CUT, 3), _measure(4, CUT)]
    read = [_measure(1, THREE, -5), _measure(2, THREE), _measure(3, TWO, 2), _measure(4, TWO)]

    result = exp_15.compare_keys(truth, [0, 1, 2, 3], [read], tolerance=1)
    counts = result["counts"]

    assert result["truth_start"] == -5
    assert result["truth_changes"] == [{"measure": 3, "fifths": 3}]
    assert counts["page_starts_correct"] == 1
    assert counts["changes_detected"] == 1
    assert counts.get("changes_correct", 0) == 0
    assert counts["measures_correct"] == 2
    assert counts.get("spurious_changes", 0) == 0


def test_a_page_inherits_the_key_and_a_read_without_key_is_c_major() -> None:
    truth = [_measure(1, FOUR, 4), _measure(2, FOUR), _measure(3, FOUR)]
    read = [_measure(1, FOUR), _measure(2, FOUR)]

    counts = exp_15.compare_keys(truth, [1, 2], [read], tolerance=1)["counts"]

    assert counts.get("page_starts_correct", 0) == 0
    assert counts.get("measures_correct", 0) == 0
    assert exp_15.effective_keys(read) == [0, 0]


# ---------------------------------------------------------------------------- tresillos


def test_tuplet_measures_are_found_by_kind_and_checked_both_ways() -> None:
    truth = [
        _measure(1, FOUR),
        _measure(2, FOUR, events=_triplets(12)),
        _measure(3, FOUR),
        _measure(4, FOUR, events=_triplets(12)),
    ]
    read = [
        _measure(1, FOUR, events=_triplets(12)),
        _measure(2, FOUR, events=_triplets(12)),
        _measure(3, FOUR),
        _measure(4, FOUR),
        _measure(5, FOUR),
        _measure(6, FOUR),
        _measure(7, FOUR, events=_triplets(3) + _quarters(3)),
    ]
    kinds = {2: "implicit", 4: "marked"}

    result = exp_15.compare_tuplets([truth], [0, 1, 2, 3], [read], kinds, tolerance=0)
    counts = result["counts"]

    # 4 compases en la verdad y 7 en la lectura: el 1 va al 2 (sin tresillos) y el 3 al 6 (con).
    assert counts["truth_measures_marked"] == 1
    assert counts["truth_measures_marked_read"] == 1
    assert counts["truth_measures_implicit"] == 1
    assert counts.get("truth_measures_implicit_read", 0) == 0
    assert counts["read_measures"] == 3
    assert counts["read_measures_in_truth"] == 1
    assert counts["truth_notes"] == 24
    assert counts["read_notes"] == 27


def _musicxml_with_tuplets() -> str:
    def note(tuplet: str) -> str:
        return (
            "<note><pitch><step>C</step><octave>5</octave></pitch><duration>1</duration>"
            "<type>eighth</type><time-modification><actual-notes>3</actual-notes>"
            f"<normal-notes>2</normal-notes></time-modification><notations>{tuplet}</notations>"
            "</note>"
        )

    shown = note('<tuplet type="start" bracket="yes"/>')
    hidden = note('<tuplet type="start" bracket="no" show-number="none"/>')
    return (
        '<?xml version="1.0"?><score-partwise version="3.1"><part-list><score-part id="P1">'
        '<part-name>V</part-name></score-part></part-list><part id="P1">'
        f'<measure number="1">{shown}</measure>'
        f'<measure number="2">{hidden}</measure>'
        f'<measure number="3">{shown}{hidden}</measure>'
        '<measure number="X4"></measure>'
        "</part></score-partwise>"
    )


def test_tuplet_display_is_read_from_musicxml_and_mxl(tmp_path: Path) -> None:
    xml = _musicxml_with_tuplets()
    plain = tmp_path / "truth.musicxml"
    plain.write_text(xml, encoding="utf-8")
    packed = tmp_path / "truth.mxl"
    with zipfile.ZipFile(packed, "w") as archive:
        archive.writestr(
            "META-INF/container.xml",
            '<container><rootfiles><rootfile full-path="score.xml"/></rootfiles></container>',
        )
        archive.writestr("score.xml", xml)

    expected = {1: "marked", 2: "implicit", 3: "mixed"}
    assert exp_15.tuplet_display_by_measure(plain) == expected
    assert exp_15.tuplet_display_by_measure(packed) == expected


# ---------------------------------------------------------------------------- partes


def test_layout_compares_parts_and_staves_per_part() -> None:
    voice = [_measure(1, FOUR)]
    truth = ScoreIR(
        parts=(
            Part(id="v", staves=(Staff(id="v0", measures=tuple(voice)),)),
            Part(
                id="p",
                staves=(
                    Staff(id="p0", measures=tuple(voice)),
                    Staff(id="p1", measures=tuple(voice)),
                ),
            ),
        )
    )
    flat = _score(voice, voice, voice)

    assert exp_15.compare_layout(truth, truth)["layout_correct"] is True
    result = exp_15.compare_layout(truth, flat)
    assert result["truth"] == [1, 2] and result["read"] == [1, 1, 1]
    assert result["staves_correct"] is True
    assert result["parts_correct"] is False
    assert result["layout_correct"] is False


def _notes(*pitches: str) -> tuple[Event, ...]:
    return tuple(
        Event(kind=EventKind.NOTE, pitch=pitch, duration_beats=Fraction(1)) for pitch in pitches
    )


def _voice_and_hands(
    voice: Sequence[Measure], right: Sequence[Measure], left: Sequence[Measure]
) -> ScoreIR:
    return ScoreIR(
        parts=(
            Part(id="v", staves=(Staff(id="v0", measures=tuple(voice)),)),
            Part(
                id="p",
                staves=(
                    Staff(id="p0", measures=tuple(right)),
                    Staff(id="p1", measures=tuple(left)),
                ),
            ),
        )
    )


def test_staff_content_counts_measures_read_in_their_own_staff() -> None:
    # Voz, mano derecha y mano izquierda, dos compases (#239).
    voice = [_measure(1, FOUR, events=_notes("A4", "B4", "C5", "D5")), _measure(2, None)]
    right = [
        _measure(1, FOUR, events=_notes("E5", "G5", "E5", "G5")),
        _measure(2, None, events=_notes("F5", "A5", "F5", "A5")),
    ]
    left = [
        _measure(1, FOUR, events=_notes("C3", "G3", "C3", "G3")),
        _measure(2, None, events=_notes("D3", "A3", "D3", "A3")),
    ]
    truth = _voice_and_hands(voice, right, left)

    assert exp_15.compare_page(truth, truth, 1, 2, {}, 1)["staves"] == {
        "units": 6,
        "in_place": 6,
        "elsewhere": 0,
        "missing": 0,
    }

    # HOMR junta la voz y la mano derecha en el primer compás: lo de la mano derecha sale en el
    # pentagrama de la voz y la mano izquierda, en el de la mano derecha.
    merged = [
        _measure(1, FOUR, events=_notes("A4", "B4", "C5", "D5", "E5", "G5")),
        voice[1],
    ]
    read = _voice_and_hands(merged, [left[0], right[1]], [_measure(1, FOUR, events=()), left[1]])
    staves = exp_15.compare_page(truth, read, 1, 2, {}, 1)["staves"]

    # La voz del c. 1 sigue en su pentagrama (comparte más con ella que con la mano derecha);
    # la mano derecha está en otro, la izquierda no se leyó en el suyo.
    assert staves == {"units": 6, "in_place": 4, "elsewhere": 1, "missing": 1}


def test_staff_content_ignores_measures_without_notes_in_the_truth() -> None:
    rest = (Event(kind=EventKind.REST, pitch=None, duration_beats=Fraction(4)),)
    staff = [_measure(1, FOUR, events=rest)]
    truth = _score(staff)

    assert exp_15.compare_page(truth, truth, 1, 1, {}, 1)["staves"]["units"] == 0
    assert exp_15.compare_page(truth, ScoreIR(parts=()), 1, 1, {}, 1)["staves"]["units"] == 0


def test_page_features_come_from_the_truth_of_the_page() -> None:
    staff = [
        _measure(1, THREE, -5),
        _measure(2, THREE),
        _measure(3, CUT, 3),
        _measure(4, CUT, events=_triplets(6)),
        _measure(5, C, events=_triplets(12)),
    ]
    truth = ScoreIR(
        parts=(
            Part(id="v", staves=(Staff(id="v0", measures=tuple(staff)),)),
            Part(
                id="p",
                staves=(
                    Staff(id="p0", measures=tuple(staff)),
                    Staff(id="p1", measures=tuple(staff)),
                ),
            ),
        )
    )
    kinds = {4: "marked", 5: "implicit"}

    assert exp_15.page_features(truth, 1, 2, kinds) == ["voice_piano"]
    assert exp_15.page_features(truth, 2, 4, kinds) == [
        "key_change",
        "time_change",
        "time_symbol_cut",
        "tuplets_marked",
        "voice_piano",
    ]
    # El C del compás 5 se imprime al principio de esa página: no es un cambio a mitad de página.
    assert exp_15.page_features(truth, 5, 5, kinds) == [
        "time_symbol_common",
        "tuplets_implicit",
        "voice_piano",
    ]


# ---------------------------------------------------------------------------- PrIMuS


def test_primus_pair_separates_meter_from_symbol() -> None:
    truth = _score([_measure(1, C), _measure(2, C)])
    read_four = _score([_measure(1, FOUR), _measure(2, FOUR)])
    read_three = _score([_measure(1, THREE), _measure(2, THREE)])

    result = exp_15.compare_primus_pair(read_four, truth)
    assert result["meter_correct"] is True
    assert result["notation_correct"] is False
    assert (result["symbol_correct"], result["symbol_wrong"]) == (0, 2)
    assert (result["truth"], result["read"]) == ("C", "4/4")

    result = exp_15.compare_primus_pair(read_three, truth)
    assert result["numerator_correct"] is False
    assert result["denominator_correct"] is True


# ---------------------------------------------------------------------------- mundo completo


class _FixedEngine:
    """Un motor que devuelve siempre la misma lectura y cuenta las llamadas."""

    def __init__(self, xml_text: str) -> None:
        self.xml_text = xml_text
        self.calls: list[Path] = []

    def transcribe_musicxml(self, image_path: Path) -> str:
        assert image_path.is_file()
        self.calls.append(image_path)
        return self.xml_text


def _voice_piano(measures: Sequence[Measure]) -> ScoreIR:
    return ScoreIR(
        parts=(
            Part(id="v", staves=(Staff(id="v0", measures=tuple(measures)),)),
            Part(
                id="p",
                staves=(
                    Staff(id="p0", measures=tuple(measures)),
                    Staff(id="p1", measures=tuple(measures)),
                ),
            ),
        )
    )


def _build_world(root: Path) -> dict[str, Any]:
    data = root / "data"
    pages = root / "pages"
    (data / "reference" / "scans").mkdir(parents=True)
    (data / "reference" / "truth").mkdir(parents=True)
    pages.mkdir()
    pdf = data / "reference" / "scans" / "song.pdf"
    pdf.write_bytes(b"%PDF de prueba")
    truth_measures = [_measure(1, THREE, -1), _measure(2, THREE), _measure(3, CUT, 2)]
    truth_path = data / "reference" / "truth" / "song.musicxml"
    truth_path.write_text(score_ir_to_musicxml(_voice_piano(truth_measures)), encoding="utf-8")
    image = pages / "song-p1.png"
    image.write_bytes(b"imagen rasterizada de prueba")

    # PrIMuS: un incipit leído y otro que HOMR no pudo transcribir.
    primus = data / "primus"
    predictions = primus / "predictions"
    predictions.mkdir(parents=True)
    truth_incipit = primus / "a.musicxml"
    truth_incipit.write_text(score_ir_to_musicxml(_score([_measure(1, C)])), encoding="utf-8")
    (predictions / "a.musicxml").write_text(
        score_ir_to_musicxml(_score([_measure(1, THREE)])), encoding="utf-8"
    )
    (predictions / "failures.json").write_text(json.dumps([{"id": "b"}]), encoding="utf-8")
    primus_manifest = data / "manifest.json"
    primus_manifest.write_text(
        json.dumps(
            {
                "corpus": "primus",
                "entries": [
                    {
                        "id": "a",
                        "ground_truth": "primus/a.musicxml",
                        "ground_truth_sha256": sha256_of_file(truth_incipit),
                    },
                    {"id": "b", "ground_truth": "primus/b.mei", "ground_truth_sha256": "x"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = {
        "rasterization": {"tool": "pdftoppm", "tool_version": "24.04.0", "dpi": 300},
        "scans": [{"id": "s", "path": "reference/scans/song.pdf", "sha256": sha256_of_file(pdf)}],
        "truths": [
            {
                "id": "t",
                "path": "reference/truth/song.musicxml",
                "sha256": sha256_of_file(truth_path),
                "license": "CC0 1.0",
            }
        ],
        "cases": [
            {
                "id": "song-p1",
                "scan": "s",
                "pdf_page": 1,
                "truth": "t",
                "measures": [1, 3],
                "features": ["key_change", "time_change", "time_symbol_cut", "voice_piano"],
                "image": {"path": "song-p1.png", "sha256": sha256_of_file(image)},
            }
        ],
        "primus": [
            {
                "id": "primus-test",
                "manifest": {"path": "manifest.json", "sha256": sha256_of_file(primus_manifest)},
                "predictions": {
                    "path": "primus/predictions",
                    "sha256": exp_15.predictions_digest(predictions),
                },
                "images": "Renders de Verovio, no escaneos",
            }
        ],
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    read_measures = [_measure(1, THREE, -1), _measure(2, THREE), _measure(3, TWO, 1)]
    return {
        "data": data,
        "pages": pages,
        "manifest": manifest_path,
        "manifest_data": manifest,
        "read_xml": score_ir_to_musicxml(_voice_piano(read_measures)),
        "predictions": predictions,
        "truth": truth_path,
        "image": image,
    }


def test_run_measures_the_reference_set_and_writes_its_outputs(tmp_path: Path) -> None:
    world = _build_world(tmp_path)
    engine = _FixedEngine(world["read_xml"])
    out = tmp_path / "out"

    summary = exp_15.run(
        manifest_path=world["manifest"],
        data_dir=world["data"],
        pages_dir=world["pages"],
        output_dir=out,
        engine=engine,
        log=lambda _message: None,
    )

    assert len(engine.calls) == 1
    assert summary["simulated"] is False
    page = summary["pages"][0]
    assert page["comparison"]["layout"]["layout_correct"] is True
    time_counts = page["comparison"]["time"]["counts"]
    # Tres pentagramas leídos, cada uno con el ¢ en números.
    assert time_counts["segments_mid_page_meter_correct"] == 3
    assert time_counts.get("segments_mid_page_notation_correct", 0) == 0
    assert page["comparison"]["key"]["counts"]["changes_detected"] == 3
    assert page["comparison"]["key"]["counts"].get("changes_correct", 0) == 0
    head = summary["headline"]
    assert head["pages"]["time_segments"]["mid_page_meter_correct"]["proportion"] == 1.0
    assert head["primus"]["numerator_correct"] == {"cases": 0, "n": 1, "proportion": 0.0}
    assert head["primus"]["denominator_correct"]["cases"] == 1
    primus = summary["primus"][0]
    assert primus["transcription_failures"] == 1
    assert primus["confusions"] == {"C -> 3/4": 1}
    assert summary["coverage"]["missing"] == ["tuplets_marked", "tuplets_implicit"]
    assert summary["coverage"]["complete"] is False
    run_info = json.loads((out / exp_15.RUN_INFO_NAME).read_text(encoding="utf-8"))
    assert run_info["experiment"] == "exp_15"
    assert run_info["simulated"] is False
    assert run_info["manifest_sha256"] == sha256_of_file(world["manifest"])
    assert (out / exp_15.SUMMARY_NAME).is_file()
    assert (out / exp_15.PREDICTIONS_DIR_NAME / "song-p1.musicxml").read_text(
        encoding="utf-8"
    ) == world["read_xml"]
    with (out / exp_15.PAGES_CSV_NAME).open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["case"] for row in rows] == ["song-p1"]
    staves = page["comparison"]["staves"]
    assert head["pages"]["staves_in_place"]["n"] == staves["units"] > 0
    assert rows[0]["staves_in_place"] == str(staves["in_place"])
    with (out / exp_15.PRIMUS_CSV_NAME).open(encoding="utf-8") as handle:
        assert [row["id"] for row in csv.DictReader(handle)] == ["a"]

    # Con --reuse-predictions no se vuelve a transcribir la misma imagen.
    exp_15.run(
        manifest_path=world["manifest"],
        data_dir=world["data"],
        pages_dir=world["pages"],
        output_dir=out,
        engine=engine,
        reuse_predictions=True,
        log=lambda _message: None,
    )
    assert len(engine.calls) == 1


def test_run_without_output_dir_writes_to_the_redirected_results(tmp_path: Path) -> None:
    world = _build_world(tmp_path)

    exp_15.run(
        manifest_path=world["manifest"],
        data_dir=world["data"],
        pages_dir=world["pages"],
        engine=_FixedEngine(world["read_xml"]),
        log=lambda _message: None,
    )

    assert (common.RESULTS_DIR / exp_15.SUMMARY_NAME).is_file()


def test_run_fails_with_the_list_of_missing_or_changed_files(tmp_path: Path) -> None:
    world = _build_world(tmp_path)
    (world["data"] / "reference" / "scans" / "song.pdf").unlink()
    world["truth"].write_text("otra verdad", encoding="utf-8")
    (world["predictions"] / "extra.musicxml").write_text("<x/>", encoding="utf-8")
    engine = _FixedEngine(world["read_xml"])

    with pytest.raises(exp_15.ReferenceSetError) as error:
        exp_15.run(
            manifest_path=world["manifest"],
            data_dir=world["data"],
            pages_dir=world["pages"],
            output_dir=tmp_path / "out",
            engine=engine,
            log=lambda _message: None,
        )

    message = str(error.value)
    assert "falta el PDF s" in message
    assert "la verdad t: su sha256 no es el del manifiesto" in message
    assert "las predicciones de primus-test: su huella no es la del manifiesto" in message
    assert engine.calls == []
    assert not (tmp_path / "out").exists()


def test_run_fails_without_the_manifest(tmp_path: Path) -> None:
    with pytest.raises(exp_15.ReferenceSetError, match="falta el manifiesto"):
        exp_15.run(
            manifest_path=tmp_path / "no.json",
            data_dir=tmp_path,
            output_dir=tmp_path / "out",
            engine=_FixedEngine(""),
        )


def test_an_image_that_is_not_the_one_of_the_manifest_stops_the_run(tmp_path: Path) -> None:
    world = _build_world(tmp_path)
    world["image"].write_bytes(b"otros pixeles")
    engine = _FixedEngine(world["read_xml"])

    with pytest.raises(exp_15.ReferenceSetError, match="no son las del manifiesto"):
        exp_15.run(
            manifest_path=world["manifest"],
            data_dir=world["data"],
            pages_dir=world["pages"],
            output_dir=tmp_path / "out",
            engine=engine,
            log=lambda _message: None,
        )
    assert engine.calls == []


def test_a_missing_image_is_rasterized_with_the_manifest_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = _build_world(tmp_path)
    content = world["image"].read_bytes()
    world["image"].unlink()
    calls: list[tuple[Path, int, int, Path]] = []

    def fake_rasterize(exe: str, pdf: Path, page: int, dpi: int, target: Path) -> None:
        calls.append((pdf, page, dpi, target))
        target.write_bytes(content)

    monkeypatch.setattr(exp_15, "find_pdftoppm", lambda explicit: "pdftoppm")
    monkeypatch.setattr(exp_15, "pdftoppm_version", lambda exe: "24.04.0")
    monkeypatch.setattr(exp_15, "rasterize_page", fake_rasterize)
    manifest = exp_15.load_manifest(world["manifest"])

    info = exp_15.prepare_pages(manifest, world["data"], world["pages"], None)

    assert info["generated"] == ["song-p1"]
    assert calls == [
        (world["data"] / "reference" / "scans" / "song.pdf", 1, 300, world["pages"] / "song-p1.png")
    ]
    # Ya está: no se vuelve a rasterizar.
    assert exp_15.prepare_pages(manifest, world["data"], world["pages"], None)["generated"] == []


def test_the_manifest_must_agree_with_the_truth_of_its_pages(tmp_path: Path) -> None:
    world = _build_world(tmp_path)
    data = world["manifest_data"]
    data["cases"][0]["features"] = ["voice_piano"]
    world["manifest"].write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(exp_15.ReferenceSetError, match="revisa los compases"):
        exp_15.run(
            manifest_path=world["manifest"],
            data_dir=world["data"],
            pages_dir=world["pages"],
            output_dir=tmp_path / "out",
            engine=_FixedEngine(world["read_xml"]),
            log=lambda _message: None,
        )


def test_the_versioned_manifest_covers_every_feature_and_spares_the_study_bank() -> None:
    manifest = exp_15.load_manifest()
    raw = json.loads(exp_15.MANIFEST_PATH.read_text(encoding="utf-8"))

    covered = {feature for case in manifest.cases for feature in case.features}
    # El numerador lo cubre PrIMuS; lo demás, alguna página.
    assert set(exp_15.REQUIRED_FEATURES) - covered == {"time_numerator"}
    assert {source.id for source in manifest.primus} == {"primus-exp-03", "primus-exp-12"}
    assert raw["required_features"] == list(exp_15.REQUIRED_FEATURES)
    study_bank = {"lc5007180", "lc5023603", "lc5013945"}
    assert study_bank.isdisjoint(manifest.truths)
    winterreise = [case for case in manifest.cases if case.scan == "imslp-60822"]
    assert {case.pdf_page for case in winterreise} == {64, 65}
    for case in manifest.cases:
        assert len(case.image_sha256) == 64
        assert manifest.truths[case.truth].meta["license"].startswith("CC0")
        assert manifest.scans[case.scan].meta["license"].startswith("Dominio público")
    for source in manifest.primus:
        assert "Verovio" in str(source.meta["images"])
    pages = [(case.scan, case.pdf_page) for case in manifest.cases]
    assert len(set(pages)) == len(pages)
    for truth in manifest.truths:
        ranges = sorted(
            (case.first_measure, case.last_measure)
            for case in manifest.cases
            if case.truth == truth
        )
        assert ranges[0][0] == 1
        for (_, end), (start, _) in itertools.pairwise(ranges):
            assert start == end + 1


# ---------------------------------------------------------------------------- de la revisión


def test_one_read_tuplet_measure_does_not_count_for_two_truth_measures() -> None:
    truth = [
        _measure(1, FOUR),
        _measure(2, FOUR, events=_triplets(12)),
        _measure(3, FOUR, events=_triplets(12)),
        _measure(4, FOUR),
    ]
    read = [
        _measure(1, FOUR),
        _measure(2, FOUR, events=_triplets(12)),
        _measure(3, FOUR),
        _measure(4, FOUR),
    ]

    counts = exp_15.compare_tuplets(
        [truth], [0, 1, 2, 3], [read], {2: "marked", 3: "marked"}, tolerance=1
    )["counts"]

    assert counts["truth_measures_marked"] == 2
    assert counts["truth_measures_marked_read"] == 1
    assert counts["read_measures_in_truth"] == 1


def test_a_read_that_flips_around_a_real_change_has_a_spurious_change() -> None:
    truth = [_measure(n, FOUR if n < 4 else THREE) for n in range(1, 7)]
    read = [_measure(n, time) for n, time in enumerate((FOUR, FOUR, THREE, FOUR, THREE, THREE), 1)]

    counts = exp_15.compare_time(truth, list(range(6)), [read], tolerance=1)["counts"]

    # Se empareja el cambio leído que da la métrica buena (q = 2), no el más cercano (q = 3).
    assert counts["segments_mid_page_detected"] == 1
    assert counts["segments_mid_page_meter_correct"] == 1
    assert counts["spurious_changes"] == 2


def test_a_staff_that_homr_does_not_read_counts_as_a_miss() -> None:
    truth = [_measure(1, THREE, -1), _measure(2, CUT, 2)]
    read = [_measure(1, THREE, -1), _measure(2, CUT, 2)]

    time = exp_15.compare_time(truth, [0, 1], [read, read], tolerance=1, truth_staves=3)["counts"]
    keys = exp_15.compare_keys(truth, [0, 1], [read, read], tolerance=1, truth_staves=3)["counts"]
    extra = exp_15.compare_time(truth, [0, 1], [read] * 4, tolerance=1, truth_staves=3)["counts"]

    assert time["missing_staves"] == 1
    assert time["segments_mid_page"] == 3 and time["segments_mid_page_notation_correct"] == 2
    assert time["printed_measures"] == 6 and time["printed_measures_missing"] == 2
    assert keys["changes"] == 3 and keys["changes_correct"] == 2
    assert keys["page_starts"] == 3 and keys["page_starts_correct"] == 2
    assert extra["extra_read_staves"] == 1 and extra["segments_mid_page"] == 3
    symbol = exp_15.compare_time(truth, [0, 1], [read, read], tolerance=1, truth_staves=3)
    # El ¢ del compás 2: bien en los dos pentagramas leídos y mal en el que falta.
    assert symbol["symbol_agreement"] == {"correct": 2, "wrong": 1}


def test_an_empty_reading_counts_every_unit_as_missed() -> None:
    staff = [_measure(1, THREE, -1, events=_triplets(9)), _measure(2, CUT, 2)]
    truth = _voice_piano(staff)

    comparison = exp_15.compare_page(truth, ScoreIR(parts=()), 1, 2, {1: "marked"}, 1)
    page = {"comparison": comparison}
    head = exp_15.headline([page], [])["pages"]

    assert comparison["empty_reading"] is True
    assert head["empty_readings"] == 1
    assert head["missing_staves"] == 3
    assert head["time_segments"]["mid_page_detected"] == {"cases": 0, "n": 3, "proportion": 0.0}
    assert head["key_changes_detected"]["n"] == 3
    assert head["tuplet_measures_marked_read"] == {"cases": 0, "n": 1, "proportion": 0.0}


def test_a_tuplet_without_its_start_in_the_truth_stops_the_features() -> None:
    truth = _score([_measure(1, FOUR, events=_triplets(12))])

    with pytest.raises(exp_15.ReferenceSetError, match="no se sabe si es marcado o implícito"):
        exp_15.page_features(truth, 1, 1, {})


def test_the_predictions_digest_changes_with_the_content(tmp_path: Path) -> None:
    (tmp_path / "a.musicxml").write_text("uno", encoding="utf-8")
    before = exp_15.predictions_digest(tmp_path)
    (tmp_path / "a.musicxml").write_text("dos", encoding="utf-8")

    assert exp_15.predictions_digest(tmp_path) != before


def test_primus_records_unreadable_predictions_and_fails_without_one(tmp_path: Path) -> None:
    world = _build_world(tmp_path)
    (world["predictions"] / "a.musicxml").write_text("no es MusicXML", encoding="utf-8")
    source = exp_15.load_manifest(world["manifest"]).primus[0]

    summary, rows = exp_15.measure_primus(source, world["data"], workers=1)

    assert summary["counts"] == {}
    assert list(summary["prediction_unreadable"]) == ["a"]
    assert [row["status"] for row in rows] == ["prediction_unreadable"]
    head = exp_15.headline([], [summary])["primus"]
    assert head["numerator_correct_with_failures"] == {"cases": 0, "n": 2, "proportion": 0.0}
    assert head["numerator_correct"]["n"] == 0

    (world["predictions"] / "a.musicxml").unlink()
    with pytest.raises(exp_15.ReferenceSetError, match="sin predicción ni fallo registrado"):
        exp_15.measure_primus(source, world["data"], workers=1)


class _OtherEngine(_FixedEngine):
    """Otro motor con la misma lectura: sus predicciones no valen para el primero."""


def test_reused_predictions_must_come_from_the_same_engine(tmp_path: Path) -> None:
    world = _build_world(tmp_path)
    out = tmp_path / "out"
    first = _FixedEngine(world["read_xml"])
    second = _OtherEngine(world["read_xml"])
    common_args: dict[str, Any] = {
        "manifest_path": world["manifest"],
        "data_dir": world["data"],
        "pages_dir": world["pages"],
        "output_dir": out,
        "reuse_predictions": True,
        "log": lambda _message: None,
    }

    exp_15.run(engine=first, **common_args)
    exp_15.run(engine=second, **common_args)
    exp_15.run(engine=second, **common_args)

    assert len(first.calls) == 1
    assert len(second.calls) == 1
