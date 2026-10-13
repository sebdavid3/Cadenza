"""Pruebas del adaptador `HOMREngine` y de su importación perezosa."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from cadenza.omr import HOMREngine


def _check_homr_installed() -> bool:
    try:
        from homr import main  # noqa: F401

        return True
    except (ImportError, RuntimeError):
        return False


HOMR_INSTALLED = _check_homr_installed()


def test_engine_id() -> None:
    assert HOMREngine().engine_id == "homr"


def test_missing_image_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        HOMREngine().transcribe(tmp_path / "does-not-exist.png")


@pytest.mark.skipif(HOMR_INSTALLED, reason="el extra opcional 'homr' está instalado")
def test_requires_optional_extra(tmp_path: Path) -> None:
    image = tmp_path / "score.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(RuntimeError, match="extra opcional 'homr'"):
        HOMREngine().transcribe(image)


def test_effective_device_cpu_by_default() -> None:
    from cadenza.omr.adapters.homr import get_effective_device

    assert get_effective_device(use_gpu=False) == "cpu"
    assert HOMREngine(use_gpu=False).device == "cpu"


def test_effective_device_with_mocked_gpu(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import types

    from cadenza.omr.adapters.homr import get_effective_device

    fake_ort = types.ModuleType("onnxruntime")
    fake_ort.get_available_providers = lambda: ["CUDAExecutionProvider", "CPUExecutionProvider"]  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)

    assert get_effective_device(use_gpu=True) == "cuda"
    assert HOMREngine(use_gpu=True).device == "cuda"


def test_import_homr_disables_detect_title(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import types
    from unittest.mock import MagicMock

    from cadenza.omr.adapters.homr import _import_homr

    fake_homr: Any = types.ModuleType("homr")
    fake_main: Any = types.ModuleType("homr.main")
    original_detect_title = MagicMock()
    fake_main.detect_title = original_detect_title
    fake_homr.main = fake_main

    monkeypatch.setitem(sys.modules, "homr", fake_homr)
    monkeypatch.setitem(sys.modules, "homr.main", fake_main)

    imported_main = _import_homr()
    assert imported_main is fake_main
    assert fake_main.detect_title is not original_detect_title

    future = fake_main.detect_title("debug_obj", "top_staff_obj")
    assert future.done()
    assert future.result() == ""
    original_detect_title.assert_not_called()

    # Llamarlo dos veces es idempotente y no cambia nada
    patched_detect_title = fake_main.detect_title
    imported_again = _import_homr()
    assert imported_again is fake_main
    assert fake_main.detect_title is patched_detect_title
    original_detect_title.assert_not_called()


def test_import_homr_raises_if_detect_title_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import types

    from cadenza.omr.adapters.homr import _import_homr

    fake_homr: Any = types.ModuleType("homr")
    fake_main: Any = types.ModuleType("homr.main")
    fake_homr.main = fake_main

    monkeypatch.setitem(sys.modules, "homr", fake_homr)
    monkeypatch.setitem(sys.modules, "homr.main", fake_main)

    with pytest.raises(RuntimeError, match="detect_title"):
        _import_homr()


@pytest.mark.skipif(not HOMR_INSTALLED, reason="requiere el extra opcional 'homr'")
def test_homr_real_transcription_does_not_initialize_ocr_reader() -> None:
    import json

    import homr.title_detection

    manifest_path = Path(__file__).resolve().parents[3] / "data" / "manifest.json"
    if not manifest_path.is_file():
        pytest.skip("no hay data/manifest.json para inferencia real de HOMR")
    entries = json.loads(manifest_path.read_text(encoding="utf-8"))["entries"]
    real_image = manifest_path.parent / entries[0]["image"]
    if not real_image.is_file():
        pytest.skip(f"no existe la imagen del manifiesto: {real_image}")

    assert homr.title_detection._reader is None
    engine = HOMREngine(use_gpu=False)
    doc = engine.transcribe(real_image)
    assert doc is not None
    assert homr.title_detection._reader is None
