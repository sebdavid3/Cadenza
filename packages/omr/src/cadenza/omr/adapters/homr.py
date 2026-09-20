"""Adaptador HOMR: inferencia **in-process** sobre la API de Python de HOMR.

Cumple ADR-0005: nada de `subprocess` ni *scraping* de la terminal. El stack
pesado (`homr`, `onnxruntime`, `opencv`) está declarado como extra opcional y se
importa de forma perezosa dentro de `transcribe`, de modo que `cadenza.omr`
importa sin tenerlo instalado (test/CI usan `FakeOMREngine`).
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from cadenza.domain import Provenance, ScoreDocument, build_anchor_index

from ..engine import OMREngine

ENGINE_ID = "homr"
TITLE_DETECTION = False
_HOMR_EXTRA_HINT = (
    "HOMREngine requiere el extra opcional 'homr'. "
    'Instálalo con: uv sync --extra homr (o uv pip install -e "packages/omr[homr]").'
)


def _import_homr() -> Any:
    """Importa `homr.main` de forma perezosa, con mensaje de error accionable."""

    try:
        from homr import main as homr_main
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise RuntimeError(_HOMR_EXTRA_HINT) from exc
    return homr_main


def _gpu_available(homr_main: Any) -> bool:
    try:
        return bool(homr_main.cuda_available() or homr_main.rocm_available())
    except Exception:  # pragma: no cover - detección best-effort
        return False


def _homr_version() -> str:
    try:
        return version("homr")
    except PackageNotFoundError:  # pragma: no cover - depende del entorno
        return "unknown"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _run_homr(homr_main: Any, image_path: Path, use_gpu: bool) -> str:
    """Ejecuta el pipeline de HOMR en un directorio temporal y devuelve el MusicXML."""

    from homr.music_xml_generator import XmlGeneratorArguments

    with tempfile.TemporaryDirectory(prefix="cadenza-omr-") as work_dir:
        staged_image = Path(work_dir) / image_path.name
        shutil.copy2(image_path, staged_image)

        homr_main.download_weights(
            segnet_use_gpu=use_gpu,
            transformer_use_gpu=use_gpu,
            coreml_encoder=False,
        )
        config = homr_main.ProcessingConfig(
            enable_debug=False,
            enable_cache=False,
            write_staff_positions=False,
            read_staff_positions=False,
            selected_staff=-1,
            transformer_use_gpu=use_gpu,
            segnet_use_gpu=use_gpu,
            coreml_encoder=False,
            title_detection=TITLE_DETECTION,
        )
        xml_generator_args = XmlGeneratorArguments(False, None, None)
        xml_path = Path(homr_main.process_image(str(staged_image), config, xml_generator_args))
        return xml_path.read_text(encoding="utf-8", errors="replace")


class HOMREngine(OMREngine):
    """Adaptador principal: HOMR sobre `onnxruntime`, integrado in-process."""

    def __init__(self, *, use_gpu: bool = True, document_id: str | None = None) -> None:
        self._use_gpu = use_gpu
        self._document_id = document_id

    @property
    def engine_id(self) -> str:
        return ENGINE_ID

    def transcribe(self, image_path: Path) -> ScoreDocument:
        # Import perezoso: mantiene `cadenza.omr` importable sin music21 hasta que
        # se usa el motor real (FakeOMREngine no lo necesita).
        from cadenza.interchange import musicxml_to_score_ir

        if not image_path.is_file():
            raise FileNotFoundError(f"image not found: {image_path}")

        homr_main = _import_homr()
        use_gpu = self._use_gpu and _gpu_available(homr_main)
        source_hash = _sha256(image_path)
        xml_text = _run_homr(homr_main, image_path, use_gpu)

        score = musicxml_to_score_ir(xml_text)
        return ScoreDocument(
            id=self._document_id or f"homr-{source_hash[:12]}",
            score=score,
            anchors=build_anchor_index(score),
            provenance=Provenance(
                omr_engine=ENGINE_ID,
                model_version=_homr_version(),
                source_image_hash=source_hash,
            ),
        )
