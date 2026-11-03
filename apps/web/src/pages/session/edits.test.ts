import { describe, expect, it } from "vitest";
import type {
  AnchorPayload,
  EditEventRead,
  ScoreEventPayload,
  ScoreIRPayload,
  SessionDetailRead,
} from "../../types";
import {
  accidentalOf,
  activeClef,
  activeFifths,
  carryAnchor,
  CLEFS,
  editCommand,
  eventAt,
  figureDuration,
  figureOf,
  FIGURES,
  keyName,
  octavePitch,
  planAgain,
  planClef,
  planCommand,
  planDelete,
  planEdit,
  planInsert,
  planKey,
  replan,
  stepPitch,
  withAccidental,
  type DecidedEdit,
  type ValueCommand,
  type EditRequestLike,
  type EditTarget,
} from "./edits";

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

function anchor(measure: number, eventIndex = 0, voice = 0): AnchorPayload {
  return {
    part: 0,
    staff: 0,
    measure,
    voice,
    event_index: eventIndex,
    staff_id: "part-0-staff-0",
    bbox: null,
    confidence: null,
  };
}

/** Partitura de un pentagrama con los compases dados, cada uno con su armadura (o sin ella). */
function score(
  measures: { events: ScoreEventPayload[]; fifths?: number | null }[],
): ScoreIRPayload {
  return {
    parts: [
      {
        id: "part-0",
        staves: [
          {
            id: "part-0-staff-0",
            measures: measures.map((measure, index) => ({
              number: index + 1,
              events: measure.events,
              key_signature:
                measure.fifths === undefined || measure.fifths === null
                  ? null
                  : { fifths: measure.fifths, mode: "major" },
            })),
          },
        ],
      },
    ],
  };
}

function target(event: ScoreEventPayload, chord = false): EditTarget {
  return { anchor: anchor(1), event, chord };
}

describe("subir y bajar la altura un paso dentro de la armadura", () => {
  it.each([
    ["E4", 1, 0, "F4"],
    ["B4", 1, 0, "C5"],
    ["C4", -1, 0, "B3"],
    // Sol mayor: el Fa lleva el sostenido de la armadura.
    ["E4", 1, 1, "F#4"],
    ["G4", -1, 1, "F#4"],
    // Fa mayor: el Si es bemol.
    ["A4", 1, -1, "Bb4"],
    // Una alteración accidental no se arrastra: el paso cae en la nota de la armadura.
    ["F#4", 1, 0, "G4"],
    ["Bb3", -1, 0, "A3"],
    // Las grafías de music21 también se entienden.
    ["B-3", 1, 0, "C4"],
    // Do# mayor y Dob mayor, los extremos de la armadura.
    ["A4", 1, 7, "B#4"],
    ["G4", 1, -7, "Ab4"],
  ] as const)("%s, %i paso con %i quintas, es %s", (pitch, direction, fifths, expected) => {
    expect(stepPitch(pitch, direction, fifths)).toBe(expected);
  });

  it("no sale del registro admitido (octavas de 0 a 9, MIDI de 0 a 127)", () => {
    expect(stepPitch("G9", 1, 0)).toBeNull();
    expect(stepPitch("C0", -1, 0)).toBeNull();
    expect(stepPitch("F9", 1, 0)).toBe("G9");
  });

  it("no inventa una altura que no entiende", () => {
    expect(stepPitch("H4", 1, 0)).toBeNull();
    expect(stepPitch(null, 1, 0)).toBeNull();
  });
});

describe("subir y bajar una octava", () => {
  it("conserva la letra y la alteración", () => {
    expect(octavePitch("F#4", 1)).toBe("F#5");
    expect(octavePitch("Bb3", -1)).toBe("Bb2");
    expect(octavePitch("C##4", 1)).toBe("C##5");
  });

  it("no sale del registro admitido", () => {
    expect(octavePitch("A8", 1)).toBeNull();
    expect(octavePitch("G8", 1)).toBe("G9");
    expect(octavePitch("B0", -1)).toBeNull();
  });
});

describe("alteraciones", () => {
  it.each([
    ["C4", ""],
    ["F#5", "#"],
    ["Bb3", "b"],
    ["B-3", "b"],
    ["Cx4", "##"],
    ["C##4", "##"],
    ["E--4", "bb"],
  ] as const)("%s lleva «%s»", (pitch, accidental) => {
    expect(accidentalOf(pitch)).toBe(accidental);
  });

  it("cambia la alteración y conserva la letra y la octava", () => {
    expect(withAccidental("F4", "#")).toBe("F#4");
    expect(withAccidental("F#4", "")).toBe("F4");
    expect(withAccidental("B-3", "bb")).toBe("Bbb3");
  });

  it("no da una altura fuera del rango MIDI", () => {
    expect(withAccidental("G9", "#")).toBeNull();
    expect(withAccidental("G9", "b")).toBe("Gb9");
  });
});

describe("figuras y puntillo", () => {
  it("ofrece siete figuras, de la semifusa a la redonda, con las teclas del 1 al 7", () => {
    expect(FIGURES.map((figure) => [figure.key, figure.name])).toEqual([
      ["1", "Semifusa"],
      ["2", "Fusa"],
      ["3", "Semicorchea"],
      ["4", "Corchea"],
      ["5", "Negra"],
      ["6", "Blanca"],
      ["7", "Redonda"],
    ]);
  });

  it.each([
    ["1", 4, false, false],
    ["3/2", 4, true, false],
    ["2/4", 3, false, false],
    ["6", 6, true, false],
    ["1/16", 0, false, false],
    ["3/32", 0, true, false],
    // Una figura de tresillo es su figura (#241): la corchea de tresillo, una corchea.
    ["1/3", 3, false, true],
    ["2/3", 4, false, true],
    ["1/24", 0, false, true],
    // Ni una duración partida ni una nota de adorno son una figura.
    ["5/4", null, false, false],
    ["2/9", null, false, false],
    ["0", null, false, false],
    [null, null, false, false],
  ] as const)(
    "%s es la figura %s con puntillo %s y tresillo %s",
    (duration, figure, dotted, triplet) => {
      expect(figureOf(duration)).toEqual({ figure, dotted, triplet });
    },
  );

  it("calcula la duración de una figura, con puntillo o sin él", () => {
    expect(figureDuration(4, false)).toBe("1");
    expect(figureDuration(4, true)).toBe("3/2");
    expect(figureDuration(3, true)).toBe("3/4");
    expect(figureDuration(6, true)).toBe("6");
    expect(figureDuration(0, true)).toBe("3/32");
  });
});

describe("el evento de un ancla", () => {
  const voices = score([
    {
      events: [
        note("C4"),
        note("E4", "1", { is_chord: true }),
        note("G4", "1", { voice: 1 }),
        note(null),
      ],
    },
  ]);

  it("cuenta los eventos de su voz en el compás, como el mapa de tiempos", () => {
    expect(eventAt(voices, anchor(1, 0, 1))?.event.pitch).toBe("G4");
    expect(eventAt(voices, anchor(1, 2, 0))?.event.kind).toBe("rest");
  });

  it("dice si es de un acorde, también la nota que lo empieza", () => {
    expect(eventAt(voices, anchor(1, 0))?.chord).toBe(true);
    expect(eventAt(voices, anchor(1, 1))?.chord).toBe(true);
    expect(eventAt(voices, anchor(1, 2))?.chord).toBe(false);
  });

  it("no encuentra lo que no existe", () => {
    expect(eventAt(voices, anchor(1, 3))).toBeNull();
    expect(eventAt(voices, anchor(2))).toBeNull();
    expect(eventAt(voices, { ...anchor(1), staff: 1 })).toBeNull();
  });
});

describe("la armadura activa", () => {
  it("es la última que aparece hasta el compás, en su pentagrama", () => {
    const keys = score([
      { events: [note("C4")], fifths: 2 },
      { events: [note("C4")] },
      { events: [note("C4")], fifths: -3 },
      { events: [note("C4")] },
    ]);
    expect(activeFifths(keys, anchor(1))).toBe(2);
    expect(activeFifths(keys, anchor(2))).toBe(2);
    expect(activeFifths(keys, anchor(4))).toBe(-3);
  });

  it("sin armadura es Do mayor", () => {
    expect(activeFifths(score([{ events: [note("C4")] }]), anchor(1))).toBe(0);
  });
});

