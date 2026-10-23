import { describe, expect, it } from "vitest";
import type { ScoreEventPayload } from "../../types";
import { describeEvent, durationName, pitchName } from "./noteNames";

describe("nombres de las alturas", () => {
  it.each([
    ["C4", "Do4", "Do 4"],
    ["F#5", "Fa#5", "Fa sostenido 5"],
    ["Bb3", "Sib3", "Si bemol 3"],
    ["B-3", "Sib3", "Si bemol 3"],
    ["G##4", "Sol##4", "Sol doble sostenido 4"],
    ["Ebb2", "Mibb2", "Mi doble bemol 2"],
    ["a4", "La4", "La 4"],
  ])("%s se escribe %s y se dice «%s»", (pitch, written, spoken) => {
    expect(pitchName(pitch)).toEqual({ written, spoken });
  });

  it("no inventa un nombre para una altura que no entiende", () => {
    expect(pitchName("H4")).toBeNull();
  });
});

describe("nombres de las duraciones", () => {
  it.each([
    ["4", "redonda"],
    ["2", "blanca"],
    ["1", "negra"],
    ["1/2", "corchea"],
    ["1/4", "semicorchea"],
    ["1/8", "fusa"],
    ["1/16", "semifusa"],
    ["3", "blanca con puntillo"],
    ["3/2", "negra con puntillo"],
    ["3/4", "corchea con puntillo"],
    ["7/4", "negra con doble puntillo"],
    ["1/3", "corchea de tresillo"],
    ["2/3", "negra de tresillo"],
    ["11/2", "11/2 negras"],
    ["5/8", "5/8 de negra"],
    ["0", "sin duración"],
    [null, "sin duración"],
  ])("%s negras es %s", (beats, name) => {
    expect(durationName(beats)).toBe(name);
  });
});

function event(changes: Partial<ScoreEventPayload>): ScoreEventPayload {
  return {
    kind: "note",
    voice: 0,
    pitch: "F#4",
    duration_beats: "1/2",
    tie: null,
    is_chord: false,
    bbox: null,
    confidence: null,
    ir_handle: null,
    ...changes,
  };
}

describe("descripción del evento elegido", () => {
  it("dice el compás, la voz, la altura y la duración", () => {
    expect(describeEvent(event({}), { measure: 3, staff: 0, multiStaff: false })).toEqual({
      place: "Compás 3 · Voz 1",
      what: "Fa#4 · corchea",
      spoken: "Compás 3, voz 1: Fa sostenido 4, corchea.",
    });
  });

  it("dice si es un silencio, si está en un acorde o ligada y en qué pentagrama", () => {
    expect(
      describeEvent(event({ kind: "rest", pitch: null, duration_beats: "1", voice: 1 }), {
        measure: 2,
        staff: 1,
        multiStaff: true,
      }),
    ).toEqual({
      place: "Pentagrama 2 · Compás 2 · Voz 2",
      what: "Silencio de negra",
      spoken: "Pentagrama 2, compás 2, voz 2: silencio de negra.",
    });
    expect(
      describeEvent(event({ pitch: "C5", duration_beats: "2", is_chord: true, tie: "start" }), {
        measure: 1,
        staff: 0,
        multiStaff: false,
      }).spoken,
    ).toBe("Compás 1, voz 1: Do 5, blanca, en acorde, ligada.");
  });

  it("con una altura que no entiende, la muestra tal cual", () => {
    expect(
      describeEvent(event({ pitch: "H4" }), { measure: 1, staff: 0, multiStaff: false }).what,
    ).toBe("H4 · corchea");
  });
});
