import { describe, expect, it } from "vitest";
import type { AnchorPayload, ScoreEventPayload, ScoreIRPayload } from "../../types";
import {
  eventAt,
  planCommand,
  staffPitch,
  staffSteps,
  writeDuration,
  type EditTarget,
} from "./edits";
import type { SelectableEvent } from "./noteMap";
import type { Box } from "./osmd";
import { ledgerSteps, staffLines, stepsAt, stepY, writeSpotAt } from "./writing";

/** Escribir con el ratón (#350): la altura de cada línea, el sitio del clic y lo que se envía. */

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

function anchor(eventIndex: number, voice = 0, measure = 1): AnchorPayload {
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

function staffScore(
  events: ScoreEventPayload[],
  clef: { sign: string; line: number; octave_change?: number } = { sign: "G", line: 2 },
  fifths: number | null = null,
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
                events,
                clef,
                key_signature: fifths === null ? null : { fifths, mode: "major" },
              },
            ],
          },
        ],
      },
    ],
  };
}

function chosen(state: ScoreIRPayload, at: AnchorPayload): EditTarget {
  const found = eventAt(state, at);
  if (!found) throw new Error("ancla sin evento");
  return { anchor: at, ...found };
}

describe("la altura de cada línea y cada espacio", () => {
  const treble = { sign: "G", line: 2 };
  const bass = { sign: "F", line: 4 };
  const alto = { sign: "C", line: 3 };

  it.each([
    [treble, 0, 0, "F5"],
    [treble, 1, 0, "E5"],
    [treble, 8, 0, "E4"],
    [treble, 10, 0, "C4"],
    [treble, -2, 0, "A5"],
    [bass, 0, 0, "A3"],
    [bass, 8, 0, "G2"],
    [alto, 4, 0, "C4"],
    [{ sign: "G", line: 2, octave_change: -1 }, 0, 0, "F4"],
    // En sol mayor, la línea de fa es Fa sostenido; en fa mayor, el si es bemol.
    [treble, 7, 1, "F#4"],
    [treble, 4, -1, "Bb4"],
  ])(
    "clave %o, %i medios espacios bajo la quinta línea y armadura %i → %s",
    (clef, steps, fifths, pitch) => {
      expect(staffPitch(clef, fifths, steps)).toBe(pitch);
    },
  );

  it("una clave desconocida no da altura", () => {
    expect(staffPitch({ sign: "TAB", line: 5 }, 0, 0)).toBeNull();
  });

  it("y al revés: dónde se dibuja cada nota", () => {
    expect(staffSteps({ sign: "G", line: 2 }, "F#5")).toBe(0);
    expect(staffSteps({ sign: "G", line: 2 }, "C4")).toBe(10);
    expect(staffSteps({ sign: "F", line: 4 }, "G2")).toBe(8);
    expect(staffSteps({ sign: "G", line: 2 }, null)).toBeNull();
  });
});

describe("el pentagrama dibujado", () => {
  // La franja de un compás lleva dos espacios sobre y bajo las cinco líneas (ADR-0021).
  const box: Box = { left: 20, top: 100, width: 200, height: 80 };

  it("sitúa la quinta línea y el espacio", () => {
    expect(staffLines(box)).toEqual({ top: 120, space: 10 });
  });

  it("redondea al medio espacio más cercano, con cuatro líneas adicionales como mucho", () => {
    const lines = staffLines(box);
    expect(stepsAt(120, lines)).toBe(0);
    expect(stepsAt(126, lines)).toBe(1);
    expect(stepsAt(160, lines)).toBe(8);
    expect(stepsAt(0, lines)).toBe(-8);
    expect(stepsAt(400, lines)).toBe(16);
    expect(stepY(8, lines)).toBe(160);
  });

  it("dibuja las líneas adicionales entre el pentagrama y la nota", () => {
    expect(ledgerSteps(4)).toEqual([]);
    expect(ledgerSteps(-1)).toEqual([]);
    expect(ledgerSteps(-2)).toEqual([-2]);
    expect(ledgerSteps(-5)).toEqual([-2, -4]);
    expect(ledgerSteps(10)).toEqual([10]);
    expect(ledgerSteps(13)).toEqual([10, 12]);
  });
});

describe("insertar ante una nota con adornos", () => {
  it("la nota nueva entra antes de los adornos, no entre ellos y su nota", () => {
    const state = staffScore([note("C5"), note("D5", "1", { duration_beats: null }), note("E5")]);
    const plan = planCommand(
      { kind: "write-insert", pitch: "G4", figure: 4, dotted: false, end: false },
      chosen(state, anchor(2)),
      state,
    );
    expect(plan).toMatchObject({ kind: "edit", op: "InsertEvent", anchor: { event_index: 1 } });
  });
});

