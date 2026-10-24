import type {
  AnchorPayload,
  EditOp,
  ScoreEventPayload,
  ScoreIRPayload,
  SessionDetailRead,
} from "../../types";
import { durationName, pitchName } from "./noteNames";

/**
 * Correcciones de la altura, la duración y la alteración de una nota (#183, ADR-0030): qué
 * edición pide cada control o tecla sobre el evento elegido, en el vocabulario del contrato
 * (ADR-0017). Nada de esto se da por guardado: lo decide el servidor.
 */

const STEPS = ["C", "D", "E", "F", "G", "A", "B"] as const;
type Step = (typeof STEPS)[number];
const SEMITONES: Record<Step, number> = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };

/** Alteraciones canónicas del contrato, de la más grave a la más aguda. */
export const ACCIDENTALS = ["bb", "b", "", "#", "##"] as const;
export type Accidental = (typeof ACCIDENTALS)[number];
const ALTER: Record<Accidental, number> = { bb: -2, b: -1, "": 0, "#": 1, "##": 2 };
/** Grafías de la alteración en el `ScoreIR` (también las de music21). */
const WRITTEN: Record<string, Accidental> = {
  "": "",
  "#": "#",
  "##": "##",
  x: "##",
  b: "b",
  "-": "b",
  bb: "bb",
  "--": "bb",
};

interface Spelling {
  step: Step;
  accidental: Accidental;
  octave: number;
}

