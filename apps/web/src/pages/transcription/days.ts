import type { SessionSummaryRead } from "../../types";
import { parseUtc } from "./sessions";

/**
 * El diario de la vista de transcripción (#370): las sesiones, agrupadas por el día en que se
 * crearon en la hora local, el más reciente primero.
 */
export interface Day {
  /** `AAAA-MM-DD` en la hora local; «sin-fecha» si la fecha no se puede leer. */
  key: string;
  /** Mediodía local del día: sirve para darle formato sin depender de la hora. */
  date: Date | null;
  sessions: SessionSummaryRead[];
}

const UNDATED = "sin-fecha";

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

/** La clave local de un instante. */
export function dayKey(date: Date): string {
  return `${String(date.getFullYear())}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function noonOf(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate(), 12);
}

/**
 * Agrupa las sesiones por día local en el orden en que llegan (la API, la más reciente primero).
 * Un día que vuelve a aparecer más abajo se une al primero en lugar de repetirse.
 */
export function groupByDay(sessions: SessionSummaryRead[]): Day[] {
  const days = new Map<string, Day>();
  for (const session of sessions) {
    const created = parseUtc(session.created_at);
    const valid = !Number.isNaN(created.getTime());
    const key = valid ? dayKey(created) : UNDATED;
    let day = days.get(key);
    if (!day) {
      day = { key, date: valid ? noonOf(created) : null, sessions: [] };
      days.set(key, day);
    }
    day.sessions.push(session);
  }
  return [...days.values()];
}

/**
 * Los días que se dibujan: los de las sesiones y, si hay algo en la cola, el de hoy, aunque aún
 * no tenga sesiones. Hoy va siempre primero.
 */
export function daysWithToday(days: Day[], now: Date, withToday: boolean): Day[] {
  if (!withToday) return days;
  const key = dayKey(now);
  const today = days.find((day) => day.key === key) ?? { key, date: noonOf(now), sessions: [] };
  return [today, ...days.filter((day) => day.key !== key)];
}

/** «Hoy», «Ayer» o null. */
export function relativeDay(day: Day, now: Date): string | null {
  if (day.key === dayKey(now)) return "Hoy";
  const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1, 12);
  return day.key === dayKey(yesterday) ? "Ayer" : null;
}

const DAY_NUMBER = new Intl.DateTimeFormat("es", { day: "2-digit" });
const MONTH_YEAR = new Intl.DateTimeFormat("es", { month: "short", year: "numeric" });
const FULL_DATE = new Intl.DateTimeFormat("es", {
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
});

/** Las piezas del margen del día: el número en display, el mes y el año, y la fecha entera. */
export function dayParts(day: Day): { number: string; monthYear: string; full: string } {
  if (!day.date) return { number: "—", monthYear: "Sin fecha", full: "Sin fecha" };
  return {
    number: DAY_NUMBER.format(day.date),
    monthYear: MONTH_YEAR.format(day.date).replace(".", ""),
    full: FULL_DATE.format(day.date),
  };
}
