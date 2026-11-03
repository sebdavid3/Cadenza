"""El banco de partituras del estudio con participantes (#247, protocolo §2.3).

El manifiesto versionado dice de dónde sale cada partitura, con qué licencia y con qué sha256;
`scripts/build_study_bank.py` regenera las imágenes y las verdades fuera de `data/` y de
`results/`. Aquí se prueba con fuentes sintéticas: las reales (el PDF de IMSLP, PrIMuS y
OpenScore) están en `data/`, que no se versiona.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest

from scripts.build_study_bank import (
    MANIFEST,
    REPO_ROOT,
    BankError,
    apply_errata,
    build_truth,
    check_output_dir,
    load_manifest,
    stable_musicxml,
)

SHA256 = re.compile(r"^[0-9a-f]{64}$")
IDS = ["TS-01", "calentamiento", "TS-02", "TS-03", "TS-04"]


def test_the_manifest_has_the_approved_bank() -> None:
    manifest = load_manifest()

    assert [entry["id"] for entry in manifest["partituras"]] == IDS
    for entry in manifest["partituras"]:
        assert entry["licencia"], entry["id"]
        assert entry["compases"] > 0, entry["id"]
        for kind in ("imagen", "verdad"):
            assert SHA256.match(entry["sha256"][kind]), (entry["id"], kind)
            assert entry["salida"][kind].startswith(entry["id"]), (entry["id"], kind)
        truth = entry["verdad"]
        assert SHA256.match(truth["sha256_origen"]), entry["id"]
        if truth["tipo"] == "openscore":
            first, last = truth["compases"]
            assert last - first + 1 == entry["compases"], entry["id"]
    for source in manifest["fuentes"].values():
        assert SHA256.match(source["sha256"])
        assert source["licencia"]


def test_the_page_images_are_300_dpi_pages_of_the_pdf() -> None:
    for entry in load_manifest()["partituras"]:
        image = entry["imagen"]
        if image["origen"] != "pdf":
            continue
        assert image["ppp"] == 300
        # La página del PDF es la impresa + 4 (comprobado en las tres).
        assert image["pagina_pdf"] == image["pagina_impresa"] + 4


def test_the_output_folder_is_not_versioned() -> None:
    folder = load_manifest()["salida"]
    ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert f"/{folder}/" in ignored
    assert folder not in ("data", "results")


@pytest.mark.parametrize("name", ["data", "results", "data/banco", "results/x/y"])
def test_the_bank_is_never_written_in_data_or_results(tmp_path: Path, name: str) -> None:
    with pytest.raises(BankError):
        check_output_dir(tmp_path / name, tmp_path)


def test_the_bank_may_be_written_elsewhere(tmp_path: Path) -> None:
    check_output_dir(tmp_path / "banco_estudio", tmp_path)


_MEI = """<?xml version="1.0" encoding="UTF-8"?>
<mei xmlns="http://www.music-encoding.org/ns/mei" meiversion="4.0.0">
  <meiHead><fileDesc><titleStmt><title /></titleStmt><pubStmt /></fileDesc></meiHead>
  <music><body><mdiv><score>
    <scoreDef key.sig="1s" meter.sym="common">
      <staffGrp><staffDef clef.shape="G" clef.line="2" n="1" lines="5" /></staffGrp>
    </scoreDef>
    <section>
      <measure right="single"><staff n="1"><layer>
        <note dur="4" oct="4" pname="g" />
        <beam><note dur="8" oct="4" pname="f" /><note dur="8" oct="4" pname="g" /></beam>
        <note dur="2" oct="4" pname="a" />
      </layer></staff></measure>
    </section>
  </score></mdiv></body></music>
