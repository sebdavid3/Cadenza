import { describe, expect, it } from "vitest";
import type { FindingRead, ScoreIRPayload } from "../../types";
import {
  measureMarks,
  measureSlot,
  measuresPerStaff,
  ruleLabel,
  splitFindings,
  validationState,
  withFinding,
} from "./findings";

function staff(id: string, numbers: number[]) {
  return { id, measures: numbers.map((number) => ({ number, events: [] })) };
}

/** Dos partes: la primera con dos pentagramas (piano) y la segunda con uno. */
const SCORE: ScoreIRPayload = {
  parts: [
    {
      id: "part-0",
      staves: [staff("part-0-staff-0", [1, 2, 3]), staff("part-0-staff-1", [1, 2, 3])],
    },
    { id: "part-1", staves: [staff("part-1-staff-0", [1, 2, 3])] },
  ],
};

function finding(id: number, measure: number, changes: Partial<FindingRead> = {}): FindingRead {
  return {
    id,
    rule_id: "measure.balance",
    severity: "error",
    message: `El compás ${String(measure)} no suma lo que pide su métrica.`,
    suggested_fix: null,
    anchor: {
      part: 0,
      staff: 0,
      measure,
      voice: 0,
      event_index: 0,
      staff_id: "part-0-staff-0",
      bbox: null,
      confidence: null,
    },
    at_seq: 0,
    status: "active",
    dismissed_at: null,
    dismissed_by: null,
    dismissal_reason: null,
    ...changes,
  };
}

describe("measureSlot", () => {
  it("cuenta los pentagramas de todas las partes seguidos y el compás por posición", () => {
    const anchor = { ...finding(1, 2).anchor, part: 1, staff: 0, staff_id: "part-1-staff-0" };
    expect(measureSlot(SCORE, anchor)).toEqual({ staff: 2, measure: 1 });
  });

  it("busca el compás por su número, no por el número menos uno", () => {
    const score: ScoreIRPayload = { parts: [{ id: "p", staves: [staff("s", [0, 1, 2])] }] };
    expect(measureSlot(score, finding(1, 1).anchor)).toEqual({ staff: 0, measure: 1 });
  });

  it("devuelve null si el ancla apunta a un compás o pentagrama que no existe", () => {
    expect(measureSlot(SCORE, finding(1, 9).anchor)).toBeNull();
    expect(measureSlot(SCORE, { ...finding(1, 1).anchor, staff: 5 })).toBeNull();
  });
});

describe("measureMarks", () => {
  it("agrupa los hallazgos del mismo compás y ordena por posición en la partitura", () => {
    const { marks } = measureMarks(SCORE, [
      finding(1, 3),
      finding(2, 1),
      finding(3, 3, { rule_id: "pitch.range" }),
    ]);
    expect(marks.map((mark) => [mark.measureNumber, mark.findings.map((f) => f.id)])).toEqual([
      [1, [2]],
      [3, [1, 3]],
    ]);
  });

  it("marca el compás del ancla sea cual sea su voz o su evento (ADR-0032)", () => {
    // `voice.collision` ancla al evento, también en una segunda voz o en un hueco invisible.
    const second = finding(1, 2, {
      rule_id: "voice.collision",
      anchor: { ...finding(1, 2).anchor, voice: 1, event_index: 3 },
    });
    const { marks, unplaced } = measureMarks(SCORE, [second, finding(2, 2)]);
    expect(marks).toHaveLength(1);
    expect(marks[0]?.slot).toEqual({ staff: 0, measure: 1 });
    expect(marks[0]?.findings.map((f) => f.id)).toEqual([1, 2]);
    expect(unplaced).toEqual([]);
  });

  it("no marca los hallazgos cuyo compás no está en la partitura, pero los devuelve", () => {
    const { marks, unplaced } = measureMarks(SCORE, [finding(1, 7), finding(2, 2)]);
    expect(marks.map((mark) => mark.measureNumber)).toEqual([2]);
    expect(unplaced.map((f) => f.id)).toEqual([1]);
  });
});

describe("splitFindings", () => {
  it("separa los descartados de los activos", () => {
    const { active, dismissed } = splitFindings([
      finding(1, 1),
      finding(2, 2, { status: "dismissed", dismissal_reason: "Es así en el original" }),
    ]);
    expect(active.map((f) => f.id)).toEqual([1]);
    expect(dismissed.map((f) => f.id)).toEqual([2]);
  });
});

describe("validationState", () => {
  it("avisa si la última validación es anterior al estado actual", () => {
    expect(validationState([finding(1, 1, { at_seq: 2 })], 5)).toEqual({ kind: "stale", seq: 2 });
  });

  it("está al día si los hallazgos son del estado actual, también los descartados", () => {
    expect(validationState([finding(1, 1, { at_seq: 5 })], 5)).toEqual({ kind: "current" });
    expect(validationState([finding(1, 1, { at_seq: 5, status: "dismissed" })], 5)).toEqual({
      kind: "current",
    });
  });

  it("sin hallazgos ni ediciones, la validación es la de la transcripción", () => {
    expect(validationState([], 0)).toEqual({ kind: "current" });
  });

  it("sin hallazgos pero con ediciones no se sabe de qué estado es la última validación", () => {
    expect(validationState([], 5)).toEqual({ kind: "unknown" });
  });

  it("sin hallazgos, una validación conocida dice de qué estado es", () => {
    expect(validationState([], 5, 5)).toEqual({ kind: "current" });
    expect(validationState([], 5, 3)).toEqual({ kind: "stale", seq: 3 });
  });

  it("la validación conocida y los hallazgos cuentan juntos: vale la más reciente", () => {
    expect(validationState([finding(1, 1, { at_seq: 2 })], 5, 4)).toEqual({
      kind: "stale",
      seq: 4,
    });
    expect(validationState([finding(1, 1, { at_seq: 5 })], 5, 2)).toEqual({ kind: "current" });
  });
});

describe("withFinding", () => {
  it("sustituye el hallazgo con el mismo id y conserva el orden", () => {
    const dismissed = finding(2, 2, { status: "dismissed", dismissal_reason: "Así es" });
    const list = withFinding([finding(1, 1), finding(2, 2), finding(3, 3)], dismissed);
    expect(list.map((f) => [f.id, f.status])).toEqual([
      [1, "active"],
      [2, "dismissed"],
      [3, "active"],
    ]);
    expect(list[1]?.dismissal_reason).toBe("Así es");
  });

  it("si el hallazgo no está en la lista, la deja igual", () => {
    const list = [finding(1, 1)];
    expect(withFinding(list, finding(9, 2))).toEqual(list);
  });
});

describe("measuresPerStaff y ruleLabel", () => {
  it("cuenta los compases de cada pentagrama en orden global", () => {
    expect(measuresPerStaff(SCORE)).toEqual([3, 3, 3]);
  });

  it("nombra las familias de reglas y deja el identificador de una desconocida", () => {
    expect(ruleLabel("measure.balance")).toBe("Duración del compás");
    expect(ruleLabel("nueva.regla")).toBe("nueva.regla");
  });
});
