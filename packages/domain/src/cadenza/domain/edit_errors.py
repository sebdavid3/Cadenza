"""Error de contenido de una edición (ADR-0017), común a la validación de todas las operaciones."""

from __future__ import annotations


class InvalidEditPayload(ValueError):
    """El `after` de una edición no es coherente con su operación (ADR-0017)."""
