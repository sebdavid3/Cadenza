import { create } from "zustand";
import type { ApiClient } from "../../api/client";
import { UPLOAD_TIMEOUT_MS } from "../../api/config";
import { ApiError } from "../../api/errors";
import { useAuthStore } from "../../auth/store";
import { registerPendingWork } from "../../pendingWork";
import type { SessionViewRead, TranscribeResponse, TranscriptionJobRead } from "../../types";
import { appendScoreData, emptyDraft, type ScoreDataDraft } from "./scoreData";

/** Límite de la API: `max_upload_size_bytes` (20 MB). */
export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
const ACCEPTED_TYPES = new Set(["image/png", "image/jpeg"]);
const ACCEPTED_EXTENSIONS = /\.(png|jpe?g)$/i;

/**
 * Cada cuánto se pregunta en qué están las transcripciones en curso (#375, ADR-0064). Es un objeto
 * para que las pruebas puedan acortarlo.
 */
export const JOB_POLLING = { intervalMs: 1000 };

export type ItemStatus = "queued" | "transcribing" | "done" | "error";

export interface QueueItem {
  id: string;
  /** La imagen elegida; falta en las que se recuperan del servidor al volver a la vista. */
  file?: File;
  /** El nombre del archivo y, si se conoce, su tamaño. */
  name: string;
  size?: number;
  status: ItemStatus;
  /** La transcripción en el servidor, una vez subida la imagen, con su último estado (#375). */
  job?: TranscriptionJobRead;
  /** Subiéndose: aún no tiene trabajo, pero ya no se puede quitar. */
  uploading?: boolean;
  /** Cuándo empezó a transcribirse (ms): el contador no se reinicia al volver a la vista. */
  startedAt?: number;
  result?: TranscribeResponse;
  error?: string;
  /** Rechazado antes de enviarlo: no se puede reintentar tal cual. */
  rejected?: boolean;
  /** Se interrumpió: el servidor se reinició antes de terminarla y no creó su sesión. */
  interrupted?: boolean;
  /** Los datos de la partitura que se envían con la imagen (#240); sin ellos, ninguno. */
  data?: ScoreDataDraft;
  /** El título que se le dio, en las recuperadas del servidor, que no traen sus datos. */
  title?: string | null;
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

/** Por qué no se suben ahora las imágenes que esperan (#375). */
export type UploadHold = "own-limit" | "queue-full";

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

/** Mensajes al subir una imagen a la cola del servidor (`POST /transcription-jobs`, #375). */
export function uploadErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.kind === "timeout") {
    return "La subida tardó demasiado. Comprueba la conexión y vuelve a intentarlo.";
  }
  return transcribeErrorMessage(error);
}

/** Por qué falló una transcripción en el servidor, con las palabras de la web. */
export function jobFailureMessage(failure: TranscriptionJobRead["failure"]): string {
  return failure === "unreadable"
    ? "No se reconoció ninguna partitura en la imagen."
    : "Algo falló en el servidor al transcribirla. Vuelve a intentarlo.";
}

/** La transcripción ya no está en el servidor y no creó su sesión: la API se reinició. */
export const INTERRUPTED_MESSAGE =
  "Se interrumpió: ya no está en el servidor y no llegó a crear su sesión (el servidor pudo reiniciarse). Vuelve a subirla.";

/** Si la transcripción ya terminó en el servidor, bien o mal. */
function finished(job: TranscriptionJobRead): boolean {
  return job.stage === "done" || job.stage === "failed";
}

/** Cuándo empezó a transcribirse, en la hora del navegador; ahora, si no se sabe. */
function startedAtOf(job: TranscriptionJobRead): number {
  const started = job.started_at ? Date.parse(job.started_at) : Number.NaN;
  return Number.isFinite(started) ? Math.min(started, Date.now()) : Date.now();
}

/** Lo que cambia en una imagen de la cola con el último estado de su transcripción. */
function fromJob(item: QueueItem, job: TranscriptionJobRead): Partial<QueueItem> {
  switch (job.stage) {
    case "queued":
      return { job, status: "queued", uploading: false };
    case "detecting":
    case "reading":
    case "reviewing":
      return {
        job,
        status: "transcribing",
        uploading: false,
        startedAt: item.startedAt ?? startedAtOf(job),
      };
    case "done":
      return { job, status: "done", uploading: false, result: job.result ?? undefined };
    case "failed":
      return { job, status: "error", uploading: false, error: jobFailureMessage(job.failure) };
  }
}

