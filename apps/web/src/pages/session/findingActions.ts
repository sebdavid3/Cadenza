import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { ApiClient } from "../../api/client";
import { ApiError, errorMessage } from "../../api/errors";
import type { FindingRead } from "../../types";
import { withFinding } from "./findings";
import {
  dismissFinding,
  restoreFinding,
  revalidateSession,
  sessionDetailQuery,
  sessionFindingsKey,
  sessionFindingsQuery,
  validatedSeqQuery,
} from "./session";

/** Qué se puede hacer con los posibles errores (ADR-0035). */
export type FindingAction = "dismiss" | "restore" | "revalidate";

/**
 * Qué pasó con la última orden sobre los posibles errores. Mientras una está en curso no se envía
 * otra: revalidar sustituye los hallazgos del estado validado, con otros id.
 */
export type FindingActionsStatus =
  | { kind: "idle" }
  | { kind: "busy"; action: FindingAction; findingId: number | null }
  /** `nonce` distingue dos mensajes iguales seguidos, para que se vuelvan a anunciar. */
  | { kind: "said"; message: string; nonce: number };

/**
 * Cómo acabó una orden, para el panel: `done` se hizo; `failed` no se hizo o no se sabe, y se
 * puede volver a intentar; `gone`, el posible error ya no está; `closed`, la sesión ya no admite
 * cambios; `ignored`, no se envió (había otra en curso) o se canceló.
 */
export type FindingOutcome = "done" | "failed" | "gone" | "closed" | "ignored";

const VERBS: Record<FindingAction, { done: string }> = {
  dismiss: { done: "descartó" },
  restore: { done: "restauró" },
  revalidate: { done: "revalidó" },
};

/** Qué decir de un error que no es un 409 ni un 404, y si hay que decirlo. */
function failureText(action: FindingAction, error: unknown): string | null {
  const kind = error instanceof ApiError ? error.kind : "unexpected";
  const { done } = VERBS[action];
  switch (kind) {
    // Cancelada, o un 401, ante el que el cliente ya cierra la sesión del navegador (ADR-0020).
    case "aborted":
    case "unauthorized":
      return null;
    case "forbidden":
      return `No se ${done}: solo la persona que hizo la transcripción puede cambiar sus posibles errores.`;
    // Sin respuesta, o con una que no lo confirma: pudo hacerse. Repetirlo no cambia nada.
    case "network":
    case "timeout":
    case "server":
    case "unexpected":
      return `No llegó la confirmación: no se sabe si se ${done}. ${errorMessage(error)} Puedes volver a intentarlo.`;
    default:
      return `No se ${done}: ${errorMessage(error)}`;
  }
}

const plural = (count: number, one: string, many: string) =>
  `${String(count)} ${count === 1 ? one : many}`;

/**
 * Qué dejó la revalidación, sin prometer más de lo que sabe el validador (ADR-0021 §4): que no
 * señale nada no garantiza que la transcripción esté bien.
 */
function summary(findings: readonly FindingRead[]): string {
  const dismissed = findings.filter((finding) => finding.status === "dismissed").length;
  const active = findings.length - dismissed;
  const kept =
    dismissed > 0
      ? ` ${plural(dismissed, "sigue descartado", "siguen descartados")} como falso positivo porque su nota no cambió.`
      : "";
  if (active > 0) return `${plural(active, "posible error", "posibles errores")}.${kept}`;
  if (dismissed > 0) {
    return `No queda ningún posible error activo.${kept} Que no quede ninguno no garantiza que la transcripción esté bien.`;
  }
  return "El validador no señala ningún compás. Que no señale ninguno no garantiza que la transcripción esté bien.";
}

const HARD_SPACE = String.fromCharCode(0xa0);

const lowerFirst = (text: string) => `${text.charAt(0).toLowerCase()}${text.slice(1)}`;

interface FindingActionsOptions {
  /** Estado que se ve: el de la partitura dibujada y la lista. */
  seq: number;
  /** Nombra un posible error: «Duración del compás, compás 3». */
  labelOf: (finding: FindingRead) => string;
  /**
   * Carga y muestra de una vez el estado actual de la sesión (el `reload` del editor), cuando el
   * servidor va por delante del que se ve o la sesión ya no admite cambios.
   */
  reload: () => Promise<void>;
}

