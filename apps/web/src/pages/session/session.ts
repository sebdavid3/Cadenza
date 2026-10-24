import { queryOptions } from "@tanstack/react-query";
import type { ApiClient } from "../../api/client";
import { ApiError } from "../../api/errors";
import type {
  EditEventCreate,
  EditEventRead,
  FindingRead,
  SessionDetailRead,
  TimingMapRead,
  UndoRequest,
  UndoResponse,
} from "../../types";
import { sessionImage } from "../transcription/sessions";

const sessionPath = (sessionId: string) => `/sessions/${encodeURIComponent(sessionId)}` as const;

/** Detalle de una sesión: su estado actual (`current_seq`), la partitura y el log de ediciones. */
export async function fetchSessionDetail(
  api: ApiClient,
  sessionId: string,
  signal?: AbortSignal,
): Promise<SessionDetailRead> {
  const detail = await api.request<SessionDetailRead>(sessionPath(sessionId), { signal });
  // Sin partitura materializada no hay nada que dibujar: se trata como respuesta inesperada.
  if (!detail.current_score) throw new ApiError("unexpected", 200);
  return detail;
}

export const sessionDetailQuery = (api: ApiClient, sessionId: string) =>
  queryOptions({
    queryKey: ["session", sessionId],
    queryFn: ({ signal }) => fetchSessionDetail(api, sessionId, signal),
  });

/**
 * `POST /sessions/{id}/edits`: una corrección sobre el estado `base_seq` (ADR-0011). Responde 201
 * con la edición guardada, no con la partitura: el estado nuevo se pide aparte.
 */
export function postEdit(
  api: ApiClient,
  sessionId: string,
  edit: EditEventCreate,
  signal?: AbortSignal,
): Promise<EditEventRead> {
  return api.request<EditEventRead>(`${sessionPath(sessionId)}/edits`, {
    method: "POST",
    json: edit,
    signal,
  });
}

/**
 * `POST /sessions/{id}/undo`: deshace en el servidor la última edición vigente sobre el estado
 * `base_seq`, con una edición compensatoria (ADR-0007, ADR-0017). Responde 200 con el `seq` nuevo
 * y la edición deshecha; el estado nuevo se pide aparte, como tras una edición.
 */
export function postUndo(
  api: ApiClient,
  sessionId: string,
  body: UndoRequest,
  signal?: AbortSignal,
): Promise<UndoResponse> {
  return api.request<UndoResponse>(`${sessionPath(sessionId)}/undo`, {
    method: "POST",
    json: body,
    signal,
  });
}

/**
 * Hallazgos de la última validación (`latest_only`), también los descartados para poder
 * contarlos y listarlos aparte (ADR-0021).
 */
export const sessionFindingsQuery = (api: ApiClient, sessionId: string, seq: number) =>
  queryOptions({
    queryKey: ["session", sessionId, "findings", seq],
    queryFn: async ({ signal }) => {
      const findings = await api.request(`${sessionPath(sessionId)}/findings`, {
        query: { latest_only: true, include_dismissed: true },
        signal,
      });
      if (!Array.isArray(findings)) throw new ApiError("unexpected", 200);
      return findings as FindingRead[];
    },
  });

/** MusicXML del estado materializado: lo que OSMD dibuja. Cambia con cada edición. */
export const sessionMusicXmlQuery = (api: ApiClient, sessionId: string, seq: number) =>
  queryOptions({
    queryKey: ["session", sessionId, "musicxml", seq],
    queryFn: async ({ signal }) => {
      const blob = await api.request<Blob>(`${sessionPath(sessionId)}/export`, {
        query: { format: "musicxml" },
        responseType: "blob",
        signal,
      });
      return blob.text();
    },
    staleTime: Infinity,
  });

/**
 * Mapa tiempo→ancla del estado materializado (D12): cuándo empieza cada compás y cada evento, en
 * negras. Con las alturas de `current_score`, es lo que se reproduce (ADR-0026).
 */
export const sessionTimingQuery = (api: ApiClient, sessionId: string, seq: number) =>
  queryOptions({
    queryKey: ["session", sessionId, "timing", seq],
    queryFn: async ({ signal }) => {
      const timing = await api.request<TimingMapRead>(`${sessionPath(sessionId)}/timing`, {
        signal,
      });
      if (typeof timing.total_beats !== "string") throw new ApiError("unexpected", 200);
      return timing;
    },
    staleTime: Infinity,
  });

/** Imagen original a tamaño completo (la del listado se reduce para la miniatura). */
export const sessionFullImageQuery = (api: ApiClient, sessionId: string) =>
  queryOptions({
    queryKey: ["session", sessionId, "image"],
    queryFn: ({ signal }) => sessionImage(api, sessionId, signal),
    // La imagen de una sesión no cambia.
    staleTime: Infinity,
  });
