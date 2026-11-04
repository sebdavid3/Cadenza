"""Puertos de la capa de sugerencias: el modelo y su registro (ADR-0036 §7, §8).

`SuggestionModel` es un `typing.Protocol`: la implementación de `cadenza.validation.learned`
lo cumple por estructura sin importar esta capa (no hay ciclo). El registro es distinto del
del motor OMR (`ModelRegistry`): sus métricas (SER, OMR-NED) no tienen sentido aquí.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Protocol

from cadenza.domain import Finding, ScoreDocument, SuggestionResult


class SuggestionModel(Protocol):
    """Capa que, tras las reglas, ordena sus candidatos y propone posibles errores propios."""

    @property
    def version(self) -> str:
        """Versión del registro que se cargó: va en cada sugerencia y en la procedencia."""
        ...

    def suggest(self, document: ScoreDocument, findings: Sequence[Finding]) -> SuggestionResult:
        """Los hallazgos de las reglas, en su orden, con sus sugerencias, y los propios."""
        ...


@dataclass(frozen=True)
class SuggestionModelVersionData:
    """Una versión registrada de la capa: su artefacto, cómo se entrenó y lo que midió."""

    version: str
    artifact_hash: str
    dataset_hash: str
    config_hash: str
    seed: int
    model_type: str
    feature_version: int
    metrics: Mapping[str, Any] = field(default_factory=dict)
    promoted: bool = False
    created_at: datetime | None = None


class SuggestionModelRegistry(ABC):
    """Registro de las versiones de la capa, con una sola promovida a la vez (ADR-0036 §8).

    Promover es explícito y no comprueba métricas: el criterio (mejorar en la partición de
    prueba fija) lo aplica la CLI de `ml` antes de llamar a `promote` (§9).
    """

    @abstractmethod
    def register(self, version: SuggestionModelVersionData) -> SuggestionModelVersionData:
        """Registra una versión; falla con ValueError si ya existe."""

    @abstractmethod
    def promote(self, version_id: str) -> SuggestionModelVersionData:
        """Promueve una versión y retira la promoción de las demás; KeyError si no existe."""

    @abstractmethod
    def active(self) -> SuggestionModelVersionData | None:
        """La versión promovida, o None."""

    @abstractmethod
    def versions(self) -> tuple[SuggestionModelVersionData, ...]:
        """Todas las versiones, de la más antigua a la más reciente."""


class InMemorySuggestionModelRegistry(SuggestionModelRegistry):
    """Registro en memoria para las pruebas."""

    def __init__(self) -> None:
        self._versions: list[SuggestionModelVersionData] = []

    def register(self, version: SuggestionModelVersionData) -> SuggestionModelVersionData:
        if any(existing.version == version.version for existing in self._versions):
            raise ValueError(f"version already registered: {version.version}")
        created = (
            version
            if version.created_at is not None
            else replace(version, created_at=datetime.now(UTC))
        )
        self._versions.append(created)
        return created

    def promote(self, version_id: str) -> SuggestionModelVersionData:
        if not any(v.version == version_id for v in self._versions):
            raise KeyError(version_id)
        self._versions = [replace(v, promoted=v.version == version_id) for v in self._versions]
        return next(v for v in self._versions if v.version == version_id)

    def active(self) -> SuggestionModelVersionData | None:
        return next((v for v in self._versions if v.promoted), None)

    def versions(self) -> tuple[SuggestionModelVersionData, ...]:
        return tuple(self._versions)
