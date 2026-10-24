import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ApiClient } from "../../api/client";
import { ApiError } from "../../api/errors";
import type { AnchorPayload, EditEventRead, SessionDetailRead } from "../../types";
import {
  carryAnchor,
  planCommand,
  replan,
  type EditCommand,
  type EditPlan,
  type EditRequestLike,
  type EditTarget,
} from "./edits";
import { describeEdit, historyPlacement, inverseOf, readLog } from "./history";
import { anchorKey } from "./noteMap";
import { useSelectionStore } from "./selection";
import {
  fetchSessionDetail,
  postEdit,
  postUndo,
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

/**
 * Deshacer o rehacer una edición del log (#185, ADR-0034), sobre el estado `baseSeq`. Su
 * operación y su ancla son las de esa edición: dicen dónde está lo que cambia.
 */
export interface HistoryRequest {
  kind: "undo" | "redo";
  /** La edición del log que se deshace, o la deshecha que se vuelve a enviar. */
  edit: EditEventRead;
  /** Qué hace esa edición, para decirlo: «altura Re 4». */
  change: string;
  op: string;
  anchor: AnchorPayload;
  baseSeq: number;
  /**
   * Evento que queda elegido en el estado siguiente, o null si ninguno; sin él, la selección
   * sigue en su evento.
   */
  select?: AnchorPayload | null;
  /** Nota elegida al dar la orden (su clave), o null: si cambia mientras tanto, se respeta. */
  chosen: string | null;
}

/** Una orden enviada: una edición, deshacer o rehacer. */
export type EditorRequest = EditRequest | HistoryRequest;

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
  | { kind: "saving"; request: EditorRequest }
  | { kind: "saved"; request: EditorRequest }
  /** Una orden que no se envió (no se puede sobre esa nota); `nonce` distingue repeticiones. */
  | { kind: "refused"; message: string; nonce: number }
  /** 409 porque otra pestaña o dispositivo editó antes: ya se recargó. */
  | { kind: "conflict"; request: EditorRequest }
  /** 409 porque la sesión está finalizada (ADR-0014): ya se recargó. */
  | { kind: "closed"; request: EditorRequest }
  /** 409, pero no se pudo cargar el estado actual. */
  | { kind: "outdated"; request: EditorRequest }
  /** 422 (u otro rechazo del servidor): no se guardó nada. */
  | { kind: "rejected"; request: EditorRequest }
  /** 403: la sesión no es de quien la ve (ADR-0012). */
  | { kind: "forbidden"; request: EditorRequest }
  /** 404: la sesión ya no existe o no se tiene acceso. */
  | { kind: "missing"; request: EditorRequest }
  /**
   * No se sabe si se guardó: sin respuesta (`silent`: red, tiempo agotado) o con una respuesta
   * que no lo confirma (`server`: 5xx, respuesta inesperada).
   */
  | { kind: "unknown"; request: EditorRequest; reason: "silent" | "server" }
  /** 201 (o 200 al deshacer), pero no se pudo cargar el estado nuevo. */
  | { kind: "unsynced"; request: EditorRequest }
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

/** Qué pasó según el error de una orden que no es un 409, o null si no hay nada que decir. */
function failure(
  error: unknown,
  request: EditorRequest,
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

/** Lo que responde el servidor a una orden: el `seq` del estado que crea y, si lo cambia, qué se hizo. */
interface Outcome {
  seq: number;
  request?: EditorRequest;
}

/**
 * Corrección de la nota elegida (#183, ADR-0030), y deshacer y rehacer (#185, ADR-0034). Cada orden
 * es una edición con el `base_seq` del estado que se ve; nada se da por guardado sin el 201 (o el
 * 200 de `POST /undo`). Tras él, o tras un 409, se pide el detalle de la sesión y, antes de
 * mostrarlo, el MusicXML, los posibles errores y los tiempos de ese estado: la vista pasa de un
 * estado al otro de una vez. Un 409 nunca se reintenta solo.
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
  // Una orden guardada cuyo estado nuevo no se pudo cargar: qué deja elegido, para la recarga.
  const pendingPlacement = useRef<{ request: EditorRequest; seq: number } | null>(null);
  const nonce = useRef(0);
  const controllerRef = useRef<AbortController | null>(null);
  useEffect(
    () => () => {
      controllerRef.current?.abort();
    },
    [],
  );

  const detailKey = sessionDetailQuery(api, sessionId).queryKey;
  // Qué se desharía y qué se rehará, leído del log del estado que se ve.
  const edits = detail?.edits;
  const log = useMemo(() => readLog(edits ?? []), [edits]);

  /** La nota elegida en el estado `at` (su clave), o null si no hay ninguna de ese estado. */
  function chosenAt(at: number): string | null {
    const { selection } = useSelectionStore.getState();
    return selection?.sessionId === sessionId && selection.seq === at
      ? anchorKey(selection.anchor)
      : null;
  }

  /**
   * Tras guardar una orden, elige el evento que dice en el estado `seq` que acaba de crear
   * (ADR-0033, ADR-0034), si la selección sigue donde estaba al darla: lo que la persona eligiera
   * mientras se guardaba se respeta. Lo demás lo lleva la vista.
   */
  function place(request: EditorRequest, seq: number) {
    if (request.select === undefined) return;
    const { selection, select, clear } = useSelectionStore.getState();
    if (request.kind === "edit") {
      if (
        selection?.sessionId !== sessionId ||
        selection.seq !== request.baseSeq ||
        anchorKey(selection.anchor) !== anchorKey(request.target)
      ) {
        return;
      }
    } else if (chosenAt(request.baseSeq) !== request.chosen) {
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

  /** Envía una orden con `post` y, con su respuesta, pasa al estado nuevo. */
  async function submit(request: EditorRequest, post: (signal: AbortSignal) => Promise<Outcome>) {
    const controller = begin();
    if (!controller) return;
    const { signal } = controller;
    // Función y no propiedad: TypeScript no sabe que la señal puede cambiar durante un await.
    const cancelled = () => signal.aborted;
    setStatus({ kind: "saving", request });
    try {
      let outcome: Outcome;
      try {
        outcome = await post(signal);
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
      const done = outcome.request ?? request;
      const saved = outcome.seq;
      const fresh = await refresh(signal, () => {
        place(done, saved);
      }).catch(() => null);
      if (cancelled()) return;
      if (!fresh) pendingPlacement.current = { request: done, seq: saved };
      setStatus(fresh ? { kind: "saved", request: done } : { kind: "unsynced", request: done });
    } finally {
      inFlight.current = false;
    }
  }

  function send(request: EditRequest) {
    return submit(request, async (signal) => {
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
      return { seq: edit.seq };
    });
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

  /** Dice por qué una orden no sale, sin borrar un aviso que hay que conservar. */
  function refuse(message: string) {
    nonce.current += 1;
    const refused = { message, nonce: nonce.current };
    if (LASTING.has(status.kind)) setRefusal(refused);
    else setStatus({ kind: "refused", ...refused });
  }

  /** Una orden sobre el evento elegido: se envía o se dice por qué no. */
  function run(command: EditCommand, target: EditTarget | null) {
    if (blocked || !score) return;
    const plan = planCommand(command, target, score);
    if (plan.kind === "refused") {
      refuse(plan.message);
      return;
    }
    if (!target) return;
    void send(requestOf(plan, target.anchor, seq));
  }

  /**
   * Deshacer o rehacer `edit` aplicando `applied` (la compensatoria o la misma edición) sobre el
   * estado que se ve: con qué se dice y qué queda elegido. Un cambio de valor del evento ya
   * elegido no lo vuelve a elegir, como al corregirlo (ADR-0030 §10).
   */
  function historyRequest(
    kind: HistoryRequest["kind"],
    edit: EditEventRead,
    applied: Pick<EditEventRead, "op" | "anchor" | "after">,
  ): HistoryRequest | null {
    if (!score) return null;
    const chosen = chosenAt(seq);
    const placement = historyPlacement(applied, score);
    const moves = applied.op === "InsertEvent" || applied.op === "DeleteEvent";
    return {
      kind,
      edit,
      change: describeEdit(edit),
      op: edit.op,
      anchor: edit.anchor,
      baseSeq: seq,
      chosen,
      select: placement && !moves && anchorKey(placement) === chosen ? undefined : placement,
    };
  }

  /**
   * Deshace en el servidor la última edición vigente (`POST /undo`, ADR-0007): el log la compensa
   * con otra, nunca la borra. Sin nada que deshacer, lo dice.
   */
  function undo() {
    if (blocked || !detail) return;
    const edit = log.undo;
    if (!edit) {
      refuse("Nada que deshacer.");
      return;
    }
    const request = historyRequest("undo", edit, inverseOf(edit));
    if (!request) return;
    const { edits: before } = detail;
    void submit(request, async (signal) => {
      const result = await postUndo(api, sessionId, { base_seq: request.baseSeq }, signal);
      if (result.undone_edit_id === edit.id) return { seq: result.current_seq };
      // El servidor deshizo otra: se dice esa y la selección no se mueve.
      const undone = before.find((candidate) => candidate.id === result.undone_edit_id);
      const unplaced = { ...request, select: undefined };
      return {
        seq: result.current_seq,
        request: undone
          ? {
              ...unplaced,
              edit: undone,
              change: describeEdit(undone),
              op: undone.op,
              anchor: undone.anchor,
            }
          : unplaced,
      };
    });
  }

  /**
   * Rehace la última edición deshecha: la vuelve a enviar igual (su operación, su ancla y su
   * valor), como edición nueva y con el `base_seq` del estado que se ve. Tras deshacerla, el
   * estado es el previo a ella y su ancla vuelve a valer (ADR-0011). Sin nada que rehacer, lo dice.
   */
  function redo() {
    if (blocked || !detail) return;
    const edit = log.redo;
    if (!edit) {
      refuse("Nada que rehacer.");
      return;
    }
    const request = historyRequest("redo", edit, edit);
    if (!request) return;
    void submit(request, async (signal) => {
      const saved = await postEdit(
        api,
        sessionId,
        {
          base_seq: request.baseSeq,
          op: edit.op,
          anchor: edit.anchor,
          before: null,
          after: edit.after,
        },
        signal,
      );
      return { seq: saved.seq };
    });
  }

  /**
   * Tras un 409, la misma edición sobre el estado recargado, si el ancla sigue designando el
   * mismo evento (o el mismo compás, la clave y la armadura) y no tiene ya ese valor. Solo se
   * envía si la persona lo pide. Deshacer y rehacer no se vuelven a aplicar: sobre el estado
   * recargado serían otra orden, que se da con sus propios controles.
   */
  const conflicted =
    status.kind === "conflict" && status.request.kind === "edit" ? status.request : null;
  const retry: { plan: EditPlan; anchor: AnchorPayload | null } | null =
    conflicted && detail && score ? replan(conflicted, detail) : null;

  function reapply() {
    if (blocked || retry?.plan.kind !== "edit" || !retry.anchor || !conflicted || !detail) return;
    // El evento elegido, llevado al estado recargado: en un acorde no es el ancla de la inserción,
    // y es el que tiene que seguir elegido para que la edición deje elegido el evento nuevo.
    const chosen = carryAnchor(conflicted.target, conflicted.baseSeq, detail);
    void send(requestOf(retry.plan, chosen ?? retry.anchor, seq));
  }

  return { status, refusal, blocked, run, reload, retry, reapply, log, undo, redo };
}

export type Editor = ReturnType<typeof useEditor>;
