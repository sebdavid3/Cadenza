import type {
  AnchorPayload,
  ClefPayload,
  EditOp,
  KeySignaturePayload,
  MeasurePayload,
  ScoreEventPayload,
  ScoreIRPayload,
  SessionViewRead,
} from "../../types";
import { durationName, pitchName } from "./noteNames";

/**
 * Correcciones de la nota elegida: su altura, su duración y su alteración (#183, ADR-0030), y
 * insertar y borrar eventos y cambiar la clave y la armadura de su compás (#184, ADR-0033). Qué
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

/** Compás de un pentagrama: dónde está la nota elegida, sin su voz ni su posición. */
export type MeasurePlace = Pick<AnchorPayload, "part" | "staff" | "measure">;

const measuresOf = (score: ScoreIRPayload, place: MeasurePlace) =>
  score.parts[place.part]?.staves[place.staff]?.measures ?? [];

/**
 * Clave o armadura de un compás: la suya (un cambio en ese compás), la que trae de los anteriores
 * de su pentagrama y hasta qué compás rige la suya, el anterior al siguiente cambio o el último.
 */
function measureAttribute<K extends "clef" | "key_signature">(
  score: ScoreIRPayload,
  place: MeasurePlace,
  attribute: K,
): {
  measure: MeasurePayload;
  own: NonNullable<MeasurePayload[K]> | null;
  inherited: NonNullable<MeasurePayload[K]> | null;
  until: number;
} | null {
  const measures = measuresOf(score, place);
  const index = measures.findIndex((candidate) => candidate.number === place.measure);
  const measure = measures[index];
  if (!measure) return null;
  let inherited: NonNullable<MeasurePayload[K]> | null = null;
  for (const previous of measures.slice(0, index)) inherited = previous[attribute] ?? inherited;
  const next = measures.slice(index + 1).findIndex((later) => (later[attribute] ?? null) !== null);
  const last = next < 0 ? measures.at(-1) : measures[index + next];
  return {
    measure,
    own: measure[attribute] ?? null,
    inherited,
    until: last?.number ?? measure.number,
  };
}

/** Armadura activa en el compás del ancla: la última de su pentagrama hasta él (0 si no hay). */
export function activeFifths(score: ScoreIRPayload, anchor: MeasurePlace): number {
  let fifths = 0;
  for (const measure of measuresOf(score, anchor)) {
    if (measure.key_signature) fifths = measure.key_signature.fifths;
    if (measure.number === anchor.measure) break;
  }
  return fifths;
}

const TREBLE: ClefPayload = { sign: "G", line: 2 };

/** Clave activa en el compás: la última de su pentagrama hasta él; sin ninguna, la de sol. */
export function activeClef(score: ScoreIRPayload, place: MeasurePlace): ClefPayload {
  let clef = TREBLE;
  for (const measure of measuresOf(score, place)) {
    if (measure.clef) clef = measure.clef;
    if (measure.number === place.measure) break;
  }
  return clef;
}

const sameClef = (a: ClefPayload, b: ClefPayload) =>
  a.sign === b.sign &&
  (a.line ?? 2) === (b.line ?? 2) &&
  (a.octave_change ?? 0) === (b.octave_change ?? 0);

/** Operaciones que no mueven la posición de ningún evento (ADR-0011 §2). */
const IN_PLACE: readonly string[] = [
  "SetPitch",
  "SetDuration",
  "SetAccidental",
  "SetClef",
  "SetKey",
] satisfies EditOp[];

const sameVoice = (a: AnchorPayload, b: AnchorPayload) =>
  a.part === b.part && a.staff === b.staff && a.measure === b.measure && a.voice === b.voice;

/**
 * Ancla del mismo evento en el estado actual de `detail`, a partir de su ancla en el estado
 * `fromSeq`, con la regla de desplazamiento de ADR-0011 §2: en su misma voz y compás, insertar
 * en su posición o antes la retrasa una y borrar antes la adelanta una. Null si se borró, si
 * alguna edición no se sabe desplazar, si el evento ya no está o si el estado es anterior.
 */