describe("qué edición pide cada orden", () => {
  const step = (direction: 1 | -1): ValueCommand => ({ kind: "step", direction });

  it("una altura, con la grafía de la armadura", () => {
    expect(planEdit(step(1), target(note("E4")), 1)).toMatchObject({
      kind: "edit",
      op: "SetPitch",
      after: { pitch: "F#4" },
      change: "altura Fa sostenido 4",
    });
    expect(planEdit({ kind: "octave", direction: -1 }, target(note("E4")), 0)).toMatchObject({
      op: "SetPitch",
      after: { pitch: "E3" },
    });
  });

  it("una alteración, con su nombre del contrato (el becuadro es «natural»)", () => {
    expect(planEdit({ kind: "accidental", accidental: "#" }, target(note("F4")), 0)).toMatchObject({
      op: "SetAccidental",
      after: { accidental: "#" },
      change: "alteración: Fa sostenido 4",
    });
    expect(planEdit({ kind: "accidental", accidental: "" }, target(note("F#4")), 0)).toMatchObject({
      op: "SetAccidental",
      after: { accidental: "natural" },
      change: "alteración: Fa 4",
    });
  });

  it("una figura conserva el puntillo, y el puntillo conserva la figura", () => {
    expect(planEdit({ kind: "figure", figure: 3 }, target(note("C4", "3/2")), 0)).toMatchObject({
      op: "SetDuration",
      after: { duration_beats: "3/4" },
      change: "figura corchea con puntillo",
    });
    expect(planEdit({ kind: "dot" }, target(note("C4", "3/2")), 0)).toMatchObject({
      op: "SetDuration",
      after: { duration_beats: "1" },
    });
    expect(planEdit({ kind: "dot" }, target(note(null, "1/2")), 0)).toMatchObject({
      op: "SetDuration",
      after: { duration_beats: "3/4" },
    });
  });

  it("una figura sobre una duración que no lo es (adorno, partida) la deja sin puntillo", () => {
    expect(planEdit({ kind: "figure", figure: 4 }, target(note("C4", "5/4")), 0)).toMatchObject({
      after: { duration_beats: "1" },
    });
    expect(planEdit({ kind: "figure", figure: 4 }, target(note("C4", "0")), 0)).toMatchObject({
      after: { duration_beats: "1" },
    });
  });

  it("la figura de una nota de tresillo conserva el tresillo, que no lleva puntillo (#241)", () => {
    expect(planEdit({ kind: "figure", figure: 4 }, target(note("C4", "1/3")), 0)).toMatchObject({
      after: { duration_beats: "2/3" },
      change: "figura negra de tresillo",
    });
    expect(planEdit({ kind: "figure", figure: 3 }, target(note("C4", "1/3")), 0)).toMatchObject({
      kind: "refused",
      reason: "same",
    });
    expect(planEdit({ kind: "dot" }, target(note("C4", "1/3")), 0)).toEqual({
      kind: "refused",
      reason: "triplet-dot",
      message: "Una figura de tresillo no lleva puntillo: quita antes el tresillo.",
    });
    expect(figureDuration(3, false, true)).toBe("1/3");
  });

  it.each<[string, ValueCommand, EditTarget | null, string]>([
    ["sin nada elegido", step(1), null, "no-target"],
    ["un silencio no tiene altura", step(1), target(note(null)), "rest"],
    ["ni alteración", { kind: "accidental", accidental: "#" }, target(note(null)), "rest"],
    ["fuera del registro", step(1), target(note("G9")), "range"],
    [
      "alteración fuera del registro",
      { kind: "accidental", accidental: "#" },
      target(note("G9")),
      "range",
    ],
    ["una altura que no se entiende", step(1), target(note("H4")), "unknown-pitch"],
    // Sin la partitura no se sabe qué notas tiene el acorde (ADR-0049).
    [
      "la figura de un acorde sin partitura",
      { kind: "figure", figure: 4 },
      target(note("C4"), true),
      "no-target",
    ],
    ["el puntillo sin figura simple", { kind: "dot" }, target(note("C4", "5/4")), "not-figure"],
    ["el puntillo de un tresillo", { kind: "dot" }, target(note("C4", "2/3")), "triplet-dot"],
    ["el mismo valor", { kind: "figure", figure: 4 }, target(note("C4")), "same"],
    ["la misma alteración", { kind: "accidental", accidental: "" }, target(note("C4")), "same"],
  ])("rechaza %s", (_name, command, edited, reason) => {
    expect(planEdit(command, edited, 0)).toMatchObject({ kind: "refused", reason });
  });

  it("cada rechazo trae un mensaje propio", () => {
    const refused = planEdit(step(1), target(note(null)), 0);
    expect(refused.kind === "refused" && refused.message).toBe(
      "Un silencio no tiene altura ni alteración: solo se puede cambiar su figura.",
    );
  });
});

describe("teclas de edición sobre la partitura", () => {
  const key = (value: string, modifiers: Partial<Record<string, boolean>> = {}) => ({
    key: value,
    shiftKey: false,
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    ...modifiers,
  });

  it.each([
    [key("ArrowUp", { shiftKey: true }), { kind: "step", direction: 1 }],
    [key("ArrowDown", { shiftKey: true }), { kind: "step", direction: -1 }],
    [key("PageUp", { shiftKey: true }), { kind: "octave", direction: 1 }],
    [key("PageDown", { shiftKey: true }), { kind: "octave", direction: -1 }],
    [key("1"), { kind: "figure", figure: 0 }],
    [key("7"), { kind: "figure", figure: 6 }],
    [key("."), { kind: "dot" }],
    // «+» y «=» llevan Mayús en unos teclados y no en otros.
    [key("+", { shiftKey: true }), { kind: "accidental", accidental: "#" }],
    [key("+"), { kind: "accidental", accidental: "#" }],
    [key("-"), { kind: "accidental", accidental: "b" }],
    [key("=", { shiftKey: true }), { kind: "accidental", accidental: "" }],
  ])("%o es %o", (event, command) => {
    expect(editCommand(event)).toEqual(command);
  });

  it.each([
    // N inserta una nota y S un silencio, con Mayús o sin ella; Supr y Retroceso borran (#184).
    [key("n"), { kind: "insert", rest: false }],
    [key("N", { shiftKey: true }), { kind: "insert", rest: false }],
    [key("s"), { kind: "insert", rest: true }],
    [key("S", { shiftKey: true }), { kind: "insert", rest: true }],
    [key("Delete"), { kind: "delete" }],
    [key("Backspace"), { kind: "delete" }],
    // R pone o quita el tresillo de tres figuras y, con Mayús, el del compás (#241).
    [key("r"), { kind: "tuplet", scope: "group" }],
    [key("R"), { kind: "tuplet", scope: "group" }],
    [key("R", { shiftKey: true }), { kind: "tuplet", scope: "measure" }],
  ])("%o es %o", (event, command) => {
    expect(editCommand(event)).toEqual(command);
  });

  it.each([
    // Las flechas solas, y con Ctrl o ⌘, son de la selección (#182).
    key("ArrowUp"),
    key("ArrowRight", { shiftKey: true }),
    key("PageUp"),
    // Con Ctrl, ⌘ o Alt son del navegador o del sistema (zoom, atrás…).
    key("+", { ctrlKey: true }),
    key("-", { metaKey: true }),
    key("1", { altKey: true }),
    key("ArrowUp", { shiftKey: true, ctrlKey: true }),
    key("8"),
    key("0"),
    key("n", { ctrlKey: true }),
    key("s", { metaKey: true }),
    key("Backspace", { altKey: true }),
    key("Delete", { ctrlKey: true }),
    key("r", { ctrlKey: true }),
    key("R", { metaKey: true, shiftKey: true }),
  ])("%o no edita", (event) => {
    expect(editCommand(event)).toBeNull();
  });
});

