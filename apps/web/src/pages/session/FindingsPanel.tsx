import type { FindingRead } from "../../types";
import { ruleLabel, type MeasureMark } from "./findings";

interface FindingsPanelProps {
  marks: readonly MeasureMark[];
  dismissed: readonly FindingRead[];
  /** Estado validado si es anterior al actual (la partitura se editó después). */
  staleSeq: number | null;
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

/**
 * Posibles errores del validador agrupados por compás. Nunca se presentan como errores seguros:
 * el validador no lo detecta todo y lo que señala hay que comprobarlo (ADR-0021).
 */
export function FindingsPanel({
  marks,
  dismissed,
  staleSeq,
  selectedKey,
  onSelect,
  status,
  errorText,
  onRetry,
}: FindingsPanelProps) {
  const total = marks.reduce((count, mark) => count + mark.findings.length, 0);

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
        <p className="findings__empty">El validador no ha señalado ningún compás.</p>
      )}

      {status === "ready" && total > 0 && (
        <ul className="findings__list" role="list">
          {marks.map((mark) => {
            const selected = mark.key === selectedKey;
            return (
              <li key={mark.key}>
                <button
                  type="button"
                  className="findings__item"
                  aria-pressed={selected}
                  onClick={() => {
                    onSelect(selected ? null : mark.key);
                  }}
                >
                  <span className="findings__measure">Compás {mark.measureNumber}</span>
                  {mark.findings.map((finding) => (
                    <span key={finding.id} className="findings__finding">
                      <FindingText finding={finding} />
                    </span>
                  ))}
                </button>
              </li>
            );
          })}
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
