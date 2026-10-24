import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import type { ApiClient } from "../../api/client";
import { ApiError } from "../../api/errors";
import type { AnchorPayload, SessionDetailRead } from "../../types";
import {
  carryAnchor,
  planCommand,
  replan,
  type EditCommand,
  type EditPlan,
  type EditRequestLike,
  type EditTarget,
} from "./edits";
import { anchorKey } from "./noteMap";
import { useSelectionStore } from "./selection";
import {
  fetchSessionDetail,
  postEdit,
  sessionDetailQuery,
  sessionFindingsQuery,
  sessionMusicXmlQuery,
  sessionTimingQuery,
} from "./session";

/**
 * Edición enviada: lo que se pidió (con qué se dice y qué queda elegido al guardarla), sobre qué
 * ancla y en qué estado (ADR-0011).
 */
export type EditRequest = Extract<EditPlan, { kind: "edit" }> &
  EditRequestLike & {
    /** Evento elegido cuando se dio la orden, en el estado `baseSeq`. */
    target: AnchorPayload;
  };

/** La edición que pide un plan sobre el evento elegido, en el estado `baseSeq`. */
const requestOf = (
  plan: Extract<EditPlan, { kind: "edit" }>,
  target: AnchorPayload,
  baseSeq: number,
): EditRequest => ({ ...plan, anchor: plan.anchor ?? target, baseSeq, target });

/**
 * Qué pasó con la última orden. Mientras se guarda o si no se sabe en qué estado quedó la sesión
 * (sin respuesta, o sin poder cargar el estado nuevo), no se edita: el `base_seq` podría no ser ya
 * el del servidor.
 */
export type EditorStatus =
  | { kind: "idle" }
  | { kind: "saving"; request: EditRequest }
  | { kind: "saved"; request: EditRequest }
  /** Una orden que no se envió (no se puede sobre esa nota); `nonce` distingue repeticiones. */
  | { kind: "refused"; message: string; nonce: number }
  /** 409 porque otra pestaña o dispositivo editó antes: ya se recargó. */
  | { kind: "conflict"; request: EditRequest }
  /** 409 porque la sesión está finalizada (ADR-0014): ya se recargó. */
  | { kind: "closed"; request: EditRequest }
  /** 409, pero no se pudo cargar el estado actual. */
  | { kind: "outdated"; request: EditRequest }
  /** 422 (u otro rechazo del servidor): no se guardó nada. */
  | { kind: "rejected"; request: EditRequest }
  /** 403: la sesión no es de quien la ve (ADR-0012). */
  | { kind: "forbidden"; request: EditRequest }
  /** 404: la sesión ya no existe o no se tiene acceso. */
  | { kind: "missing"; request: EditRequest }
  /**
   * No se sabe si se guardó: sin respuesta (`silent`: red, tiempo agotado) o con una respuesta
   * que no lo confirma (`server`: 5xx, respuesta inesperada).
   */
  | { kind: "unknown"; request: EditRequest; reason: "silent" | "server" }
  /** 201, pero no se pudo cargar el estado nuevo. */
  | { kind: "unsynced"; request: EditRequest }
  | { kind: "reloading" }
  | { kind: "reloaded" }
  | { kind: "reload-failed" };

/** Estados en los que no se envía nada: hasta recargar, hasta que acabe lo que está en curso o
 * porque la sesión no se puede editar. */
const BLOCKING = new Set<EditorStatus["kind"]>([
  "saving",
  "outdated",
  "forbidden",
  "missing",
  "unknown",
  "unsynced",
  "reloading",
  "reload-failed",
]);

/** Avisos que no se pueden perder por una orden rechazada: el rechazo se dice aparte. */
const LASTING = new Set<EditorStatus["kind"]>([
  "conflict",
  "closed",
  "outdated",
  "rejected",
  "forbidden",
  "missing",
  "unknown",
  "unsynced",
  "reload-failed",
]);

