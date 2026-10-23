import type { ScoreEventPayload, ScoreIRPayload, TimingMapRead } from "../../types";
import type { MeasureSlot } from "./findings";

/** Nota que suena, en negras desde el principio: la unidad del mapa de tiempos. */
export interface PlayedNote {
  start: number;
  duration: number;
  /** Altura como número MIDI (60 es el do central). */
  midi: number;
  measure: number;
}

/** Dónde empieza y dónde acaba un compás, en negras. */
export interface MeasureSpan {
  number: number;
  start: number;
  end: number;
}

/** Lo que suena: notas y compases en el tiempo (ADR-0026). */
export interface Playback {
  notes: PlayedNote[];
  measures: MeasureSpan[];
  totalBeats: number;
}

/** Negras por minuto si la persona no elige otro tempo: las del MIDI que exporta la API. */
export const DEFAULT_TEMPO = 120;
export const MIN_TEMPO = 40;
export const MAX_TEMPO = 200;
export const TEMPO_STEP = 10;

/** Fracción exacta del mapa de tiempos («3/8», «2») en negras; NaN si no se entiende. */
export function parseBeats(value: string): number {
  const match = /^\s*(\d+)(?:\s*\/\s*(\d+))?\s*$/.exec(value);
  if (!match) return Number.NaN;
  const numerator = Number(match[1]);
  const denominator = match[2] === undefined ? 1 : Number(match[2]);
  return denominator === 0 ? Number.NaN : numerator / denominator;
}

const STEPS: Record<string, number> = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
const ACCIDENTALS: Record<string, number> = {
  "": 0,
  "#": 1,
  "##": 2,
  x: 2,
  b: -1,
  bb: -2,
  "-": -1,
  "--": -2,
};

/**
 * Altura del `ScoreIR` («C4», «F#5», «Bb3», también «B-3» de music21) como número MIDI, o null
 * si no se entiende o cae fuera del rango MIDI.
 */
export function pitchToMidi(pitch: string): number | null {
  const match = /^([A-Ga-g])(##|bb|--|#|b|-|x)?(-?\d+)$/.exec(pitch.trim());
  if (!match) return null;
  const step = STEPS[(match[1] ?? "").toUpperCase()];
  const accidental = ACCIDENTALS[match[2] ?? ""];
  if (step === undefined || accidental === undefined) return null;
  const midi = 12 * (Number(match[3]) + 1) + step + accidental;
  return midi >= 0 && midi <= 127 ? midi : null;
}

export function midiToFrequency(midi: number): number {
  return 440 * 2 ** ((midi - 69) / 12);
}

/** Negras a segundos con un tempo en negras por minuto. */
export function beatsToSeconds(beats: number, tempo: number): number {
  return (beats * 60) / tempo;
}

const EPSILON = 1e-9;

/**
 * Notas y compases a partir del mapa de tiempos (`GET /sessions/{id}/timing`) y de las alturas
 * del `ScoreIR` del mismo estado. El `event_index` del ancla cuenta los eventos de su voz dentro
 * del compás. Las notas ligadas suenan como una sola; los silencios no suenan, y una nota sin
 * altura que se entienda tampoco.
 */
export function buildPlayback(score: ScoreIRPayload, timing: TimingMapRead): Playback {
  const voices = new Map<string, ScoreEventPayload[]>();
  score.parts.forEach((part, partIndex) => {
    part.staves.forEach((staff, staffIndex) => {
      for (const measure of staff.measures) {
        for (const event of measure.events) {
          const key = `${String(partIndex)}:${String(staffIndex)}:${String(measure.number)}:${String(event.voice)}`;
          const list = voices.get(key);
          if (list) list.push(event);
          else voices.set(key, [event]);
        }
      }
    });
  });

  const notes: PlayedNote[] = [];
  // Nota ligada que sigue abierta, por parte, pentagrama, voz y altura.
  const open = new Map<string, PlayedNote>();
  for (const timed of timing.events ?? []) {
    if (timed.kind !== "note") continue;
    const start = parseBeats(timed.offset_beats);
    const duration = parseBeats(timed.duration_beats);
    if (!(duration > 0) || !Number.isFinite(start)) continue;
    const { anchor } = timed;
    const event = voices.get(
      `${String(anchor.part)}:${String(anchor.staff)}:${String(anchor.measure)}:${String(anchor.voice)}`,
    )?.[anchor.event_index];
    const midi = event?.pitch ? pitchToMidi(event.pitch) : null;
    if (midi === null) continue;

    const tieKey = `${String(anchor.part)}:${String(anchor.staff)}:${String(anchor.voice)}:${String(midi)}`;
    const tie = event?.tie ?? null;
    const previous = open.get(tieKey);
    let note: PlayedNote;
    if (
      (tie === "stop" || tie === "continue") &&
      previous &&
      Math.abs(previous.start + previous.duration - start) < EPSILON
    ) {
      previous.duration += duration;
      note = previous;
    } else {
      note = { start, duration, midi, measure: timed.measure_number };
      notes.push(note);
    }
    if (tie === "start" || tie === "continue") open.set(tieKey, note);
    else open.delete(tieKey);
  }

  const totalBeats = parseBeats(timing.total_beats);
  const starts = Object.entries(timing.measure_offsets ?? {})
    .map(([number, offset]) => ({ number: Number(number), start: parseBeats(offset) }))
    .filter((measure) => Number.isInteger(measure.number) && Number.isFinite(measure.start))
    .sort((a, b) => a.number - b.number);
  const measures = starts.map((measure, index) => ({
    ...measure,
    end: starts[index + 1]?.start ?? totalBeats,
  }));

  return { notes, measures, totalBeats: Number.isFinite(totalBeats) ? totalBeats : 0 };
}

/** Dónde se dibuja un compás en cada pentagrama de la partitura (orden global de OSMD). */
export function measureSlots(score: ScoreIRPayload, measureNumber: number): MeasureSlot[] {
  const slots: MeasureSlot[] = [];
  let staffIndex = 0;
  for (const part of score.parts) {
    for (const staff of part.staves) {
      const measure = staff.measures.findIndex((candidate) => candidate.number === measureNumber);
      if (measure >= 0) slots.push({ staff: staffIndex, measure });
      staffIndex += 1;
    }
  }
  return slots;
}
