import type { AnchorPayload, ScoreEventPayload, ScoreIRPayload } from "../../types";
import { slotKey, type MeasureSlot } from "./findings";
import type { Box, DrawnFigure, DrawnVoice } from "./osmd";
import { parseBeats, pitchToMidi } from "./playback";

/** Evento del `ScoreIR` que se puede elegir: su ancla y dónde está dibujado (ADR-0027). */
export interface SelectableEvent {
  /** Clave del ancla: parte, pentagrama, compás, voz y posición en la voz. */
  key: string;
  anchor: AnchorPayload;
  event: ScoreEventPayload;
  /** Compás dibujado: pentagrama en el orden global de OSMD e índice del compás. */
  slot: MeasureSlot;
  /** Cuándo empieza dentro del compás, en negras: sirve para pasar de una voz a otra. */
  onset: number;
  /** Caja de cada figura que lo dibuja: más de una si el exportador partió su duración. */
  boxes: Box[];
  /** Caja que abarca todas sus figuras. */
  box: Box;
}

/**
 * Mapa ancla→caja de una partitura dibujada. Solo se ofrece completo: si algún evento no se
 * empareja con seguridad, no se elige ninguno (como los compases en ADR-0021).
 */
export type NoteMap =
  | { status: "complete"; events: SelectableEvent[] }
  | { status: "incomplete"; total: number; unmatched: number };

type AnchorPath = Pick<AnchorPayload, "part" | "staff" | "measure" | "voice" | "event_index">;

export function anchorKey(anchor: AnchorPath): string {
  return [anchor.part, anchor.staff, anchor.measure, anchor.voice, anchor.event_index].join(":");
}

type Fraction = readonly [number, number];

function gcd(a: number, b: number): number {
  return b === 0 ? Math.abs(a) : gcd(b, a % b);
}

function add([a, b]: Fraction, [c, d]: Fraction): Fraction {
  const numerator = a * d + c * b;
  const denominator = b * d;
  const divisor = gcd(numerator, denominator) || 1;
  return [numerator / divisor, denominator / divisor];
}

const compare = ([a, b]: Fraction, [c, d]: Fraction) => a * d - c * b;

/**
 * Duración con la que el exportador escribe un evento, en negras. music21 ignora una duración
 * cero y escribe una negra, igual que con una duración nula; null si no se entiende.
 */
function exportedBeats(value: string | null): Fraction | null {
  if (value === null) return [1, 1];
  const match = /^\s*(\d+)(?:\s*\/\s*(\d+))?\s*$/.exec(value);
  if (!match) return null;
  const numerator = Number(match[1]);
  const denominator = match[2] === undefined ? 1 : Number(match[2]);
  if (denominator === 0) return null;
  return numerator === 0 ? [1, 1] : [numerator, denominator];
}

interface Indexed {
  event: ScoreEventPayload;
  /** Posición del evento en `measure.events`. */
  index: number;
}

/** Nota o silencio que el exportador escribe como una figura: un silencio, una nota o un acorde. */
interface Group {
  rest: boolean;
  members: Indexed[];
}

/**
 * Agrupa los eventos de una voz como el exportador (`_build_voice_elements`): un silencio solo,
 * y una nota con las que la siguen marcadas como acorde. Null si hay un evento que el exportador
 * no escribe como nota o silencio con altura.
 */
function groupsOf(voice: Indexed[]): Group[] | null {
  const groups: Group[] = [];
  for (let i = 0; i < voice.length;) {
    const first = voice[i];
    if (!first) break;
    if (first.event.kind === "rest") {
      groups.push({ rest: true, members: [first] });
      i += 1;
      continue;
    }
    if (first.event.kind !== "note" || first.event.pitch === null) return null;
    const members = [first];
    let j = i + 1;
    for (let next = voice[j]; next?.event.is_chord && next.event.kind === "note"; next = voice[j]) {
      if (next.event.pitch === null) return null;
      members.push(next);
      j += 1;
    }
    groups.push({ rest: false, members });
    i = j;
  }
  return groups;
}

const stepOf = (pitch: string) => pitch.trim().charAt(0).toUpperCase();

/**
 * Para cada miembro de un acorde (o la nota sola), la posición de su nota en la figura dibujada,
 * por altura y nombre: OSMD ordena el acorde de grave a agudo. Null si no son las mismas notas.
 */
function pairNotes(members: Indexed[], figure: DrawnFigure): number[] | null {
  if (figure.notes.length !== members.length) return null;
  const used = new Set<number>();
  const pairs: number[] = [];
  for (const { event } of members) {
    const midi = event.pitch === null ? null : pitchToMidi(event.pitch);
    if (midi === null || event.pitch === null) return null;
    const step = stepOf(event.pitch);
    const position = figure.notes.findIndex(
      (note, candidate) => !used.has(candidate) && note.midi === midi && note.step === step,
    );
    if (position < 0) return null;
    used.add(position);
    pairs.push(position);
  }
  return pairs;
}

