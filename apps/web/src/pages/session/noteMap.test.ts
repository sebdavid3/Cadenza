import { describe, expect, it } from "vitest";
import type { ScoreEventPayload, ScoreIRPayload } from "../../types";
import type { MeasureSlot } from "./findings";
import {
  anchorKey,
  buildNoteMap,
  moveSelection,
  nearestEvent,
  type NoteMap,
  type SelectableEvent,
} from "./noteMap";
import type { Box, DrawnFigure, DrawnVoice } from "./osmd";

function event(changes: Partial<ScoreEventPayload> = {}): ScoreEventPayload {
  return {
    kind: "note",
    voice: 0,
    pitch: "C4",
    duration_beats: "1",
    tie: null,
    is_chord: false,
    bbox: null,
    confidence: null,
    ir_handle: null,
    ...changes,
  };
}

const rest = (duration = "1", voice = 0) =>
  event({ kind: "rest", pitch: null, duration_beats: duration, voice });
const note = (
  pitch: string,
  duration: string | null = "1",
  changes: Partial<ScoreEventPayload> = {},
) => event({ pitch, duration_beats: duration, ...changes });

/** Partitura de una parte con los pentagramas dados, cada uno una lista de compases. */
function score(...staves: ScoreEventPayload[][][]): ScoreIRPayload {
  return {
    parts: [
      {
        id: "part-0",
        staves: staves.map((measures, staff) => ({
          id: `part-0-staff-${String(staff)}`,
          measures: measures.map((events, index) => ({
            number: index + 1,
            events,
            time_signature: index === 0 ? { beats: 4, beat_type: 4 } : null,
          })),
        })),
      },
    ],
  };
}

const MIDI: Record<string, number> = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };

