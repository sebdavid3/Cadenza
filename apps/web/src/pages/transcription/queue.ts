import { create } from "zustand";
import type { ApiClient } from "../../api/client";
import { TRANSCRIBE_TIMEOUT_MS } from "../../api/config";
import { ApiError } from "../../api/errors";
import type { TranscribeResponse } from "../../types";

/** Límite de la API: `max_upload_size_bytes` (20 MB). */
export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
const ACCEPTED_TYPES = new Set(["image/png", "image/jpeg"]);
const ACCEPTED_EXTENSIONS = /\.(png|jpe?g)$/i;

export type ItemStatus = "queued" | "transcribing" | "done" | "error";

export interface QueueItem {
  id: string;
  file: File;
  status: ItemStatus;
  result?: TranscribeResponse;
  error?: string;
  /** Rechazado antes de enviarlo: no se puede reintentar tal cual. */
  rejected?: boolean;
}

/** Comprobación previa en el navegador; la API sigue siendo la autoridad (magic bytes). */
export function precheck(file: File): string | null {
  const typeOk =
    ACCEPTED_TYPES.has(file.type) || (!file.type && ACCEPTED_EXTENSIONS.test(file.name));
  if (!typeOk) return "No es una imagen PNG o JPEG.";
  if (file.size > MAX_UPLOAD_BYTES) return "Supera el tamaño máximo de 20 MB.";
  if (file.size === 0) return "El archivo está vacío.";
  return null;
}

/** Mensajes de la transcripción: aquí un 422 es una imagen sin partitura reconocible. */
export function transcribeErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "No se pudo transcribir. Inténtalo de nuevo.";
  switch (error.kind) {
    case "validation":
      return "No se reconoció ninguna partitura en la imagen.";
    case "unsupported-media-type":
      return "El servidor no la reconoce como imagen PNG o JPEG.";
    case "timeout":
      return "La transcripción tardó más de 30 s. Inténtalo de nuevo.";
    default:
      return error.message;
  }
}

let nextId = 0;
const newId = () => `img-${String(++nextId)}`;

interface QueueState {
  items: QueueItem[];
  running: boolean;
  /** Persona dueña de la cola: si entra otra en la misma pestaña, la cola se vacía. */
  ownerId: string | null;
  claim: (ownerId: string) => void;
  reset: () => void;
  add: (files: Iterable<File>) => void;
  remove: (id: string) => void;
  retry: (id: string) => void;
  clearFinished: () => void;
  /** Envía los pendientes de uno en uno; termina cuando no queda ninguno en cola. */
  run: (api: ApiClient, onTranscribed?: (result: TranscribeResponse) => void) => Promise<void>;
}

export const useQueueStore = create<QueueState>()((set, get) => {
  const patch = (id: string, changes: Partial<QueueItem>) => {
    set((state) => ({
      items: state.items.map((item) => (item.id === id ? { ...item, ...changes } : item)),
    }));
  };

  return {
    items: [],
    running: false,
    ownerId: null,
    claim: (ownerId) => {
      if (get().ownerId !== ownerId) set({ items: [], ownerId });
    },
    reset: () => {
      set({ items: [], ownerId: null });
    },
    add: (files) => {
      const added = [...files].map((file): QueueItem => {
        const problem = precheck(file);
        return problem
          ? { id: newId(), file, status: "error", error: problem, rejected: true }
          : { id: newId(), file, status: "queued" };
      });
      set((state) => ({ items: [...state.items, ...added] }));
    },
    remove: (id) => {
      set((state) => ({
        items: state.items.filter((item) => item.id !== id || item.status === "transcribing"),
      }));
    },
    retry: (id) => {
      const item = get().items.find((candidate) => candidate.id === id);
      if (item?.status === "error" && !item.rejected) {
        patch(id, { status: "queued", error: undefined });
      }
    },
    clearFinished: () => {
      set((state) => ({
        items: state.items.filter(
          (item) => item.status === "queued" || item.status === "transcribing",
        ),
      }));
    },
    run: async (api, onTranscribed) => {
      if (get().running) return;
      set({ running: true });
      try {
        for (;;) {
          const next = get().items.find((item) => item.status === "queued");
          if (!next) break;
          patch(next.id, { status: "transcribing" });
          const body = new FormData();
          body.append("file", next.file, next.file.name);
          try {
            const result = await api.request<TranscribeResponse>("/transcribe", {
              method: "POST",
              body,
              timeoutMs: TRANSCRIBE_TIMEOUT_MS,
            });
            patch(next.id, { status: "done", result });
            onTranscribed?.(result);
          } catch (error) {
            patch(next.id, { status: "error", error: transcribeErrorMessage(error) });
            // Sin sesión no tiene sentido seguir: el resto espera a que se vuelva a entrar.
            if (error instanceof ApiError && error.kind === "unauthorized") break;
          }
        }
      } finally {
        set({ running: false });
      }
    },
  };
});
