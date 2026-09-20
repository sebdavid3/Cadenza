"""Adaptadores concretos del puerto `OMREngine`."""

from __future__ import annotations

from .fake import FakeOMREngine
from .homr import HOMREngine

__all__ = ["FakeOMREngine", "HOMREngine"]
