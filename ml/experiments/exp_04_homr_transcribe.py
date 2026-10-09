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
import os
from pathlib import Path

from cadenza.omr import HOMREngine, ensure_cuda_dll_dirs

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"


def _prepare_runtime(use_gpu: bool) -> dict[str, object]:
    """Precarga las DLLs CUDA y sondea el provider real (trazabilidad del run)."""

    info: dict[str, object] = {"use_gpu_requested": use_gpu}
    try:
        import onnxruntime
    except ImportError:  # pragma: no cover - depende del extra
        info["onnxruntime_version"] = None
        return info

    info["onnxruntime_version"] = onnxruntime.__version__
    if use_gpu:
        info["cuda_dll_dirs"] = len(ensure_cuda_dll_dirs())
        try:
            onnxruntime.preload_dlls()
        except Exception as exc:  # DLLs de CUDA/cuDNN ausentes
            info["preload_error"] = str(exc)
    info["available_providers"] = list(onnxruntime.get_available_providers())
    try:
        package_dir = os.path.dirname(str(onnxruntime.__file__ or ""))
        model = os.path.join(package_dir, "datasets", "mul_1.onnx")
        if os.path.isfile(model):
            session = onnxruntime.InferenceSession(model, providers=["CUDAExecutionProvider"])
            info["gpu_session_providers"] = list(session.get_providers())
    except Exception as exc:  # pragma: no cover - depende del entorno
        info["gpu_session_error"] = str(exc)
    return info


def transcribe_corpus(
    manifest_path: Path, *, use_gpu: bool = True, limit: int | None = None
) -> tuple[int, list[dict[str, str]]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = manifest_path.parent
    corpus = str(manifest.get("corpus", "corpus"))
    predictions = root / corpus / "predictions"
    predictions.mkdir(parents=True, exist_ok=True)
    # Un run es autocontenido: evita mezclar predicciones de corridas previas.
    stale = list(predictions.glob("*.musicxml"))
    for path in stale:
        path.unlink()
    if stale:
        print(f"[exp_04] limpiadas {len(stale)} predicciones previas")

    runtime = _prepare_runtime(use_gpu)
    if use_gpu and "gpu_session_providers" in runtime:
        print(f"[exp_04] GPU activa: {runtime['gpu_session_providers']}")
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
                "written": written,
                "failures": len(failures),
                **runtime,
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

    written, failures = transcribe_corpus(args.manifest, use_gpu=not args.cpu, limit=args.limit)
    print(f"[exp_04] {written} predicciones escritas, {len(failures)} fallos")


if __name__ == "__main__":
    main()
