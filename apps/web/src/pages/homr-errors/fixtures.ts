// Cifras de prueba con la forma de `GET /stats/homr-errors` (#423): inventadas, para las pruebas.

import type {
  ErrorRateRead,
  FigureRead,
  HomrErrorStatsGroupRead,
  HomrErrorStatsRead,
  HomrErrorStatsValuesRead,
} from "../../types";

const figure = (name: string, base = name, dots = 0): FigureRead => ({
  name,
  symbol: [{ figure: base, dots, tuplet: 0, grace: false }],
});

export const FIGURES: Record<string, FigureRead> = {
  "1/4": figure("semicorchea"),
  "1/2": figure("corchea"),
  "3/4": figure("corchea con puntillo", "corchea", 1),
  "1": figure("negra"),
  "2": figure("blanca"),
};

export function rate(key: string, label: string, n: number, wrong: number): ErrorRateRead {
  return { key, label, n, wrong, rate: wrong / n };
}

export function values(
  overrides: Partial<HomrErrorStatsValuesRead> = {},
): HomrErrorStatsValuesRead {
  return {
    scores: 12,
    clean_scores: 3,
    read: 1000,
    outcome: { bien: 820, corregida: 120, borrada: 40, sin_alinear: 20 },
    missing: 35,
    reordered: 0,
    ops: { SetDuration: 90, SetPitch: 60, DeleteEvent: 40, InsertEvent: 35, SetKey: 2 },
    steps: { "-1": 20, "1": 30, "7": 4 },
    durations: [
      { read: "1/2", fix: "1", read_name: "corchea", fix_name: "negra", n: 40 },
      { read: "1", fix: "1/2", read_name: "negra", fix_name: "corchea", n: 10 },
      { read: "3/4", fix: "1", read_name: "corchea con puntillo", fix_name: "negra", n: 3 },
    ],
    by_vs_key: [
      rate("vs:against_key", "contra la armadura", 250, 90),
      rate("vs:in_key", "según la armadura", 700, 105),
    ],
    by_clef: [rate("clef:G2", "clave de sol", 900, 160), rate("clef:F4", "clave de fa", 100, 20)],
    by_duration: [
      rate("readdur:1/4", "semicorchea", 300, 120),
      rate("readdur:1", "negra", 400, 40),
    ],
    figures: FIGURES,
    ...overrides,
  };
}

export function group(
  id: string,
  overrides: Partial<HomrErrorStatsGroupRead> = {},
): HomrErrorStatsGroupRead {
  const source = id === "cadenza" || id === "pruebas" ? "cadenza" : "corpus";
  return {
    id,
    source,
    computed_at: "2026-11-19T12:00:00Z",
    min_sessions: source === "cadenza" ? 5 : 0,
    published: true,
    sessions: 12,
    stats: values(),
    ...overrides,
  };
}

export function payload(
  groups: HomrErrorStatsGroupRead[],
  computedAt: string | null = "2026-11-19T12:00:00Z",
): HomrErrorStatsRead {
  return { computed_at: computedAt, groups };
}

/** Cadenza sin publicar: ni sus sesiones ni sus cifras. */
export const UNPUBLISHED = { published: false, sessions: null, stats: null } as const;

/** Los ejemplos de un corpus: seis de «Figura equivocada» y uno de «Altura equivocada». */
export function withExamples(stats: HomrErrorStatsValuesRead): HomrErrorStatsValuesRead {
  const durationExamples = Array.from({ length: 6 }, (_, i) => ({
    score: `00010013${String(i)}-1_1_1`,
    measure: String(i + 1),
    staff: "0-0",
    kind: "change" as const,
    read: "C5 corchea",
    fix: "C5 negra",
    read_beats: "1/2",
    fix_beats: "1",
    bar: "b0",
    at_read: 1,
    at_fix: 1,
  }));
  const pitchExample = {
    score: "000100200-1_1_1",
    measure: "3",
    staff: "0-0",
    kind: "change" as const,
    read: "Bb4 negra",
    fix: "B4 negra",
    read_beats: "1",
    fix_beats: "1",
    bar: "b0",
    at_read: 0,
    at_fix: 0,
  };
  return {
    ...stats,
    examples: [...durationExamples, pitchExample],
    example_keys: { "op:SetDuration": [0, 1, 2, 3, 4, 5], "op:SetPitch": [6] },
    bars: {
      b0: {
        clef: "G2",
        key: -1,
        read: [
          { kind: "note", pitch: "Bb4", beats: "1", chord: false },
          { kind: "note", pitch: "C5", beats: "1/2", chord: false },
          { kind: "rest", pitch: "", beats: "1", chord: false },
        ],
        fixed: [
          { kind: "note", pitch: "B4", beats: "1", chord: false },
          { kind: "note", pitch: "C5", beats: "1", chord: false },
          { kind: "rest", pitch: "", beats: "1", chord: false },
        ],
      },
    },
  };
}
