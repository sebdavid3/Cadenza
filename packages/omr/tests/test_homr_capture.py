"""Las cajas de los pentagramas, el recorte del papel y los sistemas de una lectura de HOMR
(#403, ADR-0067), con un `homr.main` de mentira que llama a las funciones que envuelve la captura
como lo hace el de verdad."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from cadenza.omr.adapters import homr_capture, homr_grand_staff

SYSTEMS_XML = """<?xml version="1.0"?>
<score-partwise><part id="P1">
<measure number="1"/><measure number="2"/><measure number="3"/>
<measure number="4"><print new-system="yes"/></measure><measure number="5"/>
</part><part id="P2"><measure number="1"/></part></score-partwise>"""


def _staff(x0: float, y0: float, x1: float, y1: float, grand: bool = False) -> Any:
    return SimpleNamespace(min_x=x0, min_y=y0, max_x=x1, max_y=y1, is_grandstaff=grand)


def test_crop_rectangle_finds_the_paper_inside_the_image() -> None:
    image: Any = np.zeros((100, 200, 3), dtype=np.uint8)
    assert homr_capture.crop_rectangle(image, image) is None
    assert homr_capture.crop_rectangle(image, image[10:60, 30:180]) == (30, 10, 150, 50)
    gray: Any = np.zeros((40, 50), dtype=np.uint8)
    assert homr_capture.crop_rectangle(gray, gray[5:, 7:]) == (7, 5, 43, 35)


def test_staff_boxes_are_relative_to_the_image_homr_saw() -> None:
    staffs = [SimpleNamespace(staffs=[_staff(100, 50, 900, 150), _staff(100, 300, 900, 500, True)])]
    boxes = homr_capture.staff_boxes(staffs, (1000, 1000))
    assert boxes == [
        {"grand": False, "cx": 0.5, "cy": 0.1, "w": 0.8, "h": 0.1},
        {"grand": True, "cx": 0.5, "cy": 0.4, "w": 0.8, "h": 0.2},
    ]


def test_systems_of_gives_the_first_measure_of_each_system() -> None:
    assert homr_capture.systems_of(SYSTEMS_XML) == ["1", "4"]
    assert homr_capture.systems_or_empty("<no es xml") == []


class _CapturingHomrMain:
    """`homr.main` que en cada lectura recorta el papel, guarda las cajas y escribe el MusicXML,
    en ese orden, como `process_image` de HOMR 0.7."""

    def __init__(self, piano: list[int] | None = None, fail_alone: bool = False) -> None:
        self.piano = piano
        self.fail_alone = fail_alone
        self.configs: list[dict[str, Any]] = []
        self.saved_files: list[str] = []

    def ProcessingConfig(self, **kwargs: Any) -> dict[str, Any]:
        self.configs.append(kwargs)
        return kwargs

    def download_weights(self, **kwargs: Any) -> None:
        pass

    def autocrop(self, image: Any) -> Any:
        return image[20:220, 40:440]

    def save_staff_positions(self, multi_staffs: Any, shape: Any, file_path: str) -> None:
        self.saved_files.append(file_path)  # fuera de una captura, HOMR lo escribe

    def process_image(self, image: str, config: Any, args: Any) -> None:
        record = homr_grand_staff._current
        assert record is not None
        if self.piano is not None:
            record.piano_pairs.append(self.piano)
        if self.fail_alone and record.mode.value == "alone":
            raise RuntimeError("HOMR falló")
        cropped = self.autocrop(np.zeros((300, 500, 3), dtype=np.uint8))
        alone = record.mode.value == "alone"
        staffs = [_staff(0, 10, 400, 40), _staff(0, 60, 400, 90, grand=not alone)]
        if config["write_staff_positions"]:
            self.save_staff_positions(
                [SimpleNamespace(staffs=staffs)], cropped.shape[:2], image + ".txt"
            )
        Path(image).with_suffix(".musicxml").write_text(SYSTEMS_XML, encoding="utf-8")


@pytest.fixture
def xml_generator(monkeypatch: pytest.MonkeyPatch) -> None:
    module: Any = types.ModuleType("homr.music_xml_generator")
    module.XmlGeneratorArguments = lambda *args: args
    monkeypatch.setitem(sys.modules, "homr.music_xml_generator", module)


def test_a_reading_leaves_its_boxes_crop_and_systems(tmp_path: Path, xml_generator: None) -> None:
    from cadenza.omr.adapters.homr import _run_homr

    main = _CapturingHomrMain()
    homr_capture.install(main)
    homr_capture.install(main)  # una sola vez
    image = tmp_path / "page.png"
    image.write_bytes(b"png")
    capture = homr_capture.Capture()

    _run_homr(main, image, use_gpu=False, capture=capture)

    assert main.configs[0]["write_staff_positions"] is True
    assert main.saved_files == []  # durante la captura no se escribe ningún archivo
    assert capture.systems == ["1", "4"]
    [reading] = capture.readings
    assert reading.mode == "paired"
    assert reading.source_shape == (300, 500)
    assert reading.autocrop == (40, 20, 400, 200)
    assert reading.image_shape == (200, 400)
    assert [staff["grand"] for staff in reading.staves] == [False, True]
    assert reading.staves[0]["cy"] == pytest.approx(25 / 200)

    # Fuera de una captura, HOMR guarda sus cajas como siempre.
    _run_homr(main, image, use_gpu=False)
    assert len(main.saved_files) == 1


def test_a_voice_and_piano_page_keeps_both_readings_or_only_the_one_that_worked(
    tmp_path: Path, xml_generator: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cadenza.omr.adapters import homr_piano
    from cadenza.omr.adapters.homr import _run_homr

    monkeypatch.setattr(homr_piano, "combine_musicxml", lambda paired, alone: "<combinado/>")
    image = tmp_path / "page.png"
    image.write_bytes(b"png")

    both = homr_capture.Capture()
    main = _CapturingHomrMain(piano=[1, 2])
    homr_capture.install(main)
    assert _run_homr(main, image, use_gpu=False, capture=both) == "<combinado/>"
    assert [reading.mode for reading in both.readings] == ["paired", "alone"]
    assert [s["grand"] for s in both.readings[1].staves] == [False, False]
    # Los sistemas salen del MusicXML de HOMR, no de la combinación.
    assert both.systems == ["1", "4"]

    paired_only = homr_capture.Capture()
    failing = _CapturingHomrMain(piano=[1, 2], fail_alone=True)
    homr_capture.install(failing)
    _run_homr(failing, image, use_gpu=False, capture=paired_only)
    assert [reading.mode for reading in paired_only.readings] == ["paired"]


def test_a_failing_capture_does_not_break_the_reading(tmp_path: Path, xml_generator: None) -> None:
    from cadenza.omr.adapters.homr import _run_homr

    main = _CapturingHomrMain()
    main.autocrop = lambda image: image.copy()[5:, 5:]  # type: ignore[method-assign]
    homr_capture.install(main)
    image = tmp_path / "page.png"
    image.write_bytes(b"png")
    capture = homr_capture.Capture()

    assert _run_homr(main, image, use_gpu=False, capture=capture) == SYSTEMS_XML
    assert capture.errors and "recorte" in capture.errors[0]
    assert capture.readings[0].autocrop is None


def test_the_capture_primitive_keeps_the_raw_musicxml_compressed() -> None:
    capture = homr_capture.Capture(systems=["1", "4"])
    capture.readings.append(
        homr_capture.ReadingCapture(
            mode="paired", image_shape=(10, 20), source_shape=None, autocrop=None
        )
    )
    primitive = homr_capture.capture_primitive(
        capture, SYSTEMS_XML, homr_version="0.7.0", preprocessed=False
    )
    assert primitive["format_version"] == 1
    assert primitive["systems"] == ["1", "4"]
    assert primitive["readings"][0]["mode"] == "paired"
    assert primitive["musicxml"]["encoding"] == "zlib+base64"
    assert homr_capture.raw_musicxml(primitive) == SYSTEMS_XML
    assert len(primitive["musicxml"]["sha256"]) == 64


def _homr_available() -> bool:
    try:
        from homr import main  # noqa: F401

        return True
    except (ImportError, RuntimeError):
        return False


def _manifest_image(root: Path) -> Path | None:
    import json

    manifest = root / "data" / "manifest.json"
    if not manifest.is_file():
        return None
    image = (
        manifest.parent / json.loads(manifest.read_text(encoding="utf-8"))["entries"][0]["image"]
    )
    return image if image.is_file() else None


@pytest.mark.skipif(not _homr_available(), reason="requiere el extra opcional 'homr'")
def test_a_real_transcription_keeps_its_capture_and_its_strips_match_the_score() -> None:
    from cadenza.learning.staff_strips import plan_strips
    from cadenza.omr import HOMREngine
    from PIL import Image

    # La imagen del manifiesto del corpus, como las demás pruebas con HOMR real (#97).
    image = _manifest_image(Path(__file__).resolve().parents[3])
    if image is None:
        pytest.skip("no hay data/manifest.json con su imagen para ejecutar HOMR real")
    document = HOMREngine(use_gpu=False).transcribe(image)

    capture = document.omr_capture
    assert capture is not None and capture["errors"] == []
    assert capture["readings"] and capture["readings"][0]["staves"]
    assert capture["systems"][0] == str(document.score.parts[0].staves[0].measures[0].number)
    assert homr_capture.raw_musicxml(dict(capture)).lstrip().startswith("<?xml")
    with Image.open(image) as photo:
        strips = plan_strips(capture, document.score, photo.size)
    staves = sum(len(part.staves) for part in document.score.parts)
    assert len(strips) >= len(capture["systems"]) and staves >= 1
    assert all(0 <= s.box[0] < s.box[2] <= photo.size[0] for s in strips)
