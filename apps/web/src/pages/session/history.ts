import type { AnchorPayload, EditEventRead, ScoreIRPayload } from "../../types";
import { CLEFS, eventAt, eventName, keyName, selectAfterDelete } from "./edits";
import { durationName, pitchName } from "./noteNames";

/**
 * Deshacer y rehacer desde la vista de una sesión (#185, ADR-0034), sobre el log de ediciones de
 * `GET /sessions/{id}`. Deshacer es `POST /undo`: el servidor registra la compensatoria de la
 * última edición vigente (ADR-0007, ADR-0017). Rehacer es volver a enviar la edición deshecha,
 * igual, como edición nueva. Qué se puede deshacer y rehacer se lee del log, no de la memoria de
 * la pestaña: vale tras recargar y con lo que se haga en otra.
 */

/** Una edición del log con lo que se sabe de ella al leerlo entero. */
export interface LogEntry {
  edit: EditEventRead;
  /** `seq` de la compensatoria que la deshizo, o null si sigue vigente. */
  undoneBy: number | null;
  /** Si es una compensatoria: el `seq` de la edición que deshace. */
  undoes: number | null;
  /** Si vuelve a enviar una edición deshecha (la rehace): el `seq` de esa. */
  redoes: number | null;
}

export interface EditLog {
  /** En orden de `seq`. */
  entries: LogEntry[];
  /** La edición que desharía `POST /undo`: la última vigente, o null si no queda ninguna. */
  undo: EditEventRead | null;
  /** La última deshecha que se puede rehacer, o null si no hay ninguna. */
  redo: EditEventRead | null;
}

/** Posición lógica de un ancla: lo que decide a qué evento apunta (sin caja ni confianza). */
const samePlace = (a: AnchorPayload, b: AnchorPayload) =>
  a.part === b.part &&
  a.staff === b.staff &&
  a.measure === b.measure &&
  a.voice === b.voice &&
  a.event_index === b.event_index &&
  a.staff_id === b.staff_id;

/** JSON con las claves ordenadas, para comparar valores sin depender de su orden. */
function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value !== null && typeof value === "object") {
    const entries = Object.entries(value).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
    return `{${entries.map(([key, item]) => `${JSON.stringify(key)}:${canonicalJson(item)}`).join(",")}}`;
  }
  return JSON.stringify(value ?? null);
}

/** Si dos ediciones hacen lo mismo sobre el mismo estado: la misma operación, ancla y valor. */
const sameEdit = (a: EditEventRead, b: EditEventRead) =>
  a.op === b.op &&
  samePlace(a.anchor, b.anchor) &&
  canonicalJson(a.after) === canonicalJson(b.after);

/**
 * Lee el log como la pila del servidor (`get_last_active_edit`): cada compensatoria retira de las
 * vigentes la que revierte, y esa pasa a la pila de rehacer. Una edición igual a la última de esa
 * pila la rehace (deja el mismo estado que rehacerla); cualquier otra la vacía: lo deshecho ya no
 * se puede volver a aplicar sobre un estado que no es el suyo (ADR-0011).
 */
export function readLog(edits: readonly EditEventRead[]): EditLog {
  const entries: LogEntry[] = [...edits]
    .sort((a, b) => a.seq - b.seq)
    .map((edit) => ({ edit, undoneBy: null, undoes: null, redoes: null }));
  const active: LogEntry[] = [];
  let redo: LogEntry[] = [];
  for (const entry of entries) {
    const reverts = entry.edit.reverts_edit_id;
    if (reverts) {
      let index = active.length - 1;
      while (index >= 0 && active[index]?.edit.id !== reverts) index -= 1;
      const undone = index >= 0 ? active.splice(index, 1)[0] : undefined;
      if (undone) {
        undone.undoneBy = entry.edit.seq;
        entry.undoes = undone.edit.seq;
        redo.push(undone);
      }
      continue;
    }
    active.push(entry);
    const top = redo.at(-1);
    if (top && sameEdit(top.edit, entry.edit)) {
      redo.pop();
      entry.redoes = top.edit.seq;
    } else {
      redo = [];
    }
  }
  return { entries, undo: active.at(-1)?.edit ?? null, redo: redo.at(-1)?.edit ?? null };
}

/** Un valor del log como texto («1/2», «D4»), o null si no lo es. */
const text = (value: unknown): string | null =>
  typeof value === "string" ? value : typeof value === "number" ? String(value) : null;

const record = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;

const spoken = (pitch: string) => pitchName(pitch)?.spoken ?? pitch;

/** Alteraciones del contrato (ADR-0017), por su nombre. */
const ACCIDENTAL_NAMES: Record<string, string> = {
  "": "becuadro",
  natural: "becuadro",
  "#": "sostenido",
  "##": "doble sostenido",
  x: "doble sostenido",
  b: "bemol",
  "-": "bemol",
  bb: "doble bemol",
  "--": "doble bemol",
};