// --- Las transcripciones subidas que aún no se vieron terminar (#375) -------------------------
// Se apuntan en `localStorage` (el identificador y el nombre, nunca la imagen) para decir, tras
// recargar la página, cuáles se interrumpieron porque el servidor se reinició.

const REMEMBERED_PREFIX = "cadenza.transcripciones.";

interface Remembered {
  id: string;
  name: string;
}

function rememberedKey(ownerId: string) {
  return `${REMEMBERED_PREFIX}${ownerId}`;
}

export function readRemembered(ownerId: string): Remembered[] {
  try {
    const raw = window.localStorage.getItem(rememberedKey(ownerId));
    const value = raw ? (JSON.parse(raw) as unknown) : [];
    if (!Array.isArray(value)) return [];
    return value.filter(
      (entry): entry is Remembered =>
        typeof entry === "object" &&
        entry !== null &&
        typeof (entry as Remembered).id === "string" &&
        typeof (entry as Remembered).name === "string",
    );
  } catch {
    return [];
  }
}

function writeRemembered(ownerId: string, entries: Remembered[]) {
  try {
    if (entries.length === 0) window.localStorage.removeItem(rememberedKey(ownerId));
    else window.localStorage.setItem(rememberedKey(ownerId), JSON.stringify(entries));
  } catch {
    // Sin almacenamiento: tras recargar no se sabrá cuáles se interrumpieron.
  }
}

export function remember(ownerId: string, entry: Remembered) {
  writeRemembered(ownerId, [...readRemembered(ownerId).filter((e) => e.id !== entry.id), entry]);
}

export function forget(ownerId: string, jobIds: Iterable<string>) {
  const gone = new Set(jobIds);
  const entries = readRemembered(ownerId);
  const kept = entries.filter((entry) => !gone.has(entry.id));
  if (kept.length !== entries.length) writeRemembered(ownerId, kept);
}

/**
 * Una transcripción que ya no está en el servidor: lista si creó su sesión (que se llama como el
 * trabajo, ADR-0064); si no, se interrumpió. Null si no se pudo saber (sin conexión, otro error).
 */
export async function settleMissing(
  api: ApiClient,
  token: string,
  jobId: string,
  signal?: AbortSignal,
): Promise<{ result: TranscribeResponse } | { interrupted: true } | null> {
  try {
    const session = await api.request<SessionViewRead>(`/sessions/${encodeURIComponent(jobId)}`, {
      query: { fields: "view" },
      token,
      signal,
    });
    return {
      result: {
        session_id: session.session_id,
        document_id: session.document_id,
        omr_engine: session.omr_engine,
        findings_count: session.findings.length,
        condition: session.condition,
        test_score_id: session.test_score_id ?? null,
      },
    };
  } catch (error) {
    if (error instanceof ApiError && error.kind === "not-found") return { interrupted: true };
    return null;
  }
}

let nextId = 0;
const newId = () => `img-${String(++nextId)}`;

