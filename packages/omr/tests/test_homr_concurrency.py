"""HOMR no es seguro entre hilos: el adaptador serializa sus llamadas (#165)."""

from __future__ import annotations

import sys
import threading
import time
import types
from pathlib import Path
from typing import Any

import pytest
from cadenza.omr.adapters.homr import _run_homr


def test_concurrent_calls_never_overlap_inside_homr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Las sesiones de ONNX de HOMR son estado global del proceso: con dos hilos a la vez fallan con
    # errores internos de ONNX Runtime (medido en el servidor del despliegue, #165).
    fake_generator: Any = types.ModuleType("homr.music_xml_generator")
    fake_generator.XmlGeneratorArguments = lambda *args: args
    if "homr" not in sys.modules:
        monkeypatch.setitem(sys.modules, "homr", types.ModuleType("homr"))
    monkeypatch.setitem(sys.modules, "homr.music_xml_generator", fake_generator)

    state = {"active": 0, "peak": 0, "calls": 0}
    counter = threading.Lock()

    def process_image(path: str, _config: Any, _args: Any) -> None:
        with counter:
            state["active"] += 1
            state["calls"] += 1
            state["peak"] = max(state["peak"], state["active"])
        time.sleep(0.05)
        Path(path).with_suffix(".musicxml").write_text("<score-partwise/>", encoding="utf-8")
        with counter:
            state["active"] -= 1

    fake_main: Any = types.SimpleNamespace(
        ProcessingConfig=lambda **kwargs: kwargs,
        download_weights=lambda **_kwargs: None,
        process_image=process_image,
    )
    images = []
    for n in range(4):
        image = tmp_path / f"imagen{n}.png"
        image.write_bytes(b"png")
        images.append(image)
    results: list[str] = []

    def run(image: Path) -> None:
        results.append(_run_homr(fake_main, image, False))

    threads = [threading.Thread(target=run, args=(image,)) for image in images]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert state["calls"] == 4
    assert state["peak"] == 1
    assert results == ["<score-partwise/>"] * 4
