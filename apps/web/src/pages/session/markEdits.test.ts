import { describe, expect, it } from "vitest";
import type {
  AnchorPayload,
  EditEventRead,
  MeasurePayload,
  ScoreEventPayload,
  ScoreIRPayload,
  SessionViewRead,
} from "../../types";
import { carryAnchor, editCommand, planCommand, replan, type EditTarget } from "./edits";
import { describeEdit, hasCompleteBefore, historyPlacement, placeOf } from "./history";
import { dynamicAt, spansAt } from "./markEdits";

function note(pitch: string | null, duration = "1", changes: Partial<ScoreEventPayload> = {}) {
  return {
    kind: pitch === null ? "rest" : "note",
    voice: 0,
    pitch,
    duration_beats: duration,
    tie: null,
    is_chord: false,
    bbox: null,
    confidence: null,
    ir_handle: null,
    ...changes,
  } satisfies ScoreEventPayload;
}

function anchor(measure: number, eventIndex = 0, staff = 0): AnchorPayload {
  return {
    part: 0,
    staff,
    measure,
    voice: 0,
    event_index: eventIndex,
    staff_id: `part-0-staff-${String(staff)}`,
    bbox: null,
    confidence: null,
  };
}

/** Un pentagrama de 4/4: compás 1 Do-Re-Mi(blanca), compás 2 Fa, silencio, Sol+Si (acorde). */
function score(
  changes: { first?: Partial<MeasurePayload>; second?: Partial<MeasurePayload> } = {},
): ScoreIRPayload {
  return {
    parts: [
      {
        id: "part-0",
        staves: [
          {
            id: "part-0-staff-0",
            measures: [
              {
                number: 1,
                events: [
                  note("C5", "1", {
                    articulations: ["staccato"],
                    slurs: [{ type: "start", number: 1 }],
                  }),
                  note("D5"),
                  note("E5", "2", { slurs: [{ type: "stop", number: 1 }] }),
                ],
                time_signature: { beats: 4, beat_type: 4 },
                dynamics: [{ mark: "p", offset_beats: "0" }],
                wedges: [
                  { type: "crescendo", number: 1, offset_beats: "1" },
                  { type: "stop", number: 1, offset_beats: "2" },
                ],
                ...changes.first,
              },
              {
                number: 2,
                events: [
                  note("F5"),
                  note(null),
                  note("G5", "2"),
                  note("B5", "2", { is_chord: true }),
                ],
                ...changes.second,
              },
            ],
          },
        ],
      },
    ],
  };
}

function targetAt(state: ScoreIRPayload, measure: number, eventIndex: number): EditTarget {
  const place = anchor(measure, eventIndex);
  const events = state.parts[0]?.staves[0]?.measures.find((m) => m.number === measure)?.events;
  const event = events?.[eventIndex];
  if (!event) throw new Error("sin evento");
  return { anchor: place, event, chord: event.is_chord === true };
}

const slot = (measure: number, eventIndex: number) => ({
  staff: 0,
  measure,
  voice: 0,
  event_index: eventIndex,
});

describe("articulaciones y calderón (SetNoteMarks)", () => {
  it("pone y quita una articulación con el valor final, en el orden canónico", () => {
    const state = score();
    expect(
      planCommand({ kind: "articulation", articulation: "accent" }, targetAt(state, 1, 0), state),
    ).toMatchObject({
      kind: "edit",
      op: "SetNoteMarks",
      after: { articulations: ["staccato", "accent"], fermata: false },
      anchor: anchor(1, 0),
      change: "acento en Do 5",
    });
    expect(
      planCommand({ kind: "articulation", articulation: "staccato" }, targetAt(state, 1, 0), state),
    ).toMatchObject({
      after: { articulations: [], fermata: false },
      change: "sin picado en Do 5",
    });
  });

  it("pone el calderón también en un silencio, que no lleva articulaciones", () => {
    const state = score();
    const rest = targetAt(state, 2, 1);
    expect(planCommand({ kind: "fermata" }, rest, state)).toMatchObject({
      op: "SetNoteMarks",
      after: { articulations: [], fermata: true },
      change: "calderón en el silencio de negra",
    });
    expect(
      planCommand({ kind: "articulation", articulation: "tenuto" }, rest, state),
    ).toMatchObject({
      kind: "refused",
      reason: "rest",
    });
  });

  it("el calderón de un silencio con articulaciones importadas se las quita", () => {
    const state = score({
      second: {
        events: [
          note("F5"),
          note(null, "1", { articulations: ["staccato"] }),
          note("G5", "2"),
          note("B5", "2", { is_chord: true }),
        ],
      },
    });
    expect(planCommand({ kind: "fermata" }, targetAt(state, 2, 1), state)).toMatchObject({
      after: { articulations: [], fermata: true },
    });
  });

  it("en un acorde, las marcas van en su primera nota", () => {
    const state = score();
    expect(
      planCommand({ kind: "articulation", articulation: "marcato" }, targetAt(state, 2, 3), state),
    ).toMatchObject({
      op: "SetNoteMarks",
      anchor: anchor(2, 2),
      after: { articulations: ["marcato"], fermata: false },
    });
  });
});

