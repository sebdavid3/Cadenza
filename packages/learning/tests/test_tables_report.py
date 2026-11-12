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
    # Sin red: ni scripts, ni hojas de estilo, ni imágenes de fuera.
    assert "http://" not in text and "https://" not in text

    data = _data(page)
    assert data["sources"] == ["cadenza"]
    assert set(data["variants"]) == {"todas|0", "todas|1", "cadenza|0", "cadenza|1"}
    notas = _rows(output / "notas.csv")
    every = data["variants"]["todas|0"]
    assert every["read"] == len(notas)
    assert every["outcome"] == dict(Counter(r["resultado"] for r in notas))
    assert every["missing"] == len(_rows(output / "faltantes.csv"))
    assert every["scores"] == len(_rows(output / "partituras.csv"))

    # La altura corregida del compás 2 lleva a la tira de su sistema.
    examples = [every["examples"][i] for i in every["example_keys"]["op:SetPitch"]]
    assert {(x["measure"], x["read"], x["fix"], x["img"]) for x in examples} == {
        ("2", "C4 4", "D4 4", "recortes/s-foto/s1_0-0.png")
    }
    for example in every["examples"]:
        assert not example["img"] or (output / example["img"]).is_file()
    assert every["example_keys"]["step:1"], "un paso arriba: de C4 a D4"


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
    assert data["sources"] == ["primus"]
    assert data["variants"]["primus|0"]["read"] == len(_rows(output / "notas.csv"))


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