/**
 * Descartar, restaurar y revalidar los posibles errores (#186, ADR-0035). Nada se da por hecho
 * sin la respuesta del servidor. Descartar y restaurar no cambian la partitura: solo la lista, que
 * se actualiza con el hallazgo devuelto. Revalidar sustituye los hallazgos de la última
 * validación: se vuelven a pedir (con los descartados que se conservan) y, si el servidor validó
 * un estado posterior al que se ve, se carga ese estado.
 */
export function useFindingActions(
  api: ApiClient,
  sessionId: string,
  options: FindingActionsOptions,
) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<FindingActionsStatus>({ kind: "idle" });
  const inFlight = useRef(false);
  const nonce = useRef(0);
  const controllerRef = useRef<AbortController | null>(null);
  // Lo de la vista en el último render: una respuesta llega después de varios.
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

  function say(message: string) {
    nonce.current += 1;
    setStatus({ kind: "said", message, nonce: nonce.current });
  }

  /** Una orden a la vez; devuelve su señal, o null si ya hay otra en curso. */
  function begin(action: FindingAction, findingId: number | null) {
    if (inFlight.current) return null;
    inFlight.current = true;
    const controller = new AbortController();
    controllerRef.current = controller;
    setStatus({ kind: "busy", action, findingId });
    return controller.signal;
  }

  /** Vuelve a pedir la lista de la última validación para todos los estados de la sesión. */
  function refetchFindings() {
    return queryClient.invalidateQueries({ queryKey: sessionFindingsKey(sessionId) });
  }

  /**
   * Da por vieja la lista de todos los estados sin pedirla ahora: la próxima vista que la necesite
   * la pide. Para cuando no se sabe qué hizo el servidor (la vista se cerró con la orden en curso)
   * o cuando se va a cargar otro estado.
   */
  function forgetFindings() {
    void queryClient.invalidateQueries({
      queryKey: sessionFindingsKey(sessionId),
      refetchType: "none",
    });
  }

  /** Descartar o restaurar: cambia el estado de un hallazgo, no la partitura. */
  async function change(
    action: "dismiss" | "restore",
    finding: FindingRead,
    post: (signal: AbortSignal) => Promise<FindingRead>,
  ): Promise<FindingOutcome> {
    const signal = begin(action, finding.id);
    if (!signal) return "ignored";
    const cancelled = () => signal.aborted;
    const label = optionsRef.current.labelOf(finding);
    const { done } = VERBS[action];
    try {
      let updated: FindingRead;
      try {
        updated = await post(signal);
      } catch (error) {
        if (cancelled()) {
          forgetFindings();
          return "ignored";
        }
        const kind = error instanceof ApiError ? error.kind : "unexpected";
        // El único 409 de estas rutas: la sesión está finalizada (ADR-0014).
        if (kind === "conflict") {
          say(
            `No se ${done}: la sesión está finalizada y sus posibles errores ya no se pueden cambiar.`,
          );
          await optionsRef.current.reload();
          return "closed";
        }
        // Otra validación sustituyó a la que se ve (sus hallazgos tienen otro id), o la sesión ya
        // no está: se vuelve a pedir la lista y, si tampoco está, la vista lo dice.
        if (kind === "not-found") {
          await refetchFindings();
          if (cancelled()) return "ignored";
          const listed = queryClient.getQueryState(
            sessionFindingsQuery(api, sessionId, optionsRef.current.seq).queryKey,
          );
          if (listed?.error instanceof ApiError && listed.error.kind === "not-found") {
            void queryClient.invalidateQueries({
              queryKey: sessionDetailQuery(api, sessionId).queryKey,
            });
          }
          say(
            `No se ${done}: ese posible error ya no está en la última validación. Ya ves la lista actual.`,
          );
          return "gone";
        }
        const text = failureText(action, error);
        if (text) say(text);
        else setStatus({ kind: "idle" });
        return "failed";
      }
      // El hallazgo devuelto sustituye al de la lista, en todos los estados que la tengan, también
      // si la vista ya se cerró: la caché la puede volver a mostrar.
      queryClient.setQueriesData<FindingRead[]>(
        { queryKey: sessionFindingsKey(sessionId) },
        (list) => (list ? withFinding(list, updated) : list),
      );
      if (cancelled()) return "ignored";
      say(
        action === "dismiss"
          ? `Descartado como falso positivo: ${label}. La partitura no cambia.`
          : `Restaurado: ${label} vuelve a señalarse.`,
      );
      return "done";
    } finally {
      inFlight.current = false;
    }
  }

  function dismiss(finding: FindingRead, reason: string) {
    const trimmed = reason.trim();
    return change("dismiss", finding, (signal) =>
      dismissFinding(
        api,
        sessionId,
        finding.id,
        { reason: trimmed === "" ? null : trimmed },
        signal,
      ),
    );
  }

  function restore(finding: FindingRead) {
    return change("restore", finding, (signal) =>
      restoreFinding(api, sessionId, finding.id, signal),
    );
  }

  /**
   * Revalida el estado actual del servidor. Su `current_seq` dice qué estado se validó: el que se
   * ve, uno posterior (se editó en otra parte: se carga) o uno anterior (se editó mientras tanto:
   * hay que volver a revalidar).
   */
  async function revalidate(): Promise<FindingOutcome> {
    const signal = begin("revalidate", null);
    if (!signal) return "ignored";
    const cancelled = () => signal.aborted;
    try {
      let validated: number;
      try {
        validated = (await revalidateSession(api, sessionId, signal)).current_seq;
      } catch (error) {
        if (cancelled()) {
          forgetFindings();
          return "ignored";
        }
        if (error instanceof ApiError && error.kind === "not-found") {
          say("No se revalidó: la sesión ya no existe o no tienes acceso a ella.");
          void queryClient.invalidateQueries({
            queryKey: sessionDetailQuery(api, sessionId).queryKey,
          });
          return "failed";
        }
        const text = failureText("revalidate", error);
        if (text) say(text);
        else setStatus({ kind: "idle" });
        return "failed";
      }
      queryClient.setQueryData(validatedSeqQuery(sessionId).queryKey, (known) =>
        Math.max(known ?? 0, validated),
      );
      if (cancelled()) {
        forgetFindings();
        return "ignored";
      }
      const shown = optionsRef.current.seq;
      // Lo que el validador dejó en la lista del estado validado, ya pedida.
      const listed = () => {
        const key = sessionFindingsQuery(api, sessionId, validated).queryKey;
        const state = queryClient.getQueryState(key);
        return state?.status === "success" ? queryClient.getQueryData(key) : undefined;
      };
      if (validated > shown) {
        // El servidor va por delante: se carga su estado entero, con la lista de ese estado. La
        // del que se ve ya no hace falta pedirla.
        forgetFindings();
        await optionsRef.current.reload();
        if (cancelled()) return "ignored";
        const findings = listed();
        say(
          `La sesión cambió en otra pestaña o dispositivo: se revalidó su estado actual, que ya ves.${
            findings ? ` ${summary(findings)}` : ""
          }`,
        );
        return "done";
      }
      await refetchFindings();
      if (cancelled()) return "ignored";
      if (validated < shown) {
        say(
          `Se revalidó la partitura tal como estaba tras ${plural(validated, "edición", "ediciones")}, pero se editó mientras tanto: hay que volver a revalidar.`,
        );
        return "done";
      }
      const findings = listed();
      say(
        findings
          ? `Revalidada la partitura actual: ${lowerFirst(summary(findings))}`
          : "Se revalidó la partitura actual, pero no se pudo cargar la lista de posibles errores.",
      );
      return "done";
    } finally {
      inFlight.current = false;
    }
  }

  const busy = status.kind === "busy";
  /** Lo que el panel dice de la última orden, o null si no hay nada que decir. */
  const message =
    status.kind === "said"
      ? // Un espacio duro alterno: el mismo mensaje dos veces seguidas se vuelve a anunciar.
        `${status.message}${status.nonce % 2 === 1 ? HARD_SPACE : ""}`
      : status.kind === "busy"
        ? { dismiss: "Descartando…", restore: "Restaurando…", revalidate: "Revalidando…" }[
            status.action
          ]
        : null;

  return {
    status,
    busy,
    message,
    pendingId: status.kind === "busy" ? status.findingId : null,
    dismiss,
    restore,
    revalidate,
  };
}

export type FindingActions = ReturnType<typeof useFindingActions>;
