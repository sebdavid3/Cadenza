import { queryOptions, type QueryClient } from "@tanstack/react-query";
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

const pendingRefresh = new WeakSet<QueryClient>();

/**
 * Actualiza el listado tras un envío. Si ya está pidiendo algo (otra página o una actualización
 * anterior, también en pausa por falta de red), espera a que termine: invalidar en ese momento
 * cancelaría esa petición, y la que llegara después podría no traer la sesión nueva. Si lo que
 * terminó fue un error, sigue esperando a la próxima petición que salga bien, para no tapar ese
 * error con una actualización.
 */
export function refreshSessions(queryClient: QueryClient) {
  const cache = queryClient.getQueryCache();
  const state = () => cache.find({ queryKey: SESSIONS_QUERY_KEY, exact: true })?.state;
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: SESSIONS_QUERY_KEY });
  };
  const current = state();
  if (!current || current.fetchStatus === "idle") {
    invalidate();
    return;
  }
  if (pendingRefresh.has(queryClient)) return;
  pendingRefresh.add(queryClient);
  const unsubscribe = cache.subscribe(() => {
    const now = state();
    if (now && (now.fetchStatus !== "idle" || now.status === "error")) return;
    unsubscribe();
    pendingRefresh.delete(queryClient);
    invalidate();
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
          const index = waiting.indexOf(start);
          if (index >= 0) waiting.splice(index, 1);
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

/** Hueco de la miniatura (96 × 48 px) a doble densidad, que `object-fit: cover` debe cubrir. */
const THUMBNAIL_BOX = { width: 192, height: 96 };

/** Tamaño reducido que aún cubre el hueco, o null si la imagen ya es igual o más pequeña. */
export function thumbnailSize(width: number, height: number) {
  const scale = Math.max(THUMBNAIL_BOX.width / width, THUMBNAIL_BOX.height / height);
  if (!(scale < 1)) return null;
  return {
    width: Math.max(1, Math.round(width * scale)),
    height: Math.max(1, Math.round(height * scale)),
  };
}

/**
 * Reduce la imagen al tamaño de la miniatura para no guardar ni decodificar escaneos enteros en
 * un hueco de 96 × 48. Si el navegador no puede, se queda la original.
 */
export async function shrinkForThumbnail(blob: Blob): Promise<Blob> {
  if (!("createImageBitmap" in globalThis) || !("OffscreenCanvas" in globalThis)) return blob;
  const bitmaps: ImageBitmap[] = [];
  try {
    const full = await createImageBitmap(blob);
    bitmaps.push(full);
    const size = thumbnailSize(full.width, full.height);
    if (!size) return blob;
    const small = await createImageBitmap(full, {
      resizeWidth: size.width,
      resizeHeight: size.height,
      resizeQuality: "high",
    });
    bitmaps.push(small);
    const canvas = new OffscreenCanvas(size.width, size.height);
    const context = canvas.getContext("2d");
    if (!context) return blob;
    // Con el tamaño explícito: si el navegador no aplicara resizeWidth, se reduce aquí.
    context.drawImage(small, 0, 0, size.width, size.height);
    return await canvas.convertToBlob({ type: "image/png" });
  } catch {
    return blob;
  } finally {
    for (const bitmap of bitmaps) bitmap.close();
  }
}

/**
 * La API solo sirve la imagen original, sin miniaturas: se descargan de pocas en pocas, se
 * reducen y el Blob pequeño se guarda en la caché de consultas, que se vacía al cerrar la sesión.
 */
const thumbnailSlots = createLimiter(3);

export const sessionImageQuery = (api: ApiClient, sessionId: string) =>
  queryOptions({
    queryKey: ["session-image", sessionId],
    queryFn: ({ signal }) =>
      thumbnailSlots(
        async () => shrinkForThumbnail(await sessionImage(api, sessionId, signal)),
        signal,
      ),
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
