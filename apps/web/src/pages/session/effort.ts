import { useEffect, useState } from "react";
import type { ApiClient } from "../../api/client";
import { ApiError } from "../../api/errors";
import { EFFORT_IDLE_THRESHOLD_MS } from "../../config";
import type { EffortMetricsRead, EffortSegmentUpdate } from "../../types";
import { EffortClock } from "./effortClock";

/** Cada cuánto se guarda lo medido en la pestaña y, si cambió, se envía. */
export const EFFORT_FLUSH_INTERVAL_MS = 10_000;

/** Lo que cuenta como actividad: teclado, ratón y toque (protocolo §3.4). */
const ACTIVITY_EVENTS = ["keydown", "pointerdown", "pointermove", "wheel", "touchstart"] as const;

const STORAGE_PREFIX = "cadenza:effort:";

/**
 * `PUT /sessions/{id}/effort/segments/{segment_id}`: lo que midió esta pestaña hasta ahora. El
 * servidor suma los tramos en el registro de la sesión y solo los deja crecer (ADR-0050).
 */
export function putEffortSegment(
  api: ApiClient,
  sessionId: string,
  segmentId: string,
  body: EffortSegmentUpdate,
  keepalive = false,
): Promise<EffortMetricsRead> {
  return api.request<EffortMetricsRead>(
    `/sessions/${encodeURIComponent(sessionId)}/effort/segments/${encodeURIComponent(segmentId)}`,
    { method: "PUT", json: body, keepalive },
  );
}

/** Un tramo: lo que mide una pestaña, que sigue tras sus recargas (`sessionStorage`). */
interface Segment {
  id: string;
  activeMs: number;
  firstEditMs: number | null;
}

