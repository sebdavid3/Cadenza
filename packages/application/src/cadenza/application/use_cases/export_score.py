"""Caso de uso: exportación de partituras a MusicXML o MIDI (Issue #12, ADR-0010, ADR-0012)."""

from __future__ import annotations

from collections.abc import Mapping

from cadenza.domain import ScoreIR, materialize

from ..exceptions import SessionNotFound, UnsupportedExportFormat
from ..export import ExportedScore, ExportFormat
from ..ports.edit_event_repository import EditEventRepository
from ..ports.score_exporter import ScoreExporter
from ..ports.session_repository import SessionRepository
from ..user import Role, User


def export_score(
    session_repo: SessionRepository,
    edit_repo: EditEventRepository,
    exporter: ScoreExporter,
    *,
    session_id: str,
    format: str | ExportFormat,
    current_user: User,
) -> ExportedScore:
    """Exporta el ScoreIR materializado de una sesión en el formato solicitado.

    - Control de acceso ADR-0012: transcriptor ajeno recibe SessionNotFound;
      investigador o dueño pueden exportar.
    - Se materializa el estado actual: ``materialize(raw_score, edits)``.
    - Formatos admitidos: 'musicxml' y 'midi'. Cualquier otro lanza UnsupportedExportFormat.
    """
    raw_fmt = format.value if isinstance(format, ExportFormat) else str(format).strip().lower()
    try:
        export_fmt = ExportFormat(raw_fmt)
    except ValueError:
        raise UnsupportedExportFormat(str(format)) from None

    session = session_repo.get(session_id)
    if session is None:
        raise SessionNotFound(session_id)

    # Control de acceso ADR-0012: transcriptor solo puede ver su propia sesión
    if current_user.role == Role.TRANSCRIPTOR and session.owner_id != current_user.id:
        raise SessionNotFound(session_id)

    if hasattr(session.document, "score"):
        raw_score = session.document.score
    elif isinstance(session.document, Mapping) and "score" in session.document:
        score_val = session.document["score"]
        raw_score = (
            score_val if isinstance(score_val, ScoreIR) else ScoreIR.from_primitive(score_val)
        )
    else:
        raise ValueError("Documento de sesión sin ScoreIR válido")

    edits = edit_repo.list_events(session_id)
    current_score = materialize(raw_score, edits)

    if export_fmt is ExportFormat.MUSICXML:
        xml_content = exporter.to_musicxml(current_score)
        return ExportedScore(
            content=xml_content,
            media_type="application/vnd.recordare.musicxml+xml",
            filename=f"session-{session_id}.musicxml",
        )
    elif export_fmt is ExportFormat.MIDI:
        midi_content = exporter.to_midi(current_score)
        return ExportedScore(
            content=midi_content,
            media_type="audio/midi",
            filename=f"session-{session_id}.mid",
        )
    else:  # pragma: no cover
        raise UnsupportedExportFormat(str(format))
