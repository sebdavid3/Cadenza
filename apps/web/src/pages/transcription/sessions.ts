import { queryOptions } from "@tanstack/react-query";
import type { ApiClient } from "../../api/client";
import { ApiError } from "../../api/errors";
import type { SessionSummaryRead, UserRead } from "../../types";

export const SESSIONS_PAGE_SIZE = 20;
export const SESSIONS_QUERY_KEY = ["sessions"] as const;

export async function listSessions(api: ApiClient, offset: number, signal?: AbortSignal) {
  const page = await api.request("/sessions", {
    query: { limit: SESSIONS_PAGE_SIZE, offset },
    signal,
  });
  // El contrato devuelve una lista; otra cosa se trata como respuesta inesperada, no se pinta.
  if (!Array.isArray(page)) throw new ApiError("unexpected", 200);
  return page as SessionSummaryRead[];
}

export function listUsers(api: ApiClient, signal?: AbortSignal) {
  return api.request<UserRead[]>("/users", { signal });
}

export function sessionImage(api: ApiClient, sessionId: string, signal?: AbortSignal) {
  return api.request<Blob>(`/sessions/${encodeURIComponent(sessionId)}/image`, {
    responseType: "blob",
    signal,
  });
}

/**
 * Limita cuántas tareas corren a la vez; las demás esperan su turno en orden. Al terminar una,
 * su hueco pasa directamente a la siguiente, y la que se cancela mientras espera no lo ocupa.
 */
export function createLimiter(max: number) {
  let active = 0;
  const waiting: (() => void)[] = [];
  const release = () => {
    const next = waiting.shift();
    if (next) next();
    else active -= 1;
  };
  return async function limit<T>(task: () => Promise<T>, signal?: AbortSignal): Promise<T> {
    if (signal?.aborted) throw new ApiError("aborted");
    if (active < max) {
      active += 1;
    } else {
      await new Promise<void>((resolve, reject) => {
        const start = () => {
          signal?.removeEventListener("abort", cancel);
          resolve();
        };
        const cancel = () => {
          waiting.splice(waiting.indexOf(start), 1);
          reject(new ApiError("aborted"));
        };
        waiting.push(start);
        signal?.addEventListener("abort", cancel, { once: true });
      });
    }
    try {
      return await task();
    } finally {
      release();
    }
  };
}

/**
 * La API solo sirve la imagen original, sin miniaturas: se descargan de pocas en pocas y el Blob
 * se guarda en la caché de consultas, que se vacía al cerrar la sesión.
 */
const thumbnailSlots = createLimiter(3);

export const sessionImageQuery = (api: ApiClient, sessionId: string) =>
  queryOptions({
    queryKey: ["session-image", sessionId],
    queryFn: ({ signal }) => thumbnailSlots(() => sessionImage(api, sessionId, signal), signal),
    // La imagen de una sesión no cambia.
    staleTime: Infinity,
  });

/** `created_at` llega sin zona horaria pero es UTC. */
export function parseUtc(value: string): Date {
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value);
  return new Date(hasZone ? value : `${value}Z`);
}

/** Valor de `<time dateTime>`: ISO con zona; si la fecha no se puede leer, la cadena tal cual. */
export function isoUtc(value: string): string {
  const date = parseUtc(value);
  return Number.isNaN(date.getTime()) ? value : date.toISOString();
}

const DATE_FORMAT = new Intl.DateTimeFormat("es", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

export function formatDate(value: string): string {
  const date = parseUtc(value);
  return Number.isNaN(date.getTime()) ? value : DATE_FORMAT.format(date);
}

const DAY_FORMAT = new Intl.DateTimeFormat("es", {
  day: "numeric",
  month: "short",
  year: "numeric",
});
const TIME_FORMAT = new Intl.DateTimeFormat("es", { hour: "2-digit", minute: "2-digit" });

/** Día y hora por separado, para partir la fecha en dos líneas controladas. */
export function formatDay(value: string): string {
  const date = parseUtc(value);
  return Number.isNaN(date.getTime()) ? value : DAY_FORMAT.format(date);
}

export function formatTime(value: string): string {
  const date = parseUtc(value);
  return Number.isNaN(date.getTime()) ? "" : TIME_FORMAT.format(date);
}

const STATUS_LABELS: Record<string, string> = {
  transcribed: "Transcrita",
  correcting: "En corrección",
  finalized: "Finalizada",
  failed: "Fallida",
};

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}
