import type {
  AnchorPayload,
  MeasurePayload,
  ScoreEventPayload,
  ScoreIRPayload,
  TimeSignaturePayload,
} from "../../types";
import type { EditPlan, EditTarget, MeasurePlace } from "./edits";
import { chordStart, measureAnchor, voiceEvents } from "./markEdits";

/**
 * Cambiar el compás y poner o quitar tresillos desde la barra de corrección (#241, ADR-0048), con
 * las operaciones de ADR-0044: `SetTime` cambia la indicación de compás desde el compás elegido
 * hasta el siguiente cambio, en todos los pentagramas de todas las partes (#326); `SetTuplet` pone o quita el
 * tresillo de 3:2 a varios eventos seguidos de una voz con una sola edición. Qué edición pide
 * cada orden, en el vocabulario del contrato. Nada se da por guardado: lo decide el servidor.
 */

/** Símbolo con que se escribe una indicación de compás: C (4/4) o ¢ (2/2). */
export type TimeSymbol = NonNullable<TimeSignaturePayload["symbol"]>;

/** Una indicación de compás, con su grafía: con números o con su símbolo. */
export interface TimeChoice {
  beats: number;
  beat_type: number;
  symbol: TimeSymbol | null;
}

/** Las indicaciones que se ofrecen: el símbolo primero, después las de numerador 2, 3, 4… */
export const TIME_SIGNATURES: readonly TimeChoice[] = [
  { beats: 4, beat_type: 4, symbol: "common" },
  { beats: 2, beat_type: 2, symbol: "cut" },
  { beats: 2, beat_type: 4, symbol: null },
  { beats: 3, beat_type: 4, symbol: null },
  { beats: 4, beat_type: 4, symbol: null },
  { beats: 5, beat_type: 4, symbol: null },
  { beats: 6, beat_type: 4, symbol: null },
  { beats: 2, beat_type: 2, symbol: null },
  { beats: 3, beat_type: 2, symbol: null },
  { beats: 4, beat_type: 2, symbol: null },
  { beats: 3, beat_type: 8, symbol: null },
  { beats: 5, beat_type: 8, symbol: null },
  { beats: 6, beat_type: 8, symbol: null },
  { beats: 7, beat_type: 8, symbol: null },
  { beats: 9, beat_type: 8, symbol: null },
  { beats: 12, beat_type: 8, symbol: null },
];

const SYMBOL_METERS: Record<TimeSymbol, readonly [number, number]> = {
  common: [4, 4],
  cut: [2, 2],
};
const SYMBOL_SIGNS: Record<TimeSymbol, string> = { common: "C", cut: "¢" };

/** La indicación de un compás como se elige: sin símbolo si no lo lleva o no es el de su métrica. */
export function timeChoiceOf(signature: TimeSignaturePayload): TimeChoice {
  const symbol = signature.symbol ?? null;
  const meter = symbol ? SYMBOL_METERS[symbol] : null;
  const valid = meter?.[0] === signature.beats && meter[1] === signature.beat_type;
  return {
    beats: signature.beats,
    beat_type: signature.beat_type,
    symbol: valid ? symbol : null,
  };
}

/** Cómo se dice una indicación: «C», «¢», «3/4». */
export const timeName = (choice: TimeChoice) =>
  choice.symbol
    ? SYMBOL_SIGNS[choice.symbol]
    : `${String(choice.beats)}/${String(choice.beat_type)}`;

/** Cómo se elige en el desplegable: «C (4/4)», «¢ (2/2)», «3/4». */
export const timeLabel = (choice: TimeChoice) =>
  choice.symbol
    ? `${SYMBOL_SIGNS[choice.symbol]} (${String(choice.beats)}/${String(choice.beat_type)})`
    : timeName(choice);

/** Clave de una indicación en el desplegable: «4/4:common», «3/4». */
export const timeKey = (choice: TimeChoice) =>
  `${String(choice.beats)}/${String(choice.beat_type)}${choice.symbol ? `:${choice.symbol}` : ""}`;

/** Misma métrica y misma grafía (`same_time_notation` en el servidor); ninguna es igual a ninguna. */
function sameTime(a: TimeSignaturePayload | null, b: TimeSignaturePayload | null): boolean {
  if (a === null || b === null) return a === null && b === null;
  return (
    a.beats === b.beats && a.beat_type === b.beat_type && (a.symbol ?? null) === (b.symbol ?? null)
  );
}

