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
         Con ``"is_chord": true``, una nota más del acorde de la nota anterior (ADR-0055). La
         compensatoria de borrar la primera nota de un acorde lleva además ``"next_in_chord"``.

    5. `DELETE_EVENT` ("DeleteEvent"):
       - Elimina el evento musical anclado en la voz del compás.
       - ``before``: snapshot del evento previo.
       - ``after``: ``None`` o, en la primera nota de un acorde, ``{"keep_chord": true}``: la
         nota siguiente pasa a ser la primera, con la figura y las marcas del acorde (ADR-0055).

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

    Compás y tresillos (ADR-0044). También de tipo «fijar», y tampoco mueven ningún evento.

    12. `SET_TIME` ("SetTime"):
        - Cambia la indicación de compás desde el compás del ancla hasta el siguiente cambio, en
          todos los pentagramas de la parte.
        - ``before``/``after``: ``{"time_signature": {"beats": int, "beat_type": int,
          "symbol": "common" | "cut" | None} | None, "measures": int}`` (``measures``, el
          número de compases que cambia, es opcional en el ``after`` del cliente; ``None`` en
          ``time_signature`` solo lo escribe la compensatoria).
        - Con ``"all_parts": true`` en el ``after`` (#326), en todas las partes de la partitura,
          cada una en su tramo: el ``before`` guarda además ``"all_parts": true`` y ``"parts"``,
          ``[{"time_signature", "measures"} | None, ...]``, lo de cada parte (None si no tiene
          el compás), con lo que la compensatoria devuelve cada parte a lo suyo. Sin él, solo
          la parte del ancla, como antes de #326.

    13. `SET_TUPLET` ("SetTuplet"):
        - Pone o quita el tresillo (3:2) a los eventos seguidos de una voz desde el ancla.
        - ``before``/``after``: ``{"durations": [str | None, ...]}``, sus figuras.

    Figura de un acorde (ADR-0049). También de tipo «fijar», y tampoco mueve ningún evento.

    14. `SET_CHORD_DURATION` ("SetChordDuration"):
        - Fija la figura de todas las notas de un acorde, anclada en su primera nota.
        - ``before``/``after``: ``{"durations": [str | None, ...]}``, una por nota del acorde
          (en el ``after`` del cliente, todas iguales y con duración).

    Ligadura de prolongación (ADR-0055). También de tipo «fijar», y tampoco mueve ningún evento.

    15. `SET_TIE` ("SetTie"):
        - Pone o quita la ligadura de prolongación entre la nota anclada y la que la sigue (en su
          voz o, al cruzar la barra, al empezar el compás siguiente), o quita la marca de la
          nota anclada sola.
        - ``before``/``after``: ``{"tie": str | None, "next": {"measure": int, "voice": int,
          "event_index": int, "tie": str | None} | None}``, el valor de cada nota
          (``"start"``, ``"continue"``, ``"stop"`` o ``None``).

    Los huecos de una voz (ADR-0058). También de tipo «fijar», y tampoco mueve ningún evento.

    16. `SET_EVENT_KIND` ("SetEventKind"):
        - Convierte un hueco (un silencio invisible, ADR-0032) en un silencio que se ve o en una
          nota en su lugar, con la misma figura. También un silencio que se ve en una nota (#350).
          La compensatoria lo devuelve a lo que era.
        - ``before``/``after``: ``{"kind": "note" | "rest", "pitch": str | None,
          "hidden": bool}``.
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
    SET_TIME = "SetTime"
    SET_TUPLET = "SetTuplet"
    SET_CHORD_DURATION = "SetChordDuration"
    SET_TIE = "SetTie"
    SET_EVENT_KIND = "SetEventKind"


MARK_EDIT_OPS: frozenset[EditOp] = frozenset(
    {EditOp.SET_NOTE_MARKS, EditOp.SET_DYNAMIC, EditOp.SET_WEDGE, EditOp.SET_SLUR}
)
"""Operaciones sobre las marcas de notación (ADR-0039). No entran en el dataset ni en las
métricas de los experimentos, como las marcas mismas (ADR-0031 §6)."""

METER_EDIT_OPS: frozenset[EditOp] = frozenset(
    {EditOp.SET_TIME, EditOp.SET_TUPLET, EditOp.SET_CHORD_DURATION, EditOp.SET_TIE}
)
"""Operaciones sobre el compás y la duración de varios eventos a la vez: los tresillos
(ADR-0044), la figura de un acorde (ADR-0049) y la ligadura de prolongación, que suma las
figuras de dos notas (ADR-0055). `derive_edit_events` no las produce (no alinea las indicaciones
de compás, un tresillo o la figura de un acorde salen como un `SetDuration` por nota, y una
ligadura como un borrado y una inserción de cada nota), así que no entran en la cobertura de
`exp_02` ni son muestras del dataset."""

GAP_EDIT_OPS: frozenset[EditOp] = frozenset({EditOp.SET_EVENT_KIND})
"""Operaciones sobre los huecos de una voz (ADR-0058): convertir un silencio invisible en un
silencio que se ve o en una nota en su lugar. `derive_edit_events` no las produce (un silencio que
se ve no se empareja con uno invisible: el diff da un borrado del hueco y una inserción), así que
no entran en la cobertura de `exp_02` ni son muestras del dataset. Las métricas de esfuerzo las
cuentan como contenido."""

CONTENT_EDIT_OPS: frozenset[EditOp] = frozenset(
    {
        EditOp.SET_PITCH,
        EditOp.SET_DURATION,
        EditOp.SET_ACCIDENTAL,
        EditOp.INSERT_EVENT,
        EditOp.DELETE_EVENT,
        EditOp.SET_CLEF,
        EditOp.SET_KEY,
    }
)
"""Operaciones sobre el contenido (alturas, duraciones, eventos, clave y armadura): las que
derivan los experimentos del diff con la verdad (`derive_edit_events`) y las que cubre el
dataset (ADR-0039). Una operación nueva se clasifica al crearla (ADR-0039 §3.7)."""


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
    - SetPitch / SetDuration / SetAccidental / SetClef / SetKey, las de marcas (SetNoteMarks,
      SetDynamic, SetWedge, SetSlur, ADR-0039), las de compás y tresillos (SetTime,
      SetTuplet, ADR-0044), la figura de un acorde (SetChordDuration, ADR-0049) y la ligadura
      de prolongación (SetTie, ADR-0055) y los huecos de una voz (SetEventKind, ADR-0058):
      intercambia `before` y `after`.
    - InsertEvent: el inverso es un DeleteEvent en el mismo ancla, con
      `before = edit.after` y `after = None`.
    - DeleteEvent: el inverso es un InsertEvent en el mismo ancla, con
      `before = None` y `after = edit.before` (si borró la primera nota de un acorde, su
      `before` lleva `next_in_chord` y el inverso devuelve también la nota siguiente, ADR-0055).

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
