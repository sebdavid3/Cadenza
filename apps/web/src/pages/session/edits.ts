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
import {
  ARTICULATIONS,
  chordStart,
  MARK_OPS,
  measureAnchor,
  planMark,
  replanMark,
  voiceEvents,
  type MarkCommand,
  type MarkDecision,
} from "./markEdits";
import {
  METER_OPS,
  planTime,
  planTuplet,
  replanMeter,
  type MeterDecision,
  type TimeChoice,
  type TupletCommand,
} from "./meterEdits";
import { durationName, pitchName } from "./noteNames";
import { planTie, replanTie, type TieCommand, type TieDecision } from "./tieEdits";

/**
 * Correcciones de la nota elegida: su altura, su duración y su alteración (#183, ADR-0030; la
 * figura de un acorde entero, #243, ADR-0049), insertar y borrar eventos y cambiar la clave y la
 * armadura de su compás (#184, ADR-0033), sus marcas de notación (#214, ADR-0039, en
 * `markEdits`), el compás y los tresillos (#241, ADR-0048, en `meterEdits`), y las notas de un
 * acorde y la ligadura de prolongación (#312, ADR-0055; la ligadura, en `tieEdits`). Qué edición
 * pide cada control o tecla sobre el evento elegido, en el vocabulario del contrato (ADR-0017).
 * Nada de esto se da por guardado: lo decide el servidor.
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

/** Número MIDI de una altura, para ordenar las notas de un acorde. */
const midiOf = ({ step, accidental, octave }: Spelling) =>
  (octave + 1) * 12 + SEMITONES[step] + ALTER[accidental];

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

/** Una figura de tresillo de 3:2: dura 2/3 de la figura (#241). */
const triplet = ([numerator, denominator]: Fraction): Fraction =>
  reduce([numerator * 2, denominator * 3]);

/**
 * Figura (índice de `FIGURES`), puntillo y tresillo de una duración en negras: una corchea de
 * tresillo es la corchea con `triplet` (#241). Una duración que no es una figura, con puntillo o
 * de tresillo (una duración partida, una nota de adorno) no tiene figura.
 */
export function figureOf(beats: string | null): {
  figure: number | null;
  dotted: boolean;
  triplet: boolean;
} {
  const value = parseBeats(beats);
  if (value && value[0] > 0) {
    for (const [index, figure] of FIGURES.entries()) {
      if (sameFraction(value, figure.beats))
        return { figure: index, dotted: false, triplet: false };
      if (sameFraction(value, dot(figure.beats))) {
        return { figure: index, dotted: true, triplet: false };
      }
      if (sameFraction(value, triplet(figure.beats))) {
        return { figure: index, dotted: false, triplet: true };
      }
    }
  }
  return { figure: null, dotted: false, triplet: false };
}

/**
 * Duración en negras de una figura, con puntillo o sin él, o de tresillo, como la escribe el
 * contrato.
 */
