"""`ml export-tables` con varios corpus a la vez: PrIMuS (`exp_12`) y Camera-PrIMuS (`exp_18`,
#421).

Los dos corpus tienen los mismos incipits: el de Camera-PrIMuS los nombra
`camera-primus:<id>` y dice `source: camera-primus`, así que no se confunden en las tablas ni en
el informe, que nombra cada corpus y explica qué es.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from cadenza.learning import primus_work_id

from ml.cli import main
from ml.tables_report import report_data

from .suggestions_support import corpus_records, incipit_id

CAMERA = "camera-primus"


def _write(path: Path, records: list[dict[str, Any]]) -> Path:
    path.write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in records), encoding="utf-8"
    )
    return path


def _camera_records(works: int) -> list[dict[str, Any]]:
    """Los registros de `corpus_records` como los escribe exp_18: otra fuente, otro id y la obra
    de PrIMuS."""
    records = corpus_records(works)
    for record in records:
        raw = str(record["incipit_id"])
        record.update(
            {"incipit_id": f"{CAMERA}:{raw}", "source": CAMERA, "work_id": primus_work_id(raw)}
        )
    return records


def _corpora(tmp_path: Path, works: int = 2) -> tuple[Path, Path]:
    primus = _write(tmp_path / "correction_corpus.jsonl", corpus_records(works))
    camera = _write(tmp_path / "camera_primus_correction_corpus.jsonl", _camera_records(works))
    return primus, camera


def _export(output: Path, *args: str) -> int:
    return main(["export-tables", "--output-dir", str(output), *args])


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_several_corpora_go_to_the_same_tables_without_mixing_their_incipits(
    tmp_path: Path,
) -> None:
    primus, camera = _corpora(tmp_path)
    output = tmp_path / "salida"
    assert _export(output, "--corpus", str(primus), "--corpus", str(camera)) == 0

    scores = _rows(output / "partituras.csv")
    by_source: dict[str, set[str]] = {}
    for row in scores:
        by_source.setdefault(row["source"], set()).add(row["incipit_id"])
    raw = {incipit_id(work, index) for work in range(2) for index in range(2)}
    assert by_source == {"primus": raw, CAMERA: {f"{CAMERA}:{i}" for i in raw}}
    # La obra y el lado de la partición son los de PrIMuS: el mismo incipit, del mismo lado.
    side = {(r["source"], r["work_id"]): r["split"] for r in scores}
    assert {w for _, w in side} == {primus_work_id(i) for i in raw}
    for (_, work), split in side.items():
        assert side[("primus", work)] == split
    notes = _rows(output / "notas.csv")
    assert {r["source"] for r in notes} == {"primus", CAMERA}
    assert sum(r["source"] == CAMERA for r in notes) == sum(r["source"] == "primus" for r in notes)

    info = json.loads((output / "run_info.json").read_text(encoding="utf-8"))
    corpora = info["origins"]["corpus"]
    assert [c["file"] for c in corpora] == [primus.name, camera.name]
    assert [c["sources"] for c in corpora] == [
        {"primus": len(corpus_records(2))},
        {CAMERA: len(corpus_records(2))},
    ]
    assert info["tables"]["notas"]["by_source"] == {
        "primus": len(notes) // 2,
        CAMERA: len(notes) // 2,
    }


def test_a_single_corpus_keeps_its_origin_as_before(tmp_path: Path) -> None:
    _, camera = _corpora(tmp_path)
    output = tmp_path / "salida"
    assert _export(output, "--corpus", str(camera)) == 0
    info = json.loads((output / "run_info.json").read_text(encoding="utf-8"))
    assert info["origins"]["corpus"]["file"] == camera.name
    assert {r["source"] for r in _rows(output / "partituras.csv")} == {CAMERA}


def test_the_same_incipit_of_the_same_corpus_twice_is_refused(tmp_path: Path) -> None:
    primus, _ = _corpora(tmp_path)
    copy = _write(tmp_path / "copia.jsonl", corpus_records(1))
    output = tmp_path / "salida"
    assert _export(output, "--corpus", str(primus), "--corpus", str(copy)) == 1
    assert not output.exists()


def _camera_dir(tmp_path: Path, ids: list[str]) -> Path:
    corpus = tmp_path / "camera_primus" / "Corpus"
    for raw in ids:
        folder = corpus / raw
        folder.mkdir(parents=True)
        (folder / f"{raw}_distorted.jpg").write_bytes(f"jpg {raw}".encode())
        (folder / f"{raw}.png").write_bytes(f"png {raw}".encode())  # la limpia no se usa
    return corpus


def test_camera_primus_rows_point_to_their_distorted_image(tmp_path: Path) -> None:
    _, camera = _corpora(tmp_path, works=1)
    found, missing = incipit_id(0, 0), incipit_id(0, 1)
    images = _camera_dir(tmp_path, [found])
    output = tmp_path / "salida"
    assert (
        _export(output, "--corpus", str(camera), "--recortes", "--camera-primus-dir", str(images))
        == 0
    )

    copied = output / "recortes" / CAMERA / f"{found}.jpg"
    assert copied.read_bytes() == f"jpg {found}".encode()
    notas = _rows(output / "notas.csv")
    mine = [r for r in notas if r["incipit_id"] == f"{CAMERA}:{found}"]
    assert mine and {(r["sistema"], r["recorte"]) for r in mine} == {
        ("1", f"recortes/{CAMERA}/{found}.jpg")
    }
    assert {r["recorte"] for r in notas if r["incipit_id"] == f"{CAMERA}:{missing}"} == {""}
    recortes = json.loads((output / "run_info.json").read_text(encoding="utf-8"))["recortes"]
    assert recortes["camera_primus_images"] == 1
    assert recortes["camera_primus_missing"] == [f"{CAMERA}:{missing}"]


def test_the_camera_primus_images_need_recortes_and_an_existing_folder(tmp_path: Path) -> None:
    _, camera = _corpora(tmp_path, works=1)
    output = tmp_path / "salida"
    assert _export(output, "--corpus", str(camera), "--camera-primus-dir", str(tmp_path)) == 1
    missing = str(tmp_path / "no-existe")
    assert (
        _export(output, "--corpus", str(camera), "--recortes", "--camera-primus-dir", missing) == 1
    )
    assert not output.exists()


def _page_data(page: Path) -> dict[str, Any]:
    match = re.search(r"const DATA = (.*?);\n", page.read_text(encoding="utf-8"))
    assert match is not None
    data: dict[str, Any] = json.loads(match.group(1))
    return data


def test_the_report_names_each_corpus_without_splitting_them(tmp_path: Path) -> None:
    """El informe nombra y explica Camera-PrIMuS; el único filtro sigue siendo el de las pruebas
    reales (ADR-0069, #418): la fuente de cada partitura está en el historial."""
    primus, camera = _corpora(tmp_path, works=3)
    output = tmp_path / "salida"
    args = ["--corpus", str(primus), "--corpus", str(camera), "--informe"]
    assert _export(output, *args) == 0

    data = _page_data(output / "informe.html")
    assert data["groups"] == [] and set(data["variants"]) == {"todas|0", "todas|1"}
    assert data["counts"]["primus"] == data["counts"][CAMERA] == 6
    assert data["variants"]["todas|0"]["scores"] == 12
    assert data["variants"]["todas|0"]["read"] == len(_rows(output / "notas.csv"))
    # En el historial, el mismo incipit sale dos veces, una por corpus, con su nombre.
    history = data["history"]
    assert len({h["id"] for h in history}) == 12
    origins = {h["id"]: h["origin"] for h in history}
    raw = incipit_id(0, 0)
    assert origins[raw] == "PrIMuS" and origins[f"{CAMERA}:{raw}"] == "Camera-PrIMuS"
    labels = {h["id"]: h["label"] for h in history}
    assert labels[raw] == labels[f"{CAMERA}:{raw}"] == raw


def test_a_single_camera_primus_corpus_is_not_split_and_is_named(tmp_path: Path) -> None:
    _, camera = _corpora(tmp_path)
    output = tmp_path / "salida"
    assert _export(output, "--corpus", str(camera)) == 0
    data = report_data(output)
    assert data["groups"] == [] and set(data["variants"]) == {"todas|0", "todas|1"}
    assert {h["origin"] for h in data["history"]} == {"Camera-PrIMuS"}
    assert data["counts"][CAMERA] == 4 and data["counts"]["primus"] == 0
