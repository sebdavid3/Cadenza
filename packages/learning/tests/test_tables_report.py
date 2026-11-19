"""`ml export-tables --informe` (#415, ADR-0069): el informe visual de los errores de HOMR.

Usa la base de `test_export_tables_recortes` (una foto de dos sistemas, una altura corregida en
el compás 2). El informe se genera de los CSV ya escritos: sus cifras coinciden con ellos, y sus
ejemplos llevan a la foto del compás.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from ml import tables_report
from ml.cli import main
from ml.tables_report import diatonic, reordered_chords

from .suggestions_support import SPLIT_SEED, write_corpus
from .test_export_tables_recortes import base  # noqa: F401  (fixture)


def _data(page: Path) -> dict[str, Any]:
    match = re.search(r"const DATA = (.*?);\n", page.read_text(encoding="utf-8"))
    assert match is not None
    data: dict[str, Any] = json.loads(match.group(1))
    return data


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _export(output: Path, copy: tuple[str, Path], *extra: str) -> int:
    db_url, artifacts = copy
    return main(
        [
            "export-tables",
            "--output-dir",
            str(output),
            "--db-url",
            db_url,
            "--split-seed",
            str(SPLIT_SEED),
            "--artifacts-dir",
            str(artifacts),
            *extra,
        ]
    )


def test_the_report_agrees_with_the_csv_and_shows_the_photos(
    base: tuple[str, Path], tmp_path: Path  # noqa: F811
) -> None:
    output = tmp_path / "salida"
    assert _export(output, base, "--recortes", "--informe") == 0
    page = output / "informe.html"
    text = page.read_text(encoding="utf-8")
    # Sin red: ni scripts, ni hojas de estilo, ni imágenes, ni fuentes de fuera. Los enlaces a
    # HOMR y a PrIMuS solo se abren si se siguen.
    assert not re.search(r"""(src|srcset)\s*=\s*["']?\s*(https?:)?//""", text)
    assert not re.search(r"""url\(\s*["']?\s*(https?:)?//""", text)
    assert not re.search(r"<link\b|@import|<iframe\b|fetch\(|XMLHttpRequest", text)
    assert set(re.findall(r'href="(https?://[^"]+)"', text)) == {
        "https://github.com/liebharc/homr",
        "https://grfia.dlsi.ua.es/primus/",
    }

    data = _data(page)
    # Sin cuentas del registro no hay pruebas reales que separar: solo «todas».
    assert data["groups"] == []
    assert set(data["variants"]) == {"todas|0", "todas|1"}
    notas = _rows(output / "notas.csv")
    every = data["variants"]["todas|0"]
    assert every["read"] == len(notas)
    assert every["outcome"] == dict(Counter(r["resultado"] for r in notas))
    assert every["missing"] == len(_rows(output / "faltantes.csv"))
    assert every["scores"] == len(_rows(output / "partituras.csv"))

    # La altura corregida del compás 2 lleva a la tira de su sistema.
    examples = [every["examples"][i] for i in every["example_keys"]["op:SetPitch"]]
    assert {(x["measure"], x["read"], x["fix"], x["img"]) for x in examples} == {
        ("2", "C4 redonda", "D4 redonda", "recortes/s-foto/s1_0-0.png")
    }
    for example in every["examples"]:
        assert not example["img"] or (output / example["img"]).is_file()
    assert every["example_keys"]["step:1"], "un paso arriba: de C4 a D4"
    # Las tiras escriben cada duración con el nombre de su figura, nunca con una fracción.
    durations = {
        match.group(1)
        for row in _rows(output / "pentagramas.csv")
        for text in (row["lectura"], row["corregida"])
        for match in re.finditer(r":([^:\s~]+)~?(?=\s|$)", text)
    }
    assert durations and durations <= set(data["figures"])
    assert {r["read_duration_beats"] for r in notas} <= set(data["figures"])
    assert all(not re.search(r"\d", f["name"]) and f["symbol"] for f in data["figures"].values())
    assert all(x["read_beats"] or x["fix_beats"] for x in every["examples"])
    # Cada ejemplo de una nota lleva su compás para dibujarlo: lo leído y lo correcto.
    pitch = next(x for x in examples if x["kind"] == "change")
    bar = data["bars"][pitch["bar"]]
    assert bar["read"][pitch["at_read"]][1] == "C4" and bar["fixed"][pitch["at_fix"]][1] == "D4"
    assert "clef" in bar and isinstance(bar["key"], int)  # sin clave leída se dibuja en la de sol
    assert data["counts"] == {
        "primus": 0,
        "cadenza": len(_rows(output / "partituras.csv")),
        "real": 0,
    }


