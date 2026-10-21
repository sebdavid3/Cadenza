"""Contrato del puerto `OMREngine` y de sus adaptadores (ADR-0018)."""

from __future__ import annotations

import inspect

import cadenza.omr
import pytest
from cadenza.omr import HOMREngine, OMREngine
from cadenza.omr.testing import FakeOMREngine


def test_omr_engine_is_abstract() -> None:
    assert inspect.isabstract(OMREngine)
    with pytest.raises(TypeError):
        OMREngine()  # type: ignore[abstract]


def test_homr_is_the_only_production_adapter() -> None:
    assert isinstance(HOMREngine(), OMREngine)
    assert HOMREngine().engine_id == "homr"


@pytest.mark.parametrize(
    "name",
    ["FakeOMREngine", "OemerEngine", "OEMER_ENGINE_ID", "ensure_oemer_checkpoints"],
)
def test_package_does_not_export_other_engines(name: str) -> None:
    assert not hasattr(cadenza.omr, name)
    assert name not in cadenza.omr.__all__


def test_oemer_adapter_no_longer_exists() -> None:
    with pytest.raises(ModuleNotFoundError):
        __import__("cadenza.omr.adapters.oemer")


def test_test_double_implements_port_without_being_a_production_adapter() -> None:
    double = FakeOMREngine()
    assert isinstance(double, OMREngine)
    assert double.engine_id == "fake"
    with pytest.raises(ModuleNotFoundError):
        __import__("cadenza.omr.adapters.fake")


def test_test_double_mirrors_homr_from_active_model_signature() -> None:
    """La API reconstruye el motor con `type(engine).from_active_model(...)` (#133)."""
    homr = inspect.signature(HOMREngine.from_active_model).parameters
    double = inspect.signature(FakeOMREngine.from_active_model).parameters
    assert list(double) == list(homr)
