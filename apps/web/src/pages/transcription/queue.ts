import { create } from "zustand";
import type { ApiClient } from "../../api/client";
import { TRANSCRIBE_TIMEOUT_MS } from "../../api/config";
import { ApiError } from "../../api/errors";
import { useAuthStore } from "../../auth/store";
import { registerPendingWork } from "../../pendingWork";
import type { TranscribeResponse } from "../../types";
import { appendScoreData, emptyDraft, type ScoreDataDraft } from "./scoreData";

/** Límite de la API: `max_upload_size_bytes` (20 MB). */
export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
const ACCEPTED_TYPES = new Set(["image/png", "image/jpeg"]);
const ACCEPTED_EXTENSIONS = /\.(png|jpe?g)$/i;

export type ItemStatus = "queued" | "transcribing" | "done" | "error";

export interface QueueItem {
  id: string;
  file: File;
  status: ItemStatus;
  /** Cuándo empezó a transcribirse (ms): el contador no se reinicia al volver a la vista. */
  startedAt?: number;
  result?: TranscribeResponse;
  error?: string;
  /** Rechazado antes de enviarlo: no se puede reintentar tal cual. */
  rejected?: boolean;
  /** Los datos de la partitura que se envían con la imagen (#240); sin ellos, ninguno. */
  data?: ScoreDataDraft;
}

/**
 * Partes que pide el formulario antes de transcribir: la voz o el instrumento de arriba y la
 * segunda, el piano que acompaña. Las que HOMR no detecte se descartan sin error (ADR-0041 §3).
 */
export const PREPARED_PARTS = 2;

/** Una imagen elegida que espera a «Transcribir» (#240, ADR-0045). */
export interface PreparedItem {
  id: string;
  file: File;
  /** Sus propios datos; null, los comunes del lote. */
  own: ScoreDataDraft | null;
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

/** Sin conexión o con el servidor caído no tiene sentido seguir enviando: la cola se pausa. */
function serverUnreachable(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false;
  return error.kind === "network" || [502, 503, 504].includes(error.status ?? 0);
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
      // La imagen ya se había enviado: la API puede terminar y crear la sesión igualmente.
      return "La transcripción tardó más de 30 s. Puede que se haya creado; revisa el listado antes de reintentar.";
    case "server":
      // Con los huecos de HOMR ocupados, la API responde 503 con `Retry-After` (ADR-0024).
      if (error.status === 503) {
        const wait = error.retryAfterSeconds;
        return wait !== null
          ? `El servidor está ocupado con otras transcripciones. Vuelve a probar en ${String(wait)} s.`
          : "El servidor está ocupado con otras transcripciones. Vuelve a probar en unos segundos.";
      }
      return error.message;
    default:
      return error.message;
  }
}

let nextId = 0;
const newId = () => `img-${String(++nextId)}`;

interface QueueState {
  items: QueueItem[];
  running: boolean;
  /** Pausada tras perder el servidor: lo pendiente espera hasta que la persona la reanude. */
  paused: boolean;
  /** Persona dueña de la cola: solo se envía con su sesión, y si entra otra, la cola se vacía. */
  ownerId: string | null;
  /** Imágenes elegidas que aún no se han enviado, y los datos comunes del lote (#240). */
  prepared: PreparedItem[];
  common: ScoreDataDraft;
  claim: (ownerId: string) => void;
  reset: () => void;
  /** Pone las imágenes en la cola, sin datos, y pide que se envíen. */
  add: (files: Iterable<File>) => void;
  /**
   * Prepara las imágenes elegidas: esperan a `submitPrepared` para enviarse. Las que no pasan la
   * comprobación previa van directamente a la cola como rechazadas.
   */
  prepare: (files: Iterable<File>) => void;
  setCommon: (data: ScoreDataDraft) => void;
  /** Datos propios de una imagen preparada; null vuelve a los comunes. */
  setOwn: (id: string, data: ScoreDataDraft | null) => void;
  unprepare: (id: string) => void;
  discardPrepared: () => void;
  /** Pasa lo preparado a la cola, cada imagen con sus datos, y deja el formulario como estaba. */
  submitPrepared: () => void;
  remove: (id: string) => void;
  retry: (id: string) => void;
  clearFinished: () => void;
  resume: () => void;
  /**
   * Envía los pendientes de uno en uno; termina cuando no queda ninguno en cola o cuando la
   * sesión de la dueña ya no está. `onSettled` se llama tras cada envío, salga bien o mal.
   */
  run: (api: ApiClient, onSettled?: () => void) => Promise<void>;
}