/** La indicación vigente al empezar el compás `index`: la del último anterior que la lleva. */
function effectiveBefore(measures: readonly MeasurePayload[], index: number) {
  for (const measure of measures.slice(0, index).reverse()) {
    if (measure.time_signature) return measure.time_signature;
  }
  return null;
}

/**
 * Cuántos compases, desde `index`, llevan la indicación vigente en él o ninguna: hasta el
 * siguiente cambio (`_run_length` en el servidor). La importación da a cada compás su métrica, así
 * que el tramo son los compases seguidos que llevan la misma.
 */
function runLength(measures: readonly MeasurePayload[], index: number): number {
  const current = measures[index]?.time_signature ?? effectiveBefore(measures, index);
  let length = 1;
  for (const measure of measures.slice(index + 1)) {
    const signature = measure.time_signature ?? null;
    if (signature !== null && !sameTime(signature, current)) break;
    length += 1;
  }
  return length;
}

/**
 * Lo de una parte en el compás `number`: la indicación que rige en él, hasta dónde llega su tramo y
 * si sus pentagramas no llevan la misma ahí o no cambian en los mismos compases (`uneven`: el
 * servidor lo rechazaría, ADR-0044 §2). Null si ningún pentagrama de la parte tiene el compás.
 */
function partScope(
  staves: readonly { measures: readonly MeasurePayload[] }[],
  number: number,
  ownStaff: number,
): {
  measure: MeasurePayload;
  current: TimeSignaturePayload | null;
  until: number;
  uneven: boolean;
} | null {
  const present = staves
    .map((staff, index) => ({
      index,
      measures: staff.measures,
      position: staff.measures.findIndex((candidate) => candidate.number === number),
    }))
    .filter((staff) => staff.position >= 0);
  const own = present.find((staff) => staff.index === ownStaff) ?? present[0];
  const measure = own?.measures[own.position];
  if (!own || !measure) return null;
  const run = runLength(own.measures, own.position);
  const uneven = present.some(
    (staff) =>
      !sameTime(
        staff.measures[staff.position]?.time_signature ?? null,
        measure.time_signature ?? null,
      ) || runLength(staff.measures, staff.position) !== run,
  );
  return {
    measure,
    current: measure.time_signature ?? effectiveBefore(own.measures, own.position),
    until: own.measures[own.position + run - 1]?.number ?? measure.number,
    uneven,
  };
}

/**
 * La indicación de compás que rige el compás elegido y hasta dónde llegaría una nueva puesta en
 * él: el tramo de su parte. El compás se cambia en todas las partes (#326, enmienda de ADR-0044 y
 * ADR-0048): `uneven` si los pentagramas de alguna parte no llevan la misma en ese compás o no
 * cambian en los mismos compases; `currents`, la que rige en cada parte que tiene el compás. Si la
 * parte elegida no lleva ninguna (una sesión con el compás puesto en otra parte antes de #326),
 * rige la de otra parte, que es la que dibuja la partitura y la que usa el mapa de tiempos.
 */
function timeScope(
  score: ScoreIRPayload,
  place: MeasurePlace,
): {
  measure: MeasurePayload;
  current: TimeSignaturePayload | null;
  currents: (TimeSignaturePayload | null)[];
  from: number;
  until: number;
  uneven: boolean;
} | null {
  const staves = score.parts[place.part]?.staves ?? [];
  const index = (staves[place.staff]?.measures ?? []).findIndex(
    (candidate) => candidate.number === place.measure,
  );
  if (index < 0) return null;
  const own = partScope(staves, place.measure, place.staff);
  if (!own) return null;
  const others = score.parts.map((part, number) =>
    number === place.part ? own : partScope(part.staves, place.measure, 0),
  );
  const present = others.filter((scope) => scope !== null);
  return {
    measure: own.measure,
    current: own.current ?? present.find((scope) => scope.current !== null)?.current ?? null,
    currents: present.map((scope) => scope.current),
    from: own.measure.number,
    until: own.until,
    uneven: present.some((scope) => scope.uneven),
  };
}

/** La indicación de compás que rige el compás elegido, como se elige, o null si no hay ninguna. */
export function activeTime(score: ScoreIRPayload, place: MeasurePlace): TimeChoice | null {
  const current = timeScope(score, place)?.current ?? null;
  return current ? timeChoiceOf(current) : null;
}