describe("dinámica (SetDynamic)", () => {
  it("pone, cambia y quita la dinámica en el ataque del evento elegido, anclada al compás", () => {
    const state = score();
    expect(dynamicAt(state, anchor(1, 0))).toBe("p");
    expect(dynamicAt(state, anchor(1, 2))).toBeNull();
    expect(
      planCommand({ kind: "dynamic", mark: "mf" }, targetAt(state, 1, 2), state),
    ).toMatchObject({
      op: "SetDynamic",
      after: { offset_beats: "2", mark: "mf" },
      anchor: anchor(1, 0),
      change: "dinámica mf en la nota del compás 1",
    });
    expect(
      planCommand({ kind: "dynamic", mark: null }, targetAt(state, 1, 0), state),
    ).toMatchObject({
      after: { offset_beats: "0", mark: null },
      change: "sin la dinámica p en la nota del compás 1",
    });
    expect(planCommand({ kind: "dynamic", mark: "p" }, targetAt(state, 1, 0), state)).toMatchObject(
      {
        kind: "refused",
        reason: "same",
      },
    );
  });

  it("en un acorde, la posición es la de su primera nota", () => {
    const state = score();
    expect(planCommand({ kind: "dynamic", mark: "f" }, targetAt(state, 2, 3), state)).toMatchObject(
      {
        after: { offset_beats: "2", mark: "f" },
      },
    );
  });
});

