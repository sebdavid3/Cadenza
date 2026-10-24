import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import type { ApiClient } from "../../api/client";
import { ApiError } from "../../api/errors";
import type { AnchorPayload, SessionDetailRead } from "../../types";
import {
  activeFifths,
  carryAnchor,
  eventAt,
  planAgain,
  planEdit,
  type DecidedEdit,
  type EditCommand,
  type EditPlan,
  type EditTarget,
} from "./edits";
import {
  fetchSessionDetail,
  postEdit,
  sessionDetailQuery,
  sessionFindingsQuery,
  sessionMusicXmlQuery,
  sessionTimingQuery,
} from "./session";

/** Edición enviada: qué se pidió, sobre qué evento y en qué estado (ADR-0011). */
export interface EditRequest extends DecidedEdit {
  anchor: AnchorPayload;
  baseSeq: number;
  /** Qué cambia, dicho: «altura Re 4». */
  change: string;
}

type Failure = "rejected" | "forbidden" | "missing" | "unknown";

/**
 * Qué pasó con la última orden. Mientras se guarda o si no se sabe en qué estado quedó la sesión
 * (sin respuesta, o sin poder cargar el estado nuevo), no se edita: el `base_seq` podría no ser ya
 * el del servidor.
 */
export type EditorStatus =
  | { kind: "idle" }
  | { kind: "saving"; request: EditRequest }
  | { kind: "saved"; request: EditRequest }
  | { kind: "refused"; message: string }
  /** 409 porque otra pestaña o dispositivo editó antes: ya se recargó. */
  | { kind: "conflict"; request: EditRequest }
  /** 409 porque la sesión está finalizada (ADR-0014): ya se recargó. */
  | { kind: "closed"; request: EditRequest }
  /** 409, pero no se pudo cargar el estado actual. */
  | { kind: "outdated"; request: EditRequest }
  /** 422, 403, 404 o sin respuesta clara (red, tiempo agotado, 5xx). */
  | { kind: Failure; request: EditRequest }
  /** 201, pero no se pudo cargar el estado nuevo. */
  | { kind: "unsynced"; request: EditRequest }
  | { kind: "reloading" }
  | { kind: "reloaded" }
  | { kind: "reload-failed" };

/** Estados en los que no se envía nada hasta recargar o hasta que acabe lo que está en curso. */
const BLOCKING = new Set<EditorStatus["kind"]>([
  "saving",
  "outdated",
  "unknown",
  "unsynced",
  "reloading",
  "reload-failed",
]);

/** Qué dice un error de `POST /edits` que no es un 409, o null si no hay nada que decir. */
function failure(error: unknown): Failure | "idle" | null {
  const kind = error instanceof ApiError ? error.kind : "unexpected";
  switch (kind) {
    case "aborted":
      return null;
    case "validation":
      return "rejected";
    case "forbidden":
      return "forbidden";
    case "not-found":
      return "missing";
    // El cliente ya cierra la sesión del navegador ante un 401 (ADR-0020).
    case "unauthorized":
      return "idle";
    default:
      return "unknown";
  }
}

/**
 * Corrección de la nota elegida (#183, ADR-0030). Cada orden es una edición con el `base_seq` del
 * estado que se ve; nada se da por guardado sin el 201. Tras él, o tras un 409, se pide el detalle
 * de la sesión y, antes de mostrarlo, el MusicXML, los posibles errores y los tiempos de ese
 * estado: la vista pasa de un estado al otro de una vez. Un 409 nunca se reintenta solo.
 */
