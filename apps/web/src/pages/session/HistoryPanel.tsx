import { useMemo } from "react";
import type { EditEventRead, ScoreIRPayload } from "../../types";
import { isoUtc, parseUtc } from "../transcription/sessions";
import { describeEdit, placeOf, readLog, type LogEntry } from "./history";

interface HistoryPanelProps {
  /** Log de ediciones de la sesión (`edits` de `GET /sessions/{id}`). */
  edits: readonly EditEventRead[];
  /** Con varios pentagramas, cada edición dice en cuál está. */
  multiStaff: boolean;
  /** Estado actual: cuenta los pentagramas de toda la partitura. */
  score: ScoreIRPayload | null;
}

const capitalize = (text: string) => `${text.charAt(0).toUpperCase()}${text.slice(1)}`;

const WHEN = new Intl.DateTimeFormat("es", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

/** Qué hace una edición del log: la corrección, o qué edición deshace o rehace. */
function changeOf(entry: LogEntry, bySeq: ReadonlyMap<number, EditEventRead>): string {
  const undone = entry.undoes === null ? undefined : bySeq.get(entry.undoes);
  if (undone) return `Deshace la ${String(undone.seq)}: ${describeEdit(undone)}`;
  if (entry.redoes !== null) {
    return `Rehace la ${String(entry.redoes)}: ${describeEdit(entry.edit)}`;
  }
  return capitalize(describeEdit(entry.edit));
}

/**
 * Historia de ediciones de la sesión (ADR-0034), de la más reciente a la primera. El log no se
 * borra (ADR-0007): deshacer añade una edición que compensa la deshecha, y rehacer, la misma
 * edición otra vez. Lo deshecho se tacha y lo dice, también para un lector de pantalla.
 */
export function HistoryPanel({ edits, multiStaff, score }: HistoryPanelProps) {
  const log = useMemo(() => readLog(edits), [edits]);
  const bySeq = useMemo(() => new Map(edits.map((edit) => [edit.seq, edit])), [edits]);
  const count = edits.length;
  const undone = log.entries.filter((entry) => entry.undoneBy !== null).length;

  return (
    <section className="history" aria-labelledby="history-title">
      <div className="history__head">
        <h2 id="history-title" className="history__title">
          Historia
        </h2>
        <span className="label history__count">{count}</span>
      </div>
      {count === 0 ? (
        <p className="history__empty">Sin ediciones: la partitura es la que transcribió HOMR.</p>
      ) : (
        <>
          <p className="history__summary">
            {`${String(count)} ${count === 1 ? "edición" : "ediciones"}`}
            {undone > 0 && `, ${String(undone)} ${undone === 1 ? "deshecha" : "deshechas"}`}. Nada
            se borra: deshacer añade una edición que compensa la deshecha.
          </p>
          <details className="history__details">
            <summary className="label">
              {count === 1 ? "Ver la edición" : `Ver las ${String(count)} ediciones`}
            </summary>
            {/* Con muchas ediciones la lista se desplaza: con el foco, también con el teclado. */}
            <ol
              className="history__list"
              role="list"
              tabIndex={0}
              aria-label="Ediciones, de la más reciente a la primera"
            >
              {[...log.entries].reverse().map((entry) => {
                // En UTC aunque llegue sin zona (así lo da la API sobre SQLite).
                const date = parseUtc(entry.edit.created_at);
                return (
                  <li
                    key={entry.edit.id}
                    className="history__item"
                    data-undone={entry.undoneBy !== null}
                  >
                    <span className="label history__seq">{entry.edit.seq}</span>
                    <span className="history__change">{changeOf(entry, bySeq)}</span>
                    <span className="history__meta">
                      {capitalize(placeOf(entry.edit, multiStaff, score))}
                      {!Number.isNaN(date.getTime()) && (
                        <>
                          {" · "}
                          <time dateTime={isoUtc(entry.edit.created_at)}>{WHEN.format(date)}</time>
                        </>
                      )}
                    </span>
                    {entry.undoneBy !== null && (
                      <span className="label history__tag">Deshecha en la {entry.undoneBy}</span>
                    )}
                  </li>
                );
              })}
            </ol>
          </details>
        </>
      )}
    </section>
  );
}