/** Compases a los que llega un compás puesto en el compás elegido, o null si no está. */
export function timeRange(
  score: ScoreIRPayload,
  place: MeasurePlace,
): { from: number; until: number } | null {
  const found = timeScope(score, place);
  return found ? { from: found.from, until: found.until } : null;
}

const span = (from: number, until: number) =>
  from === until
    ? `en el compás ${String(from)}`
    : `en los compases ${String(from)} a ${String(until)}`;

/** Lo que conviene saber al cambiar el compás: SetTime no toca las figuras (ADR-0044 §2). */
const KEEPS_FIGURES = "Las figuras no cambian: revalida para ver los compases que no cuadran.";

/** Lo que guarda una edición de compás o de tresillo para volver a pedirla tras un 409. */
export type MeterDecision =
  | {
      op: "SetTime";
      after: { time_signature: TimeSignaturePayload; all_parts: true };
      /** La indicación elegida: el tramo depende del estado. */
      time: TimeChoice;
    }
  | {
      op: "SetTuplet";
      after: { durations: (string | null)[] };
      tuplet: {
        scope: TupletScope;
        /** Si lo pone (o lo quita). */
        put: boolean;
        /** El evento elegido al darla, en el estado en que se pidió. */
        chosen: AnchorPayload;
        /** El inicio marcado, si va desde él. */
        from: AnchorPayload | null;
      };
    };

const refuse = (message: string, reason: "meter" | "same" | "no-target" = "meter"): EditPlan => ({
  kind: "refused",
  reason,
  message,
});

const NO_TARGET = "Elige primero una nota o un silencio.";

/**
 * Cambiar la indicación de compás desde el compás elegido (`SetTime`, ADR-0044 §2): hasta el
 * siguiente cambio, en todos los pentagramas de todas las partes (`all_parts`, #326), con una sola
 * edición que se deshace de un paso. Anclada al primer evento del compás, como la armadura
 * (ADR-0033). Las figuras no cambian: el validador señala después los compases que no cuadran.
 * Para quitar un cambio se pone la indicación del compás anterior. Si las partes llevaban compases
 * distintos en ese compás, se dice al guardar: ahora todas llevan el mismo.
 */
export function planTime(
  choice: TimeChoice,
  place: MeasurePlace | null,
  score: ScoreIRPayload,
): EditPlan {
  const found = place ? timeScope(score, place) : null;
  if (!place || !found) return refuse(NO_TARGET, "no-target");
  const signature: TimeSignaturePayload = {
    beats: choice.beats,
    beat_type: choice.beat_type,
    ...(choice.symbol ? { symbol: choice.symbol } : {}),
  };
  const chosen = { ...signature, symbol: choice.symbol };
  if (found.currents.every((current) => sameTime(current, chosen))) {
    return refuse("El compás ya tiene esa indicación.", "same");
  }
  if (found.uneven) {
    return refuse(
      "Los pentagramas de una parte no llevan el mismo compás desde aquí: no se puede cambiar desde la vista.",
    );
  }
  const several = score.parts.length > 1;
  const mixed = found.currents.some((current) => !sameTime(current, found.currents[0] ?? null));
  return {
    kind: "edit",
    op: "SetTime",
    after: { time_signature: signature, all_parts: true },
    time: choice,
    anchor: measureAnchor(score, place, found.measure),
    change: `compás ${timeName(choice)} ${span(found.from, found.until)}${several ? ", en todas las partes" : ""}`,
    notice: mixed
      ? `Las partes no llevaban el mismo compás: ahora todas llevan ${timeName(choice)}. ${KEEPS_FIGURES}`
      : KEEPS_FIGURES,
  };
}

// --- Tresillos --------------------------------------------------------------------------------

/**
 * A qué eventos se pone o se quita el tresillo: tres figuras desde la elegida (o el grupo de tres
 * de la elegida, si ya lo lleva), todas las de su voz en el compás, o las que van del inicio
 * marcado a la elegida.
 */
export type TupletScope = "group" | "measure" | "range";

export interface TupletCommand {
  kind: "tuplet";
  scope: TupletScope;
}

type Fraction = readonly [number, number];

function gcd(a: number, b: number): number {
  return b === 0 ? Math.abs(a) : gcd(b, a % b);
}

