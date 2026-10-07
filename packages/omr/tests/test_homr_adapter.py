"""Pruebas del adaptador `HOMREngine` y de su importación perezosa."""

from __future__ import annotations

from pathlib import Path

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
