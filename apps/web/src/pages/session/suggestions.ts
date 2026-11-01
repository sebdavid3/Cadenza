import type { AnchorPayload, FindingRead, SessionViewRead, SuggestionRead } from "../../types";
import { carryAnchor } from "./edits";
import { anchorKey } from "./noteMap";

/**
 * Sugerencias de la capa que aprende de las correcciones (#258, ADR-0036, ADR-0047): ediciones
 * propuestas junto al posible error que corrigen. Aplicar una es una corrección de la persona;
 * rechazarla guarda su respuesta y no descarta el posible error.
 */

/** Si un posible error lo señala la capa (`learned.*`) y no una regla del validador. */
export const isLearned = (finding: Pick<FindingRead, "rule_id">) =>
  finding.rule_id.startsWith("learned.");

/** De dónde viene un posible error, en palabras: distingue los de la capa de los de las reglas. */
export const originLabel = (finding: Pick<FindingRead, "rule_id">) =>
  isLearned(finding) ? "Aprendido de las correcciones" : "Regla del validador";

/** La confianza en palabras, nunca en porcentaje (#258). */
export const confidenceLabel = (level: SuggestionRead["confidence_level"]) =>
  level === "high" ? "Confianza alta" : "Confianza media";

/**
 * Qué se puede hacer con una sugerencia en el estado que se ve:
 * - `open`: de la validación del estado que se ve y sin respuesta: se aplica o se rechaza;
 * - `old`: antigua, de una validación anterior al estado que se ve o rechazada por el servidor al
 *   aplicarla (`stale_suggestion`): no se aplica hasta revalidar, pero se puede rechazar;
 * - `later`: de un estado posterior al que se ve (otra pestaña): hay que recargar la sesión;
 * - `accepted` y `rejected`: ya tiene respuesta, que no cambia (ADR-0036 §5).
 */
export type SuggestionState = "open" | "old" | "later" | "accepted" | "rejected";

export function suggestionState(
  finding: Pick<FindingRead, "at_seq">,
  suggestion: Pick<SuggestionRead, "id" | "response">,
  seq: number,
  stale: ReadonlySet<number> = new Set(),
): SuggestionState {
  if (suggestion.response === "accepted") return "accepted";
  if (suggestion.response === "rejected") return "rejected";
  const validated = finding.at_seq ?? 0;
  if (validated > seq) return "later";
  if (validated < seq || stale.has(suggestion.id)) return "old";
  return "open";
}

/** Una sugerencia con el posible error que corrige y lo que se puede hacer con ella. */
export interface SuggestionItem {
  finding: FindingRead;
  suggestion: SuggestionRead;
  state: SuggestionState;
}

/** Las sugerencias de un posible error, con su estado en el que se ve. */
export function suggestionItems(
  finding: FindingRead,
  seq: number,
  stale: ReadonlySet<number> = new Set(),
): SuggestionItem[] {
  return (finding.suggestions ?? []).map((suggestion) => ({
    finding,
    suggestion,
    state: suggestionState(finding, suggestion, seq, stale),
  }));
}

/**
 * Las sugerencias de los posibles errores activos que proponen cambiar el evento elegido (`anchor`,
 * en el estado actual de `detail`). El ancla de cada sugerencia es relativa al estado de su
 * validación (ADR-0011): se lleva al actual con la regla de desplazamiento; si su evento ya no
 * está, o es de un estado posterior, no es de esta nota.
 */
export function suggestionsAt(
  findings: readonly FindingRead[],
  anchor: AnchorPayload,
  detail: SessionViewRead,
  stale: ReadonlySet<number> = new Set(),
): SuggestionItem[] {
  const seq = detail.current_seq ?? 0;
  const key = anchorKey(anchor);
  return findings
    .filter((finding) => finding.status !== "dismissed")
    .flatMap((finding) => suggestionItems(finding, seq, stale))
    .filter(({ finding, suggestion }) => {
      const validated = finding.at_seq ?? 0;
      const carried =
        validated === seq ? suggestion.anchor : carryAnchor(suggestion.anchor, validated, detail);
      return carried !== null && anchorKey(carried) === key;
    });
}

/** La lista con la sugerencia `updated` en lugar de la suya, en el posible error que la lleva. */
export function withSuggestion(
  findings: readonly FindingRead[],
  updated: SuggestionRead,
): FindingRead[] {
  return findings.map((finding) =>
    finding.suggestions?.some((suggestion) => suggestion.id === updated.id)
      ? {
          ...finding,
          suggestions: finding.suggestions.map((suggestion) =>
            suggestion.id === updated.id ? updated : suggestion,
          ),
        }
      : finding,
  );
}

/** La lista con la respuesta `response` en la sugerencia `id`, si está. */
export function withResponse(
  findings: readonly FindingRead[],
  id: number,
  response: NonNullable<SuggestionRead["response"]>,
): FindingRead[] {
  const found = findings
    .flatMap((finding) => finding.suggestions ?? [])
    .find((suggestion) => suggestion.id === id);
  return found ? withSuggestion(findings, { ...found, response }) : [...findings];
}
