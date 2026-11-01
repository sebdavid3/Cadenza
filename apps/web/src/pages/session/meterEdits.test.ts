import { describe, expect, it } from "vitest";
import type {
  AnchorPayload,
  MeasurePayload,
  ScoreEventPayload,
  ScoreIRPayload,
  TimeSignaturePayload,
} from "../../types";
import type { EditTarget } from "./edits";
import {
  activeTime,
  hasTriplet,
  planTime,
  planTuplet,
  replanMeter,
  timeLabel,
  timeRange,
  TIME_SIGNATURES,
  tupletPressed,
  type MeterDecision,
  type TimeChoice,
} from "./meterEdits";

function note(
  pitch: string | null,
  duration: string | null,
  changes: Partial<ScoreEventPayload> = {},
) {
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

const eighths = (count: number, duration = "1/2") =>
  Array.from({ length: count }, (_unused, index) => note(index % 2 ? "E4" : "C4", duration));

function anchor(measure: number, eventIndex = 0, changes: Partial<AnchorPayload> = {}) {
  return {
    part: 0,
    staff: 0,
    measure,
    voice: 0,
    event_index: eventIndex,
    staff_id: "part-0-staff-0",
    bbox: null,
    confidence: null,
    ...changes,
  } satisfies AnchorPayload;
}

const time = (beats: number, beatType: number, symbol: TimeSignaturePayload["symbol"] = null) => ({
  beats,
  beat_type: beatType,
  ...(symbol ? { symbol } : {}),
});

/** Una parte con un pentagrama por lista de compases; cada compás, sus eventos y su compás. */
function score(
  ...staves: { events: ScoreEventPayload[]; time?: TimeSignaturePayload | null }[][]
): ScoreIRPayload {
  return {
    parts: [
      {
        id: "part-0",
        staves: staves.map((measures, staff) => ({
          id: `part-0-staff-${String(staff)}`,
          measures: measures.map((measure, index): MeasurePayload => ({
            number: index + 1,
            events: measure.events,
            time_signature: measure.time === undefined ? time(3, 2) : measure.time,
          })),
        })),
      },
    ],
  };
}

function target(current: ScoreIRPayload, at: AnchorPayload): EditTarget {
  const measure = current.parts[0]?.staves[at.staff]?.measures.find(
    (candidate) => candidate.number === at.measure,
  );
  const event = measure?.events.filter((candidate) => candidate.voice === at.voice)[at.event_index];
  if (!event) throw new Error("sin evento");
  return { anchor: at, event, chord: false };
}

const CUT: TimeChoice = { beats: 2, beat_type: 2, symbol: "cut" };
const COMMON: TimeChoice = { beats: 4, beat_type: 4, symbol: "common" };
const FOUR: TimeChoice = { beats: 4, beat_type: 4, symbol: null };

describe("cambiar el compás (SetTime)", () => {
  // Un piano leído en 3/2 en los compases 1 a 4, con un cambio a 2/2 en el 5.
  const piano = () =>
    score(
      [1, 2, 3, 4, 5].map((number) => ({
        events: eighths(12),
        time: number === 5 ? time(2, 2) : time(3, 2),
      })),
      [1, 2, 3, 4, 5].map((number) => ({
        events: [note("C3", "6")],
        time: number === 5 ? time(2, 2) : time(3, 2),
      })),
    );

  it("ofrece C y ¢ con su métrica y las indicaciones con números", () => {
    expect(TIME_SIGNATURES.map(timeLabel).slice(0, 4)).toEqual([
      "C (4/4)",
      "¢ (2/2)",
      "2/4",
      "3/4",
    ]);
  });

  it("pone ¢ desde el compás elegido hasta el siguiente cambio, en toda la parte", () => {
    const current = piano();
    expect(planTime(CUT, anchor(1, 3), current)).toEqual({
      kind: "edit",
      op: "SetTime",
      after: { time_signature: { beats: 2, beat_type: 2, symbol: "cut" } },
      time: CUT,
      anchor: anchor(1),
      change: "compás ¢ en los compases 1 a 4",
      notice: "Las figuras no cambian: revalida para ver los compases que no cuadran.",
    });
    // Desde un compás del tramo, hasta su final; en el pentagrama de abajo, lo mismo.
    expect(planTime(FOUR, anchor(3, 0, { staff: 1 }), current)).toMatchObject({
      after: { time_signature: { beats: 4, beat_type: 4 } },
      anchor: { measure: 3, staff: 1, event_index: 0 },
      change: "compás 4/4 en los compases 3 a 4",
    });
    expect(timeRange(current, anchor(5))).toEqual({ from: 5, until: 5 });
    expect(activeTime(current, anchor(2))).toEqual({ beats: 3, beat_type: 2, symbol: null });
  });

  it("C y 4/4 son la misma métrica pero no la misma grafía", () => {
    const current = score([
      { events: eighths(8), time: time(4, 4) },
      { events: eighths(8), time: null },
    ]);
    expect(planTime(FOUR, anchor(1), current)).toMatchObject({
      kind: "refused",
      reason: "same",
      message: "El compás ya tiene esa indicación.",
    });
    // Un compás sin indicación hereda la del anterior, y es del mismo tramo.
    expect(planTime(FOUR, anchor(2), current)).toMatchObject({ kind: "refused", reason: "same" });
    expect(planTime(COMMON, anchor(1), current)).toMatchObject({
      kind: "edit",
      after: { time_signature: { beats: 4, beat_type: 4, symbol: "common" } },
      change: "compás C en los compases 1 a 2",
    });
    expect(activeTime(current, anchor(2))).toEqual(FOUR);
    const common = score([{ events: eighths(8), time: time(4, 4, "common") }]);
    expect(activeTime(common, anchor(1))).toEqual(COMMON);
    expect(planTime(FOUR, anchor(1), common)).toMatchObject({
      kind: "edit",
      change: "compás 4/4 en el compás 1",
    });
  });

  it("no lo cambia si los pentagramas de la parte no llevan el mismo compás", () => {
    const uneven = score(
      [{ events: eighths(12), time: time(3, 2) }],
      [{ events: [note("C3", "4")], time: time(2, 2) }],
    );
    expect(planTime(CUT, anchor(1), uneven)).toMatchObject({
      kind: "refused",
      reason: "meter",
      message: expect.stringContaining("no llevan el mismo compás") as string,
    });
    expect(planTime(CUT, null, uneven)).toMatchObject({ kind: "refused", reason: "no-target" });
  });
});

describe("poner y quitar tresillos (SetTuplet)", () => {
  it("convierte en tresillos todas las corcheas del compás con una edición", () => {
    const current = score([{ events: eighths(12) }]);
    const plan = planTuplet("measure", target(current, anchor(1, 5)), current, null);
    expect(plan).toEqual({
      kind: "edit",
      op: "SetTuplet",
      after: { durations: Array<string>(12).fill("1/3") },
      tuplet: { scope: "measure", put: true, chosen: anchor(1, 5), from: null },
      anchor: anchor(1, 0),
      change: "tresillo en 12 figuras del compás 1",
    });
    expect(tupletPressed("measure", target(current, anchor(1, 5)), current, null)).toBe(false);
  });

  it("lo quita si todas lo llevan, y en un compás a medias lo pone a las que no", () => {
    const tripled = score([{ events: eighths(12, "1/3") }]);
    expect(planTuplet("measure", target(tripled, anchor(1)), tripled, null)).toMatchObject({
      after: { durations: Array<string>(12).fill("1/2") },
      tuplet: { put: false },
      change: "quitar el tresillo de 12 figuras del compás 1",
    });
    expect(tupletPressed("measure", target(tripled, anchor(1)), tripled, null)).toBe(true);

    // HOMR leyó el «3» solo en el primer grupo.
    const half = score([{ events: [...eighths(3, "1/3"), ...eighths(9)] }]);
    expect(planTuplet("measure", target(half, anchor(1, 7)), half, null)).toMatchObject({
      after: { durations: Array<string>(9).fill("1/3") },
      anchor: { event_index: 3 },
      change: "tresillo en 9 figuras del compás 1",
    });
    // Con figuras con tresillo entre las que no lo llevan, por grupos.
    const scattered = score([{ events: [...eighths(3), ...eighths(3, "1/3"), ...eighths(3)] }]);
    expect(planTuplet("measure", target(scattered, anchor(1)), scattered, null)).toMatchObject({
      kind: "refused",
      reason: "meter",
    });
  });

  it("R pone el tresillo a tres figuras desde la elegida y lo quita a su grupo", () => {
    const current = score([{ events: [note("C4", "1"), ...eighths(6)] }]);
    expect(planTuplet("group", target(current, anchor(1, 2)), current, null)).toMatchObject({
      after: { durations: ["1/3", "1/3", "1/3"] },
      anchor: { event_index: 2 },
      change: "tresillo en 3 figuras del compás 1",
    });
    // Desde la cuarta corchea no quedan tres.
    expect(planTuplet("group", target(current, anchor(1, 5)), current, null)).toMatchObject({
      kind: "refused",
      message: expect.stringContaining("No quedan tres figuras") as string,
    });

    // En un compás de doce corcheas de tresillo, la elegida quita el de su grupo de tres.
    const tripled = score([{ events: [note("C4", "1"), ...eighths(9, "1/3")] }]);
    expect(planTuplet("group", target(tripled, anchor(1, 5)), tripled, null)).toMatchObject({
      after: { durations: ["1/2", "1/2", "1/2"] },
      anchor: { event_index: 4 },
      change: "quitar el tresillo de 3 figuras del compás 1",
    });
    expect(tupletPressed("group", target(tripled, anchor(1, 9)), tripled, null)).toBe(true);
    expect(tupletPressed("group", target(tripled, anchor(1, 0)), tripled, null)).toBe(false);
  });

  it("un acorde cuenta como una figura y sus notas cambian con él; el adorno no cambia", () => {
    const current = score([
      {
        events: [
          note("C4", "1/2"),
          note("E4", "1/2", { is_chord: true }),
          note("D4", null),
          note("D4", "1/2"),
          note("E4", "1/2"),
          note("F4", "1/2"),
        ],
      },
    ]);
    // Elegida la segunda nota del acorde, el tramo empieza en la primera.
    expect(planTuplet("group", target(current, anchor(1, 1)), current, null)).toMatchObject({
      after: { durations: ["1/3", "1/3", null, "1/3", "1/3"] },
      anchor: { event_index: 0 },
      change: "tresillo en 4 figuras del compás 1",
    });
  });

  it("una figura con puntillo no pasa a tresillo, ni se quita uno que no es de 3:2", () => {
    const dotted = score([{ events: [note("C4", "3/4"), note("D4", "1/4"), note("E4", "1/2")] }]);
    expect(planTuplet("group", target(dotted, anchor(1)), dotted, null)).toMatchObject({
      kind: "refused",
      message: "Una figura con puntillo no pasa a tresillo: quítale antes el puntillo.",
    });
    const nested = score([{ events: [note("C4", "2/9"), note("D4", "2/9"), note("E4", "2/9")] }]);
    expect(planTuplet("group", target(nested, anchor(1)), nested, null)).toMatchObject({
      kind: "refused",
      message: expect.stringContaining("no es de un tresillo de 3:2") as string,
    });
    expect(planTuplet("group", null, nested, null)).toMatchObject({ reason: "no-target" });
    expect(hasTriplet("2/3")).toBe(true);
    expect(hasTriplet("3/2")).toBe(false);
    expect(hasTriplet(null)).toBe(false);
  });

  it("desde el inicio marcado hasta la elegida, en la misma voz del mismo compás", () => {
    const current = score([
      { events: [note("C4", "1"), note("D4", "1/2"), note("E4", "1"), note("F4", "1/2")] },
    ]);
    // Elegir antes el final da lo mismo.
    expect(planTuplet("range", target(current, anchor(1, 0)), current, anchor(1, 1))).toMatchObject(
      {
        after: { durations: ["2/3", "1/3"] },
        tuplet: { scope: "range", put: true, from: anchor(1, 1) },
        anchor: { event_index: 0 },
      },
    );
    expect(planTuplet("range", target(current, anchor(1, 3)), current, null)).toMatchObject({
      kind: "refused",
      message: expect.stringContaining("Marca antes el inicio") as string,
    });
    expect(
      planTuplet("range", target(current, anchor(1, 3)), current, anchor(1, 0, { voice: 1 })),
    ).toMatchObject({ kind: "refused", message: expect.stringContaining("misma voz") as string });
  });

  it("tras un 409 vuelve a pedir el mismo tresillo, salvo que ya esté puesto", () => {
    const current = score([{ events: eighths(12) }]);
    const plan = planTuplet("measure", target(current, anchor(1, 5)), current, null);
    if (plan.kind !== "edit" || plan.op !== "SetTuplet") throw new Error("sin plan");
    const decided: MeterDecision = { op: "SetTuplet", after: plan.after, tuplet: plan.tuplet };
    const same = (at: AnchorPayload) => at;
    expect(replanMeter(decided, anchor(1), current, same)).toMatchObject({
      plan: { kind: "edit", after: plan.after },
      anchor: anchor(1, 5),
    });
    const done = score([{ events: eighths(12, "1/3") }]);
    expect(replanMeter(decided, anchor(1), done, same)).toMatchObject({
      plan: { kind: "refused", reason: "same", message: "Esas figuras ya llevan el tresillo." },
    });
    expect(replanMeter(decided, anchor(1), current, () => null)).toMatchObject({
      plan: { kind: "refused", reason: "no-target" },
      anchor: null,
    });
    // El compás, en el mismo compás con su tramo de ahora.
    const time: MeterDecision = {
      op: "SetTime",
      after: { time_signature: { beats: 2, beat_type: 2, symbol: "cut" } },
      time: CUT,
    };
    expect(replanMeter(time, anchor(1), current, same).plan).toMatchObject({
      kind: "edit",
      change: "compás ¢ en el compás 1",
    });
  });
});
