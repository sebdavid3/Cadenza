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
  activeFifths,
  carryAnchor,
  editCommand,
  eventAt,
  figureDuration,
  figureOf,
  FIGURES,
  octavePitch,
  planAgain,
  planEdit,
  stepPitch,
  withAccidental,
  type DecidedEdit,
  type EditCommand,
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
    ["1", 4, false],
    ["3/2", 4, true],
    ["2/4", 3, false],
    ["6", 6, true],
    ["1/16", 0, false],
    ["3/32", 0, true],
    // Ni tresillo, ni duración partida, ni nota de adorno son una figura simple.
    ["2/3", null, false],
    ["5/4", null, false],
    ["0", null, false],
    [null, null, false],
  ] as const)("%s es la figura %s con puntillo %s", (duration, figure, dotted) => {
    expect(figureOf(duration)).toEqual({ figure, dotted });
  });

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
  const step = (direction: 1 | -1): EditCommand => ({ kind: "step", direction });

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

  it("una figura sobre una duración que no lo es (tresillo, adorno) la deja sin puntillo", () => {
    expect(planEdit({ kind: "figure", figure: 4 }, target(note("C4", "2/3")), 0)).toMatchObject({
      after: { duration_beats: "1" },
    });
    expect(planEdit({ kind: "figure", figure: 4 }, target(note("C4", "0")), 0)).toMatchObject({
      after: { duration_beats: "1" },
    });
  });

  it.each<[string, EditCommand, EditTarget | null, string]>([
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
    ["la duración de un acorde", { kind: "figure", figure: 4 }, target(note("C4"), true), "chord"],
    ["el puntillo sin figura simple", { kind: "dot" }, target(note("C4", "2/3")), "not-figure"],
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
  ])("%o no edita", (event) => {
    expect(editCommand(event)).toBeNull();
  });
});

describe("llevar un ancla a un estado posterior", () => {
  function edit(seq: number, op: string): EditEventRead {
    return {
      id: `e${String(seq)}`,
      session_id: "s",
      seq,
      op,
      author: "ana",
      anchor: anchor(1),
      before: null,
      after: null,
      created_at: "2026-10-24T00:00:00Z",
    };
  }
  function detail(seq: number, edits: EditEventRead[], events = [note("C4")]): SessionDetailRead {
    return {
      current_seq: seq,
      edits,
      current_score: score([{ events }]),
    } as SessionDetailRead;
  }

  it("la conserva si en medio solo se cambiaron alturas, duraciones, claves o armaduras", () => {
    const later = detail(3, [edit(1, "SetPitch"), edit(2, "SetDuration"), edit(3, "SetKey")]);
    expect(carryAnchor(anchor(1), 1, later)).toEqual(anchor(1));
  });

  it("no la conserva si en medio se insertó o se borró un evento (las posiciones se mueven)", () => {
    expect(
      carryAnchor(anchor(1), 1, detail(2, [edit(1, "SetPitch"), edit(2, "InsertEvent")])),
    ).toBe(null);
    expect(carryAnchor(anchor(1), 0, detail(1, [edit(1, "DeleteEvent")]))).toBeNull();
  });

  it("no la conserva si el evento ya no está", () => {
    expect(carryAnchor(anchor(1, 1), 0, detail(1, [edit(1, "SetPitch")]))).toBeNull();
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
      "si ahora es de un acorde",
      { op: "SetDuration", after: { duration_beats: "1/2" } },
      target(note("C4"), true),
      "chord",
    ],
    ["si ya no hay evento", { op: "SetPitch", after: { pitch: "D4" } }, null, "no-target"],
  ])("no la pide %s", (_name, edit, edited, reason) => {
    expect(planAgain(edit, edited)).toMatchObject({ kind: "refused", reason });
  });
});