def test_without_recortes_the_report_has_no_photos(
    base: tuple[str, Path], tmp_path: Path  # noqa: F811
) -> None:
    output = tmp_path / "sin-fotos"
    assert _export(output, base, "--informe") == 0
    every = _data(output / "informe.html")["variants"]["todas|0"]
    assert every["examples"] and all(x["img"] == "" for x in every["examples"])


def test_the_report_reads_a_primus_corpus(tmp_path: Path) -> None:
    corpus = write_corpus(tmp_path / "corpus.jsonl", works=3)
    output = tmp_path / "primus"
    assert (
        main(["export-tables", "--output-dir", str(output), "--corpus", str(corpus), "--informe"])
        == 0
    )
    data = _data(output / "informe.html")
    # PrIMuS no se separa de «todas» (#418).
    assert data["groups"] == [] and set(data["variants"]) == {"todas|0", "todas|1"}
    assert data["variants"]["todas|0"]["read"] == len(_rows(output / "notas.csv"))


def test_only_the_real_tests_of_cadenza_are_split(
    base: tuple[str, Path], tmp_path: Path  # noqa: F811
) -> None:
    output = tmp_path / "con-registro"
    assert _export(output, base, "--recortes", "--include-self-registered", "--informe") == 0
    partituras = _rows(output / "partituras.csv")
    real = {r["incipit_id"] for r in partituras if r["origen"] == "registro"}
    assert real and len(real) < len(partituras), "la de la visita y las del equipo"

    data = _data(output / "informe.html")
    assert data["groups"] == ["pruebas"]
    assert set(data["variants"]) == {"todas|0", "todas|1", "pruebas|0", "pruebas|1"}
    notas = _rows(output / "notas.csv")
    assert data["variants"]["pruebas|0"]["read"] == sum(1 for r in notas if r["incipit_id"] in real)
    assert data["variants"]["pruebas|0"]["scores"] == len(real)
    assert data["variants"]["todas|0"]["read"] == len(notas)
    real_sessions = {r["session_id"] for r in partituras if r["origen"] == "registro"}
    assert {s["session"] for s in data["sessions"] if s["real"]} <= real_sessions
    origins = {r["origin"] for r in data["variants"]["todas|0"]["top"]}
    assert origins <= {"Prueba real", "Equipo", "Banco del estudio", "PrIMuS"}


@pytest.mark.parametrize(
    ("beats", "name"),
    [
        ("0", "adorno"),
        ("1/16", "semifusa"),
        ("1/8", "fusa"),
        ("3/16", "fusa con puntillo"),
        ("1/4", "semicorchea"),
        ("1/2", "corchea"),
        ("3/4", "corchea con puntillo"),
        ("1", "negra"),
        ("3/2", "negra con puntillo"),
        ("7/4", "negra con doble puntillo"),
        ("2", "blanca"),
        ("3", "blanca con puntillo"),
        ("7/2", "blanca con doble puntillo"),
        ("4", "redonda"),
        ("6", "redonda con puntillo"),
        ("8", "cuadrada"),
        ("16", "longa"),
        ("1/3", "corchea de tresillo"),
        ("2/3", "negra de tresillo"),
        ("1/5", "semicorchea de quintillo"),
        ("5/2", "blanca + corchea"),
        ("9/2", "redonda + corchea"),
        ("1/7", "semicorchea de septillo"),
        ("1/9", "figura irregular"),
        ("?", "figura desconocida"),
        ("", "figura desconocida"),
    ],
)
def test_each_duration_is_named_by_its_figure(beats: str, name: str) -> None:
    assert tables_report.figure_name(beats) == name


@pytest.mark.parametrize(
    ("clef", "name"),
    [
        ("G2", "clave de sol"),
        ("G1", "clave de sol en 1.ª"),
        ("F4", "clave de fa"),
        ("F3", "clave de fa en 3.ª"),
        ("C1", "clave de do en 1.ª"),
        ("C3", "clave de do en 3.ª"),
        ("G2-1", "clave de sol (octava baja)"),
        ("G2+2", "clave de sol (2 octavas alta)"),
        ("", "sin clave"),
    ],
)
def test_each_clef_is_named_in_musical_language(clef: str, name: str) -> None:
    assert tables_report.clef_name(clef) == name


