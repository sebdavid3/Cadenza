import { create } from "zustand";
import type { ApiClient } from "../../api/client";
import { PREVIEW_TIMEOUT_MS, UPLOAD_TIMEOUT_MS } from "../../api/config";
import { ApiError } from "../../api/errors";
import { useAuthStore } from "../../auth/store";
import { registerPendingWork } from "../../pendingWork";
import type { PreviewResponse, TranscribeResponse, TranscriptionJobRead } from "../../types";
import {
  forget,
  INTERRUPTED_MESSAGE,
  JOB_POLLING,
  jobFailureMessage,
  precheck,
  PREPARED_PARTS,
  remember,
  settleMissing,
  transcribeErrorMessage,
  uploadErrorMessage,
} from "../transcription/queue";
import {
  appendScoreData,
  emptyDraft,
  nonBlank,
  type ScoreDataDraft,
} from "../transcription/scoreData";

/**
 * El recuadro de la portada (#277, ADR-0053): una imagen, sus datos y su transcripción. Vive en
 * memoria, fuera de la vista, para que la imagen elegida sobreviva a ir a entrar y volver; nunca
 * se guarda en el navegador. Solo se apunta en `sessionStorage` el nombre del archivo mientras se
 * entra, para avisar de que se perdió si la página se recarga entretanto.
 *
 * Sin cuenta (#278, ADR-0054), si el despliegue lo abre, la imagen se transcribe con
 * `POST /previews`: el resultado se ve igual y, para editarlo, se entra y se reclama con su token,
 * que se apunta en `sessionStorage` (no la imagen) para poder reclamarlo también tras una recarga.
 */

/** Los fallos al preguntar por la transcripción que no cortan el seguimiento (#375). */
const PASSING_FAILURES = new Set<ApiError["kind"]>(["network", "server", "timeout"]);

/** Fallos pasajeros seguidos tras los que se deja de preguntar y se dice. */
export const MAX_POLL_FAILURES = 10;

/** Ancla de la sección en la portada: adonde se vuelve tras entrar. */
export const LANDING_UPLOAD_HASH = "#transcribir";
export const LANDING_UPLOAD_PATH = `/${LANDING_UPLOAD_HASH}`;

/** Clave de `sessionStorage` con el nombre de la imagen que espera a que se entre. */
export const PENDING_UPLOAD_KEY = "cadenza.portada.pendiente";

/** Clave de `sessionStorage` con la transcripción sin cuenta que espera a reclamarse (#278). */
export const PENDING_CLAIM_KEY = "cadenza.portada.reclamar";

/** Una transcripción sin cuenta que se puede reclamar: su id, su token y cuándo caduca (ms). */
export interface PendingClaim {
  id: string;
  token: string;
  expiresAt: number;
  name: string;
}

export type LandingStage =
  /** Sin imagen. */
  | { kind: "empty" }
  /** Con la imagen elegida y sus datos, antes de transcribir. */
  | { kind: "chosen" }
  /** Subiéndose o transcribiéndose; `job`, en qué está en el servidor (#375). */
  | { kind: "transcribing"; startedAt: number; job?: TranscriptionJobRead }
  /**
   * Transcrita: la sesión es de `ownerId`; `name`, el nombre que tendrá (el dado o el del
   * archivo), mientras llega el de la sesión.
   */
  | { kind: "done"; result: TranscribeResponse; ownerId: string; name: string }
  /** `mayExist`: la transcripción puede seguir en el servidor y crear su sesión igualmente. */
  | { kind: "failed"; message: string; mayExist: boolean }
  /**
   * Transcrita sin cuenta (#278): lo que leyó HOMR, para verlo, y cómo reclamarlo. Sin `preview`
   * tras una recarga: solo queda el token.
   */
  | { kind: "previewed"; preview: PreviewResponse | null; claim: PendingClaim }
  /** Reclamándola tras entrar. */
  | { kind: "claiming"; claim: PendingClaim }
  /** Reclamada: ya es la sesión `sessionId`, que la portada abre. */
  | { kind: "claimed"; sessionId: string };