function parsePitch(pitch: string | null): Spelling | null {
  const match = pitch === null ? null : /^([A-Ga-g])(##|bb|--|#|b|-|x)?(-?\d+)$/.exec(pitch.trim());
  if (!match) return null;
  const step = (match[1] ?? "").toUpperCase() as Step;
  const accidental = WRITTEN[match[2] ?? ""];
  if (accidental === undefined) return null;
  return { step, accidental, octave: Number(match[3]) };
}

/**
 * Altura canónica del contrato («C#4»): octava de 0 a 9 y número MIDI de 0 a 127, como exige el
 * servidor (`is_canonical_pitch`). Null si se sale.
 */
function canonical({ step, accidental, octave }: Spelling): string | null {
  const midi = (octave + 1) * 12 + SEMITONES[step] + ALTER[accidental];
  if (octave < 0 || octave > 9 || midi < 0 || midi > 127) return null;
  return `${step}${accidental}${String(octave)}`;
}

/** Alteración que da la armadura (quintas, de -7 a 7) a una letra. */
function keyAccidental(step: Step, fifths: number): Accidental {
  const sharps = ["F", "C", "G", "D", "A", "E", "B"];
  if (fifths > 0) return sharps.indexOf(step) < fifths ? "#" : "";
  if (fifths < 0) return [...sharps].reverse().indexOf(step) < -fifths ? "b" : "";
  return "";
}

/**
 * Un paso diatónico arriba o abajo dentro de la armadura: la nota pasa a la línea o el espacio
 * vecinos con la alteración que la armadura da a esa letra. Una alteración accidental no se
 * arrastra. Null si la altura no se entiende o la nueva se sale del registro.
 */
export function stepPitch(pitch: string | null, direction: 1 | -1, fifths: number): string | null {
  const spelling = parsePitch(pitch);
  if (!spelling) return null;
  const index = STEPS.indexOf(spelling.step) + direction;
  const step = STEPS[(index + STEPS.length) % STEPS.length] ?? "C";
  const octave = spelling.octave + (index < 0 ? -1 : index >= STEPS.length ? 1 : 0);
  return canonical({ step, accidental: keyAccidental(step, fifths), octave });
}

/** La misma nota una octava arriba o abajo, con su letra y su alteración. */
export function octavePitch(pitch: string | null, direction: 1 | -1): string | null {
  const spelling = parsePitch(pitch);
  return spelling ? canonical({ ...spelling, octave: spelling.octave + direction }) : null;
}

export function accidentalOf(pitch: string | null): Accidental | null {
  return parsePitch(pitch)?.accidental ?? null;
}

/** La nota con otra alteración y su letra y su octava, como `SetAccidental` en el servidor. */
export function withAccidental(pitch: string | null, accidental: Accidental): string | null {
  const spelling = parsePitch(pitch);
  return spelling ? canonical({ ...spelling, accidental }) : null;
}

type Fraction = readonly [number, number];

function gcd(a: number, b: number): number {
  return b === 0 ? Math.abs(a) : gcd(b, a % b);
}

function reduce([numerator, denominator]: Fraction): Fraction {
  const divisor = gcd(numerator, denominator) || 1;
  return [numerator / divisor, denominator / divisor];
}

function parseBeats(beats: string | null): Fraction | null {
  const match = beats === null ? null : /^\s*(\d+)(?:\s*\/\s*(\d+))?\s*$/.exec(beats);
  if (!match) return null;
  const denominator = Number(match[2] ?? 1);
  return denominator === 0 ? null : reduce([Number(match[1]), denominator]);
}

const sameFraction = (a: Fraction, b: Fraction) => a[0] * b[1] === b[0] * a[1];

/** Figuras que se ofrecen, de la más breve a la más larga, con la tecla de cada una. */
export const FIGURES = [
  { key: "1", name: "Semifusa", beats: [1, 16] },
  { key: "2", name: "Fusa", beats: [1, 8] },
  { key: "3", name: "Semicorchea", beats: [1, 4] },
  { key: "4", name: "Corchea", beats: [1, 2] },
  { key: "5", name: "Negra", beats: [1, 1] },
  { key: "6", name: "Blanca", beats: [2, 1] },
  { key: "7", name: "Redonda", beats: [4, 1] },
] as const satisfies readonly { key: string; name: string; beats: Fraction }[];

const dot = ([numerator, denominator]: Fraction): Fraction =>
  reduce([numerator * 3, denominator * 2]);

/**
 * Figura (índice de `FIGURES`) y puntillo de una duración en negras. Una duración que no es una
 * figura ni una figura con puntillo (un tresillo, una duración partida, una nota de adorno) no
 * tiene figura.
 */
export function figureOf(beats: string | null): { figure: number | null; dotted: boolean } {
  const value = parseBeats(beats);
  if (value && value[0] > 0) {
    for (const [index, figure] of FIGURES.entries()) {
      if (sameFraction(value, figure.beats)) return { figure: index, dotted: false };
      if (sameFraction(value, dot(figure.beats))) return { figure: index, dotted: true };
    }
  }
  return { figure: null, dotted: false };
}

/** Duración en negras de una figura, con puntillo o sin él, como la escribe el contrato. */
export function figureDuration(figure: number, dotted: boolean): string {
  const beats = FIGURES[figure]?.beats ?? [1, 1];
  const [numerator, denominator] = dotted ? dot(beats) : beats;
  return denominator === 1 ? String(numerator) : `${String(numerator)}/${String(denominator)}`;
}

/** Eventos de la voz del ancla en su compás: el `event_index` cuenta solo los de su voz. */
function voiceEvents(score: ScoreIRPayload, anchor: AnchorPayload): ScoreEventPayload[] | null {
  const measure = score.parts[anchor.part]?.staves[anchor.staff]?.measures.find(
    (candidate) => candidate.number === anchor.measure,
  );
  return measure ? measure.events.filter((event) => event.voice === anchor.voice) : null;
}

/**
 * Evento al que apunta un ancla en un estado (ADR-0011) y si es una nota de un acorde, también la
 * que lo empieza (la siguiente de su voz lleva `is_chord`).
 */
export function eventAt(
  score: ScoreIRPayload,
  anchor: AnchorPayload,
): { event: ScoreEventPayload; chord: boolean } | null {
  const events = voiceEvents(score, anchor);
  const event = events?.[anchor.event_index];
  if (!events || !event) return null;
  const next = events[anchor.event_index + 1];
  const chord =
    event.kind === "note" &&
    (event.is_chord === true || (next?.kind === "note" && !!next.is_chord));
  return { event, chord };
}

/** Armadura activa en el compás del ancla: la última de su pentagrama hasta él (0 si no hay). */
export function activeFifths(score: ScoreIRPayload, anchor: AnchorPayload): number {
  let fifths = 0;
  for (const measure of score.parts[anchor.part]?.staves[anchor.staff]?.measures ?? []) {
    if (measure.key_signature) fifths = measure.key_signature.fifths;
    if (measure.number === anchor.measure) break;
  }
  return fifths;
}

/** Operaciones que no mueven la posición de ningún evento (ADR-0011 §2). */
const IN_PLACE: readonly string[] = [
  "SetPitch",
  "SetDuration",
  "SetAccidental",
  "SetClef",
  "SetKey",
] satisfies EditOp[];

/**
 * Ancla del mismo evento en el estado actual de `detail`, si el ancla de `fromSeq` sigue
 * designándolo: entre los dos estados no se insertó ni se borró nada y el evento sigue ahí.
 * Null si no se puede asegurar (o si el estado es anterior).
 */
export function carryAnchor(
  anchor: AnchorPayload,
  fromSeq: number,
  detail: SessionDetailRead,
): AnchorPayload | null {
  const seq = detail.current_seq ?? 0;
  if (fromSeq > seq || !detail.current_score) return null;
  const moved = detail.edits.some((edit) => edit.seq > fromSeq && !IN_PLACE.includes(edit.op));
  if (moved || !eventAt(detail.current_score, anchor)) return null;
  return anchor;
}

/** Orden de corrección, venga de un botón o de una tecla. */
export type EditCommand =
  | { kind: "step"; direction: 1 | -1 }
  | { kind: "octave"; direction: 1 | -1 }
  | { kind: "accidental"; accidental: Accidental }
  | { kind: "figure"; figure: number }
  | { kind: "dot" };

interface KeyLike {
  key: string;
  shiftKey: boolean;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
}

/**
 * Tecla de corrección sobre la partitura, o null. No usa ninguna tecla de la selección (#182):
 * Mayús con ↑ y ↓ cambia la altura un paso y con Re Pág y Av Pág, una octava; del 1 al 7, la
 * figura, y el punto, el puntillo; + − =, la alteración. Con Ctrl, ⌘ o Alt nada es de la vista:
 * son atajos del navegador o del sistema (zoom, atrás).
 */
export function editCommand(event: KeyLike): EditCommand | null {
  if (event.ctrlKey || event.metaKey || event.altKey) return null;
  if (event.shiftKey) {
    switch (event.key) {
      case "ArrowUp":
        return { kind: "step", direction: 1 };
      case "ArrowDown":
        return { kind: "step", direction: -1 };
      case "PageUp":
        return { kind: "octave", direction: 1 };
      case "PageDown":
        return { kind: "octave", direction: -1 };
    }
  }
  // «+» y «=» llevan Mayús en unos teclados y no en otros: aquí cuenta el carácter.
  switch (event.key) {
    case "+":
      return { kind: "accidental", accidental: "#" };
    case "-":
      return { kind: "accidental", accidental: "b" };
    case "=":
      return { kind: "accidental", accidental: "" };
    case ".":
      return { kind: "dot" };
  }
  const figure = FIGURES.findIndex((candidate) => candidate.key === event.key);
  return figure >= 0 ? { kind: "figure", figure } : null;
}

/** Evento elegido sobre el que se corrige, en el estado que muestra la vista. */
export interface EditTarget {
  anchor: AnchorPayload;
  event: ScoreEventPayload;
  chord: boolean;
}

export type RefusalReason =
  "no-target" | "rest" | "range" | "unknown-pitch" | "chord" | "not-figure" | "same";

const REFUSALS: Record<RefusalReason, string> = {
  "no-target": "Elige primero una nota o un silencio.",
  rest: "Un silencio no tiene altura ni alteración: solo se puede cambiar su figura.",
  range: "La nota saldría del registro que admite la partitura (octavas de 0 a 9).",
  "unknown-pitch": "No se reconoce la altura de esta nota.",
  chord: "En un acorde la figura se cambia en todas sus notas a la vez: desde aquí todavía no.",
  "not-figure": "Esta duración no es una figura simple: elige antes una figura.",
  same: "La nota ya tiene ese valor.",
};

export type EditPlan =
  | {
      kind: "edit";
      op: "SetPitch" | "SetDuration" | "SetAccidental";
      after: Record<string, string>;
      /** Qué cambia, para decirlo: «altura Re 4», «figura corchea». */
      change: string;
    }
  | { kind: "refused"; reason: RefusalReason; message: string };

const refuse = (reason: RefusalReason): EditPlan => ({
  kind: "refused",
  reason,
  message: REFUSALS[reason],
});

const spoken = (pitch: string) => pitchName(pitch)?.spoken ?? pitch;

/**
 * Edición que pide una orden sobre el evento elegido, con `fifths` la armadura de su compás, o
 * por qué no se puede. Cada orden es una decisión completa: una sola edición en el log.
 */
export function planEdit(
  command: EditCommand,
  target: EditTarget | null,
  fifths: number,
): EditPlan {
  if (!target) return refuse("no-target");
  const { event } = target;

  if (command.kind === "figure" || command.kind === "dot") {
    if (target.chord) return refuse("chord");
    const current = figureOf(event.duration_beats);
    let duration: string;
    if (command.kind === "dot") {
      if (current.figure === null) return refuse("not-figure");
      duration = figureDuration(current.figure, !current.dotted);
    } else {
      duration = figureDuration(command.figure, current.figure !== null && current.dotted);
    }
    const before = parseBeats(event.duration_beats);
    const after = parseBeats(duration);
    if (before && after && sameFraction(before, after)) return refuse("same");
    return {
      kind: "edit",
      op: "SetDuration",
      after: { duration_beats: duration },
      change: `figura ${durationName(duration)}`,
    };
  }

  if (event.kind !== "note") return refuse("rest");
  if (!parsePitch(event.pitch)) return refuse("unknown-pitch");

  if (command.kind === "accidental") {
    if (accidentalOf(event.pitch) === command.accidental) return refuse("same");
    const result = withAccidental(event.pitch, command.accidental);
    if (!result) return refuse("range");
    return {
      kind: "edit",
      op: "SetAccidental",
      // El becuadro va con su nombre del contrato, el más explícito en el log.
      after: { accidental: command.accidental === "" ? "natural" : command.accidental },
      change: `alteración: ${spoken(result)}`,
    };
  }

  const pitch =
    command.kind === "step"
      ? stepPitch(event.pitch, command.direction, fifths)
      : octavePitch(event.pitch, command.direction);
  if (!pitch) return refuse("range");
  return { kind: "edit", op: "SetPitch", after: { pitch }, change: `altura ${spoken(pitch)}` };
}

/** Edición ya decidida (su operación y su `after`), para volver a pedirla en otro estado. */
export interface DecidedEdit {
  op: "SetPitch" | "SetDuration" | "SetAccidental";
  after: Record<string, string>;
}

/**
 * La misma edición sobre el evento del estado actual, tras un 409 (ADR-0011: el cliente recarga
 * y reconstruye la edición). Pide el mismo valor final, no el mismo paso: si la nota ya lo tiene,
 * o ya no admite la operación, no hay nada que volver a aplicar.
 */
export function planAgain(edit: DecidedEdit, target: EditTarget | null): EditPlan {
  if (!target) return refuse("no-target");
  const { event } = target;
  if (edit.op === "SetDuration") {
    if (target.chord) return refuse("chord");
    const duration = edit.after.duration_beats ?? null;
    const before = parseBeats(event.duration_beats);
    const after = parseBeats(duration);
    if (before && after && sameFraction(before, after)) return refuse("same");
    return {
      kind: "edit",
      op: "SetDuration",
      after: edit.after,
      change: `figura ${durationName(duration)}`,
    };
  }
  if (event.kind !== "note") return refuse("rest");
  const spelling = parsePitch(event.pitch);
  if (!spelling) return refuse("unknown-pitch");
  if (edit.op === "SetPitch") {
    const pitch = edit.after.pitch ?? "";
    if (canonical(spelling) === pitch) return refuse("same");
    return { kind: "edit", op: "SetPitch", after: edit.after, change: `altura ${spoken(pitch)}` };
  }
  const raw = edit.after.accidental ?? "";
  const accidental = WRITTEN[raw === "natural" ? "" : raw] ?? "";
  if (spelling.accidental === accidental) return refuse("same");
  const result = withAccidental(event.pitch, accidental);
  if (!result) return refuse("range");
  return {
    kind: "edit",
    op: "SetAccidental",
    after: edit.after,
    change: `alteración: ${spoken(result)}`,
  };
}
