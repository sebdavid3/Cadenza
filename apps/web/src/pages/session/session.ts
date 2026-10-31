import { queryOptions } from "@tanstack/react-query";
import type { ApiClient } from "../../api/client";
import { ApiError } from "../../api/errors";
import type {
  DismissFindingRequest,
  EditAppliedRead,
  EditEventCreate,
  FindingRead,
  RevalidateResponse,
  SessionViewRead,
  TimingMapRead,
  UndoRequest,
  UndoResponse,
} from "../../types";
import { sessionImage } from "../transcription/sessions";

const sessionPath = (sessionId: string) => `/sessions/${encodeURIComponent(sessionId)}` as const;

/**
 * Detalle de una sesión: su estado actual (`current_seq`), la partitura y el log de ediciones.
 * Con `fields=view`: sin el documento crudo ni el índice de anclas, que la vista no usa y el
 * servidor no tiene que calcular (#275).
 */
export async function fetchSessionDetail(
  api: ApiClient,
  sessionId: string,
  signal?: AbortSignal,
): Promise<SessionViewRead> {
  const detail = await api.request<SessionViewRead>(sessionPath(sessionId), {
    query: { fields: "view" },
    signal,
  });
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
 * con la edición guardada y el estado que crea: su partitura, su MusicXML y su mapa de tiempos si
 * cambia (#275, ADR-0037). No hace falta pedir nada más.
 */
export function postEdit(
  api: ApiClient,
  sessionId: string,
  edit: EditEventCreate,
  signal?: AbortSignal,
  requestId?: string,
): Promise<EditAppliedRead> {
  return api.request<EditAppliedRead>(`${sessionPath(sessionId)}/edits`, {
    method: "POST",
    json: edit,
    signal,
    requestId,
  });
}

/**
 * `POST /sessions/{id}/undo`: deshace en el servidor la última edición vigente sobre el estado
 * `base_seq`, con una edición compensatoria (ADR-0007, ADR-0017). Responde 200 con el `seq` nuevo,
 * la edición deshecha y el estado nuevo, como tras una edición (#275).
 */
export function postUndo(
  api: ApiClient,
  sessionId: string,
  body: UndoRequest,
  signal?: AbortSignal,
  requestId?: string,
): Promise<UndoResponse> {
  return api.request<UndoResponse>(`${sessionPath(sessionId)}/undo`, {
    method: "POST",
    json: body,
    signal,
    requestId,
  });
}

/** Raíz de las consultas de hallazgos de una sesión, de todos sus estados. */
export const sessionFindingsKey = (sessionId: string) =>
  ["session", sessionId, "findings"] as const;

/**
 * Hallazgos de la última validación (`latest_only`), también los descartados para poder
 * contarlos y listarlos aparte (ADR-0021).
 */
export async function fetchSessionFindings(
  api: ApiClient,
  sessionId: string,
  signal?: AbortSignal,
): Promise<FindingRead[]> {
  const findings = await api.request(`${sessionPath(sessionId)}/findings`, {
    query: { latest_only: true, include_dismissed: true },
    signal,
  });
  if (!Array.isArray(findings)) throw new ApiError("unexpected", 200);
  return findings as FindingRead[];
}

export const sessionFindingsQuery = (api: ApiClient, sessionId: string, seq: number) =>
  queryOptions({
    queryKey: [...sessionFindingsKey(sessionId), seq],
    queryFn: ({ signal }) => fetchSessionFindings(api, sessionId, signal),
  });

/**
 * Estado de la última validación que se sabe hecha en esta pestaña (`current_seq` de
 * `POST /validate`). No hay endpoint que lo dé: sin hallazgos, la lista no dice de qué estado es
 * (ADR-0021 §3), así que se guarda al revalidar y la consulta solo lo lee (ADR-0035).
 */
export const validatedSeqQuery = (sessionId: string) =>
  queryOptions({
    queryKey: ["session", sessionId, "validated"],
    queryFn: (): number | null => null,
    enabled: false,
    staleTime: Infinity,
    // Se pierde al recargar la página, no al pasar un rato en otra vista (D64).
    gcTime: Infinity,
  });

const findingPath = (sessionId: string, findingId: number) =>
  `${sessionPath(sessionId)}/findings/${String(findingId)}` as const;

/**
 * `POST /sessions/{id}/findings/{finding_id}/dismiss`: descarta un posible error como falso
 * positivo, con un motivo opcional (#36). No cambia la partitura ni el log de ediciones.
 */
export function dismissFinding(
  api: ApiClient,
  sessionId: string,
  findingId: number,
  body: DismissFindingRequest,
  signal?: AbortSignal,
): Promise<FindingRead> {
  return api.request<FindingRead>(`${findingPath(sessionId, findingId)}/dismiss`, {
    method: "POST",
    json: body,
    signal,
  });
}

/** `POST /sessions/{id}/findings/{finding_id}/restore`: vuelve a dar por activo un descartado. */
export function restoreFinding(
  api: ApiClient,
  sessionId: string,
  findingId: number,
  signal?: AbortSignal,
): Promise<FindingRead> {
  return api.request<FindingRead>(`${findingPath(sessionId, findingId)}/restore`, {
    method: "POST",
    signal,
  });
}

/**
 * `POST /sessions/{id}/validate`: revalida el estado actual del servidor (ADR-0013). Responde con
 * el `current_seq` que validó y solo los hallazgos activos: los descartados que conserva (#36) se
 * piden aparte, con la lista.
 */
export function revalidateSession(
  api: ApiClient,
  sessionId: string,
  signal?: AbortSignal,
): Promise<RevalidateResponse> {
  return api.request<RevalidateResponse>(`${sessionPath(sessionId)}/validate`, {
    method: "POST",
    signal,
  });
}

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
