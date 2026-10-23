import { describe, expect, it } from "vitest";
import type {
  EventTimingRead,
  ScoreEventPayload,
  ScoreIRPayload,
  TimingMapRead,
} from "../../types";
import {
  beatsToSeconds,
  buildPlayback,
  measureSlots,
  midiToFrequency,
  parseBeats,
  pitchToMidi,
} from "./playback";

function event(changes: Partial<ScoreEventPayload>): ScoreEventPayload {
  return {
    kind: "note",
    voice: 0,
    pitch: "C4",
    duration_beats: "1",
    tie: null,
    is_chord: false,
    bbox: null,
    confidence: null,
    ir_handle: null,
    ...changes,
  };
}

function score(measures: ScoreEventPayload[][]): ScoreIRPayload {
  return {
    parts: [
      {
        id: "part-0",
        staves: [
          {
            id: "part-0-staff-0",
            measures: measures.map((events, index) => ({ number: index + 1, events })),
          },
        ],
      },
    ],
  };
}

function timed(
  measure: number,
  eventIndex: number,
  offset: string,
  duration: string,
  kind = "note",
  voice = 0,
): EventTimingRead {
  return {
    anchor: {
      part: 0,
      staff: 0,
      measure,
      voice,
      event_index: eventIndex,
      staff_id: "part-0-staff-0",
      bbox: null,
      confidence: null,
    },
    kind,
    measure_number: measure,
    voice,
    offset_beats: offset,
    duration_beats: duration,
    measure_offset_beats: "0",
  };
}

function timing(
  events: EventTimingRead[],
  offsets: Record<string, string>,
  total: string,
): TimingMapRead {
  return { session_id: "s", total_beats: total, measure_offsets: offsets, events };
}

