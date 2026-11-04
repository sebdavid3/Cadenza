"""Regenera el banco de partituras del estudio con participantes (#247, protocolo §2.3).

    uv run --no-sync python -P scripts/build_study_bank.py [--out banco_estudio]
        [--update-manifest]

Lee el manifiesto versionado (`docs/experimentos/banco_de_partituras.json`) y, de las fuentes
de `data/` que nombra (solo las lee), escribe en `--out` la imagen y la verdad en MusicXML de
cada partitura:

- La imagen de una página impresa es su página del PDF a 300 ppp con `pdftoppm` (poppler),
  recortada si el manifiesto da un recorte; la de un íncipit de PrIMuS, su PNG tal cual.
- La verdad de un recorte de OpenScore son sus compases del MusicXML, con
  `cadenza.interchange.musicxml_excerpt`: lleva al principio el compás, la armadura y la clave
  que rigen allí, aunque la imagen no los imprima. Las erratas del manifiesto (lo que la
  fuente codifica distinto de lo grabado en la página) se corrigen después.
- La de un íncipit de PrIMuS es su MEI con la altura que suena de cada nota tomada de su
  `.semantic` (el MEI no escribe la alteración de la armadura, `cadenza.learning.primus`),
  escrita con el exportador del sistema.

Antes comprueba el sha256 de cada fuente y después el de cada archivo escrito, contra el
manifiesto: falla si una fuente falta o no es la misma, o si una salida no coincide (otra
versión de `pdftoppm`, Pillow, music21 o converter21 puede dar otros bytes). Con
`--update-manifest` escribe en el manifiesto los sha256 de las salidas en lugar de compararlos.
La carpeta de salida no se versiona (`.gitignore`) y no puede estar dentro de `data/` ni de
`results/`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "docs" / "experimentos" / "banco_de_partituras.json"
FORBIDDEN_OUTPUTS = ("data", "results")


class BankError(RuntimeError):
    """El banco no se puede regenerar tal como dice el manifiesto."""


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(path: Path = MANIFEST) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def check_output_dir(out: Path, *roots: Path) -> None:
    """La salida no puede caer en `data/` ni en `results/` (la evidencia de la tesis)."""

    resolved = out.resolve()
    for root in roots or (REPO_ROOT,):
        for name in FORBIDDEN_OUTPUTS:
            forbidden = (root / name).resolve()
            if resolved == forbidden or forbidden in resolved.parents:
                raise BankError(f"La salida no puede estar dentro de {name}/: {out}")


def _source(repo_root: Path, relative: str, expected: str) -> Path:
    path = repo_root / relative
    if not path.is_file():
        raise BankError(f"Falta la fuente {relative}: se obtiene a mano (ver el manifiesto)")
    found = sha256_of(path)
    if found != expected:
        raise BankError(f"La fuente {relative} no es la del manifiesto: sha256 {found}")
    return path


def rasterize_page(pdf: Path, page: int, dpi: int, workdir: Path) -> Path:
    """La página `page` del PDF a `dpi` ppp, en PNG, con `pdftoppm` (poppler), como ADR-0056."""

    tool = shutil.which("pdftoppm")
    if tool is None:
        raise BankError("Falta pdftoppm (poppler-utils): sin él no se rasteriza el PDF")
    prefix = workdir / f"page-{page}"
    command = [tool, "-r", str(dpi), "-f", str(page), "-l", str(page), "-png", "-singlefile"]
    try:
        subprocess.run([*command, str(pdf), str(prefix)], check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", "replace").strip()
        raise BankError(f"pdftoppm no rasterizó la página {page} de {pdf.name}: {detail}") from exc
    raster = prefix.with_suffix(".png")
    if not raster.is_file():
        raise BankError(f"pdftoppm no dio la página {page} de {pdf.name}")
    return raster


def build_image(
    entry: dict[str, Any], manifest: dict[str, Any], out: Path, workdir: Path, repo_root: Path
) -> Path:
    image = entry["imagen"]
    target = out / str(entry["salida"]["imagen"])
    if image["origen"] == "primus":
        shutil.copyfile(_source(repo_root, image["archivo"], image["sha256_origen"]), target)
        return target
    if image["origen"] != "pdf":
        raise BankError(f"Origen de imagen desconocido: {image['origen']}")

    from PIL import Image

    source = manifest["fuentes"][image["fuente"]]
    pdf = _source(repo_root, source["archivo"], source["sha256"])
    page = rasterize_page(pdf, image["pagina_pdf"], image["ppp"], workdir)
    with Image.open(page) as raster:
        box = image.get("recorte")
        result = raster.crop(tuple(box)) if box is not None else raster.copy()
    result.save(target, format="PNG", dpi=(image["ppp"], image["ppp"]))
    return target


def _pitch_of(note: ET.Element) -> tuple[str | None, str | None, str | None]:
    return (
        note.findtext("pitch/step"),
        note.findtext("pitch/alter"),
        note.findtext("pitch/octave"),
    )


def _slur_to_tie(root: ET.Element, erratum: dict[str, Any]) -> None:
    """La ligadura de expresión entre dos notas iguales de una voz de un pentagrama de un
    compás pasa a ser una ligadura de prolongación. Solo cambia esa ligadura (su inicio y su
    final, con el mismo número); otra que empiece o acabe en esas notas se queda como está."""

    parts = root.findall("part")
    index = erratum["parte"] - 1
    measure = (
        parts[index].find(f"measure[@number='{erratum['compas']}']")
        if 0 <= index < len(parts)
        else None
    )
    notes = [
        note
        for note in ([] if measure is None else measure.findall("note"))
        if note.findtext("staff", "1") == str(erratum["pentagrama"])
        and note.findtext("voice") == erratum["voz"]
    ]
    ends: list[tuple[ET.Element, ET.Element, ET.Element]] = []
    for note in notes:
        notations = note.find("notations")
        if notations is not None:
            ends.extend((note, notations, slur) for slur in notations.findall("slur"))
    pairs = [
        (start, stop)
        for start in ends
        for stop in ends
        if start[2].get("type") == "start"
        and stop[2].get("type") == "stop"
        and start[2].get("number") == stop[2].get("number")
        and start[0] is not stop[0]
        and _pitch_of(start[0]) == _pitch_of(stop[0])
    ]
    if len(pairs) != 1:
        raise BankError(f"Errata sin su ligadura entre dos notas iguales: {erratum}")
    for (note, notations, slur), kind in zip(pairs[0], ("start", "stop"), strict=True):
        notations.remove(slur)
        duration = [i for i, child in enumerate(note) if child.tag == "duration"]
        if not duration:
            raise BankError(f"Errata sobre una nota sin duración: {erratum}")
        note.insert(duration[0] + 1, ET.Element("tie", {"type": kind}))
        ET.SubElement(notations, "tied", {"type": kind})


_ERRATA = {"ligadura_de_expresion_a_prolongacion": _slur_to_tie}


def apply_errata(xml: str, errata: list[dict[str, Any]]) -> str:
    """Corrige en el MusicXML lo que la fuente codifica distinto de lo grabado en la página.

    Conserva la declaración y el DOCTYPE que escribe music21. Falla si una errata no encuentra
    lo que corrige: no se da por corregida una verdad que no lo está.
    """

    if not errata:
        return xml
    start = xml.index("<score-partwise")
    root = ET.fromstring(xml[start:])
    for erratum in errata:
        change = _ERRATA.get(erratum.get("cambio", ""))
        if change is None:
            raise BankError(f"Errata desconocida: {erratum}")
        change(root, erratum)
    return xml[:start] + ET.tostring(root, encoding="unicode") + "\n"


_PART_LIST_ID = re.compile(r'<(score-part|score-instrument) id="([^"]+)"')
_ID = re.compile(r'id="([^"]+)"')
_ENCODING_DATE = re.compile(r"\n\s*<encoding-date>[^<]*</encoding-date>")


def stable_musicxml(xml: str) -> str:
    """El MusicXML sin lo que cambia en cada escritura, para que su sha256 no cambie.

    Quita la fecha de codificación y numera en orden los identificadores de las partes y de
    sus instrumentos, que music21 inventa al azar: P1, P2... y P1-I1, P1-I2... (en una sola
    pasada, para que un nombre nuevo no se confunda con uno viejo).
    """

    renamed: dict[str, str] = {}
    part = ""
    parts = instruments = 0
    for tag, old in _PART_LIST_ID.findall(xml):
        if tag == "score-part":
            parts += 1
            part, instruments = f"P{parts}", 0
            renamed[old] = part
        else:
            instruments += 1
            renamed[old] = f"{part}-I{instruments}"
    xml = _ID.sub(lambda m: f'id="{renamed.get(m[1], m[1])}"', xml)
    return _ENCODING_DATE.sub("", xml)


def _primus_truth(truth: dict[str, Any], repo_root: Path) -> str:
    from cadenza.interchange import read_score, score_ir_to_musicxml
    from cadenza.learning.primus import semantic_note_pitches, with_sounding_pitches

    mei = _source(repo_root, truth["archivo"], truth["sha256_origen"])
    semantic = _source(repo_root, truth["semantic"], truth["sha256_semantic"])
    pitches = semantic_note_pitches(semantic.read_text(encoding="utf-8"))
    return score_ir_to_musicxml(with_sounding_pitches(read_score(mei), pitches))


def build_truth(entry: dict[str, Any], out: Path, repo_root: Path) -> Path:
    truth = entry["verdad"]
    if truth["tipo"] == "primus":
        xml = _primus_truth(truth, repo_root)
    elif truth["tipo"] == "openscore":
        from cadenza.interchange import musicxml_excerpt

        source = _source(repo_root, truth["archivo"], truth["sha256_origen"])
        first, last = truth["compases"]
        xml = apply_errata(musicxml_excerpt(source, first, last), truth.get("erratas", []))
    else:
        raise BankError(f"Tipo de verdad desconocido: {truth['tipo']}")
    target = out / str(entry["salida"]["verdad"])
    target.write_text(stable_musicxml(xml), encoding="utf-8", newline="\n")
    return target


def build(
    manifest: dict[str, Any], out: Path, repo_root: Path = REPO_ROOT
) -> dict[str, dict[str, str]]:
    """Escribe la imagen y la verdad de cada partitura; devuelve sus sha256 por id.

    `repo_root` es donde están las fuentes (`data/...`): el checkout que las tiene.
    """

    check_output_dir(out, REPO_ROOT, repo_root)
    out.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, dict[str, str]] = {}
    with tempfile.TemporaryDirectory(prefix="banco-") as tmp:
        for entry in manifest["partituras"]:
            image = build_image(entry, manifest, out, Path(tmp), repo_root)
            truth = build_truth(entry, out, repo_root)
            hashes[entry["id"]] = {"imagen": sha256_of(image), "verdad": sha256_of(truth)}
    return hashes


def mismatches(manifest: dict[str, Any], hashes: dict[str, dict[str, str]]) -> list[str]:
    found: list[str] = []
    for entry in manifest["partituras"]:
        for kind in ("imagen", "verdad"):
            expected = entry.get("sha256", {}).get(kind)
            if hashes[entry["id"]][kind] != expected:
                found.append(f"{entry['id']} ({kind}): {hashes[entry['id']][kind]} != {expected}")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--out", default=None, help="Por defecto, la `salida` del manifiesto.")
    parser.add_argument("--manifest", default=str(MANIFEST))
    parser.add_argument(
        "--sources-root",
        default=str(REPO_ROOT),
        help="Checkout con las fuentes de data/ (por defecto, este).",
    )
    parser.add_argument(
        "--update-manifest",
        action="store_true",
        help="Escribe en el manifiesto los sha256 de las salidas en lugar de compararlos.",
    )
    args = parser.parse_args(argv)

    manifest_path = Path(args.manifest)
    manifest = load_manifest(manifest_path)
    out = Path(args.out) if args.out else REPO_ROOT / manifest["salida"]
    try:
        hashes = build(manifest, out, Path(args.sources_root))
    except BankError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.update_manifest:
        for entry in manifest["partituras"]:
            entry["sha256"] = hashes[entry["id"]]
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"Manifiesto actualizado: {manifest_path}")
        return 0

    wrong = mismatches(manifest, hashes)
    for line in wrong:
        print(f"No coincide con el manifiesto: {line}", file=sys.stderr)
    if wrong:
        return 1
    print(f"{len(hashes)} partituras regeneradas en {out}; los sha256 coinciden")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
