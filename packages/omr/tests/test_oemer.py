"""Pruebas del adaptador `OemerEngine`, importación perezosa y contrato del puerto."""

from __future__ import annotations

import argparse
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from cadenza.omr import OEMER_ENGINE_ID, OemerEngine, OMRTranscriptionError, PreprocessingConfig
from cadenza.omr.adapters.oemer import (
    _import_oemer,
    ensure_oemer_checkpoints,
    get_effective_device,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
SIMPLE_MUSICXML = FIXTURES_DIR / "simple.musicxml"


def test_engine_id() -> None:
    engine = OemerEngine()
    assert engine.engine_id == "oemer"
    assert OEMER_ENGINE_ID == "oemer"


def test_missing_image_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="image not found"):
        OemerEngine().transcribe(tmp_path / "non-existent.png")

    with pytest.raises(FileNotFoundError, match="image not found"):
        OemerEngine().transcribe_musicxml(tmp_path / "non-existent.png")


def test_requires_optional_extra_when_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def _failing_import(
        name: str,
        globals: Any = None,
        locals: Any = None,
        fromlist: Any = (),
        level: int = 0,
    ) -> Any:
        if name.startswith("oemer"):
            raise ImportError("No module named 'oemer'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _failing_import)
    with pytest.raises(RuntimeError, match="extra opcional 'oemer'"):
        _import_oemer()


def test_effective_device_cpu_by_default() -> None:
    assert get_effective_device(use_gpu=False) == "cpu"
    assert OemerEngine(use_gpu=False).device == "cpu"


def test_effective_device_with_mocked_gpu(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_ort = types.ModuleType("onnxruntime")
    fake_ort.get_available_providers = lambda: [  # type: ignore[attr-defined]
        "CUDAExecutionProvider",
        "CPUExecutionProvider",
    ]
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)

    assert get_effective_device(use_gpu=True) == "cuda"
    assert OemerEngine(use_gpu=True).device == "cuda"


def test_from_active_model_factory() -> None:
    # Caso 1: registry es None
    engine = OemerEngine.from_active_model(None)
    assert engine.engine_id == "oemer"

    # Caso 2: registry sin versión activa
    empty_registry = MagicMock()
    empty_registry.active.return_value = None
    engine_empty = OemerEngine.from_active_model(empty_registry)
    assert engine_empty.engine_id == "oemer"

    # Caso 3: registry con versión activa
    active_mock = MagicMock()
    active_mock.version = "oemer-custom-v1"
    registry_with_model = MagicMock()
    registry_with_model.active.return_value = active_mock

    engine_active = OemerEngine.from_active_model(
        registry_with_model,
        document_id="doc-123",
        preprocessing=PreprocessingConfig(enabled=True, deskew=True),
        without_deskew=True,
    )
    assert engine_active._model_version == "oemer-custom-v1"
    assert engine_active._document_id == "doc-123"
    assert engine_active.preprocessing is not None
    assert engine_active.preprocessing.deskew is True


def test_transcribe_musicxml_and_document_mocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image_file = tmp_path / "test_score.png"
    image_file.write_bytes(b"\x89PNG\r\n\x1a\nfake-image-content")

    sample_xml = SIMPLE_MUSICXML.read_text(encoding="utf-8")

    fake_ete = types.ModuleType("oemer.ete")
    fake_ete.MODULE_PATH = str(tmp_path)  # type: ignore[attr-defined]
    fake_ete.CHECKPOINTS_URL = {}  # type: ignore[attr-defined]

    def _fake_clear_data() -> None:
        pass

    def _fake_extract(args: argparse.Namespace) -> str:
        # Crea el archivo .musicxml en el directorio output_path o staged
        target_xml = Path(args.output_path) / "test_score.musicxml"
        target_xml.write_text(sample_xml, encoding="utf-8")
        return str(target_xml)

    fake_ete.clear_data = _fake_clear_data  # type: ignore[attr-defined]
    fake_ete.extract = _fake_extract  # type: ignore[attr-defined]

    monkeypatch.setattr("cadenza.omr.adapters.oemer._import_oemer", lambda: fake_ete)

    engine = OemerEngine(document_id="custom-doc-1")

    # 1. Probar transcribe_musicxml
    xml_out = engine.transcribe_musicxml(image_file)
    assert "<score-partwise" in xml_out

    # 2. Probar transcribe devolviendo ScoreDocument
    doc = engine.transcribe(image_file)
    assert doc.id == "custom-doc-1"
    assert doc.score is not None
    assert len(doc.score.parts) == 1
    assert doc.provenance.omr_engine == "oemer"
    assert doc.provenance.device == "cpu"
    assert doc.provenance.source_image_hash is not None
    assert len(doc.provenance.source_image_hash) == 64
    assert len(doc.anchors) > 0


def test_transcribe_with_preprocessing_integration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PIL import Image

    # Crear una imagen PNG real válida para que preprocess_image_file funcione
    img = Image.new("RGB", (100, 100), color=(255, 255, 255))
    image_file = tmp_path / "preproc_score.png"
    img.save(image_file)

    sample_xml = SIMPLE_MUSICXML.read_text(encoding="utf-8")

    fake_ete = types.ModuleType("oemer.ete")
    fake_ete.MODULE_PATH = str(tmp_path)  # type: ignore[attr-defined]
    fake_ete.CHECKPOINTS_URL = {}  # type: ignore[attr-defined]

    captured_args: list[argparse.Namespace] = []

    def _fake_extract(args: argparse.Namespace) -> str:
        captured_args.append(args)
        target_xml = Path(args.output_path) / f"{Path(args.img_path).stem}.musicxml"
        target_xml.write_text(sample_xml, encoding="utf-8")
        return str(target_xml)

    fake_ete.clear_data = lambda: None  # type: ignore[attr-defined]
    fake_ete.extract = _fake_extract  # type: ignore[attr-defined]

    monkeypatch.setattr("cadenza.omr.adapters.oemer._import_oemer", lambda: fake_ete)

    preproc = PreprocessingConfig(enabled=True, deskew=True, binarize=True)
    engine = OemerEngine(preprocessing=preproc)

    doc = engine.transcribe(image_file)
    assert doc.provenance.preprocessing is not None
    assert doc.provenance.preprocessing["deskew"]["applied"] is True
    assert doc.provenance.preprocessing["binarize"]["applied"] is True

    # Verificar que without_deskew se pasó como True a oemer para evitar doble deskew
    assert len(captured_args) == 1
    assert captured_args[0].without_deskew is True


def test_transcription_error_on_extraction_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image_file = tmp_path / "broken.png"
    image_file.write_bytes(b"\x89PNG\r\n\x1a\n")

    fake_ete = types.ModuleType("oemer.ete")
    fake_ete.MODULE_PATH = str(tmp_path)  # type: ignore[attr-defined]
    fake_ete.CHECKPOINTS_URL = {}  # type: ignore[attr-defined]

    def _broken_extract(args: argparse.Namespace) -> str:
        raise RuntimeError("UNet segmentation crashed")

    fake_ete.clear_data = lambda: None  # type: ignore[attr-defined]
    fake_ete.extract = _broken_extract  # type: ignore[attr-defined]

    monkeypatch.setattr("cadenza.omr.adapters.oemer._import_oemer", lambda: fake_ete)

    engine = OemerEngine()
    with pytest.raises(OMRTranscriptionError, match="Oemer falló al procesar la imagen"):
        engine.transcribe_musicxml(image_file)


def test_transcription_error_when_no_musicxml_produced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image_file = tmp_path / "no_output.png"
    image_file.write_bytes(b"\x89PNG\r\n\x1a\n")

    fake_ete = types.ModuleType("oemer.ete")
    fake_ete.MODULE_PATH = str(tmp_path)  # type: ignore[attr-defined]
    fake_ete.CHECKPOINTS_URL = {}  # type: ignore[attr-defined]

    # No escribe ningún archivo .musicxml
    fake_ete.clear_data = lambda: None  # type: ignore[attr-defined]
    fake_ete.extract = lambda args: str(tmp_path / "ghost.musicxml")  # type: ignore[attr-defined]

    monkeypatch.setattr("cadenza.omr.adapters.oemer._import_oemer", lambda: fake_ete)

    engine = OemerEngine()
    with pytest.raises(OMRTranscriptionError, match="Oemer no produjo ningún MusicXML"):
        engine.transcribe_musicxml(image_file)


def test_ensure_oemer_checkpoints_downloads_missing(tmp_path: Path) -> None:
    fake_ete = types.ModuleType("oemer.ete")
    fake_ete.MODULE_PATH = str(tmp_path)  # type: ignore[attr-defined]
    fake_ete.CHECKPOINTS_URL = {  # type: ignore[attr-defined]
        "1st_model.onnx": "https://fake.url/1st.onnx",
        "2nd_model.onnx": "https://fake.url/2nd.onnx",
        "skip_weights.h5": "https://fake.url/weights.h5",
    }

    downloaded: list[tuple[str, str, str]] = []

    def _mock_download(title: str, url: str, save_path: str) -> None:
        downloaded.append((title, url, save_path))
        p = Path(save_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"mock-onnx-bytes")

    fake_ete.download_file = _mock_download  # type: ignore[attr-defined]

    ensure_oemer_checkpoints(fake_ete)

    # Solo debe descargar los dos archivos .onnx
    assert len(downloaded) == 2
    assert downloaded[0][0] == "1st_model.onnx"
    assert downloaded[1][0] == "2nd_model.onnx"

    # Segunda llamada: ya existen, no vuelve a descargar
    downloaded.clear()
    ensure_oemer_checkpoints(fake_ete)
    assert len(downloaded) == 0