/**
 * Empareja los eventos de un compás con sus figuras dibujadas: voz con voz por orden y, dentro
 * de cada voz, cada nota, acorde o silencio con las figuras que suman su duración, que han de
 * ser de su misma clase y alturas. Devuelve las cajas de cada evento, o null si algo no cuadra.
 */
function matchMeasure(
  events: readonly ScoreEventPayload[],
  drawn: readonly DrawnVoice[] | null,
): Map<number, Box[]> | null {
  if (!drawn) return null;
  const voices = new Map<number, Indexed[]>();
  events.forEach((event, index) => {
    const voice = voices.get(event.voice);
    if (voice) voice.push({ event, index });
    else voices.set(event.voice, [{ event, index }]);
  });
  const ordered = [...voices.entries()].sort(([a], [b]) => a - b).map(([, voice]) => voice);
  if (ordered.length !== drawn.length) return null;

  const boxes = new Map<number, Box[]>();
  for (const [voiceIndex, voice] of ordered.entries()) {
    const figures = drawn[voiceIndex] ?? [];
    const groups = groupsOf(voice);
    if (!groups) return null;
    let cursor = 0;
    for (const group of groups) {
      const first = group.members[0];
      const wanted = first ? exportedBeats(first.event.duration_beats) : null;
      if (!wanted) return null;
      const used: DrawnFigure[] = [];
      let sum: Fraction = [0, 1];
      while (compare(sum, wanted) < 0) {
        const figure = figures[cursor];
        if (!figure || figure.grace) return null;
        sum = add(sum, figure.beats);
        used.push(figure);
        cursor += 1;
      }
      if (compare(sum, wanted) !== 0) return null;

      const perMember: Box[][] = group.members.map(() => []);
      for (const figure of used) {
        if (figure.rest !== group.rest) return null;
        const pairs = group.rest
          ? figure.notes.length === 1
            ? [0]
            : null
          : pairNotes(group.members, figure);
        if (!pairs) return null;
        for (const [member, position] of pairs.entries()) {
          const box = figure.notes[position]?.box;
          if (!box) return null;
          perMember[member]?.push(box);
        }
      }
      group.members.forEach((member, position) => {
        boxes.set(member.index, perMember[position] ?? []);
      });
    }
    if (cursor !== figures.length) return null;
  }
  return boxes;
}

function union(boxes: readonly Box[]): Box {
  const left = Math.min(...boxes.map((box) => box.left));
  const top = Math.min(...boxes.map((box) => box.top));
  const right = Math.max(...boxes.map((box) => box.left + box.width));
  const bottom = Math.max(...boxes.map((box) => box.top + box.height));
  return { left, top, width: right - left, height: bottom - top };
}

/**
 * Mapa ancla→caja de la partitura: cada evento del `ScoreIR` con su ancla (`event_index` cuenta
 * los eventos de su voz en el compás, como `compute_timing_map`) y las cajas de las figuras que
 * OSMD dibujó para él. `drawn` da las figuras de cada compás dibujado.
 */
export function buildNoteMap(
  score: ScoreIRPayload,
  drawn: (slot: MeasureSlot) => readonly DrawnVoice[] | null,
): NoteMap {
  const events: SelectableEvent[] = [];
  let total = 0;
  let unmatched = 0;
  let globalStaff = 0;
  score.parts.forEach((part, partIndex) => {
    part.staves.forEach((staff, staffIndex) => {
      const slotStaff = globalStaff;
      globalStaff += 1;
      staff.measures.forEach((measure, measureIndex) => {
        total += measure.events.length;
        const slot = { staff: slotStaff, measure: measureIndex };
        const boxes = matchMeasure(measure.events, drawn(slot));
        if (!boxes) {
          unmatched += measure.events.length;
          return;
        }
        const counters = new Map<number, number>();
        const onsets = new Map<number, number>();
        const previousOnsets = new Map<number, number>();
        const found: SelectableEvent[] = [];
        measure.events.forEach((event, index) => {
          const eventIndex = counters.get(event.voice) ?? 0;
          counters.set(event.voice, eventIndex + 1);
          // Como el mapa de tiempos: una nota de acorde empieza con la anterior de su voz.
          const start = event.is_chord
            ? (previousOnsets.get(event.voice) ?? 0)
            : (onsets.get(event.voice) ?? 0);
          if (!event.is_chord) {
            previousOnsets.set(event.voice, start);
            const duration = event.duration_beats === null ? 0 : parseBeats(event.duration_beats);
            onsets.set(event.voice, start + (Number.isFinite(duration) ? duration : 0));
          }
          const anchor: AnchorPayload = {
            part: partIndex,
            staff: staffIndex,
            measure: measure.number,
            voice: event.voice,
            event_index: eventIndex,
            staff_id: staff.id,
            bbox: event.bbox,
            confidence: event.confidence,
          };
          const eventBoxes = boxes.get(index) ?? [];
          found.push({
            key: anchorKey(anchor),
            anchor,
            event,
            slot,
            onset: start,
            boxes: eventBoxes,
            box: union(eventBoxes),
          });
        });
        found.sort(
          (a, b) => a.anchor.voice - b.anchor.voice || a.anchor.event_index - b.anchor.event_index,
        );
        events.push(...found);
      });
    });
  });
  return unmatched > 0
    ? { status: "incomplete", total, unmatched }
    : { status: "complete", events };
}