/** Un identificador de tramo: 32 cifras hexadecimales, la forma que acepta la API. */
function newSegmentId(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

const isCount = (value: unknown): value is number =>
  typeof value === "number" && Number.isInteger(value) && value >= 0;

function loadSegment(sessionId: string): Segment {
  try {
    const raw = sessionStorage.getItem(STORAGE_PREFIX + sessionId);
    if (raw) {
      const stored = JSON.parse(raw) as Partial<Segment>;
      if (
        typeof stored.id === "string" &&
        /^[0-9a-f]{32}$/.test(stored.id) &&
        isCount(stored.activeMs) &&
        (stored.firstEditMs === null ||
          (isCount(stored.firstEditMs) && stored.firstEditMs <= stored.activeMs))
      ) {
        return { id: stored.id, activeMs: stored.activeMs, firstEditMs: stored.firstEditMs };
      }
    }
  } catch {
    // Sin `sessionStorage` (o con algo ilegible), cada carga es un tramo nuevo: el servidor los
    // suma igual; solo se pierde lo que no llegó a enviarse.
  }
  return { id: newSegmentId(), activeMs: 0, firstEditMs: null };
}

function storeSegment(sessionId: string, segment: Segment) {
  try {
    sessionStorage.setItem(STORAGE_PREFIX + sessionId, JSON.stringify(segment));
  } catch {
    // Igual que al leer: sin dónde guardarlo, lo que cuenta es lo enviado.
  }
}

/**
 * Cómo acabó un envío: `saved`, guardado; `refused`, el servidor lo rechazó (la sesión ya está
 * finalizada, no existe o no es tuya: lo dice la orden que venga después); `failed`, sin
 * respuesta que lo confirme.
 */
export type EffortSendResult = "saved" | "refused" | "failed";

type Send = (segmentId: string, body: EffortSegmentUpdate, keepalive: boolean) => Promise<unknown>;

interface MeterOptions {
  sessionId: string;
  send: Send;
  idleMs?: number;
  now?: () => number;
}

/**
 * La medición del esfuerzo de una sesión en esta pestaña (#188, ADR-0050, protocolo §3.4).
 * Cuenta mientras se mide (quien la transcribió, con la sesión abierta), la página está
 * visible y no se está finalizando; guarda su tramo en `sessionStorage` para seguir tras una
 * recarga y lo envía cada `EFFORT_FLUSH_INTERVAL_MS` si cambió, al ocultar o dejar la página,
 * al guardarse la primera edición y antes de finalizar.
 */
export class EffortMeter {
  readonly idleMs: number;
  private readonly segment: Segment;
  private readonly clock: EffortClock;
  private readonly now: () => number;
  private readonly send: Send;
  private readonly sessionId: string;
  private measuring = false;
  private visible = false;
  private attached = false;
  private held = false;
  /**
   * El servidor rechazó el tramo (la sesión se finalizó en otra parte, ya no existe o no es
   * tuya): no se vuelve a enviar hasta que se vuelva a medir.
   */
  private closed = false;
  /** Lo último que el servidor confirmó. */
  private sent: EffortSegmentUpdate | null = null;
  private inFlight: Promise<EffortSendResult> | null = null;

  constructor({ sessionId, send, idleMs = EFFORT_IDLE_THRESHOLD_MS, now }: MeterOptions) {
    this.sessionId = sessionId;
    this.send = send;
    this.idleMs = idleMs;
    this.now = now ?? (() => performance.now());
    this.segment = loadSegment(sessionId);
    this.clock = new EffortClock(idleMs, this.segment.activeMs);
  }

  /** La pestaña empieza a escuchar (`visible`: si la página se ve ahora). */
  attach(visible: boolean): void {
    this.attached = true;
    this.visible = visible;
    this.sync();
  }

  /** La vista se desmonta o la página se va: lo medido se guarda y se envía sin esperar. */
  detach(): void {
    this.attached = false;
    this.sync();
    this.leave();
  }

  /** Si se mide: quien la transcribió, con la sesión abierta. Al reabrir se vuelve a medir. */
  setMeasuring(measuring: boolean): void {
    if (measuring === this.measuring) return;
    this.measuring = measuring;
    // Una finalización que acabó (o que la vista supo por otra vía) ya no espera.
    this.held = false;
    this.closed = false;
    this.sync();
    if (measuring) void this.flush();
  }

  setVisible(visible: boolean): void {
    this.visible = visible;
    this.sync();
    if (!visible) this.leave();
  }

  /** Una tecla, el ratón o un toque. */
  activity(): void {
    this.clock.activity(this.now());
  }

  /** Se guardó una edición que dejó el log en `seq`: si es la primera (seq 1), se apunta cuándo. */
  saved(seq: number): void {
    if (seq !== 1 || !this.measuring || this.segment.firstEditMs !== null) return;
    this.segment.firstEditMs = Math.floor(this.clock.read(this.now()));
    this.persist();
    void this.flush();
  }

  /** El tiempo medido en esta pestaña hasta ahora. */
  activeMs(): number {
    return Math.floor(this.clock.read(this.now()));
  }

  /** Antes de finalizar: el reloj se para y se envía lo medido hasta aquí. */
  async finish(): Promise<EffortSendResult> {
    this.held = true;
    this.sync();
    this.persist();
    if (!this.measuring) return "saved";
    return this.flush();
  }

  /** La finalización no se hizo: se sigue midiendo. */
  resume(): void {
    this.held = false;
    this.sync();
  }

  /** Guarda en la pestaña y, si se mide y cambió algo, lo envía (de uno en uno). */
  async flush(): Promise<EffortSendResult> {
    this.persist();
    while (this.inFlight) await this.inFlight;
    if (!this.measuring && !this.held) return "saved";
    if (this.closed) return "refused";
    const body = this.body();
    if (this.sent && sameBody(this.sent, body)) return "saved";
    const sending = this.deliver(body, false);
    this.inFlight = sending;
    try {
      return await sending;
    } finally {
      this.inFlight = null;
    }
  }

  private async deliver(body: EffortSegmentUpdate, keepalive: boolean): Promise<EffortSendResult> {
    try {
      await this.send(this.segment.id, body, keepalive);
      if (!this.sent || body.active_ms >= this.sent.active_ms) this.sent = body;
      return "saved";
    } catch (error) {
      const kind = error instanceof ApiError ? error.kind : "unexpected";
      if (UNCONFIRMED.has(kind)) return "failed";
      // La sesión se finalizó en otra parte (o ya no es tuya): lo que viene no es corrección.
      this.closed = true;
      this.sync();
      return "refused";
    }
  }

  /** Al ocultar o dejar la página: se guarda y se envía con `keepalive`, sin esperar turno. */
  private leave() {
    this.persist();
    if (!this.measuring || this.closed) return;
    const body = this.body();
    if (this.sent && sameBody(this.sent, body)) return;
    void this.deliver(body, true);
  }

  private body(): EffortSegmentUpdate {
    return {
      active_ms: this.activeMs(),
      first_edit_ms: this.segment.firstEditMs,
      idle_threshold_ms: this.idleMs,
    };
  }

  private persist() {
    this.segment.activeMs = this.activeMs();
    storeSegment(this.sessionId, this.segment);
  }

  private sync() {
    const counting = this.attached && this.measuring && this.visible && !this.held && !this.closed;
    const t = this.now();
    if (counting) this.clock.start(t);
    else this.clock.stop(t);
  }
}

/** Errores tras los que no se sabe si se guardó: se vuelve a enviar en el siguiente turno. */
const UNCONFIRMED = new Set([
  "network",
  "timeout",
  "server",
  "unexpected",
  "aborted",
  "rate-limited",
]);

const sameBody = (a: EffortSegmentUpdate, b: EffortSegmentUpdate) =>
  a.active_ms === b.active_ms &&
  a.first_edit_ms === b.first_edit_ms &&
  a.idle_threshold_ms === b.idle_threshold_ms;

/**
 * Mide el esfuerzo de la corrección en la vista de la sesión (#188): escucha la actividad, la
 * visibilidad y la salida de la página, y envía lo medido. `measuring`: quien la transcribió,
 * con la sesión cargada y abierta. Nada de esto se muestra a la persona.
 */
export function useEffortMeter(api: ApiClient, sessionId: string, measuring: boolean) {
  const [meter] = useState(
    () =>
      new EffortMeter({
        sessionId,
        send: (segmentId, body, keepalive) =>
          putEffortSegment(api, sessionId, segmentId, body, keepalive),
      }),
  );

  useEffect(() => {
    meter.setMeasuring(measuring);
  }, [meter, measuring]);

  useEffect(() => {
    const onActivity = () => {
      meter.activity();
    };
    const onVisibility = () => {
      meter.setVisible(document.visibilityState === "visible");
    };
    const onPageHide = () => {
      meter.setVisible(false);
    };
    const onPageShow = () => {
      meter.setVisible(document.visibilityState === "visible");
    };
    const options = { capture: true, passive: true } as const;
    for (const type of ACTIVITY_EVENTS) window.addEventListener(type, onActivity, options);
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", onPageHide);
    window.addEventListener("pageshow", onPageShow);
    meter.attach(document.visibilityState === "visible");
    const timer = window.setInterval(() => {
      void meter.flush();
    }, EFFORT_FLUSH_INTERVAL_MS);
    return () => {
      for (const type of ACTIVITY_EVENTS) window.removeEventListener(type, onActivity, options);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", onPageHide);
      window.removeEventListener("pageshow", onPageShow);
      window.clearInterval(timer);
      meter.detach();
    };
  }, [meter]);

  return meter;
}
