import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { newRequestId, type ApiClient } from "../../api/client";
import { ApiError } from "../../api/errors";
import type {
  AnchorPayload,
  EditAppliedRead,
  EditEventRead,
  FindingRead,
  ScoreIRPayload,
  SessionViewRead,
  TimingMapRead,
} from "../../types";
import {
  carryAnchor,
  eventAt,
  planCommand,
  replan,
  type EditCommand,
  type EditPlan,
  type EditRequestLike,
  type EditTarget,
} from "./edits";
import { describeEdit, historyPlacement, inverseOf, readLog } from "./history";
import { markReceived, markSent } from "./marks";
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

/**
 * Orden que llega mientras se guarda otra (#276, ADR-0038): espera, y al guardarse la anterior se
 * vuelve a planear sobre el estado nuevo (con la nota elegida entonces) y sale con su `base_seq`.
 */
export type QueuedOrder =
  { kind: "command"; command: EditCommand } | { kind: "undo" } | { kind: "redo" };

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

/**
 * El estado que crea una orden, tal como lo devuelve el servidor con ella (#275, ADR-0037): la
 * edición que entra en el log, la partitura, el MusicXML (null si no se pudo exportar) y el mapa
 * de tiempos (null si no cambia).
 */
interface NewState {
  seq: number;
  edit: EditEventRead;
  score: ScoreIRPayload;
  status: string;
  musicxml: string | null;
  timing: TimingMapRead | null;
}

/**
 * Lo que responde el servidor a una orden: el `seq` del estado que crea, ese estado (null si la
 * respuesta no lo trae entero: entonces se pide, como antes de #275) y, si lo cambia, qué se hizo.
 */
interface Outcome {
  seq: number;
  state: NewState | null;
  request?: EditorRequest;
}

/** Si la respuesta trae el estado nuevo entero; un servidor anterior a #275 no lo trae. */
const carriesState = (body: object) =>
  ["current_score", "status", "musicxml", "timing"].every((key) => key in body);

/** El resultado del 201 de una edición: la edición, sin el estado, es la que entra en el log. */
function outcomeOfEdit(applied: EditAppliedRead): Outcome {
  const { current_seq, current_score, status, musicxml, timing, ...edit } = applied;
  const state = carriesState(applied)
    ? { seq: current_seq, edit, score: current_score, status, musicxml, timing }
    : null;
  return { seq: applied.seq, state };
}

/**
 * Corrección de la nota elegida (#183, ADR-0030), y deshacer y rehacer (#185, ADR-0034). Cada orden
 * es una edición con el `base_seq` del estado que se ve; nada se da por guardado sin el 201 (o el
 * 200 de `POST /undo`). Con él llega el estado nuevo (#275, ADR-0037): la partitura, el MusicXML y
 * los tiempos si cambian; los posibles errores no cambian sin revalidar. La vista pasa a él de una
 * vez, sin pedir nada más. Tras un 409 se recarga todo: el detalle de la sesión y, antes de
 * mostrarlo, el MusicXML, los posibles errores y los tiempos de ese estado. Un 409 nunca se
 * reintenta solo. Con `held`, las órdenes esperan: se está revalidando y una edición cambiaría el
 * estado validado (ADR-0035).
 */
