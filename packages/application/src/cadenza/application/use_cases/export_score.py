"""Caso de uso: exportación de partituras a MusicXML o MIDI (Issue #12, ADR-0010, ADR-0012)."""

from __future__ import annotations

from ..exceptions import SessionNotFound, UnsupportedExportFormat
from ..export import ExportedScore, ExportFormat
from ..ports.edit_event_repository import EditEventRepository
from ..ports.score_exporter import ScoreExporter
from ..ports.score_state_cache import ScoreStateCache
from ..ports.session_repository import SessionRepository
from ..score_state import load_state, musicxml_of
from ..stage_timing import timed_stage
from ..user import Role, User


def export_score(
    session_repo: SessionRepository,
    edit_repo: EditEventRepository,
    exporter: ScoreExporter,
    *,
    session_id: str,
    format: str | ExportFormat,
    current_user: User,
    score_cache: ScoreStateCache | None = None,
) -> ExportedScore:
    """Exporta el ScoreIR materializado de una sesión en el formato solicitado.

    - Control de acceso ADR-0012: transcriptor ajeno recibe SessionNotFound;
      investigador o dueño pueden exportar.
    - Se materializa el estado actual: ``materialize(raw_score, edits)``.
    - Formatos admitidos: 'musicxml' y 'midi'. Cualquier otro lanza UnsupportedExportFormat.
    - Con `score_cache`, el estado y su MusicXML salen de la caché si están: cada estado se
      exporta una sola vez (#275, ADR-0037).
    """
    raw_fmt = format.value if isinstance(format, ExportFormat) else str(format).strip().lower()
    try:
        export_fmt = ExportFormat(raw_fmt)
    except ValueError:
        raise UnsupportedExportFormat(str(format)) from None

    with timed_stage("db"):
        session = session_repo.get(session_id)
    if session is None:
        raise SessionNotFound(session_id)

    # Control de acceso ADR-0012: transcriptor solo puede ver su propia sesión
    if current_user.role == Role.TRANSCRIPTOR and session.owner_id != current_user.id:
        raise SessionNotFound(session_id)

    with timed_stage("db"):
        edits = edit_repo.list_events(session_id)
    key, state = load_state(session_id, session.document, edits, score_cache)

    if export_fmt is ExportFormat.MUSICXML:
        _, xml_content = musicxml_of(key, state, exporter, score_cache)
        return ExportedScore(
            content=xml_content,
            media_type="application/vnd.recordare.musicxml+xml",
            filename=f"session-{session_id}.musicxml",
        )
    elif export_fmt is ExportFormat.MIDI:
        with timed_stage("export"):
            midi_content = exporter.to_midi(state.score)
        return ExportedScore(
            content=midi_content,
            media_type="audio/midi",
            filename=f"session-{session_id}.mid",
        )
    else:  # pragma: no cover
        raise UnsupportedExportFormat(str(format))