export function useEditor(
  api: ApiClient,
  sessionId: string,
  detail: SessionDetailRead | undefined,
) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<EditorStatus>({ kind: "idle" });
  // Último estado que se sabe que tiene el servidor: hasta que la vista lo muestre no se edita.
  const [knownSeq, setKnownSeq] = useState<number | null>(null);
  const inFlight = useRef(false);
  const controllerRef = useRef<AbortController | null>(null);
  useEffect(
    () => () => {
      controllerRef.current?.abort();
    },
    [],
  );

  /** Carga el estado actual del servidor con todo lo que la vista pide de él, y lo muestra. */
  async function refresh(signal: AbortSignal) {
    const fresh = await fetchSessionDetail(api, sessionId, signal);
    const seq = fresh.current_seq ?? 0;
    // Si algo no llega, no se deja de mostrar el estado: la vista lo pide y lo dice como siempre.
    const ignore = () => undefined;
    await Promise.all([
      queryClient.query(sessionMusicXmlQuery(api, sessionId, seq)).catch(ignore),
      queryClient.query(sessionFindingsQuery(api, sessionId, seq)).catch(ignore),
      queryClient.query(sessionTimingQuery(api, sessionId, seq)).catch(ignore),
    ]);
    if (signal.aborted) return null;
    setKnownSeq(seq);
    queryClient.setQueryData(sessionDetailQuery(api, sessionId).queryKey, fresh);
    return fresh;
  }

  /** Una sola petición a la vez: la siguiente se construiría sobre un estado que va a cambiar. */
  function begin() {
    if (inFlight.current) return null;
    inFlight.current = true;
    const controller = new AbortController();
    controllerRef.current = controller;
    return controller;
  }

  async function send(request: EditRequest) {
    const controller = begin();
    if (!controller) return;
    const { signal } = controller;
    // Función y no propiedad: TypeScript no sabe que la señal puede cambiar durante un await.
    const cancelled = () => signal.aborted;
    setStatus({ kind: "saving", request });
    try {
      try {
        await postEdit(
          api,
          sessionId,
          {
            base_seq: request.baseSeq,
            op: request.op,
            anchor: request.anchor,
            // El servidor fija el estado previo (ADR-0017).
            before: null,
            after: request.after,
          },
          signal,
        );
      } catch (error) {
        if (cancelled()) return;
        if (!(error instanceof ApiError && error.kind === "conflict")) {
          const kind = failure(error);
          if (kind === "idle") setStatus({ kind });
          else if (kind) setStatus({ kind, request });
          return;
        }
        // 409: o se editó antes en otra parte o la sesión está cerrada. Lo dice el estado recargado.
        const fresh = await refresh(signal).catch(() => null);
        if (cancelled()) return;
        if (!fresh) setStatus({ kind: "outdated", request });
        else setStatus({ kind: fresh.status === "finalized" ? "closed" : "conflict", request });
        return;
      }
      const fresh = await refresh(signal).catch(() => null);
      if (cancelled()) return;
      setStatus(fresh ? { kind: "saved", request } : { kind: "unsynced", request });
    } finally {
      inFlight.current = false;
    }
  }

  async function reload() {
    const controller = begin();
    if (!controller) return;
    setStatus({ kind: "reloading" });
    try {
      const fresh = await refresh(controller.signal).catch(() => null);
      if (controller.signal.aborted) return;
      setStatus({ kind: fresh ? "reloaded" : "reload-failed" });
    } finally {
      inFlight.current = false;
    }
  }

  const score = detail?.current_score ?? null;
  const seq = detail?.current_seq ?? 0;
  const blocked = BLOCKING.has(status.kind) || (knownSeq !== null && seq < knownSeq);

  /** Una orden sobre el evento elegido: se envía o se dice por qué no. */
  function run(command: EditCommand, target: EditTarget | null) {
    if (blocked || !score) return;
    const plan = planEdit(command, target, target ? activeFifths(score, target.anchor) : 0);
    if (plan.kind === "refused") {
      setStatus({ kind: "refused", message: plan.message });
      return;
    }
    if (!target) return;
    const { op, after, change } = plan;
    void send({ op, after, anchor: target.anchor, baseSeq: seq, change });
  }

  /**
   * Tras un 409, la misma edición sobre el estado recargado, si el ancla sigue designando el
   * mismo evento y no lo tiene ya. Solo se envía si la persona lo pide.
   */
  let retry: { plan: EditPlan; anchor: AnchorPayload | null } | null = null;
  if (status.kind === "conflict" && detail && score) {
    const anchor = carryAnchor(status.request.anchor, status.request.baseSeq, detail);
    const found = anchor ? eventAt(score, anchor) : null;
    retry = {
      plan: planAgain(status.request, anchor && found ? { anchor, ...found } : null),
      anchor,
    };
  }

  function reapply() {
    if (blocked || retry?.plan.kind !== "edit" || !retry.anchor) return;
    const { op, after, change } = retry.plan;
    void send({ op, after, anchor: retry.anchor, baseSeq: seq, change });
  }

  return { status, blocked, run, reload, retry, reapply };
}

export type Editor = ReturnType<typeof useEditor>;