interface LandingUploadState {
  file: File | null;
  /** Quien eligió la imagen con la sesión iniciada; null si la eligió sin cuenta. */
  chooserId: string | null;
  draft: ScoreDataDraft;
  stage: LandingStage;
  /** Se pidió entrar para transcribir: al volver con la sesión iniciada, se transcribe sola. */
  resumeAfterAuth: boolean;
  /** La sesión caducó al enviar: la imagen sigue y se pide volver a entrar. */
  expired: boolean;
  /** Por qué no se aceptó la última imagen elegida (antes de enviarla). */
  rejection: string | null;
  /** La página se recargó mientras se entraba: el nombre de la imagen que hay que volver a elegir. */
  lostFile: string | null;
  /** El servidor no transcribe sin cuenta (404): se vuelve a pedir que se entre (#278). */
  previewsOff: boolean;
  /** Se pidió entrar para editar la transcripción sin cuenta: al volver, se reclama sola. */
  claimAfterAuth: boolean;
  choose: (files: File[]) => void;
  setDraft: (draft: ScoreDataDraft) => void;
  /** Olvida la imagen y el resultado: el recuadro vuelve a empezar. */
  discard: () => void;
  /** Se va a entrar o a crear la cuenta para transcribir la imagen elegida. */
  requestAuth: () => void;
  /** Comprueba, al montar la portada, si una imagen que esperaba a entrar se perdió al recargar. */
  detectLost: () => void;
  dismissLost: () => void;
  transcribe: (api: ApiClient) => Promise<void>;
  /** Transcribe sin cuenta con `POST /previews` (#278, ADR-0054). */
  preview: (api: ApiClient) => Promise<void>;
  /** Se va a entrar o a crear la cuenta para editar la transcripción sin cuenta. */
  requestClaim: () => void;
  /** Con la sesión iniciada, la convierte en una sesión suya (`POST /previews/{id}/claim`). */
  claim: (api: ApiClient) => Promise<void>;
  /** Al montar la portada, recupera una transcripción sin cuenta que espera tras una recarga. */
  detectPendingClaim: () => void;
  reset: () => void;
}

function storage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function markPending(name: string | null) {
  try {
    const store = storage();
    if (name === null) store?.removeItem(PENDING_UPLOAD_KEY);
    else store?.setItem(PENDING_UPLOAD_KEY, name);
  } catch {
    // Sin almacenamiento: tras una recarga no habrá aviso, pero la imagen tampoco estaba.
  }
}

/** La hora a la que caduca una transcripción sin cuenta, en la hora local («14:05»). */
export function expiryTime(expiresAt: number): string {
  return new Date(expiresAt).toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" });
}

function writeClaim(claim: PendingClaim | null) {
  try {
    const store = storage();
    if (claim === null) store?.removeItem(PENDING_CLAIM_KEY);
    else store?.setItem(PENDING_CLAIM_KEY, JSON.stringify(claim));
  } catch {
    // Sin almacenamiento: se puede reclamar mientras no se recargue la página.
  }
}

/** La transcripción sin cuenta apuntada, si sigue vigente. */
function readClaim(now: number = Date.now()): PendingClaim | null {
  try {
    const raw = storage()?.getItem(PENDING_CLAIM_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<PendingClaim> | null;
    if (
      !value ||
      typeof value.id !== "string" ||
      typeof value.token !== "string" ||
      typeof value.expiresAt !== "number" ||
      !Number.isFinite(value.expiresAt) ||
      typeof value.name !== "string" ||
      value.expiresAt <= now
    ) {
      storage()?.removeItem(PENDING_CLAIM_KEY);
      return null;
    }
    return { id: value.id, token: value.token, expiresAt: value.expiresAt, name: value.name };
  } catch {
    return null;
  }
}

function minutes(seconds: number) {
  const value = Math.max(1, Math.ceil(seconds / 60));
  return value === 1 ? "un minuto" : `${String(value)} minutos`;
}

/** Mensajes de la transcripción sin cuenta: los de la cola, más el límite por conexión. */
export function previewErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.kind === "rate-limited") {
    return error.retryAfterSeconds !== null
      ? `Has transcrito varias imágenes sin cuenta desde tu conexión. Vuelve a probar en ${minutes(error.retryAfterSeconds)} o entra con tu cuenta.`
      : "Has transcrito varias imágenes sin cuenta desde tu conexión. Vuelve a probar más tarde o entra con tu cuenta.";
  }
  if (error instanceof ApiError && error.kind === "timeout") {
    // La transcripción sin cuenta sigue siendo síncrona y está apagada (#278).
    return "La transcripción tardó más de 30 s. Vuelve a intentarlo en un momento.";
  }
  return transcribeErrorMessage(error);
}

