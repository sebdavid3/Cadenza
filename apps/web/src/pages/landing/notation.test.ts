import { describe, expect, it } from "vitest";
import {
  BEATS_PER_MEASURE,
  CORRECTED,
  FLAGGED_MEASURE,
  GEOMETRY,
  measureX,
  OMR_READING,
} from "./incipit";
import { layoutIncipit, STAFF_END } from "./notation";

const beats = (measure: { beats: number }[]) => measure.reduce((sum, note) => sum + note.beats, 0);

describe("incipit de la demostración", () => {
  it("solo el compás señalado no cuadra en la lectura del motor, y la corrección lo arregla", () => {
    OMR_READING.forEach((measure, index) => {
      expect(beats(measure) === BEATS_PER_MEASURE).toBe(index !== FLAGGED_MEASURE);
    });
    for (const measure of CORRECTED) expect(beats(measure)).toBe(BEATS_PER_MEASURE);
  });

  it("la blanca con puntillo lleva plica y puntillo", () => {
    const dotted = layoutIncipit(CORRECTED).notes.find(({ note }) => note.beats === 3);

    expect(dotted?.stem).not.toBeNull();
    expect(dotted?.dot).not.toBeNull();
    expect(dotted?.open).toBe(true);
  });

  it("no pone barra entre la cifra de compás y el primer compás, y cierra con doble barra", () => {
    const { barlines } = layoutIncipit(CORRECTED);
    const xs = barlines.map((bar) => bar.x);

    expect(xs).not.toContain(measureX(0));
    expect(xs).toEqual(expect.arrayContaining([measureX(1), measureX(2), measureX(3)]));
    const last = barlines.at(-1);
    expect(last?.width).toBeGreaterThan(3);
    expect((last?.x ?? 0) + (last?.width ?? 0) / 2).toBeCloseTo(STAFF_END);
    expect(STAFF_END).toBeLessThan(GEOMETRY.width);
  });

  it("une las dos corcheas corregidas con una barra", () => {
    expect(layoutIncipit(CORRECTED).beams).toHaveLength(1);
    expect(layoutIncipit(OMR_READING).beams).toHaveLength(0);
  });
});
