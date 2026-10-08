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

    def __init__(
        self,
        expected_seq: int = 0,
        actual_seq: int = 0,
        message: str | None = None,
    ) -> None:
        msg = (
            message
            or f"Conflicto de secuencia: base_seq esperado {expected_seq}, recibido {actual_seq}"
        )
        super().__init__(msg)
        self.expected_seq = expected_seq
        self.actual_seq = actual_seq
        self.message = msg


class ArtifactNotFound(ApplicationError):
    """El artefacto solicitado no existe en el almacén."""

    def __init__(self, sha256: str) -> None:
        super().__init__(f"Artefacto no encontrado: {sha256}")
        self.sha256 = sha256


class UserNotFound(ApplicationError):
    """El usuario solicitado no existe."""

    def __init__(self, identifier: str) -> None:
        super().__init__(f"Usuario no encontrado: {identifier}")
        self.identifier = identifier


class DuplicateUsername(ApplicationError):
    """Ya existe un usuario con el mismo nombre de usuario."""

    def __init__(self, username: str) -> None:
        super().__init__(f"Nombre de usuario ya existente: {username}")
        self.username = username


class NotAuthenticated(ApplicationError):
    """Fallo de autenticación: credenciales inválidas o token ausente/inválido (ADR-0012)."""

    def __init__(self, message: str = "Credenciales inválidas") -> None:
        super().__init__(message)
        self.message = message


class Forbidden(ApplicationError):
    """Acceso prohibido: permisos o rol insuficiente para la operación (ADR-0012)."""

    def __init__(self, message: str = "Permisos insuficientes") -> None:
        super().__init__(message)
        self.message = message


class WeakPassword(ApplicationError):
    """La contraseña no cumple con la longitud mínima de seguridad (ADR-0012)."""

    def __init__(self, min_length: int = 8) -> None:
        super().__init__(f"La contraseña debe tener al menos {min_length} caracteres")
        self.min_length = min_length


class SessionClosed(ApplicationError):
    """La sesión está finalizada y no admite más ediciones sin reapertura explícita.

    ADR-0014, #34.
    """

    def __init__(self, session_id: str) -> None:
        msg = (
            f"La sesión '{session_id}' está finalizada y no admite más ediciones. "
            "Debe reabrirse explícitamente para continuar editando."
        )
        super().__init__(msg)
        self.session_id = session_id
        self.message = msg


class UnsupportedExportFormat(ApplicationError):
    """El formato de exportación solicitado no es admitido (Issue #12)."""

    def __init__(self, fmt: str) -> None:
        msg = (
            f"Formato de exportación no admitido: '{fmt}'. "
            "Los formatos válidos son: 'musicxml' y 'midi'."
        )
        super().__init__(msg)
        self.format = fmt
        self.message = msg


class NoEditsToUndo(ApplicationError):
    """No hay ediciones activas para deshacer en la sesión (#35, ADR-0007)."""

    def __init__(self, session_id: str) -> None:
        msg = f"No hay ediciones activas para deshacer en la sesión '{session_id}'."
        super().__init__(msg)
        self.session_id = session_id
        self.message = msg