function readPending(): string | null {
  try {
    return storage()?.getItem(PENDING_UPLOAD_KEY) ?? null;
  } catch {
    return null;
  }
}

const initial = () => ({
  file: null,
  chooserId: null,
  draft: emptyDraft(PREPARED_PARTS),
  stage: { kind: "empty" } as LandingStage,
  resumeAfterAuth: false,
  expired: false,
  rejection: null,
  lostFile: null,
  claimAfterAuth: false,
});

export const useLandingUpload = create<LandingUploadState>()((set, get) => {
  // Cada vaciado abre una generación nueva: la respuesta de una petición anterior no toca nada.
  let generation = 0;
  let inFlight: AbortController | null = null;
  const cancel = () => {
    generation += 1;
    inFlight?.abort();
    inFlight = null;
  };

  const finishClaim = (sessionId: string) => {
    writeClaim(null);
    set({
      file: null,
      chooserId: null,
      draft: emptyDraft(PREPARED_PARTS),
      stage: { kind: "claimed", sessionId },
      claimAfterAuth: false,
    });
  };

  return {
    ...initial(),
    // Lo que el servidor no ofrece (un 404 de `/previews`) sigue así hasta salir de la sesión:
    // descartar la imagen no lo olvida.
    previewsOff: false,
    choose: (files) => {
      const busy = get().stage.kind;
      if (busy === "transcribing" || busy === "claiming") return;
      if (files.length > 1) {
        set({
          rejection:
            "Aquí se transcribe una imagen cada vez. Para varias, entra y usa la transcripción por lotes.",
        });
        return;
      }
      const [file] = files;
      if (!file) return;
      const problem = precheck(file);
      if (problem) {
        set({ rejection: problem });
        return;
      }
      // Una imagen nueva empieza de cero, con los datos que ya se hubieran escrito.
      cancel();
      markPending(null);
      set({
        file,
        chooserId: useAuthStore.getState().user?.id ?? null,
        stage: { kind: "chosen" },
        rejection: null,
        lostFile: null,
        resumeAfterAuth: false,
        expired: false,
      });
    },
    setDraft: (draft) => {
      set({ draft });
    },
    discard: () => {
      cancel();
      markPending(null);
      writeClaim(null);
      set(initial());
    },
    requestAuth: () => {
      const { file } = get();
      if (!file) return;
      markPending(file.name);
      set({ resumeAfterAuth: true });
    },
    detectLost: () => {
      const pending = readPending();
      if (pending === null) return;
      // Con la imagen en memoria no se perdió nada: se volvió de entrar sin recargar.
      if (get().file) return;
      markPending(null);
      set({ lostFile: pending, resumeAfterAuth: false });
    },
    dismissLost: () => {
      set({ lostFile: null });
    },
    transcribe: async (api) => {
      const { file, draft, stage } = get();
      if (!file || stage.kind === "transcribing") return;
      const { token, user } = useAuthStore.getState();
      if (!token || !user) {
        set({ resumeAfterAuth: true });
        return;
      }
      const runGeneration = generation;
      const current = () => runGeneration === generation;
      const controller = new AbortController();
      inFlight = controller;
      markPending(null);
      const startedAt = Date.now();
      set({
        stage: { kind: "transcribing", startedAt },
        resumeAfterAuth: false,
        expired: false,
      });
      const name = nonBlank(draft.title) ?? file.name;
      const body = new FormData();
      body.append("file", file, file.name);
      appendScoreData(body, draft);
      // La imagen sube a la cola del servidor y se pregunta en qué está hasta que acaba, sin
      // plazo (#375, ADR-0064).
      let job: TranscriptionJobRead;
      try {
        job = await api.request<TranscriptionJobRead>("/transcription-jobs", {
          method: "POST",
          body,
          token,
          signal: controller.signal,
          timeoutMs: UPLOAD_TIMEOUT_MS,
        });
      } catch (error) {
        if (inFlight === controller) inFlight = null;
        if (!current()) return;
        if (error instanceof ApiError && error.kind === "unauthorized") {
          // La sesión caducó: la imagen se conserva y se transcribe al volver a entrar.
          set({ stage: { kind: "chosen" }, expired: true });
          return;
        }
        const timedOut = error instanceof ApiError && error.kind === "timeout";
        const ownLimit = error instanceof ApiError && error.status === 429;
        set({
          stage: {
            kind: "failed",
            // Aquí no hay listado a la vista: se dice dónde buscar la sesión.
            message: timedOut
              ? "La subida tardó demasiado. Puede que la imagen llegara: búscala en tus transcripciones antes de volver a intentarlo."
              : ownLimit
                ? "Ya tienes el máximo de transcripciones en curso. Vuelve a intentarlo cuando termine alguna."
                : uploadErrorMessage(error),
            mayExist: timedOut,
          },
        });
        return;
      }
      if (!current()) return;
      remember(user.id, { id: job.id, name });
      // Se pregunta hasta que acaba. Un fallo pasajero (sin conexión, un 5xx, un plazo) no corta
      // el seguimiento: se vuelve a preguntar, y solo tras muchos seguidos se dice.
      let failures = 0;
      let result: TranscribeResponse | null;
      try {
        while (job.stage !== "done" && job.stage !== "failed") {
          set({ stage: { kind: "transcribing", startedAt, job } });
          await new Promise((resolve) => setTimeout(resolve, JOB_POLLING.intervalMs));
          if (!current()) return;
          // Solo con la sesión de quien la subió (ADR-0012).
          const { token: pollToken, user: pollUser } = useAuthStore.getState();
          if (!pollToken || pollUser?.id !== user.id) throw new ApiError("unauthorized", 401);
          try {
            job = await api.request<TranscriptionJobRead>(
              `/transcription-jobs/${encodeURIComponent(job.id)}`,
              { token: pollToken, signal: controller.signal },
            );
            failures = 0;
          } catch (error) {
            if (!(error instanceof ApiError) || !PASSING_FAILURES.has(error.kind)) throw error;
            failures += 1;
            if (failures >= MAX_POLL_FAILURES) throw error;
          }
          if (!current()) return;
        }
        result = job.result ?? null;
      } catch (error) {
        if (!current()) return;
        if (error instanceof ApiError && error.kind === "not-found") {
          // Ya no está en el servidor: puede que creara su sesión justo antes de desaparecer.
          const token = useAuthStore.getState().token;
          const outcome = token ? await settleMissing(api, token, job.id) : null;
          if (!current()) return;
          if (outcome && "result" in outcome) {
            forget(user.id, [job.id]);
            result = outcome.result;
          } else {
            if (outcome) forget(user.id, [job.id]);
            // La imagen sigue aquí para volver a subirla.
            set({ stage: { kind: "failed", message: INTERRUPTED_MESSAGE, mayExist: true } });
            return;
          }
        } else {
          // Sin sesión o sin conexión: la transcripción sigue en el servidor.
          set({
            stage: {
              kind: "failed",
              message:
                error instanceof ApiError && error.kind === "unauthorized"
                  ? "Tu sesión caducó, pero la transcripción sigue en el servidor: al volver a entrar la verás en tus transcripciones."
                  : "Se perdió la conexión con el servidor, pero la transcripción sigue allí: la verás en tus transcripciones.",
              mayExist: true,
            },
          });
          return;
        }
      } finally {
        if (inFlight === controller) inFlight = null;
      }
      forget(user.id, [job.id]);
      if (!result) {
        set({
          stage: { kind: "failed", message: jobFailureMessage(job.failure), mayExist: false },
        });
        return;
      }
      // La imagen ya está en el servidor: no se guarda más tiempo del necesario.
      set({
        file: null,
        chooserId: null,
        draft: emptyDraft(PREPARED_PARTS),
        stage: { kind: "done", result, ownerId: user.id, name },
      });
    },
    preview: async (api) => {
      const { file, draft, stage } = get();
      if (!file || stage.kind === "transcribing" || get().previewsOff) return;
      const runGeneration = generation;
      const controller = new AbortController();
      inFlight = controller;
      markPending(null);
      set({
        stage: { kind: "transcribing", startedAt: Date.now() },
        resumeAfterAuth: false,
        expired: false,
      });
      const body = new FormData();
      body.append("file", file, file.name);
      appendScoreData(body, draft);
      try {
        const preview = await api.request<PreviewResponse>("/previews", {
          method: "POST",
          body,
          auth: false,
          signal: controller.signal,
          timeoutMs: PREVIEW_TIMEOUT_MS,
        });
        if (runGeneration !== generation) return;
        const claim: PendingClaim = {
          id: preview.preview_id,
          token: preview.claim_token,
          expiresAt: Date.parse(preview.expires_at),
          name: nonBlank(draft.title) ?? file.name,
        };
        writeClaim(claim);
        // La imagen se queda en memoria: si la transcripción caduca antes de reclamarla, se puede
        // transcribir otra vez con la cuenta sin volver a elegirla.
        set({ stage: { kind: "previewed", preview, claim } });
      } catch (error) {
        if (runGeneration !== generation) return;
        if (error instanceof ApiError && error.kind === "not-found") {
          // El servidor no transcribe sin cuenta: se pide entrar, como sin #278.
          set({ stage: { kind: "chosen" }, previewsOff: true });
          return;
        }
        set({
          stage: { kind: "failed", message: previewErrorMessage(error), mayExist: false },
        });
      } finally {
        if (inFlight === controller) inFlight = null;
      }
    },
    requestClaim: () => {
      set({ claimAfterAuth: true });
    },
    claim: async (api) => {
      const { stage } = get();
      if (stage.kind !== "previewed") return;
      const { token } = useAuthStore.getState();
      if (!token) {
        set({ claimAfterAuth: true });
        return;
      }
      const { claim, preview } = stage;
      const runGeneration = generation;
      set({
        stage: { kind: "claiming", claim },
        claimAfterAuth: false,
        expired: false,
        rejection: null,
      });
      try {
        const result = await api.request<TranscribeResponse>(
          `/previews/${encodeURIComponent(claim.id)}/claim`,
          { method: "POST", json: { claim_token: claim.token }, token },
        );
        if (runGeneration !== generation) return;
        finishClaim(result.session_id);
      } catch (error) {
        if (runGeneration !== generation) return;
        if (error instanceof ApiError && error.kind === "unauthorized") {
          set({ stage: { kind: "previewed", preview, claim }, expired: true });
          return;
        }
        if (error instanceof ApiError && error.kind === "not-found") {
          // Caducó, ya se reclamó o el servidor dejó de ofrecerlo: con la imagen aún en memoria,
          // se puede transcribir con la cuenta; sin ella, hay que volver a elegirla.
          writeClaim(null);
          if (get().file) {
            set({
              stage: {
                kind: "failed",
                message:
                  "La transcripción sin cuenta ya no está: caduca a la hora, solo se puede editar una vez y el servidor puede haber dejado de ofrecerla. Vuelve a transcribir la imagen con tu cuenta.",
                mayExist: false,
              },
            });
          } else {
            set({
              ...initial(),
              rejection: `La transcripción sin cuenta de «${claim.name}» ya no está: caduca a la hora y solo se puede editar una vez. Vuelve a elegir la imagen para transcribirla.`,
            });
          }
          return;
        }
        set({
          stage: { kind: "previewed", preview, claim },
          rejection: `No se pudo abrir la transcripción para editarla. ${errorMessageOf(error)}`,
        });
      }
    },
    detectPendingClaim: () => {
      if (get().stage.kind !== "empty") return;
      const claim = readClaim();
      if (claim) set({ stage: { kind: "previewed", preview: null, claim } });
    },
    reset: () => {
      cancel();
      markPending(null);
      writeClaim(null);
      set({ ...initial(), previewsOff: false });
    },
  };
});

