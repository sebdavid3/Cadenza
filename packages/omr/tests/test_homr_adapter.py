"""Pruebas del adaptador `HOMREngine` y de su importación perezosa."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from cadenza.omr import HOMREngine

HOMR_INSTALLED = importlib.util.find_spec("homr") is not None


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
