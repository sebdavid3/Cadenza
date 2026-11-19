import { describe, expect, it } from "vitest";
import type { DrawnEventRead } from "../../types";
import {
  clefOf,
  keyAlter,
  keySignaturePositions,
  parsePitch,
  staffPosition,
  writtenAccidentals,
} from "./drawing";

const note = (pitch: string): DrawnEventRead => ({ kind: "note", pitch, beats: "1", chord: false });

describe("el compás dibujado de un ejemplo", () => {
  it("lee la altura y la clave", () => {
    expect(parsePitch("Bb4")).toEqual({ step: "B", alter: -1, d: 4 * 7 + 6 });
    expect(parsePitch("F##5")?.alter).toBe(2);
    expect(parsePitch("")).toBeNull();
    // Sol4 en la segunda línea de la clave de sol; Fa3 en la cuarta de la de fa.
    expect(staffPosition(parsePitch("G4") ?? { step: "", alter: 0, d: 0 }, clefOf("G2"))).toBe(2);
    expect(staffPosition(parsePitch("F3") ?? { step: "", alter: 0, d: 0 }, clefOf("F4"))).toBe(6);
    expect(clefOf("raro")).toEqual(clefOf("G2"));
  });

  it("escribe solo la alteración que cambia lo que rige en el compás", () => {
    // Con dos sostenidos (fa y do): do# va en la armadura; do natural se escribe; el siguiente do
    // natural ya no, ni otra vez el fa#.
    const events = [note("C#5"), note("C5"), note("C5"), note("F#4"), note("F4")];
    expect(writtenAccidentals(events, 2)).toEqual([false, true, false, false, true]);
    // La alteración rige por letra y octava: el do de otra octava vuelve a la armadura.
    expect(writtenAccidentals([note("C5"), note("C4")], 2)).toEqual([true, true]);
    expect(keyAlter("B", -1)).toBe(-1);
    expect(keyAlter("E", -1)).toBe(0);
  });

  it("desplaza la armadura según la clave", () => {
    const treble = keySignaturePositions(clefOf("G2"), -2);
    const bass = keySignaturePositions(clefOf("F4"), -2);
    const alto = keySignaturePositions(clefOf("C3"), -2);
    // Si bemol en la tercera línea de sol; en la de fa, dos posiciones más abajo; en la de do,
    // una.
    expect(treble).toEqual([4, 7]);
    expect(bass).toEqual(treble.map((pos) => pos - 2));
    expect(alto).toEqual(treble.map((pos) => pos - 1));
    for (const pos of keySignaturePositions(clefOf("F4"), 7)) {
      expect(pos).toBeGreaterThanOrEqual(-1);
      expect(pos).toBeLessThanOrEqual(9);
    }
  });
});