</mei>"""

_SEMANTIC = (
    "clef-G2\tkeySignature-GM\ttimeSignature-C\tnote-G4_quarter\tnote-F#4_eighth\t"
    "note-G4_eighth\tnote-A4_half\tbarline\t"
)


def _primus_entry(tmp_path: Path) -> dict[str, Any]:
    import hashlib

    (tmp_path / "incipit.mei").write_text(_MEI, encoding="utf-8")
    (tmp_path / "incipit.semantic").write_text(_SEMANTIC, encoding="utf-8")

    def digest(name: str) -> str:
        return hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()

    return {
        "id": "TS-00",
        "verdad": {
            "tipo": "primus",
            "archivo": "incipit.mei",
            "sha256_origen": digest("incipit.mei"),
            "semantic": "incipit.semantic",
            "sha256_semantic": digest("incipit.semantic"),
        },
        "salida": {"verdad": "TS-00.musicxml"},
    }


def _pitches(path: Path) -> list[str]:
    root = ET.parse(path).getroot()
    found = []
    for note in root.iter("note"):
        step = note.findtext("pitch/step")
        if step is None:
            continue
        alter = {"1": "#", "-1": "b"}.get(note.findtext("pitch/alter") or "0", "")
        found.append(f"{step}{alter}{note.findtext('pitch/octave')}")
    return found


def test_a_primus_truth_takes_the_sounding_pitch_from_the_semantic(tmp_path: Path) -> None:
    # El MEI de PrIMuS no escribe la alteración de la armadura (`pname="f"` sin `accid.ges`
    # con un sostenido): leído tal cual, sería Fa natural donde suena Fa sostenido.
    out = tmp_path / "out"
    out.mkdir()

    truth = build_truth(_primus_entry(tmp_path), out, tmp_path)

    assert _pitches(truth) == ["G4", "F#4", "G4", "A4"]
    root = ET.parse(truth).getroot()
    assert root.findtext("part/measure/attributes/key/fifths") == "1"
    assert root.find("part/measure/attributes/time[@symbol='common']") is not None


def test_a_source_that_is_not_the_one_of_the_manifest_is_refused(tmp_path: Path) -> None:
    entry = _primus_entry(tmp_path)
    (tmp_path / "incipit.semantic").write_text(_SEMANTIC + "note-B4_quarter\t", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()

    with pytest.raises(BankError, match="no es la del manifiesto"):
        build_truth(entry, out, tmp_path)


def test_a_missing_source_is_refused_with_a_clear_message(tmp_path: Path) -> None:
    entry = _primus_entry(tmp_path)
    (tmp_path / "incipit.mei").unlink()

    with pytest.raises(BankError, match="Falta la fuente"):
        build_truth(entry, tmp_path, tmp_path)


_SLURRED = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE score-partwise  PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "x">
<score-partwise version="4.0">
  <part id="P1"><measure number="1"><note><rest/><duration>1</duration></note></measure></part>
  <part id="P2">
    <measure number="1"><note><rest/><duration>1</duration></note></measure>
    <measure number="2">
      <note><pitch><step>C</step><alter>1</alter><octave>4</octave></pitch>
        <duration>3</duration><voice>2</voice><type>quarter</type><dot/><staff>1</staff>
        <notations><slur number="4" type="start"/></notations></note>
      <note><pitch><step>C</step><alter>1</alter><octave>4</octave></pitch>
        <duration>1</duration><voice>2</voice><type>eighth</type><staff>1</staff>
        <notations><slur number="4" type="stop"/></notations></note>
    </measure>
  </part>
</score-partwise>"""

_SLUR_TO_TIE = {
    "cambio": "ligadura_de_expresion_a_prolongacion",
    "parte": 2,
    "compas": 2,
    "pentagrama": 1,
    "voz": "2",
    "motivo": "prueba",
}


def _type(note: ET.Element, path: str) -> str | None:
    found = note.find(path)
    return None if found is None else found.get("type")


def test_an_erratum_turns_a_slur_between_equal_notes_into_a_tie() -> None:
    fixed = apply_errata(_SLURRED, [_SLUR_TO_TIE])

    assert fixed.startswith('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE score-partwise')
    notes = ET.fromstring(fixed.split("\n", 2)[2]).findall("part")[1].findall("measure/note")[1:]
    assert [n.find("notations/slur") for n in notes] == [None, None]
    assert [_type(n, "tie") for n in notes] == ["start", "stop"]
    assert [_type(n, "notations/tied") for n in notes] == ["start", "stop"]
    # MusicXML pide `tie` justo después de `duration`.
    assert [child.tag for child in notes[0]][:3] == ["pitch", "duration", "tie"]