export function carryAnchor(
  anchor: AnchorPayload,
  fromSeq: number,
  detail: SessionViewRead,
): AnchorPayload | null {
  const seq = detail.current_seq ?? 0;
  if (fromSeq > seq || !detail.current_score) return null;
  let index = anchor.event_index;
  // Cada edición se interpreta sobre el estado anterior a ella: se recorren en orden.
  const later = detail.edits.filter((edit) => edit.seq > fromSeq).sort((a, b) => a.seq - b.seq);
  for (const edit of later) {
    if (IN_PLACE.includes(edit.op)) continue;
    if (edit.op !== "InsertEvent" && edit.op !== "DeleteEvent") return null;
    if (!sameVoice(edit.anchor, anchor)) continue;
    const at = edit.anchor.event_index;
    if (edit.op === "InsertEvent") {
      if (index >= at) index += 1;
    } else if (index === at) {
      return null;
    } else if (index > at) {
      index -= 1;
    }
  }
  const carried = { ...anchor, event_index: index };
  return eventAt(detail.current_score, carried) ? carried : null;
}

/** Orden de corrección, venga de un botón o de una tecla. */
export type EditCommand =
  | { kind: "step"; direction: 1 | -1 }
  | { kind: "octave"; direction: 1 | -1 }
  | { kind: "accidental"; accidental: Accidental }
  | { kind: "figure"; figure: number }
  | { kind: "dot" }
  /** Insertar una nota o un silencio antes del evento elegido. */
  | { kind: "insert"; rest: boolean }
  | { kind: "delete" }
  /** Clave del compás elegido: índice de `CLEFS`. */
  | { kind: "clef"; clef: number }
  /** Armadura del compás elegido, en quintas. */
  | { kind: "key"; fifths: number };

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
 * figura, y el punto, el puntillo; + − =, la alteración; N inserta una nota y S un silencio antes
 * del evento elegido, y Supr o Retroceso lo borran (en un Mac, la tecla de borrar es Retroceso).
 * Con Ctrl, ⌘ o Alt nada es de la vista: son atajos del navegador o del sistema (zoom, atrás).
 */
