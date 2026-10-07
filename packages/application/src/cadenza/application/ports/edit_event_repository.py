"""Puerto abstracto del log de eventos de edición inmutables (ADR-0007, ADR-0009)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from cadenza.domain import EditEvent


class EditEventRepository(ABC):
    """Contrato append-only: los eventos solo se agregan y consultan en orden de secuencia."""

    @abstractmethod
    def next_seq(self, session_id: str) -> int:
        """Devuelve el siguiente número de secuencia monotónico para la sesión."""

    @abstractmethod
    def append(self, session_id: str, edit: EditEvent) -> EditEvent:
        """Persiste un evento de edición inmutable."""

    @abstractmethod
    def list_events(self, session_id: str) -> tuple[EditEvent, ...]:
        """Devuelve todos los eventos de la sesión ordenados por seq."""
