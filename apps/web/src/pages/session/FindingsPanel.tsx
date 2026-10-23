import type { FindingRead } from "../../types";
import { ruleLabel, type MeasureMark } from "./findings";

interface FindingsPanelProps {
  marks: readonly MeasureMark[];
  /** Hallazgos activos cuyo compás no está en la partitura: se listan sin marca. */
  unplaced: readonly FindingRead[];
  dismissed: readonly FindingRead[];
  /** Estado validado si es anterior al actual (la partitura se editó después). */
  staleSeq: number | null;
  /** Ediciones de la sesión: sin hallazgos no se sabe si la validación es anterior a ellas. */
  edits: number;
  /** Con varios pentagramas, cada compás dice en cuál está. */
  multiStaff: boolean;
  /** Si las marcas no se pudieron situar, los compases de la lista no se pueden resaltar. */
  selectable: boolean;
  selectedKey: string | null;
  onSelect: (key: string | null) => void;
  /** Mientras llegan o si fallan los hallazgos, el panel lo dice en su lugar. */
  status: "loading" | "error" | "ready";
  errorText?: string;
  onRetry?: () => void;
}

function FindingText({ finding }: { finding: FindingRead }) {
  return (
    <>
      <span className="label findings__rule">{ruleLabel(finding.rule_id)}</span>
      <span className="findings__message">{finding.message}</span>
    </>
  );
}

function measureName(mark: MeasureMark, multiStaff: boolean) {
  const staff = multiStaff ? ` · pentagrama ${String(mark.slot.staff + 1)}` : "";
  return `Compás ${String(mark.measureNumber)}${staff}`;
}

/** Qué decir cuando no queda ningún posible error activo, sin prometer más de lo que se sabe. */
function EmptyMessage({ dismissed, edits }: { dismissed: number; edits: number }) {
  if (dismissed > 0) {
    return (
      <p className="findings__empty">
        No queda ningún posible error activo: los que señaló el validador se descartaron como falso
        positivo.
      </p>
    );
  }
  return (
    <p className="findings__empty">
      El validador no señaló ningún compás en su última validación.
      {edits > 0 &&
        " La partitura tiene ediciones: si se hicieron después de esa validación, puede que el resultado ya no esté al día."}
    </p>
  );
}

/**
 * Posibles errores del validador agrupados por compás. Nunca se presentan como errores seguros:
 * el validador no lo detecta todo y lo que señala hay que comprobarlo (ADR-0021).
 */
export function FindingsPanel({
  marks,
  unplaced,
  dismissed,
  staleSeq,
  edits,
  multiStaff,
  selectable,
  selectedKey,
  onSelect,
  status,
  errorText,
  onRetry,
}: FindingsPanelProps) {
  const total = marks.reduce((count, mark) => count + mark.findings.length, 0) + unplaced.length;

  return (
    <section className="findings" aria-labelledby="findings-title">
      <div className="findings__head">
        <h2 id="findings-title" className="findings__title">
          Posibles errores
        </h2>
        {status === "ready" && <span className="label findings__count">{total}</span>}
      </div>

      {status === "loading" && (
        <p className="findings__empty" role="status">
          Cargando los posibles errores…
        </p>
      )}

      {status === "error" && (
        <div className="findings__error" role="alert">
          <p>No se pudieron cargar los posibles errores. {errorText}</p>
          {onRetry && (
            <button type="button" className="link-button" onClick={onRetry}>
              Reintentar
            </button>
          )}
        </div>
      )}

      {status === "ready" && staleSeq !== null && (
        <p className="findings__stale">
          Corresponden a la partitura tal como estaba tras {staleSeq}{" "}
          {staleSeq === 1 ? "edición" : "ediciones"}; después se editó y todavía no se ha vuelto a
          validar.
        </p>
      )}

      {status === "ready" && total === 0 && (
        <EmptyMessage dismissed={dismissed.length} edits={edits} />
      )}

      {status === "ready" && total > 0 && (
        <ul className="findings__list" role="list">
          {marks.map((mark) => {
            const selected = mark.key === selectedKey;
            const content = (
              <>
                <span className="findings__measure">{measureName(mark, multiStaff)}</span>
                {mark.findings.map((finding) => (
                  <span key={finding.id} className="findings__finding">
                    <FindingText finding={finding} />
                  </span>
                ))}
              </>
            );
            return (
              <li key={mark.key}>
                {selectable ? (
                  <button
                    type="button"
                    className="findings__item"
                    aria-pressed={selected}
                    onClick={() => {
                      onSelect(selected ? null : mark.key);
                    }}
                  >
                    {content}
                  </button>
                ) : (
                  <div className="findings__item findings__item--static">{content}</div>
                )}
              </li>
            );
          })}
          {unplaced.map((finding) => (
            <li key={finding.id}>
              <div className="findings__item findings__item--static">
                <span className="findings__measure">Compás {finding.anchor.measure}</span>
                <span className="findings__finding">
                  <FindingText finding={finding} />
                </span>
                <span className="findings__reason">
                  Ese compás ya no está en la partitura: no se puede marcar.
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}

      <p className="findings__notice">
        El validador señala compases que conviene revisar con la imagen. No lo detecta todo: que no
        señale un compás no garantiza que esté bien transcrito.
      </p>

      {status === "ready" && dismissed.length > 0 && (
        <details className="findings__dismissed">
          <summary className="label">Descartados como falso positivo · {dismissed.length}</summary>
          <ul role="list">
            {dismissed.map((finding) => (
              <li key={finding.id} className="findings__dismissed-item">
                <span className="findings__measure">Compás {finding.anchor.measure}</span>
                <FindingText finding={finding} />
                {finding.dismissal_reason && (
                  <span className="findings__reason">Motivo: {finding.dismissal_reason}</span>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