export function editCommand(event: KeyLike): EditCommand | null {
  if (event.ctrlKey || event.metaKey || event.altKey) return null;
  switch (event.key) {
    case "Delete":
    case "Backspace":
      return { kind: "delete" };
    case "n":
    case "N":
      return { kind: "insert", rest: false };
    case "s":
    case "S":
      return { kind: "insert", rest: true };
  }
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
  "no-target" | "rest" | "range" | "unknown-pitch" | "chord" | "chord-head" | "not-figure" | "same";

const REFUSALS: Record<RefusalReason, string> = {
  "no-target": "Elige primero una nota o un silencio.",
  rest: "Un silencio no tiene altura ni alteración: solo se puede cambiar su figura.",
  range: "La nota saldría del registro que admite la partitura (octavas de 0 a 9).",
  "unknown-pitch": "No se reconoce la altura de esta nota.",
  chord: "En un acorde la figura se cambia en todas sus notas a la vez: desde aquí todavía no.",
  "chord-head":
    "La primera nota de un acorde lleva su figura y sus marcas: borra antes las demás notas del acorde.",
  "not-figure": "Esta duración no es una figura simple: elige antes una figura.",
  same: "La nota ya tiene ese valor.",
};

/** Edición ya decidida (su operación y su `after`), para volver a pedirla en otro estado. */
export type DecidedEdit =
  | { op: "SetPitch" | "SetDuration" | "SetAccidental"; after: Record<string, string> }
  | { op: "InsertEvent"; after: Record<string, string> }
  | { op: "DeleteEvent"; after: null }
  /** La clave elegida (índice de `CLEFS`): su `after` depende del estado (ADR-0033). */
  | { op: "SetClef"; after: Record<string, unknown>; clef: number }
  /** La armadura elegida, en quintas. */
  | { op: "SetKey"; after: Record<string, unknown>; fifths: number };

export type EditPlan =
  | (DecidedEdit & {
      kind: "edit";
      /** Qué cambia, para decirlo: «altura Re 4», «figura corchea». */
      change: string;
      /** Ancla de la edición, si no es la del evento elegido (un acorde, un compás). */
      anchor?: AnchorPayload;
      /**
       * Evento que queda elegido en el estado siguiente al guardarla, o null si ninguno; sin
       * él, la selección sigue en su evento (ADR-0030 §6).
       */
      select?: AnchorPayload | null;
      /** Lo que se añade al decir que se guardó. */
      notice?: string;
    })
  | { kind: "refused"; reason: RefusalReason; message: string };

const refuse = (reason: RefusalReason, message = REFUSALS[reason]): EditPlan => ({
  kind: "refused",
  reason,
  message,
});

const spoken = (pitch: string) => pitchName(pitch)?.spoken ?? pitch;

/** Órdenes que cambian un valor del evento elegido (ADR-0030). */
export type ValueCommand = Extract<
  EditCommand,
  { kind: "step" | "octave" | "accidental" | "figure" | "dot" }
>;

/**
 * Edición que pide una orden de altura, alteración o figura sobre el evento elegido, con
 * `fifths` la armadura de su compás, o por qué no se puede. Cada orden es una decisión
 * completa: una sola edición en el log.
 */
export function planEdit(
  command: ValueCommand,
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

/**
 * La misma edición sobre el evento del estado actual, tras un 409 (ADR-0011: el cliente recarga
 * y reconstruye la edición). Pide el mismo valor final, no el mismo paso: si la nota ya lo tiene,
 * o ya no admite la operación, no hay nada que volver a aplicar. Insertar lo hace antes del mismo
 * evento, y borrar, ese evento; la clave y la armadura se calculan de nuevo sobre `score`.
 */
export function planAgain(
  edit: DecidedEdit,
  target: EditTarget | null,
  score: ScoreIRPayload | null = null,
): EditPlan {
  if (!target) return refuse("no-target");
  switch (edit.op) {
    case "InsertEvent": {
      if (!score) return refuse("no-target");
      const events = voiceEvents(score, target.anchor) ?? [];
      const anchor = insertionAnchor(target.anchor, chordStart(events, target.anchor.event_index));
      return {
        kind: "edit",
        op: "InsertEvent",
        after: edit.after,
        anchor,
        select: anchor,
        change: insertionChange(edit.after),
      };
    }
    case "DeleteEvent":
      return score ? planDelete(target, score) : refuse("no-target");
    case "SetClef":
      return score ? planClef(edit.clef, target.anchor, score) : refuse("no-target");
    case "SetKey":
      return score ? planKey(edit.fifths, target.anchor, score) : refuse("no-target");
  }
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

const isHidden = (event: ScoreEventPayload) => event.hidden === true;

/**
 * Posición del evento que empieza el acorde del evento `index` de una voz, o la suya si no es de
 * un acorde. Se agrupan como el exportador: una nota y las que la siguen marcadas como acorde.
 */
function chordStart(events: readonly ScoreEventPayload[], index: number): number {
  let start = index;
  while (
    start > 0 &&
    events[start]?.kind === "note" &&
    events[start]?.is_chord === true &&
    events[start - 1]?.kind === "note"
  ) {
    start -= 1;
  }
  return start;
}

/** Ancla de una inserción: la posición en que queda el evento nuevo, sin caja ni confianza. */
const insertionAnchor = (anchor: AnchorPayload, eventIndex: number): AnchorPayload => ({
  ...anchor,
  event_index: eventIndex,
  bbox: null,
  confidence: null,
});

/** Una nota o un silencio, para decirlo: «Re 4, negra», «un silencio de negra». */
export function eventName(
  kind: string,
  pitch: string | null | undefined,
  beats: string | null,
): string {
  const duration = durationName(beats);
  return kind === "note" && pitch ? `${spoken(pitch)}, ${duration}` : `un silencio de ${duration}`;
}

export const insertionChange = (after: Record<string, string>) =>
  `inserción de ${eventName(after.kind ?? "rest", after.pitch, after.duration_beats ?? null)}`;

/**
 * La duración en negras como la admite el servidor (ADR-0017): mayor que 0, como mucho 16, con
 * denominador 2^a·t (t ∈ {1, 3, 5, 7}) de hasta 128. Null si no lo es.
 */
function admissible(beats: string | null): string | null {
  const value = parseBeats(beats);
  if (!value || value[0] <= 0 || value[0] > 16 * value[1] || value[1] > 128) return null;
  let odd = value[1];
  while (odd % 2 === 0) odd /= 2;
  if (![1, 3, 5, 7].includes(odd)) return null;
  return value[1] === 1 ? String(value[0]) : `${String(value[0])}/${String(value[1])}`;
}

/** Nota de la línea en que va cada clave: el sol 4, el fa 3 y el do 4. */
const CLEF_NOTES: Record<string, { step: Step; octave: number }> = {
  G: { step: "G", octave: 4 },
  F: { step: "F", octave: 3 },
  C: { step: "C", octave: 4 },
};

/**
 * Nota de la línea central del pentagrama con una clave, con la alteración que le da la
 * armadura: el Si4 en clave de sol, el Re3 en clave de fa. Null con otra clave (la de percusión).
 */
function middleLine(clef: ClefPayload, fifths: number): string | null {
  const reference = CLEF_NOTES[clef.sign];
  if (!reference) return null;
  // La línea central es la tercera, y de una línea a la siguiente hay dos pasos.
  const position =
    STEPS.indexOf(reference.step) +
    (3 - (clef.line ?? 2)) * 2 +
    STEPS.length * (reference.octave + (clef.octave_change ?? 0));
  const step = STEPS[((position % STEPS.length) + STEPS.length) % STEPS.length] ?? "B";
  const octave = Math.floor(position / STEPS.length);
  return canonical({ step, accidental: keyAccidental(step, fifths), octave });
}

/**
 * Insertar una nota o un silencio antes del evento elegido (ADR-0033): con la figura del evento
 * elegido (una negra si no la admite el servidor, como una nota de adorno) y, una nota, con su
 * altura o, ante un silencio, la de la línea central de la clave. Dentro de un acorde se inserta
 * antes del acorde entero. El evento nuevo queda elegido.
 */
export function planInsert(
  rest: boolean,
  target: EditTarget | null,
  score: ScoreIRPayload,
): EditPlan {
  if (!target) return refuse("no-target");
  const events = voiceEvents(score, target.anchor) ?? [];
  const start = chordStart(events, target.anchor.event_index);
  const duration = admissible(events[start]?.duration_beats ?? null) ?? "1";
  const after: Record<string, string> = { kind: rest ? "rest" : "note", duration_beats: duration };
  if (!rest) {
    const own = parsePitch(target.event.kind === "note" ? target.event.pitch : null);
    after.pitch =
      (own && canonical(own)) ??
      middleLine(activeClef(score, target.anchor), activeFifths(score, target.anchor)) ??
      "B4";
  }
  const anchor = insertionAnchor(target.anchor, start);
  return {
    kind: "edit",
    op: "InsertEvent",
    after,
    anchor,
    select: anchor,
    change: insertionChange(after),
  };
}

/** Eventos que se ven de una voz en un compás, con su posición en la voz. */
function visibleIn(measure: MeasurePayload, voice: number) {
  return measure.events
    .filter((event) => event.voice === voice)
    .map((event, index) => ({ event, index }))
    .filter(({ event }) => !isHidden(event));
}

/**
 * Evento que queda elegido tras borrar el del ancla, con su ancla en el estado siguiente: el que
 * pasa a ocupar su sitio en la voz o, si no hay, el anterior; si su voz se queda sin nada que se
 * vea en el compás, el primero del compás siguiente (de la misma voz o de la primera) o el último
 * del anterior, como los movimientos de la selección. Los silencios invisibles no se eligen.
 */
export function selectAfterDelete(
  score: ScoreIRPayload,
  anchor: AnchorPayload,
): AnchorPayload | null {
  const staff = score.parts[anchor.part]?.staves[anchor.staff];
  if (!staff) return null;
  const at = (
    measure: MeasurePayload,
    voice: number,
    eventIndex: number,
    event: ScoreEventPayload,
  ): AnchorPayload => ({
    part: anchor.part,
    staff: anchor.staff,
    measure: measure.number,
    voice,
    event_index: eventIndex,
    staff_id: staff.id,
    bbox: event.bbox,
    confidence: event.confidence,
  });
  const position = staff.measures.findIndex((measure) => measure.number === anchor.measure);
  const measure = staff.measures[position];
  if (!measure) return null;
  const own = visibleIn(measure, anchor.voice);
  const next = own.find(({ index }) => index > anchor.event_index);
  if (next) return at(measure, anchor.voice, next.index - 1, next.event);
  const previous = own.filter(({ index }) => index < anchor.event_index).at(-1);
  if (previous) return at(measure, anchor.voice, previous.index, previous.event);

  const lane = (other: MeasurePayload) => {
    const voices = [
      ...new Set(other.events.filter((event) => !isHidden(event)).map((e) => e.voice)),
    ].sort((a, b) => a - b);
    const voice = voices.includes(anchor.voice) ? anchor.voice : voices[0];
    return voice === undefined ? null : { voice, events: visibleIn(other, voice) };
  };
  for (const later of staff.measures.slice(position + 1)) {
    const found = lane(later);
    const first = found?.events[0];
    if (found && first) return at(later, found.voice, first.index, first.event);
  }
  for (const earlier of staff.measures.slice(0, position).reverse()) {
    const found = lane(earlier);
    const last = found?.events.at(-1);
    if (found && last) return at(earlier, found.voice, last.index, last.event);
  }
  return null;
}

/**
 * Extremos de ligadura de expresión del evento que se dibujan: los que tienen pareja en su parte.
 * Al borrarlo, la otra se queda huérfana y la ligadura deja de dibujarse (ADR-0031 §5).
 */
function drawnSlurEnds(score: ScoreIRPayload, target: EditTarget): number {
  const ends = target.event.slurs ?? [];
  if (ends.length === 0) return 0;
  const others = (score.parts[target.anchor.part]?.staves ?? []).flatMap((staff) =>
    staff.measures.flatMap((measure) =>
      measure.events
        .filter((event) => event !== target.event)
        .flatMap((event) => event.slurs ?? []),
    ),
  );
  return ends.filter((end) =>
    others.some((other) => other.number === end.number && other.type !== end.type),
  ).length;
}

/**
 * Borrar el evento elegido (ADR-0033). La primera nota de un acorde con más notas no se borra:
 * lleva la figura y las marcas del acorde, y la siguiente pasaría a formar acorde con lo que la
 * precede. Si la nota lleva un extremo de una ligadura de expresión, se dice que la ligadura deja
 * de dibujarse. Queda elegido el evento vecino (`selectAfterDelete`).
 */
export function planDelete(target: EditTarget | null, score: ScoreIRPayload): EditPlan {
  if (!target) return refuse("no-target");
  const events = voiceEvents(score, target.anchor) ?? [];
  const index = target.anchor.event_index;
  const next = events[index + 1];
  if (
    target.event.kind === "note" &&
    chordStart(events, index) === index &&
    next?.kind === "note" &&
    next.is_chord === true
  ) {
    return refuse("chord-head");
  }
  const slurs = drawnSlurEnds(score, target);
  const { kind, pitch, duration_beats } = target.event;
  return {
    kind: "edit",
    op: "DeleteEvent",
    after: null,
    anchor: target.anchor,
    select: selectAfterDelete(score, target.anchor),
    change: `borrado de ${eventName(kind, pitch, duration_beats)}`,
    ...(slurs === 0
      ? {}
      : {
          notice:
            slurs === 1
              ? "Su ligadura de expresión ya no se dibuja."
              : "Sus ligaduras de expresión ya no se dibujan.",
        }),
  };
}

/** Claves que se ofrecen: las que HOMR y los métodos de lectura usan. */
export const CLEFS = [
  { word: "Sol", name: "Clave de sol", spoken: "sol", sign: "G", line: 2 },
  { word: "Fa", name: "Clave de fa", spoken: "fa", sign: "F", line: 4 },
  { word: "Do 3", name: "Clave de do en tercera", spoken: "do en tercera", sign: "C", line: 3 },
  { word: "Do 4", name: "Clave de do en cuarta", spoken: "do en cuarta", sign: "C", line: 4 },
] as const;

/** Una armadura por sus alteraciones: «2 sostenidos», «1 bemol», «sin alteraciones». */
export function keyName(fifths: number): string {
  const count = Math.abs(fifths);
  if (count === 0) return "sin alteraciones";
  const word = fifths > 0 ? "sostenido" : "bemol";
  return `${String(count)} ${word}${count === 1 ? "" : fifths > 0 ? "s" : "es"}`;
}

/** Una armadura para elegirla: «2 sostenidos», «Sin alteraciones» (se cuentan en la imagen). */
export function keyLabel(fifths: number): string {
  const name = keyName(fifths);
  return `${name.charAt(0).toUpperCase()}${name.slice(1)}`;
}

/** Compases a los que llega un cambio de clave o de armadura: «compases 3 a 8», «compás 3». */
export interface MeasureRange {
  from: number;
  until: number;
}

/**
 * Compases a los que llega la clave o la armadura que se ponga en el compás: de él al anterior
 * al siguiente cambio de su pentagrama, o al último. Null si el compás no está.
 */
export function attributeRange(
  score: ScoreIRPayload,
  place: MeasurePlace,
  attribute: "clef" | "key_signature",
): MeasureRange | null {
  const found = measureAttribute(score, place, attribute);
  return found ? { from: found.measure.number, until: found.until } : null;
}

export const rangeName = ({ from, until }: MeasureRange) =>
  from === until ? `compás ${String(from)}` : `compases ${String(from)} a ${String(until)}`;

/** Los compases a los que llega un cambio, para decirlo: «en los compases 3 a 8». */
const span = (from: number, until: number) =>
  `en ${from === until ? "el" : "los"} ${rangeName({ from, until })}`;

/** Lo que conviene saber al cambiar la clave o la armadura: SetClef y SetKey no tocan las notas. */
const KEEPS_PITCHES = "Las notas conservan su altura.";

/** Ancla de una edición del compás: su primer evento (ADR-0010), o la posición 0 de la voz 0. */
function measureAnchor(
  score: ScoreIRPayload,
  place: MeasurePlace,
  measure: MeasurePayload,
): AnchorPayload {
  const first = measure.events[0];
  return {
    part: place.part,
    staff: place.staff,
    measure: measure.number,
    voice: first?.voice ?? 0,
    event_index: 0,
    staff_id: score.parts[place.part]?.staves[place.staff]?.id ?? "",
    bbox: first?.bbox ?? null,
    confidence: first?.confidence ?? null,
  };
}

/**
 * Cambiar la clave del compás elegido (ADR-0033): la clave del compás, que rige hasta el
 * siguiente cambio de su pentagrama. Si es la que trae de los compases anteriores, se quita el
 * cambio del compás (`{"clef": null}`); en el primero se escribe siempre. Las notas conservan su
 * altura: SetClef solo cambia la clave (ADR-0010).
 */
export function planClef(
  choice: number,
  place: MeasurePlace | null,
  score: ScoreIRPayload,
): EditPlan {
  const clef = CLEFS[choice];
  const found = place ? measureAttribute(score, place, "clef") : null;
  if (!place || !clef || !found) return refuse("no-target");
  const chosen: ClefPayload = { sign: clef.sign, line: clef.line };
  if (sameClef(found.own ?? found.inherited ?? TREBLE, chosen)) {
    return refuse("same", "El compás ya tiene esa clave.");
  }
  const back = found.own !== null && found.inherited !== null && sameClef(found.inherited, chosen);
  return {
    kind: "edit",
    op: "SetClef",
    after: back ? { clef: null } : { sign: clef.sign, line: clef.line },
    clef: choice,
    anchor: measureAnchor(score, place, found.measure),
    change: `clave de ${clef.spoken} ${span(found.measure.number, found.until)}`,
    notice: KEEPS_PITCHES,
  };
}

/**
 * Cambiar la armadura del compás elegido (ADR-0033), con el modo de la que rige si es mayor o menor. Si
 * es la que trae de los compases anteriores (sin ninguna, «sin alteraciones»), se quita el cambio
 * del compás (`{"key_signature": null}`). Las notas conservan su altura.
 */
export function planKey(
  fifths: number,
  place: MeasurePlace | null,
  score: ScoreIRPayload,
): EditPlan {
  const found = place ? measureAttribute(score, place, "key_signature") : null;
  if (!place || !found || !Number.isInteger(fifths) || Math.abs(fifths) > 7) {
    return refuse("no-target");
  }
  const active: KeySignaturePayload | null = found.own ?? found.inherited;
  if ((active?.fifths ?? 0) === fifths) return refuse("same", "El compás ya tiene esa armadura.");
  const back = found.own !== null && (found.inherited?.fifths ?? 0) === fifths;
  // Solo los modos que admite el servidor (ADR-0017); otro (un dórico de music21) se omite.
  const mode = active?.mode === "major" || active?.mode === "minor" ? active.mode : null;
  return {
    kind: "edit",
    op: "SetKey",
    after: back ? { key_signature: null } : { fifths, ...(mode ? { mode } : {}) },
    fifths,
    anchor: measureAnchor(score, place, found.measure),
    change: `armadura ${fifths === 0 ? keyName(0) : `de ${keyName(fifths)}`} ${span(found.measure.number, found.until)}`,
    notice: KEEPS_PITCHES,
  };
}

/** Edición que pide cualquier orden sobre el evento elegido en el estado `score`. */
export function planCommand(
  command: EditCommand,
  target: EditTarget | null,
  score: ScoreIRPayload | null,
): EditPlan {
  if (!score) return refuse("no-target");
  switch (command.kind) {
    case "insert":
      return planInsert(command.rest, target, score);
    case "delete":
      return planDelete(target, score);
    case "clef":
      return planClef(command.clef, target?.anchor ?? null, score);
    case "key":
      return planKey(command.fifths, target?.anchor ?? null, score);
    default:
      return planEdit(command, target, target ? activeFifths(score, target.anchor) : 0);
  }
}

/** Edición enviada: lo decidido, su ancla y el estado sobre el que se construyó (ADR-0011). */
export type EditRequestLike = DecidedEdit & { anchor: AnchorPayload; baseSeq: number };

/**
 * Tras un 409, la misma edición sobre el estado recargado (`detail`), con su ancla llevada a él
 * (ADR-0011 §2), y el ancla llevada, o null si su evento ya no está. La clave y la armadura son
 * del compás: no dependen de que siga su primer evento.
 */
export function replan(
  request: EditRequestLike,
  detail: SessionViewRead,
): { plan: EditPlan; anchor: AnchorPayload | null } {
  const score = detail.current_score ?? null;
  if (score && (request.op === "SetClef" || request.op === "SetKey")) {
    const plan =
      request.op === "SetClef"
        ? planClef(request.clef, request.anchor, score)
        : planKey(request.fifths, request.anchor, score);
    return { plan, anchor: request.anchor };
  }
  const anchor = carryAnchor(request.anchor, request.baseSeq, detail);
  const found = anchor && score ? eventAt(score, anchor) : null;
  return { plan: planAgain(request, anchor && found ? { anchor, ...found } : null, score), anchor };
}
