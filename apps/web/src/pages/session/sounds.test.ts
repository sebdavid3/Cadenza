import { describe, expect, it } from "vitest";
import type { Instrument } from "../../types";
import { SOUNDS, soundOf } from "./sounds";

describe("sonido de cada instrumento (ADR-0046)", () => {
  it("cada instrumento de la lista cerrada tiene el suyo; «otro» suena como el piano", () => {
    const instruments: Instrument[] = [
      "piano",
      "voice",
      "violin",
      "cello",
      "flute",
      "clarinet",
      "guitar",
      "other",
    ];
    expect(instruments.map((instrument) => soundOf({ instrument, name: null }))).toEqual([
      "piano",
      "voice",
      "violin",
      "cello",
      "flute",
      "clarinet",
      "guitar",
      "piano",
    ]);
  });

  it("sin instrumento, o con uno que esta versión no conoce, suena como el piano", () => {
    expect(soundOf(undefined)).toBe("piano");
    expect(soundOf(null)).toBe("piano");
    expect(soundOf({ instrument: null, name: "Bajo" })).toBe("piano");
    // La lista solo crece (ADR-0041): un instrumento de una versión posterior no rompe la vista.
    expect(soundOf({ instrument: "oboe" as Instrument, name: null })).toBe("piano");
    expect(soundOf({ instrument: "toString" as Instrument, name: null })).toBe("piano");
  });

  it("el piano es el sintetizador de ADR-0026 tal cual", () => {
    expect(SOUNDS.piano).toEqual({
      oscillator: { type: "triangle" },
      envelope: { attack: 0.01, decay: 0.12, sustain: 0.4, release: 0.2 },
      volume: -10,
    });
  });

  it("la voz se distingue del piano: entra suave, se sostiene y tiene vibrato", () => {
    const { piano, voice } = SOUNDS;
    expect(voice.envelope.attack).toBeGreaterThan(piano.envelope.attack);
    expect(voice.envelope.sustain).toBeGreaterThan(piano.envelope.sustain);
    expect(voice.vibrato).toBeDefined();
    expect(piano.vibrato).toBeUndefined();
  });

  it("todos los sonidos tienen una envolvente y un volumen razonables", () => {
    for (const spec of Object.values(SOUNDS)) {
      const { attack, decay, sustain, release } = spec.envelope;
      expect(attack).toBeGreaterThan(0);
      expect(attack).toBeLessThanOrEqual(0.2);
      expect(decay).toBeGreaterThan(0);
      expect(sustain).toBeGreaterThanOrEqual(0);
      expect(sustain).toBeLessThanOrEqual(1);
      expect(release).toBeGreaterThan(0);
      expect(spec.volume).toBeLessThan(0);
      expect(spec.volume).toBeGreaterThanOrEqual(-24);
    }
  });
});