/** Claves por su nombre en el contrato (`_extract_clef` del servidor). */
const CLEF_WORDS: Record<string, { sign: string; line: number }> = {
  treble: { sign: "G", line: 2 },
  sol: { sign: "G", line: 2 },
  g: { sign: "G", line: 2 },
  bass: { sign: "F", line: 4 },
  fa: { sign: "F", line: 4 },
  f: { sign: "F", line: 4 },
  alto: { sign: "C", line: 3 },
  do3: { sign: "C", line: 3 },
  c3: { sign: "C", line: 3 },
  tenor: { sign: "C", line: 4 },
  do4: { sign: "C", line: 4 },
  c4: { sign: "C", line: 4 },
};

function clefChange(after: Record<string, unknown>): string {
  const raw = "clef" in after ? after.clef : after;
  if (raw === null || raw === undefined) return "quitar el cambio de clave";
  const word = text(raw);
  const clef = word === null ? record(raw) : (CLEF_WORDS[word.trim().toLowerCase()] ?? null);
  const sign = text(clef?.sign)?.toUpperCase() ?? word?.trim().toUpperCase() ?? "";
  const line = Number(clef?.line ?? (sign === "F" ? 4 : sign === "C" ? 3 : 2));
  const known = CLEFS.find((candidate) => candidate.sign === sign && candidate.line === line);
  return known ? `clave de ${known.spoken}` : `clave ${sign} en la línea ${String(line)}`;
}

function keyChange(after: Record<string, unknown>): string {
  const raw = "key_signature" in after ? after.key_signature : "key" in after ? after.key : after;
  if (raw === null || raw === undefined) return "quitar el cambio de armadura";
  const fifths = Number(typeof raw === "number" ? raw : record(raw)?.fifths);
  if (!Number.isInteger(fifths)) return "armadura";
  return fifths === 0 ? "armadura sin alteraciones" : `armadura de ${keyName(fifths)}`;
}

/**
 * El evento de una inserción o de la instantánea de un borrado: «Re 4, negra», «un silencio de
 * negra»; un silencio invisible (ADR-0032) no se ve en la partitura, y se dice.
 */
function eventOf(payload: Record<string, unknown>): string {
  const kind = text(payload.kind) ?? "rest";
  const beats = text(payload.duration_beats);
  if (kind === "rest" && payload.hidden === true) {
    return `un silencio invisible de ${durationName(beats)}`;
  }
  return eventName(kind, text(payload.pitch), beats);
}

/**
 * Qué hace una edición del log, como lo dice la barra de corrección: «altura Re 4», «figura
 * corchea», «borrado de Mi 4, negra». Un borrado se describe por la instantánea del servidor.
 */
export function describeEdit(edit: Pick<EditEventRead, "op" | "before" | "after">): string {
  const after = record(edit.after) ?? {};
  switch (edit.op) {
    case "SetPitch": {
      const pitch = text(after.pitch);
      return pitch ? `altura ${spoken(pitch)}` : "altura";
    }
    case "SetDuration":
      return `figura ${durationName(text(after.duration_beats))}`;
    case "SetAccidental": {
      const raw = after.accidental;
      const name = ACCIDENTAL_NAMES[raw === null || raw === undefined ? "" : (text(raw) ?? "")];
      return name ? `alteración ${name}` : "alteración";
    }
    case "InsertEvent":
      return `inserción de ${eventOf(after)}`;
    case "DeleteEvent": {
      const before = record(edit.before);
      return before ? `borrado de ${eventOf(before)}` : "borrado de un evento";
    }
    case "SetClef":
      return clefChange(after);
    case "SetKey":
      return keyChange(after);
    default:
      return edit.op;
  }
}

/**
 * Dónde está lo que cambia una edición, para decirlo: «compás 2, voz 1»; la clave y la armadura
 * son del compás, sin voz. El pentagrama se cuenta en toda la partitura, sumando los de las partes
 * anteriores, como los compases marcados (`measureSlot`); sin `score`, dentro de su parte.
 */
export function placeOf(
  { op, anchor }: { op: string; anchor: AnchorPayload },
  multiStaff: boolean,
  score: ScoreIRPayload | null = null,
): string {
  const measureOnly = op === "SetClef" || op === "SetKey";
  const place = measureOnly
    ? `compás ${String(anchor.measure)}`
    : `compás ${String(anchor.measure)}, voz ${String(anchor.voice + 1)}`;
  if (!multiStaff) return place;
  const previous = (score?.parts ?? [])
    .slice(0, anchor.part)
    .reduce((total, part) => total + part.staves.length, 0);
  return `pentagrama ${String(previous + anchor.staff + 1)}, ${place}`;
}

