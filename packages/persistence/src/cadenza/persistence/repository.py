"""Puerto y adaptador del log de ediciones append-only (ADR-0007).

El puerto `EditEventRepository` define el contrato que consume la capa de
aplicación; `SqlAlchemyEditEventRepository` es una implementación intercambiable
(SQLite/PostgreSQL) que nunca expone el ORM hacia afuera.
"""

from cadenza.application import EditEventRepository, SequenceConflict
from cadenza.domain import Anchor, EditEvent, EditOp
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from .models import EditEventRecord
from .models import Session as SessionRecord

__all__ = ["EditEventRepository", "SqlAlchemyEditEventRepository"]


class SqlAlchemyEditEventRepository(EditEventRepository):
    """Adaptador SQLAlchemy del log de ediciones."""

    def __init__(self, session: DbSession) -> None:
        self._session = session

    def next_seq(self, session_id: str) -> int:
        current = self._session.scalar(
            select(func.coalesce(func.max(EditEventRecord.seq), 0)).where(
                EditEventRecord.session_id == session_id
            )
        )
        return int(current or 0) + 1

    def append(self, session_id: str, edit: EditEvent) -> EditEvent:
        row = EditEventRecord(
            id=edit.id,
            session_id=session_id,
            seq=edit.seq,
            op=edit.op.value,
            author=edit.author,
            anchor=edit.anchor.to_primitive(),
            before=None if edit.before is None else dict(edit.before),
            after=None if edit.after is None else dict(edit.after),
            reverts_edit_id=edit.reverts_edit_id,
            created_at=edit.created_at,
        )
        try:
            self._session.add(row)
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise SequenceConflict(
                expected_seq=edit.seq,
                actual_seq=edit.seq,
                message=(
                    f"Conflicto de secuencia al registrar la edición con seq={edit.seq} "
                    f"en la sesión '{session_id}'."
                ),
            ) from exc
        return edit

    def list_events(self, session_id: str) -> tuple[EditEvent, ...]:
        document_id = self._session.scalar(
            select(SessionRecord.document_id).where(SessionRecord.id == session_id)
        )
        if document_id is None:
            return ()
        rows = self._session.scalars(
            select(EditEventRecord)
            .where(EditEventRecord.session_id == session_id)
            .order_by(EditEventRecord.seq)
        ).all()
        return tuple(self._to_domain(document_id, row) for row in rows)

    @staticmethod
    def _to_domain(document_id: str, row: EditEventRecord) -> EditEvent:
        return EditEvent(
            id=row.id,
            document_id=document_id,
            seq=row.seq,
            anchor=Anchor.from_primitive(row.anchor),
            op=EditOp(row.op),
            author=row.author,
            created_at=row.created_at,
            before=row.before,
            after=row.after,
            reverts_edit_id=row.reverts_edit_id,
        )