def test_a_bar_keeps_what_was_read_and_what_is_right_in_order() -> None:
    def note(index: str, pitch: str, **fields: str) -> dict[str, str]:
        return _row(event_index=index, read_pitch=pitch, ctx_key_fifths="-1", **fields)

    tables = {
        "notas": [
            note("0", "C4"),
            note("1", "E4", resultado="borrada", ops="DeleteEvent"),
            note("2", "G4", resultado="corregida", ops="SetPitch", fix_pitch="A4"),
        ],
        # Faltaba un F4 delante del G4 (posición 2 de lo leído).
        "faltantes": [
            {
                **_row(event_index="2"),
                "ins_kind": "note",
                "ins_pitch": "F4",
                "ins_duration_beats": "1/2",
                "ins_is_chord": "false",
                "ins_hidden": "false",
            }
        ],
        "clave_armadura": [],
        "partituras": [
            {"source": "cadenza", "incipit_id": "cadenza:s", "session_id": "s", "test_score_id": ""}
        ],
    }
    bars = tables_report._Bars(tables)
    bar_id, at_read, at_fix = bars.note(2)
    bar = bars.bars[bar_id]
    assert [e[1] for e in bar["read"]] == ["C4", "E4", "G4"]
    assert [e[1] for e in bar["fixed"]] == ["C4", "F4", "A4"]
    assert (at_read, at_fix) == (2, 2)
    assert bars.note(1)[1:] == (1, None), "la leída de más no está en lo correcto"
    assert bars.missing(0) == (bar_id, None, 1), "la que faltaba solo está en lo correcto"
    assert bar["key"] == -1 and bar["clef"] == "G2"

    every = tables_report.aggregate(tables, None, False, set(), bars)
    kinds = {x["kind"] for x in every["examples"]}
    assert kinds == {"change", "extra", "missing"}
    extra = next(x for x in every["examples"] if x["kind"] == "extra")
    assert extra["fix"] == "" and extra["read"] == "E4 negra"


def test_the_symbol_of_a_figure_has_its_dots_tuplet_and_grace() -> None:
    def symbol(beats: str) -> list[tuple[str, int, int, bool]]:
        return [
            (p["figure"], p["dots"], p["tuplet"], p["grace"])
            for p in tables_report.figure_symbol(beats)
        ]

    assert symbol("1") == [("negra", 0, 0, False)]
    assert symbol("3/4") == [("corchea", 1, 0, False)]
    assert symbol("7/2") == [("blanca", 2, 0, False)]
    assert symbol("1/3") == [("corchea", 0, 3, False)]
    assert symbol("0") == [("corchea", 0, 0, True)]
    assert symbol("5/2") == [("blanca", 0, 0, False), ("corchea", 0, 0, False)]
    assert symbol("1/9") == [] and symbol("?") == []


def _note(
    measure: str, read: str, fixed: str, *, chord: bool, result: str = "corregida"
) -> dict[str, str]:
    return {
        "incipit_id": "cadenza:s",
        "part": "1",
        "staff": "0",
        "measure": measure,
        "voice": "0",
        "read_is_chord": "true" if chord else "false",
        "resultado": result if read != fixed else "bien",
        "ops": "SetPitch" if read != fixed else "",
        "read_pitch": read,
        "fix_pitch": fixed if read != fixed else "",
    }


def test_a_chord_read_in_another_order_is_only_reordered() -> None:
    notas = [
        # Compás 1: el mismo acorde, en otro orden: dos correcciones que no son errores.
        _note("1", "F4", "D4", chord=False),
        _note("1", "D4", "F4", chord=True),
        # Compás 2: una nota del acorde cambia de verdad.
        _note("2", "C4", "E4", chord=False),
        _note("2", "E4", "G4", chord=True),
        # Compás 3: una nota sola corregida no es un acorde.
        _note("3", "A4", "B4", chord=False),
    ]
    assert reordered_chords(notas) == {0, 1}


def test_diatonic_counts_staff_positions() -> None:
    c4 = diatonic("C4")
    assert c4 is not None
    assert diatonic("D4") == c4 + 1
    assert diatonic("C5") == c4 + 7
    assert diatonic("Bb3") == diatonic("B3")
    assert diatonic("F#4") == diatonic("F4")
    assert diatonic("") is None and diatonic("x") is None


def test_a_chord_reordered_around_a_good_note_and_what_is_not_a_reordering() -> None:
    notas = [
        # Compás 1: acorde de tres con la nota del medio bien: solo reordenado.
        _note("1", "F4", "A4", chord=False),
        _note("1", "C4", "C4", chord=True),
        _note("1", "A4", "F4", chord=True),
        # Compás 2: el mismo cambio de orden, pero una nota cambia también de figura.
        _note("2", "F4", "D4", chord=False),
        {**_note("2", "D4", "F4", chord=True), "ops": "SetPitch+SetDuration"},
        # Compás 3 y 4: una nota marcada como de acorde que empieza otro compás no se une al
        # acorde del anterior.
        _note("3", "E4", "G4", chord=False),
        _note("4", "G4", "E4", chord=True),
    ]
    assert reordered_chords(notas) == {0, 2}


