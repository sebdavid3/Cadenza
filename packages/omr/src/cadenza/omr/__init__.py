"""Adaptador OMR de Cadenza: puerto `OMREngine` y adaptadores concretos."""

from __future__ import annotations

from .adapters import FakeOMREngine, HOMREngine
from .engine import OMREngine

__all__ = ["FakeOMREngine", "HOMREngine", "OMREngine"]