/** Nota dibujada con la altura que daría OSMD y una caja en la columna `x`. */
function drawnNote(pitch: string, x = 0, y = 0) {
  const match = /^([A-G])(#|b)?(\d)$/.exec(pitch);
  if (!match) throw new Error(pitch);
  const alter = match[2] === "#" ? 1 : match[2] === "b" ? -1 : 0;
  return {
    midi: 12 * (Number(match[3]) + 1) + (MIDI[match[1] ?? "C"] ?? 0) + alter,
    step: match[1] ?? "C",
    box: { left: x, top: y, width: 10, height: 8 },
  };
}

function figure(
  pitches: string[] | "rest",
  beats: [number, number] = [1, 1],
  x = 0,
  extra: Partial<DrawnFigure> = {},
): DrawnFigure {
  if (pitches === "rest") {
    return {
      rest: true,
      grace: false,
      beats,
      notes: [{ midi: null, step: null, box: { left: x, top: 0, width: 8, height: 20 } }],
      ...extra,
    };
  }
  return {
    rest: false,
    grace: false,
    beats,
    notes: pitches.map((pitch, index) => drawnNote(pitch, x, index * 10)),
    ...extra,
  };
}

/** Lo dibujado: por pentagrama, por compás, las voces con sus figuras. */
function drawing(...staves: DrawnVoice[][][]) {
  return (slot: MeasureSlot) => staves[slot.staff]?.[slot.measure] ?? null;
}

function complete(map: NoteMap): SelectableEvent[] {
  if (map.status !== "complete") throw new Error(`incompleto: ${JSON.stringify(map)}`);
  return map.events;
}

describe("emparejamiento del ScoreIR con lo dibujado", () => {
  it("empareja en orden notas y silencios y da a cada uno su ancla y su caja", () => {
    const events = complete(
      buildNoteMap(
        score([[note("C4"), rest("1"), note("E4", "2")], [note("G4", "4")]]),
        drawing([
          [[figure(["C4"], [1, 1], 10), figure("rest", [1, 1], 30), figure(["E4"], [2, 1], 50)]],
          [[figure(["G4"], [4, 1], 90)]],
        ]),
      ),
    );

    expect(events.map((selectable) => selectable.key)).toEqual([
      "0:0:1:0:0",
      "0:0:1:0:1",
      "0:0:1:0:2",
      "0:0:2:0:0",
    ]);
    expect(events[1]?.anchor).toEqual({
      part: 0,
      staff: 0,
      measure: 1,
      voice: 0,
      event_index: 1,
      staff_id: "part-0-staff-0",
      bbox: null,
      confidence: null,
    });
    expect(events[1]?.slot).toEqual({ staff: 0, measure: 0 });
    expect(events[2]?.box).toEqual({ left: 50, top: 0, width: 10, height: 8 });
    expect(events[3]?.slot).toEqual({ staff: 0, measure: 1 });
    expect(events[2]?.onset).toBe(2);
  });

  it("empareja cada nota de un acorde por su altura, aunque OSMD las ordene de grave a agudo", () => {
    const events = complete(
      buildNoteMap(
        score([
          [
            note("E5", "2"),
            note("C4", "2", { is_chord: true }),
            note("G4", "2", { is_chord: true }),
            note("A4", "2"),
          ],
        ]),
        drawing([[[figure(["C4", "G4", "E5"], [2, 1], 10), figure(["A4"], [2, 1], 40)]]]),
      ),
    );

    // Las notas del acorde dibujado están a 0, 10 y 20 px de altura, de grave a agudo.
    expect(events.map((selectable) => [selectable.event.pitch, selectable.box.top])).toEqual([
      ["E5", 20],
      ["C4", 0],
      ["G4", 10],
      ["A4", 0],
    ]);
    expect(events.map((selectable) => selectable.anchor.event_index)).toEqual([0, 1, 2, 3]);
    // Las notas de un acorde empiezan a la vez.
    expect(events.map((selectable) => selectable.onset)).toEqual([0, 0, 0, 2]);
  });

  it("une las figuras en que el exportador parte una duración que no cabe en una sola", () => {
    const events = complete(
      buildNoteMap(
        score([[note("G4", "5/4"), note("A4", "3/4"), rest("5/2"), rest("1/2")]]),
        drawing([
          [
            [
              figure(["G4"], [1, 1], 10),
              figure(["G4"], [1, 4], 30),
              figure(["A4"], [3, 4], 50),
              figure("rest", [2, 1], 70),
              figure("rest", [1, 2], 90),
              figure("rest", [1, 2], 110),
            ],
          ],
        ]),
      ),
    );

    expect(events).toHaveLength(4);
    // La caja abarca las dos figuras ligadas.
    expect(events[0]?.box).toEqual({ left: 10, top: 0, width: 30, height: 8 });
    expect(events[0]?.boxes).toHaveLength(2);
    expect(events[2]?.box).toEqual({ left: 70, top: 0, width: 28, height: 20 });
    expect(events[3]?.box.left).toBe(110);
  });

  it("empareja la nota de duración nula o cero con su nota de adorno (D60)", () => {
    // OSMD da a la nota de adorno la duración de su figura (aquí, negra), pero no ocupa tiempo.
    const grace = { grace: true };
    const events = complete(
      buildNoteMap(
        score([[note("F#4", "0"), note("Gb4", null), note("C5", "2")]]),
        drawing([
          [
            [
              figure(["F#4"], [1, 1], 10, grace),
              figure(["Gb4"], [1, 1], 30, grace),
              figure(["C5"], [2, 1], 50),
            ],
          ],
        ]),
      ),
    );

    expect(events.map((selectable) => [selectable.event.pitch, selectable.box.left])).toEqual([
      ["F#4", 10],
      ["Gb4", 30],
      ["C5", 50],
    ]);
  });

  it("un silencio de duración cero sigue contando como un silencio de negra", () => {
    const events = complete(
      buildNoteMap(
        score([[rest("0"), note("C5", "2")]]),
        drawing([[[figure("rest", [1, 1], 10), figure(["C5"], [2, 1], 30)]]]),
      ),
    );
    expect(events.map((selectable) => selectable.onset)).toEqual([0, 1]);
  });

  it("empareja tresillos y ligaduras sin tratarlos aparte", () => {
    const events = complete(
      buildNoteMap(
        score([
          [
            note("C5", "1/3"),
            note("D5", "1/3"),
            note("E5", "1/3"),
            note("F5", "1", { tie: "start" }),
            note("F5", "2", { tie: "stop" }),
          ],
        ]),
        drawing([
          [
            [
              figure(["C5"], [1, 3]),
              figure(["D5"], [1, 3]),
              figure(["E5"], [1, 3]),
              figure(["F5"], [1, 1]),
              figure(["F5"], [2, 1]),
            ],
          ],
        ]),
      ),
    );

    expect(events).toHaveLength(5);
  });

  it("empareja las voces por su orden y conserva el número de voz del ScoreIR en el ancla", () => {
    const events = complete(
      buildNoteMap(
        score([
          [note("E5", "2"), note("C4", "1", { voice: 1 }), note("F5", "2"), rest("1", 1)],
          [note("G4", "4", { voice: 1 })],
        ]),
        drawing([
          [
            [figure(["E5"], [2, 1], 10), figure(["F5"], [2, 1], 50)],
            [figure(["C4"], [1, 1], 10), figure("rest", [1, 1], 30)],
          ],
          [[figure(["G4"], [4, 1], 90)]],
        ]),
      ),
    );

    expect(events.map((selectable) => selectable.key)).toEqual([
      "0:0:1:0:0",
      "0:0:1:0:1",
      "0:0:1:1:0",
      "0:0:1:1:1",
      "0:0:2:1:0",
    ]);
    expect(events[3]?.event.kind).toBe("rest");
    expect(events[3]?.onset).toBe(1);
  });

  it("numera los pentagramas de todas las partes seguidos, como OSMD", () => {
    const twoParts: ScoreIRPayload = {
      parts: [
        score([[note("A4", "4")]]).parts[0],
        {
          id: "part-1",
          staves: [
            {
              id: "part-1-staff-0",
              measures: [{ number: 1, events: [note("F3", "4")], time_signature: null }],
            },
          ],
        },
      ],
    } as ScoreIRPayload;
    const events = complete(
      buildNoteMap(twoParts, drawing([[[figure(["A4"], [4, 1])]]], [[[figure(["F3"], [4, 1])]]])),
    );

    expect(events[1]?.anchor).toMatchObject({ part: 1, staff: 0, staff_id: "part-1-staff-0" });
    expect(events[1]?.slot).toEqual({ staff: 1, measure: 0 });
  });

  it("acepta un compás vacío si OSMD tampoco dibuja nada en él", () => {
    const events = complete(
      buildNoteMap(score([[note("C4", "4")], []]), drawing([[[figure(["C4"], [4, 1])]], []])),
    );
    expect(events).toHaveLength(1);
  });
});

describe("lo que sale del dibujo", () => {
  it("marca como de acorde también la nota que lo empieza", () => {
    const events = complete(
      buildNoteMap(
        score([[note("C4", "2"), note("E4", "2", { is_chord: true }), note("G4", "2")]]),
        drawing([[[figure(["C4", "E4"], [2, 1], 10), figure(["G4"], [2, 1], 40)]]]),
      ),
    );
    expect(events.map((selectable) => selectable.chord)).toEqual([true, true, false]);
  });

  it("una nota de adorno no ocupa tiempo: la siguiente empieza en su mismo instante", () => {
    const events = complete(
      buildNoteMap(
        score([[note("C4", "0"), note("D4"), note("E4")]]),
        drawing([[[figure(["C4"], [1, 1], 0, { grace: true }), figure(["D4"]), figure(["E4"])]]]),
      ),
    );
    expect(events.map((selectable) => selectable.onset)).toEqual([0, 0, 1]);
  });

  it("una nota marcada como de acorde tras un silencio es una figura aparte", () => {
    const events = complete(
      buildNoteMap(
        score([[rest("1"), note("D4", "1", { is_chord: true }), note("E4")]]),
        drawing([[[figure("rest"), figure(["D4"]), figure(["E4"])]]]),
      ),
    );
    expect(events.map((selectable) => [selectable.onset, selectable.chord])).toEqual([
      [0, false],
      [1, false],
      [2, false],
    ]);
  });
});

describe("lo que no se empareja no se ofrece", () => {
  const base = score([[note("C4"), note("D4")], [note("E4", "2")]]);
  const ok = () => [[[figure(["C4"]), figure(["D4"])]], [[figure(["E4"], [2, 1])]]];

  it.each([
    ["otra altura", () => [[[figure(["C4"]), figure(["D#4"])]], [[figure(["E4"], [2, 1])]]]],
    ["otra clase", () => [[[figure(["C4"]), figure("rest")]], [[figure(["E4"], [2, 1])]]]],
    [
      "otra duración",
      () => [[[figure(["C4"]), figure(["D4"], [2, 1])]], [[figure(["E4"], [2, 1])]]],
    ],
    ["una figura de más", () => [[[figure(["C4"]), figure(["D4"]), figure(["E4"])]], ok()[1]]],
    ["una figura de menos", () => [[[figure(["C4"])]], ok()[1]]],
    ["otro número de voces", () => [[[figure(["C4"]), figure(["D4"])], [figure("rest")]], ok()[1]]],
    [
      "una nota de adorno donde la nota tiene duración",
      () => [[[figure(["C4"], [1, 1], 0, { grace: true }), figure(["D4"])]], ok()[1]],
    ],
    ["un acorde con otras notas", () => [[[figure(["C4", "E4"]), figure(["D4"])]], ok()[1]]],
    [
      "una figura sin caja",
      () => [
        [[figure(["C4"]), { ...figure(["D4"]), notes: [{ midi: 62, step: "D", box: null }] }]],
        ok()[1],
      ],
    ],
  ])("con %s en el compás 1, dice cuántos eventos no se pueden elegir", (_name, staves) => {
    const map = buildNoteMap(base, drawing(staves() as DrawnVoice[][]));
    expect(map).toEqual({ status: "incomplete", total: 3, unmatched: 2 });
  });

  it("una nota de duración cero dibujada como negra, como antes de D60, no se empareja", () => {
    const map = buildNoteMap(
      score([[note("G#4", "0"), note("A4", "3")]]),
      drawing([[[figure(["G#4"], [1, 1]), figure(["A4"], [3, 1])]]]),
    );
    expect(map).toEqual({ status: "incomplete", total: 2, unmatched: 2 });
  });

  it("distingue las enarmonías: un Sol bemol no es un Fa sostenido", () => {
    const map = buildNoteMap(score([[note("Gb4", "4")]]), drawing([[[figure(["F#4"], [4, 1])]]]));
    expect(map).toEqual({ status: "incomplete", total: 1, unmatched: 1 });
  });

  it("si OSMD no dibujó un compás, sus eventos no se pueden elegir", () => {
    const map = buildNoteMap(base, drawing([ok()[0] as DrawnVoice[]]));
    expect(map).toEqual({ status: "incomplete", total: 3, unmatched: 1 });
  });

  it("si dos compases de un pentagrama tienen el mismo número, no se elige ninguno de los dos", () => {
    const repeated = score([[note("C4", "4")], [note("D4", "4")]]);
    const second = repeated.parts[0]?.staves[0]?.measures[1];
    if (second) second.number = 1;
    const map = buildNoteMap(
      repeated,
      drawing([[[figure(["C4"], [4, 1])]], [[figure(["D4"], [4, 1])]]]),
    );
    expect(map).toEqual({ status: "incomplete", total: 2, unmatched: 2 });
  });

  it("un evento que no es nota ni silencio no se puede elegir", () => {
    const map = buildNoteMap(
      score([[event({ kind: "clef", pitch: null, duration_beats: "1" })]]),
      drawing([[[figure("rest")]]]),
    );
    expect(map).toEqual({ status: "incomplete", total: 1, unmatched: 1 });
  });
});

describe("moverse entre eventos", () => {
  // Pentagrama 0: compás 1 con dos voces, compás 2 solo con la voz 0 y compás 3 vacío.
  // Pentagrama 1: un compás 1 con dos notas.
  const events = complete(
    buildNoteMap(
      score(
        [
          [
            note("E5"),
            note("F5"),
            note("G5", "2"),
            note("C4", "2", { voice: 1 }),
            note("D4", "2", { voice: 1 }),
          ],
          [note("A5", "2"), note("B5", "2")],
          [],
        ],
        [[note("C3", "3"), note("D3", "1")]],
      ),
      drawing(
        [
          [
            [figure(["E5"], [1, 1], 0), figure(["F5"], [1, 1], 20), figure(["G5"], [2, 1], 40)],
            [figure(["C4"], [2, 1], 0), figure(["D4"], [2, 1], 40)],
          ],
          [[figure(["A5"], [2, 1], 80), figure(["B5"], [2, 1], 100)]],
          [],
        ],
        [[[figure(["C3"], [3, 1], 0), figure(["D3"], [1, 1], 60)]]],
      ),
    ),
  );
  const key = (measure: number, voice: number, index: number, staff = 0) =>
    `0:${String(staff)}:${String(measure)}:${String(voice)}:${String(index)}`;
  const move = (from: string | null, how: Parameters<typeof moveSelection>[2]) =>
    moveSelection(events, from, how)?.key ?? null;

  it("sin nada elegido, cualquier movimiento elige el primer evento", () => {
    expect(move(null, "next")).toBe(key(1, 0, 0));
    expect(move(null, "down")).toBe(key(1, 0, 0));
  });

  it("avanza y retrocede dentro de la voz y pasa de compás", () => {
    expect(move(key(1, 0, 0), "next")).toBe(key(1, 0, 1));
    expect(move(key(1, 0, 2), "next")).toBe(key(2, 0, 0));
    expect(move(key(2, 0, 0), "previous")).toBe(key(1, 0, 2));
    // De la voz 1 al compás 2, que solo tiene la voz 0.
    expect(move(key(1, 1, 1), "next")).toBe(key(2, 0, 0));
    // Al final del pentagrama se queda donde está (el compás 3 está vacío).
    expect(move(key(2, 0, 1), "next")).toBe(key(2, 0, 1));
    expect(move(key(1, 0, 0), "previous")).toBe(key(1, 0, 0));
  });

  it("salta al compás anterior o siguiente y al primero o último del compás", () => {
    expect(move(key(1, 0, 1), "next-measure")).toBe(key(2, 0, 0));
    expect(move(key(2, 0, 1), "previous-measure")).toBe(key(1, 0, 0));
    expect(move(key(1, 1, 1), "previous-measure")).toBe(key(1, 1, 1));
    expect(move(key(1, 0, 1), "measure-end")).toBe(key(1, 0, 2));
    expect(move(key(1, 0, 2), "measure-start")).toBe(key(1, 0, 0));
  });

  it("baja por las voces y después por los pentagramas, al evento que empieza más cerca", () => {
    // Fa5 empieza en la negra 1; en la voz 1 hay Do4 (0) y Re4 (2): gana el que empieza antes.
    expect(move(key(1, 0, 1), "down")).toBe(key(1, 1, 0));
    // Sol5 (negra 2) baja a Re4 (negra 2).
    expect(move(key(1, 0, 2), "down")).toBe(key(1, 1, 1));
    // Re4 (negra 2) baja al pentagrama de abajo: Do3 (0) o Re3 (3), el más cercano es Re3.
    expect(move(key(1, 1, 1), "down")).toBe(key(1, 0, 1, 1));
    expect(move(key(1, 0, 1, 1), "up")).toBe(key(1, 1, 1));
    expect(move(key(1, 0, 0), "up")).toBe(key(1, 0, 0));
    // El compás 2 del pentagrama de abajo no existe: no se mueve.
    expect(move(key(2, 0, 0), "down")).toBe(key(2, 0, 0));
  });

  it("si lo elegido ya no está en el mapa, empieza por el primer evento", () => {
    expect(move("0:0:9:0:0", "next")).toBe(key(1, 0, 0));
  });
});

describe("elegir con el puntero", () => {
  const map = complete(
    buildNoteMap(
      score([
        [note("C4", "2"), note("E4", "2", { is_chord: true }), note("G4", "2")],
        [note("A4", "4")],
      ]),
      drawing([
        [[figure(["C4", "E4"], [2, 1], 20), figure(["G4"], [2, 1], 60)]],
        [[figure(["A4"], [4, 1], 140)]],
      ]),
    ),
  );
  const measures = (slot: MeasureSlot): Box | null =>
    slot.measure === 0
      ? { left: 0, top: -20, width: 100, height: 60 }
      : slot.measure === 1
        ? { left: 100, top: -20, width: 100, height: 60 }
        : null;
  const pick = (x: number, y: number) => nearestEvent(map, x, y, measures)?.event.pitch ?? null;

  it("elige el evento más cercano del compás tocado", () => {
    expect(pick(25, 4)).toBe("C4");
    // Entre Do-Mi (20–30) y Sol (60–70), más cerca de Sol.
    expect(pick(50, 4)).toBe("G4");
    // En el compás 2, aunque Sol esté más cerca en la página.
    expect(pick(105, 4)).toBe("A4");
  });

  it("en un acorde, elige la nota más cercana en vertical", () => {
    expect(pick(25, 13)).toBe("E4");
    expect(pick(25, 2)).toBe("C4");
  });

  it("fuera de los compases no elige nada", () => {
    expect(pick(50, 200)).toBeNull();
  });

  it("elige una nota dibujada fuera de la franja de su compás, con líneas adicionales", () => {
    const drawn = figure(["A6"], [4, 1], 20);
    const high = complete(
      buildNoteMap(
        score([[note("A6", "4")]]),
        drawing([
          [
            [
              {
                ...drawn,
                notes: [{ midi: 93, step: "A", box: { left: 20, top: -60, width: 10, height: 8 } }],
              },
            ],
          ],
        ]),
      ),
    );
    expect(nearestEvent(high, 25, -56, measures)?.event.pitch).toBe("A6");
  });

  it("en una figura partida, mide la distancia a cada una de sus figuras", () => {
    // Sol de 5/4 en dos figuras (10–20 y 70–80) y, entre ellas, el La de la otra voz (40–50).
    const split = complete(
      buildNoteMap(
        score([[note("G4", "5/4"), note("A4", "5/4", { voice: 1 })]]),
        drawing([
          [
            [figure(["G4"], [1, 1], 10), figure(["G4"], [1, 4], 70)],
            [figure(["A4"], [1, 1], 40), figure(["A4"], [1, 4], 100)],
          ],
        ]),
      ),
    );
    expect(nearestEvent(split, 45, 4, measures)?.event.pitch).toBe("A4");
  });

  it("las anclas de los eventos tienen claves únicas", () => {
    const keys = map.map((selectable) => anchorKey(selectable.anchor));
    expect(new Set(keys).size).toBe(keys.length);
  });
});
