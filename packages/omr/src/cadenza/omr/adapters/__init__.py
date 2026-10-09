"""Adaptadores concretos del puerto `OMREngine`."""

from __future__ import annotations

from .fake import FakeOMREngine
from .homr import HOMREngine
from .oemer import OEMER_ENGINE_ID, OemerEngine

__all__ = ["OEMER_ENGINE_ID", "FakeOMREngine", "HOMREngine", "OemerEngine"]