export function figureDuration(figure: number, dotted: boolean, inTriplet = false): string {
  const beats = FIGURES[figure]?.beats ?? [1, 1];
  const [numerator, denominator] = dotted ? dot(beats) : inTriplet ? triplet(beats) : beats;
  return denominator === 1 ? String(numerator) : `${String(numerator)}/${String(denominator)}`;
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

/** Operaciones que no mueven la posición de ningún evento (ADR-0011 §2); las marcas tampoco. */
const IN_PLACE: readonly string[] = [
  ...([
    "SetPitch",
    "SetDuration",
    "SetChordDuration",
    "SetAccidental",
    "SetClef",
    "SetKey",
  ] satisfies EditOp[]),
  ...MARK_OPS,
  // El compás y los tresillos tampoco (ADR-0044), ni la ligadura de prolongación (ADR-0055), ni
  // escribir en un hueco o hacerlo visible (ADR-0058).
  ...METER_OPS,
  "SetTie",
  "SetEventKind",
];

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
  | { kind: "key"; fifths: number }
  /** Marcas de notación del evento elegido (ADR-0039). */
  | MarkCommand
  /** Poner o quitar el tresillo (ADR-0044, #241). */
  | TupletCommand
  /** Indicación de compás desde el compás elegido (ADR-0044, #241). */
  | { kind: "time"; time: TimeChoice }
  /** Añadir una nota al acorde de la elegida, o formar uno con ella (ADR-0055, #312). */
  | { kind: "chord-add" }
  /** Ligar con la siguiente, o quitar la ligadura que sale o la que llega (ADR-0055, #312). */
  | TieCommand
  /**
   * Marcar el evento elegido como inicio de la ligadura o el regulador que se cree después: no
   * es una edición.
   */
  | { kind: "origin" }
  /** Entrar en el modo «Escribir» o salir de él (#350): no es una edición; lo lleva la vista. */
  | { kind: "writing" }
  | WriteCommand;

/**
 * Escribir con el ratón (#350). `write` da al evento la altura señalada: una nota cambia de
 * altura y un silencio o un hueco pasa a ser esa nota, con su figura; `write-figure` le da la
 * figura elegida; `write-insert` inserta una nota nueva antes del evento (o, con `end`, tras el
 * último de su voz en el compás); `write-chord` añade la altura al acorde de la nota.
 */
export type WriteCommand =
  | { kind: "write"; pitch: string }
  | { kind: "write-figure"; figure: number; dotted: boolean }
  | { kind: "write-insert"; pitch: string; figure: number; dotted: boolean; end: boolean }
  | { kind: "write-chord"; pitch: string };

/** Órdenes que piden una edición (todas menos marcar el inicio y entrar en el modo «Escribir»). */
export type PlannedCommand = Exclude<EditCommand, { kind: "origin" } | { kind: "writing" }>;

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
 * del evento elegido (en un hueco de la voz, los escriben en él, ADR-0058), y Supr o Retroceso lo
 * borran (en un Mac, la tecla de borrar es Retroceso).
 * Las marcas (ADR-0039): P, A, M y T ponen o quitan el picado, el acento, el marcato y el tenuto,
 * y C el calderón; I marca el inicio, y L, < y > crean desde él una ligadura de expresión, un
 * crescendo o un diminuendo hasta el evento elegido. R pone o quita el tresillo de tres figuras
 * desde el evento elegido y Mayús+R, el de todo su compás (#241). E añade una nota al acorde y U
 * pone o quita la ligadura de prolongación con la siguiente (#312). Con Ctrl, ⌘ o Alt nada es de
 * la vista: son atajos del navegador o del sistema (zoom, atrás).
 */
export function editCommand(event: KeyLike): EditCommand | null {
  if (event.ctrlKey || event.metaKey || event.altKey) return null;
  const letter = event.key.length === 1 ? event.key.toUpperCase() : "";
  const articulation = ARTICULATIONS.find((candidate) => candidate.key === letter);
  if (articulation) return { kind: "articulation", articulation: articulation.value };
  switch (letter) {
    case "C":
      return { kind: "fermata" };
    case "I":
      return { kind: "origin" };
    case "L":
      return { kind: "span", span: "slur" };
    case "R":
      // Con Mayús (no con Bloq Mayús), en todo el compás.
      return { kind: "tuplet", scope: event.shiftKey ? "measure" : "group" };
    case "E":
      return { kind: "chord-add" };
    case "U":
      return { kind: "tie" };
    case "W":
      return { kind: "writing" };
  }
  switch (event.key) {
    case "<":
      return { kind: "span", span: "crescendo" };
    case ">":
      return { kind: "span", span: "diminuendo" };
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
  | "no-target"
  | "rest"
  | "range"
  | "unknown-pitch"
  | "not-figure"
  /** El puntillo de una figura de tresillo (#241). */
  | "triplet-dot"
  | "same"
  /** Crear una ligadura o un regulador sin un inicio marcado que siga en la partitura. */
  | "no-origin"
  /** Un inicio y un final que no forman una ligadura o un regulador. */
  | "span"
  /** Un compás o un tresillo que no se puede poner ahí (#241). */
  | "meter"
  /** Una ligadura de prolongación que no se puede poner o quitar ahí (#312). */
  | "tie"
  /** Una nota que no se puede añadir a ese acorde (#312). */
  | "chord"
  /** Lo que un hueco de una voz no admite (ADR-0058, #317). */
  | "gap";

/** Rechazos que dicen su motivo con un mensaje propio. */
type OwnMessage = "no-origin" | "span" | "meter" | "tie" | "chord";

const REFUSALS: Record<Exclude<RefusalReason, OwnMessage>, string> = {
  "no-target": "Elige primero una nota o un silencio.",
  rest: "Un silencio no tiene altura ni alteración: solo se puede cambiar su figura.",
  range: "La nota saldría del registro que admite la partitura (octavas de 0 a 9).",
  "unknown-pitch": "No se reconoce la altura de esta nota.",
  "not-figure": "Esta duración no es una figura simple: elige antes una figura.",
  "triplet-dot": "Una figura de tresillo no lleva puntillo: quita antes el tresillo.",
  same: "La nota ya tiene ese valor.",
  gap: "Un hueco no tiene altura ni marcas: escribe antes una nota en él (N) o hazlo un silencio (S).",
};

/** Edición ya decidida (su operación y su `after`), para volver a pedirla en otro estado. */
export type DecidedEdit =
  | { op: "SetPitch" | "SetDuration" | "SetAccidental"; after: Record<string, string> }
  /** Con `is_chord: true`, una nota más del acorde que la precede (ADR-0055). */
  | { op: "InsertEvent"; after: Record<string, string | boolean> }
  /** En la primera nota de un acorde, `{ keep_chord: true }` (ADR-0055). */
  | { op: "DeleteEvent"; after: null | { keep_chord: true } }
  /** La figura de un acorde entero (ADR-0049): la misma para cada una de sus notas. */
  | { op: "SetChordDuration"; after: { durations: string[] } }
  /**
   * Una nota o un silencio que se ve en un hueco de una voz (ADR-0058). Un literal, no una
   * interfaz: va como `Record<string, unknown>` en la petición.
   */
  | { op: "SetEventKind"; after: { kind: "note" | "rest"; pitch: string | null; hidden: false } }
  /** La clave elegida (índice de `CLEFS`): su `after` depende del estado (ADR-0033). */
  | { op: "SetClef"; after: Record<string, unknown>; clef: number }
  /** La armadura elegida, en quintas. */
  | { op: "SetKey"; after: Record<string, unknown>; fifths: number }
  /** Una marca de notación (ADR-0039). */
  | MarkDecision
  /** El compás o un tresillo (ADR-0044, #241). */
  | MeterDecision
  /** La ligadura de prolongación (ADR-0055, #312). */
  | TieDecision;

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

const refuse = (
  reason: Exclude<RefusalReason, OwnMessage>,
  message = REFUSALS[reason],
): EditPlan => ({
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

/** Las notas de un acorde y el ancla de la primera, que lo empieza (ADR-0049). */
export interface ChordNotes {
  anchor: AnchorPayload;
  notes: ScoreEventPayload[];
}

/**
 * El acorde del evento elegido en `score`, agrupado como el exportador (una nota y las que la
 * siguen marcadas como acorde), o null si el evento no es de un acorde de dos o más notas.
 */
export function chordOf(score: ScoreIRPayload, anchor: AnchorPayload): ChordNotes | null {
  const events = voiceEvents(score, anchor);
  if (!events?.[anchor.event_index]) return null;
  const start = chordStart(events, anchor.event_index);
  const head = events[start];
  if (head?.kind !== "note") return null;
  let end = start + 1;
  while (events[end]?.kind === "note" && events[end]?.is_chord === true) end += 1;
  if (end - start < 2) return null;
  return {
    anchor: { ...anchor, event_index: start, bbox: head.bbox, confidence: head.confidence },
    notes: events.slice(start, end),
  };
}

/** La figura que se dibuja del evento elegido: en un acorde, la de su primera nota. */
export function drawnDuration(target: EditTarget, score: ScoreIRPayload | null): string | null {
  const chord = target.chord && score ? chordOf(score, target.anchor) : null;
  return (chord?.notes[0] ?? target.event).duration_beats ?? null;
}

const sameBeats = (a: string | null | undefined, b: string | null) => {
  const left = parseBeats(a ?? null);
  const right = parseBeats(b);
  return left !== null && right !== null && sameFraction(left, right);
};

/**
 * La edición que pone la figura `duration` al evento elegido: `SetDuration` en una nota o un
 * silencio y, en un acorde, `SetChordDuration` en todas sus notas a la vez, anclada en la primera
 * (ADR-0049). Sin `score` no se sabe qué notas tiene el acorde.
 */
function planFigure(duration: string, target: EditTarget, score: ScoreIRPayload | null): EditPlan {
  if (target.chord) {
    if (!score) return refuse("no-target");
    const chord = chordOf(score, target.anchor);
    if (chord) {
      if (chord.notes.every((note) => sameBeats(note.duration_beats, duration))) {
        return refuse("same", "El acorde ya tiene esa figura.");
      }
      return {
        kind: "edit",
        op: "SetChordDuration",
        after: { durations: chord.notes.map(() => duration) },
        anchor: chord.anchor,
        change: `figura ${durationName(duration)} en el acorde`,
      };
    }
  }
  if (sameBeats(target.event.duration_beats, duration)) return refuse("same");
  return {
    kind: "edit",
    op: "SetDuration",
    after: { duration_beats: duration },
    // El ancla es la del evento para el que se calculó: tras un 409 de una figura de acorde, la
    // primera nota del acorde, que puede no ser la elegida.
    anchor: target.anchor,
    change: `figura ${durationName(duration)}`,
  };
}

/**
 * Edición que pide una orden de altura, alteración o figura sobre el evento elegido, con
 * `fifths` la armadura de su compás, o por qué no se puede. Cada orden es una decisión
 * completa: una sola edición en el log; la figura de un acorde, también (ADR-0049).
 */
export function planEdit(
  command: ValueCommand,
  target: EditTarget | null,
  fifths: number,
  score: ScoreIRPayload | null = null,
): EditPlan {
  if (!target) return refuse("no-target");
  const { event } = target;

  if (command.kind === "figure" || command.kind === "dot") {
    const current = figureOf(drawnDuration(target, score));
    let duration: string;
    if (command.kind === "dot") {
      if (current.figure === null) return refuse("not-figure");
      // Con puntillo, una figura de tresillo dura lo que otra sin él (#241).
      if (current.triplet) return refuse("triplet-dot");
      duration = figureDuration(current.figure, !current.dotted);
    } else {
      // La figura conserva el puntillo y el tresillo.
      duration = figureDuration(command.figure, current.dotted, current.triplet);
    }
    return planFigure(duration, target, score);
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
      // Una nota más del acorde: tras su última nota, con la misma altura (ADR-0055).
      if (edit.after.is_chord === true) return planChordAgain(edit.after, target, score);
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
    // El evento elegido ya es del estado `score`: no hay que llevar ningún ancla.
    case "SetNoteMarks":
    case "SetDynamic":
    case "SetSlur":
    case "SetWedge":
      return score
        ? replanMark(edit, target.anchor, score, (anchor) => anchor).plan
        : refuse("no-target");
    case "SetTime":
    case "SetTuplet":
      return score
        ? replanMeter(edit, target.anchor, score, (anchor) => anchor).plan
        : refuse("no-target");
    case "SetTie":
      return score ? replanTie(edit, score, (anchor) => anchor).plan : refuse("no-target");
    case "SetEventKind": {
      // Lo mismo en el hueco, si sigue siéndolo, o en el silencio que pasa a ser nota (#350), si
      // sigue siéndolo, y si una nota no se uniría a un acorde.
      if (!isGap(target.event)) {
        if (target.event.kind !== "rest") {
          return refuse("same", "Ya no es un silencio: no hay nada que escribir en él.");
        }
        if (edit.after.kind !== "note") {
          return refuse("same", "Ya es un silencio que se ve: no hay nada que cambiar.");
        }
        return score !== null && joinsChordAfter(score, target)
          ? JOINS_CHORD
          : restPlan(edit.after.pitch ?? "", target);
      }
      const joins = edit.after.kind === "note" && score !== null && joinsChordAfter(score, target);
      return joins ? JOINS_CHORD : gapPlan(edit.after, target);
    }
  }
  const { event } = target;
  if (edit.op === "SetDuration" || edit.op === "SetChordDuration") {
    // La misma figura sobre lo que el evento sea ahora: una nota sola o un acorde entero.
    const duration =
      edit.op === "SetDuration" ? edit.after.duration_beats : edit.after.durations[0];
    return duration ? planFigure(duration, target, score) : refuse("no-target");
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

/** Un hueco de una voz: un silencio invisible (ADR-0032), que se elige y se corrige (ADR-0058). */
export const isGap = (event: ScoreEventPayload) => event.kind === "rest" && isHidden(event);

/** Lo que se escribe en un hueco con `SetEventKind` (ADR-0058): una nota o un silencio que se ve. */
export type GapFill = Extract<DecidedEdit, { op: "SetEventKind" }>["after"];

/** La edición que escribe `after` en el hueco elegido: el evento se queda donde está y elegido. */
function gapPlan(after: GapFill, target: EditTarget): EditPlan {
  const figure = durationName(target.event.duration_beats ?? null);
  return {
    kind: "edit",
    op: "SetEventKind",
    after,
    anchor: target.anchor,
    change:
      after.kind === "note" && after.pitch
        ? `${spoken(after.pitch)} en el hueco de ${figure}`
        : `silencio de ${figure} en el hueco`,
  };
}

/**
 * Si lo que sigue al hueco o al silencio en su voz es una nota de un acorde: una nota en su lugar
 * se le uniría.
 */
function joinsChordAfter(score: ScoreIRPayload, target: EditTarget): boolean {
  const following = (voiceEvents(score, target.anchor) ?? [])[target.anchor.event_index + 1];
  return following?.kind === "note" && following.is_chord === true;
}

const JOINS_CHORD: EditPlan = {
  kind: "refused",
  reason: "chord",
  message: "Lo que sigue es una nota de un acorde: una nota escrita aquí se uniría a ese acorde.",
};

/**
 * Escribir una nota en el hueco elegido o hacerlo un silencio que se ve (ADR-0058), con su
 * figura: una nota con la altura de la nota anterior de su voz en el compás, o la siguiente; sin
 * ninguna, la de la línea central de la clave, como al insertar ante un silencio (ADR-0033).
 */
export function planFill(rest: boolean, target: EditTarget, score: ScoreIRPayload): EditPlan {
  if (rest) return gapPlan({ kind: "rest", pitch: null, hidden: false }, target);
  if (joinsChordAfter(score, target)) return JOINS_CHORD;
  const events = voiceEvents(score, target.anchor) ?? [];
  const index = target.anchor.event_index;
  const near = (from: readonly ScoreEventPayload[]) =>
    from
      .map((event) => parsePitch(event.kind === "note" ? event.pitch : null))
      .find((spelling): spelling is Spelling => spelling !== null);
  const own = near(events.slice(0, index).reverse()) ?? near(events.slice(index + 1));
  const pitch =
    (own && canonical(own)) ??
    middleLine(activeClef(score, target.anchor), activeFifths(score, target.anchor)) ??
    "B4";
  return gapPlan({ kind: "note", pitch, hidden: false }, target);
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

/** Un valor de un `after` como texto, o null. */
const textOf = (value: unknown): string | null => (typeof value === "string" ? value : null);

export const insertionChange = (after: Record<string, string | boolean>) =>
  after.is_chord === true
    ? `inserción de ${spoken(textOf(after.pitch) ?? "")} en el acorde`
    : `inserción de ${eventName(textOf(after.kind) ?? "rest", textOf(after.pitch), textOf(after.duration_beats))}`;

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

/** Posición del evento que sigue a la última nota del acorde del evento `index` (o a él). */
function chordEnd(events: readonly ScoreEventPayload[], index: number): number {
  let end = chordStart(events, index) + 1;
  while (events[end]?.kind === "note" && events[end]?.is_chord === true) end += 1;
  return end;
}

/**
 * Añadir una nota al acorde de la nota elegida, o formar uno con ella (ADR-0055 §5): un
 * `InsertEvent` con `is_chord` tras su última nota, con la figura del acorde y una tercera por
 * encima de su nota más aguda dentro de la armadura (o por debajo de la más grave, si se sale del
 * registro). La nota nueva queda elegida, para corregir su altura.
 */
export function planChordAdd(target: EditTarget | null, score: ScoreIRPayload): EditPlan {
  if (!target) return refuse("no-target");
  if (target.event.kind !== "note") {
    return {
      kind: "refused",
      reason: "chord",
      message: "Un silencio no forma acordes: elige una nota.",
    };
  }
  const events = voiceEvents(score, target.anchor) ?? [];
  const start = chordStart(events, target.anchor.event_index);
  const end = chordEnd(events, target.anchor.event_index);
  const notes = events.slice(start, end);
  const duration = admissible(notes[0]?.duration_beats ?? null);
  if (!duration) {
    return {
      kind: "refused",
      reason: "chord",
      message: "Una nota de adorno no forma acordes desde la barra.",
    };
  }
  const spellings = notes
    .map((note) => parsePitch(note.pitch))
    .filter((spelling): spelling is Spelling => spelling !== null)
    .sort((a, b) => midiOf(a) - midiOf(b));
  const fifths = activeFifths(score, target.anchor);
  const third = (from: Spelling | undefined, direction: 1 | -1) =>
    from ? stepPitch(stepPitch(canonical(from), direction, fifths), direction, fifths) : null;
  const pitch = third(spellings.at(-1), 1) ?? third(spellings[0], -1);
  if (!pitch) return refuse(spellings.length > 0 ? "range" : "unknown-pitch");
  const after = { kind: "note", pitch, duration_beats: duration, is_chord: true };
  const anchor = insertionAnchor(target.anchor, end);
  return {
    kind: "edit",
    op: "InsertEvent",
    after,
    anchor,
    select: anchor,
    change: insertionChange(after),
  };
}

/** Tras un 409, la misma nota añadida al acorde de la elegida en el estado recargado. */
function planChordAgain(
  after: Record<string, string | boolean>,
  target: EditTarget,
  score: ScoreIRPayload,
): EditPlan {
  if (target.event.kind !== "note") {
    return {
      kind: "refused",
      reason: "chord",
      message: "Un silencio no forma acordes: elige una nota.",
    };
  }
  const events = voiceEvents(score, target.anchor) ?? [];
  const anchor = insertionAnchor(target.anchor, chordEnd(events, target.anchor.event_index));
  return {
    kind: "edit",
    op: "InsertEvent",
    after,
    anchor,
    select: anchor,
    change: insertionChange(after),
  };
}

/** Eventos de una voz en un compás, con su posición en la voz. */
function eventsIn(measure: MeasurePayload, voice: number) {
  return measure.events
    .filter((event) => event.voice === voice)
    .map((event, index) => ({ event, index }));
}

/**
 * Evento que queda elegido tras borrar el del ancla, con su ancla en el estado siguiente: el que
 * pasa a ocupar su sitio en la voz o, si no hay, el anterior; si su voz se queda sin nada en el
 * compás, el primero del compás siguiente (de la misma voz o de la primera) o el último del
 * anterior, como los movimientos de la selección. Los huecos de una voz también se eligen
 * (ADR-0058).
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
  const own = eventsIn(measure, anchor.voice);
  const next = own.find(({ index }) => index > anchor.event_index);
  if (next) return at(measure, anchor.voice, next.index - 1, next.event);
  const previous = own.filter(({ index }) => index < anchor.event_index).at(-1);
  if (previous) return at(measure, anchor.voice, previous.index, previous.event);

  const lane = (other: MeasurePayload) => {
    const voices = [...new Set(other.events.map((e) => e.voice))].sort((a, b) => a - b);
    const voice = voices.includes(anchor.voice) ? anchor.voice : voices[0];
    return voice === undefined ? null : { voice, events: eventsIn(other, voice) };
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
 * Borrar el evento elegido (ADR-0033). La primera nota de un acorde con más notas se borra con
 * `{ keep_chord: true }` (ADR-0055): la siguiente pasa a ser la primera, con la figura y las marcas
 * del acorde (también sus ligaduras de expresión, que se siguen dibujando). Si la nota lleva un
 * extremo de una ligadura de expresión, se dice que la ligadura deja de dibujarse. Queda elegido el
 * evento vecino (`selectAfterDelete`): en un acorde, el que ocupa su sitio.
 */
export function planDelete(target: EditTarget | null, score: ScoreIRPayload): EditPlan {
  if (!target) return refuse("no-target");
  const events = voiceEvents(score, target.anchor) ?? [];
  const index = target.anchor.event_index;
  const next = events[index + 1];
  const head =
    target.event.kind === "note" &&
    chordStart(events, index) === index &&
    next?.kind === "note" &&
    next.is_chord === true;
  const { kind, pitch, duration_beats, hidden } = target.event;
  const inChord = head || target.chord;
  const slurs = head ? 0 : drawnSlurEnds(score, target);
  return {
    kind: "edit",
    op: "DeleteEvent",
    after: head ? { keep_chord: true } : null,
    anchor: target.anchor,
    select: selectAfterDelete(score, target.anchor),
    change: inChord
      ? `borrado de ${spoken(pitch ?? "")} del acorde`
      : hidden === true
        ? `borrado del hueco de ${durationName(duration_beats)}`
        : `borrado de ${eventName(kind, pitch, duration_beats)}`,
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

/**
 * Edición que pide cualquier orden sobre el evento elegido en el estado `score`. `origin` es el
 * inicio marcado para una ligadura o un regulador, llevado a ese estado.
 */
export function planCommand(
  command: PlannedCommand,
  target: EditTarget | null,
  score: ScoreIRPayload | null,
  origin: AnchorPayload | null = null,
): EditPlan {
  if (!score) return refuse("no-target");
  switch (command.kind) {
    case "write":
      return planWrite(command.pitch, target, score);
    case "write-figure":
      return planWriteFigure(command.figure, command.dotted, target, score);
    case "write-insert":
      return planWriteInsert(command, target, score);
    case "write-chord":
      return planWriteChord(command.pitch, target, score);
  }
  if (target && isGap(target.event)) {
    // Un hueco (ADR-0058): N escribe una nota en él, S lo hace un silencio que se ve y Supr lo
    // borra; su figura se cambia como la de un silencio. No tiene altura ni marcas.
    switch (command.kind) {
      case "insert":
        return planFill(command.rest, target, score);
      case "step":
      case "octave":
      case "accidental":
      case "articulation":
      case "fermata":
      case "chord-add":
      case "tie":
      case "untie-in":
        return refuse("gap");
    }
  }
  switch (command.kind) {
    case "articulation":
    case "fermata":
    case "dynamic":
    case "span":
    case "unspan":
      return planMark(command, target, score, origin);
    case "insert":
      return planInsert(command.rest, target, score);
    case "delete":
      return planDelete(target, score);
    case "clef":
      return planClef(command.clef, target?.anchor ?? null, score);
    case "key":
      return planKey(command.fifths, target?.anchor ?? null, score);
    case "time":
      return planTime(command.time, target?.anchor ?? null, score);
    case "tuplet":
      return planTuplet(command.scope, target, score, origin);
    case "chord-add":
      return planChordAdd(target, score);
    case "tie":
    case "untie-in":
      return planTie(command, target, score);
    default:
      return planEdit(command, target, target ? activeFifths(score, target.anchor) : 0, score);
  }
}

// --- Escribir con el ratón (#350) ------------------------------------------------------------

/**
 * Altura de una línea o un espacio del pentagrama: `steps` medios espacios bajo la línea superior
 * (0 es la quinta línea; 8, la primera), con la clave del compás y la alteración que la armadura
 * da a esa letra, como al subir o bajar un paso. Null si la clave no se conoce o la altura se
 * sale del registro.
 */
export function staffPitch(clef: ClefPayload, fifths: number, steps: number): string | null {
  const top = topLine(clef);
  if (top === null) return null;
  const position = top - steps;
  const step = STEPS[((position % STEPS.length) + STEPS.length) % STEPS.length] ?? "C";
  const octave = Math.floor(position / STEPS.length);
  return canonical({ step, accidental: keyAccidental(step, fifths), octave });
}

/** Posición diatónica de la quinta línea con una clave, o null si la clave no se conoce. */
function topLine(clef: ClefPayload): number | null {
  const reference = CLEF_NOTES[clef.sign];
  if (!reference) return null;
  // La quinta línea está a dos pasos por línea por encima de la de la clave.
  return (
    STEPS.indexOf(reference.step) +
    (5 - (clef.line ?? 2)) * 2 +
    STEPS.length * (reference.octave + (clef.octave_change ?? 0))
  );
}

/**
 * Medios espacios bajo la quinta línea en que se dibuja una nota con una clave: lo contrario de
 * `staffPitch`, sin la alteración. Null si la clave o la altura no se conocen.
 */
export function staffSteps(clef: ClefPayload, pitch: string | null): number | null {
  const top = topLine(clef);
  const spelling = parsePitch(pitch);
  if (top === null || !spelling) return null;
  return top - (STEPS.indexOf(spelling.step) + STEPS.length * spelling.octave);
}

/** Un silencio que se ve pasa a ser una nota en su lugar, con su figura (#350, ADR-0058). */
function restPlan(pitch: string, target: EditTarget): EditPlan {
  const figure = durationName(target.event.duration_beats ?? null);
  return {
    kind: "edit",
    op: "SetEventKind",
    after: { kind: "note", pitch, hidden: false },
    anchor: target.anchor,
    change: `${spoken(pitch)} en lugar del silencio de ${figure}`,
  };
}

/** La altura que se escribe: una nota cambia de altura; un silencio o un hueco, pasa a ser nota. */
function planWrite(pitch: string, target: EditTarget | null, score: ScoreIRPayload): EditPlan {
  if (!target) return refuse("no-target");
  const spelling = parsePitch(pitch);
  const written = spelling ? canonical(spelling) : null;
  if (!written) return refuse("range");
  if (target.event.kind === "rest") {
    if (joinsChordAfter(score, target)) return JOINS_CHORD;
    return isGap(target.event)
      ? gapPlan({ kind: "note", pitch: written, hidden: false }, target)
      : restPlan(written, target);
  }
  const own = parsePitch(target.event.pitch);
  if (own && canonical(own) === written) return refuse("same");
  return {
    kind: "edit",
    op: "SetPitch",
    after: { pitch: written },
    change: `altura ${spoken(written)}`,
  };
}

/**
 * La figura con que se escribe: la elegida, con su puntillo; en un tresillo, la figura de
 * tresillo, como al cambiarla desde la barra (#241).
 */
export function writeDuration(
  figure: number,
  dotted: boolean,
  target: EditTarget | null,
  score: ScoreIRPayload | null,
): string {
  const current = target ? figureOf(drawnDuration(target, score)) : null;
  return figureDuration(figure, dotted, !dotted && current?.triplet === true);
}

function planWriteFigure(
  figure: number,
  dotted: boolean,
  target: EditTarget | null,
  score: ScoreIRPayload,
): EditPlan {
  if (!target) return refuse("no-target");
  return planFigure(writeDuration(figure, dotted, target, score), target, score);
}

/** Una nota nueva con la figura elegida, antes del evento o tras el último de su voz. */
function planWriteInsert(
  command: Extract<WriteCommand, { kind: "write-insert" }>,
  target: EditTarget | null,
  score: ScoreIRPayload,
): EditPlan {
  if (!target) return refuse("no-target");
  const spelling = parsePitch(command.pitch);
  const pitch = spelling ? canonical(spelling) : null;
  if (!pitch) return refuse("range");
  const events = voiceEvents(score, target.anchor) ?? [];
  let index = command.end ? events.length : chordStart(events, target.anchor.event_index);
  // Las notas de adorno van con la nota que las sigue: la nueva entra antes de ellas.
  while (!command.end && index > 0 && isGraceNote(events[index - 1])) {
    index = chordStart(events, index - 1);
  }
  const after = {
    kind: "note",
    pitch,
    duration_beats: figureDuration(command.figure, command.dotted),
  };
  const anchor = insertionAnchor(target.anchor, index);
  return {
    kind: "edit",
    op: "InsertEvent",
    after,
    anchor,
    select: anchor,
    change: insertionChange(after),
  };
}

/** Una nota de adorno: no ocupa tiempo y no tiene figura (ADR-0028). */
function isGraceNote(event: ScoreEventPayload | undefined): boolean {
  return event?.kind === "note" && (event.duration_beats ?? null) === null;
}

/** La altura señalada como una nota más del acorde de la nota (ADR-0055 §5). */
function planWriteChord(pitch: string, target: EditTarget | null, score: ScoreIRPayload): EditPlan {
  if (!target) return refuse("no-target");
  if (target.event.kind !== "note") {
    return {
      kind: "refused",
      reason: "chord",
      message: "Un silencio no forma acordes: elige una nota.",
    };
  }
  const spelling = parsePitch(pitch);
  const written = spelling ? canonical(spelling) : null;
  if (!written) return refuse("range");
  const events = voiceEvents(score, target.anchor) ?? [];
  const start = chordStart(events, target.anchor.event_index);
  const end = chordEnd(events, target.anchor.event_index);
  const notes = events.slice(start, end);
  if (
    notes.some((note) => {
      const own = parsePitch(note.pitch);
      return own !== null && canonical(own) === written;
    })
  ) {
    return refuse("same", "Esa nota ya está en el acorde.");
  }
  const duration = admissible(notes[0]?.duration_beats ?? null);
  if (!duration) {
    return {
      kind: "refused",
      reason: "chord",
      message: "Una nota de adorno no forma acordes desde la barra.",
    };
  }
  const after = { kind: "note", pitch: written, duration_beats: duration, is_chord: true };
  const anchor = insertionAnchor(target.anchor, end);
  return {
    kind: "edit",
    op: "InsertEvent",
    after,
    anchor,
    select: anchor,
    change: insertionChange(after),
  };
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
  if (
    score &&
    (request.op === "SetNoteMarks" ||
      request.op === "SetDynamic" ||
      request.op === "SetSlur" ||
      request.op === "SetWedge")
  ) {
    return replanMark(request, request.anchor, score, (anchor) =>
      carryAnchor(anchor, request.baseSeq, detail),
    );
  }
  if (score && (request.op === "SetTime" || request.op === "SetTuplet")) {
    return replanMeter(request, request.anchor, score, (anchor) =>
      carryAnchor(anchor, request.baseSeq, detail),
    );
  }
  // La ligadura se pide de nuevo desde la nota elegida, que puede no ser el ancla (ADR-0055).
  if (score && request.op === "SetTie") {
    return replanTie(request, score, (anchor) => carryAnchor(anchor, request.baseSeq, detail));
  }
  // Una nota añadida a un acorde va tras su última nota: se lleva esa nota, que sigue estando
  // (la posición de la inserción puede ser la siguiente a la última de la voz).
  if (request.op === "InsertEvent" && request.after.is_chord === true) {
    const last = carryAnchor(
      { ...request.anchor, event_index: request.anchor.event_index - 1 },
      request.baseSeq,
      detail,
    );
    const found = last && score ? eventAt(score, last) : null;
    return {
      plan: planAgain(request, last && found ? { anchor: last, ...found } : null, score),
      anchor: last,
    };
  }
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

/**
 * Si la edición sale del inicio marcado (una ligadura, un regulador o un tresillo desde él): al
 * guardarla, el inicio se olvida (ADR-0039, ADR-0048).
 */
export function usesOrigin(edit: DecidedEdit): boolean {
  return "span" in edit || ("tuplet" in edit && edit.tuplet.from !== null);
}