describe("dónde cae el clic", () => {
  const measure: Box = { left: 20, top: 100, width: 200, height: 80 };
  const slot = { staff: 0, measure: 0 };

  function selectable(
    index: number,
    left: number,
    top = 135,
    changes: Partial<SelectableEvent> = {},
  ): SelectableEvent {
    const box = { left, top, width: 10, height: 10 };
    return {
      key: `0:0:1:0:${String(index)}`,
      anchor: anchor(index),
      event: note("C5"),
      slot,
      onset: index,
      chord: false,
      grace: false,
      gap: false,
      boxes: [box],
      box,
      ...changes,
    };
  }
  const events = [selectable(0, 50), selectable(1, 100), selectable(2, 150)];
  const at = (x: number, y = 140, list = events) =>
    writeSpotAt(list, x, y, (candidate) =>
      candidate.staff === slot.staff && candidate.measure === slot.measure ? measure : null,
    );

  it("sobre una figura, la sustituye, en su columna", () => {
    const spot = at(104);
    expect(spot?.aim).toMatchObject({ kind: "replace", x: 105 });
    expect(spot?.aim.event.anchor.event_index).toBe(1);
    expect(spot?.steps).toBe(4);
  });

  it("entre dos figuras, inserta antes de la siguiente, en medio del hueco", () => {
    const spot = at(80);
    expect(spot?.aim).toMatchObject({ kind: "insert", end: false, x: 80 });
    expect(spot?.aim.event.anchor.event_index).toBe(1);
  });

  it("tras la última figura, inserta al final; antes de la primera, delante de ella", () => {
    const last = at(200);
    expect(last?.aim).toMatchObject({ kind: "insert", end: true });
    expect(last?.aim.event.anchor.event_index).toBe(2);
    const first = at(30);
    expect(first?.aim).toMatchObject({ kind: "insert", end: false });
    expect(first?.aim.event.anchor.event_index).toBe(0);
  });

  it("en un acorde, sustituye la nota más cercana en vertical", () => {
    // `chord` lo llevan todas las notas del acorde; `is_chord`, las que siguen a la primera.
    const chord = [
      selectable(0, 50),
      selectable(1, 100, 150, { chord: true }),
      selectable(2, 100, 120, {
        chord: true,
        onset: 1,
        event: note("E5", "1", { is_chord: true }),
      }),
    ];
    expect(at(104, 122, chord)?.aim.event.anchor.event_index).toBe(2);
    expect(at(104, 152, chord)?.aim.event.anchor.event_index).toBe(1);
    // Insertar antes de un acorde va antes de su primera nota.
    expect(at(80, 140, chord)?.aim).toMatchObject({ kind: "insert", end: false });
    expect(at(80, 140, chord)?.aim.event.anchor.event_index).toBe(1);
  });

  it("fuera de los compases o lejos del pentagrama, nada", () => {
    expect(at(5)).toBeNull();
    expect(at(100, 30)).toBeNull();
    expect(at(100, 260)).toBeNull();
  });

  it("ajusta las líneas a las cabezas dibujadas cuando el modelo se desvía", () => {
    // El modelo dice que la quinta línea está a 120 px, pero un Mi 4 (8 pasos) se dibuja a 165 px
    // y no a 160: las líneas están 5 px más abajo.
    const drawn = [selectable(0, 100, 160, { event: note("E4") })];
    const steps = (candidate: SelectableEvent) =>
      candidate.event.kind === "note"
        ? staffSteps({ sign: "G", line: 2 }, candidate.event.pitch)
        : null;
    const spot = writeSpotAt(drawn, 104, 165, () => measure, steps);
    expect(spot?.lines.top).toBe(125);
    expect(spot?.steps).toBe(8);
    // Sin ajustar, el mismo punto caería un paso más abajo.
    expect(writeSpotAt(drawn, 104, 165, () => measure)?.steps).toBe(9);
  });

  it("las notas de adorno no se escriben con el ratón", () => {
    const grace = [selectable(0, 100, 135, { grace: true })];
    expect(at(104, 140, grace)).toBeNull();
  });

  it("antes de una nota con adornos, la línea de inserción va antes de ellos", () => {
    const withGrace = [
      selectable(0, 50),
      selectable(1, 80, 135, { grace: true }),
      selectable(2, 100),
    ];
    // Sobre el adorno o antes de él: se inserta ante su nota, con la línea antes del adorno.
    for (const x of [72, 85]) {
      const spot = at(x, 140, withGrace);
      expect(spot?.aim).toMatchObject({ kind: "insert", end: false, x: 70 });
      expect(spot?.aim.event.anchor.event_index).toBe(2);
    }
  });

  it("ante un hueco no se inserta: se escribe en él", () => {
    const gap = { kind: "rest", pitch: null, hidden: true } as const;
    const withGap = [
      selectable(0, 50),
      selectable(1, 100, 135, { gap: true, event: { ...note(null), ...gap } }),
      selectable(2, 150),
    ];
    const spot = at(80, 140, withGap);
    expect(spot?.aim).toMatchObject({ kind: "replace", x: 105 });
    expect(spot?.aim.event.anchor.event_index).toBe(1);
  });

  it("en una voz con un solo silencio, se escribe en él en cualquier sitio del compás", () => {
    const whole = [selectable(0, 100, 135, { event: note(null, "3") })];
    for (const x of [30, 104, 200]) {
      expect(at(x, 140, whole)?.aim).toMatchObject({ kind: "replace", x: 105 });
    }
  });
});

