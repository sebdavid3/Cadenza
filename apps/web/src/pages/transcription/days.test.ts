import { describe, expect, it } from "vitest";
import type { SessionSummaryRead } from "../../types";
import { dayParts, daysWithToday, groupByDay, relativeDay } from "./days";

function session(id: string, createdAt: string): SessionSummaryRead {
  return {
    session_id: id,
    document_id: `doc-${id}`,
    omr_engine: "homr",
    status: "transcribed",
    created_at: createdAt,
  };
}

// Las pruebas corren en la hora de Bogotá (UTC−5).
describe("diario de sesiones por días (#370)", () => {
  it("agrupa por el día local, no por el de UTC, en el orden de la API", () => {
    const days = groupByDay([
      // 02:00 UTC del 10 es aún el 9 en Bogotá.
      session("a", "2026-11-10T02:00:00"),
      session("b", "2026-11-09T15:00:00"),
      session("c", "2026-11-03T23:30:00Z"),
    ]);

    expect(days.map((day) => day.key)).toEqual(["2026-11-09", "2026-11-03"]);
    expect(days[0]?.sessions.map((s) => s.session_id)).toEqual(["a", "b"]);
  });

  it("une un día que reaparece más abajo en lugar de repetirlo", () => {
    const days = groupByDay([
      session("a", "2026-11-09T15:00:00"),
      session("b", "2026-11-08T15:00:00"),
      session("c", "2026-11-09T14:00:00"),
    ]);

    expect(days.map((day) => [day.key, day.sessions.length])).toEqual([
      ["2026-11-09", 2],
      ["2026-11-08", 1],
    ]);
  });

  it("deja aparte, sin fecha, una sesión cuya fecha no se puede leer", () => {
    const [day] = groupByDay([session("a", "no es una fecha")]);

    expect(day?.key).toBe("sin-fecha");
    expect(day && dayParts(day)).toEqual({
      number: "—",
      monthYear: "Sin fecha",
      full: "Sin fecha",
    });
  });

  it("pone hoy primero cuando hay algo en la cola, aunque no tenga sesiones", () => {
    const now = new Date(2026, 10, 9, 10, 0);
    const older = groupByDay([session("a", "2026-11-03T15:00:00")]);

    expect(daysWithToday(older, now, false).map((day) => day.key)).toEqual(["2026-11-03"]);
    const withToday = daysWithToday(older, now, true);
    expect(withToday.map((day) => day.key)).toEqual(["2026-11-09", "2026-11-03"]);
    expect(withToday[0]?.sessions).toEqual([]);

    const today = groupByDay([
      session("b", "2026-11-09T14:00:00"),
      session("a", "2026-11-03T15:00:00"),
    ]);
    expect(daysWithToday(today, now, true).map((day) => day.key)).toEqual([
      "2026-11-09",
      "2026-11-03",
    ]);
  });

  it("dice «Hoy» y «Ayer» y da el número, el mes y la fecha entera", () => {
    const now = new Date(2026, 10, 9, 10, 0);
    const days = groupByDay([
      session("a", "2026-11-09T15:00:00"),
      session("b", "2026-11-08T15:00:00"),
      session("c", "2026-11-03T15:00:00"),
    ]);

    expect(days.map((day) => relativeDay(day, now))).toEqual(["Hoy", "Ayer", null]);
    expect(days[2] && dayParts(days[2])).toEqual({
      number: "03",
      monthYear: "nov 2026",
      full: "martes, 3 de noviembre de 2026",
    });
  });
});