/**
 * Si el servidor guardó lo que hace falta para deshacerla (`has_complete_before`, ADR-0017): las
 * ediciones anteriores a ADR-0017 pueden no tenerlo, y el servidor responde 422 al deshacerlas.
 * Solo elige el mensaje de ese 422: lo decide el servidor.
 */
export function hasCompleteBefore(edit: Pick<EditEventRead, "op" | "before">): boolean {
  if (edit.op === "InsertEvent") return true;
  const before = record(edit.before);
  if (!before) return false;
  const has = (...keys: string[]) => keys.some((key) => key in before);
  switch (edit.op) {
    case "SetPitch":
      return has("pitch");
    case "SetDuration":
      return has("duration_beats");
    case "SetAccidental":
      return has("accidental", "pitch");
    case "DeleteEvent":
      return ["kind", "pitch", "duration_beats"].every((key) => key in before);
    case "SetClef":
      return has("clef", "sign");
    case "SetKey":
      return has("key_signature", "key", "fifths");
    default:
      return false;
  }
}

/**
 * La compensatoria que registra el servidor al deshacer `edit` (`create_inverse_edit`): borrar lo
 * insertado, volver a insertar lo borrado con su instantánea y, el resto, volver al valor previo.
 */
export function inverseOf(edit: EditEventRead): Pick<EditEventRead, "op" | "anchor" | "after"> {
  if (edit.op === "InsertEvent") return { op: "DeleteEvent", anchor: edit.anchor, after: null };
  return {
    op: edit.op === "DeleteEvent" ? "InsertEvent" : edit.op,
    anchor: edit.anchor,
    after: edit.before,
  };
}

/**
 * Evento que queda elegido tras aplicar una edición sobre `score` (el estado en que se pide), con
 * su ancla en el estado siguiente (ADR-0011, ADR-0033): el evento cambiado, el insertado o el que
 * ocupa el sitio del borrado; undefined si la edición no mueve la selección (la clave y la
 * armadura) o si sería un silencio invisible, que no se elige (ADR-0032); null si no queda ninguno.
 */
export function historyPlacement(
  edit: Pick<EditEventRead, "op" | "anchor" | "after">,
  score: ScoreIRPayload,
): AnchorPayload | null | undefined {
  switch (edit.op) {
    case "SetClef":
    case "SetKey":
      return undefined;
    case "InsertEvent":
      return record(edit.after)?.hidden === true ? undefined : edit.anchor;
    case "DeleteEvent":
      return selectAfterDelete(score, edit.anchor);
    default: {
      const found = eventAt(score, edit.anchor);
      return found && found.event.hidden !== true ? edit.anchor : undefined;
    }
  }
}

/** Tecla de deshacer o rehacer. */
export interface KeyLike {
  key: string;
  /** Tecla física: con una distribución no latina, `key` es otra letra («я» en la Z rusa). */
  code?: string;
  shiftKey: boolean;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
}

/**
 * Ctrl+Z o ⌘Z deshacen; con Mayús, o Ctrl+Y, rehacen. ⌘Y no: es la historia del navegador en un
 * Mac. Con Alt no es de la vista (AltGr llega como Ctrl y Alt). Cuenta la letra (en un teclado
 * francés la Z está en otro sitio) y, si no es latina, la tecla física, como hace el navegador.
 */
export function historyKey(event: KeyLike): "undo" | "redo" | null {
  if (event.altKey || !(event.ctrlKey || event.metaKey)) return null;
  const latin = /^[a-z]$/i.test(event.key);
  const physical = event.code === "KeyZ" ? "z" : event.code === "KeyY" ? "y" : "";
  const key = latin ? event.key.toLowerCase() : physical;
  if (key === "z") return event.shiftKey ? "redo" : "undo";
  if (key === "y" && event.ctrlKey && !event.metaKey && !event.shiftKey) return "redo";
  return null;
}

/** Tipos de `<input>` sin texto que editar: en ellos Ctrl+Z no tiene un deshacer propio. */
const NON_TEXT_INPUTS = new Set([
  "button",
  "checkbox",
  "color",
  "file",
  "hidden",
  "image",
  "radio",
  "range",
  "reset",
  "submit",
]);

/** Si es un campo de texto, con su propio deshacer: ahí Ctrl+Z es el del navegador. */
export function isTextField(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target instanceof HTMLTextAreaElement) return true;
  if (target instanceof HTMLInputElement) return !NON_TEXT_INPUTS.has(target.type);
  return (
    target.isContentEditable ||
    target.closest("[contenteditable='true'], [contenteditable='']") !== null
  );
}