describe("llevar un ancla a un estado posterior", () => {
  function edit(seq: number, op: string, at: AnchorPayload = anchor(1)): EditEventRead {
    return {
      id: `e${String(seq)}`,
      session_id: "s",
      seq,
      op,
      author: "ana",
      anchor: at,
      before: null,
      after: null,
      created_at: "2026-10-24T00:00:00Z",
    };
  }
  function detail(
    seq: number,
    edits: EditEventRead[],
    events = [note("C4"), note("D4"), note("E4")],
  ): SessionDetailRead {
    return {
      current_seq: seq,
      edits,
      current_score: score([{ events }, { events: [note("F4")] }]),
    } as SessionDetailRead;
  }

  it("la conserva si en medio solo se cambiaron alturas, duraciones, claves o armaduras", () => {
    const later = detail(3, [edit(1, "SetPitch"), edit(2, "SetDuration"), edit(3, "SetKey")]);
    expect(carryAnchor(anchor(1, 1), 1, later)).toEqual(anchor(1, 1));
  });

  it("la conserva tras cambiar la figura de un acorde, que no mueve ningún evento", () => {
    const later = detail(1, [edit(1, "SetChordDuration", anchor(1, 0))]);
    expect(carryAnchor(anchor(1, 1), 0, later)).toEqual(anchor(1, 1));
  });

  it("el compás y los tresillos no mueven ningún evento (ADR-0044)", () => {
    const later = detail(2, [edit(1, "SetTime"), edit(2, "SetTuplet")]);
    expect(carryAnchor(anchor(1, 1), 0, later)).toEqual(anchor(1, 1));
  });

  it("la desplaza como ADR-0011: insertar en su posición o antes la retrasa", () => {
    expect(carryAnchor(anchor(1, 1), 0, detail(1, [edit(1, "InsertEvent", anchor(1, 1))]))).toEqual(
      anchor(1, 2),
    );
    expect(carryAnchor(anchor(1, 1), 0, detail(1, [edit(1, "InsertEvent", anchor(1, 2))]))).toEqual(
      anchor(1, 1),
    );
  });

  it("borrar antes la adelanta, en el orden del log", () => {
    const later = detail(2, [
      edit(2, "DeleteEvent", anchor(1, 0)),
      edit(1, "InsertEvent", anchor(1, 0)),
    ]);
    // Insertar delante (1 → 2) y después borrar el primero (2 → 1).
    expect(carryAnchor(anchor(1, 1), 0, later)).toEqual(anchor(1, 1));
  });

  it("no la mueven las inserciones ni los borrados de otra voz o de otro compás", () => {
    const later = detail(2, [
      edit(1, "InsertEvent", anchor(2, 0)),
      edit(2, "DeleteEvent", anchor(1, 0, 1)),
    ]);
    expect(carryAnchor(anchor(1, 1), 0, later)).toEqual(anchor(1, 1));
  });

  it("no la conserva si se borró su evento o si una edición no se sabe desplazar", () => {
    expect(carryAnchor(anchor(1, 1), 0, detail(1, [edit(1, "DeleteEvent", anchor(1, 1))]))).toBe(
      null,
    );
    expect(carryAnchor(anchor(1, 1), 0, detail(1, [edit(1, "Desconocida")]))).toBeNull();
  });

  it("no la conserva si el evento ya no está", () => {
    expect(carryAnchor(anchor(1, 3), 0, detail(1, [edit(1, "SetPitch")]))).toBeNull();
  });

  it("no la lleva hacia atrás", () => {
    expect(carryAnchor(anchor(1), 2, detail(1, [edit(1, "SetPitch")]))).toBeNull();
  });
});

describe("volver a pedir una edición en otro estado", () => {
  it("pide el mismo valor final, no el mismo paso", () => {
    expect(planAgain({ op: "SetPitch", after: { pitch: "D4" } }, target(note("E4")))).toMatchObject(
      { kind: "edit", op: "SetPitch", after: { pitch: "D4" } },
    );
    expect(
      planAgain({ op: "SetAccidental", after: { accidental: "natural" } }, target(note("F#4"))),
    ).toMatchObject({ kind: "edit", change: "alteración: Fa 4" });
  });

  it.each<[string, DecidedEdit, EditTarget | null, string]>([
    [
      "si la nota ya lo tiene",
      { op: "SetPitch", after: { pitch: "D4" } },
      target(note("D4")),
      "same",
    ],
    [
      "si la duración ya es esa",
      { op: "SetDuration", after: { duration_beats: "1/2" } },
      target(note("C4", "2/4")),
      "same",
    ],
    [
      "si la alteración ya es esa",
      { op: "SetAccidental", after: { accidental: "#" } },
      target(note("F#4")),
      "same",
    ],
    [
      "si ahora es un silencio",
      { op: "SetPitch", after: { pitch: "D4" } },
      target(note(null)),
      "rest",
    ],
    [
      "si ahora es de un acorde y no se sabe de qué notas",
      { op: "SetDuration", after: { duration_beats: "1/2" } },
      target(note("C4"), true),
      "no-target",
    ],
    ["si ya no hay evento", { op: "SetPitch", after: { pitch: "D4" } }, null, "no-target"],
  ])("no la pide %s", (_name, edit, edited, reason) => {
    expect(planAgain(edit, edited)).toMatchObject({ kind: "refused", reason });
  });
});

/** Compás de prueba con lo que se le dé: eventos, clave o armadura propias. */
interface MeasureSpec {
  events: ScoreEventPayload[];
  clef?: { sign: string; line: number } | null;
  fifths?: number | null;
  mode?: string | null;
}

/** Partitura de un pentagrama con compases numerados desde 1. */
function staffScore(measures: MeasureSpec[]): ScoreIRPayload {
  return {
    parts: [
      {
        id: "part-0",
        staves: [
          {
            id: "part-0-staff-0",
            measures: measures.map((measure, index) => ({
              number: index + 1,
              events: measure.events,
              clef: measure.clef ?? null,
              key_signature:
                measure.fifths === undefined || measure.fifths === null
                  ? null
                  : { fifths: measure.fifths, mode: measure.mode ?? null },
            })),
          },
        ],
      },
    ],
  };
}

/** Evento elegido en un estado: su ancla, el evento y si es de un acorde. */
function chosen(state: ScoreIRPayload, at: AnchorPayload): EditTarget {
  const found = eventAt(state, at);
  if (!found) throw new Error("ancla sin evento");
  return { anchor: at, ...found };
}

const hiddenRest = (duration: string, voice = 0) => note(null, duration, { voice, hidden: true });

describe("insertar un evento antes del elegido", () => {
  const treble = { sign: "G", line: 2 };

  it("una nota copia la altura y la figura de la nota elegida y queda elegida", () => {
    const state = staffScore([{ events: [note("C4"), note("D4", "1/2")], clef: treble }]);
    const plan = planInsert(false, chosen(state, anchor(1, 1)), state);
    expect(plan).toMatchObject({
      kind: "edit",
      op: "InsertEvent",
      after: { kind: "note", duration_beats: "1/2", pitch: "D4" },
      anchor: { ...anchor(1, 1), bbox: null, confidence: null },
      select: anchor(1, 1),
      change: "inserción de Re 4, corchea",
    });
  });

  it("un silencio copia la figura y no lleva altura", () => {
    const state = staffScore([{ events: [note("C4", "3/2")], clef: treble }]);
    const plan = planInsert(true, chosen(state, anchor(1)), state);
    expect(plan).toMatchObject({
      kind: "edit",
      op: "InsertEvent",
      after: { kind: "rest", duration_beats: "3/2" },
      change: "inserción de un silencio de negra con puntillo",
    });
    expect(plan.kind === "edit" && plan.after).not.toHaveProperty("pitch");
  });

  it.each([
    ["en clave de sol, el Si4", treble, 0, "B4"],
    ["en clave de fa, el Re3", { sign: "F", line: 4 }, 0, "D3"],
    ["en clave de do en tercera, el Do4", { sign: "C", line: 3 }, 0, "C4"],
    ["en clave de do en cuarta, el La3", { sign: "C", line: 4 }, 0, "A3"],
    ["con la alteración de la armadura", treble, -1, "Bb4"],
  ])("antes de un silencio, una nota en la línea central: %s", (_name, clef, fifths, pitch) => {
    const state = staffScore([{ events: [note(null)], clef, fifths }]);
    expect(planInsert(false, chosen(state, anchor(1)), state)).toMatchObject({
      after: { kind: "note", pitch },
    });
  });

  it("la línea central sigue la clave que rige el compás, aunque sea de uno anterior", () => {
    const state = staffScore([
      { events: [note("C3")], clef: { sign: "F", line: 4 } },
      { events: [note(null)] },
    ]);
    expect(planInsert(false, chosen(state, anchor(2)), state)).toMatchObject({
      after: { pitch: "D3" },
    });
  });

  it("dentro de un acorde inserta antes del acorde entero, con su figura", () => {
    const state = staffScore([
      { events: [note("G3"), note("C4", "2"), note("E4", "2", { is_chord: true })], clef: treble },
    ]);
    expect(planInsert(false, chosen(state, anchor(1, 2)), state)).toMatchObject({
      after: { kind: "note", duration_beats: "2", pitch: "E4" },
      anchor: { event_index: 1 },
      select: anchor(1, 1),
    });
  });

  it("antes de una nota de adorno, o de una duración que no se admite, inserta una negra", () => {
    const state = staffScore([{ events: [note("D4", "0"), note("E4", "1/17")], clef: treble }]);
    expect(planInsert(false, chosen(state, anchor(1, 0)), state)).toMatchObject({
      after: { duration_beats: "1" },
    });
    expect(planInsert(true, chosen(state, anchor(1, 1)), state)).toMatchObject({
      after: { duration_beats: "1" },
    });
  });

  it("tras un hueco de una voz secundaria, inserta entre el hueco y la nota (ADR-0032)", () => {
    const state = staffScore([
      { events: [note("E5", "4"), hiddenRest("2", 1), note("C5", "1", { voice: 1 })] },
    ]);
    expect(planInsert(false, chosen(state, anchor(1, 1, 1)), state)).toMatchObject({
      anchor: { voice: 1, event_index: 1 },
      after: { kind: "note", pitch: "C5", duration_beats: "1" },
      select: anchor(1, 1, 1),
    });
  });

  it("sin nada elegido no inserta", () => {
    expect(planInsert(false, null, staffScore([{ events: [] }]))).toMatchObject({
      kind: "refused",
      reason: "no-target",
    });
  });
});

