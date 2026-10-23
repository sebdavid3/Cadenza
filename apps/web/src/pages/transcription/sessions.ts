import type { ApiClient } from "../../api/client";
import type { SessionSummaryRead, UserRead } from "../../types";

export const SESSIONS_PAGE_SIZE = 20;
export const SESSIONS_QUERY_KEY = ["sessions"] as const;

export function listSessions(api: ApiClient, offset: number, signal?: AbortSignal) {
  return api.request<SessionSummaryRead[]>("/sessions", {
    query: { limit: SESSIONS_PAGE_SIZE, offset },
    signal,
  });
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

/** `created_at` llega sin zona horaria pero es UTC. */
export function parseUtc(value: string): Date {
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value);
  return new Date(hasZone ? value : `${value}Z`);
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

const STATUS_LABELS: Record<string, string> = {
  transcribed: "Transcrita",
  correcting: "En corrección",
  finalized: "Finalizada",
  failed: "Fallida",
};

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}
