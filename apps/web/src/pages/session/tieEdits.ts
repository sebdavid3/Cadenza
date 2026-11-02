import type { AnchorPayload, ScoreEventPayload, ScoreIRPayload } from "../../types";
import type { EditPlan, EditTarget } from "./edits";
import { chordStart } from "./markEdits";
import { pitchName } from "./noteNames";

/**
 * La ligadura de prolongación de la nota elegida (#312, ADR-0055): «Ligar» la pone hasta la nota
 * de la misma altura que la sigue o quita la que sale de ella, y «Quitar la ligadura que llega»
 * quita la que le llega. Cada orden es un `SetTie` con los valores finales de las dos notas.
 */

export type TieValue = "start" | "continue" | "stop" | null;

/** Ligar con la siguiente (o quitar la que sale) y quitar la que llega. */
export type TieCommand = { kind: "tie" } | { kind: "untie-in" };

/** Lo que se pidió: ponerla, quitar la que sale o la que llega, desde la nota elegida. */
export type TieIntent = "put" | "remove" | "remove-in";

export interface TieDecision {
  op: "SetTie";
  /**
   * El `after` (y el `before`) de `SetTie`: el valor de la nota del ancla y el de la otra. Un
   * literal, no una interfaz: va como `Record<string, unknown>` en la petición.
   */
  after: {
    tie: TieValue;
    next: { measure: number; voice: number; event_index: number; tie: TieValue } | null;
  };
  tie: { intent: TieIntent; from: AnchorPayload };
}

export type TieAfter = TieDecision["after"];

/** Si llega una ligadura a la nota (`stop`, `continue`). */
export const tieArrives = (tie: string | null | undefined) => tie === "stop" || tie === "continue";
/** Si sale una ligadura de la nota (`start`, `continue`). */
export const tieLeaves = (tie: string | null | undefined) => tie === "start" || tie === "continue";

const tieOf = (arrives: boolean, leaves: boolean): TieValue =>
  arrives ? (leaves ? "continue" : "stop") : leaves ? "start" : null;

/** Una nota de un pentagrama: su compás, su voz, su posición en la voz y su evento. */
export interface NotePlace {
  measure: number;
  voice: number;
  event_index: number;
  event: ScoreEventPayload;
}

const isNote = (event: ScoreEventPayload | undefined): event is ScoreEventPayload =>
  event?.kind === "note";

/** El grupo `[inicio, fin)` del evento `index` de una voz: su acorde entero o solo él. */
function groupOf(events: readonly ScoreEventPayload[], index: number): [number, number] {
  const start = chordStart(events, index);
  let end = start + 1;
  while (isNote(events[end]) && events[end]?.is_chord === true && isNote(events[end - 1])) {
    end += 1;
  }
  return [start, end];
}

/** El primer grupo de la voz desde `from` que ocupa tiempo: sin las notas de adorno. */
function firstTimedGroup(events: readonly ScoreEventPayload[], from = 0): [number, number] | null {
  let index = from;
  while (index < events.length) {
    const [start, end] = groupOf(events, index);
    if (events[start]?.duration_beats != null) {
      // Los silencios invisibles del final de la voz no cuentan: tras ellos no hay nada, y la
      // ligadura cruza la barra (como en el servidor y en `tie.resolution`).
      const rest = events.slice(start);
      if (rest.every((event) => event.hidden === true || event.duration_beats == null)) return null;
      return [start, end];
    }
    index = end;
  }
  return null;
}

const measuresOf = (score: ScoreIRPayload, anchor: AnchorPayload) =>
  score.parts[anchor.part]?.staves[anchor.staff]?.measures ?? [];

const inVoice = (events: readonly ScoreEventPayload[], voice: number) =>
  events.filter((event) => event.voice === voice);

/**
 * Las notas que siguen a la del ancla, como las busca el servidor (`tie_edits.following`): las
 * del grupo siguiente de su voz o, si el suyo es el último de su voz en el compás, las del primer
 * grupo de cada voz del compás siguiente (su voz primero).
 */
export function followingNotes(score: ScoreIRPayload, anchor: AnchorPayload): NotePlace[] {
  return followingPlaces(score, anchor).filter(
    (place) => isNote(place.event) && place.event.duration_beats != null,
  );
}