interface QueueState {
  items: QueueItem[];
  running: boolean;
  /** Pausada tras perder el servidor: lo pendiente espera hasta que la persona la reanude. */
  paused: boolean;
  /** Las imágenes que esperan no se suben ahora: el tope de la persona o la cola llena (#375). */
  hold: UploadHold | null;
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
  /**
   * Quita una imagen: si espera en el servidor, se retira de su cola; si ya se transcribe, no se
   * puede (se queda). Una terminada se olvida también en el servidor.
   */
  remove: (id: string, api: ApiClient) => Promise<void>;
  retry: (id: string, api: ApiClient) => void;
  clearFinished: (api: ApiClient) => void;
  resume: () => void;
  /**
   * Al volver a la vista: las transcripciones de la persona que siguen en el servidor, y las que
   * se subieron y desaparecieron sin crear su sesión, que se interrumpieron (#375).
   */
  restore: (api: ApiClient) => Promise<void>;
  /**
   * Sube las imágenes que esperan y sigue sus transcripciones hasta que terminan; termina cuando
   * no queda nada pendiente o cuando la sesión de la dueña ya no está. `onSettled` se llama cada
   * vez que una transcripción termina, bien o mal, y tras una subida que pudo crearla.
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
  // La espera entre dos consultas: se corta al vaciar la cola o al añadir imágenes.
  let wake: (() => void) | null = null;
  const nap = (ms: number) =>
    new Promise<void>((resolve) => {
      const timer = setTimeout(done, ms);
      function done() {
        clearTimeout(timer);
        if (wake === done) wake = null;
        resolve();
      }
      wake = done;
    });
  // Una sola recuperación a la vez: la vista puede pedirla dos veces al montarse.
  let restoring: Promise<void> | null = null;
  const cancel = () => {
    generation += 1;
    inFlight?.abort();
    inFlight = null;
    wake?.();
  };

  const rejectedItem = (file: File, problem: string): QueueItem => ({
    id: newId(),
    file,
    name: file.name,
    size: file.size,
    status: "error",
    error: problem,
    rejected: true,
  });

  const tokenOfOwner = () => {
    const { token, user } = useAuthStore.getState();
    return token && user?.id === get().ownerId ? token : null;
  };

  const restoredItem = (job: TranscriptionJobRead): QueueItem => {
    const base: QueueItem = {
      id: newId(),
      name: job.source_filename ?? "Imagen sin nombre",
      title: job.title ?? null,
      status: "queued",
    };
    return { ...base, ...fromJob(base, job) };
  };

  const restoreJobs = async (api: ApiClient) => {
    const token = tokenOfOwner();
    const ownerId = get().ownerId;
    if (!token || !ownerId) return;
    const restoreGeneration = generation;
    const current = () => restoreGeneration === generation;
    const controller = new AbortController();
    let jobs: TranscriptionJobRead[];
    try {
      jobs = await api.request<TranscriptionJobRead[]>("/transcription-jobs", {
        token,
        signal: controller.signal,
      });
    } catch {
      return;
    }
    if (!current()) return;
    const known = () => new Set(get().items.flatMap((item) => (item.job ? [item.job.id] : [])));
    const onServer = new Set(jobs.map((job) => job.id));
    // Las listas están en el diario; las terminadas que se vieron ya no se apuntan.
    forget(
      ownerId,
      jobs.filter(finished).map((job) => job.id),
    );
    const restored = jobs
      .filter((job) => job.stage !== "done" && !known().has(job.id))
      .map(restoredItem);
    // Las apuntadas que el servidor ya no tiene: o crearon su sesión, o se interrumpieron.
    const missing = readRemembered(ownerId).filter(
      (entry) => !onServer.has(entry.id) && !known().has(entry.id),
    );
    const interrupted: QueueItem[] = [];
    for (const entry of missing) {
      const outcome = await settleMissing(api, token, entry.id, controller.signal);
      if (!current()) return;
      if (outcome === null) continue;
      forget(ownerId, [entry.id]);
      if ("interrupted" in outcome) {
        interrupted.push({
          id: newId(),
          name: entry.name,
          status: "error",
          error: INTERRUPTED_MESSAGE,
          interrupted: true,
        });
      }
    }
    const fresh = [...restored, ...interrupted].filter(
      (item) => !item.job || !known().has(item.job.id),
    );
    if (fresh.length > 0) set((state) => ({ items: [...fresh, ...state.items] }));
  };

  return {
    items: [],
    running: false,
    paused: false,
    hold: null,
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
        hold: null,
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
        hold: null,
        ownerId: null,
        prepared: [],
        common: emptyDraft(PREPARED_PARTS),
      });
    },
    add: (files) => {
      const added = [...files].map((file): QueueItem => {
        const problem = precheck(file);
        return problem
          ? rejectedItem(file, problem)
          : { id: newId(), file, name: file.name, size: file.size, status: "queued" };
      });
      // Añadir es pedir que se envíe: si la cola estaba en pausa, se vuelve a intentar.
      set((state) => ({ items: [...state.items, ...added], paused: false }));
      wake?.();
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
        name: item.file.name,
        size: item.file.size,
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
      wake?.();
    },
    remove: async (id, api) => {
      const item = get().items.find((candidate) => candidate.id === id);
      if (!item || item.status === "transcribing" || item.uploading) return;
      const drop = () => {
        set((state) => ({ items: state.items.filter((candidate) => candidate.id !== id) }));
      };
      const { job } = item;
      const token = tokenOfOwner();
      if (!job || !token) {
        drop();
        return;
      }
      const ownerId = get().ownerId;
      if (ownerId) forget(ownerId, [job.id]);
      if (item.status !== "queued") {
        // Terminada: se olvida aquí y, sin esperar, en el servidor.
        drop();
        void api
          .request(`/transcription-jobs/${encodeURIComponent(job.id)}`, {
            method: "DELETE",
            token,
          })
          .catch(() => undefined);
        return;
      }
      try {
        await api.request(`/transcription-jobs/${encodeURIComponent(job.id)}`, {
          method: "DELETE",
          token,
        });
        drop();
      } catch (error) {
        // Ya no está en el servidor: no hay nada que quitar allí.
        if (error instanceof ApiError && error.kind === "not-found") drop();
        // Empezó a transcribirse entretanto (409): se queda, y la consulta dirá en qué está.
        else if (ownerId) remember(ownerId, { id: job.id, name: item.name });
      }
    },
    retry: (id, api) => {
      const item = get().items.find((candidate) => candidate.id === id);
      if (item?.status !== "error" || item.rejected || !item.file) return;
      const old = item.job;
      const token = tokenOfOwner();
      if (old && token) {
        void api
          .request(`/transcription-jobs/${encodeURIComponent(old.id)}`, {
            method: "DELETE",
            token,
          })
          .catch(() => undefined);
      }
      patch(id, { status: "queued", error: undefined, job: undefined, startedAt: undefined });
      set({ paused: false });
      wake?.();
    },
    clearFinished: (api) => {
      const isFinished = (item: QueueItem) => item.status === "done" || item.status === "error";
      const gone = get().items.filter(isFinished);
      set((state) => ({ items: state.items.filter((item) => !isFinished(item)) }));
      const token = tokenOfOwner();
      if (!token) return;
      for (const item of gone) {
        if (!item.job) continue;
        void api
          .request(`/transcription-jobs/${encodeURIComponent(item.job.id)}`, {
            method: "DELETE",
            token,
          })
          .catch(() => undefined);
      }
    },
    resume: () => {
      set({ paused: false });
    },
    restore: (api) => {
      restoring ??= restoreJobs(api).finally(() => {
        restoring = null;
      });
      return restoring;
    },
    run: async (api, onSettled) => {
      if (get().running || get().paused) return;
      const runGeneration = generation;
      const current = () => runGeneration === generation;
      set({ running: true });
      // Tras un 429 (el tope de la persona) o un 503 (la cola llena), no se sube hasta entonces
      // o hasta que termine una de las suyas.
      let holdUntil = 0;
      const release = () => {
        holdUntil = 0;
        if (get().hold !== null) set({ hold: null });
      };
      try {
        for (;;) {
          // Solo con la sesión de la dueña: si caducó o entró otra persona, lo pendiente
          // sigue en cola hasta que ella vuelva a entrar (ADR-0012: el autor es quien envía).
          const ownerId = get().ownerId;
          if (!tokenOfOwner() || !ownerId) break;
          if (holdUntil !== 0 && Date.now() >= holdUntil) release();

          // 1. Subir las imágenes que esperan, en orden: cada una recibe su trabajo enseguida.
          let stop = false;
          while (holdUntil === 0) {
            const next = get().items.find(
              (item) => item.status === "queued" && !item.job && item.file,
            );
            if (!next?.file) break;
            // El token de cada subida: si la sesión caducó con otra en vuelo, esta espera.
            const token = tokenOfOwner();
            if (!token) {
              stop = true;
              break;
            }
            patch(next.id, { uploading: true });
            const controller = new AbortController();
            inFlight = controller;
            const body = new FormData();
            body.append("file", next.file, next.file.name);
            if (next.data) appendScoreData(body, next.data);
            try {
              const job = await api.request<TranscriptionJobRead>("/transcription-jobs", {
                method: "POST",
                body,
                token,
                signal: controller.signal,
                timeoutMs: UPLOAD_TIMEOUT_MS,
              });
              if (!current()) return;
              // Si al volver a la vista ya se recuperó del servidor con la subida en vuelo,
              // esa copia sobra: la sigue la imagen que se subió.
              set((state) => ({
                items: state.items.filter(
                  (candidate) => candidate.id === next.id || candidate.job?.id !== job.id,
                ),
              }));
              const item = get().items.find((candidate) => candidate.id === next.id);
              if (item) patch(next.id, fromJob(item, job));
              if (finished(job)) {
                // Ya terminó (un servidor sin cola): el listado puede tener su sesión.
                onSettled?.();
              } else {
                remember(ownerId, { id: job.id, name: next.name });
              }
            } catch (error) {
              if (!current()) return;
              patch(next.id, { uploading: false });
              if (error instanceof ApiError && (error.status === 429 || error.status === 503)) {
                // No es esta imagen: espera su turno para subirse.
                const ownLimit = error.status === 429;
                holdUntil = Date.now() + (error.retryAfterSeconds ?? (ownLimit ? 10 : 60)) * 1000;
                set({ hold: ownLimit ? "own-limit" : "queue-full" });
                break;
              }
              patch(next.id, { status: "error", error: uploadErrorMessage(error) });
              // Tras un timeout la imagen puede haber llegado: la consulta lo dirá.
              onSettled?.();
              // Sin sesión no tiene sentido seguir: el resto espera a que se vuelva a entrar.
              if (error instanceof ApiError && error.kind === "unauthorized") {
                stop = true;
                break;
              }
              // Sin servidor, el resto fallaría en cadena: espera a que la persona reanude.
              if (serverUnreachable(error)) {
                set({ paused: true });
                stop = true;
                break;
              }
            } finally {
              if (inFlight === controller) inFlight = null;
            }
          }
          if (stop) break;

          // 2. Seguir las que se transcriben en el servidor.
          const tracked = () =>
            get().items.filter(
              (item): item is QueueItem & { job: TranscriptionJobRead } =>
                item.job !== undefined && !finished(item.job),
            );
          const waiting = get().items.some(
            (item) => item.status === "queued" && !item.job && item.file,
          );
          if (tracked().length === 0 && !waiting) break;
          await nap(
            tracked().length === 0 ? Math.max(0, holdUntil - Date.now()) : JOB_POLLING.intervalMs,
          );
          if (!current()) return;
          if (tracked().length === 0) continue;
          const pollToken = tokenOfOwner();
          if (!pollToken) break;
          const controller = new AbortController();
          inFlight = controller;
          let jobs: TranscriptionJobRead[];
          try {
            jobs = await api.request<TranscriptionJobRead[]>("/transcription-jobs", {
              token: pollToken,
              signal: controller.signal,
            });
          } catch (error) {
            if (!current()) return;
            if (error instanceof ApiError && error.kind === "unauthorized") break;
            if (serverUnreachable(error)) {
              set({ paused: true });
              break;
            }
            continue;
          } finally {
            if (inFlight === controller) inFlight = null;
          }
          if (!current()) return;
          const byId = new Map(jobs.map((job) => [job.id, job]));
          let settled = 0;
          for (const item of tracked()) {
            const job = byId.get(item.job.id);
            if (job) {
              if (finished(job)) {
                settled += 1;
                forget(ownerId, [job.id]);
              }
              patch(item.id, fromJob(item, job));
              continue;
            }
            // Ya no está: la API se reinició (o se quitó desde otra pestaña).
            const outcome = await settleMissing(api, pollToken, item.job.id, controller.signal);
            if (!current()) return;
            if (outcome === null) continue;
            settled += 1;
            forget(ownerId, [item.job.id]);
            const gone = { ...item.job, stage: "failed" as const };
            patch(
              item.id,
              "result" in outcome
                ? { job: { ...gone, stage: "done" }, status: "done", result: outcome.result }
                : { job: gone, status: "error", error: INTERRUPTED_MESSAGE, interrupted: true },
            );
          }
          if (settled > 0) {
            release();
            onSettled?.();
          }
        }
      } finally {
        if (current()) set({ running: false });
      }
    },
  };
});

/** Hay imágenes que se perderían al cerrar la pestaña o salir: las que aún no se han subido. */
export function hasPendingWork(items: QueueItem[]): boolean {
  return items.some((item) => item.status === "queued" && !item.job);
}

export const LEAVE_WARNING =
  "Hay imágenes que aún no se han subido. Si sales, esas se pierden; las que ya están en el servidor siguen transcribiéndose. ¿Salir igualmente?";

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
