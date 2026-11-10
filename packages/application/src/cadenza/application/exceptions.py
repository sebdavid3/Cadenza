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


class StaleDataConsent(ApplicationError):
    """El permiso de uso de los datos se dio para otro texto que el vigente (#378, ADR-0065):
    la web pide releerlo."""

    detail = "stale_data_consent"

    def __init__(self, given: str | None, current: str) -> None:
        super().__init__(
            "El texto del permiso de uso de los datos ha cambiado: vuelve a leerlo antes de darlo"
        )
        self.given = given
        self.current = current


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


class InvalidSessionMetadata(ApplicationError):
    """El título, el compositor o los instrumentos no son válidos (#235, ADR-0041).

    Demasiado largos, o instrumentos para más partes de las que tiene la partitura.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


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


class FindingNotFound(ApplicationError):
    """El hallazgo solicitado no existe en la sesión (#36)."""

    def __init__(self, finding_id: int) -> None:
        msg = f"Hallazgo no encontrado: {finding_id}"
        super().__init__(msg)
        self.finding_id = finding_id
        self.message = msg


class SuggestionNotFound(ApplicationError):
    """La sugerencia no existe en la sesión (ADR-0036 §5)."""

    def __init__(self, suggestion_id: int) -> None:
        msg = f"Sugerencia no encontrada: {suggestion_id}"
        super().__init__(msg)
        self.suggestion_id = suggestion_id
        self.message = msg


class StaleSuggestion(ApplicationError):
    """La sugerencia que se quiere aplicar no es de la validación de `base_seq` o ya tiene
    respuesta: la web la marca como antigua y ofrece revalidar (ADR-0036 §5)."""

    detail = "stale_suggestion"

    def __init__(self, suggestion_id: int) -> None:
        msg = f"La sugerencia {suggestion_id} es antigua o ya tiene respuesta"
        super().__init__(msg)
        self.suggestion_id = suggestion_id
        self.message = msg


class PreviewNotFound(ApplicationError):
    """La transcripción sin cuenta no existe, caducó o el token no es el suyo (ADR-0054).

    Las tres responden igual: no se puede averiguar cuáles existen.
    """

    def __init__(self, preview_id: str) -> None:
        msg = f"Transcripción sin cuenta no encontrada: {preview_id}"
        super().__init__(msg)
        self.preview_id = preview_id
        self.message = msg


class PreviewCapacityExceeded(ApplicationError):
    """Hay ya demasiadas transcripciones sin cuenta guardadas (ADR-0054)."""

    def __init__(self, max_active: int, retry_after_seconds: int = 60) -> None:
        msg = f"Hay {max_active} transcripciones sin cuenta guardadas: el máximo"
        super().__init__(msg)
        self.max_active = max_active
        # Lo que falta para que caduque la más antigua: antes no cabe otra (#278).
        self.retry_after_seconds = retry_after_seconds
        self.message = msg


class SuggestionConflict(ApplicationError):
    """La sugerencia no admite esa respuesta: rechazar una ya aceptada (ADR-0036 §5)."""

    def __init__(self, suggestion_id: int, message: str) -> None:
        super().__init__(message)
        self.suggestion_id = suggestion_id
        self.message = message


class InvalidEffortSegment(ApplicationError):
    """Un tramo de la medición del esfuerzo que no puede ser (#188, ADR-0050 §2).

    Un identificador vacío, largo o con caracteres raros, un tiempo negativo, una primera edición
    posterior al tiempo del tramo, o un total que no cabe en el registro.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