describe("borrar el evento elegido", () => {
  it("borra el elegido y deja elegido el que pasa a ocupar su sitio", () => {
    const state = staffScore([{ events: [note("C4"), note("D4"), note("E4")] }]);
    expect(planDelete(chosen(state, anchor(1, 1)), state)).toMatchObject({
      kind: "edit",
      op: "DeleteEvent",
      after: null,
      anchor: anchor(1, 1),
      select: anchor(1, 1),
      change: "borrado de Re 4, negra",
    });
  });

  it("si era el último de su voz en el compás, deja elegido el anterior", () => {
    const state = staffScore([{ events: [note("C4"), note("D4", "1", { voice: 1 }), note("E4")] }]);
    expect(planDelete(chosen(state, anchor(1, 1)), state)).toMatchObject({
      select: anchor(1, 0),
    });
  });

  it("elige también un hueco, que ahora se elige (ADR-0058)", () => {
    const state = staffScore([
      { events: [note("C4"), hiddenRest("1"), note("E4")] },
      { events: [hiddenRest("2"), note("F4")] },
    ]);
    // Tras borrar Do4, el hueco pasa a la posición 0 y queda elegido.
    expect(planDelete(chosen(state, anchor(1, 0)), state)).toMatchObject({
      select: anchor(1, 0),
    });
    // Tras borrar Fa4 queda el hueco en su voz: se elige.
    expect(planDelete(chosen(state, anchor(2, 1)), state)).toMatchObject({
      select: anchor(2, 0),
    });
  });

  it("si su voz se queda sin nada que se vea en el compás, pasa al compás siguiente", () => {
    const state = staffScore([
      { events: [note("C4", "3"), note("G3", "3", { voice: 1 })] },
      { events: [note("D4", "3")] },
    ]);
    // La voz 2 no está en el compás 2: se elige el primero de la primera voz.
    expect(planDelete(chosen(state, anchor(1, 0, 1)), state)).toMatchObject({
      select: anchor(2, 0),
    });
  });

  it("si no queda nada que elegir, la selección se quita", () => {
    const state = staffScore([{ events: [note("C4")] }]);
    expect(planDelete(chosen(state, anchor(1)), state)).toMatchObject({ select: null });
  });

  it("una nota de un acorde se borra sola; la primera conserva el acorde (ADR-0055)", () => {
    const state = staffScore([
      {
        events: [
          note("C4", "1", { slurs: [{ type: "start", number: 1 }] }),
          note("E4", "1", { is_chord: true }),
          note("G4", "1", { slurs: [{ type: "stop", number: 1 }] }),
        ],
      },
    ]);
    expect(planDelete(chosen(state, anchor(1, 1)), state)).toMatchObject({
      kind: "edit",
      op: "DeleteEvent",
      after: null,
      select: anchor(1, 1),
      change: "borrado de Mi 4 del acorde",
    });
    // La primera: con keep_chord, y queda elegida la siguiente, que ocupa su sitio. Su ligadura de
    // expresión pasa a la siguiente: se sigue dibujando y no hay nada que avisar.
    const head = planDelete(chosen(state, anchor(1, 0)), state);
    expect(head).toMatchObject({
      kind: "edit",
      op: "DeleteEvent",
      after: { keep_chord: true },
      anchor: anchor(1, 0),
      select: anchor(1, 0),
      change: "borrado de Do 4 del acorde",
    });
    expect(head).not.toHaveProperty("notice");
  });

  it("dice si la nota lleva un extremo de una ligadura de expresión, que dejará de dibujarse", () => {
    const state = staffScore([
      { events: [note("C4", "1", { slurs: [{ type: "start", number: 1 }] }), note("D4")] },
      { events: [note("E4", "1", { slurs: [{ type: "stop", number: 1 }] })] },
    ]);
    expect(planDelete(chosen(state, anchor(1, 0)), state)).toMatchObject({
      notice: "Su ligadura de expresión ya no se dibuja.",
    });
    expect(planDelete(chosen(state, anchor(2, 0)), state)).toMatchObject({
      notice: "Su ligadura de expresión ya no se dibuja.",
    });
    // Un extremo que ya no tenía pareja no se dibujaba: no hay nada que decir.
    const orphan = staffScore([
      { events: [note("C4", "1", { slurs: [{ type: "start", number: 2 }] }), note("D4")] },
    ]);
    expect(planDelete(chosen(orphan, anchor(1, 0)), orphan)).not.toHaveProperty("notice");
  });

  it("un silencio se dice como silencio", () => {
    const state = staffScore([{ events: [note(null, "2"), note("C4")] }]);
    expect(planDelete(chosen(state, anchor(1, 0)), state)).toMatchObject({
      change: "borrado de un silencio de blanca",
    });
  });

  it("sin nada elegido no borra", () => {
    expect(planDelete(null, staffScore([{ events: [] }]))).toMatchObject({
      kind: "refused",
      reason: "no-target",
    });
  });
});

describe("cambiar la clave del compás elegido", () => {
  const G = { sign: "G", line: 2 };
  const F = { sign: "F", line: 4 };
  const clefOf = (word: string) => CLEFS.findIndex((clef) => clef.word === word);
  const place = (measure: number) => anchor(measure);

  it("ofrece sol, fa, do en tercera y do en cuarta", () => {
    expect(CLEFS.map(({ word, sign, line }) => [word, sign, line])).toEqual([
      ["Sol", "G", 2],
      ["Fa", "F", 4],
      ["Do 3", "C", 3],
      ["Do 4", "C", 4],
    ]);
  });

  it("la clave activa es la última hasta el compás, o la de sol si no hay ninguna", () => {
    const state = staffScore([{ events: [note("C4")], clef: F }, { events: [note("C4")] }]);
    expect(activeClef(state, place(2))).toEqual(F);
    expect(activeClef(staffScore([{ events: [] }]), place(1))).toEqual(G);
  });

  it("pone la clave en el compás, anclada a su primer evento, y dice hasta dónde llega", () => {
    const state = staffScore([
      { events: [note("C4")], clef: G },
      { events: [note("G3", "1", { voice: 1 }), note("C4")] },
      { events: [note("C4")] },
      { events: [note("C4")], clef: G },
    ]);
    expect(planClef(clefOf("Fa"), place(2), state)).toMatchObject({
      kind: "edit",
      op: "SetClef",
      after: { sign: "F", line: 4 },
      // ADR-0010: la clave es del compás; la edición se ancla a su primer evento.
      anchor: anchor(2, 0, 1),
      change: "clave de fa en los compases 2 a 3",
      notice: "Las notas conservan su altura.",
    });
    expect(planClef(clefOf("Do 3"), place(4), state)).toMatchObject({
      change: "clave de do en tercera en el compás 4",
    });
  });

  it("si se elige la que trae del compás anterior, quita el cambio de clave del compás", () => {
    const state = staffScore([
      { events: [note("C4")], clef: G },
      { events: [note("C4")], clef: F },
    ]);
    expect(planClef(clefOf("Sol"), place(2), state)).toMatchObject({
      kind: "edit",
      after: { clef: null },
      change: "clave de sol en el compás 2",
    });
  });

  it("en el primer compás la clave se escribe siempre", () => {
    const state = staffScore([{ events: [note("C4")], clef: F }]);
    expect(planClef(clefOf("Sol"), place(1), state)).toMatchObject({
      after: { sign: "G", line: 2 },
    });
  });

  it("no cambia la que ya rige el compás, ni sin nada elegido", () => {
    const state = staffScore([{ events: [note("C4")], clef: F }, { events: [note("C4")] }]);
    expect(planClef(clefOf("Fa"), place(2), state)).toMatchObject({ reason: "same" });
    expect(planClef(clefOf("Fa"), null, state)).toMatchObject({ reason: "no-target" });
  });

  it("un compás sin eventos se ancla a la posición 0 de la primera voz", () => {
    const state = staffScore([{ events: [note("C4")], clef: G }, { events: [] }]);
    expect(planClef(clefOf("Fa"), place(2), state)).toMatchObject({ anchor: anchor(2, 0, 0) });
  });
});

