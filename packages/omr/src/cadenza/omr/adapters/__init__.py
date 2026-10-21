"""Adaptadores concretos del puerto `OMREngine`: solo HOMR (ADR-0018)."""

from __future__ import annotations

from .homr import HOMREngine

__all__ = ["HOMREngine"]