def test_an_erratum_that_does_not_find_its_slur_fails() -> None:
    with pytest.raises(BankError):
        apply_errata(_SLURRED, [{**_SLUR_TO_TIE, "compas": 1}])
    with pytest.raises(BankError):
        apply_errata(_SLURRED, [{**_SLUR_TO_TIE, "cambio": "otro"}])


def test_the_manifest_is_valid_json_with_lf() -> None:
    raw = MANIFEST.read_bytes()

    assert b"\r\n" not in raw
    assert json.loads(raw.decode("utf-8"))["salida"] == "banco_estudio"


def test_part_and_instrument_ids_are_numbered_in_order() -> None:
    xml = (
        "<identification><encoding>\n  <encoding-date>2026-11-02</encoding-date>"
        "\n  <software>music21</software></encoding></identification>"
        '<part-list><score-part id="Pa1b2"><score-instrument id="Ic3d4"/>'
        '<midi-instrument id="Ic3d4"/></score-part><score-part id="Pe5f6">'
        '<score-instrument id="I0a0b"/></score-part></part-list>'
        '<part id="Pa1b2"><note><instrument id="Ic3d4"/></note></part><part id="Pe5f6"/>'
    )

    assert stable_musicxml(xml) == (
        "<identification><encoding>\n  <software>music21</software></encoding></identification>"
        '<part-list><score-part id="P1"><score-instrument id="P1-I1"/>'
        '<midi-instrument id="P1-I1"/></score-part><score-part id="P2">'
        '<score-instrument id="P2-I1"/></score-part></part-list>'
        '<part id="P1"><note><instrument id="P1-I1"/></note></part><part id="P2"/>'
    )


def test_renaming_ids_does_not_chain_old_and_new_names() -> None:
    xml = (
        '<part-list><score-part id="P2"/><score-part id="P1"/></part-list>'
        '<part id="P2"/><part id="P1"/>'
    )

    assert stable_musicxml(xml) == (
        '<part-list><score-part id="P1"/><score-part id="P2"/></part-list>'
        '<part id="P1"/><part id="P2"/>'
    )


def test_an_erratum_only_changes_its_own_slur() -> None:
    # Otra ligadura de expresión (número 7) empieza en la segunda nota: se queda.
    other = '<slur number="4" type="stop"/><slur number="7" type="start"/>'
    xml = _SLURRED.replace('<slur number="4" type="stop"/>', other)

    fixed = apply_errata(xml, [_SLUR_TO_TIE])

    notes = ET.fromstring(fixed.split("\n", 2)[2]).findall("part")[1].findall("measure/note")[1:]
    assert [s.get("number") for s in notes[1].findall("notations/slur")] == ["7"]
    assert [_type(n, "tie") for n in notes] == ["start", "stop"]


def test_a_primus_image_is_the_png_of_the_incipit(tmp_path: Path) -> None:
    import hashlib

    from scripts.build_study_bank import build_image, mismatches

    (tmp_path / "incipit.png").write_bytes(b"\x89PNG prueba")
    digest = hashlib.sha256(b"\x89PNG prueba").hexdigest()
    entry = {
        "id": "TS-00",
        "imagen": {"origen": "primus", "archivo": "incipit.png", "sha256_origen": digest},
        "salida": {"imagen": "TS-00.png"},
    }
    out = tmp_path / "out"
    out.mkdir()

    image = build_image(entry, {"fuentes": {}}, out, tmp_path, tmp_path)

    assert image.read_bytes() == b"\x89PNG prueba"
    manifest = {"partituras": [{**entry, "sha256": {"imagen": digest, "verdad": "x"}}]}
    assert mismatches(manifest, {"TS-00": {"imagen": digest, "verdad": "x"}}) == []
    assert mismatches(manifest, {"TS-00": {"imagen": digest, "verdad": "y"}}) == [
        "TS-00 (verdad): y != x"
    ]
