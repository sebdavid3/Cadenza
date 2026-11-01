import type { Instrument, PartInstrumentRead } from "../../types";

/**
 * Sonido con que suena una parte en la vista (ADR-0046): uno por instrumento de la lista cerrada
 * de ADR-0041, salvo «otro», que suena como el piano.
 */
export type Sound = "piano" | "voice" | "violin" | "cello" | "flute" | "clarinet" | "guitar";

/**
 * Cómo se sintetiza un sonido con Tone.js, sin muestras: la onda, su envolvente, el volumen y,
 * si los tiene, un filtro de paso bajo y un vibrato. Son datos, para poder probarlos sin audio.
 */
export interface SoundSpec {
  oscillator:
    | { type: "sine" | "triangle" | "square" | "sawtooth" }
    | { type: "fattriangle"; count: number; spread: number };
  /** Ataque, caída y liberación en segundos; sostenimiento de 0 a 1. */
  envelope: { attack: number; decay: number; sustain: number; release: number };
  /** Volumen del sintetizador, en dB. */
  volume: number;
  /** Frecuencia de corte de un filtro de paso bajo, en Hz. */
  lowpass?: number;
  /** Vibrato: frecuencia en Hz y profundidad de 0 a 1. */
  vibrato?: { frequency: number; depth: number };
}

/**
 * Los sonidos. El piano es el sintetizador de ADR-0026 tal cual: una parte sin instrumento, o con
 * «otro», suena como antes de #242. Los demás se distinguen por su ataque, su sostenimiento, su
 * timbre (la onda y el filtro) y su vibrato; ninguno imita de cerca el instrumento real.
 */
export const SOUNDS: Readonly<Record<Sound, SoundSpec>> = {
  piano: {
    oscillator: { type: "triangle" },
    envelope: { attack: 0.01, decay: 0.12, sustain: 0.4, release: 0.2 },
    volume: -10,
  },
  // Coro «aah»: tres ondas algo desafinadas entre sí, entrada suave, sostenida y con vibrato.
  voice: {
    oscillator: { type: "fattriangle", count: 3, spread: 20 },
    envelope: { attack: 0.1, decay: 0.2, sustain: 0.85, release: 0.35 },
    volume: -12,
    lowpass: 1800,
    vibrato: { frequency: 5, depth: 0.15 },
  },
  // Cuerda frotada: diente de sierra filtrado, sostenido y con vibrato.
  violin: {
    oscillator: { type: "sawtooth" },
    envelope: { attack: 0.05, decay: 0.1, sustain: 0.9, release: 0.25 },
    volume: -16,
    lowpass: 3500,
    vibrato: { frequency: 5.5, depth: 0.12 },
  },
  cello: {
    oscillator: { type: "sawtooth" },
    envelope: { attack: 0.07, decay: 0.1, sustain: 0.9, release: 0.3 },
    volume: -14,
    lowpass: 1500,
    vibrato: { frequency: 5, depth: 0.1 },
  },
  // Senoidal casi pura con un vibrato lento.
  flute: {
    oscillator: { type: "sine" },
    envelope: { attack: 0.04, decay: 0.1, sustain: 0.85, release: 0.2 },
    volume: -8,
    vibrato: { frequency: 4.5, depth: 0.08 },
  },
  // Onda cuadrada (solo armónicos impares, como el clarinete) filtrada, sin vibrato.
  clarinet: {
    oscillator: { type: "square" },
    envelope: { attack: 0.03, decay: 0.1, sustain: 0.9, release: 0.15 },
    volume: -18,
    lowpass: 2200,
  },
  // Cuerda pulsada: ataque inmediato y la nota se apaga sola aunque sea larga.
  guitar: {
    oscillator: { type: "triangle" },
    envelope: { attack: 0.002, decay: 1.2, sustain: 0, release: 0.4 },
    volume: -8,
    lowpass: 3000,
  },
};

const BY_INSTRUMENT: Readonly<Record<Instrument, Sound>> = {
  piano: "piano",
  voice: "voice",
  violin: "violin",
  cello: "cello",
  flute: "flute",
  clarinet: "clarinet",
  guitar: "guitar",
  other: "piano",
};

/**
 * Sonido de una parte: el de su instrumento. Sin instrumento, con «otro» o con uno que esta
 * versión no conoce (la lista solo crece, ADR-0041), el piano.
 */
export function soundOf(entry: PartInstrumentRead | null | undefined): Sound {
  const instrument = entry?.instrument;
  if (!instrument || !Object.hasOwn(BY_INSTRUMENT, instrument)) return "piano";
  return BY_INSTRUMENT[instrument];
}