function reduce([numerator, denominator]: Fraction): Fraction {
  const divisor = gcd(numerator, denominator) || 1;
  return [numerator / divisor, denominator / divisor];
}

function parseBeats(beats: string | null | undefined): Fraction | null {
  const match =
    beats === null || beats === undefined ? null : /^\s*(\d+)(?:\s*\/\s*(\d+))?\s*$/.exec(beats);
  if (!match) return null;
  const denominator = Number(match[2] ?? 1);
  const value = reduce([Number(match[1]), denominator]);
  return denominator === 0 || value[0] <= 0 ? null : value;
}

const text = ([numerator, denominator]: Fraction) =>
  denominator === 1 ? String(numerator) : `${String(numerator)}/${String(denominator)}`;

/** Si una figura lleva el tresillo: un 3 en el denominador (`_has_triplet` en el servidor). */
export function hasTriplet(beats: string | null | undefined): boolean {
  const value = parseBeats(beats);
  return value !== null && value[1] % 3 === 0;
}

/**
 * Si el servidor admite la duración (ADR-0017): como mucho 16 negras, con denominador 2^a·t
 * (t ∈ {1, 3, 5, 7}) de hasta 128.
 */
function admissible([numerator, denominator]: Fraction): boolean {
  if (numerator <= 0 || numerator > 16 * denominator || denominator > 128) return false;
  let odd = denominator;
  while (odd % 2 === 0) odd /= 2;
  return [1, 3, 5, 7].includes(odd);
}

/** Las posiciones de la voz que empiezan un ataque: lo que no es nota de un acorde ya empezado. */
function heads(events: readonly ScoreEventPayload[]): number[] {
  return events
    .map((_event, index) => index)
    .filter((index) => chordStart(events, index) === index);
}

/** Posición siguiente a la última nota del acorde que empieza en `head`. */
function chordEnd(events: readonly ScoreEventPayload[], head: number): number {
  let end = head + 1;
  while (end < events.length && chordStart(events, end) === head) end += 1;
  return end;
}

/** Si el evento ocupa tiempo: una nota de adorno no (ADR-0028). */
const timed = (event: ScoreEventPayload | undefined) => parseBeats(event?.duration_beats) !== null;

/** Un silencio invisible: el hueco de una voz (ADR-0032), que no es una figura que se vea. */
const isHidden = (event: ScoreEventPayload | undefined) => event?.hidden === true;

/** Si es una figura que cuenta para el tresillo: ocupa tiempo y se ve. */
const figure = (event: ScoreEventPayload | undefined) => timed(event) && !isHidden(event);

/** Tramo `[start, end)` de la voz y si ya lleva el tresillo (todo), no (nada) o en parte. */
interface Stretch {
  start: number;
  end: number;
}

function tripletState(events: readonly ScoreEventPayload[], { start, end }: Stretch) {
  const values = events.slice(start, end).filter(figure);
  const triplets = values.filter((event) => hasTriplet(event.duration_beats)).length;
  if (values.length === 0) return "empty" as const;
  return triplets === 0
    ? ("none" as const)
    : triplets === values.length
      ? ("all" as const)
      : ("mixed" as const);
}

/** Tres ataques con duración desde `from` (un acorde es uno; las notas de adorno no cuentan). */
function threeFrom(events: readonly ScoreEventPayload[], from: number): Stretch | null {
  let counted = 0;
  for (const head of heads(events).filter((index) => index >= from)) {
    if (figure(events[head])) counted += 1;
    if (counted === 3) return { start: from, end: chordEnd(events, head) };
  }
  return null;
}

/**
 * El grupo de tres de la figura con tresillo `head`: los ataques seguidos con tresillo en que
 * está, de tres en tres desde el primero (el último grupo puede quedar más corto).
 */
function groupOf(events: readonly ScoreEventPayload[], head: number): Stretch {
  const all = heads(events);
  // La racha: los ataques seguidos con tresillo; una nota de adorno no la corta, un hueco sí.
  const inRun = (index: number | undefined) => {
    const event = index === undefined ? undefined : events[index];
    return (
      event !== undefined && (!timed(event) || (figure(event) && hasTriplet(event.duration_beats)))
    );
  };
  const position = all.indexOf(head);
  let first = position;
  while (first > 0 && inRun(all[first - 1])) first -= 1;
  let last = position;
  while (last < all.length - 1 && inRun(all[last + 1])) last += 1;
  const figures = all.slice(first, last + 1).filter((index) => figure(events[index]));
  const group = Math.floor(figures.indexOf(head) / 3) * 3;
  const members = figures.slice(group, group + 3);
  return {
    start: members[0] ?? head,
    end: chordEnd(events, members.at(-1) ?? head),
  };
}