/** Cómo moverse desde el evento elegido. */
export type Move =
  | "next"
  | "previous"
  | "next-measure"
  | "previous-measure"
  | "measure-start"
  | "measure-end"
  | "up"
  | "down";

const voicesIn = (lane: readonly SelectableEvent[]) =>
  [...new Set(lane.map((selectable) => selectable.anchor.voice))].sort((a, b) => a - b);

/**
 * Evento al que se llega con un movimiento. Izquierda y derecha recorren la voz y pasan de
 * compás; los saltos de compás van al primer evento de la misma voz (o de la primera, si allí no
 * está); arriba y abajo pasan por las voces del pentagrama y después a los pentagramas vecinos,
 * al evento que empieza más cerca. En un borde se queda donde está. Sin nada elegido (o si lo
 * elegido ya no existe), cualquier movimiento elige el primer evento.
 */
export function moveSelection(
  events: readonly SelectableEvent[],
  currentKey: string | null,
  move: Move,
): SelectableEvent | null {
  const current = events.find((selectable) => selectable.key === currentKey);
  if (!current) return events[0] ?? null;

  const { staff, measure } = current.slot;
  const inMeasure = (measureIndex: number, staffIndex = staff) =>
    events.filter(
      (selectable) =>
        selectable.slot.staff === staffIndex && selectable.slot.measure === measureIndex,
    );
  const inVoice = (lane: readonly SelectableEvent[], voice: number) =>
    lane.filter((selectable) => selectable.anchor.voice === voice);
  const sameVoice = inVoice(inMeasure(measure), current.anchor.voice);
  const position = sameVoice.indexOf(current);
  const measures = [
    ...new Set(
      events
        .filter((selectable) => selectable.slot.staff === staff)
        .map((selectable) => selectable.slot.measure),
    ),
  ].sort((a, b) => a - b);
  const neighbour = (step: number) => measures[measures.indexOf(measure) + step];
  const enter = (measureIndex: number | undefined, edge: "first" | "last") => {
    if (measureIndex === undefined) return current;
    const lane = inMeasure(measureIndex);
    const voices = voicesIn(lane);
    const voice = voices.includes(current.anchor.voice) ? current.anchor.voice : (voices[0] ?? 0);
    const target = inVoice(lane, voice);
    return (edge === "first" ? target[0] : target.at(-1)) ?? current;
  };

  switch (move) {
    case "next":
      return sameVoice[position + 1] ?? enter(neighbour(1), "first");
    case "previous":
      return (position > 0 ? sameVoice[position - 1] : undefined) ?? enter(neighbour(-1), "last");
    case "next-measure":
      return enter(neighbour(1), "first");
    case "previous-measure":
      return enter(neighbour(-1), "first");
    case "measure-start":
      return sameVoice[0] ?? current;
    case "measure-end":
      return sameVoice.at(-1) ?? current;
    case "up":
    case "down": {
      const staves = [...new Set(events.map((selectable) => selectable.slot.staff))].sort(
        (a, b) => a - b,
      );
      const lanes = staves.flatMap((staffIndex) => {
        const lane = inMeasure(measure, staffIndex);
        return voicesIn(lane).map((voice) => inVoice(lane, voice));
      });
      const here = lanes.findIndex((lane) => lane.includes(current));
      const target = lanes[here + (move === "down" ? 1 : -1)];
      if (!target) return current;
      let best = current;
      let distance = Infinity;
      for (const candidate of target) {
        const offset = Math.abs(candidate.onset - current.onset);
        if (offset < distance) {
          distance = offset;
          best = candidate;
        }
      }
      return best;
    }
  }
}

const gap = (value: number, start: number, length: number) =>
  value < start ? start - value : value > start + length ? value - (start + length) : 0;

/**
 * Evento que se elige al tocar un punto de la partitura: el más cercano en horizontal entre los
 * del compás tocado y, a igual distancia (las notas de un acorde), el más cercano en vertical.
 * Fuera de los compases no se elige nada.
 */
export function nearestEvent(
  events: readonly SelectableEvent[],
  x: number,
  y: number,
  measureBox: (slot: MeasureSlot) => Box | null,
): SelectableEvent | null {
  const touched = new Map<string, boolean>();
  let best: SelectableEvent | null = null;
  let bestX = Infinity;
  let bestY = Infinity;
  for (const selectable of events) {
    const key = slotKey(selectable.slot);
    let inside = touched.get(key);
    if (inside === undefined) {
      const box = measureBox(selectable.slot);
      inside =
        box !== null && gap(x, box.left, box.width) === 0 && gap(y, box.top, box.height) === 0;
      touched.set(key, inside);
    }
    if (!inside) continue;
    const dx = gap(x, selectable.box.left, selectable.box.width);
    const dy = gap(y, selectable.box.top, selectable.box.height);
    if (dx < bestX || (dx === bestX && dy < bestY)) {
      best = selectable;
      bestX = dx;
      bestY = dy;
    }
  }
  return best;
}