export const useQueueStore = create<QueueState>()((set, get) => {
  const patch = (id: string, changes: Partial<QueueItem>) => {
    set((state) => ({
      items: state.items.map((item) => (item.id === id ? { ...item, ...changes } : item)),
    }));
  };

  // Cada vaciado abre una generación nueva: un recorrido de una generación anterior se
  // detiene tras su `await` sin tocar la cola, y su petición en vuelo se cancela.
  let generation = 0;
  let inFlight: AbortController | null = null;
  const cancel = () => {
    generation += 1;
    inFlight?.abort();
    inFlight = null;
  };

  const rejectedItem = (file: File, problem: string): QueueItem => ({
    id: newId(),
    file,
    status: "error",
    error: problem,
    rejected: true,
  });

  return {
    items: [],
    running: false,
    paused: false,
    prepared: [],
    common: emptyDraft(PREPARED_PARTS),
    // Si este módulo se carga con la sesión ya abierta, la cola es de quien está dentro.
    ownerId: useAuthStore.getState().user?.id ?? null,
    claim: (ownerId) => {
      if (get().ownerId === ownerId) return;
      cancel();
      set({
        items: [],
        running: false,
        paused: false,
        ownerId,
        prepared: [],
        common: emptyDraft(PREPARED_PARTS),
      });
    },
    reset: () => {
      cancel();
      set({
        items: [],
        running: false,
        paused: false,
        ownerId: null,
        prepared: [],
        common: emptyDraft(PREPARED_PARTS),
      });
    },
    add: (files) => {
      const added = [...files].map((file): QueueItem => {
        const problem = precheck(file);
        return problem ? rejectedItem(file, problem) : { id: newId(), file, status: "queued" };
      });
      // Añadir es pedir que se envíe: si la cola estaba en pausa, se vuelve a intentar.
      set((state) => ({ items: [...state.items, ...added], paused: false }));
    },
    prepare: (files) => {
      const rejected: QueueItem[] = [];
      const prepared: PreparedItem[] = [];
      for (const file of files) {
        const problem = precheck(file);
        if (problem) rejected.push(rejectedItem(file, problem));
        else prepared.push({ id: newId(), file, own: null });
      }
      set((state) => ({
        items: [...state.items, ...rejected],
        prepared: [...state.prepared, ...prepared],
      }));
    },
    setCommon: (common) => {
      set({ common });
    },
    setOwn: (id, own) => {
      set((state) => ({
        prepared: state.prepared.map((item) => (item.id === id ? { ...item, own } : item)),
      }));
    },
    unprepare: (id) => {
      set((state) => {
        const prepared = state.prepared.filter((item) => item.id !== id);
        // Sin imágenes, el formulario vuelve a sus valores por defecto, como al descartar.
        if (prepared.length === 0) return { prepared, common: emptyDraft(PREPARED_PARTS) };
        // Con una sola, el recuadro enseña los datos comunes: si ella tenía los suyos, pasan a
        // serlo, para que lo que se ve sea lo que se envía.
        const [only] = prepared;
        if (prepared.length === 1 && only?.own) {
          return { prepared: [{ ...only, own: null }], common: only.own };
        }
        return { prepared };
      });
    },
    discardPrepared: () => {
      set({ prepared: [], common: emptyDraft(PREPARED_PARTS) });
    },
    submitPrepared: () => {
      const { prepared, common } = get();
      if (prepared.length === 0) return;
      const queued = prepared.map((item): QueueItem => ({
        id: item.id,
        file: item.file,
        status: "queued",
        data: item.own ?? common,
      }));
      // Enviar es pedirlo: si la cola estaba en pausa, se vuelve a intentar.
      set((state) => ({
        items: [...state.items, ...queued],
        prepared: [],
        common: emptyDraft(PREPARED_PARTS),
        paused: false,
      }));
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
        set({ paused: false });
      }
    },
    clearFinished: () => {
      set((state) => ({
        items: state.items.filter(
          (item) => item.status === "queued" || item.status === "transcribing",
        ),
      }));
    },
    resume: () => {
      set({ paused: false });
    },
    run: async (api, onSettled) => {
      if (get().running || get().paused) return;
      const runGeneration = generation;
      const current = () => runGeneration === generation;
      set({ running: true });
      try {
        for (;;) {
          const next = get().items.find((item) => item.status === "queued");
          if (!next) break;
          // Solo con la sesión de la dueña: si caducó o entró otra persona, lo pendiente
          // sigue en cola hasta que ella vuelva a entrar (ADR-0012: el autor es quien envía).
          const { token, user } = useAuthStore.getState();
          if (!token || user?.id !== get().ownerId) break;

          patch(next.id, { status: "transcribing", startedAt: Date.now() });
          const controller = new AbortController();
          inFlight = controller;
          const body = new FormData();
          body.append("file", next.file, next.file.name);
          if (next.data) appendScoreData(body, next.data);
          try {
            const result = await api.request<TranscribeResponse>("/transcribe", {
              method: "POST",
              body,
              token,
              signal: controller.signal,
              timeoutMs: TRANSCRIBE_TIMEOUT_MS,
            });
            if (!current()) return;
            patch(next.id, { status: "done", result });
          } catch (error) {
            if (!current()) return;
            patch(next.id, { status: "error", error: transcribeErrorMessage(error) });
            // Sin sesión no tiene sentido seguir: el resto espera a que se vuelva a entrar.
            if (error instanceof ApiError && error.kind === "unauthorized") break;
            // Sin servidor, el resto fallaría en cadena: espera a que la persona reanude.
            if (serverUnreachable(error)) {
              set({ paused: true });
              break;
            }
          } finally {
            if (inFlight === controller) inFlight = null;
            // Tras un timeout, un fallo de red o un 5xx la sesión puede existir igualmente.
            onSettled?.();
          }
        }
      } finally {
        if (current()) set({ running: false });
      }
    },
  };
});

/** Hay trabajo que se perdería al cerrar la pestaña o salir: imágenes en cola o en curso. */
export function hasPendingWork(items: QueueItem[]): boolean {
  return items.some((item) => item.status === "queued" || item.status === "transcribing");
}

export const LEAVE_WARNING =
  "Hay imágenes en cola o transcribiéndose. Si sales, la cola se pierde, aunque la imagen en curso puede llegar a crear su sesión. ¿Salir igualmente?";

registerPendingWork(() => (hasPendingWork(useQueueStore.getState().items) ? LEAVE_WARNING : null));

// La cola es de quien la llenó. Si entra otra persona en la pestaña, o la dueña sale, se
// vacía y se cancela lo que esté en vuelo; si la sesión caduca, se conserva para reanudarla
// (también si estaba en pausa: haber podido entrar indica que el servidor responde).
useAuthStore.subscribe((auth, previous) => {
  const queue = useQueueStore.getState();
  if (auth.user) {
    queue.claim(auth.user.id);
    if (!previous.user) queue.resume();
  } else if (auth.endReason === "signed-out" && queue.ownerId !== null) {
    queue.reset();
  }
});