/** Qué pasó según el error de un `POST /edits` que no es un 409, o null si no hay nada que decir. */
function failure(
  error: unknown,
  request: EditRequest,
): Exclude<EditorStatus, { kind: "refused" }> | null {
  const kind = error instanceof ApiError ? error.kind : "unexpected";
  switch (kind) {
    case "aborted":
      return null;
    // El servidor lo rechazó: no se guardó nada.
    case "validation":
    case "payload-too-large":
    case "unsupported-media-type":
    case "rate-limited":
      return { kind: "rejected", request };
    case "forbidden":
      return { kind: "forbidden", request };
    case "not-found":
      return { kind: "missing", request };
    // El cliente ya cierra la sesión del navegador ante un 401 (ADR-0020).
    case "unauthorized":
      return { kind: "idle" };
    case "network":
    case "timeout":
      return { kind: "unknown", request, reason: "silent" };
    default:
      return { kind: "unknown", request, reason: "server" };
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
  // Una orden rechazada mientras dura un aviso que no se puede perder (un 409, por ejemplo).
  const [refusal, setRefusal] = useState<{ message: string; nonce: number } | null>(null);
  // Último estado que se sabe que tiene el servidor: hasta que la vista lo muestre no se edita.
  const [knownSeq, setKnownSeq] = useState<number | null>(null);
  const inFlight = useRef(false);
  // Una edición guardada cuyo estado nuevo no se pudo cargar: qué deja elegido, para la recarga.
  const pendingPlacement = useRef<{ request: EditRequest; seq: number } | null>(null);
  const nonce = useRef(0);
  const controllerRef = useRef<AbortController | null>(null);
  useEffect(
    () => () => {
      controllerRef.current?.abort();
    },
    [],
  );

  const detailKey = sessionDetailQuery(api, sessionId).queryKey;

  /**
   * Tras guardar una inserción o un borrado, elige el evento que dice la edición en el estado
   * `seq` que acaba de crear (ADR-0033), si sigue elegido el evento sobre el que se dio la orden:
   * lo que la persona eligiera mientras se guardaba se respeta. Lo demás lo lleva la vista.
   */
  function place(request: EditRequest, seq: number) {
    if (request.select === undefined) return;
    const { selection, select, clear } = useSelectionStore.getState();
    if (
      selection?.sessionId !== sessionId ||
      selection.seq !== request.baseSeq ||
      anchorKey(selection.anchor) !== anchorKey(request.target)
    ) {
      return;
    }
    if (request.select === null) clear();
    else select({ sessionId, seq, anchor: request.select, placedBy: seq });
  }

  /**
   * Carga el estado actual del servidor con todo lo que la vista pide de él, y lo muestra.
   * `beforeShow` se hace justo antes de mostrarlo, en el mismo paso.
   */
  async function refresh(signal: AbortSignal, beforeShow?: () => void) {
    const fresh = await fetchSessionDetail(api, sessionId, signal);
    const seq = fresh.current_seq ?? 0;
    // Si algo no llega, no se deja de mostrar el estado: la vista lo pide y lo dice como siempre.
    const ignore = () => undefined;
    await Promise.all([
      queryClient.query(sessionMusicXmlQuery(api, sessionId, seq)).catch(ignore),
      queryClient.query(sessionFindingsQuery(api, sessionId, seq)).catch(ignore),
      queryClient.query(sessionTimingQuery(api, sessionId, seq)).catch(ignore),
    ]);
    // Una recarga del detalle que siguiera en curso (al recuperar la red, por ejemplo) traería
    // un estado anterior y lo pondría encima de este.
    await queryClient.cancelQueries({ queryKey: detailKey });
    if (signal.aborted) return null;
    setKnownSeq(seq);
    beforeShow?.();
    queryClient.setQueryData(detailKey, fresh);
    return fresh;
  }

  /** Una sola petición a la vez: la siguiente se construiría sobre un estado que va a cambiar. */
  function begin() {
    if (inFlight.current) return null;
    inFlight.current = true;
    setRefusal(null);
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
      let saved: number;
      try {
        const edit = await postEdit(
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
        saved = edit.seq;
      } catch (error) {
        if (cancelled()) return;
        if (!(error instanceof ApiError && error.kind === "conflict")) {
          const next = failure(error, request);
          if (next) setStatus(next);
          // La sesión ya no está: la vista lo dice al volver a pedirla.
          if (next?.kind === "missing") void queryClient.invalidateQueries({ queryKey: detailKey });
          return;
        }
        // 409: o se editó antes en otra parte o la sesión está cerrada. Lo dice el estado recargado.
        const fresh = await refresh(signal).catch(() => null);
        if (cancelled()) return;
        if (!fresh) setStatus({ kind: "outdated", request });
        else setStatus({ kind: fresh.status === "finalized" ? "closed" : "conflict", request });
        return;
      }
      const fresh = await refresh(signal, () => {
        place(request, saved);
      }).catch(() => null);
      if (cancelled()) return;
      if (!fresh) pendingPlacement.current = { request, seq: saved };
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
      // Si se guardó una edición sin poder mostrar su estado, la recarga deja elegido lo que ella dejaba.
      const fresh = await refresh(controller.signal, () => {
        const pending = pendingPlacement.current;
        pendingPlacement.current = null;
        if (pending) place(pending.request, pending.seq);
      }).catch(() => null);
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
    const plan = planCommand(command, target, score);
    if (plan.kind === "refused") {
      nonce.current += 1;
      const refused = { message: plan.message, nonce: nonce.current };
      if (LASTING.has(status.kind)) setRefusal(refused);
      else setStatus({ kind: "refused", ...refused });
      return;
    }
    if (!target) return;
    void send(requestOf(plan, target.anchor, seq));
  }

  /**
   * Tras un 409, la misma edición sobre el estado recargado, si el ancla sigue designando el
   * mismo evento (o el mismo compás, la clave y la armadura) y no tiene ya ese valor. Solo se
   * envía si la persona lo pide.
   */
  const retry: { plan: EditPlan; anchor: AnchorPayload | null } | null =
    status.kind === "conflict" && detail && score ? replan(status.request, detail) : null;

  function reapply() {
    if (blocked || retry?.plan.kind !== "edit" || !retry.anchor) return;
    // El evento elegido, llevado al estado recargado: en un acorde no es el ancla de la inserción,
    // y es el que tiene que seguir elegido para que la edición deje elegido el evento nuevo.
    const chosen =
      status.kind === "conflict" && detail
        ? carryAnchor(status.request.target, status.request.baseSeq, detail)
        : null;
    void send(requestOf(retry.plan, chosen ?? retry.anchor, seq));
  }

  return { status, refusal, blocked, run, reload, retry, reapply };
}

export type Editor = ReturnType<typeof useEditor>;
