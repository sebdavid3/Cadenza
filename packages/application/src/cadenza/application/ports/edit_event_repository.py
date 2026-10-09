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


class InMemoryEditEventRepository(EditEventRepository):
    """Implementación en memoria de EditEventRepository para pruebas unitarias."""

    def __init__(self) -> None:
        self.events: dict[str, list[EditEvent]] = {}

    def next_seq(self, session_id: str) -> int:
        return len(self.events.get(session_id, [])) + 1

    def append(self, session_id: str, edit: EditEvent) -> EditEvent:
        self.events.setdefault(session_id, []).append(edit)
        return edit

    def list_events(self, session_id: str) -> tuple[EditEvent, ...]:
        return tuple(self.events.get(session_id, []))
