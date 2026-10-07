"""Jerarquía de excepciones del módulo OMR."""

from __future__ import annotations


class OMRError(Exception):
    """Excepción base para errores en el reconocimiento óptico de música."""


class OMRTranscriptionError(OMRError):
    """Error durante la transcripción de una imagen (ej. fallo al detectar pentagramas)."""