describe("reproducción a partir del mapa de tiempos", () => {
  it("lee las fracciones exactas del mapa", () => {
    expect(parseBeats("3/8")).toBe(0.375);
    expect(parseBeats("2")).toBe(2);
    expect(parseBeats("71/4")).toBe(17.75);
    expect(parseBeats("1/0")).toBeNaN();
    expect(parseBeats("uno")).toBeNaN();
  });

  it("traduce las alturas del ScoreIR a MIDI y a frecuencia", () => {
    expect(pitchToMidi("C4")).toBe(60);
    expect(pitchToMidi("A4")).toBe(69);
    expect(pitchToMidi("F#5")).toBe(78);
    expect(pitchToMidi("Bb3")).toBe(58);
    expect(pitchToMidi("B-3")).toBe(58);
    expect(pitchToMidi("Cbb4")).toBe(58);
    expect(pitchToMidi("Gx4")).toBe(69);
    expect(pitchToMidi("H4")).toBeNull();
    expect(pitchToMidi("C10")).toBeNull();
    expect(midiToFrequency(69)).toBe(440);
    expect(midiToFrequency(60)).toBeCloseTo(261.626, 3);
    expect(beatsToSeconds(6, 120)).toBe(3);
  });

  it("programa las notas en su pulso, con su altura y su compás, y calla los silencios", () => {
    const ir = score([
      [event({ kind: "rest", pitch: null, duration_beats: "1" }), event({ pitch: "E4" })],
      [
        event({ pitch: "G4", duration_beats: "1/2" }),
        event({ pitch: "A4", duration_beats: "3/2" }),
      ],
    ]);
    const map = timing(
      [
        timed(1, 0, "0", "1", "rest"),
        timed(1, 1, "1", "1"),
        timed(2, 0, "2", "1/2"),
        timed(2, 1, "5/2", "3/2"),
      ],
      { "1": "0", "2": "2" },
      "4",
    );

    const playback = buildPlayback(ir, map);

    expect(playback.notes).toEqual([
      { start: 1, duration: 1, midi: 64, measure: 1 },
      { start: 2, duration: 0.5, midi: 67, measure: 2 },
      { start: 2.5, duration: 1.5, midi: 69, measure: 2 },
    ]);
    expect(playback.measures).toEqual([
      { number: 1, start: 0, end: 2 },
      { number: 2, start: 2, end: 4 },
    ]);
    expect(playback.totalBeats).toBe(4);
  });

  it("une las notas ligadas, también de un compás al siguiente", () => {
    const ir = score([
      [event({ pitch: "D4", duration_beats: "2", tie: "start" })],
      [event({ pitch: "D4", duration_beats: "1", tie: "continue" })],
      [event({ pitch: "D4", duration_beats: "1", tie: "stop" }), event({ pitch: "D4" })],
    ]);
    const map = timing(
      [timed(1, 0, "0", "2"), timed(2, 0, "2", "1"), timed(3, 0, "3", "1"), timed(3, 1, "4", "1")],
      { "1": "0", "2": "2", "3": "3" },
      "5",
    );

    expect(buildPlayback(ir, map).notes).toEqual([
      { start: 0, duration: 4, midi: 62, measure: 1 },
      { start: 4, duration: 1, midi: 62, measure: 3 },
    ]);
  });

  it("no une una ligadura que no llega a la nota siguiente ni mezcla voces", () => {
    const ir = score([
      [
        event({ pitch: "E4", tie: "start" }),
        event({ kind: "rest", pitch: null }),
        event({ pitch: "E4", tie: "stop" }),
        event({ pitch: "E4", voice: 1, tie: "stop" }),
      ],
    ]);
    const map = timing(
      [
        timed(1, 0, "0", "1"),
        timed(1, 1, "1", "1", "rest"),
        timed(1, 2, "2", "1"),
        timed(1, 0, "2", "1", "note", 1),
      ],
      { "1": "0" },
      "3",
    );

    expect(buildPlayback(ir, map).notes.map((note) => note.start)).toEqual([0, 2, 2]);
  });

  it("hace sonar a la vez las notas de un acorde", () => {
    const ir = score([
      [event({ pitch: "C4" }), event({ pitch: "E4", is_chord: true }), event({ pitch: "G4" })],
    ]);
    const map = timing(
      [timed(1, 0, "0", "1"), timed(1, 1, "0", "1"), timed(1, 2, "1", "1")],
      { "1": "0" },
      "2",
    );

    expect(buildPlayback(ir, map).notes.map((note) => [note.start, note.midi])).toEqual([
      [0, 60],
      [0, 64],
      [1, 67],
    ]);
  });

  it("omite lo que no puede sonar: sin altura, altura ilegible o duración nula", () => {
    const ir = score([
      [
        event({ pitch: null }),
        event({ pitch: "X9" }),
        event({ kind: "clef", pitch: null, duration_beats: null }),
        event({ pitch: "C4" }),
      ],
    ]);
    const map = timing(
      [
        timed(1, 0, "0", "1"),
        timed(1, 1, "1", "1"),
        timed(1, 2, "2", "0", "clef"),
        timed(1, 3, "2", "1"),
        timed(1, 9, "3", "1"),
      ],
      { "1": "0" },
      "4",
    );

    expect(buildPlayback(ir, map).notes).toEqual([{ start: 2, duration: 1, midi: 60, measure: 1 }]);
  });

  it("sitúa un compás en cada pentagrama donde aparece, en el orden global de OSMD", () => {
    const ir: ScoreIRPayload = {
      parts: [
        {
          id: "p0",
          staves: [
            { id: "s0", measures: [0, 1, 2].map((number) => ({ number, events: [] })) },
            { id: "s1", measures: [1, 2].map((number) => ({ number, events: [] })) },
          ],
        },
        { id: "p1", staves: [{ id: "s2", measures: [{ number: 2, events: [] }] }] },
      ],
    };

    expect(measureSlots(ir, 2)).toEqual([
      { staff: 0, measure: 2 },
      { staff: 1, measure: 1 },
      { staff: 2, measure: 0 },
    ]);
    expect(measureSlots(ir, 7)).toEqual([]);
  });
});
