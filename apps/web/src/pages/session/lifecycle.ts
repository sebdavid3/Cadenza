import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { ApiClient } from "../../api/client";
import { ApiError, errorMessage } from "../../api/errors";
import type { FinalizeResponse, FindingRead, ReopenResponse, SessionViewRead } from "../../types";
import { refreshSessions } from "../transcription/sessions";
import { summary } from "./findingActions";
import {
  sessionDetailQuery,
  sessionFindingsKey,
  sessionFindingsQuery,
  validatedSeqQuery,
} from "./session";

const sessionPath = (sessionId: string) => `/sessions/${encodeURIComponent(sessionId)}` as const;

/**
 * `POST /sessions/{id}/finalize`: valida el estado actual del servidor como una revalidación
 * (conserva los descartes de la validación vigente, D65) y cierra la sesión a las ediciones
 * (ADR-0014). Responde con el `final_seq` validado y solo los hallazgos activos; 409 si ya estaba
 * finalizada (ADR-0043).
 */
export function finalizeSession(
  api: ApiClient,
  sessionId: string,
  signal?: AbortSignal,
): Promise<FinalizeResponse> {
  return api.request<FinalizeResponse>(`${sessionPath(sessionId)}/finalize`, {
    method: "POST",
    signal,
  });
}

/** `POST /sessions/{id}/reopen`: la vuelve a abrir a las ediciones, con su log intacto. */
export function reopenSession(
  api: ApiClient,
  sessionId: string,
  signal?: AbortSignal,
): Promise<ReopenResponse> {
  return api.request<ReopenResponse>(`${sessionPath(sessionId)}/reopen`, {
    method: "POST",
    signal,
  });
}

/** Finalizar o reabrir la sesión (#187). */
export type LifecycleAction = "finalize" | "reopen";

export type LifecycleStatus =
  | { kind: "idle" }
  | { kind: "busy"; action: LifecycleAction }
  /** `nonce` distingue dos mensajes iguales seguidos; `seq`, el estado del que habla. */
  | { kind: "said"; message: string; nonce: number; seq: number | null };

/**
 * Cómo acabó una orden: `done` se hizo; `failed` no se hizo o no se sabe; `closed`, la sesión ya
 * estaba finalizada; `ignored`, no se envió (había otra en curso) o se canceló.
 */
export type LifecycleOutcome = "done" | "failed" | "closed" | "ignored";

const VERBS: Record<LifecycleAction, { done: string; it: string }> = {
  finalize: { done: "finalizó", it: "finalizarla" },
  reopen: { done: "reabrió", it: "reabrirla" },
};

/** Qué decir de un error que no es un 409 ni un 404, o null si no hay nada que decir. */
function failureText(action: LifecycleAction, error: unknown): string | null {
  const kind = error instanceof ApiError ? error.kind : "unexpected";
  const { done, it } = VERBS[action];
  switch (kind) {
    // Cancelada, o un 401, ante el que el cliente ya cierra la sesión del navegador (ADR-0020).
    case "aborted":
    case "unauthorized":
      return null;
    case "forbidden":
      return `No se ${done}: solo la persona que hizo la transcripción puede ${it}.`;
    // Sin respuesta, o con una que no lo confirma: pudo hacerse. Volver a intentarlo es seguro: si
    // ya se finalizó, el servidor responde 409 y la vista lo dice.
    case "network":
    case "timeout":
    case "server":
    case "unexpected":
      return `No llegó la confirmación: no se sabe si se ${done}. ${errorMessage(error)} Puedes volver a intentarlo.`;
    default:
      return `No se ${done}: ${errorMessage(error)}`;
  }
}

/** Errores tras los que no se sabe si la orden se hizo. */
const UNKNOWN = new Set(["network", "timeout", "server", "unexpected"]);

const plural = (count: number, one: string, many: string) =>
  `${String(count)} ${count === 1 ? one : many}`;

const lowerFirst = (text: string) => `${text.charAt(0).toLowerCase()}${text.slice(1)}`;

const HARD_SPACE = String.fromCharCode(0xa0);

interface LifecycleOptions {
  /** Estado que se ve. */
  seq: number;
  /**
   * Si la sesión es asistida. En una no asistida no se habla del validador: ni corre al finalizar
   * ni se muestra (ADR-0040 §13).
   */
  assisted: boolean;
  /**
   * Carga y muestra de una vez el estado actual de la sesión (el `reload` del editor). Devuelve el
   * `seq` que cargó, o null si no lo cargó.
   */
  reload: () => Promise<number | null>;
}

/**
 * Finalizar y reabrir la sesión (#187, ADR-0043). Nada se da por hecho sin la respuesta del
 * servidor. Finalizar valida el estado del servidor: si es el que se ve, la vista pasa a solo
 * lectura con la lista de la validación final (que se vuelve a pedir, con los descartados que se
 * conservan); si el servidor iba por uno posterior, se carga ese estado entero. Mientras se
 * finaliza, las correcciones y las órdenes sobre los posibles errores esperan (`busy`).
 */
