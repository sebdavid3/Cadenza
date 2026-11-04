import type {
  AnchorPayload,
  DynamicPayload,
  MeasurePayload,
  ScoreEventPayload,
  ScoreIRPayload,
} from "../../types";
import type { EditPlan, EditTarget, MeasurePlace, RefusalReason } from "./edits";
import { durationName, pitchName } from "./noteNames";

/**
 * Añadir y quitar marcas de notación desde la vista de una sesión (#214, ADR-0039): las
 * articulaciones y el calderón del evento elegido (`SetNoteMarks`), la dinámica de su posición
 * (`SetDynamic`), y las ligaduras de expresión y los reguladores (`SetSlur`, `SetWedge`), que se
 * crean desde un inicio marcado hasta el evento elegido y se quitan enteros. Qué edición pide cada
 * orden, en el vocabulario del contrato. Nada se da por guardado: lo decide el servidor.
 */

export type ArticulationValue = NonNullable<ScoreEventPayload["articulations"]>[number];
export type DynamicValue = DynamicPayload["mark"];

/** Articulaciones, en el orden canónico del `ScoreIR` (ADR-0031), con su tecla si la tienen. */
export const ARTICULATIONS = [
  { value: "staccato", name: "Picado", spoken: "picado", key: "P" },
  { value: "staccatissimo", name: "Staccatissimo", spoken: "staccatissimo", key: null },
  { value: "accent", name: "Acento", spoken: "acento", key: "A" },
  { value: "marcato", name: "Marcato", spoken: "marcato", key: "M" },
  { value: "tenuto", name: "Tenuto", spoken: "tenuto", key: "T" },
] as const satisfies readonly {
  value: ArticulationValue;
  name: string;
  spoken: string;
  key: string | null;
}[];

/** Dinámicas del `ScoreIR` (ADR-0031), de la más suave a la más fuerte y los acentos. */
export const DYNAMICS: readonly DynamicValue[] = [
  "ppp",
  "pp",
  "p",
  "mp",
  "mf",
  "f",
  "ff",
  "fff",
  "sf",
  "sfz",
  "fp",
  "fz",
];

/** Ligadura de expresión o regulador que se crea desde el inicio marcado hasta el evento elegido. */
export type SpanKind = "slur" | "crescendo" | "diminuendo";

/** Órdenes sobre las marcas del evento elegido. */
export type MarkCommand =
  | { kind: "articulation"; articulation: ArticulationValue }
  | { kind: "fermata" }
  /** La dinámica de la posición del evento elegido, o null para quitarla. */
  | { kind: "dynamic"; mark: DynamicValue | null }
  /** Crear una ligadura o un regulador desde el inicio marcado hasta el evento elegido. */
  | { kind: "span"; span: SpanKind }
  /** Quitar una ligadura o un regulador de la parte del evento elegido, por su número. */
  | { kind: "unspan"; mark: "slur" | "wedge"; number: number };

/** Lo que guarda una edición de marcas para volver a pedirla en otro estado tras un 409. */
export type MarkDecision =
  | { op: "SetNoteMarks"; after: { articulations: ArticulationValue[]; fermata: boolean } }
  | {
      op: "SetDynamic";
      after: { offset_beats: string; mark: DynamicValue | null };
      /** Compás y pentagrama de la dinámica: es una posición del compás, no de un evento. */
      place: MeasurePlace;
    }
  | {
      op: "SetSlur" | "SetWedge";
      after: Record<string, unknown>;
      /** Creada desde el inicio `from` hasta `to`, en el estado en que se pidió. */
      span: { kind: SpanKind; from: AnchorPayload; to: AnchorPayload };
    }
  | {
      op: "SetSlur" | "SetWedge";
      after: Record<string, unknown>;
      /** Quitada por su número, en su parte. */
      /** `name` dice qué marca era («la ligadura de expresión de los compases 1 a 2»). */
      remove: { mark: "slur" | "wedge"; number: number; part: number; name: string };
    };

