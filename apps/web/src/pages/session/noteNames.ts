import type { ScoreEventPayload } from "../../types";

const STEPS: Record<string, string> = {
  C: "Do",
  D: "Re",
  E: "Mi",
  F: "Fa",
  G: "Sol",
  A: "La",
  B: "Si",
};

/** Alteraciones del `ScoreIR` (también las de music21): cómo se escriben y cómo se dicen. */
const ACCIDENTALS: Record<string, { written: string; spoken: string }> = {
  "": { written: "", spoken: "" },
  "#": { written: "#", spoken: " sostenido" },
  "##": { written: "##", spoken: " doble sostenido" },
  x: { written: "##", spoken: " doble sostenido" },
  b: { written: "b", spoken: " bemol" },
  "-": { written: "b", spoken: " bemol" },
  bb: { written: "bb", spoken: " doble bemol" },
  "--": { written: "bb", spoken: " doble bemol" },
};

/**
 * Altura del `ScoreIR` («F#5») con el nombre de solfeo: escrita («Fa#5») y para leerla en voz
 * alta («Fa sostenido 5»). Null si no se entiende.
 */
export function pitchName(pitch: string): { written: string; spoken: string } | null {
  const match = /^([A-Ga-g])(##|bb|--|#|b|-|x)?(-?\d+)$/.exec(pitch.trim());
  if (!match) return null;
  const step = STEPS[(match[1] ?? "").toUpperCase()];
  const accidental = ACCIDENTALS[match[2] ?? ""];
  if (!step || !accidental) return null;
  const octave = match[3] ?? "";
  return {
    written: `${step}${accidental.written}${octave}`,
    spoken: `${step}${accidental.spoken} ${octave}`,
  };
}

/** Figuras por su duración en negras, como fracción reducida. */
const FIGURES: [number, number, string][] = [
  [8, 1, "cuadrada"],
  [4, 1, "redonda"],
  [2, 1, "blanca"],
  [1, 1, "negra"],
  [1, 2, "corchea"],
  [1, 4, "semicorchea"],
  [1, 8, "fusa"],
  [1, 16, "semifusa"],
];

function gcd(a: number, b: number): number {
  return b === 0 ? a : gcd(b, a % b);
}

/** Nombre de la figura de una duración en negras («3/2» es «negra con puntillo»). */
export function durationName(beats: string | null): string {
  const match = beats === null ? null : /^\s*(\d+)(?:\s*\/\s*(\d+))?\s*$/.exec(beats);
  const numerator = Number(match?.[1] ?? 0);
  const denominator = Number(match?.[2] ?? 1);
  if (!match || numerator === 0 || denominator === 0) return "sin duración";
  const divisor = gcd(numerator, denominator);
  const [n, d] = [numerator / divisor, denominator / divisor];
  // Una figura, con puntillo (×3/2), con doble puntillo (×7/4) o de tresillo (×2/3).
  const variants: [number, number, string][] = [
    [1, 1, ""],
    [3, 2, " con puntillo"],
    [7, 4, " con doble puntillo"],
    [2, 3, " de tresillo"],
  ];
  for (const [vn, vd, suffix] of variants) {
    for (const [fn, fd, name] of FIGURES) {
      if (n * fd * vd === fn * vn * d) return `${name}${suffix}`;
    }
  }
  const value = `${String(n)}/${String(d)}`;
  return n < d ? `${value} de negra` : `${value} negras`;
}

/** Dónde está el evento elegido y qué es: para la barra y para el anuncio. */
export function describeEvent(
  event: ScoreEventPayload,
  where: { measure: number; staff: number; multiStaff: boolean },
): { place: string; what: string; spoken: string } {
  const voice = String(event.voice + 1);
  const staff = where.multiStaff ? `Pentagrama ${String(where.staff + 1)}` : null;
  const place = [staff, `Compás ${String(where.measure)}`, `Voz ${voice}`]
    .filter((part) => part !== null)
    .join(" · ");
  const spokenPlace = `${staff ? `${staff}, compás` : "Compás"} ${String(where.measure)}, voz ${voice}`;

  const duration = durationName(event.duration_beats);
  if (event.kind === "rest") {
    return {
      place,
      what: `Silencio de ${duration}`,
      spoken: `${spokenPlace}: silencio de ${duration}.`,
    };
  }
  const pitch = event.pitch === null ? null : pitchName(event.pitch);
  const written = pitch?.written ?? event.pitch ?? "Sin altura";
  const extras = [event.is_chord ? "en acorde" : null, event.tie ? "ligada" : null].filter(
    (extra) => extra !== null,
  );
  return {
    place,
    what: `${written} · ${duration}`,
    spoken: `${spokenPlace}: ${[pitch?.spoken ?? written, duration, ...extras].join(", ")}.`,
  };
}
