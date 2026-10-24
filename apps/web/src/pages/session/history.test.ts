import { describe, expect, it } from "vitest";
import type { AnchorPayload, EditEventRead, ScoreIRPayload } from "../../types";
import {
  describeEdit,
  hasCompleteBefore,
  historyKey,
  historyPlacement,
  isTextField,
  placeOf,
  readLog,
} from "./history";

const anchor = (measure = 2, eventIndex = 0, voice = 0): AnchorPayload => ({
  part: 0,
  staff: 0,
  measure,
  voice,
  event_index: eventIndex,
  staff_id: "part-0-staff-0",
  bbox: null,
  confidence: null,
});

/** Edición del log como la devuelve la API; `reverts` hace de ella una compensatoria. */
function edit(
  seq: number,
  op: string,
  after: Record<string, unknown> | null,
  changes: Partial<EditEventRead> = {},
): EditEventRead {
  return {
    id: `edit-${String(seq)}`,
    session_id: "s",
    seq,
    op,
    author: "ana",
    anchor: anchor(),
    before: null,
    after,
    reverts_edit_id: null,
    created_at: "2026-10-24T10:00:00Z",
    ...changes,
  };
}

const pitch = (seq: number, value: string, before = "C4") =>
  edit(seq, "SetPitch", { pitch: value }, { before: { pitch: before } });
/** Compensatoria de `target`, como la registra `POST /undo`. */
const undoOf = (seq: number, target: EditEventRead) =>
  edit(seq, target.op, target.before, { before: target.after, reverts_edit_id: target.id });

describe("readLog: deshacer y rehacer sobre el log (ADR-0007)", () => {
  it("sin ediciones no hay nada que deshacer ni rehacer", () => {
    expect(readLog([])).toEqual({ entries: [], undo: null, redo: null });
  });

  it("deshace la última edición vigente, como el servidor, y apila lo deshecho para rehacerlo", () => {
    const first = pitch(1, "D4");
    const second = pitch(2, "E4", "D4");
    const log = readLog([first, second, undoOf(3, second)]);
    expect(log.undo).toBe(first);
    expect(log.redo).toBe(second);

    const both = readLog([first, second, undoOf(3, second), undoOf(4, first)]);
    expect(both.undo).toBeNull();
    // Se rehace en orden inverso: primero lo último que se deshizo.
    expect(both.redo).toBe(first);
  });

  it("lee el log en orden de seq aunque llegue en otro", () => {
    const first = pitch(1, "D4");
    const second = pitch(2, "E4", "D4");
    expect(readLog([undoOf(3, second), second, first]).undo).toBe(first);
  });

  it("rehacer es la misma edición otra vez: saca lo deshecho de la pila y se vuelve a poder deshacer", () => {
    const first = pitch(1, "D4");
    const second = pitch(2, "E4", "D4");
    const redone = { ...second, id: "edit-5", seq: 5 };
    const log = readLog([first, second, undoOf(3, second), undoOf(4, first), pitch(6, "D4")]);
    // La edición 6 vuelve a enviar la 1 (misma operación, ancla y valor): la siguiente es la 2.
    expect(log.redo).toBe(second);
    expect(log.undo?.seq).toBe(6);
    expect(log.entries.find((entry) => entry.edit.seq === 6)?.redoes).toBe(1);

    const again = readLog([first, second, undoOf(3, second), redone]);
    expect(again.redo).toBeNull();
    expect(again.undo).toBe(redone);
  });

  it("una edición nueva, distinta de la que se desharía, vacía la pila de rehacer", () => {
    const first = pitch(1, "D4");
    const log = readLog([first, undoOf(2, first), pitch(3, "F4")]);
    expect(log.redo).toBeNull();
    expect(log.undo?.seq).toBe(3);
    // Otra ancla, aunque el valor sea el mismo, es otra edición.
    const elsewhere = edit(3, "SetPitch", { pitch: "D4" }, { anchor: anchor(3) });
    expect(readLog([first, undoOf(2, first), elsewhere]).redo).toBeNull();
  });

  it("compara el ancla por su posición, no por la caja ni la confianza", () => {
    const first = pitch(1, "D4");
    const same = edit(
      3,
      "SetPitch",
      { pitch: "D4" },
      { anchor: { ...anchor(), bbox: [1, 2, 3, 4] } },
    );
    expect(readLog([first, undoOf(2, first), same]).redo).toBeNull();
    expect(readLog([first, undoOf(2, first), same]).entries[2]?.redoes).toBe(1);
  });

  it("compara los valores sin depender del orden de sus claves", () => {
    const first = edit(1, "InsertEvent", { kind: "note", duration_beats: "1", pitch: "C4" });
    const same = edit(3, "InsertEvent", { pitch: "C4", kind: "note", duration_beats: "1" });
    expect(readLog([first, undoOf(2, first), same]).entries[2]?.redoes).toBe(1);
  });

  it("marca lo deshecho, lo que deshace y lo que rehace", () => {
    const first = pitch(1, "D4");
    const log = readLog([first, undoOf(2, first), pitch(3, "D4")]);
    expect(
      log.entries.map(({ edit: { seq }, undoneBy, undoes, redoes }) => ({
        seq,
        undoneBy,
        undoes,
        redoes,
      })),
    ).toEqual([
      { seq: 1, undoneBy: 2, undoes: null, redoes: null },
      { seq: 2, undoneBy: null, undoes: 1, redoes: null },
      { seq: 3, undoneBy: null, undoes: null, redoes: 1 },
    ]);
  });

  it("una compensatoria de una edición que no está vigente no cambia nada", () => {
    const first = pitch(1, "D4");
    const stray = edit(2, "SetPitch", { pitch: "C4" }, { reverts_edit_id: "otra" });
    const log = readLog([first, stray]);
    expect(log.undo).toBe(first);
    expect(log.redo).toBeNull();
    expect(log.entries[1]?.undoes).toBeNull();
  });
});

