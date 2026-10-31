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
/** Órdenes recibidas cuyo estado aún no está dibujado: `seq` → nombre de la orden. */
const awaitingDraw = new Map<number, string>();

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

/** Marca la respuesta de la orden, que crea el estado `seq`. */
export function markReceived(order: string, seq: number) {
  if (!mark(`${order}:recibir`, { seq })) return;
  measure(`${order}:servidor`, `${order}:enviar`, `${order}:recibir`);
  awaitingDraw.set(seq, order);
}

/** Marca que el estado `seq` está dibujado y, si lo creó una orden, mide la orden entera. */
export function markDrawn(seq: number) {
  const order = awaitingDraw.get(seq);
  if (order === undefined) return;
  awaitingDraw.delete(seq);
  if (!mark(`${order}:dibujado`, { seq })) return;
  measure(order, `${order}:enviar`, `${order}:dibujado`);
}