describe("lo que envía cada clic", () => {
  it("una nota cambia de altura; con la misma, no se envía nada", () => {
    const state = staffScore([note("C4"), note("D4")]);
    const target = chosen(state, anchor(0));
    expect(planCommand({ kind: "write", pitch: "G4" }, target, state)).toMatchObject({
      kind: "edit",
      op: "SetPitch",
      after: { pitch: "G4" },
      change: "altura Sol 4",
    });
    expect(planCommand({ kind: "write", pitch: "C4" }, target, state)).toMatchObject({
      kind: "refused",
      reason: "same",
    });
  });

  it("un silencio que se ve o un hueco pasan a ser la nota, con su figura", () => {
    const state = staffScore([note(null, "1/2"), note(null, "1/2", { hidden: true }), note("D4")]);
    expect(planCommand({ kind: "write", pitch: "G4" }, chosen(state, anchor(0)), state)).toEqual({
      kind: "edit",
      op: "SetEventKind",
      after: { kind: "note", pitch: "G4", hidden: false },
      anchor: anchor(0),
      change: "Sol 4 en lugar del silencio de corchea",
    });
    expect(
      planCommand({ kind: "write", pitch: "G4" }, chosen(state, anchor(1)), state),
    ).toMatchObject({ op: "SetEventKind", change: "Sol 4 en el hueco de corchea" });
  });

  it("la figura elegida, con su puntillo; la misma, no se envía", () => {
    const state = staffScore([note("C4"), note("D4", "3/2")]);
    expect(
      planCommand(
        { kind: "write-figure", figure: 3, dotted: false },
        chosen(state, anchor(0)),
        state,
      ),
    ).toMatchObject({ op: "SetDuration", after: { duration_beats: "1/2" } });
    expect(
      planCommand(
        { kind: "write-figure", figure: 4, dotted: true },
        chosen(state, anchor(1)),
        state,
      ),
    ).toMatchObject({ kind: "refused", reason: "same" });
  });

  it("en un tresillo, la figura es de tresillo", () => {
    const state = staffScore([note("C4", "1/3"), note("D4", "1/3"), note("E4", "1/3")]);
    expect(writeDuration(3, false, chosen(state, anchor(1)), state)).toBe("1/3");
    expect(writeDuration(3, false, null, state)).toBe("1/2");
  });

  it("insertar antes del evento o tras el último de su voz, con la figura y la altura", () => {
    const state = staffScore([note("C4"), note("D4"), note("E4", "1", { is_chord: true })]);
    const before = planCommand(
      { kind: "write-insert", pitch: "A4", figure: 3, dotted: false, end: false },
      chosen(state, anchor(2)),
      state,
    );
    // Antes de un acorde, antes de su primera nota.
    expect(before).toMatchObject({
      op: "InsertEvent",
      after: { kind: "note", pitch: "A4", duration_beats: "1/2" },
      anchor: { event_index: 1 },
      select: { event_index: 1 },
    });
    const end = planCommand(
      { kind: "write-insert", pitch: "A4", figure: 5, dotted: true, end: true },
      chosen(state, anchor(2)),
      state,
    );
    expect(end).toMatchObject({
      op: "InsertEvent",
      after: { duration_beats: "3" },
      anchor: { event_index: 3 },
    });
  });

  it("Mayús + clic añade la altura al acorde, tras su última nota", () => {
    const state = staffScore([note("C4"), note("E4", "1", { is_chord: true }), note("D4")]);
    expect(
      planCommand({ kind: "write-chord", pitch: "G4" }, chosen(state, anchor(0)), state),
    ).toMatchObject({
      op: "InsertEvent",
      after: { pitch: "G4", duration_beats: "1", is_chord: true },
      anchor: { event_index: 2 },
    });
    expect(
      planCommand({ kind: "write-chord", pitch: "E4" }, chosen(state, anchor(1)), state),
    ).toMatchObject({ kind: "refused", reason: "same" });
    const rest = staffScore([note(null)]);
    expect(
      planCommand({ kind: "write-chord", pitch: "E4" }, chosen(rest, anchor(0)), rest),
    ).toMatchObject({ kind: "refused", reason: "chord" });
  });

  it("sin evento elegido no se escribe nada", () => {
    const state = staffScore([note("C4")]);
    expect(planCommand({ kind: "write", pitch: "G4" }, null, state)).toMatchObject({
      kind: "refused",
      reason: "no-target",
    });
  });
});
