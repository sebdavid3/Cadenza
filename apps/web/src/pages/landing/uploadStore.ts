import { create } from "zustand";
import type { ApiClient } from "../../api/client";
import { TRANSCRIBE_TIMEOUT_MS } from "../../api/config";
import { ApiError } from "../../api/errors";
import { useAuthStore } from "../../auth/store";
import { registerPendingWork } from "../../pendingWork";
import type { TranscribeResponse } from "../../types";
import { precheck, PREPARED_PARTS, transcribeErrorMessage } from "../transcription/queue";
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
 */

/** Ancla de la sección en la portada: adonde se vuelve tras entrar. */
export const LANDING_UPLOAD_HASH = "#transcribir";
export const LANDING_UPLOAD_PATH = `/${LANDING_UPLOAD_HASH}`;

/** Clave de `sessionStorage` con el nombre de la imagen que espera a que se entre. */
export const PENDING_UPLOAD_KEY = "cadenza.portada.pendiente";

export type LandingStage =
  /** Sin imagen. */
  | { kind: "empty" }
  /** Con la imagen elegida y sus datos, antes de transcribir. */
  | { kind: "chosen" }
  | { kind: "transcribing"; startedAt: number }
  /**
   * Transcrita: la sesión es de `ownerId`; `name`, el nombre que tendrá (el dado o el del
   * archivo), mientras llega el de la sesión.
   */
  | { kind: "done"; result: TranscribeResponse; ownerId: string; name: string }
  /** `timedOut`: venció la espera y la sesión puede haberse creado igualmente. */
  | { kind: "failed"; message: string; timedOut: boolean };

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

  return {
    ...initial(),
    choose: (files) => {
      if (get().stage.kind === "transcribing") return;
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
        const result = await api.request<TranscribeResponse>("/transcribe", {
          method: "POST",
          body,
          token,
          signal: controller.signal,
          timeoutMs: TRANSCRIBE_TIMEOUT_MS,
        });
        if (runGeneration !== generation) return;
        // La imagen ya está en el servidor: no se guarda más tiempo del necesario.
        set({
          file: null,
          chooserId: null,
          draft: emptyDraft(PREPARED_PARTS),
          stage: {
            kind: "done",
            result,
            ownerId: user.id,
            name: nonBlank(draft.title) ?? file.name,
          },
        });
      } catch (error) {
        if (runGeneration !== generation) return;
        if (error instanceof ApiError && error.kind === "unauthorized") {
          // La sesión caducó: la imagen se conserva y se transcribe al volver a entrar.
          set({ stage: { kind: "chosen" }, expired: true });
          return;
        }
        const timedOut = error instanceof ApiError && error.kind === "timeout";
        set({
          stage: {
            kind: "failed",
            // Aquí no hay listado a la vista: se dice dónde buscar la sesión.
            message: timedOut
              ? "La transcripción tardó más de 30 s. Puede que la sesión se haya creado: búscala en tus sesiones antes de volver a intentarlo."
              : transcribeErrorMessage(error),
            timedOut,
          },
        });
      } finally {
        if (inFlight === controller) inFlight = null;
      }
    },
    reset: () => {
      cancel();
      markPending(null);
      set(initial());
    },
  };
});

export const LANDING_LEAVE_WARNING =
  "La imagen de la portada se está transcribiendo. Si sales, puede que la sesión llegue a crearse igualmente. ¿Salir?";

registerPendingWork(() =>
  useLandingUpload.getState().stage.kind === "transcribing" ? LANDING_LEAVE_WARNING : null,
);

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