describe("cambiar la armadura del compás elegido", () => {
  const place = (measure: number) => anchor(measure);

  it("nombra las armaduras por sus alteraciones", () => {
    expect([-7, -1, 0, 1, 2].map((fifths) => keyName(fifths))).toEqual([
      "7 bemoles",
      "1 bemol",
      "sin alteraciones",
      "1 sostenido",
      "2 sostenidos",
    ]);
  });

  it("pone la armadura en el compás, con el modo de la que rige, y dice hasta dónde llega", () => {
    const state = staffScore([
      { events: [note("C4")], fifths: 1, mode: "minor" },
      { events: [note("C4")] },
      { events: [note("C4")] },
    ]);
    expect(planKey(2, place(2), state)).toMatchObject({
      kind: "edit",
      op: "SetKey",
      after: { fifths: 2, mode: "minor" },
      anchor: anchor(2),
      change: "armadura de 2 sostenidos en los compases 2 a 3",
      notice: "Las notas conservan su altura.",
    });
  });

  it("sin modo en la armadura que rige, no lo inventa", () => {
    const state = staffScore([{ events: [note("C4")] }]);
    const plan = planKey(-3, place(1), state);
    expect(plan).toMatchObject({
      after: { fifths: -3 },
      change: "armadura de 3 bemoles en el compás 1",
    });
    expect(plan.kind === "edit" && plan.after).not.toHaveProperty("mode");
  });

  it("solo conserva el modo mayor o menor, los que admite el servidor (ADR-0017)", () => {
    const state = staffScore([{ events: [note("C4")], fifths: 1, mode: "dorian" }]);
    const plan = planKey(2, place(1), state);
    expect(plan).toMatchObject({ kind: "edit", after: { fifths: 2 } });
    expect(plan.kind === "edit" && plan.after).not.toHaveProperty("mode");
  });

  it("si se elige la que trae del compás anterior, quita el cambio de armadura", () => {
    const state = staffScore([
      { events: [note("C4")], fifths: 1 },
      { events: [note("C4")], fifths: 3 },
    ]);
    expect(planKey(1, place(2), state)).toMatchObject({ after: { key_signature: null } });
    // Sin armadura antes, «sin alteraciones» también es quitarla.
    const first = staffScore([{ events: [note("C4")], fifths: 2 }]);
    expect(planKey(0, place(1), first)).toMatchObject({
      after: { key_signature: null },
      change: "armadura sin alteraciones en el compás 1",
    });
  });

  it("no cambia la que ya rige el compás", () => {
    const state = staffScore([{ events: [note("C4")], fifths: 2 }, { events: [note("C4")] }]);
    expect(planKey(2, place(2), state)).toMatchObject({ reason: "same" });
    expect(planKey(0, place(1), staffScore([{ events: [note("C4")] }]))).toMatchObject({
      reason: "same",
    });
  });
});

describe("cada orden pide su edición", () => {
  it("las de altura, alteración y figura, con la armadura del compás", () => {
    const state = staffScore([{ events: [note("E4")], fifths: 1 }]);
    const target = chosen(state, anchor(1));
    expect(planCommand({ kind: "step", direction: 1 }, target, state)).toMatchObject({
      op: "SetPitch",
      after: { pitch: "F#4" },
    });
  });

  it("las de insertar, borrar, clave y armadura", () => {
    const state = staffScore([{ events: [note("E4"), note("F4")] }]);
    const target = chosen(state, anchor(1, 1));
    expect(planCommand({ kind: "insert", rest: true }, target, state)).toMatchObject({
      op: "InsertEvent",
    });
    expect(planCommand({ kind: "delete" }, target, state)).toMatchObject({ op: "DeleteEvent" });
    expect(planCommand({ kind: "clef", clef: 1 }, target, state)).toMatchObject({ op: "SetClef" });
    expect(planCommand({ kind: "key", fifths: 1 }, target, state)).toMatchObject({ op: "SetKey" });
  });

  it("las del compás y los tresillos (#241)", () => {
    const state = staffScore([
      { events: [note("E4", "1/2"), note("F4", "1/2"), note("G4", "1/2")] },
    ]);
    const target = chosen(state, anchor(1, 1));
    expect(
      planCommand({ kind: "time", time: { beats: 2, beat_type: 2, symbol: "cut" } }, target, state),
    ).toMatchObject({ op: "SetTime", anchor: anchor(1) });
    expect(planCommand({ kind: "tuplet", scope: "measure" }, target, state)).toMatchObject({
      op: "SetTuplet",
      after: { durations: ["1/3", "1/3", "1/3"] },
    });
  });
});

describe("volver a pedir una edición de estructura tras un 409", () => {
  function edit(seq: number, op: string, at: AnchorPayload): EditEventRead {
    return {
      id: `e${String(seq)}`,
      session_id: "s",
      seq,
      op,
      author: "ana",
      anchor: at,
      before: null,
      after: null,
      created_at: "2026-10-24T00:00:00Z",
    };
  }
  const reloaded = (state: ScoreIRPayload, edits: EditEventRead[]) =>
    ({ current_seq: edits.length, edits, current_score: state }) as SessionDetailRead;

  it("inserta lo mismo antes del mismo evento, en su posición nueva", () => {
    const request: EditRequestLike = {
      op: "InsertEvent",
      after: { kind: "note", duration_beats: "1", pitch: "D4" },
      anchor: { ...anchor(1, 1), bbox: null, confidence: null },
      baseSeq: 0,
    };
    // Otra pestaña insertó una nota al principio del compás: el evento pasa a la posición 2.
    const state = staffScore([{ events: [note("B3"), note("C4"), note("E4")] }]);
    const { plan, anchor: carried } = replan(
      request,
      reloaded(state, [edit(1, "InsertEvent", anchor(1, 0))]),
    );
    expect(carried).toMatchObject({ event_index: 2 });
    expect(plan).toMatchObject({
      kind: "edit",
      op: "InsertEvent",
      after: request.after,
      anchor: { event_index: 2 },
      select: { event_index: 2 },
    });
  });

  it("borra el mismo evento si sigue, y si no, dice por qué no", () => {
    const request: EditRequestLike = {
      op: "DeleteEvent",
      after: null,
      anchor: anchor(1, 0),
      baseSeq: 0,
    };
    const state = staffScore([{ events: [note("C4"), note("D4")] }]);
    expect(
      replan(request, reloaded(state, [edit(1, "SetPitch", anchor(1, 1))])).plan,
    ).toMatchObject({ kind: "edit", op: "DeleteEvent", anchor: anchor(1, 0) });
    const gone = replan(request, reloaded(state, [edit(1, "DeleteEvent", anchor(1, 0))]));
    expect(gone.anchor).toBeNull();
    expect(gone.plan).toMatchObject({ kind: "refused", reason: "no-target" });
  });

  it("la clave y la armadura se vuelven a calcular sobre el compás en el estado recargado", () => {
    const state = staffScore([{ events: [note("C4")], clef: { sign: "F", line: 4 } }]);
    const clef: EditRequestLike = {
      op: "SetClef",
      after: { sign: "F", line: 4 },
      clef: 1,
      anchor: anchor(1),
      baseSeq: 0,
    };
    // La otra pestaña ya puso la clave de fa: no hay nada que volver a aplicar.
    expect(replan(clef, reloaded(state, [edit(1, "SetClef", anchor(1))])).plan).toMatchObject({
      reason: "same",
    });
    const key: EditRequestLike = {
      op: "SetKey",
      after: { fifths: 2 },
      fifths: 2,
      anchor: anchor(1),
      baseSeq: 0,
    };
    // Aunque se borrara el primer evento del compás, la armadura sigue siendo del compás.
    const empty = staffScore([{ events: [] }]);
    expect(replan(key, reloaded(empty, [edit(1, "DeleteEvent", anchor(1))])).plan).toMatchObject({
      kind: "edit",
      after: { fifths: 2 },
    });
  });

  it("las de altura siguen pidiendo el mismo valor final", () => {
    const state = staffScore([{ events: [note("E4")] }]);
    const request: EditRequestLike = {
      op: "SetPitch",
      after: { pitch: "D4" },
      anchor: anchor(1),
      baseSeq: 0,
    };
    expect(
      replan(request, reloaded(state, [edit(1, "SetDuration", anchor(1))])).plan,
    ).toMatchObject({ kind: "edit", op: "SetPitch", after: { pitch: "D4" } });
  });
});

