"""Adaptador HOMR: inferencia **in-process** sobre la API de Python de HOMR.

Cumple ADR-0005: nada de `subprocess` ni *scraping* de la terminal. El stack
pesado (`homr`, `onnxruntime`, `opencv`) está declarado como extra opcional y se
importa de forma perezosa dentro de `transcribe`, de modo que `cadenza.omr`
importa sin tenerlo instalado (test/CI usan `FakeOMREngine`).
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import site
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from cadenza.domain import Provenance, ScoreDocument, build_anchor_index

from ..engine import OMREngine
from ..errors import OMRTranscriptionError
from ..preprocessing import PreprocessingConfig, preprocess_image_file

ENGINE_ID = "homr"
_HOMR_EXTRA_HINT = (
    "HOMREngine requiere el extra opcional 'homr'. "
    'Instálalo con: uv pip install -e "packages/omr[homr]".'
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


_CUDA_DLL_DIRS: set[str] = set()


def ensure_cuda_dll_dirs() -> list[str]:
    """Añade al `PATH` los `bin` de los wheels NVIDIA (CUDA/cuDNN). Solo Windows.

    `onnxruntime.preload_dlls()` carga las DLLs principales, pero cuDNN carga
    dinámicamente sus sub-librerías (`cudnn_engines_*`, `cudnn_heuristic_*`)
    durante la inferencia y necesita encontrarlas en el `PATH`; si no, la primera
    `Conv` falla con `CUDNN_STATUS_SUBLIBRARY_LOADING_FAILED`.

    Es **idempotente**: cada directorio se añade una sola vez (si no, llamarla
    por imagen haría crecer `PATH` hasta exceder el límite de Windows). Devuelve
    los directorios añadidos en esta llamada.
    """

    if os.name != "nt":
        return []
    added: list[str] = []
    for base in site.getsitepackages():
        nvidia = Path(base) / "nvidia"
        if not nvidia.is_dir():
            continue
        for directory in sorted(nvidia.glob("*/bin")):
            path = str(directory)
            if not directory.is_dir() or path in _CUDA_DLL_DIRS:
                continue
            add_dll = getattr(os, "add_dll_directory", None)
            if callable(add_dll):
                with contextlib.suppress(OSError):
                    add_dll(path)
            os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")
            _CUDA_DLL_DIRS.add(path)
            added.append(path)
    return added


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _run_homr(
    homr_main: Any,
    image_path: Path,
    use_gpu: bool,
    weights_path: Path | None = None,
) -> str:
    """Ejecuta el pipeline de HOMR en un directorio temporal y devuelve el MusicXML."""

    from homr.music_xml_generator import XmlGeneratorArguments

    if use_gpu:
        ensure_cuda_dll_dirs()

    with tempfile.TemporaryDirectory(prefix="cadenza-omr-") as work_dir:
        staged_image = Path(work_dir) / image_path.name
        shutil.copy2(image_path, staged_image)

        if weights_path is None:
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
        )
        xml_generator_args = XmlGeneratorArguments(False, None, None)
        try:
            # HOMR >=0.7 escribe `<imagen>.musicxml` junto a la imagen y devuelve None.
            homr_main.process_image(str(staged_image), config, xml_generator_args)
        except Exception as exc:
            raise OMRTranscriptionError(f"HOMR falló al procesar la imagen: {exc}") from exc

        xml_path = staged_image.with_suffix(".musicxml")
        if not xml_path.is_file():
            candidates = sorted(Path(work_dir).glob("*.musicxml"))
            if not candidates:
                raise OMRTranscriptionError("HOMR no produjo ningún MusicXML")
            xml_path = candidates[0]
        return xml_path.read_text(encoding="utf-8", errors="replace")


class HOMREngine(OMREngine):
    """Adaptador principal: HOMR sobre `onnxruntime`, integrado in-process."""

    def __init__(
        self,
        *,
        use_gpu: bool = True,
        document_id: str | None = None,
        model_version: str | None = None,
        weights_path: Path | None = None,
        preprocessing: PreprocessingConfig | None = None,
    ) -> None:
        self._use_gpu = use_gpu
        self._document_id = document_id
        self._model_version = model_version
        self._weights_path = weights_path
        self._preprocessing = preprocessing

    @property
    def preprocessing(self) -> PreprocessingConfig | None:
        return self._preprocessing

    @classmethod
    def from_active_model(
        cls,
        model_registry: Any | None,
        artifact_store: Any | None = None,
        *,
        use_gpu: bool = True,
        document_id: str | None = None,
        preprocessing: PreprocessingConfig | None = None,
    ) -> HOMREngine:
        """Instancia HOMREngine con la versión de modelo activa si existe (#21)."""
        if model_registry is None:
            return cls(
                use_gpu=use_gpu,
                document_id=document_id,
                preprocessing=preprocessing,
            )

        active = model_registry.active()
        if active is None:
            return cls(
                use_gpu=use_gpu,
                document_id=document_id,
                preprocessing=preprocessing,
            )

        weights_path: Path | None = None
        if artifact_store is not None and hasattr(artifact_store, "resolve_path"):
            try:
                weights_path = Path(artifact_store.resolve_path(active.artifact_hash))
            except Exception:
                weights_path = None

        return cls(
            use_gpu=use_gpu,
            document_id=document_id,
            model_version=active.version,
            weights_path=weights_path,
            preprocessing=preprocessing,
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
        """Devuelve el MusicXML nativo de HOMR sin pasar por el `ScoreIR`.

        Se usa para evaluar la calidad real del motor OMR (OMR-NED) sin la
        pérdida de información del `ScoreIR` (que no modela armaduras, claves ni
        barras de compás).
        """

        if not image_path.is_file():
            raise FileNotFoundError(f"image not found: {image_path}")

        homr_main = _import_homr()
        use_gpu = self._use_gpu and _gpu_available(homr_main)
        effective_preproc = (
            override_preprocessing if override_preprocessing is not None else self._preprocessing
        )

        if effective_preproc is not None and effective_preproc.enabled:
            with tempfile.TemporaryDirectory(prefix="cadenza-preproc-") as temp_dir:
                preproc_path = Path(temp_dir) / f"preprocessed_{image_path.name}"
                if not preproc_path.suffix:
                    preproc_path = preproc_path.with_suffix(".png")
                preprocess_image_file(image_path, preproc_path, effective_preproc)
                return _run_homr(
                    homr_main,
                    preproc_path,
                    use_gpu,
                    weights_path=self._weights_path,
                )

        return _run_homr(homr_main, image_path, use_gpu, weights_path=self._weights_path)

    def transcribe(self, image_path: Path) -> ScoreDocument:
        # Import perezoso: mantiene `cadenza.omr` importable sin music21 hasta que
        # se usa el motor real (FakeOMREngine no lo necesita).
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
        effective_version = self._model_version or _homr_version()
        return ScoreDocument(
            id=self._document_id or f"homr-{source_hash[:12]}",
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
