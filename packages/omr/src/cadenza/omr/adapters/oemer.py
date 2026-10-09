"""Adaptador Oemer: inferencia **in-process** sobre la API de Python de oemer.

Cumple ADR-0005: proporciona una línea base OMR no asistida alternativa para
comparación experimental (deuda técnica D1, hito M1). El stack pesado (`oemer`,
`onnxruntime`, `scikit-learn`, `scipy`) está declarado como extra opcional `oemer`
y se importa de forma perezosa dentro de `transcribe`, de modo que `cadenza.omr`
se pueda importar sin tenerlo instalado (la suite de tests y la CI pueden usar
`FakeOMREngine` o mocks).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from cadenza.domain import Provenance, ScoreDocument, build_anchor_index

from ..engine import OMREngine
from ..errors import OMRTranscriptionError
from ..preprocessing import PreprocessingConfig, preprocess_image_file

ENGINE_ID = "oemer"
OEMER_ENGINE_ID = "oemer"
_OEMER_EXTRA_HINT = (
    "OemerEngine requiere el extra opcional 'oemer'. "
    'Instálalo con: uv pip install -e "packages/omr[oemer]".'
)


def get_effective_device(use_gpu: bool = False) -> str:
    """Obtiene el dispositivo efectivo sondeando `onnxruntime.get_available_providers()`."""
    if not use_gpu:
        return "cpu"
    try:
        import onnxruntime

        providers = onnxruntime.get_available_providers()
        if "CUDAExecutionProvider" in providers or "ROCMExecutionProvider" in providers:
            return "cuda"
    except Exception:
        pass
    return "cpu"


def _import_oemer() -> Any:
    """Importa `oemer.ete` de forma perezosa, con mensaje de error accionable."""
    try:
        import oemer.ete as oemer_ete
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise RuntimeError(_OEMER_EXTRA_HINT) from exc
    return oemer_ete


def _oemer_version() -> str:
    try:
        return version("oemer")
    except PackageNotFoundError:  # pragma: no cover - depende del entorno
        return "0.1.8"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _patch_onnx_pads_if_needed(model_path: Path) -> None:
    """Sanea atributos `pads` negativos en ConvTranspose heredados de exportaciones tf2onnx."""
    if not model_path.is_file():
        return
    try:
        import onnx

        model = onnx.load(str(model_path))
        modified = False
        for node in model.graph.node:
            if node.op_type == "ConvTranspose":
                for attr in node.attribute:
                    if attr.name == "pads" and any(x < 0 for x in attr.ints):
                        attr.ints[:] = [max(0, x) for x in attr.ints]
                        modified = True
        if modified:
            onnx.save(model, str(model_path))
    except Exception:
        pass


def ensure_oemer_checkpoints(oemer_ete: Any) -> None:
    """Verifica y descarga los checkpoints ONNX de oemer si no están presentes."""
    module_path = getattr(oemer_ete, "MODULE_PATH", None)
    if not module_path:
        import oemer

        module_path = Path(oemer.__file__).parent

    chk_path = Path(module_path) / "checkpoints" / "unet_big" / "model.onnx"
    if chk_path.is_file():
        _patch_onnx_pads_if_needed(chk_path)
        return

    checkpoints_url = getattr(oemer_ete, "CHECKPOINTS_URL", None)
    if not checkpoints_url:
        return

    for title, url in checkpoints_url.items():
        if not title.endswith(".onnx"):
            continue
        save_dir = "unet_big" if title.startswith("1st") else "seg_net"
        target_dir = Path(module_path) / "checkpoints" / save_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        save_path = target_dir / title.split("_")[1]
        if not save_path.is_file():
            download_func = getattr(oemer_ete, "download_file", None)
            if callable(download_func):
                download_func(title, url, str(save_path))

    _patch_onnx_pads_if_needed(chk_path)


def _run_oemer(
    oemer_ete: Any,
    image_path: Path,
    *,
    without_deskew: bool = False,
    use_tf: bool = False,
) -> str:
    """Ejecuta el pipeline de `oemer` en un directorio temporal y devuelve el MusicXML."""
    with tempfile.TemporaryDirectory(prefix="cadenza-oemer-") as work_dir:
        staged_image = Path(work_dir) / image_path.name
        shutil.copy2(image_path, staged_image)

        ensure_oemer_checkpoints(oemer_ete)

        clear_data = getattr(oemer_ete, "clear_data", None)
        if callable(clear_data):
            clear_data()

        args = argparse.Namespace(
            img_path=str(staged_image),
            output_path=str(work_dir),
            use_tf=use_tf,
            save_cache=False,
            without_deskew=without_deskew,
        )

        try:
            oemer_ete.extract(args)
        except Exception as exc:
            raise OMRTranscriptionError(f"Oemer falló al procesar la imagen: {exc}") from exc

        basename = os.path.splitext(staged_image.name)[0]
        xml_path = staged_image.parent / f"{basename}.musicxml"
        if not xml_path.is_file():
            candidates = sorted(Path(work_dir).glob("*.musicxml"))
            if not candidates:
                raise OMRTranscriptionError("Oemer no produjo ningún MusicXML")
            xml_path = candidates[0]

        return xml_path.read_text(encoding="utf-8", errors="replace")


class OemerEngine(OMREngine):
    """Adaptador de línea base: `oemer` integrado in-process (ADR-0005)."""

    def __init__(
        self,
        *,
        use_gpu: bool = False,
        document_id: str | None = None,
        model_version: str | None = None,
        preprocessing: PreprocessingConfig | None = None,
        without_deskew: bool | None = None,
        use_tf: bool = False,
    ) -> None:
        self._use_gpu = use_gpu
        self._document_id = document_id
        self._model_version = model_version
        self._preprocessing = preprocessing
        self._without_deskew = without_deskew
        self._use_tf = use_tf

    @property
    def preprocessing(self) -> PreprocessingConfig | None:
        return self._preprocessing

    @classmethod
    def from_active_model(
        cls,
        model_registry: Any | None,
        artifact_store: Any | None = None,
        *,
        use_gpu: bool = False,
        document_id: str | None = None,
        preprocessing: PreprocessingConfig | None = None,
        without_deskew: bool | None = None,
    ) -> OemerEngine:
        """Instancia OemerEngine con la versión de modelo activa si existe (#21)."""
        if model_registry is None:
            return cls(
                use_gpu=use_gpu,
                document_id=document_id,
                preprocessing=preprocessing,
                without_deskew=without_deskew,
            )

        active = model_registry.active()
        if active is None:
            return cls(
                use_gpu=use_gpu,
                document_id=document_id,
                preprocessing=preprocessing,
                without_deskew=without_deskew,
            )

        return cls(
            use_gpu=use_gpu,
            document_id=document_id,
            model_version=active.version,
            preprocessing=preprocessing,
            without_deskew=without_deskew,
        )

    @property
    def engine_id(self) -> str:
        return ENGINE_ID

    @property
    def device(self) -> str:
        """Devuelve el dispositivo efectivo de inferencia ('cuda' o 'cpu')."""
        return get_effective_device(self._use_gpu)

    def transcribe_musicxml(
        self,
        image_path: Path,
        *,
        override_preprocessing: PreprocessingConfig | None = None,
    ) -> str:
        """Devuelve el MusicXML nativo de oemer sin pasar por el `ScoreIR`."""
        if not image_path.is_file():
            raise FileNotFoundError(f"image not found: {image_path}")

        oemer_ete = _import_oemer()
        effective_preproc = (
            override_preprocessing if override_preprocessing is not None else self._preprocessing
        )

        effective_without_deskew = (
            self._without_deskew
            if self._without_deskew is not None
            else bool(effective_preproc and effective_preproc.enabled and effective_preproc.deskew)
        )

        if effective_preproc is not None and effective_preproc.enabled:
            with tempfile.TemporaryDirectory(prefix="cadenza-preproc-") as temp_dir:
                preproc_path = Path(temp_dir) / f"preprocessed_{image_path.name}"
                if not preproc_path.suffix:
                    preproc_path = preproc_path.with_suffix(".png")
                preprocess_image_file(image_path, preproc_path, effective_preproc)
                return _run_oemer(
                    oemer_ete,
                    preproc_path,
                    without_deskew=effective_without_deskew,
                    use_tf=self._use_tf,
                )

        return _run_oemer(
            oemer_ete,
            image_path,
            without_deskew=effective_without_deskew,
            use_tf=self._use_tf,
        )

    def transcribe(self, image_path: Path) -> ScoreDocument:
        from cadenza.interchange import musicxml_to_score_ir

        if not image_path.is_file():
            raise FileNotFoundError(f"image not found: {image_path}")

        source_hash = _sha256(image_path)
        effective_preproc = self._preprocessing
        preproc_meta: dict[str, Any] | None = None

        if effective_preproc is not None and effective_preproc.enabled:
            with tempfile.TemporaryDirectory(prefix="cadenza-preproc-") as temp_dir:
                preproc_path = Path(temp_dir) / f"preprocessed_{image_path.name}"
                if not preproc_path.suffix:
                    preproc_path = preproc_path.with_suffix(".png")
                preproc_meta = preprocess_image_file(image_path, preproc_path, effective_preproc)
                xml_text = self.transcribe_musicxml(
                    image_path,
                    override_preprocessing=effective_preproc,
                )
        else:
            xml_text = self.transcribe_musicxml(image_path)

        score = musicxml_to_score_ir(xml_text)
        effective_version = self._model_version or _oemer_version()
        return ScoreDocument(
            id=self._document_id or f"oemer-{source_hash[:12]}",
            score=score,
            anchors=build_anchor_index(score),
            provenance=Provenance(
                omr_engine=ENGINE_ID,
                model_version=effective_version,
                source_image_hash=source_hash,
                device=self.device,
                preprocessing=preproc_meta
                or (effective_preproc.to_primitive() if effective_preproc else None),
            ),
        )