describe("describeEdit", () => {
  it("dice qué cambia cada operación, como la barra de corrección", () => {
    expect(describeEdit(pitch(1, "F#4"))).toBe("altura Fa sostenido 4");
    expect(describeEdit(edit(1, "SetDuration", { duration_beats: "1/2" }))).toBe("figura corchea");
    expect(describeEdit(edit(1, "SetAccidental", { accidental: "#" }))).toBe(
      "alteración sostenido",
    );
    expect(describeEdit(edit(1, "SetAccidental", { accidental: "natural" }))).toBe(
      "alteración becuadro",
    );
    expect(describeEdit(edit(1, "SetAccidental", { accidental: "--" }))).toBe(
      "alteración doble bemol",
    );
    expect(
      describeEdit(edit(1, "InsertEvent", { kind: "note", pitch: "D4", duration_beats: "1" })),
    ).toBe("inserción de Re 4, negra");
    expect(describeEdit(edit(1, "InsertEvent", { kind: "rest", duration_beats: "2" }))).toBe(
      "inserción de un silencio de blanca",
    );
  });

  it("un borrado se describe por la instantánea que guardó el servidor", () => {
    const deleted = edit(1, "DeleteEvent", null, {
      before: { kind: "note", pitch: "E4", duration_beats: "1", tie: null, is_chord: false },
    });
    expect(describeEdit(deleted)).toBe("borrado de Mi 4, negra");
    expect(describeEdit(edit(1, "DeleteEvent", null))).toBe("borrado de un evento");
  });

  it("la clave y la armadura, también cuando se quita el cambio del compás", () => {
    expect(describeEdit(edit(1, "SetClef", { sign: "F", line: 4 }))).toBe("clave de fa");
    expect(describeEdit(edit(1, "SetClef", { clef: { sign: "C", line: 3 } }))).toBe(
      "clave de do en tercera",
    );
    expect(describeEdit(edit(1, "SetClef", { clef: "treble" }))).toBe("clave de sol");
    expect(describeEdit(edit(1, "SetClef", { clef: null }))).toBe("quitar el cambio de clave");
    expect(describeEdit(edit(1, "SetKey", { fifths: 2, mode: "major" }))).toBe(
      "armadura de 2 sostenidos",
    );
    expect(describeEdit(edit(1, "SetKey", { key_signature: { fifths: -1 } }))).toBe(
      "armadura de 1 bemol",
    );
    expect(describeEdit(edit(1, "SetKey", { key: 0 }))).toBe("armadura sin alteraciones");
    expect(describeEdit(edit(1, "SetKey", { key_signature: null }))).toBe(
      "quitar el cambio de armadura",
    );
  });
});