describe("ligaduras de expresión y reguladores (SetSlur, SetWedge)", () => {
  it("una ligadura va del inicio marcado al evento elegido, en el orden en que suenan, con un número libre", () => {
    const state = score();
    const plan = planCommand(
      { kind: "span", span: "slur" },
      targetAt(state, 2, 0),
      state,
      anchor(1, 1),
    );
    expect(plan).toMatchObject({
      kind: "edit",
      op: "SetSlur",
      after: { number: 2, start: slot(1, 1), stop: slot(2, 0) },
      anchor: anchor(1, 1),
      change: "ligadura de expresión de los compases 1 a 2",
    });
    // Elegir antes el final que el inicio da lo mismo.
    expect(
      planCommand({ kind: "span", span: "slur" }, targetAt(state, 1, 1), state, anchor(2, 0)),
    ).toMatchObject({
      after: { number: 2, start: slot(1, 1), stop: slot(2, 0) },
    });
  });

  it("una ligadura une dos notas distintas, y sin inicio no se crea", () => {
    const state = score();
    const span = { kind: "span", span: "slur" } as const;
    expect(planCommand(span, targetAt(state, 2, 0), state, null)).toMatchObject({
      reason: "no-origin",
    });
    expect(planCommand(span, targetAt(state, 2, 1), state, anchor(1, 1))).toMatchObject({
      reason: "span",
    });
    expect(planCommand(span, targetAt(state, 1, 1), state, anchor(1, 1))).toMatchObject({
      reason: "span",
    });
    // Un inicio que ya no está.
    expect(planCommand(span, targetAt(state, 1, 1), state, anchor(1, 7))).toMatchObject({
      reason: "no-origin",
    });
  });

  it("un regulador va del ataque del primero al final del último, también de una sola nota", () => {
    const state = score();
    expect(
      planCommand({ kind: "span", span: "diminuendo" }, targetAt(state, 2, 0), state, anchor(1, 2)),
    ).toMatchObject({
      op: "SetWedge",
      after: {
        number: 2,
        start: { staff: 0, measure: 1, offset_beats: "2", type: "diminuendo" },
        stop: { staff: 0, measure: 2, offset_beats: "1" },
      },
      anchor: anchor(1, 0),
      change: "diminuendo de los compases 1 a 2",
    });
    expect(
      planCommand({ kind: "span", span: "crescendo" }, targetAt(state, 1, 2), state, anchor(1, 2)),
    ).toMatchObject({
      after: {
        start: { measure: 1, offset_beats: "2", type: "crescendo" },
        stop: { measure: 1, offset_beats: "4" },
      },
    });
  });

  it("lista las que pasan por el evento elegido y las quita enteras por su número", () => {
    const state = score();
    expect(spansAt(state, anchor(1, 0))).toEqual([
      { mark: "slur", number: 1, kind: "slur", from: 1, until: 1 },
    ]);
    // El regulador del compás 1 va de 1 a 2 negras: cubre el Re.
    expect(spansAt(state, anchor(1, 1)).map(({ mark, kind }) => [mark, kind])).toEqual([
      ["wedge", "crescendo"],
    ]);
    expect(
      planCommand({ kind: "unspan", mark: "slur", number: 1 }, targetAt(state, 1, 2), state),
    ).toMatchObject({
      op: "SetSlur",
      after: { number: 1, start: null, stop: null },
      anchor: anchor(1, 0),
      change: "quitar la ligadura de expresión en el compás 1",
    });
    expect(
      planCommand({ kind: "unspan", mark: "wedge", number: 1 }, targetAt(state, 1, 1), state),
    ).toMatchObject({
      op: "SetWedge",
      after: { number: 1, start: null, stop: null },
      anchor: anchor(1, 0),
      change: "quitar el crescendo en el compás 1",
    });
    expect(
      planCommand({ kind: "unspan", mark: "slur", number: 9 }, targetAt(state, 1, 1), state),
    ).toMatchObject({
      kind: "refused",
    });
  });

  it("también lista y quita un extremo suelto", () => {
    const state = score({
      first: {
        events: [
          note("C5", "1", { slurs: [{ type: "start", number: 1 }] }),
          note("D5"),
          note("E5", "2"),
        ],
      },
    });
    const [orphan] = spansAt(state, anchor(1, 0));
    expect(orphan).toEqual({ mark: "slur", number: 1, kind: "slur", from: 1, until: null });
    expect(
      planCommand({ kind: "unspan", mark: "slur", number: 1 }, targetAt(state, 1, 0), state),
    ).toMatchObject({
      change: "quitar la ligadura de expresión sin fin del compás 1",
    });
  });
});

describe("teclado de las marcas", () => {
  const key = (value: string, extra: Partial<KeyboardEventInit> = {}) =>
    editCommand({
      key: value,
      shiftKey: false,
      ctrlKey: false,
      metaKey: false,
      altKey: false,
      ...extra,
    });

  it("P, A, M y T las articulaciones; C el calderón; I el inicio; L, < y > ligadura y reguladores", () => {
    expect(key("p")).toEqual({ kind: "articulation", articulation: "staccato" });
    expect(key("A", { shiftKey: true })).toEqual({ kind: "articulation", articulation: "accent" });
    expect(key("m")).toEqual({ kind: "articulation", articulation: "marcato" });
    expect(key("t")).toEqual({ kind: "articulation", articulation: "tenuto" });
    expect(key("c")).toEqual({ kind: "fermata" });
    expect(key("i")).toEqual({ kind: "origin" });
    expect(key("l")).toEqual({ kind: "span", span: "slur" });
    expect(key("<")).toEqual({ kind: "span", span: "crescendo" });
    expect(key(">", { shiftKey: true })).toEqual({ kind: "span", span: "diminuendo" });
    // Con Ctrl, ⌘ o Alt nada es de la vista (Ctrl+C copia, Ctrl+P imprime).
    expect(key("c", { ctrlKey: true })).toBeNull();
    expect(key("p", { metaKey: true })).toBeNull();
  });
});