def test_all_the_figures_of_the_report_come_from_the_csv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus = write_corpus(tmp_path / "corpus.jsonl", works=6)
    output = tmp_path / "primus"
    assert main(["export-tables", "--output-dir", str(output), "--corpus", str(corpus)]) == 0
    monkeypatch.setattr(tables_report, "MIN_SCORE_EVENTS", 1)
    every = tables_report.report_data(output)["variants"]["todas|0"]
    notas = _rows(output / "notas.csv")
    faltantes = _rows(output / "faltantes.csv")
    claves = _rows(output / "clave_armadura.csv")
    partituras = _rows(output / "partituras.csv")
    ops = Counter(op for r in notas + claves for op in r["ops"].split("+") if op)
    ops["InsertEvent"] = len(faltantes)
    assert every["ops"] == {k: n for k, n in ops.items() if n}
    assert sum(every["steps"].values()) == sum(1 for r in notas if "SetPitch" in r["ops"])
    assert sum(c["n"] for c in every["durations"]) == sum(
        1 for r in notas if "SetDuration" in r["ops"]
    )
    # Las correcciones de cada partitura son sus `correcciones_netas`.
    netas = {r["incipit_id"]: int(r["correcciones_netas"]) for r in partituras}
    shown = {r["key"].removeprefix("score:"): r["fixes"] for r in every["top"]}
    assert shown and all(netas[incipit] == fixes for incipit, fixes in shown.items())
    assert every["clean_scores"] == sum(1 for n in netas.values() if n == 0)


def _row(**fields: str) -> dict[str, str]:
    """Una fila de `notas` con lo que el informe lee; lo demás, vacío."""
    defaults = {
        "source": "cadenza",
        "incipit_id": "cadenza:s",
        "session_id": "s",
        "part": "1",
        "staff": "0",
        "measure": "1",
        "voice": "0",
        "read_kind": "note",
        "read_pitch": "C4",
        "read_duration_beats": "1",
        "read_is_chord": "false",
        "read_hidden": "false",
        "event_index": "0",
        "ctx_key_fifths": "0",
        "resultado": "bien",
        "ops": "",
        "fix_pitch": "",
        "fix_duration_beats": "",
        "ctx_accidental_vs_key": "in_key",
        "ctx_clef": "G2",
        "recorte": "",
    }
    return {**defaults, **fields}


def test_without_the_reordered_chords_they_count_as_well_read() -> None:
    notas = [
        _row(read_pitch="F4", resultado="corregida", ops="SetPitch", fix_pitch="D4"),
        _row(
            read_pitch="D4",
            read_is_chord="true",
            resultado="corregida",
            ops="SetPitch",
            fix_pitch="F4",
        ),
        _row(measure="2", read_pitch="A4", resultado="corregida", ops="SetPitch", fix_pitch="B4"),
    ]
    tables = {
        "notas": notas,
        "faltantes": [],
        "clave_armadura": [],
        "partituras": [
            {
                "source": "cadenza",
                "incipit_id": "cadenza:s",
                "session_id": "s",
                "test_score_id": "TS-04",
            }
        ],
    }
    reordered = reordered_chords(notas)
    assert reordered == {0, 1}
    counted = tables_report.aggregate(tables, None, False, reordered)
    skipped = tables_report.aggregate(tables, None, True, reordered)
    assert counted["outcome"] == {"corregida": 3} and counted["ops"]["SetPitch"] == 3
    assert skipped["outcome"] == {"bien": 2, "corregida": 1} and skipped["ops"]["SetPitch"] == 1
    assert sum(skipped["steps"].values()) == 1
    assert counted["reordered"] == skipped["reordered"] == 2
    assert [
        x["read"] for x in (skipped["examples"][i] for i in skipped["example_keys"]["op:SetPitch"])
    ] == ["A4 negra"]


def test_the_report_escapes_what_comes_from_the_tables(
    base: tuple[str, Path], tmp_path: Path  # noqa: F811
) -> None:
    output = tmp_path / "salida"
    assert _export(output, base, "--recortes") == 0
    # Un texto de las tablas con HTML: no puede cortar el script ni colarse en la página.
    path = output / "partituras.csv"
    rows = _rows(path)
    hostile = '</script><!--<script>alert("x")</script>__DATE__'
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "test_score_id": hostile})
    page = tables_report.write_report(output).read_text(encoding="utf-8")
    script = page.split("<script>", 1)[1]
    assert script.count("</script>") == 1 and "<!--" not in script
    data = _data(output / "informe.html")
    labels = {x["score"] for v in data["variants"].values() for x in v["examples"]}
    assert any(label.startswith(hostile) for label in labels)  # el texto llega entero
