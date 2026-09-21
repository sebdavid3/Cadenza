"""Adaptador OMR de Cadenza: puerto `OMREngine` y adaptadores concretos."""

from __future__ import annotations

from .adapters import FakeOMREngine, HOMREngine
from .adapters.homr import ensure_cuda_dll_dirs
from .engine import OMREngine

__all__ = ["FakeOMREngine", "HOMREngine", "OMREngine", "ensure_cuda_dll_dirs"]
