/**
 * Marcas de rendimiento de una orden de la vista (#275): cuándo se envía, cuándo llega la respuesta
 * y cuándo está dibujado el estado que crea. Quedan en `performance` (las herramientas del
 * navegador las muestran) con estos nombres:
 *
 * - `cadenza:orden-N:enviar`, con el tipo de orden, su `base_seq` y su `X-Request-ID`;
 * - `cadenza:orden-N:recibir`, con el `seq` del estado nuevo, y la medida `cadenza:orden-N:servidor`;
 * - `cadenza:orden-N:dibujado` y la medida `cadenza:orden-N`, del envío al dibujo.
 *
 * Si el navegador no tiene la API de rendimiento, no se mide nada y la vista sigue igual.
 */

const PREFIX = "cadenza:orden-";
let counter = 0;
/** Órdenes recibidas cuyo estado aún no está dibujado: `sesión:seq` → nombre de la orden. */
const awaitingDraw = new Map<string, string>();
/** Como mucho, las órdenes de las últimas sesiones: un estado que no se dibuja no se queda. */
const MAX_AWAITING = 16;
const stateKey = (sessionId: string, seq: number) => `${sessionId}:${String(seq)}`;

function mark(name: string, detail?: unknown): boolean {
  try {
    if (typeof performance === "undefined" || typeof performance.mark !== "function") return false;
    performance.mark(name, { detail });
    return true;
  } catch {
    return false;
  }
}

function measure(name: string, start: string, end: string) {
  try {
    if (typeof performance.measure === "function") performance.measure(name, start, end);
  } catch {
    // Una marca que el navegador ya descartó: no hay medida.
  }
}

/** Marca el envío de una orden y devuelve su nombre, para las marcas siguientes. */
export function markSent(kind: string, baseSeq: number, requestId: string): string {
  counter += 1;
  const order = `${PREFIX}${String(counter)}`;
  mark(`${order}:enviar`, { kind, baseSeq, requestId });
  return order;
}

/** Marca la respuesta de la orden, que crea el estado `seq` de la sesión. */
export function markReceived(order: string, sessionId: string, seq: number) {
  if (!mark(`${order}:recibir`, { seq })) return;
  measure(`${order}:servidor`, `${order}:enviar`, `${order}:recibir`);
  awaitingDraw.set(stateKey(sessionId, seq), order);
  for (const key of awaitingDraw.keys()) {
    if (awaitingDraw.size <= MAX_AWAITING) break;
    awaitingDraw.delete(key);
  }
}

/** Marca que el estado `seq` de la sesión está dibujado y, si lo creó una orden, la mide entera. */
export function markDrawn(sessionId: string, seq: number) {
  const key = stateKey(sessionId, seq);
  const order = awaitingDraw.get(key);
  if (order === undefined) return;
  awaitingDraw.delete(key);
  if (!mark(`${order}:dibujado`, { seq })) return;
  measure(order, `${order}:enviar`, `${order}:dibujado`);
}

/**
 * Etapa del dibujo de un estado (#276): leer el MusicXML (analizarlo y cargarlo en OSMD), dibujarlo
 * y construir el mapa de notas (ADR-0027).
 */
export type DrawStage = "leer" | "dibujar" | "mapa";

/**
 * Hace `run` y mide cuánto tarda como `cadenza:dibujo:<etapa>`, con la sesión y el `seq` del estado
 * en su `detail`. Si `run` falla, se mide igual y el error sigue su camino.
 */
export function timeStage<T>(stage: DrawStage, sessionId: string, seq: number, run: () => T): T {
  const clock = typeof performance === "undefined" ? null : performance;
  const start = clock?.now() ?? 0;
  try {
    return run();
  } finally {
    try {
      clock?.measure(`cadenza:dibujo:${stage}`, {
        start,
        end: clock.now(),
        detail: { sessionId, seq },
      });
    } catch {
      // Sin la API de rendimiento (o sin medidas con opciones) no se mide nada.
    }
  }
}