/**
 * El tramo de figuras sin tresillo de una voz que llevan otras con él, si es uno solo (de la
 * primera a la última sin tresillo, sin ninguna con él en medio). Así se completa un compás en
 * que el tresillo solo se leyó en algunas figuras.
 */
function untripled(events: readonly ScoreEventPayload[]): Stretch | null {
  const plain = heads(events).filter(
    (index) => figure(events[index]) && !hasTriplet(events[index]?.duration_beats),
  );
  const first = plain[0];
  const last = plain.at(-1);
  if (first === undefined || last === undefined) return null;
  const stretch = { start: first, end: chordEnd(events, last) };
  return tripletState(events, stretch) === "none" ? stretch : null;
}

const MIXED = "Unas figuras de ese tramo llevan tresillo y otras no: ponlo o quítalo por grupos.";

const sameVoice = (a: AnchorPayload, b: AnchorPayload) =>
  a.part === b.part && a.staff === b.staff && a.measure === b.measure && a.voice === b.voice;

/**
 * Poner o quitar el tresillo de 3:2 (`SetTuplet`, ADR-0044 §3) con una sola edición:
 *
 * - `group`: si la elegida no lo lleva, a ella y a las dos figuras siguientes de su voz (un acorde
 *   cuenta como una); si lo lleva, se quita a su grupo de tres.
 * - `measure`: a todas las figuras de su voz en el compás; si unas lo llevan y otras no, se pone
 *   a las que no, si van seguidas.
 * - `range`: a las que van del inicio marcado a la elegida, en la misma voz del mismo compás.
 *
 * Poner multiplica cada figura por 2/3 y quitar, por 3/2; una nota de adorno no cambia. Una
 * figura con puntillo no pasa a tresillo (sería otra figura sin él). La selección no se mueve.
 */
export function planTuplet(
  scope: TupletScope,
  target: EditTarget | null,
  score: ScoreIRPayload,
  origin: AnchorPayload | null,
): EditPlan {
  if (!target) return refuse(NO_TARGET, "no-target");
  const events = voiceEvents(score, target.anchor) ?? [];
  const chosen = chordStart(events, target.anchor.event_index);
  let stretch: Stretch | null;
  let state: ReturnType<typeof tripletState>;
  if (scope === "group") {
    const own = events[chosen];
    if (!figure(own)) return refuse("Una nota de adorno no ocupa tiempo: elige una figura.");
    if (hasTriplet(own?.duration_beats)) {
      stretch = groupOf(events, chosen);
    } else {
      stretch = threeFrom(events, chosen);
      if (!stretch) {
        return refuse(
          "No quedan tres figuras en la voz desde la elegida: elige la primera del tresillo, o márcala con «Inicio» y pulsa «Tramo» en la última.",
        );
      }
    }
    state = tripletState(events, stretch);
    if (state === "mixed") return refuse(MIXED);
  } else if (scope === "measure") {
    // De la primera figura a la última: un hueco al principio o al final (ADR-0032) se queda.
    const all = heads(events).filter((index) => figure(events[index]));
    stretch = { start: all[0] ?? 0, end: chordEnd(events, all.at(-1) ?? 0) };
    state = tripletState(events, stretch);
    if (state === "mixed") {
      stretch = untripled(events);
      if (!stretch) {
        return refuse(
          "En este compás hay figuras con tresillo entre otras sin él: ponlo o quítalo por grupos.",
        );
      }
      state = "none";
    }
  } else {
    if (!origin) {
      return refuse(
        "Marca antes el inicio: elige la primera figura, pulsa «Inicio» y elige la última.",
      );
    }
    if (!sameVoice(origin, target.anchor)) {
      return refuse(
        "El inicio y la nota elegida tienen que estar en la misma voz del mismo compás.",
      );
    }
    const from = Math.min(chordStart(events, origin.event_index), chosen);
    const to = Math.max(chordStart(events, origin.event_index), chosen);
    stretch = { start: from, end: chordEnd(events, to) };
    state = tripletState(events, stretch);
    if (state === "mixed") return refuse(MIXED);
  }
  if (state === "empty") return refuse("Ahí solo hay notas de adorno: no ocupan tiempo.");
  if (events.slice(stretch.start, stretch.end).some(isHidden)) {
    return refuse(
      "En ese tramo hay un hueco de la voz (un silencio invisible): desde la vista no se le pone el tresillo.",
    );
  }
  const put = state === "none";
  const factor: Fraction = put ? [2, 3] : [3, 2];
  const durations: (string | null)[] = [];
  for (const event of events.slice(stretch.start, stretch.end)) {
    const value = parseBeats(event.duration_beats);
    if (!value) {
      durations.push(null);
      continue;
    }
    const result = reduce([value[0] * factor[0], value[1] * factor[1]]);
    if (put && result[1] % 3 !== 0) {
      return refuse("Una figura con puntillo no pasa a tresillo: quítale antes el puntillo.");
    }
    if (!put && result[1] % 3 === 0) {
      return refuse(
        "Una de esas figuras no es de un tresillo de 3:2: corrígela con los botones de figura.",
      );
    }
    if (!admissible(result)) {
      return refuse(
        "Una de esas figuras quedaría más breve o más larga de lo que admite la partitura.",
      );
    }
    durations.push(text(result));
  }
  const first = events[stretch.start];
  const count = durations.filter((duration) => duration !== null).length;
  const figures = `${String(count)} ${count === 1 ? "figura" : "figuras"}`;
  const where = `del compás ${String(target.anchor.measure)}`;
  return {
    kind: "edit",
    op: "SetTuplet",
    after: { durations },
    tuplet: {
      scope,
      put,
      chosen: target.anchor,
      from: scope === "range" ? origin : null,
    },
    anchor: {
      ...target.anchor,
      event_index: stretch.start,
      bbox: first?.bbox ?? null,
      confidence: first?.confidence ?? null,
    },
    change: put ? `tresillo en ${figures} ${where}` : `quitar el tresillo de ${figures} ${where}`,
  };
}

