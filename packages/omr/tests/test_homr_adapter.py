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


class _FakeMultiStaff:
    def _select_grandstaffs(self, brace_dot: list[Any]) -> list[Any]:
        return []


def _fake_model(monkeypatch: pytest.MonkeyPatch, fake_homr: Any) -> Any:
    import sys
    import types

    fake_model: Any = types.ModuleType("homr.model")
    fake_model.MultiStaff = type("MultiStaff", (_FakeMultiStaff,), {})
    fake_homr.model = fake_model
    monkeypatch.setitem(sys.modules, "homr.model", fake_model)
    return fake_model


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
    _fake_model(monkeypatch, fake_homr)

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


def test_import_homr_replaces_the_grand_staff_choice(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import types
    from unittest.mock import MagicMock

    from cadenza.omr.adapters.homr import _import_homr

    fake_homr: Any = types.ModuleType("homr")
    fake_main: Any = types.ModuleType("homr.main")
    fake_main.detect_title = MagicMock()
    fake_homr.main = fake_main
    monkeypatch.setitem(sys.modules, "homr", fake_homr)
    monkeypatch.setitem(sys.modules, "homr.main", fake_main)
    fake_model = _fake_model(monkeypatch, fake_homr)
    original = fake_model.MultiStaff._select_grandstaffs

    _import_homr()
    patched = fake_model.MultiStaff._select_grandstaffs
    _import_homr()

    assert patched is not original
    assert fake_model.MultiStaff._select_grandstaffs is patched


def test_import_homr_raises_if_detect_title_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import types

    from cadenza.omr.adapters.homr import _import_homr

    fake_homr: Any = types.ModuleType("homr")
    fake_main: Any = types.ModuleType("homr.main")
    fake_homr.main = fake_main

    monkeypatch.setitem(sys.modules, "homr", fake_homr)
    monkeypatch.setitem(sys.modules, "homr.main", fake_main)
    _fake_model(monkeypatch, fake_homr)

    with pytest.raises(RuntimeError, match="detect_title"):
        _import_homr()


class _FakeHomrMain:
    """`homr.main` de mentira: cada pasada escribe `<imagen>.musicxml` con el modo de la lectura
    y anota el par de piano `piano` como haría la elección de pares."""

    def __init__(self, piano: list[int] | None, fail_alone: bool = False) -> None:
        self.piano = piano
        self.fail_alone = fail_alone
        self.passes: list[str] = []

    def ProcessingConfig(self, **kwargs: Any) -> dict[str, Any]:
        return kwargs

    def download_weights(self, **kwargs: Any) -> None:
        pass

    def process_image(self, image: str, config: Any, args: Any) -> None:
        from cadenza.omr.adapters import homr_grand_staff

        record = homr_grand_staff._current
        assert record is not None
        self.passes.append(record.mode.value)
        if self.piano is not None:
            record.piano_pairs.append(self.piano)
        if self.fail_alone and record.mode.value == "alone":
            raise RuntimeError("HOMR falló")
        Path(image).with_suffix(".musicxml").write_text(f"<{record.mode.value}/>", encoding="utf-8")


def _fake_xml_generator(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import types

    module: Any = types.ModuleType("homr.music_xml_generator")
    module.XmlGeneratorArguments = lambda *args: args
    monkeypatch.setitem(sys.modules, "homr.music_xml_generator", module)


def test_a_page_without_voice_and_piano_below_is_read_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cadenza.omr.adapters.homr import _run_homr

    _fake_xml_generator(monkeypatch)
    image = tmp_path / "page.png"
    image.write_bytes(b"png")
    for piano in (None, [0, 1]):
        # Sin piano, o con el piano arriba (que no se combina), basta una lectura.
        main = _FakeHomrMain(piano=piano)
        assert _run_homr(main, image, use_gpu=False) == "<paired/>"
        assert main.passes == ["paired"]


def test_a_voice_and_piano_page_is_read_both_ways_and_combined(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cadenza.omr.adapters import homr_piano
    from cadenza.omr.adapters.homr import _run_homr

    _fake_xml_generator(monkeypatch)
    combined: list[tuple[str, str]] = []

    def combine(paired: str, alone: str) -> str:
        combined.append((paired, alone))
        return "<combined/>"

    monkeypatch.setattr(homr_piano, "combine_musicxml", combine)
    image = tmp_path / "page.png"
    image.write_bytes(b"png")
    main = _FakeHomrMain(piano=[1, 2])

    assert _run_homr(main, image, use_gpu=False) == "<combined/>"
    assert main.passes == ["paired", "alone"]
    assert combined == [("<paired/>", "<alone/>")]


def test_if_the_reading_alone_fails_the_paired_one_is_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cadenza.omr.adapters.homr import _run_homr

    _fake_xml_generator(monkeypatch)
    image = tmp_path / "page.png"
    image.write_bytes(b"png")
    main = _FakeHomrMain(piano=[1, 2], fail_alone=True)

    assert _run_homr(main, image, use_gpu=False) == "<paired/>"
    assert main.passes == ["paired", "alone"]


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