const refuse = (reason: RefusalReason, message: string): EditPlan => ({
  kind: "refused",
  reason,
  message,
});

// --- Fracciones de negra ---------------------------------------------------------------------

type Beats = readonly [number, number];

function gcd(a: number, b: number): number {
  return b === 0 ? Math.abs(a) : gcd(b, a % b);
}

function reduce([numerator, denominator]: Beats): Beats {
  const divisor = gcd(numerator, denominator) || 1;
  return [numerator / divisor, denominator / divisor];
}

const add = (a: Beats, b: Beats): Beats => reduce([a[0] * b[1] + b[0] * a[1], a[1] * b[1]]);
const compare = (a: Beats, b: Beats) => a[0] * b[1] - b[0] * a[1];

function parseBeats(value: string | null | undefined): Beats | null {
  const match =
    value === null || value === undefined ? null : /^\s*(\d+)(?:\s*\/\s*(\d+))?\s*$/.exec(value);
  if (!match) return null;
  const denominator = Number(match[2] ?? 1);
  return denominator === 0 ? null : reduce([Number(match[1]), denominator]);
}

/** Una posición en negras como la escribe el contrato: «0», «3/2». */
const beatsText = ([numerator, denominator]: Beats) =>
  denominator === 1 ? String(numerator) : `${String(numerator)}/${String(denominator)}`;

const sameBeats = (a: string | null | undefined, b: Beats) => {
  const parsed = parseBeats(a);
  return parsed !== null && compare(parsed, b) === 0;
};

// --- El evento elegido y su compás ----------------------------------------------------------

/** Eventos de la voz del ancla en su compás: el `event_index` cuenta solo los de su voz. */
export function voiceEvents(
  score: ScoreIRPayload,
  anchor: AnchorPayload,
): ScoreEventPayload[] | null {
  const measure = score.parts[anchor.part]?.staves[anchor.staff]?.measures.find(
    (candidate) => candidate.number === anchor.measure,
  );
  return measure ? measure.events.filter((event) => event.voice === anchor.voice) : null;
}

/**
 * Posición del evento que empieza el acorde del evento `index` de una voz, o la suya si no es de
 * un acorde. Se agrupan como el exportador: una nota y las que la siguen marcadas como acorde.
 */