describe("placeOf", () => {
  it("dice el compás y la voz, y el compás solo en la clave y la armadura", () => {
    expect(placeOf({ op: "SetPitch", anchor: anchor(2, 1, 1) }, false)).toBe("compás 2, voz 2");
    expect(placeOf({ op: "SetClef", anchor: anchor(3) }, false)).toBe("compás 3");
    expect(placeOf({ op: "SetKey", anchor: { ...anchor(3), staff: 1 } }, true)).toBe(
      "pentagrama 2, compás 3",
    );
  });
});

describe("hasCompleteBefore: si el servidor puede deshacerla (ADR-0017)", () => {
  it("como el servidor: cada operación necesita su estado previo", () => {
    expect(hasCompleteBefore(edit(1, "InsertEvent", { kind: "rest", duration_beats: "1" }))).toBe(
      true,
    );
    expect(hasCompleteBefore(edit(1, "SetPitch", { pitch: "D4" }))).toBe(false);
    expect(hasCompleteBefore(pitch(1, "D4"))).toBe(true);
    expect(
      hasCompleteBefore(edit(1, "DeleteEvent", null, { before: { kind: "rest", pitch: null } })),
    ).toBe(false);
    expect(
      hasCompleteBefore(
        edit(1, "DeleteEvent", null, {
          before: { kind: "rest", pitch: null, duration_beats: "1" },
        }),
      ),
    ).toBe(true);
    expect(hasCompleteBefore(edit(1, "SetClef", { clef: null }, { before: { clef: null } }))).toBe(
      true,
    );
    expect(hasCompleteBefore(edit(1, "SetKey", { fifths: 1 }, { before: { fifths: 0 } }))).toBe(
      true,
    );
    expect(hasCompleteBefore(edit(1, "SetAccidental", { accidental: "#" }, { before: {} }))).toBe(
      false,
    );
  });
});

describe("historyKey", () => {
  const press = (
    key: string,
    modifiers: Partial<Record<"ctrl" | "meta" | "shift" | "alt", boolean>>,
  ) =>
    historyKey({
      key,
      ctrlKey: modifiers.ctrl ?? false,
      metaKey: modifiers.meta ?? false,
      shiftKey: modifiers.shift ?? false,
      altKey: modifiers.alt ?? false,
    });

  it("Ctrl+Z o ⌘Z deshacen; con Mayús, o Ctrl+Y, rehacen", () => {
    expect(press("z", { ctrl: true })).toBe("undo");
    expect(press("z", { meta: true })).toBe("undo");
    expect(press("Z", { ctrl: true, shift: true })).toBe("redo");
    expect(press("Z", { meta: true, shift: true })).toBe("redo");
    expect(press("y", { ctrl: true })).toBe("redo");
    // Con Bloq Mayús la letra llega en mayúscula.
    expect(press("Z", { ctrl: true })).toBe("undo");
  });

  it("no toma lo que no es suyo", () => {
    expect(press("z", {})).toBeNull();
    expect(press("z", { shift: true })).toBeNull();
    // ⌘Y es la historia del navegador en un Mac.
    expect(press("y", { meta: true })).toBeNull();
    // AltGr llega como Ctrl y Alt.
    expect(press("z", { ctrl: true, alt: true })).toBeNull();
    expect(press("x", { ctrl: true })).toBeNull();
  });
});

