import { describe, expect, it } from "vitest";
import type { FindingRead, ScoreIRPayload } from "../../types";
import {
  measureMarks,
  measureSlot,
  measuresPerStaff,
  ruleLabel,
  splitFindings,
  staleValidationSeq,
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
    const marks = measureMarks(SCORE, [
      finding(1, 3),
      finding(2, 1),
      finding(3, 3, { rule_id: "pitch.range" }),
    ]);
    expect(marks.map((mark) => [mark.measureNumber, mark.findings.map((f) => f.id)])).toEqual([
      [1, [2]],
      [3, [1, 3]],
    ]);
  });

  it("omite los hallazgos cuyo compás no está en la partitura", () => {
    expect(measureMarks(SCORE, [finding(1, 7)])).toEqual([]);
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

describe("staleValidationSeq", () => {
  it("avisa si la última validación es anterior al estado actual", () => {
    expect(staleValidationSeq([finding(1, 1, { at_seq: 2 })], 5)).toBe(2);
  });

  it("no avisa si están al día o si no hay hallazgos", () => {
    expect(staleValidationSeq([finding(1, 1, { at_seq: 5 })], 5)).toBeNull();
    expect(staleValidationSeq([], 5)).toBeNull();
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