describe("la figura de un acorde entero (ADR-0049)", () => {
  // Compás 1: un acorde de Do mayor en negras (Do, Mi, Sol) y un Re blanca.
  const triad = () =>
    staffScore([
      {
        events: [
          note("C4", "1", { bbox: [1, 2, 3, 4], confidence: 0.9 }),
          note("E4", "1", { is_chord: true }),
          note("G4", "1", { is_chord: true }),
          note("D4", "2"),
        ],
      },
    ]);

  it("una figura sobre cualquier nota del acorde cambia todas sus notas en una edición", () => {
    const state = triad();
    const plan = planCommand({ kind: "figure", figure: 3 }, chosen(state, anchor(1, 1)), state);
    expect(plan).toEqual({
      kind: "edit",
      op: "SetChordDuration",
      after: { durations: ["1/2", "1/2", "1/2"] },
      // Anclada en la primera nota, con su caja: la elegida sigue elegida.
      anchor: { ...anchor(1, 0), bbox: [1, 2, 3, 4], confidence: 0.9 },
      change: "figura corchea en el acorde",
    });
  });

  it("el puntillo parte de la figura del acorde, la de su primera nota", () => {
    const state = staffScore([
      { events: [note("C4", "2"), note("E4", "1", { is_chord: true }), note("D4", "2")] },
    ]);
    expect(planCommand({ kind: "dot" }, chosen(state, anchor(1, 1)), state)).toMatchObject({
      op: "SetChordDuration",
      after: { durations: ["3", "3"] },
    });
  });

  it("la figura que ya tienen todas las notas no se envía", () => {
    const state = triad();
    expect(planCommand({ kind: "figure", figure: 4 }, chosen(state, anchor(1, 2)), state)).toEqual({
      kind: "refused",
      reason: "same",
      message: "El acorde ya tiene esa figura.",
    });
  });

  it("si una nota tiene otra figura, sí se envía, para todas", () => {
    const state = staffScore([
      { events: [note("C4", "1"), note("E4", "1/2", { is_chord: true }), note("D4", "3")] },
    ]);
    expect(
      planCommand({ kind: "figure", figure: 4 }, chosen(state, anchor(1)), state),
    ).toMatchObject({ op: "SetChordDuration", after: { durations: ["1", "1"] } });
  });

  it("una nota sola sigue siendo SetDuration", () => {
    const state = triad();
    expect(planCommand({ kind: "figure", figure: 3 }, chosen(state, anchor(1, 3)), state)).toEqual({
      kind: "edit",
      op: "SetDuration",
      after: { duration_beats: "1/2" },
      anchor: anchor(1, 3),
      change: "figura corchea",
    });
  });

  it("tras un 409 pide la misma figura sobre lo que sea ahora el evento", () => {
    const request: DecidedEdit = { op: "SetChordDuration", after: { durations: ["2", "2", "2"] } };
    // La otra pestaña añadió una nota al acorde: la figura va a las cuatro.
    const grown = staffScore([
      {
        events: [
          note("C4"),
          note("E4", "1", { is_chord: true }),
          note("G4", "1", { is_chord: true }),
          note("C5", "1", { is_chord: true }),
        ],
      },
    ]);
    expect(planAgain(request, chosen(grown, anchor(1)), grown)).toMatchObject({
      op: "SetChordDuration",
      after: { durations: ["2", "2", "2", "2"] },
    });
    // Ya no es un acorde: la misma figura, a la nota sola.
    const single = staffScore([{ events: [note("C4"), note("D4")] }]);
    expect(planAgain(request, chosen(single, anchor(1)), single)).toMatchObject({
      op: "SetDuration",
      after: { duration_beats: "2" },
    });
    // Y una figura de una nota que ahora es de un acorde, al acorde entero.
    const duration: DecidedEdit = { op: "SetDuration", after: { duration_beats: "1/2" } };
    expect(planAgain(duration, chosen(grown, anchor(1, 2)), grown)).toMatchObject({
      op: "SetChordDuration",
      after: { durations: ["1/2", "1/2", "1/2", "1/2"] },
      anchor: { event_index: 0 },
    });
    // Si ya la tiene, no hay nada que volver a aplicar.
    const done = staffScore([{ events: [note("C4", "2"), note("E4", "2", { is_chord: true })] }]);
    expect(planAgain(request, chosen(done, anchor(1, 1)), done)).toMatchObject({
      kind: "refused",
      reason: "same",
    });
  });

  it("tras un 409, replan lleva el ancla del acorde al estado recargado", () => {
    const request: EditRequestLike = {
      op: "SetChordDuration",
      after: { durations: ["1/2", "1/2"] },
      anchor: anchor(1, 1),
      baseSeq: 0,
    };
    // Otra pestaña insertó una nota delante: el acorde pasa a la posición 2.
    const state = staffScore([
      { events: [note("A3"), note("B3"), note("C4"), note("E4", "1", { is_chord: true })] },
    ]);
    const inserted: EditEventRead = {
      id: "e1",
      session_id: "s",
      seq: 1,
      op: "InsertEvent",
      author: "ana",
      anchor: anchor(1, 0),
      before: null,
      after: null,
      created_at: "2026-11-01T00:00:00Z",
    };
    const reloaded = {
      current_seq: 1,
      edits: [inserted],
      current_score: state,
    } as SessionDetailRead;
    expect(replan(request, reloaded).plan).toMatchObject({
      kind: "edit",
      op: "SetChordDuration",
      after: { durations: ["1/2", "1/2"] },
      anchor: { event_index: 2 },
    });
  });

  it("si su primera nota ya no es de un acorde, la figura va a esa nota y no a la elegida", () => {
    const request: EditRequestLike = {
      op: "SetChordDuration",
      after: { durations: ["1/2", "1/2"] },
      anchor: anchor(1, 0),
      baseSeq: 0,
    };
    // Otra pestaña insertó una nota entre las dos: la elegida (Mi4) es ahora de otro acorde.
    const state = staffScore([
      { events: [note("C4"), note("D4"), note("E4", "1", { is_chord: true })] },
    ]);
    const inserted: EditEventRead = {
      id: "e1",
      session_id: "s",
      seq: 1,
      op: "InsertEvent",
      author: "ana",
      anchor: anchor(1, 1),
      before: null,
      after: null,
      created_at: "2026-11-01T00:00:00Z",
    };
    const reloaded = {
      current_seq: 1,
      edits: [inserted],
      current_score: state,
    } as SessionDetailRead;
    expect(replan(request, reloaded).plan).toMatchObject({
      kind: "edit",
      op: "SetDuration",
      after: { duration_beats: "1/2" },
      anchor: { event_index: 0 },
    });
  });
});

