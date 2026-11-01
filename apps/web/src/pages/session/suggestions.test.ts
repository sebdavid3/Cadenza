import { describe, expect, it } from "vitest";
import type { FindingRead, SessionViewRead, SuggestionRead } from "../../types";
import {
  confidenceLabel,
  isLearned,
  originLabel,
  suggestionItems,
  suggestionState,
  suggestionsAt,
  withResponse,
  withSuggestion,
} from "./suggestions";

const anchor = (measure: number, eventIndex = 0) => ({
  part: 0,
  staff: 0,
  measure,
  voice: 0,
  event_index: eventIndex,
  staff_id: "part-0-staff-0",
  bbox: null,
  confidence: null,
});

function suggestion(id: number, measure: number, changes: Partial<SuggestionRead> = {}) {
  return {
    id,
    op: "SetAccidental",
    anchor: anchor(measure),
    before: { accidental: null },
    after: { accidental: "#" },
    confidence: 0.91,
    confidence_level: "high",
    explanation: "Cambiar Do4 por Do♯4. En 30 de 33 casos parecidos, la corrección fue esa.",
    source: "learned",
    model_version: "sug-1",
    response: null,
    ...changes,
  } satisfies SuggestionRead;
}

function finding(id: number, measure: number, changes: Partial<FindingRead> = {}): FindingRead {
  return {
    id,
    rule_id: "learned.accidental",
    severity: "warning",
    message: "Puede que este Do4 sea Do♯4.",
    suggested_fix: "Cambiar Do4 por Do♯4.",
    anchor: anchor(measure),
    at_seq: 0,
    status: "active",
    dismissed_at: null,
    dismissed_by: null,
    dismissal_reason: null,
    suggestions: [suggestion(id * 10, measure)],
    ...changes,
  };
}

/** Un compás con dos notas, para que una inserción desplace la segunda. */
function detail(seq: number, edits: SessionViewRead["edits"] = []): SessionViewRead {
  const note = (pitch: string) => ({
    kind: "note",
    voice: 0,
    pitch,
    duration_beats: "1",
    tie: null,
    is_chord: false,
    bbox: null,
    confidence: null,
    ir_handle: null,
  });
  return {
    session_id: "s",
    document_id: "d",
    omr_engine: "homr",
    findings: [],
    edits,
    current_score: {
      parts: [
        {
          id: "part-0",
          staves: [
            {
              id: "part-0-staff-0",
              measures: [
                { number: 1, events: [note("C4"), note("D4"), note("E4")] },
                { number: 2, events: [note("F4")] },
              ],
            },
          ],
        },
      ],
    },
    current_seq: seq,
    image_artifact: "img",
    status: "correcting",
    condition: "assisted",
    owner_id: "ana",
  } as SessionViewRead;
}

describe("origen y confianza en palabras", () => {
  it("distingue los posibles errores de la capa de los de las reglas", () => {
    expect(isLearned(finding(1, 1))).toBe(true);
    expect(isLearned(finding(1, 1, { rule_id: "accidental.repeated" }))).toBe(false);
    expect(originLabel(finding(1, 1))).toBe("Aprendido de las correcciones");
    expect(originLabel(finding(1, 1, { rule_id: "measure.balance" }))).toBe("Regla del validador");
  });

  it("dice la confianza con palabras, sin porcentaje", () => {
    expect(confidenceLabel("high")).toBe("Confianza alta");
    expect(confidenceLabel("medium")).toBe("Confianza media");
  });
});

describe("suggestionState", () => {
  it("se aplica si es de la validación del estado que se ve y no tiene respuesta", () => {
    expect(suggestionState({ at_seq: 2 }, { id: 1, response: null }, 2)).toBe("open");
  });

  it("es antigua si la sesión avanzó desde su validación", () => {
    expect(suggestionState({ at_seq: 1 }, { id: 1, response: null }, 2)).toBe("old");
  });

  it("es antigua si el servidor la rechazó al aplicarla (stale_suggestion)", () => {
    expect(suggestionState({ at_seq: 2 }, { id: 7, response: null }, 2, new Set([7]))).toBe("old");
  });

  it("de un estado posterior al que se ve, hay que recargar", () => {
    expect(suggestionState({ at_seq: 3 }, { id: 1, response: null }, 2)).toBe("later");
  });

  it("con respuesta, la respuesta manda sobre lo demás", () => {
    expect(suggestionState({ at_seq: 0 }, { id: 1, response: "accepted" }, 2)).toBe("accepted");
    expect(suggestionState({ at_seq: 2 }, { id: 1, response: "rejected" }, 2)).toBe("rejected");
  });

  it("sin `at_seq`, la validación es la del estado 0", () => {
    expect(suggestionState({}, { id: 1, response: null }, 0)).toBe("open");
    expect(suggestionState({}, { id: 1, response: null }, 1)).toBe("old");
  });
});

describe("suggestionItems", () => {
  it("da cada sugerencia de un posible error con su estado", () => {
    const item = finding(1, 1);
    expect(suggestionItems(item, 0)).toEqual([
      { finding: item, suggestion: item.suggestions?.[0], state: "open" },
    ]);
    expect(suggestionItems(finding(1, 1, { suggestions: undefined }), 0)).toEqual([]);
  });
});

describe("suggestionsAt", () => {
  it("da las sugerencias que cambian la nota elegida, de los posibles errores activos", () => {
    const one = finding(1, 1);
    const other = finding(2, 2);
    const dismissed = finding(3, 1, { status: "dismissed" });
    const found = suggestionsAt([one, other, dismissed], anchor(1), detail(0));
    expect(found.map(({ suggestion }) => suggestion.id)).toEqual([10]);
    expect(found[0]?.state).toBe("open");
  });

  it("lleva el ancla de una validación anterior al estado que se ve y la marca antigua", () => {
    const second = finding(1, 1, { suggestions: [suggestion(10, 1, { anchor: anchor(1, 1) })] });
    // Tras insertar antes de la primera nota, la segunda pasa a ser la tercera.
    const inserted = {
      id: "e1",
      session_id: "s",
      seq: 1,
      op: "InsertEvent",
      author: "ana",
      anchor: anchor(1, 0),
      before: null,
      after: { kind: "rest", duration_beats: "1" },
      reverts_edit_id: null,
      created_at: "2026-10-31T10:00:00",
    };
    const shown = detail(1, [inserted]);
    expect(suggestionsAt([second], anchor(1, 1), shown)).toEqual([]);
    const found = suggestionsAt([second], anchor(1, 2), shown);
    expect(found.map(({ state }) => state)).toEqual(["old"]);
  });

  it("no da las de un estado posterior al que se ve", () => {
    expect(suggestionsAt([finding(1, 1, { at_seq: 3 })], anchor(1), detail(0))).toEqual([]);
  });
});

describe("withSuggestion y withResponse", () => {
  it("sustituye la sugerencia en el posible error que la lleva, sin tocar los demás", () => {
    const one = finding(1, 1);
    const other = finding(2, 2);
    const rejected = { ...suggestion(10, 1), response: "rejected" as const };
    const next = withSuggestion([one, other], rejected);
    expect(next[0]?.suggestions?.[0]?.response).toBe("rejected");
    expect(next[0]?.status).toBe("active");
    expect(next[1]).toBe(other);
  });

  it("pone una respuesta por id; sin esa sugerencia, la lista no cambia", () => {
    const list = [finding(1, 1)];
    expect(withResponse(list, 10, "accepted")[0]?.suggestions?.[0]?.response).toBe("accepted");
    expect(withResponse(list, 99, "accepted")).toEqual(list);
  });
});