function edit(op: string, before: unknown, after: unknown, at = anchor(1, 0)): EditEventRead {
  return {
    id: "e1",
    session_id: "s",
    seq: 1,
    op: op,
    author: "ana",
    anchor: at,
    before: before as EditEventRead["before"],
    after: after as EditEventRead["after"],
    reverts_edit_id: null,
    created_at: "2026-10-31T10:00:00",
  };
}

describe("las ediciones de marcas en el historial", () => {
  it("se dicen por lo que cambian", () => {
    expect(
      describeEdit(
        edit(
          "SetNoteMarks",
          { articulations: ["staccato"], fermata: false },
          { articulations: ["accent"], fermata: true },
        ),
      ),
    ).toBe("acento, calderón y sin picado");
    expect(
      describeEdit(
        edit("SetDynamic", { offset_beats: "0", mark: null }, { offset_beats: "0", mark: "mf" }),
      ),
    ).toBe("dinámica mf");
    expect(
      describeEdit(
        edit("SetDynamic", { offset_beats: "0", mark: "p" }, { offset_beats: "0", mark: null }),
      ),
    ).toBe("sin la dinámica p");
    expect(
      describeEdit(
        edit(
          "SetSlur",
          { number: 2, start: null, stop: null },
          { number: 2, start: slot(1, 1), stop: slot(2, 0) },
        ),
      ),
    ).toBe("ligadura de expresión de los compases 1 a 2");
    expect(
      describeEdit(
        edit(
          "SetWedge",
          {
            number: 1,
            start: { staff: 0, measure: 1, offset_beats: "1", type: "crescendo" },
            stop: { staff: 0, measure: 1, offset_beats: "2" },
          },
          { number: 1, start: null, stop: null },
        ),
      ),
    ).toBe("quitar el crescendo en el compás 1");
  });

  it("la dinámica y el regulador son del compás; la ligadura y las articulaciones, de su voz", () => {
    expect(placeOf({ op: "SetDynamic", anchor: anchor(2) }, false)).toBe("compás 2");
    expect(placeOf({ op: "SetWedge", anchor: anchor(2) }, false)).toBe("compás 2");
    expect(placeOf({ op: "SetSlur", anchor: anchor(2) }, false)).toBe("compás 2, voz 1");
  });

  it("se pueden deshacer con la instantánea del servidor y no mueven la selección, salvo las de nota", () => {
    expect(
      hasCompleteBefore(edit("SetNoteMarks", { articulations: [], fermata: false }, null)),
    ).toBe(true);
    expect(hasCompleteBefore(edit("SetSlur", { number: 1 }, null))).toBe(false);
    const state = score();
    expect(
      historyPlacement(
        edit("SetSlur", null, { number: 2, start: slot(1, 1), stop: slot(2, 0) }),
        state,
      ),
    ).toBeUndefined();
    expect(
      historyPlacement(edit("SetDynamic", null, { offset_beats: "0", mark: "f" }), state),
    ).toBeUndefined();
    expect(
      historyPlacement(
        edit("SetNoteMarks", null, { articulations: [], fermata: true }, anchor(1, 1)),
        state,
      ),
    ).toEqual(anchor(1, 1));
  });
});

