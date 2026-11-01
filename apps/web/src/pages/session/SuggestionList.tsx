import { useId } from "react";
import type { FindingRead, SuggestionRead } from "../../types";
import { confidenceLabel, type SuggestionItem, type SuggestionState } from "./suggestions";

/** Lo que se puede hacer con las sugerencias: quien transcribió la sesión, mientras no esté cerrada. */
export interface SuggestionActions {
  /** Ahora no se puede aplicar (se revalida, se finaliza, hay otra orden sobre los posibles errores). */
  applyBlocked: boolean;
  /** Ahora no se puede rechazar (hay otra orden sobre los posibles errores en curso). */
  rejectBlocked: boolean;
  onApply: (finding: FindingRead, suggestion: SuggestionRead) => void;
  onReject: (finding: FindingRead, suggestion: SuggestionRead) => void;
}

/** Qué se dice de una sugerencia que no se puede aplicar ahora, o de su respuesta. */
const STATE_TAGS: Record<SuggestionState, string | null> = {
  open: null,
  old: "Antigua: revalida para aplicarla",
  later: "De un estado posterior: recarga la sesión",
  accepted: "Aplicada",
  rejected: "Rechazada",
};

interface SuggestionListProps {
  items: readonly SuggestionItem[];
  /** Nombra el posible error de cada sugerencia, para sus botones: «Alteración dudosa, compás 2». */
  labelOf: (finding: FindingRead) => string;
  /** Número del posible error en su compás, si hay varios, como en su texto y su descarte. */
  ordinalOf?: (finding: FindingRead) => number | null;
  actions?: SuggestionActions;
}

/**
 * Sugerencias de la capa que aprende (#258, ADR-0036, ADR-0047): la edición propuesta en lenguaje
 * musical, con su confianza en palabras, y «Aplicar» y «Rechazar». Aplicar es una corrección como
 * cualquier otra, que se puede deshacer; rechazar guarda la respuesta y no descarta el posible
 * error. Una sugerencia antigua (la sesión avanzó desde su validación) no se aplica hasta revalidar.
 */
export function SuggestionList({ items, labelOf, ordinalOf, actions }: SuggestionListProps) {
  const base = useId();
  if (items.length === 0) return null;
  return (
    <ul className="suggestions" role="list">
      {items.map(({ finding, suggestion, state }) => {
        const textId = `${base}-${String(suggestion.id)}`;
        const ordinal = ordinalOf?.(finding) ?? null;
        const siblings = finding.suggestions ?? [];
        const number =
          siblings.length > 1 ? siblings.findIndex((s) => s.id === suggestion.id) + 1 : null;
        const tag = STATE_TAGS[state];
        // El nombre de los botones dice de qué posible error es la sugerencia, y cuál si hay varias.
        const which = `${number === null ? "" : ` ${String(number)}`} · ${
          ordinal === null ? "" : `${String(ordinal)} · `
        }${labelOf(finding)}`;
        const canReject = actions && (state === "open" || state === "old");
        return (
          <li
            key={suggestion.id}
            className="suggestion"
            data-suggestion={suggestion.id}
            data-state={state}
            tabIndex={-1}
          >
            <p className="suggestion__head">
              <span className="label suggestion__title">
                {ordinal === null ? "" : `${String(ordinal)} · `}
                Sugerencia{number === null ? "" : ` ${String(number)}`}
              </span>
              <span
                className={`label suggestion__level suggestion__level--${suggestion.confidence_level}`}
              >
                {confidenceLabel(suggestion.confidence_level)}
              </span>
            </p>
            <p id={textId} className="suggestion__text">
              {suggestion.explanation}
            </p>
            {tag && <p className="suggestion__state">{tag}</p>}
            {canReject && (
              <div className="suggestion__actions">
                {state === "open" && (
                  <button
                    type="button"
                    className="button button--compact suggestion__apply"
                    aria-disabled={actions.applyBlocked || undefined}
                    aria-describedby={textId}
                    onClick={() => {
                      if (!actions.applyBlocked) actions.onApply(finding, suggestion);
                    }}
                  >
                    Aplicar <span className="visually-hidden">la sugerencia{which}</span>
                  </button>
                )}
                <button
                  type="button"
                  className="link-button findings__action"
                  aria-disabled={actions.rejectBlocked || undefined}
                  aria-describedby={textId}
                  onClick={() => {
                    if (!actions.rejectBlocked) actions.onReject(finding, suggestion);
                  }}
                >
                  Rechazar <span className="visually-hidden">la sugerencia{which}</span>
                </button>
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