describe("isTextField", () => {
  it("los campos de texto tienen su propio deshacer; los botones y los desplegables, no", () => {
    const field = (html: string) => {
      const host = document.createElement("div");
      host.innerHTML = html;
      return host.firstElementChild;
    };
    expect(isTextField(field("<input>"))).toBe(true);
    expect(isTextField(field('<input type="number">'))).toBe(true);
    expect(isTextField(field("<textarea></textarea>"))).toBe(true);
    expect(isTextField(field('<div contenteditable="true"></div>'))).toBe(true);
    expect(isTextField(field('<input type="checkbox">'))).toBe(false);
    expect(isTextField(field('<input type="range">'))).toBe(false);
    expect(isTextField(field("<button>Deshacer</button>"))).toBe(false);
    expect(isTextField(field("<select></select>"))).toBe(false);
    expect(isTextField(document.body)).toBe(false);
    expect(isTextField(null)).toBe(false);
  });
});

describe("historyPlacement: qué queda elegido tras deshacer o rehacer (ADR-0011)", () => {
  const event = (pitchValue: string | null, hidden = false) => ({
    kind: pitchValue === null ? "rest" : "note",
    voice: 0,
    pitch: pitchValue,
    duration_beats: "1",
    tie: null,
    is_chord: false,
    bbox: null,
    confidence: null,
    ir_handle: null,
    hidden,
  });
  const score = (events: ReturnType<typeof event>[]): ScoreIRPayload =>
    ({
      parts: [
        {
          id: "part-0",
          staves: [
            {
              id: "part-0-staff-0",
              measures: [
                { number: 1, events: [event("C4")] },
                { number: 2, events },
              ],
            },
          ],
        },
      ],
    }) as unknown as ScoreIRPayload;

  it("un cambio de valor deja elegido su evento; la clave y la armadura no mueven nada", () => {
    const current = score([event("C4"), event("D4")]);
    expect(
      historyPlacement({ op: "SetPitch", anchor: anchor(2, 1), after: null }, current),
    ).toEqual(anchor(2, 1));
    expect(
      historyPlacement({ op: "SetClef", anchor: anchor(2), after: { clef: null } }, current),
    ).toBeUndefined();
    expect(
      historyPlacement({ op: "SetKey", anchor: anchor(2), after: { fifths: 1 } }, current),
    ).toBeUndefined();
  });

  it("una inserción deja elegido el evento nuevo, salvo un silencio invisible (ADR-0032)", () => {
    const current = score([event("C4")]);
    expect(
      historyPlacement(
        { op: "InsertEvent", anchor: anchor(2), after: { kind: "note", pitch: "D4" } },
        current,
      ),
    ).toEqual(anchor(2));
    expect(
      historyPlacement(
        { op: "InsertEvent", anchor: anchor(2), after: { kind: "rest", hidden: true } },
        current,
      ),
    ).toBeUndefined();
  });

  it("un borrado deja elegido el que ocupa su sitio, sin elegir un silencio invisible", () => {
    const current = score([event("C4"), event(null, true), event("E4")]);
    expect(
      historyPlacement({ op: "DeleteEvent", anchor: anchor(2), after: null }, current),
    ).toEqual(anchor(2, 1));
    const last = score([event("C4")]);
    // Sin nada más en el compás, el último del anterior.
    expect(historyPlacement({ op: "DeleteEvent", anchor: anchor(2), after: null }, last)).toEqual(
      anchor(1),
    );
  });

  it("un cambio de valor sobre un silencio invisible no lo elige", () => {
    const current = score([event(null, true), event("D4")]);
    expect(
      historyPlacement({ op: "SetDuration", anchor: anchor(2), after: null }, current),
    ).toBeUndefined();
  });
});