export function useEditor(
  api: ApiClient,
  sessionId: string,
  detail: SessionViewRead | undefined,
  held = false,
) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<EditorStatus>({ kind: "idle" });
  // Una orden rechazada mientras dura un aviso que no se puede perder (un 409, por ejemplo).
  const [refusal, setRefusal] = useState<{ message: string; nonce: number } | null>(null);
  // Último estado que se sabe que tiene el servidor: hasta que la vista lo muestre no se edita.
  const [knownSeq, setKnownSeq] = useState<number | null>(null);
  const inFlight = useRef(false);
  // Como mucho una orden espera a que se guarde la que está en curso (ADR-0038).
  const [queued, setQueued] = useState<QueuedOrder | null>(null);
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

  /**
   * Muestra el estado que devolvió el servidor con la orden, compuesto sobre el que se ve (el de
   * `baseSeq`): su log más la edición nueva, su partitura, su MusicXML y sus tiempos, y los mismos
   * posibles errores. Solo pide lo que no trae: el MusicXML si no se pudo exportar (la vista dirá
   * el error) y los tiempos si no cambian y no se tenían. Si lo que se ve ya no es `baseSeq`, se
   * recarga entero.
   */
  async function show(
    state: NewState,
    baseSeq: number,
    signal: AbortSignal,
    beforeShow?: () => void,
  ) {
    const previous = queryClient.getQueryData<SessionViewRead>(detailKey);
    if (!previous || (previous.current_seq ?? 0) !== baseSeq) return refresh(signal, beforeShow);
    const ignore = () => undefined;
    const musicXmlKey = sessionMusicXmlQuery(api, sessionId, state.seq).queryKey;
    if (state.musicxml !== null) queryClient.setQueryData(musicXmlKey, state.musicxml);
    else await queryClient.query(sessionMusicXmlQuery(api, sessionId, state.seq)).catch(ignore);
    const timing =
      state.timing ??
      queryClient.getQueryData<TimingMapRead>(sessionTimingQuery(api, sessionId, baseSeq).queryKey);
    if (timing) {
      queryClient.setQueryData(sessionTimingQuery(api, sessionId, state.seq).queryKey, timing);
    } else {
      await queryClient.query(sessionTimingQuery(api, sessionId, state.seq)).catch(ignore);
    }
    // Sin revalidar, los posibles errores son los mismos (ADR-0035): no se vuelven a pedir.
    const findings = queryClient.getQueryData<FindingRead[]>(
      sessionFindingsQuery(api, sessionId, baseSeq).queryKey,
    );
    if (findings) {
      queryClient.setQueryData(sessionFindingsQuery(api, sessionId, state.seq).queryKey, findings);
    }
    // Una recarga del detalle que siguiera en curso traería un estado anterior.
    await queryClient.cancelQueries({ queryKey: detailKey, exact: true });
    if (signal.aborted) return null;
    // Mientras tanto pudo llegar un estado posterior (de otra pestaña): no se vuelve atrás.
    const latest = queryClient.getQueryData<SessionViewRead>(detailKey);
    if (latest && (latest.current_seq ?? 0) > state.seq) {
      setKnownSeq(latest.current_seq ?? 0);
      return latest;
    }
    const fresh: SessionViewRead = {
      ...previous,
      current_seq: state.seq,
      current_score: state.score,
      status: state.status,
      edits: [...previous.edits, state.edit],
    };
    setKnownSeq(state.seq);
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

  /**
   * Envía una orden con `post` y, con su respuesta, pasa al estado nuevo. `post` recibe el
   * `X-Request-ID` de la petición, que va también en las marcas de rendimiento (#275).
   */
  async function submit(
    request: EditorRequest,
    post: (signal: AbortSignal, requestId: string) => Promise<Outcome>,
  ) {
    const controller = begin();
    if (!controller) return;
    const { signal } = controller;
    // Función y no propiedad: TypeScript no sabe que la señal puede cambiar durante un await.
    const cancelled = () => signal.aborted;
    setStatus({ kind: "saving", request });
    const requestId = newRequestId();
    const order = markSent(request.kind, request.baseSeq, requestId);
    try {
      let outcome: Outcome;
      try {
        outcome = await post(signal, requestId);
        markReceived(order, sessionId, outcome.seq);
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
      const placeSaved = () => {
        place(done, saved);
      };
      const fresh = await (
        outcome.state
          ? show(outcome.state, request.baseSeq, signal, placeSaved)
          : refresh(signal, placeSaved)
      ).catch(() => null);
      if (cancelled()) return;
      if (!fresh) pendingPlacement.current = { request: done, seq: saved };
      setStatus(fresh ? { kind: "saved", request: done } : { kind: "unsynced", request: done });
    } finally {
      inFlight.current = false;
    }
  }

  function send(request: EditRequest) {
    return submit(request, async (signal, requestId) => {
      const applied = await postEdit(
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
        requestId,
      );
      return outcomeOfEdit(applied);
    });
  }

  /** Recarga el estado actual de la sesión y lo muestra; devuelve su `seq`, o null si no lo cargó. */
  async function reload(): Promise<number | null> {
    const controller = begin();
    if (!controller) return null;
    setStatus({ kind: "reloading" });
    try {
      // Si se guardó una edición sin poder mostrar su estado, la recarga deja elegido lo que ella dejaba.
      const fresh = await refresh(controller.signal, () => {
        const pending = pendingPlacement.current;
        pendingPlacement.current = null;
        if (pending) place(pending.request, pending.seq);
      }).catch(() => null);
      if (controller.signal.aborted) return null;
      setStatus({ kind: fresh ? "reloaded" : "reload-failed" });
      return fresh ? (fresh.current_seq ?? 0) : null;
    } finally {
      inFlight.current = false;
    }
  }

  const score = detail?.current_score ?? null;
  const seq = detail?.current_seq ?? 0;
  // El servidor ya tiene un estado que la vista aún no muestra.
  const lagging = knownSeq !== null && seq < knownSeq;
  /**
   * Se está guardando una orden (o mostrando el estado que creó): la siguiente espera su turno
   * (ADR-0038). Mientras se revalida, no: el editor espera a la revalidación (ADR-0035).
   */
  const waiting = !held && (status.kind === "saving" || (lagging && !BLOCKING.has(status.kind)));
  // Ahora no sale ninguna orden; si no es por estar esperando, los controles se ven inactivos.
  const stopped = held || BLOCKING.has(status.kind) || lagging;
  const blocked = stopped && !waiting;

  /** Dice por qué una orden no sale, sin borrar un aviso que hay que conservar. */
  function refuse(message: string) {
    nonce.current += 1;
    const refused = { message, nonce: nonce.current };
    if (LASTING.has(status.kind) || waiting) setRefusal(refused);
    else setStatus({ kind: "refused", ...refused });
  }

  /** Deja esperando una orden; si ya hay otra, no se envía y se dice (ADR-0038). */
  function enqueue(order: QueuedOrder) {
    if (queued) {
      refuse("Ya hay una orden esperando a que se guarde la anterior: esta no se envió.");
      return;
    }
    setQueued(order);
  }

  /** La nota elegida en el estado que se ve, como la daría la vista, o null. */
  function currentTarget(): EditTarget | null {
    const { selection } = useSelectionStore.getState();
    if (!score || selection?.sessionId !== sessionId || selection.seq !== seq) return null;
    const found = eventAt(score, selection.anchor);
    return found ? { anchor: selection.anchor, ...found } : null;
  }

  // Cuando se guarda la orden en curso y la vista muestra su estado, sale la que esperaba,
  // planeada de nuevo sobre él, en la tarea siguiente: el estado nuevo ya está pintado. Si la
  // anterior no se guardó, no sale: se dice (ADR-0038). Sin dependencias: cada render deja la
  // salida con lo que se ve en él.
  useEffect(() => {
    if (!queued || waiting) return;
    const timer = setTimeout(() => {
      setQueued(null);
      if (status.kind !== "saved" || stopped) {
        refuse("No se envió la orden que esperaba: la anterior no se guardó.");
        return;
      }
      if (queued.kind === "undo") undo();
      else if (queued.kind === "redo") redo();
      else run(queued.command, currentTarget());
    }, 0);
    return () => {
      clearTimeout(timer);
    };
  });

  /** Una orden sobre el evento elegido: se envía, espera su turno o se dice por qué no. */
  function run(command: EditCommand, target: EditTarget | null) {
    if (!score) return;
    if (waiting) {
      enqueue({ kind: "command", command });
      return;
    }
    if (stopped) return;
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
    if (!detail) return;
    if (waiting) {
      enqueue({ kind: "undo" });
      return;
    }
    if (stopped) return;
    const edit = log.undo;
    if (!edit) {
      refuse("Nada que deshacer.");
      return;
    }
    const request = historyRequest("undo", edit, inverseOf(edit));
    if (!request) return;
    const { edits: before } = detail;
    void submit(request, async (signal, requestId) => {
      const result = await postUndo(
        api,
        sessionId,
        { base_seq: request.baseSeq },
        signal,
        requestId,
      );
      // Sin la compensatoria no se puede componer el log nuevo: el estado se pide entero.
      const state: NewState | null =
        result.compensatory_edit && carriesState(result)
          ? {
              seq: result.current_seq,
              edit: result.compensatory_edit,
              score: result.current_score,
              status: result.status,
              musicxml: result.musicxml,
              timing: result.timing,
            }
          : null;
      const seq = result.current_seq;
      if (result.undone_edit_id === edit.id) return { seq, state };
      // El servidor deshizo otra: se dice esa y la selección no se mueve.
      const undone = before.find((candidate) => candidate.id === result.undone_edit_id);
      const unplaced = { ...request, select: undefined };
      return {
        seq,
        state,
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
    if (!detail) return;
    if (waiting) {
      enqueue({ kind: "redo" });
      return;
    }
    if (stopped) return;
    const edit = log.redo;
    if (!edit) {
      refuse("Nada que rehacer.");
      return;
    }
    const request = historyRequest("redo", edit, edit);
    if (!request) return;
    void submit(request, async (signal, requestId) => {
      const applied = await postEdit(
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
        requestId,
      );
      return outcomeOfEdit(applied);
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
    if (stopped || retry?.plan.kind !== "edit" || !retry.anchor || !conflicted || !detail) return;
    // El evento elegido, llevado al estado recargado: en un acorde no es el ancla de la inserción,
    // y es el que tiene que seguir elegido para que la edición deje elegido el evento nuevo.
    const chosen = carryAnchor(conflicted.target, conflicted.baseSeq, detail);
    void send(requestOf(retry.plan, chosen ?? retry.anchor, seq));
  }

  return {
    status,
    refusal,
    blocked,
    held,
    /** Si hay una orden esperando a que se guarde la que está en curso (ADR-0038). */
    queued: queued !== null,
    run,
    reload,
    retry,
    reapply,
    log,
    undo,
    redo,
  };
}

export type Editor = ReturnType<typeof useEditor>;
