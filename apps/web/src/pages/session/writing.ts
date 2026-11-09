import type { EditTarget } from "./edits";
import { slotKey, type MeasureSlot } from "./findings";
import type { SelectableEvent } from "./noteMap";
import type { Box } from "./osmd";

/**
 * Escribir con el ratón (#350): dónde cae el puntero sobre la partitura dibujada. La nota
 * fantasma y el clic salen de aquí; lo que se envía lo deciden las órdenes `write*` de `edits`.
 */

/** Líneas de un pentagrama dibujado, en px de la partitura: la quinta línea y un espacio. */
export interface StaffLines {
  top: number;
  space: number;
}

/**
 * La franja de un compás (ADR-0021) abarca dos espacios por encima y por debajo de las cinco
 * líneas: ocho espacios en total.
 */
export function staffLines(box: Box): StaffLines {
  const space = box.height / 8;
  return { top: box.top + 2 * space, space };
}

/** Lo más lejos que se escribe: cuatro líneas adicionales por encima y por debajo. */
const HIGHEST = -8;
const LOWEST = 16;

/** Medios espacios bajo la quinta línea del punto `y` (0, la quinta; 8, la primera). */
export function stepsAt(y: number, lines: StaffLines): number {
  const steps = Math.round((y - lines.top) / (lines.space / 2));
  return Math.min(LOWEST, Math.max(HIGHEST, steps));
}

/** Altura en px de una línea o un espacio. */
export const stepY = (steps: number, lines: StaffLines) => lines.top + (steps * lines.space) / 2;

/** Las líneas adicionales que lleva una nota fuera de las cinco líneas. */
export function ledgerSteps(steps: number): number[] {
  const ledgers: number[] = [];
  for (let step = -2; step >= steps; step -= 2) ledgers.push(step);
  for (let step = 10; step <= steps; step += 2) ledgers.push(step);
  return ledgers;
}

/**
 * A qué apunta el clic: sustituir el evento (`replace`), en la columna de su figura, o insertar
 * una nota nueva antes de él (`insert`) o, con `end`, tras él, el último de su voz.
 */
export type WriteAim =
  | { kind: "replace"; event: SelectableEvent; x: number }
  | { kind: "insert"; event: SelectableEvent; end: boolean; x: number };

/** Un punto de la partitura en el modo «Escribir»: a qué apunta y en qué línea o espacio. */
export interface WriteSpot {
  aim: WriteAim;
  steps: number;
  lines: StaffLines;
}

/** Cuánto alrededor de una figura cuenta como sobre ella, en espacios. */
const FIGURE_MARGIN = 0.6;
/** El fantasma de una inserción no se aleja más de esto de la figura vecina, en espacios. */
const INSERT_REACH = 2;

/**
 * Las líneas de un compás, ajustadas a sus notas dibujadas: la franja sale del modelo de OSMD, que
 * en un sistema que no es el primero puede desviarse unos píxeles de lo que dibuja; cada cabeza,
 * con su altura conocida (`noteSteps`), dice dónde está de verdad la quinta línea. Se toma la
 * mediana; sin notas, las líneas del modelo.
 */
function calibrated(
  lines: StaffLines,
  events: readonly SelectableEvent[],
  noteSteps: (event: SelectableEvent) => number | null,
): StaffLines {
  const offsets: number[] = [];
  for (const event of events) {
    const steps = noteSteps(event);
    const head = event.boxes[0];
    if (steps === null || !head) continue;
    offsets.push(head.top + head.height / 2 - stepY(steps, lines));
  }
  if (offsets.length === 0) return lines;
  offsets.sort((a, b) => a - b);
  const middle = Math.floor(offsets.length / 2);
  const median =
    offsets.length % 2 === 1
      ? (offsets[middle] ?? 0)
      : ((offsets[middle - 1] ?? 0) + (offsets[middle] ?? 0)) / 2;
  return { top: lines.top + median, space: lines.space };
}

interface Column {
  members: SelectableEvent[];
  left: number;
  right: number;
}

function distance(value: number, start: number, size: number): number {
  if (value < start) return start - value;
  if (value > start + size) return value - start - size;
  return 0;
}

const sameVoice = (a: SelectableEvent, b: SelectableEvent) =>
  a.anchor.part === b.anchor.part &&
  a.anchor.staff === b.anchor.staff &&
  a.anchor.measure === b.anchor.measure &&
  a.anchor.voice === b.anchor.voice;

/** Las columnas de una voz: cada figura, con todas las notas de su acorde, en orden. */
function columnsOf(voice: SelectableEvent[]): Column[] {
  const columns: Column[] = [];
  const ordered = [...voice].sort((a, b) => a.anchor.event_index - b.anchor.event_index);
  for (const event of ordered) {
    const last = columns.at(-1);
    const left = Math.min(...event.boxes.map((box) => box.left));
    const right = Math.max(...event.boxes.map((box) => box.left + box.width));
    // Una nota que sigue a otra en su acorde (`is_chord`) va en su columna.
    if (event.event.is_chord === true && last) {
      last.members.push(event);
      last.left = Math.min(last.left, left);
      last.right = Math.max(last.right, right);
    } else {
      columns.push({ members: [event], left, right });
    }
  }
  return columns.sort((a, b) => a.left - b.left);
}