export function chordStart(events: readonly ScoreEventPayload[], index: number): number {
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

/** Ancla de una edición del compás: su primer evento (ADR-0010), o la posición 0 de la voz 0. */
export function measureAnchor(
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

function measureOf(score: ScoreIRPayload, place: MeasurePlace): MeasurePayload | null {
  return (
    score.parts[place.part]?.staves[place.staff]?.measures.find(
      (candidate) => candidate.number === place.measure,
    ) ?? null
  );
}

/**
 * Evento que lleva las marcas del evento elegido: él mismo o, en un acorde, su primera nota, con
 * su ancla (ADR-0031: las marcas de un acorde van en su primera nota).
 */
export function marksHolder(
  score: ScoreIRPayload,
  anchor: AnchorPayload,
): { anchor: AnchorPayload; event: ScoreEventPayload } | null {
  const events = voiceEvents(score, anchor);
  if (!events?.[anchor.event_index]) return null;
  const index = chordStart(events, anchor.event_index);
  const event = events[index];
  if (!event) return null;
  return {
    anchor: { ...anchor, event_index: index, bbox: event.bbox, confidence: event.confidence },
    event,
  };
}

/**
 * Ataque del evento en negras desde el inicio de su compás: lo que duran los anteriores de su
 * voz; una nota de un acorde ataca con la primera y una nota de adorno no ocupa tiempo.
 */
function onsetOf(score: ScoreIRPayload, anchor: AnchorPayload): Beats | null {
  const events = voiceEvents(score, anchor);
  if (!events?.[anchor.event_index]) return null;
  let onset: Beats = [0, 1];
  const head = chordStart(events, anchor.event_index);
  for (const event of events.slice(0, head)) {
    if (event.is_chord) continue;
    onset = add(onset, parseBeats(event.duration_beats) ?? [0, 1]);
  }
  return onset;
}

const spoken = (pitch: string) => pitchName(pitch)?.spoken ?? pitch;

/** El evento, para decirlo: «Re 4», «el silencio de negra». */
function eventWord(event: ScoreEventPayload): string {
  return event.kind === "note" && event.pitch
    ? spoken(event.pitch)
    : `el silencio de ${durationName(event.duration_beats)}`;
}

const span = (from: number, until: number) =>
  from === until
    ? `en el compás ${String(from)}`
    : `de los compases ${String(from)} a ${String(until)}`;

// --- Articulaciones y calderón --------------------------------------------------------------

const ORDER: readonly ArticulationValue[] = ARTICULATIONS.map(({ value }) => value);

/** Las marcas de nota de un evento, como las escribe `SetNoteMarks`. */
export function noteMarksOf(event: ScoreEventPayload): {
  articulations: ArticulationValue[];
  fermata: boolean;
} {
  const own = event.articulations ?? [];
  return {
    articulations: ORDER.filter((value) => own.includes(value)),
    fermata: event.fermata === true,
  };
}

/** El nombre de una articulación para decirlo: «acento». */
export const articulationWord = (value: string) =>
  ARTICULATIONS.find((candidate) => candidate.value === value)?.spoken ?? value;

/**
 * Poner o quitar una articulación o el calderón del evento elegido (`SetNoteMarks`, con el valor
 * final: todas sus articulaciones y su calderón). En un acorde, en su primera nota. Un silencio
 * solo lleva calderón.
 */
function planNoteMark(
  command: Extract<MarkCommand, { kind: "articulation" | "fermata" }>,
  target: EditTarget,
  score: ScoreIRPayload,
): EditPlan {
  const holder = marksHolder(score, target.anchor);
  if (!holder) return refuse("no-target", "Elige primero una nota o un silencio.");
  const current = noteMarksOf(holder.event);
  let after: { articulations: ArticulationValue[]; fermata: boolean };
  let change: string;
  if (command.kind === "fermata") {
    // Un silencio no lleva articulaciones: si las trae de la importación, se le quitan.
    after = {
      articulations: holder.event.kind === "note" ? current.articulations : [],
      fermata: !current.fermata,
    };
    change = `${after.fermata ? "calderón en" : "sin calderón en"} ${eventWord(holder.event)}`;
  } else {
    if (holder.event.kind !== "note") {
      return refuse("rest", "Un silencio solo lleva calderón, no articulaciones.");
    }
    const has = current.articulations.includes(command.articulation);
    after = {
      ...current,
      articulations: ORDER.filter((value) =>
        value === command.articulation ? !has : current.articulations.includes(value),
      ),
    };
    change = `${has ? "sin " : ""}${articulationWord(command.articulation)} en ${eventWord(holder.event)}`;
  }
  return { kind: "edit", op: "SetNoteMarks", after, anchor: holder.anchor, change };
}

// --- Dinámicas ------------------------------------------------------------------------------

/** La dinámica de la posición del evento elegido (la de su ataque en su compás), o null. */
export function dynamicAt(score: ScoreIRPayload, anchor: AnchorPayload): DynamicValue | null {
  const onset = onsetOf(score, anchor);
  const measure = measureOf(score, anchor);
  if (!onset || !measure) return null;
  return (measure.dynamics ?? []).find((d) => sameBeats(d.offset_beats, onset))?.mark ?? null;
}

/**
 * Poner, cambiar o quitar la dinámica en la posición del evento elegido (`SetDynamic`): el ataque
 * del evento en su compás. Es una posición del compás (ADR-0031), anclada como la clave y la
 * armadura a su primer evento (ADR-0010).
 */
function planDynamicAt(
  mark: DynamicValue | null,
  place: MeasurePlace,
  offset: Beats,
  who: string,
  score: ScoreIRPayload,
): EditPlan {
  const measure = measureOf(score, place);
  if (!measure) return refuse("no-target", "Elige primero una nota o un silencio.");
  const dynamics = (measure.dynamics ?? []).filter((d) => sameBeats(d.offset_beats, offset));
  const current = dynamics[0]?.mark ?? null;
  if (current === mark && dynamics.length <= 1) {
    return refuse("same", mark ? `${who} ya tiene esa dinámica.` : `${who} no tiene dinámica.`);
  }
  const at = `${who === "La nota" ? "la nota" : who.toLowerCase()} del compás ${String(measure.number)}`;
  return {
    kind: "edit",
    op: "SetDynamic",
    after: { offset_beats: beatsText(offset), mark },
    place: { part: place.part, staff: place.staff, measure: measure.number },
    anchor: measureAnchor(score, place, measure),
    change: mark ? `dinámica ${mark} en ${at}` : `sin la dinámica ${current ?? ""} en ${at}`,
  };
}

function planDynamic(mark: DynamicValue | null, target: EditTarget, score: ScoreIRPayload) {
  const onset = onsetOf(score, target.anchor);
  if (!onset) return refuse("no-target", "Elige primero una nota o un silencio.");
  const who = target.event.kind === "note" ? "La nota" : "El silencio";
  return planDynamicAt(mark, target.anchor, onset, who, score);
}

// --- Ligaduras de expresión y reguladores ---------------------------------------------------

/** Una ligadura o un regulador de la parte, con dónde están sus extremos. */
export interface SpanInfo {
  mark: "slur" | "wedge";
  number: number;
  /** Ligadura, crescendo o diminuendo; null si solo queda el fin de un regulador. */
  kind: SpanKind | null;
  /** Compás del inicio y del fin, o null si ese extremo no está (un huérfano, ADR-0031 §5). */
  from: number | null;
  until: number | null;
}

/** Nombre de una ligadura o un regulador: «la ligadura de expresión de los compases 2 a 3». */
export function spanName(info: SpanInfo): string {
  const name =
    info.kind === "crescendo"
      ? "el crescendo"
      : info.kind === "diminuendo"
        ? "el diminuendo"
        : info.mark === "slur"
          ? "la ligadura de expresión"
          : "el regulador";
  if (info.from === null || info.until === null) {
    const lone = info.from ?? info.until ?? 0;
    return `${name} sin ${info.from === null ? "inicio" : "fin"} del compás ${String(lone)}`;
  }
  return `${name} ${span(info.from, info.until)}`;
}

interface SlurEnd {
  type: "start" | "stop";
  anchor: AnchorPayload;
}

/** Los extremos de ligadura de expresión de una parte, por número. */
function slurEnds(score: ScoreIRPayload, part: number): Map<number, SlurEnd[]> {
  const ends = new Map<number, SlurEnd[]>();
  for (const [staffIndex, staff] of (score.parts[part]?.staves ?? []).entries()) {
    for (const measure of staff.measures) {
      const counters = new Map<number, number>();
      for (const event of measure.events) {
        const index = counters.get(event.voice) ?? 0;
        counters.set(event.voice, index + 1);
        for (const slur of event.slurs ?? []) {
          const anchor: AnchorPayload = {
            part,
            staff: staffIndex,
            measure: measure.number,
            voice: event.voice,
            event_index: index,
            staff_id: staff.id,
            bbox: event.bbox,
            confidence: event.confidence,
          };
          ends.set(slur.number, [...(ends.get(slur.number) ?? []), { type: slur.type, anchor }]);
        }
      }
    }
  }
  return ends;
}

interface WedgeEnd {
  type: "crescendo" | "diminuendo" | "stop";
  staff: number;
  measure: number;
  offset: Beats;
}

/** Los extremos de regulador de una parte, por número. */
function wedgeEnds(score: ScoreIRPayload, part: number): Map<number, WedgeEnd[]> {
  const ends = new Map<number, WedgeEnd[]>();
  for (const [staffIndex, staff] of (score.parts[part]?.staves ?? []).entries()) {
    for (const measure of staff.measures) {
      for (const wedge of measure.wedges ?? []) {
        const offset = parseBeats(wedge.offset_beats) ?? [0, 1];
        const end = { type: wedge.type, staff: staffIndex, measure: measure.number, offset };
        ends.set(wedge.number, [...(ends.get(wedge.number) ?? []), end]);
      }
    }
  }
  return ends;
}

const nextNumber = (numbers: Iterable<number>) => Math.max(0, ...numbers) + 1;

function slurInfo(number: number, ends: readonly SlurEnd[]): SpanInfo {
  const start = ends.find((end) => end.type === "start");
  const stop = ends.find((end) => end.type === "stop");
  return {
    mark: "slur",
    number,
    kind: "slur",
    from: start?.anchor.measure ?? null,
    until: stop?.anchor.measure ?? null,
  };
}

function wedgeInfo(number: number, ends: readonly WedgeEnd[]): SpanInfo {
  const start = ends.find((end) => end.type !== "stop");
  const stop = ends.find((end) => end.type === "stop");
  return {
    mark: "wedge",
    number,
    kind: start && start.type !== "stop" ? start.type : null,
    from: start?.measure ?? null,
    until: stop?.measure ?? null,
  };
}

/** Si una posición (compás, ataque) va antes que otra. */
const before = (a: { measure: number; offset: Beats }, b: { measure: number; offset: Beats }) =>
  a.measure !== b.measure ? a.measure < b.measure : compare(a.offset, b.offset) < 0;

/**
 * Las ligaduras y los reguladores que se pueden quitar desde el evento elegido: las ligaduras que
 * empiezan o acaban en él (en un acorde, en su primera nota) y los reguladores de su pentagrama
 * que cubren su posición o tienen un extremo suelto en su compás.
 */
export function spansAt(score: ScoreIRPayload, anchor: AnchorPayload): SpanInfo[] {
  const holder = marksHolder(score, anchor);
  const onset = onsetOf(score, anchor);
  if (!holder || !onset) return [];
  const slurs = slurEnds(score, anchor.part);
  const found: SpanInfo[] = [...new Set((holder.event.slurs ?? []).map(({ number }) => number))]
    .sort((a, b) => a - b)
    .map((number) => slurInfo(number, slurs.get(number) ?? []));
  const here = { measure: anchor.measure, offset: onset };
  for (const [number, ends] of [...wedgeEnds(score, anchor.part)].sort(([a], [b]) => a - b)) {
    const start = ends.find((end) => end.type !== "stop");
    const stop = ends.find((end) => end.type === "stop");
    const covers =
      start && stop
        ? start.staff === anchor.staff && !before(here, start) && !before(stop, here)
        : ends.some((end) => end.staff === anchor.staff && end.measure === anchor.measure);
    if (covers) found.push(wedgeInfo(number, ends));
  }
  return found;
}

/** Hueco de una ligadura en `SetSlur`: pentagrama, compás, voz y posición en la voz. */
const slurSlot = (anchor: AnchorPayload) => ({
  staff: anchor.staff,
  measure: anchor.measure,
  voice: anchor.voice,
  event_index: anchor.event_index,
});

const SPAN_NAMES: Record<SpanKind, string> = {
  slur: "ligadura de expresión",
  crescendo: "crescendo",
  diminuendo: "diminuendo",
};

/**
 * Crear una ligadura de expresión o un regulador desde el inicio marcado (`origin`, en el estado
 * que se ve) hasta el evento elegido (`SetSlur`, `SetWedge`), en el orden en que suenan: elegir
 * antes el final que el inicio da lo mismo. Con un `number` libre en la parte (el siguiente al
 * mayor, ADR-0031). Una ligadura une dos notas distintas; un regulador va del ataque del primer
 * evento al final del último, también de uno solo.
 */
function planSpan(
  kind: SpanKind,
  origin: AnchorPayload | null,
  target: EditTarget,
  score: ScoreIRPayload,
): EditPlan {
  if (!origin) {
    return refuse(
      "no-origin",
      "Marca antes el inicio: elige la primera nota, pulsa «Inicio» (I) y después elige la última.",
    );
  }
  const first = marksHolder(score, origin);
  const last = marksHolder(score, target.anchor);
  const firstOnset = onsetOf(score, origin);
  const lastOnset = onsetOf(score, target.anchor);
  if (!first || !last || !firstOnset || !lastOnset) {
    return refuse("no-origin", "La nota de inicio ya no está: márcala de nuevo.");
  }
  if (first.anchor.part !== last.anchor.part) {
    return refuse("span", "El inicio y el final tienen que ser de la misma parte.");
  }
  const part = first.anchor.part;
  const a = { ...first, measure: first.anchor.measure, offset: firstOnset };
  const b = { ...last, measure: last.anchor.measure, offset: lastOnset };
  const sameSpot = !before(a, b) && !before(b, a);
  if (kind === "slur") {
    if (first.event.kind !== "note" || last.event.kind !== "note") {
      return refuse("span", "Una ligadura de expresión une notas, no silencios.");
    }
    const sameLane =
      a.anchor.staff === b.anchor.staff &&
      a.anchor.measure === b.anchor.measure &&
      a.anchor.voice === b.anchor.voice;
    if (sameSpot && (!sameLane || a.anchor.event_index === b.anchor.event_index)) {
      return refuse(
        "span",
        "Elige como final otra nota, después o antes del inicio: una ligadura une dos notas.",
      );
    }
    // A la vez en la misma voz: una nota de adorno y su nota.
    const [start, stop] =
      before(b, a) || (sameSpot && b.anchor.event_index < a.anchor.event_index) ? [b, a] : [a, b];
    const number = nextNumber(slurEnds(score, part).keys());
    return {
      kind: "edit",
      op: "SetSlur",
      after: { number, start: slurSlot(start.anchor), stop: slurSlot(stop.anchor) },
      span: { kind, from: origin, to: target.anchor },
      anchor: start.anchor,
      change: `ligadura de expresión ${span(start.measure, stop.measure)}`,
    };
  }
  const [start, stop] = before(b, a) ? [b, a] : [a, b];
  const end = add(stop.offset, parseBeats(stop.event.duration_beats) ?? [0, 1]);
  if (start.measure === stop.measure && compare(end, start.offset) <= 0) {
    return refuse(
      "span",
      "Un regulador necesita durar: elige como final una nota con duración o después del inicio.",
    );
  }
  const number = nextNumber(wedgeEnds(score, part).keys());
  const startMeasure = measureOf(score, start.anchor);
  if (!startMeasure) return refuse("no-target", "Elige primero una nota o un silencio.");
  return {
    kind: "edit",
    op: "SetWedge",
    after: {
      number,
      start: {
        staff: start.anchor.staff,
        measure: start.measure,
        offset_beats: beatsText(start.offset),
        type: kind,
      },
      stop: { staff: stop.anchor.staff, measure: stop.measure, offset_beats: beatsText(end) },
    },
    span: { kind, from: origin, to: target.anchor },
    anchor: measureAnchor(score, start.anchor, startMeasure),
    change: `${SPAN_NAMES[kind]} ${span(start.measure, stop.measure)}`,
  };
}

/**
 * Quitar una ligadura de expresión o un regulador de la parte por su número: sus dos extremos o
 * el que quede (`{"start": null, "stop": null}`). Anclada al inicio (o, sin él, al fin): la
 * ligadura en su evento, el regulador en su compás.
 */
export function planUnspan(
  mark: "slur" | "wedge",
  number: number,
  part: number,
  score: ScoreIRPayload,
): EditPlan {
  const after = { number, start: null, stop: null };
  if (mark === "slur") {
    const ends = slurEnds(score, part).get(number) ?? [];
    const first = ends.find((end) => end.type === "start") ?? ends[0];
    if (!first) return refuse("same", "Esa ligadura de expresión ya no está.");
    const name = spanName(slurInfo(number, ends));
    return {
      kind: "edit",
      op: "SetSlur",
      after,
      remove: { mark, number, part, name },
      anchor: first.anchor,
      change: `quitar ${name}`,
    };
  }
  const ends = wedgeEnds(score, part).get(number) ?? [];
  const first = ends.find((end) => end.type !== "stop") ?? ends[0];
  const place = first ? { part, staff: first.staff, measure: first.measure } : null;
  const measure = place ? measureOf(score, place) : null;
  if (!place || !measure) return refuse("same", "Ese regulador ya no está.");
  const name = spanName(wedgeInfo(number, ends));
  return {
    kind: "edit",
    op: "SetWedge",
    after,
    remove: { mark, number, part, name },
    anchor: measureAnchor(score, place, measure),
    change: `quitar ${name}`,
  };
}

/** Edición que pide una orden sobre las marcas del evento elegido en el estado `score`. */
export function planMark(
  command: MarkCommand,
  target: EditTarget | null,
  score: ScoreIRPayload,
  origin: AnchorPayload | null,
): EditPlan {
  if (command.kind === "unspan") {
    return target
      ? planUnspan(command.mark, command.number, target.anchor.part, score)
      : refuse("no-target", "Elige primero una nota o un silencio.");
  }
  if (!target) return refuse("no-target", "Elige primero una nota o un silencio.");
  switch (command.kind) {
    case "articulation":
    case "fermata":
      return planNoteMark(command, target, score);
    case "dynamic":
      return planDynamic(command.mark, target, score);
    case "span":
      return planSpan(command.span, origin, target, score);
  }
}

/**
 * Tras un 409, la misma edición de marcas sobre el estado recargado (ADR-0011: el cliente
 * recarga y reconstruye la edición). `carry` lleva un ancla del estado en que se pidió al
 * recargado, o da null si su evento ya no está. Las marcas de nota piden el mismo valor final; la
 * dinámica, la misma posición; una ligadura o un regulador nuevos, los mismos extremos con otro
 * número libre; quitar uno, el mismo número si sigue.
 */
export function replanMark(
  edit: MarkDecision,
  anchor: AnchorPayload,
  score: ScoreIRPayload,
  carry: (anchor: AnchorPayload) => AnchorPayload | null,
): { plan: EditPlan; anchor: AnchorPayload | null } {
  if (edit.op === "SetDynamic") {
    const offset = parseBeats(edit.after.offset_beats) ?? [0, 1];
    return {
      plan: planDynamicAt(edit.after.mark, edit.place, offset, "La posición", score),
      anchor,
    };
  }
  if ("remove" in edit) {
    const { mark, number, part, name } = edit.remove;
    const plan = planUnspan(mark, number, part, score);
    // Un número libre se puede volver a usar: si ya es otra marca, no se quita.
    if (plan.kind === "edit" && "remove" in plan && plan.remove.name !== name) {
      return { plan: refuse("same", `Ya no está ${name}: elígela de nuevo.`), anchor: null };
    }
    return { plan, anchor };
  }
  if ("span" in edit) {
    const from = carry(edit.span.from);
    const to = carry(edit.span.to);
    const found = to ? marksHolder(score, to) : null;
    if (!from || !to || !found) {
      return {
        plan: refuse("no-origin", "Una de las notas ya no está en el mismo sitio."),
        anchor: null,
      };
    }
    const target: EditTarget = { anchor: to, event: found.event, chord: false };
    return { plan: planSpan(edit.span.kind, from, target, score), anchor: to };
  }
  const carried = carry(anchor);
  const holder = carried ? marksHolder(score, carried) : null;
  if (!carried || !holder) {
    return { plan: refuse("no-target", "Elige primero una nota o un silencio."), anchor: null };
  }
  const current = noteMarksOf(holder.event);
  if (
    current.fermata === edit.after.fermata &&
    current.articulations.join() === edit.after.articulations.join()
  ) {
    return { plan: refuse("same", "La nota ya tiene esas marcas."), anchor: carried };
  }
  return {
    plan: {
      kind: "edit",
      op: "SetNoteMarks",
      after: edit.after,
      anchor: holder.anchor,
      change: `${describeMarkEdit("SetNoteMarks", current, edit.after)} en ${eventWord(holder.event)}`,
    },
    anchor: carried,
  };
}

// --- Para decir una edición del log ---------------------------------------------------------

const record = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;

const words = (values: unknown): string[] =>
  Array.isArray(values) ? values.map((value) => articulationWord(String(value))) : [];

const list = (items: readonly string[]) =>
  items.length <= 1
    ? (items[0] ?? "")
    : `${items.slice(0, -1).join(", ")} y ${String(items.at(-1))}`;

/** Qué hace una edición de marcas del log: «acento», «sin picado», «dinámica mf». */
export function describeMarkEdit(op: string, beforeValue: unknown, afterValue: unknown): string {
  const after = record(afterValue) ?? {};
  const previous = record(beforeValue);
  switch (op) {
    case "SetNoteMarks": {
      const now = words(after.articulations);
      const then = words(previous?.articulations);
      const added = now.filter((word) => !then.includes(word));
      const removed = then.filter((word) => !now.includes(word));
      if (after.fermata === true && previous?.fermata !== true) added.push("calderón");
      if (after.fermata !== true && previous?.fermata === true) removed.push("calderón");
      if (!previous) {
        const all = [...now, ...(after.fermata === true ? ["calderón"] : [])];
        return all.length ? `marcas: ${list(all)}` : "sin articulaciones ni calderón";
      }
      const parts = [...added, ...removed.map((word) => `sin ${word}`)];
      return parts.length ? list(parts) : "marcas sin cambios";
    }
    case "SetDynamic": {
      const mark = typeof after.mark === "string" ? after.mark : null;
      const old = typeof previous?.mark === "string" ? previous.mark : null;
      if (mark) return `dinámica ${mark}`;
      return old ? `sin la dinámica ${old}` : "sin dinámica";
    }
    case "SetSlur":
    case "SetWedge": {
      const mark = op === "SetSlur" ? "slur" : "wedge";
      const ends = after.start === null && after.stop === null ? previous : after;
      const start = record(ends?.start);
      const stop = record(ends?.stop);
      const type = typeof start?.type === "string" ? start.type : null;
      const info: SpanInfo = {
        mark,
        number: Number(after.number),
        kind:
          mark === "slur" ? "slur" : type === "crescendo" || type === "diminuendo" ? type : null,
        from: start ? Number(start.measure) : null,
        until: stop ? Number(stop.measure) : null,
      };
      if (ends === previous) {
        // Sin el estado previo no se sabe qué se quitó.
        return previous
          ? `quitar ${spanName(info)}`
          : `quitar ${mark === "slur" ? "una ligadura de expresión" : "un regulador"}`;
      }
      return spanName(info).replace(/^(la|el) /, "");
    }
    default:
      return op;
  }
}

/** Si el `before` de una edición de marcas basta para deshacerla (`has_complete_before`). */
export function hasCompleteMarkBefore(op: string, beforeValue: unknown): boolean {
  const before = record(beforeValue);
  if (!before) return false;
  const has = (...keys: string[]) => keys.every((key) => key in before);
  switch (op) {
    case "SetNoteMarks":
      return has("articulations", "fermata");
    case "SetDynamic":
      return has("offset_beats", "mark");
    case "SetSlur":
    case "SetWedge":
      return has("number", "start", "stop");
    default:
      return false;
  }
}

/** Operaciones de marcas (ADR-0039): no mueven ningún evento. */
export const MARK_OPS: readonly string[] = ["SetNoteMarks", "SetDynamic", "SetWedge", "SetSlur"];