describe("notas de un acorde y ligaduras de prolongación (ADR-0055)", () => {
  function logged(seq: number, op: string, at: AnchorPayload): EditEventRead {
    return {
      id: `e${String(seq)}`,
      session_id: "s",
      seq,
      op,
      author: "ana",
      anchor: at,
      before: null,
      after: null,
      created_at: "2026-11-01T00:00:00Z",
    };
  }
  const reloaded = (state: ScoreIRPayload, edits: EditEventRead[]) =>
    ({ current_seq: edits.length, edits, current_score: state }) as SessionDetailRead;
  const triad = () =>
    staffScore([
      {
        events: [
          note("C4"),
          note("E4", "1", { is_chord: true }),
          note("G4", "1", { is_chord: true }),
          note("D4", "2"),
        ],
        fifths: 1,
      },
    ]);
  const key = (value: string, shiftKey = false, ctrlKey = false) =>
    editCommand({ key: value, shiftKey, ctrlKey, metaKey: false, altKey: false });

  it("E y U son las teclas de añadir al acorde y de ligar", () => {
    expect(key("e")).toEqual({ kind: "chord-add" });
    expect(key("E", true)).toEqual({ kind: "chord-add" });
    expect(key("u")).toEqual({ kind: "tie" });
    expect(key("u", false, true)).toBeNull();
  });

  it("añade una tercera por encima de la nota más aguda, tras la última nota, y la elige", () => {
    const state = triad();
    // Desde cualquier nota del acorde; en Sol mayor, la tercera sobre el Sol es Si.
    const plan = planCommand({ kind: "chord-add" }, chosen(state, anchor(1, 0)), state);
    expect(plan).toEqual({
      kind: "edit",
      op: "InsertEvent",
      after: { kind: "note", pitch: "B4", duration_beats: "1", is_chord: true },
      anchor: { ...anchor(1, 3), bbox: null, confidence: null },
      select: { ...anchor(1, 3), bbox: null, confidence: null },
      change: "inserción de Si 4 en el acorde",
    });
    // Con una nota sola forma un acorde, con su figura: sobre el Re, Fa sostenido.
    expect(planCommand({ kind: "chord-add" }, chosen(state, anchor(1, 3)), state)).toMatchObject({
      after: { pitch: "F#4", duration_beats: "2", is_chord: true },
      anchor: { event_index: 4 },
    });
  });

  it("por debajo si arriba se sale del registro; en un silencio no", () => {
    const high = staffScore([{ events: [note("C9"), note("A9", "1", { is_chord: true })] }]);
    expect(planCommand({ kind: "chord-add" }, chosen(high, anchor(1, 0)), high)).toMatchObject({
      after: { pitch: "A8" },
    });
    const rest = staffScore([{ events: [note(null), note("C4")] }]);
    expect(planCommand({ kind: "chord-add" }, chosen(rest, anchor(1, 0)), rest)).toMatchObject({
      kind: "refused",
      reason: "chord",
    });
  });

  it("tras un 409, añade la misma nota tras la última del acorde en su posición nueva", () => {
    const request: EditRequestLike = {
      op: "InsertEvent",
      after: { kind: "note", pitch: "B4", duration_beats: "1", is_chord: true },
      anchor: { ...anchor(1, 3), bbox: null, confidence: null },
      baseSeq: 0,
    };
    // Otra pestaña insertó un silencio al principio: el acorde pasa a las posiciones 1 a 3.
    const state = staffScore([
      {
        events: [
          note(null),
          note("C4"),
          note("E4", "1", { is_chord: true }),
          note("G4", "1", { is_chord: true }),
        ],
      },
    ]);
    const { plan } = replan(request, reloaded(state, [logged(1, "InsertEvent", anchor(1, 0))]));
    expect(plan).toMatchObject({
      kind: "edit",
      op: "InsertEvent",
      after: request.after,
      anchor: { event_index: 4 },
      select: { event_index: 4 },
      change: "inserción de Si 4 en el acorde",
    });
  });

  it("liga con la nota de la misma altura que la sigue, también al cruzar la barra", () => {
    const state = staffScore([
      { events: [note("C4"), note("C4"), note("D4", "1", { voice: 1 }), note("G4", "2")] },
      { events: [note(null, "2"), note("D4", "4", { voice: 1 }), note("G4", "2")] },
    ]);
    expect(planCommand({ kind: "tie" }, chosen(state, anchor(1, 0)), state)).toEqual({
      kind: "edit",
      op: "SetTie",
      after: { tie: "start", next: { measure: 1, voice: 0, event_index: 1, tie: "stop" } },
      tie: { intent: "put", from: anchor(1, 0) },
      anchor: anchor(1, 0),
      change: "ligadura de prolongación de Do 4",
    });
    // El Sol acaba el compás: el siguiente de su altura empieza el compás 2 en su voz, tras un
    // silencio no: la voz 1 del compás 2 empieza con un silencio, así que no hay Sol que ligar.
    expect(planCommand({ kind: "tie" }, chosen(state, anchor(1, 2)), state)).toMatchObject({
      kind: "refused",
      reason: "tie",
    });
    // La voz 2 (índice 1) liga su Re con el Re de su voz en el compás siguiente.
    expect(planCommand({ kind: "tie" }, chosen(state, anchor(1, 0, 1)), state)).toMatchObject({
      after: { tie: "start", next: { measure: 2, voice: 1, event_index: 0, tie: "stop" } },
      change: "ligadura de prolongación de Re 4 hasta el compás 2",
    });
  });

  it("al cruzar la barra, liga con la misma nota en otra voz si la suya no la tiene", () => {
    const state = staffScore([
      { events: [note("E4", "3"), note("C4")] },
      { events: [note(null, "4"), note("C4", "4", { voice: 1 })] },
    ]);
    expect(planCommand({ kind: "tie" }, chosen(state, anchor(1, 1)), state)).toMatchObject({
      after: { tie: "start", next: { measure: 2, voice: 1, event_index: 0, tie: "stop" } },
      change: "ligadura de prolongación de Do 4 hasta el compás 2",
    });
  });

  it("no liga con lo que no es la misma nota, ni un silencio, y dice por qué", () => {
    const state = staffScore([{ events: [note("C4"), note("D4"), note(null, "2")] }]);
    const refused = planCommand({ kind: "tie" }, chosen(state, anchor(1, 0)), state);
    expect(refused).toMatchObject({ kind: "refused", reason: "tie" });
    expect(refused.kind === "refused" && refused.message).toBe(
      "Lo siguiente no es un Do 4: una ligadura de prolongación une dos notas de la misma altura.",
    );
    expect(planCommand({ kind: "tie" }, chosen(state, anchor(1, 2)), state)).toMatchObject({
      kind: "refused",
      message: "Un silencio no se liga: elige una nota.",
    });
  });

  it("pulsado, quita la que sale con su otra nota o, si no llega a ninguna, solo la suya", () => {
    const tied = staffScore([
      {
        events: [
          note("C4", "1", { tie: "continue" }),
          note("C4", "1", { tie: "stop" }),
          note("E4"),
        ],
      },
    ]);
    expect(planCommand({ kind: "tie" }, chosen(tied, anchor(1, 0)), tied)).toMatchObject({
      after: { tie: "stop", next: { measure: 1, voice: 0, event_index: 1, tie: null } },
      tie: { intent: "remove" },
      change: "quitar la ligadura de prolongación de Do 4",
    });
    const loose = staffScore([{ events: [note("C4", "1", { tie: "start" }), note("E4")] }]);
    expect(planCommand({ kind: "tie" }, chosen(loose, anchor(1, 0)), loose)).toMatchObject({
      after: { tie: null, next: null },
    });
  });

  it("quita la que llega desde su nota de origen o, si no viene de ninguna, solo la marca", () => {
    const tied = staffScore([
      { events: [note("E4", "3"), note("C4", "1", { tie: "start" })] },
      { events: [note("C4", "4", { tie: "stop", voice: 1 })] },
    ]);
    expect(planCommand({ kind: "untie-in" }, chosen(tied, anchor(2, 0, 1)), tied)).toMatchObject({
      kind: "edit",
      op: "SetTie",
      // Anclada en la nota de origen, en el compás 1.
      anchor: anchor(1, 1),
      after: { tie: null, next: { measure: 2, voice: 1, event_index: 0, tie: null } },
      tie: { intent: "remove-in", from: anchor(2, 0, 1) },
      change: "quitar la ligadura de prolongación que llega a Do 4",
    });
    const loose = staffScore([{ events: [note("D4"), note("C4", "1", { tie: "stop" })] }]);
    expect(planCommand({ kind: "untie-in" }, chosen(loose, anchor(1, 1)), loose)).toMatchObject({
      anchor: anchor(1, 1),
      after: { tie: null, next: null },
    });
    expect(planCommand({ kind: "untie-in" }, chosen(loose, anchor(1, 0)), loose)).toMatchObject({
      kind: "refused",
      reason: "tie",
    });
  });

  it("tras un 409, pone la misma ligadura desde la nota llevada, o dice que ya está", () => {
    const request: EditRequestLike = {
      op: "SetTie",
      after: { tie: "start", next: { measure: 1, voice: 0, event_index: 1, tie: "stop" } },
      tie: { intent: "put", from: anchor(1, 0) },
      anchor: anchor(1, 0),
      baseSeq: 0,
    };
    // Otra pestaña insertó una nota al principio: los dos Do pasan a las posiciones 1 y 2.
    const state = staffScore([{ events: [note("B3"), note("C4"), note("C4")] }]);
    const detail = reloaded(state, [logged(1, "InsertEvent", anchor(1, 0))]);
    expect(replan(request, detail)).toMatchObject({
      anchor: { event_index: 1 },
      plan: {
        kind: "edit",
        anchor: { event_index: 1 },
        after: { tie: "start", next: { event_index: 2, tie: "stop" } },
      },
    });
    const tied = staffScore([
      { events: [note("C4", "1", { tie: "start" }), note("C4", "1", { tie: "stop" })] },
    ]);
    expect(replan(request, reloaded(tied, [logged(1, "SetTie", anchor(1, 0))])).plan).toMatchObject(
      { kind: "refused", reason: "same" },
    );
  });

  it("si lo siguiente es un silencio lo dice, y salta el hueco del final de la voz", () => {
    const state = staffScore([
      { events: [note("C4"), note(null, "2")] },
      { events: [note("C4", "2"), hiddenRest("1")] },
      { events: [note("C4", "3")] },
    ]);
    expect(planCommand({ kind: "tie" }, chosen(state, anchor(1, 0)), state)).toMatchObject({
      kind: "refused",
      message:
        "Lo siguiente no es un Do 4: una ligadura de prolongación une dos notas de la misma altura.",
    });
    // Tras el Do del compás 2 solo queda su hueco: la ligadura cruza al compás 3.
    expect(planCommand({ kind: "tie" }, chosen(state, anchor(2, 0)), state)).toMatchObject({
      after: { tie: "start", next: { measure: 3, voice: 0, event_index: 0, tie: "stop" } },
    });
  });

  it("la ligadura no mueve ningún ancla", () => {
    const state = staffScore([{ events: [note("C4"), note("C4")] }]);
    const detail = reloaded(state, [logged(1, "SetTie", anchor(1, 0))]);
    expect(carryAnchor(anchor(1, 1), 0, detail)).toEqual(anchor(1, 1));
  });
});

