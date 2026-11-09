import { Link } from "react-router";
import { PixelIcon } from "../../components/PixelIcon";
import type { SessionSummaryRead } from "../../types";
import { editsLabel, findingsLabel } from "./format";
import { instrumentsSummary, nonBlank, sessionName } from "./scoreData";
import { formatTime, isoUtc, statusLabel } from "./sessions";
import { SessionThumb } from "./SessionThumb";

interface SessionPlateProps {
  session: SessionSummaryRead;
  /** De quién es, para un investigador; null para quien solo ve las suyas. */
  owner: string | null;
}

/**
 * Una sesión en el diario (#370): la imagen, el nombre que lleva a su vista, la hora, la
 * partitura y lo que le falta. Toda la lámina responde al clic; el enlace es el nombre.
 */
export function SessionPlate({ session, owner }: SessionPlateProps) {
  const findings = session.findings_count ?? 0;
  const edits = session.edits_count ?? 0;
  const time = formatTime(session.created_at);
  const composer = nonBlank(session.composer);
  // El punto que separa los instrumentos va pegado al anterior: nunca empieza una línea.
  const instruments = instrumentsSummary(session.instruments)?.replaceAll(" · ", " · ");
  const finalized = session.status === "finalized";

  return (
    <li
      className="plate"
      tabIndex={-1}
      data-session-id={session.session_id}
      data-flagged={findings > 0}
    >
      <div className="plate__image">
        <SessionThumb sessionId={session.session_id} />
      </div>
      <h3 className="plate__name">
        <Link className="plate__link" to={`/sesiones/${encodeURIComponent(session.session_id)}`}>
          <span>{sessionName(session)}</span>
          <PixelIcon name="arrow-right" />
        </Link>
      </h3>
      <p className="plate__meta">
        {owner !== null && <span className="plate__owner">{owner}</span>}
        {time && <time dateTime={isoUtc(session.created_at)}>{time}</time>}
        {composer && <span>{composer}</span>}
        {instruments && <span>{instruments}</span>}
      </p>
      <p className="plate__state">
        <span className={`chip chip--status${finalized ? " chip--finalized" : ""}`}>
          {statusLabel(session.status)}
        </span>
        {edits > 0 && <span className="plate__edits">{editsLabel(edits)}</span>}
        {/* Se lee tras el estado, pero se ve colgado de la esquina de la imagen, como el rótulo
            del compás señalado en la mesa. */}
        {findings > 0 && (
          <span className="chip chip--finding plate__flag">{findingsLabel(findings)}</span>
        )}
      </p>
    </li>
  );
}