/** Lo que sigue a la nota del ancla, notas o no: el grupo de `followingNotes` entero. */
function followingPlaces(score: ScoreIRPayload, anchor: AnchorPayload): NotePlace[] {
  const measures = measuresOf(score, anchor);
  const position = measures.findIndex((measure) => measure.number === anchor.measure);
  const measure = measures[position];
  if (!measure) return [];
  const events = inVoice(measure.events, anchor.voice);
  if (!events[anchor.event_index]) return [];
  const [, end] = groupOf(events, anchor.event_index);
  const places = (
    number: number,
    voice: number,
    list: readonly ScoreEventPayload[],
    [start, stop]: [number, number],
  ) =>
    list
      .slice(start, stop)
      .map((event, offset) => ({ measure: number, voice, event_index: start + offset, event }));
  const within = firstTimedGroup(events, end);
  if (within) return places(measure.number, anchor.voice, events, within);
  const later = measures[position + 1];
  if (!later) return [];
  const voices = [...new Set(later.events.map((event) => event.voice))].sort(
    (a, b) => Number(a !== anchor.voice) - Number(b !== anchor.voice) || a - b,
  );
  return voices.flatMap((voice) => {
    const list = inVoice(later.events, voice);
    const group = firstTimedGroup(list);
    return group ? places(later.number, voice, list, group) : [];
  });
}

/** Las notas a las que sigue la del ancla: donde puede empezar la ligadura que le llega. */
function precedingNotes(score: ScoreIRPayload, anchor: AnchorPayload): NotePlace[] {
  const measures = measuresOf(score, anchor);
  const position = measures.findIndex((measure) => measure.number === anchor.measure);
  const candidates = measures.slice(Math.max(position - 1, 0), position + 1).flatMap((measure) => {
    const voices = [...new Set(measure.events.map((event) => event.voice))];
    return voices.flatMap((voice) =>
      inVoice(measure.events, voice).map((event, index) => ({
        measure: measure.number,
        voice,
        event_index: index,
        event,
      })),
    );
  });
  return candidates.filter(
    (place) =>
      isNote(place.event) &&
      followingNotes(score, { ...anchor, ...place }).some(
        (next) =>
          next.measure === anchor.measure &&
          next.voice === anchor.voice &&
          next.event_index === anchor.event_index,
      ),
  );
}

const STEPS = "CDEFGAB";
const ALTER: Record<string, number> = {
  "": 0,
  "#": 1,
  "##": 2,
  x: 2,
  b: -1,
  "-": -1,
  bb: -2,
  "--": -2,
};