/**
 * Si los eventos a los que llegaría una orden de tresillo ya lo llevan: el botón, pulsado, y
 * pulsarlo lo quita. False también si la orden no se puede.
 */
export function tupletPressed(
  scope: TupletScope,
  target: EditTarget | null,
  score: ScoreIRPayload | null,
  origin: AnchorPayload | null,
): boolean {
  if (!score) return false;
  const plan = planTuplet(scope, target, score, origin);
  return plan.kind === "edit" && "tuplet" in plan && !plan.tuplet.put;
}

/**
 * Tras un 409, la misma edición de compás o de tresillo sobre el estado recargado (ADR-0011: el
 * cliente recarga y reconstruye la edición). El compás, en el mismo compás y con el tramo
 * calculado de nuevo; el tresillo, con el evento elegido (y el inicio) llevados al estado
 * recargado por `carry` y el mismo alcance. Si ahora haría lo contrario (otra pestaña ya lo puso
 * o lo quitó), no hay nada que volver a aplicar.
 */
export function replanMeter(
  edit: MeterDecision,
  anchor: AnchorPayload,
  score: ScoreIRPayload,
  carry: (anchor: AnchorPayload) => AnchorPayload | null,
): { plan: EditPlan; anchor: AnchorPayload | null } {
  if (edit.op === "SetTime") return { plan: planTime(edit.time, anchor, score), anchor };
  const { scope, put, chosen, from } = edit.tuplet;
  const carried = carry(chosen);
  const origin = from ? carry(from) : null;
  const events = carried ? voiceEvents(score, carried) : null;
  const event = carried ? events?.[carried.event_index] : undefined;
  if (!carried || !event || (from && !origin)) {
    return { plan: refuse(NO_TARGET, "no-target"), anchor: null };
  }
  const plan = planTuplet(scope, { anchor: carried, event, chord: false }, score, origin);
  if (plan.kind === "edit" && "tuplet" in plan && plan.tuplet.put !== put) {
    return {
      plan: refuse(
        put ? "Esas figuras ya llevan el tresillo." : "Esas figuras ya no llevan el tresillo.",
        "same",
      ),
      anchor: carried,
    };
  }
  return { plan, anchor: carried };
}

/** Operaciones de compás y de tresillos: no mueven ningún evento (ADR-0044). */
export const METER_OPS: readonly string[] = ["SetTime", "SetTuplet"];