describe("los huecos de una voz (ADR-0058, #317)", () => {
  // La voz del compás 1 de TS-03, en La mayor: Sol#4, un hueco de semicorchea, Fa#4, Re5, otro
  // hueco que sobra y dos Sol#4.
  const ts03 = () =>
    staffScore([
      {
        events: [
          note("G#4", "3/4"),
          hiddenRest("1/4"),
          note("F#4", "1/2"),
          note("D5", "3/4"),
          hiddenRest("1/4"),
          note("G#4", "1/4"),
          note("G#4", "1/2"),
        ],
        clef: { sign: "G", line: 2 },
        fifths: 3,
      },
    ]);

  it("N escribe en el hueco una nota con la altura de la anterior, y el hueco queda elegido", () => {
    const state = ts03();
    const plan = planCommand({ kind: "insert", rest: false }, chosen(state, anchor(1, 1)), state);
    expect(plan).toMatchObject({
      kind: "edit",
      op: "SetEventKind",
      after: { kind: "note", pitch: "G#4", hidden: false },
      anchor: anchor(1, 1),
      change: "Sol sostenido 4 en el hueco de semicorchea",
    });
    // No mueve la selección: el evento sigue en su sitio.
    expect(plan).not.toHaveProperty("select");
  });

  it("S lo hace un silencio que se ve, con su figura", () => {
    const state = ts03();
    expect(
      planCommand({ kind: "insert", rest: true }, chosen(state, anchor(1, 4)), state),
    ).toMatchObject({
      op: "SetEventKind",
      after: { kind: "rest", pitch: null, hidden: false },
      change: "silencio de semicorchea en el hueco",
    });
  });

  it("Supr lo borra y deja elegido lo que ocupa su sitio", () => {
    const state = ts03();
    expect(planCommand({ kind: "delete" }, chosen(state, anchor(1, 4)), state)).toMatchObject({
      op: "DeleteEvent",
      after: null,
      anchor: anchor(1, 4),
      select: anchor(1, 4),
      change: "borrado del hueco de semicorchea",
    });
  });

  it("su figura se cambia como la de un silencio; no tiene altura ni marcas", () => {
    const state = ts03();
    const gap = chosen(state, anchor(1, 1));
    expect(planCommand({ kind: "figure", figure: 3 }, gap, state)).toMatchObject({
      op: "SetDuration",
      after: { duration_beats: "1/2" },
    });
    for (const command of [
      { kind: "step", direction: 1 },
      { kind: "accidental", accidental: "#" },
      { kind: "fermata" },
      { kind: "articulation", articulation: "accent" },
      { kind: "chord-add" },
      { kind: "tie" },
    ] as const) {
      expect(planCommand(command, gap, state)).toMatchObject({ kind: "refused", reason: "gap" });
    }
  });

  it("una voz que empieza con un hueco toma la altura de lo que sigue o de la línea central", () => {
    const state = staffScore([
      {
        events: [note("C#5", "3"), hiddenRest("1", 1), note("E4", "1/2", { voice: 1 })],
        clef: { sign: "G", line: 2 },
        fifths: 3,
      },
      { events: [hiddenRest("3")], clef: { sign: "F", line: 4 } },
    ]);
    expect(
      planCommand({ kind: "insert", rest: false }, chosen(state, anchor(1, 0, 1)), state),
    ).toMatchObject({ after: { kind: "note", pitch: "E4", hidden: false } });
    expect(
      planCommand({ kind: "insert", rest: false }, chosen(state, anchor(2, 0)), state),
    ).toMatchObject({ after: { kind: "note", pitch: "D3", hidden: false } });
  });

  it("no escribe una nota que se uniría al acorde que sigue al hueco", () => {
    const state = staffScore([
      { events: [hiddenRest("1"), note("E4", "1", { is_chord: true }), note("C4", "2")] },
    ]);
    expect(
      planCommand({ kind: "insert", rest: false }, chosen(state, anchor(1, 0)), state),
    ).toMatchObject({ kind: "refused", reason: "chord" });
    // Tampoco al volver a aplicarla tras un 409.
    const again: DecidedEdit = {
      op: "SetEventKind",
      after: { kind: "note", pitch: "E4", hidden: false },
    };
    expect(planAgain(again, chosen(state, anchor(1, 0)), state)).toMatchObject({
      kind: "refused",
      reason: "chord",
    });
  });

  it("no mueve ningún ancla, y tras un 409 se pide lo mismo si sigue siendo un hueco", () => {
    const state = ts03();
    const edit: EditEventRead = {
      id: "e1",
      session_id: "s",
      seq: 1,
      op: "SetEventKind",
      author: "ana",
      anchor: anchor(1, 1),
      before: null,
      after: null,
      created_at: "2026-11-02T00:00:00Z",
    };
    const detail = { current_seq: 1, edits: [edit], current_score: state } as SessionDetailRead;
    expect(carryAnchor(anchor(1, 5), 0, detail)).toEqual(anchor(1, 5));
    const request: EditRequestLike = {
      op: "SetEventKind",
      after: { kind: "note", pitch: "F#4", hidden: false },
      anchor: anchor(1, 4),
      baseSeq: 0,
    };
    expect(replan(request, detail).plan).toMatchObject({
      kind: "edit",
      op: "SetEventKind",
      after: { kind: "note", pitch: "F#4", hidden: false },
      anchor: anchor(1, 4),
    });
    // Si ya no es un hueco, no hay nada que volver a aplicar.
    const filled = staffScore([{ events: [note("G#4", "3/4"), note("F#4", "1/4")] }]);
    expect(planAgain(request, chosen(filled, anchor(1, 1)), filled)).toMatchObject({
      kind: "refused",
      reason: "same",
    });
  });
});