function errorMessageOf(error: unknown): string {
  return error instanceof ApiError ? error.message : "Inténtalo de nuevo.";
}

export const LANDING_LEAVE_WARNING =
  "La imagen de la portada se está subiendo o transcribiendo. Si ya llegó al servidor, la transcripción sigue y la verás en tus transcripciones. ¿Salir?";

registerPendingWork(() => {
  const { kind } = useLandingUpload.getState().stage;
  return kind === "transcribing" || kind === "claiming" ? LANDING_LEAVE_WARNING : null;
});

// Lo elegido es de quien está ante la pestaña. Al salir de la sesión se olvida. Si entra otra
// persona, el resultado de la anterior (una sesión suya) deja de enseñarse, y la imagen que
// eligió con su sesión (que caducó) no se transcribe a nombre de la nueva. La elegida sin cuenta
// es de quien entra para transcribirla.
useAuthStore.subscribe((auth, previous) => {
  const upload = useLandingUpload.getState();
  if (!auth.user && previous.user && auth.endReason === "signed-out") {
    upload.reset();
    return;
  }
  if (!auth.user) return;
  const { stage, file, chooserId } = upload;
  const foreignResult = stage.kind === "done" && stage.ownerId !== auth.user.id;
  const foreignImage = file !== null && chooserId !== null && chooserId !== auth.user.id;
  if (foreignResult || foreignImage) upload.reset();
});
