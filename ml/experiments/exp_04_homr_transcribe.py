"""Experimento 4: transcripción real del corpus con HOMR (Fase 6, GPU).

Recorre las imágenes del corpus, transcribe cada una con `HOMREngine` y escribe
la predicción en MusicXML (vía `score_ir_to_musicxml`), dejándola lista para que
`exp_03_omr_quality.py` la puntúe contra el ground truth.

Requiere el extra pesado de OMR:

    uv sync --extra homr

Sin él, el script falla con un mensaje accionable (no rompe el resto del repo).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cadenza.domain import ScoreDocument
from cadenza.interchange import score_ir_to_musicxml
from cadenza.omr import HOMREngine

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".tif", ".tiff"})


def _load_manifest(manifest_path: Path) -> dict[str, object]:
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def transcribe_corpus(
    manifest_path: Path, *, use_gpu: bool = True, limit: int | None = None
) -> int:
    manifest = _load_manifest(manifest_path)
    root = manifest_path.parent
    corpus = str(manifest.get("corpus", "corpus"))
    predictions = root / corpus / "predictions"
    predictions.mkdir(parents=True, exist_ok=True)

    engine = HOMREngine(use_gpu=use_gpu)
    entries = list(manifest.get("entries", []))
    if limit is not None:
        entries = entries[:limit]

    written = 0
    for entry in entries:
        image_path = root / entry["image"]
        document: ScoreDocument = engine.transcribe(image_path)
        target = predictions / f"{entry['id']}.musicxml"
        target.write_text(score_ir_to_musicxml(document.score), encoding="utf-8")
        written += 1
        print(f"[exp_04] {entry['id']} -> {target.name} ({engine.engine_id})")
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Transcripción HOMR del corpus — Fase 6")
    parser.add_argument("--manifest", type=Path, default=DATA_DIR / "manifest.json")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--cpu", action="store_true", help="Forzar inferencia en CPU")
    args = parser.parse_args()

    if not args.manifest.is_file():
        print(f"[exp_04] falta el manifiesto: {args.manifest}. Descarga el corpus primero.")
        return

    written = transcribe_corpus(
        args.manifest, use_gpu=not args.cpu, limit=args.limit
    )
    print(f"[exp_04] {written} predicciones escritas")


if __name__ == "__main__":
    main()