/** Lo que pide un clic en el modo «Escribir», con el evento en el estado que se ve. */
export type WriteRequest =
  | { kind: "replace"; target: EditTarget; pitch: string; chord: boolean }
  | { kind: "insert"; target: EditTarget; pitch: string; end: boolean };

/** El modo «Escribir», tal como lo ve la partitura (#350). */
export interface WritingMode {
  /** Figura (índice de `FIGURES`) y puntillo con que se escribe. */
  figure: number;
  dotted: boolean;
  /** Si se puede escribir ya: no se está guardando ninguna corrección. */
  ready: boolean;
  onWrite: (request: WriteRequest) => void;
  onExit: () => void;
}

/**
 * Lo que haría un clic en (`x`, `y`), en px de la partitura, o null. El compás es aquel cuya
 * franja, con sus líneas adicionales, contiene el punto (el de pentagrama más cercano, si dos se
 * tocan); la voz, la de la figura más cercana en horizontal. Sobre una figura (con un margen) se
 * sustituye su nota más cercana en vertical; entre dos figuras, antes de la primera o tras la
 * última se inserta. Las notas de adorno no se escriben con el ratón.
 */
export function writeSpotAt(
  events: readonly SelectableEvent[],
  x: number,
  y: number,
  measureBox: (slot: MeasureSlot) => Box | null,
  noteSteps: (event: SelectableEvent) => number | null = () => null,
): WriteSpot | null {
  const bySlot = new Map<string, { slot: MeasureSlot; events: SelectableEvent[] }>();
  for (const event of events) {
    if (event.grace) continue;
    const key = slotKey(event.slot);
    const group = bySlot.get(key);
    if (group) group.events.push(event);
    else bySlot.set(key, { slot: event.slot, events: [event] });
  }

  let found: { box: Box; lines: StaffLines; events: SelectableEvent[] } | null = null;
  let closest = Infinity;
  for (const { slot, events: inSlot } of bySlot.values()) {
    const box = measureBox(slot);
    if (!box) continue;
    const lines = staffLines(box);
    const top = lines.top + (HIGHEST / 2) * lines.space;
    const bottom = lines.top + (LOWEST / 2) * lines.space;
    if (x < box.left || x > box.left + box.width || y < top || y > bottom) continue;
    const fromMiddle = Math.abs(y - (lines.top + 2 * lines.space));
    if (fromMiddle < closest) {
      closest = fromMiddle;
      found = { box, lines, events: inSlot };
    }
  }
  if (!found) return null;
  const { box } = found;
  const lines = calibrated(found.lines, found.events, noteSteps);

  // La voz: la de la figura más cercana en horizontal y, a igual distancia, en vertical.
  let nearest: SelectableEvent | null = null;
  let bestX = Infinity;
  let bestY = Infinity;
  for (const event of found.events) {
    for (const figure of event.boxes) {
      const dx = distance(x, figure.left, figure.width);
      const dy = distance(y, figure.top, figure.height);
      if (dx < bestX || (dx === bestX && dy < bestY)) {
        nearest = event;
        bestX = dx;
        bestY = dy;
      }
    }
  }
  if (!nearest) return null;
  const voice = nearest;
  const columns = columnsOf(found.events.filter((event) => sameVoice(event, voice)));
  const steps = stepsAt(y, lines);
  const margin = FIGURE_MARGIN * lines.space;
  const reach = INSERT_REACH * lines.space;

  const over = columns.find((column) => x >= column.left - margin && x <= column.right + margin);
  if (over) {
    // En un acorde, la nota más cercana en vertical.
    let event = over.members[0] ?? voice;
    let bestRow = Infinity;
    for (const member of over.members) {
      for (const figure of member.boxes) {
        const dy = distance(y, figure.top, figure.height);
        if (dy < bestRow) {
          bestRow = dy;
          event = member;
        }
      }
    }
    return { aim: { kind: "replace", event, x: (over.left + over.right) / 2 }, steps, lines };
  }

  const next = columns.find((column) => column.left > x);
  const previous = [...columns].reverse().find((column) => column.right < x);
  if (next?.members[0]) {
    const from = previous ? previous.right : box.left;
    const at = Math.max((from + next.left) / 2, next.left - reach);
    return { aim: { kind: "insert", event: next.members[0], end: false, x: at }, steps, lines };
  }
  const last = previous?.members[0];
  if (!previous || !last) return null;
  const at = Math.min((previous.right + box.left + box.width) / 2, previous.right + reach);
  return { aim: { kind: "insert", event: last, end: true, x: at }, steps, lines };
}
