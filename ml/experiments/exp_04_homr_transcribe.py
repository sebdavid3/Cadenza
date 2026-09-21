"""Experimento 4: transcripción real del corpus con HOMR (Fase 6, GPU).

Recorre las imágenes del corpus y guarda el **MusicXML nativo de HOMR** (no el
`ScoreIR` del dominio, que es lossy) en `data/<corpus>/predictions/<id>.musicxml`,
listo para que `exp_03_omr_quality.py` lo puntúe contra el ground truth.

Es tolerante a fallos: si HOMR no puede procesar una imagen (p. ej. "No staffs
found"), la registra en `failures.json` y continúa con el resto.

Requiere el extra pesado de OMR:

    uv pip install -e "packages/omr[homr]"
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cadenza.omr import HOMREngine

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"


def _runtime_info() -> dict[str, object]:
    """Registra el entorno de inferencia (reproducibilidad y trazabilidad del fallback)."""

    info: dict[str, object] = {}
    try:
        import onnxruntime

        info["onnxruntime_version"] = onnxruntime.__version__
        info["available_providers"] = list(onnxruntime.get_available_providers())
    except ImportError:  # pragma: no cover - depende del extra
        info["onnxruntime_version"] = None
    return info


def transcribe_corpus(
    manifest_path: Path, *, use_gpu: bool = True, limit: int | None = None
) -> tuple[int, list[dict[str, str]]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = manifest_path.parent
    corpus = str(manifest.get("corpus", "corpus"))
    predictions = root / corpus / "predictions"
    predictions.mkdir(parents=True, exist_ok=True)

    engine = HOMREngine(use_gpu=use_gpu)
    entries = list(manifest.get("entries", []))
    if limit is not None:
        entries = entries[:limit]

    written = 0
    failures: list[dict[str, str]] = []
    for entry in entries:
        image_path = root / entry["image"]
        try:
            xml_text = engine.transcribe_musicxml(image_path)
        except Exception as exc:  # corpus real: algunas imágenes no son procesables
            failures.append({"id": entry["id"], "error": f"{type(exc).__name__}: {exc}"})
            print(f"[exp_04] FALLO {entry['id']}: {exc}")
            continue
        (predictions / f"{entry['id']}.musicxml").write_text(xml_text, encoding="utf-8")
        written += 1
        print(f"[exp_04] {entry['id']} -> {entry['id']}.musicxml ({engine.engine_id})")

    (predictions / "failures.json").write_text(
        json.dumps(failures, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (predictions / "run_info.json").write_text(
        json.dumps(
            {
                "engine": engine.engine_id,
                "use_gpu_requested": use_gpu,
                "written": written,
                "failures": len(failures),
                **_runtime_info(),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return written, failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Transcripción HOMR del corpus — Fase 6")
    parser.add_argument("--manifest", type=Path, default=DATA_DIR / "manifest.json")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--cpu", action="store_true", help="Forzar inferencia en CPU")
    args = parser.parse_args()

    if not args.manifest.is_file():
        print(f"[exp_04] falta el manifiesto: {args.manifest}. Descarga el corpus primero.")
        return

    written, failures = transcribe_corpus(
        args.manifest, use_gpu=not args.cpu, limit=args.limit
    )
    print(f"[exp_04] {written} predicciones escritas, {len(failures)} fallos")


if __name__ == "__main__":
    main()
