"""Eventos de edición inmutables del ciclo Human-in-the-Loop (ADR-0007).

En el plano online, ``after`` se valida con `validate_after` y ``before`` lo fija el
servidor con `snapshot_before` (`edit_payload`, ADR-0017).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from .anchor import Anchor


class EditOp(StrEnum):
    """Operaciones de corrección admitidas sobre un evento anclado.

    Esquemas de payload (atributos ``before`` y ``after`` en `EditEvent`):

    1. `SET_PITCH` ("SetPitch"):
       - Modifica la altura absoluta de una nota.
       - ``before``: ``{"pitch": str}`` (p. ej. ``{"pitch": "C4"}``).
       - ``after``: ``{"pitch": str}`` (p. ej. ``{"pitch": "D4"}``).

    2. `SET_DURATION` ("SetDuration"):
       - Modifica la duración en tiempos (beats) de un evento musical.
       - ``before``: ``{"duration_beats": Fraction | int | float | str}``.
       - ``after``: ``{"duration_beats": Fraction | int | float | str}``.

    3. `SET_ACCIDENTAL` ("SetAccidental"):
       - Modifica la alteración de una nota conservando su nombre de nota y octava.
       - ``before``: ``{"accidental": str | None}`` (p. ej. ``{"accidental": ""}``).
       - ``after``: ``{"accidental": str | None}``
         (p. ej. ``"#"``, ``"b"``, ``"natural"``, ``"##"``, ``"bb"``).

    4. `INSERT_EVENT` ("InsertEvent"):
       - Inserta un nuevo evento musical antes de la posición anclada.
       - ``before``: ``None``.
       - ``after``: ``{"kind": str, "pitch": str | None, "duration_beats": Fraction | str, ...}``.

    5. `DELETE_EVENT` ("DeleteEvent"):
       - Elimina el evento musical anclado en la voz del compás.
       - ``before``: snapshot del evento previo.
       - ``after``: ``None``.

    6. `SET_CLEF` ("SetClef"):
       - Modifica la clave musical del compás al que apunta el ancla.
       - ``before``: snapshot de clave previa o ``None``.
       - ``after``: ``{"clef": dict | str | Clef}`` o primitivo ``{"sign": str, "line": int}``.

    7. `SET_KEY` ("SetKey"):
       - Modifica la armadura de clave del compás al que apunta el ancla.
       - ``before``: snapshot de armadura previa o ``None``.
       - ``after``: ``{"key_signature": dict | KeySignature}`` o primitivo ``{"fifths": int}``.

    Marcas de notación (ADR-0031, ADR-0039). Las cuatro son de tipo «fijar»: el servidor guarda
    en ``before`` el estado que sustituyen y la compensatoria intercambia ``before`` y ``after``.
    No mueven ningún evento (no cambian el ``event_index`` de las anclas).

    8. `SET_NOTE_MARKS` ("SetNoteMarks"):
       - Fija las articulaciones y el calderón del evento anclado.
       - ``before``/``after``: ``{"articulations": [str, ...], "fermata": bool}``.

    9. `SET_DYNAMIC` ("SetDynamic"):
       - Pone, cambia o quita la dinámica de una posición del compás del ancla.
       - ``before``/``after``: ``{"offset_beats": str, "mark": str | None}``.

    10. `SET_WEDGE` ("SetWedge"):
        - Crea un regulador con su inicio y su fin, o quita los extremos de uno.
        - ``before``/``after``: ``{"number": int, "start": {"staff", "measure",
          "offset_beats", "type"} | None, "stop": {"staff", "measure", "offset_beats"} | None}``.

    11. `SET_SLUR` ("SetSlur"):
        - Crea una ligadura de expresión con su inicio y su fin, o quita los extremos de una.
        - ``before``/``after``: ``{"number": int, "start": {"staff", "measure", "voice",
          "event_index"} | None, "stop": {...} | None}``.
    """

    SET_PITCH = "SetPitch"
    SET_DURATION = "SetDuration"
    SET_ACCIDENTAL = "SetAccidental"
    INSERT_EVENT = "InsertEvent"
    DELETE_EVENT = "DeleteEvent"
    SET_CLEF = "SetClef"
    SET_KEY = "SetKey"
    SET_NOTE_MARKS = "SetNoteMarks"
    SET_DYNAMIC = "SetDynamic"
    SET_WEDGE = "SetWedge"
    SET_SLUR = "SetSlur"


MARK_EDIT_OPS: frozenset[EditOp] = frozenset(
    {EditOp.SET_NOTE_MARKS, EditOp.SET_DYNAMIC, EditOp.SET_WEDGE, EditOp.SET_SLUR}
)
"""Operaciones sobre las marcas de notación (ADR-0039). No entran en el dataset ni en las
métricas de los experimentos, como las marcas mismas (ADR-0031 §6)."""

CONTENT_EDIT_OPS: frozenset[EditOp] = frozenset(set(EditOp) - MARK_EDIT_OPS)
"""Operaciones sobre el contenido (alturas, duraciones, eventos, clave y armadura): las que
derivan los experimentos del diff con la verdad (`derive_edit_events`) y las que cubre el
dataset (ADR-0039)."""


@dataclass(frozen=True, slots=True)
class EditEvent:
    """Corrección humana inmutable anclada a un evento musical.

    El estado actual de un `ScoreDocument` se obtiene aplicando la secuencia de
    `EditEvent` sobre el `ScoreIR` crudo. La inmutabilidad es estructural: los
    atributos son de solo lectura y los diccionarios ``before``/``after`` se
    congelan.
    """

    id: str
    document_id: str
    seq: int
    anchor: Anchor
    op: EditOp
    author: str
    created_at: datetime
    before: Mapping[str, Any] | None = None
    after: Mapping[str, Any] | None = None
    reverts_edit_id: str | None = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id must be non-empty")
        if not self.document_id:
            raise ValueError("document_id must be non-empty")
        if not self.author:
            raise ValueError("author must be non-empty")
        if self.seq < 0:
            raise ValueError("seq must be >= 0")
        if self.before is not None:
            object.__setattr__(self, "before", MappingProxyType(dict(self.before)))
        if self.after is not None:
            object.__setattr__(self, "after", MappingProxyType(dict(self.after)))

    @property
    def is_reversion(self) -> bool:
        """Indica si este evento es una reversión compensatoria de una edición previa."""
        return self.reverts_edit_id is not None

    def __hash__(self) -> int:
        # Incluye una huella estable de ``before``/``after`` para mantener la
        # coherencia con la igualdad generada (dos eventos iguales hashean igual).
        return hash(
            (
                self.id,
                self.document_id,
                self.seq,
                self.anchor,
                self.op,
                self.author,
                self.created_at,
                None if self.before is None else hash(frozenset(self.before.items())),
                None if self.after is None else hash(frozenset(self.after.items())),
                self.reverts_edit_id,
            )
        )

    def to_primitive(self) -> dict[str, Any]:
        prim: dict[str, Any] = {
            "id": self.id,
            "document_id": self.document_id,
            "seq": self.seq,
            "anchor": self.anchor.to_primitive(),
            "op": self.op.value,
            "author": self.author,
            "created_at": self.created_at.isoformat(),
            "before": None if self.before is None else dict(self.before),
            "after": None if self.after is None else dict(self.after),
        }
        if self.reverts_edit_id is not None:
            prim["reverts_edit_id"] = self.reverts_edit_id
        return prim

    @classmethod
    def from_primitive(cls, data: Mapping[str, Any]) -> EditEvent:
        before = data.get("before")
        after = data.get("after")
        reverts = data.get("reverts_edit_id")
        return cls(
            id=str(data["id"]),
            document_id=str(data["document_id"]),
            seq=int(data["seq"]),
            anchor=Anchor.from_primitive(data["anchor"]),
            op=EditOp(data["op"]),
            author=str(data["author"]),
            created_at=datetime.fromisoformat(str(data["created_at"])),
            before=None if before is None else dict(before),
            after=None if after is None else dict(after),
            reverts_edit_id=str(reverts) if reverts is not None else None,
        )


def create_inverse_edit(
    edit: EditEvent,
    *,
    id: str,
    seq: int,
    author: str,
    created_at: datetime,
) -> EditEvent:
    """Construye el evento compensatorio inverso de una edición (ADR-0007, #35).

    Invierte semánticamente cualquier operación de `EditOp`:
    - SetPitch / SetDuration / SetAccidental / SetClef / SetKey y las de marcas (SetNoteMarks,
      SetDynamic, SetWedge, SetSlur, ADR-0039): intercambia `before` y `after`.
    - InsertEvent: el inverso es un DeleteEvent en el mismo ancla, con
      `before = edit.after` y `after = None`.
    - DeleteEvent: el inverso es un InsertEvent en el mismo ancla, con
      `before = None` y `after = edit.before`.

    El evento compensatorio referencia explícitamente la edición que revierte
    mediante `reverts_edit_id = edit.id`.
    """
    if edit.op is EditOp.INSERT_EVENT:
        inv_op = EditOp.DELETE_EVENT
        inv_before = dict(edit.after) if edit.after is not None else None
        inv_after = None
    elif edit.op is EditOp.DELETE_EVENT:
        inv_op = EditOp.INSERT_EVENT
        inv_before = None
        inv_after = dict(edit.before) if edit.before is not None else None
    else:
        inv_op = edit.op
        inv_before = dict(edit.after) if edit.after is not None else None
        inv_after = dict(edit.before) if edit.before is not None else None

    return EditEvent(
        id=id,
        document_id=edit.document_id,
        seq=seq,
        anchor=edit.anchor,
        op=inv_op,
        author=author,
        created_at=created_at,
        before=inv_before,
        after=inv_after,
        reverts_edit_id=edit.id,
    )


def get_last_active_edit(edits: Sequence[EditEvent]) -> EditEvent | None:
    """Obtiene la última edición vigente que no ha sido deshecha en la sesión (#35).

    Aplica una pila de estado: cada evento compensatorio con `reverts_edit_id`
    retira del conjunto activo a la edición que revirtió. Devuelve None si
    no hay ediciones activas.
    """
    active: list[EditEvent] = []
    for e in edits:
        if e.reverts_edit_id is not None:
            for i in range(len(active) - 1, -1, -1):
                if active[i].id == e.reverts_edit_id:
                    active.pop(i)
                    break
        else:
            active.append(e)
    return active[-1] if active else None
