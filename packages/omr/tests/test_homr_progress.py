"""Avance de HOMR por pentagrama, para la transcripción en segundo plano (#375, ADR-0063)."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest
from cadenza.omr.adapters import homr_grand_staff, homr_progress
from cadenza.omr.progress import OMRProgress, Reading, listening, report


def _fake_staff_parsing(voices: int) -> Any:
    """`homr.staff_parsing` de mentira: cada pentagrama leído devuelve su índice."""

    module: Any = types.ModuleType("homr.staff_parsing")
    module._get_number_of_voices = lambda staffs: voices
    module.parse_staff_image = lambda debug, index, *rest: [f"symbol-{index}"]
    return module


def _parse_staffs(module: Any, systems: int) -> list[Any]:
    """Como `homr.staff_parsing.parse_staffs`: cuenta las voces y lee cada una en cada sistema."""

    staffs = [object()] * systems
    voices = module._get_number_of_voices(staffs)
    read = []
    index = 0
    for _ in range(voices):
        for _ in staffs:
            read.append(module.parse_staff_image("debug", index, "staff", "image", "regions", "c"))
            index += 1
    return read


def test_each_staff_of_a_reading_is_announced_before_it_is_read() -> None:
    module = _fake_staff_parsing(voices=2)
    assert homr_progress.install(module)
    events: list[OMRProgress] = []

    with listening(events.append), homr_progress.reading(Reading.FIRST):
        read = _parse_staffs(module, systems=3)

    # Primero se detectan los pentagramas; después, el 1 de 6, el 2 de 6…
    assert events == [OMRProgress(Reading.FIRST)] + [
        OMRProgress(Reading.FIRST, staffs=6, staff=staff) for staff in range(1, 7)
    ]
    # Lo leído es lo que devuelve HOMR, tal cual.
    assert read == [[f"symbol-{index}"] for index in range(6)]


def test_the_wrappers_read_the_same_without_anyone_listening() -> None:
    module = _fake_staff_parsing(voices=3)
    homr_progress.install(module)

    assert _parse_staffs(module, systems=2) == [[f"symbol-{index}"] for index in range(6)]
    with homr_progress.reading(Reading.PIANO):
        assert _parse_staffs(module, systems=2) == [[f"symbol-{index}"] for index in range(6)]


def test_installing_twice_wraps_once() -> None:
    module = _fake_staff_parsing(voices=1)
    homr_progress.install(module)
    count, read = module._get_number_of_voices, module.parse_staff_image

    homr_progress.install(module)

    assert module._get_number_of_voices is count
    assert module.parse_staff_image is read


def test_a_homr_without_those_functions_still_transcribes() -> None:
    module: Any = types.ModuleType("homr.staff_parsing")
    module.parse_staff_image = lambda *args: []

    assert homr_progress.install(module) is False
    assert not hasattr(module, "_get_number_of_voices")


def test_a_failing_listener_does_not_stop_the_reading() -> None:
    module = _fake_staff_parsing(voices=1)
    homr_progress.install(module)

    def broken(progress: OMRProgress) -> None:
        raise RuntimeError("quien escucha se cae")

    with listening(broken), homr_progress.reading(Reading.FIRST):
        assert _parse_staffs(module, systems=2) == [["symbol-0"], ["symbol-1"]]


def test_reporting_without_a_listener_does_nothing() -> None:
    report(OMRProgress(Reading.FIRST))


class _FakeHomrMain:
    """`homr.main` de mentira que lee con el `staff_parsing` de mentira: en la emparejada, 2 voces
    (la de arriba y el piano como gran pentagrama) por 2 sistemas; con cada mano sola, 3."""

    def __init__(self, staff_parsing: Any) -> None:
        self.staff_parsing = staff_parsing

    def ProcessingConfig(self, **kwargs: Any) -> dict[str, Any]:
        return kwargs

    def download_weights(self, **kwargs: Any) -> None:
        pass

    def process_image(self, image: str, config: Any, args: Any) -> None:
        record = homr_grand_staff._current
        assert record is not None
        record.piano_pairs.append([1, 2])
        alone = record.mode is homr_grand_staff.PianoReading.ALONE
        self.staff_parsing._get_number_of_voices = lambda staffs: 3 if alone else 2
        homr_progress.install(self.staff_parsing)
        _parse_staffs(self.staff_parsing, systems=2)
        Path(image).with_suffix(".musicxml").write_text(f"<{record.mode.value}/>", encoding="utf-8")


def test_a_voice_and_piano_page_reports_its_second_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cadenza.omr.adapters import homr_piano
    from cadenza.omr.adapters.homr import _run_homr

    generator: Any = types.ModuleType("homr.music_xml_generator")
    generator.XmlGeneratorArguments = lambda *args: args
    monkeypatch.setitem(sys.modules, "homr.music_xml_generator", generator)
    monkeypatch.setattr(homr_piano, "combine_musicxml", lambda paired, alone: "<combined/>")
    image = tmp_path / "page.png"
    image.write_bytes(b"png")
    events: list[OMRProgress] = []

    with listening(events.append):
        main = _FakeHomrMain(_fake_staff_parsing(voices=2))
        assert _run_homr(main, image, use_gpu=False) == "<combined/>"

    first = [OMRProgress(Reading.FIRST)] + [
        OMRProgress(Reading.FIRST, staffs=4, staff=staff) for staff in range(1, 5)
    ]
    piano = [OMRProgress(Reading.PIANO)] + [
        OMRProgress(Reading.PIANO, staffs=6, staff=staff) for staff in range(1, 7)
    ]
    assert events == first + piano
