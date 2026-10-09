"""Tooling de corpus para la Fase 6: registro, descarga y manifiesto trazable.

Los corpus se descargan a ``data/<corpus>/{images,ground_truth}/`` y se resumen
en ``data/manifest.json`` con el sha256 de cada archivo, de modo que los
experimentos sean reproducibles sin versionar los blobs (``data/`` está ignorado
por git).

Uso:
    python ml/experiments/corpus.py info
    python ml/experiments/corpus.py fetch --url <URL_DEL_ARCHIVO> --corpus primus
    python ml/experiments/corpus.py manifest --corpus primus --limit 100
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".tif", ".tiff"})
GROUND_TRUTH_SUFFIXES = frozenset({".mei", ".krn", ".musicxml", ".xml", ".mxl", ".mid", ".midi"})


@dataclass(frozen=True, slots=True)
class CorpusSpec:
    name: str
    description: str
    landing_url: str
    ground_truth_format: str
    license_note: str


# URLs de aterrizaje oficiales (tomadas de docs/literatura/06 y 07). La descarga
# directa se pasa explícitamente con --url para no fijar enlaces que cambian.
CORPORA: dict[str, CorpusSpec] = {
    "primus": CorpusSpec(
        name="primus",
        description="PrIMuS — incipits impresos monofónicos (RISM, Verovio)",
        landing_url="https://grfia.dlsi.ua.es/primus/",
        ground_truth_format="MEI / MIDI",
        license_note="Uso académico — confirmar condiciones en el sitio oficial",
    ),
    "camera-primus": CorpusSpec(
        name="camera-primus",
        description="Camera-PrIMuS — mismas partituras con distorsión tipo cámara",
        landing_url="https://grfia.dlsi.ua.es/primus/",
        ground_truth_format="MEI",
        license_note="Uso académico — confirmar condiciones en el sitio oficial",
    ),
    "smb": CorpusSpec(
        name="smb",
        description="Sheet Music Benchmark (SMB) — 685 páginas, splits oficiales",
        landing_url="https://doi.org/10.5281/zenodo.17706531",
        ground_truth_format="**kern (Humdrum) / MusicXML",
        license_note="Zenodo — confirmar licencia del registro",
    ),
    "muscima_pp": CorpusSpec(
        name="muscima_pp",
        description="MUSCIMA++ v2.0 — manuscritos modernos con grafos MuNG / CGF (140 páginas)",
        landing_url="https://github.com/OMR-Research/muscima-pp",
        ground_truth_format="MuNG XML / CGF (anotaciones de glifos y relaciones)",
        license_note="CC BY-NC-SA 4.0 (anotación sobre CVC-MUSCIMA)",
    ),
    "muscima-pp": CorpusSpec(
        name="muscima-pp",
        description="MUSCIMA++ v2.0 — manuscritos modernos con grafos MuNG / CGF (140 páginas)",
        landing_url="https://github.com/OMR-Research/muscima-pp",
        ground_truth_format="MuNG XML / CGF (anotaciones de glifos y relaciones)",
        license_note="CC BY-NC-SA 4.0 (anotación sobre CVC-MUSCIMA)",
    ),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch(url: str, dest: Path) -> Path:
    """Descarga ``url`` a ``dest`` (archivo) y devuelve la ruta local."""

    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response, dest.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    return dest


def extract(archive: Path, dest: Path) -> None:
    """Extrae un ``.zip``/``.tar.*`` en ``dest``."""

    dest.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(dest)
        return
    if tarfile.is_tarfile(archive):
        with tarfile.open(archive) as bundle:
            bundle.extractall(dest)
        return
    raise ValueError(f"formato de archivo no soportado: {archive}")


def _is_junk(path: Path) -> bool:
    """Ignora metadatos de macOS (AppleDouble ``._*``, ``.DS_Store``, ``__MACOSX``)."""

    return path.name.startswith("._") or path.name == ".DS_Store" or "__MACOSX" in path.parts


def _index_by_stem(directory: Path, suffixes: frozenset[str]) -> dict[str, Path]:
    indexed: dict[str, Path] = {}
    if not directory.is_dir():
        return indexed
    for path in sorted(directory.rglob("*")):
        if path.is_file() and not _is_junk(path) and path.suffix.lower() in suffixes:
            indexed.setdefault(path.stem, path)
    return indexed


def build_manifest(
    root: Path,
    corpus: str,
    limit: int | None = None,
    *,
    images_dir: Path | None = None,
    ground_truth_dir: Path | None = None,
) -> dict[str, object]:
    """Empareja imágenes y ground truth por nombre base y calcula sus hashes.

    Por defecto escanea recursivamente ``data/<corpus>/`` completo (los corpus
    reales anidan sus carpetas de forma diversa); ``images_dir`` y
    ``ground_truth_dir`` permiten fijarlas explícitamente.
    """

    corpus_root = root / corpus
    images = _index_by_stem(images_dir or corpus_root, IMAGE_SUFFIXES)
    truths = _index_by_stem(ground_truth_dir or corpus_root, GROUND_TRUTH_SUFFIXES)
    stems = sorted(set(images) & set(truths))
    if limit is not None:
        stems = stems[:limit]

    entries = [
        {
            "id": stem,
            "image": str(images[stem].relative_to(root)).replace("\\", "/"),
            "image_sha256": sha256_file(images[stem]),
            "ground_truth": str(truths[stem].relative_to(root)).replace("\\", "/"),
            "ground_truth_sha256": sha256_file(truths[stem]),
        }
        for stem in stems
    ]
    spec = CORPORA.get(corpus)
    return {
        "corpus": corpus,
        "description": spec.description if spec else corpus,
        "ground_truth_format": spec.ground_truth_format if spec else "desconocido",
        "count": len(entries),
        "entries": entries,
    }


def _command_info() -> None:
    for spec in CORPORA.values():
        print(f"- {spec.name}: {spec.description}")
        print(f"    URL: {spec.landing_url}")
        print(f"    ground truth: {spec.ground_truth_format} | licencia: {spec.license_note}")


def _command_fetch(url: str, corpus: str, dest: Path) -> None:
    archive = dest / f"{corpus}-download"
    print(f"[corpus] descargando {url}")
    fetch(url, archive)
    extract(archive, dest / corpus)
    archive.unlink(missing_ok=True)
    print(f"[corpus] extraído en {dest / corpus}")


def _command_manifest(
    corpus: str,
    root: Path,
    limit: int | None,
    output: Path,
    images_dir: Path | None,
    ground_truth_dir: Path | None,
) -> None:
    manifest = build_manifest(
        root, corpus, limit, images_dir=images_dir, ground_truth_dir=ground_truth_dir
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[corpus] {manifest['count']} pares -> {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Tooling de corpus de Cadenza (Fase 6)")
    parser.add_argument("--root", type=Path, default=DATA_DIR)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("info", help="Lista los corpus registrados")

    fetch_parser = sub.add_parser("fetch", help="Descarga y extrae un archivo de corpus")
    fetch_parser.add_argument("--url", required=True)
    fetch_parser.add_argument("--corpus", required=True, choices=sorted(CORPORA))

    manifest_parser = sub.add_parser("manifest", help="Genera el manifiesto con hashes")
    manifest_parser.add_argument("--corpus", required=True, choices=sorted(CORPORA))
    manifest_parser.add_argument("--limit", type=int, default=None)
    manifest_parser.add_argument("--output", type=Path, default=DATA_DIR / "manifest.json")
    manifest_parser.add_argument("--images-dir", type=Path, default=None)
    manifest_parser.add_argument("--ground-truth-dir", type=Path, default=None)

    args = parser.parse_args()
    if args.command == "info":
        _command_info()
    elif args.command == "fetch":
        _command_fetch(args.url, args.corpus, args.root)
    elif args.command == "manifest":
        _command_manifest(
            args.corpus,
            args.root,
            args.limit,
            args.output,
            args.images_dir,
            args.ground_truth_dir,
        )


if __name__ == "__main__":
    main()
