"""Excepciones de la capa de aplicación (ADR-0009).

Indican errores de negocio y orquestación desacoplados de protocolos de transporte (HTTP, CLI).
"""

from __future__ import annotations


class ApplicationError(Exception):
    """Clase base de todas las excepciones de la capa de aplicación."""


class SessionNotFound(ApplicationError):
    """La sesión solicitada no existe o no pertenece al usuario."""

    def __init__(self, session_id: str) -> None:
        super().__init__(f"Sesión no encontrada: {session_id}")
        self.session_id = session_id


class InvalidEdit(ApplicationError):
    """La edición propuesta no es válida o no se puede proyectar sobre el ScoreIR actual."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class SequenceConflict(ApplicationError):
    """Conflicto de concurrencia: el base_seq de la edición no coincide con el estado actual."""

    def __init__(self, expected_seq: int, actual_seq: int) -> None:
        super().__init__(
            f"Conflicto de secuencia: base_seq esperado {expected_seq}, recibido {actual_seq}"
        )
        self.expected_seq = expected_seq
        self.actual_seq = actual_seq
