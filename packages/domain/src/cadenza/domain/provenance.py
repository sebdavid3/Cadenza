"""Trazabilidad del origen de un `ScoreDocument`."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class Provenance:
    """Documenta de dónde provienen los datos y cada modificación.

    Permite reproducir un experimento indicando motor, versión de modelo y
    versión de reglas (requisito del capítulo de experimentación).
    """

    omr_engine: str
    model_version: str | None = None
    rules_version: str | None = None
    source_image_hash: str | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.omr_engine:
            raise ValueError("omr_engine must be non-empty")

    def to_primitive(self) -> dict[str, Any]:
        return {
            "omr_engine": self.omr_engine,
            "model_version": self.model_version,
            "rules_version": self.rules_version,
            "source_image_hash": self.source_image_hash,
            "created_at": self.created_at.isoformat() if self.created_at is not None else None,
        }

    @classmethod
    def from_primitive(cls, data: Mapping[str, Any]) -> Provenance:
        created = data.get("created_at")
        return cls(
            omr_engine=str(data["omr_engine"]),
            model_version=None if data.get("model_version") is None else str(data["model_version"]),
            rules_version=None if data.get("rules_version") is None else str(data["rules_version"]),
            source_image_hash=(
                None if data.get("source_image_hash") is None else str(data["source_image_hash"])
            ),
            created_at=None if created is None else datetime.fromisoformat(str(created)),
        )
