"""Contrato del puerto `OMREngine` y de sus adaptadores."""

from __future__ import annotations

import inspect

import pytest
from cadenza.omr import FakeOMREngine, HOMREngine, OemerEngine, OMREngine


def test_omr_engine_is_abstract() -> None:
    assert inspect.isabstract(OMREngine)
    with pytest.raises(TypeError):
        OMREngine()  # type: ignore[abstract]


@pytest.mark.parametrize("engine", [FakeOMREngine(), HOMREngine(), OemerEngine()])
def test_adapters_implement_port(engine: OMREngine) -> None:
    assert isinstance(engine, OMREngine)
    assert engine.engine_id


def test_engines_are_interchangeable() -> None:
    engines: list[OMREngine] = [FakeOMREngine(), HOMREngine(), OemerEngine()]
    assert {engine.engine_id for engine in engines} == {"fake", "homr", "oemer"}