/** La altura escrita (letra, alteración y octava), para comparar dos notas. */
function spelling(pitch: string | null | undefined): string | null {
  const match = pitch ? /^([A-Ga-g])(##|bb|--|#|b|-|x)?(-?\d+)$/.exec(pitch.trim()) : null;
  const step = match?.[1]?.toUpperCase() ?? "";
  const alter = ALTER[match?.[2] ?? ""];
  if (!match || !STEPS.includes(step) || alter === undefined) return null;
  return `${step}${String(alter)}${match[3] ?? ""}`;
}

export const samePitch = (a: ScoreEventPayload, b: ScoreEventPayload) => {
  const left = spelling(a.pitch);
  return left !== null && left === spelling(b.pitch);
};

const spoken = (pitch: string | null | undefined) =>
  pitch ? (pitchName(pitch)?.spoken ?? pitch) : "la nota";

const refuse = (message: string, reason: "tie" | "same" | "no-target" = "tie"): EditPlan => ({
  kind: "refused",
  reason,
  message,
});

const NO_TARGET = "Elige primero una nota o un silencio.";

/** El ancla de una nota del mismo pentagrama que `anchor`, sin caja ni confianza de otra. */
const anchorOf = (anchor: AnchorPayload, place: NotePlace): AnchorPayload => ({
  ...anchor,
  measure: place.measure,
  voice: place.voice,
  event_index: place.event_index,
  bbox: place.event.bbox ?? null,
  confidence: place.event.confidence ?? null,
});

/** La nota de la lista con la misma altura que `event`, o la primera. */
const preferSame = (places: NotePlace[], event: ScoreEventPayload) =>
  places.find((place) => samePitch(place.event, event)) ?? places[0];

function planPut(target: EditTarget, score: ScoreIRPayload): EditPlan {
  const { event, anchor } = target;
  if (event.duration_beats == null) return refuse("Una nota de adorno no se liga.");
  const next = followingNotes(score, anchor);
  const name = spoken(event.pitch);
  if (followingPlaces(score, anchor).length === 0) {
    return refuse("No hay nada después de esta nota en su voz ni al empezar el compás siguiente.");
  }
  const other = next.find((place) => samePitch(place.event, event));
  if (!other) {
    return refuse(
      `Lo siguiente no es un ${name}: una ligadura de prolongación une dos notas de la misma altura.`,
    );
  }
  const crosses = other.measure !== anchor.measure;
  return {
    kind: "edit",
    op: "SetTie",
    after: {
      tie: tieOf(tieArrives(event.tie), true),
      next: {
        measure: other.measure,
        voice: other.voice,
        event_index: other.event_index,
        tie: tieOf(true, tieLeaves(other.event.tie)),
      },
    },
    tie: { intent: "put", from: anchor },
    anchor,
    change: `ligadura de prolongación de ${name}${crosses ? ` hasta el compás ${String(other.measure)}` : ""}`,
  };
}

function planRemove(target: EditTarget, score: ScoreIRPayload): EditPlan {
  const { event, anchor } = target;
  const arriving = followingNotes(score, anchor).filter((place) => tieArrives(place.event.tie));
  const other = arriving.length > 0 ? preferSame(arriving, event) : undefined;
  return {
    kind: "edit",
    op: "SetTie",
    after: {
      tie: tieOf(tieArrives(event.tie), false),
      next: other
        ? {
            measure: other.measure,
            voice: other.voice,
            event_index: other.event_index,
            tie: tieOf(false, tieLeaves(other.event.tie)),
          }
        : null,
    },
    tie: { intent: "remove", from: anchor },
    anchor,
    change: `quitar la ligadura de prolongación de ${spoken(event.pitch)}`,
  };
}

function planRemoveIncoming(target: EditTarget, score: ScoreIRPayload): EditPlan {
  const { event, anchor } = target;
  if (!tieArrives(event.tie)) return refuse("A esta nota no le llega ninguna ligadura.");
  const sources = precedingNotes(score, anchor).filter((place) => tieLeaves(place.event.tie));
  const source = sources.length > 0 ? preferSame(sources, event) : undefined;
  const change = `quitar la ligadura de prolongación que llega a ${spoken(event.pitch)}`;
  if (!source) {
    // Una ligadura que llega sin salir de ninguna nota: se quita su marca, sola.
    return {
      kind: "edit",
      op: "SetTie",
      after: { tie: tieOf(false, tieLeaves(event.tie)), next: null },
      tie: { intent: "remove-in", from: anchor },
      anchor,
      change,
    };
  }
  return {
    kind: "edit",
    op: "SetTie",
    after: {
      tie: tieOf(tieArrives(source.event.tie), false),
      next: {
        measure: anchor.measure,
        voice: anchor.voice,
        event_index: anchor.event_index,
        tie: tieOf(false, tieLeaves(event.tie)),
      },
    },
    tie: { intent: "remove-in", from: anchor },
    anchor: anchorOf(anchor, source),
    change,
  };
}

/**
 * La edición que pide una orden de ligadura sobre la nota elegida, o por qué no. «Ligar» la pone
 * si no sale ninguna de la nota y, si sale, la quita.
 */
export function planTie(
  command: TieCommand,
  target: EditTarget | null,
  score: ScoreIRPayload,
): EditPlan {
  if (!target) return refuse(NO_TARGET, "no-target");
  if (target.event.kind !== "note") return refuse("Un silencio no se liga: elige una nota.");
  if (command.kind === "untie-in") return planRemoveIncoming(target, score);
  return tieLeaves(target.event.tie) ? planRemove(target, score) : planPut(target, score);
}

/**
 * Tras un 409, lo mismo desde la nota elegida llevada al estado recargado: ponerla, quitar la que
 * sale o la que llega. Si ya está como se pedía, no hay nada que volver a aplicar.
 */
export function replanTie(
  edit: TieDecision,
  score: ScoreIRPayload,
  carry: (anchor: AnchorPayload) => AnchorPayload | null,
): { plan: EditPlan; anchor: AnchorPayload | null } {
  const { intent, from } = edit.tie;
  const carried = carry(from);
  const event = carried
    ? inVoice(
        measuresOf(score, carried).find((measure) => measure.number === carried.measure)?.events ??
          [],
        carried.voice,
      )[carried.event_index]
    : undefined;
  if (!carried || !event) return { plan: refuse(NO_TARGET, "no-target"), anchor: null };
  const target: EditTarget = { anchor: carried, event, chord: false };
  if (event.kind !== "note")
    return { plan: planTie({ kind: "tie" }, target, score), anchor: carried };
  const leaves = tieLeaves(event.tie);
  let plan: EditPlan;
  if (intent === "put") {
    plan = leaves ? refuse("La nota ya empieza una ligadura.", "same") : planPut(target, score);
  } else if (intent === "remove") {
    plan = leaves
      ? planRemove(target, score)
      : refuse("De la nota ya no sale ninguna ligadura.", "same");
  } else {
    plan = tieArrives(event.tie)
      ? planRemoveIncoming(target, score)
      : refuse("A la nota ya no le llega ninguna ligadura.", "same");
  }
  return { plan, anchor: carried };
}

/** Qué hace un `SetTie` del log, para la historia: «ligadura de prolongación», «quitar…». */
export function describeTieEdit(after: unknown): string {
  const value =
    after !== null && typeof after === "object" ? (after as Record<string, unknown>) : {};
  return tieLeaves(typeof value.tie === "string" ? value.tie : null)
    ? "ligadura de prolongación"
    : "quitar la ligadura de prolongación";
}

/** Si el `before` de un `SetTie` basta para deshacerlo (`has_complete_tie_before`). */
export const hasCompleteTieBefore = (before: Record<string, unknown>) =>
  "tie" in before && "next" in before;