describe("tras un 409, la misma marca sobre el estado recargado", () => {
  function view(state: ScoreIRPayload, edits: EditEventRead[]): SessionViewRead {
    return {
      session_id: "s",
      document_id: "d",
      omr_engine: "homr",
      findings: [],
      edits,
      current_score: state,
      current_seq: edits.length,
      image_artifact: "img",
      status: "correcting",
      condition: "assisted",
      test_score_id: null,
      owner_id: "u",
    };
  }

  it("las marcas no mueven las anclas", () => {
    const inserted = edit("SetSlur", null, { number: 2, start: slot(1, 0), stop: slot(1, 1) });
    expect(carryAnchor(anchor(1, 2), 0, view(score(), [inserted]))).toEqual(anchor(1, 2));
  });

  it("una ligadura nueva se vuelve a pedir entre las mismas notas, llevadas al estado nuevo, con otro número", () => {
    const state = score();
    // Otra pestaña insertó una nota al principio del compás 1 y creó la ligadura 2.
    const shifted = score({
      first: {
        events: [
          note("A4"),
          note("C5", "1", { slurs: [{ type: "start", number: 1 }] }),
          note("D5", "1", { slurs: [{ type: "start", number: 2 }] }),
          note("E5", "2", {
            slurs: [
              { type: "stop", number: 1 },
              { type: "stop", number: 2 },
            ],
          }),
        ],
      },
    });
    const first = planCommand(
      { kind: "span", span: "slur" },
      targetAt(state, 2, 0),
      state,
      anchor(1, 1),
    );
    if (first.kind !== "edit") throw new Error("sin plan");
    const request = { ...first, anchor: first.anchor ?? anchor(1, 1), baseSeq: 0 };
    const reloaded = view(shifted, [
      edit("InsertEvent", null, { kind: "note", pitch: "A4", duration_beats: "1" }),
      edit("SetSlur", null, { number: 2, start: slot(1, 2), stop: slot(1, 3) }),
    ]);
    const { plan, anchor: carried } = replan(request, reloaded);
    expect(carried).toEqual(anchor(2, 0));
    expect(plan).toMatchObject({
      kind: "edit",
      op: "SetSlur",
      after: { number: 3, start: slot(1, 2), stop: slot(2, 0) },
    });
  });

  it("quitar una ligadura no se vuelve a aplicar si su número ya es de otra", () => {
    const state = score();
    const removal = planCommand(
      { kind: "unspan", mark: "slur", number: 1 },
      targetAt(state, 1, 0),
      state,
    );
    if (removal.kind !== "edit") throw new Error("sin plan");
    const request = { ...removal, anchor: removal.anchor ?? anchor(1, 0), baseSeq: 0 };
    // Otra pestaña la quitó y creó otra ligadura 1, del Re al Mi.
    const other = score({
      first: {
        events: [
          note("C5", "1", { articulations: ["staccato"] }),
          note("D5", "1", { slurs: [{ type: "start", number: 1 }] }),
          note("E5", "2", { slurs: [{ type: "stop", number: 1 }] }),
        ],
      },
    });
    expect(replan(request, view(other, [])).plan).toMatchObject({ kind: "edit" });
    const elsewhere = score({
      first: {
        events: [
          note("C5", "1", { articulations: ["staccato"] }),
          note("D5"),
          note("E5", "2", { slurs: [{ type: "start", number: 1 }] }),
        ],
      },
      second: {
        events: [
          note("F5", "1", { slurs: [{ type: "stop", number: 1 }] }),
          note(null),
          note("G5", "2"),
          note("B5", "2", { is_chord: true }),
        ],
      },
    });
    expect(replan(request, view(elsewhere, [])).plan).toMatchObject({
      kind: "refused",
      message: "Ya no está la ligadura de expresión en el compás 1: elígela de nuevo.",
    });
  });

  it("las marcas de nota y la dinámica piden el mismo valor final; si ya lo tienen, nada", () => {
    const state = score();
    const marks = planCommand({ kind: "fermata" }, targetAt(state, 1, 1), state);
    if (marks.kind !== "edit") throw new Error("sin plan");
    const done = score({
      first: {
        events: [
          note("C5", "1", { articulations: ["staccato"], slurs: [{ type: "start", number: 1 }] }),
          note("D5", "1", { fermata: true }),
          note("E5", "2", { slurs: [{ type: "stop", number: 1 }] }),
        ],
      },
    });
    const request = { ...marks, anchor: marks.anchor ?? anchor(1, 1), baseSeq: 0 };
    expect(replan(request, view(state, [])).plan).toMatchObject({
      kind: "edit",
      op: "SetNoteMarks",
    });
    expect(replan(request, view(done, [])).plan).toMatchObject({ kind: "refused", reason: "same" });

    const dynamic = planCommand({ kind: "dynamic", mark: "ff" }, targetAt(state, 2, 0), state);
    if (dynamic.kind !== "edit") throw new Error("sin plan");
    const again = replan(
      { ...dynamic, anchor: dynamic.anchor ?? anchor(2, 0), baseSeq: 0 },
      view(state, []),
    );
    expect(again.plan).toMatchObject({
      op: "SetDynamic",
      after: { offset_beats: "0", mark: "ff" },
    });
  });
});