export function useLifecycle(api: ApiClient, sessionId: string, options: LifecycleOptions) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<LifecycleStatus>({ kind: "idle" });
  const inFlight = useRef(false);
  const nonce = useRef(0);
  const controllerRef = useRef<AbortController | null>(null);
  const optionsRef = useRef(options);
  useLayoutEffect(() => {
    optionsRef.current = options;
  });
  useEffect(
    () => () => {
      controllerRef.current?.abort();
    },
    [],
  );
  const detailKey = sessionDetailQuery(api, sessionId).queryKey;

  function say(message: string, seq: number | null = optionsRef.current.seq) {
    nonce.current += 1;
    setStatus({ kind: "said", message, nonce: nonce.current, seq });
  }

  function begin(action: LifecycleAction) {
    if (inFlight.current) return null;
    inFlight.current = true;
    const controller = new AbortController();
    controllerRef.current = controller;
    setStatus({ kind: "busy", action });
    return controller.signal;
  }

  /** Pasa el detalle que se ve al estado del ciclo de vida que devolvió el servidor. */
  function setSessionStatus(seq: number, next: string) {
    queryClient.setQueryData<SessionViewRead>(detailKey, (shown) =>
      shown && (shown.current_seq ?? 0) === seq ? { ...shown, status: next } : shown,
    );
  }

  /** La lista de la última validación en el estado `seq`, si llegó. */
  function listed(seq: number): FindingRead[] | undefined {
    const key = sessionFindingsQuery(api, sessionId, seq).queryKey;
    return queryClient.getQueryState(key)?.status === "success"
      ? queryClient.getQueryData(key)
      : undefined;
  }

  /** El estado validado se recuerda con su lista ya pedida, como al revalidar (ADR-0035 §7). */
  function remember(validated: number) {
    queryClient.setQueryData(validatedSeqQuery(sessionId).queryKey, (known) =>
      Math.max(known ?? 0, validated),
    );
  }

  /** Da por vieja la lista de todos los estados sin pedirla ahora (la pide quien la necesite). */
  function forgetFindings() {
    void queryClient.invalidateQueries({
      queryKey: sessionFindingsKey(sessionId),
      refetchType: "none",
    });
  }

  /**
   * Tras una orden sin respuesta, vuelve a pedir el detalle y dice si la sesión quedó como la
   * orden la habría dejado (`finalized`): entonces se vuelve a pedir también la lista, que sería
   * la de otra validación. No hace nada tras un 404 del detalle: la vista lo dice.
   */
  async function settledAs(finalized: boolean): Promise<boolean> {
    await queryClient.invalidateQueries({ queryKey: detailKey, exact: true });
    const fresh = queryClient.getQueryData<SessionViewRead>(detailKey);
    if (!fresh || (fresh.status === "finalized") !== finalized) return false;
    await queryClient.invalidateQueries({ queryKey: sessionFindingsKey(sessionId) });
    const seq = fresh.current_seq ?? 0;
    if (listed(seq)) remember(seq);
    return true;
  }

  /**
   * Lo que dejó la validación final, sin prometer más de lo que sabe el validador. Si la lista no
   * se pudo volver a pedir, se resume la respuesta, que solo trae los activos: el resumen no dice
   * entonces cuántos descartes se conservaron.
   */
  function finalText(result: FinalizeResponse): string {
    if (!optionsRef.current.assisted) return "";
    const findings = listed(result.final_seq) ?? result.findings;
    return ` Validación final: ${lowerFirst(summary(findings))}`;
  }

  async function finalize(): Promise<LifecycleOutcome> {
    const signal = begin("finalize");
    if (!signal) return "ignored";
    const cancelled = () => signal.aborted;
    try {
      let result: FinalizeResponse;
      try {
        result = await finalizeSession(api, sessionId, signal);
      } catch (error) {
        if (cancelled()) return "ignored";
        const kind = error instanceof ApiError ? error.kind : "unexpected";
        // El único 409 de esta ruta: ya estaba finalizada (en otra pestaña, o una petición
        // anterior sin respuesta). Se carga su estado, que es de solo lectura.
        if (kind === "conflict") {
          // La lista que se ve puede ser de antes de esa finalización: se carga con el estado.
          forgetFindings();
          const loaded = await optionsRef.current.reload();
          if (loaded !== null && listed(loaded)) remember(loaded);
          if (cancelled()) return "ignored";
          say(
            loaded === null
              ? "No se volvió a finalizar: la sesión ya estaba finalizada, quizá desde otra pestaña o dispositivo, pero no se pudo cargar su estado: recarga la página para verlo."
              : "No se volvió a finalizar: la sesión ya estaba finalizada, quizá desde otra pestaña o dispositivo. Ya ves su estado.",
            null,
          );
          return "closed";
        }
        if (kind === "not-found") {
          say("No se finalizó: la sesión ya no existe o no tienes acceso a ella.");
          void queryClient.invalidateQueries({ queryKey: detailKey, exact: true });
          return "failed";
        }
        const text = failureText("finalize", error);
        if (!text) {
          setStatus({ kind: "idle" });
          return "failed";
        }
        // Sin respuesta pudo finalizarse: se vuelve a pedir el detalle y, si lo está, se dice y
        // se pide la lista de la validación final.
        if (UNKNOWN.has(kind) && (await settledAs(true))) {
          say(
            "No llegó la confirmación, pero la sesión está finalizada: ya ves su estado y la lista de su validación final.",
            null,
          );
          return "closed";
        }
        if (cancelled()) return "ignored";
        say(text);
        return "failed";
      }
      refreshSessions(queryClient);
      // #188: aquí se enviarán las métricas de esfuerzo de la corrección (`POST /effort`), con la
      // sesión ya finalizada en `result.final_seq`.
      const shown = optionsRef.current.seq;
      const edits = plural(result.final_seq, "edición", "ediciones");
      if (result.final_seq !== shown) {
        // El servidor iba por otro estado (se editó en otra pestaña): se finalizó ese, y se carga.
        forgetFindings();
        const loaded = await optionsRef.current.reload();
        if (loaded !== null && listed(result.final_seq)) remember(result.final_seq);
        if (cancelled()) return "ignored";
        if (loaded === null) {
          say(
            `Se finalizó la sesión tal como estaba tras ${edits}, un estado distinto del que se ve, pero no se pudo cargar: recarga la página para verlo.`,
            shown,
          );
          return "done";
        }
        say(
          `La sesión iba por un estado posterior al que se veía (tras ${edits}): se finalizó ese estado, que ya ves.${finalText(result)}`,
          result.final_seq,
        );
        return "done";
      }
      setSessionStatus(shown, result.status);
      // La respuesta no trae los descartados que se conservan: se vuelve a pedir la lista.
      await queryClient.invalidateQueries({ queryKey: sessionFindingsKey(sessionId) });
      if (listed(result.final_seq)) remember(result.final_seq);
      if (cancelled()) return "ignored";
      say(`Sesión finalizada.${finalText(result)} Si se te pasó algo, puedes reabrirla.`);
      return "done";
    } finally {
      inFlight.current = false;
    }
  }

  async function reopen(): Promise<LifecycleOutcome> {
    const signal = begin("reopen");
    if (!signal) return "ignored";
    const cancelled = () => signal.aborted;
    try {
      let result: ReopenResponse;
      try {
        result = await reopenSession(api, sessionId, signal);
      } catch (error) {
        if (cancelled()) return "ignored";
        const kind = error instanceof ApiError ? error.kind : "unexpected";
        if (kind === "not-found") {
          say("No se reabrió: la sesión ya no existe o no tienes acceso a ella.");
          void queryClient.invalidateQueries({ queryKey: detailKey, exact: true });
          return "failed";
        }
        const text = failureText("reopen", error);
        if (!text) {
          setStatus({ kind: "idle" });
          return "failed";
        }
        if (UNKNOWN.has(kind) && (await settledAs(false))) {
          say("No llegó la confirmación, pero la sesión está abierta: puedes seguir corrigiendo.");
          return "done";
        }
        if (cancelled()) return "ignored";
        say(text);
        return "failed";
      }
      refreshSessions(queryClient);
      const shown = optionsRef.current.seq;
      if (result.current_seq === shown) setSessionStatus(shown, result.status);
      else {
        const loaded = await optionsRef.current.reload();
        if (cancelled()) return "ignored";
        if (loaded === null) {
          say(
            "Se reabrió la sesión, pero no se pudo cargar su estado actual: recarga la página para seguir corrigiendo.",
            null,
          );
          return "done";
        }
      }
      if (cancelled()) return "ignored";
      say("Sesión reabierta: puedes seguir corrigiendo.", result.current_seq);
      return "done";
    } finally {
      inFlight.current = false;
    }
  }

  const busy = status.kind === "busy";
  const message =
    status.kind === "said" && (status.seq === null || status.seq === options.seq)
      ? // Un espacio duro alterno: el mismo mensaje dos veces seguidas se vuelve a anunciar.
        `${status.message}${status.nonce % 2 === 1 ? HARD_SPACE : ""}`
      : status.kind === "busy"
        ? status.action === "finalize"
          ? "Finalizando…"
          : "Reabriendo…"
        : null;

  return {
    busy,
    finalizing: status.kind === "busy" && status.action === "finalize",
    message,
    finalize,
    reopen,
  };
}

export type Lifecycle = ReturnType<typeof useLifecycle>;
