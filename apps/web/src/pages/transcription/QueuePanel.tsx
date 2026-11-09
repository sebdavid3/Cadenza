import { useEffect, useRef, useSyncExternalStore } from "react";
import { Link } from "react-router";
import { findingsLabel, formatSize } from "./format";
import { useQueueStore, type QueueItem } from "./queue";
import { nonBlank } from "./scoreData";
import { QueueThumb } from "./SessionThumb";

/** El nombre que se dio a la partitura de una imagen, o null si no se dio ninguno. */
function titleOf(item: QueueItem): string | null {
  return nonBlank(item.data?.title);
}

/** Recuento de la región viva: lo pendiente, lo que está en curso, lo transcrito y lo fallido. */
function summary(items: QueueItem[]): string {
  const count = (status: QueueItem["status"]) =>
    items.filter((item) => item.status === status).length;
  const done = count("done");
  const running = count("transcribing");
  return [
    `${String(count("queued"))} en cola`,
    ...(running > 0 ? [`${String(running)} en curso`] : []),
    `${String(done)} ${done === 1 ? "transcrita" : "transcritas"}`,
    `${String(count("error"))} con error`,
  ].join(" · ");
}

function subscribeToClock(onTick: () => void) {
  const timer = setInterval(onTick, 1000);
  return () => {
    clearInterval(timer);
  };
}

/** Segundos desde que empezó la transcripción en curso: progreso visible sin bloquear. */
export function Elapsed({ since }: { since: number }) {
  const seconds = useSyncExternalStore(subscribeToClock, () =>
    Math.max(0, Math.floor((Date.now() - since) / 1000)),
  );
  return (
    <span className="queue__elapsed" aria-hidden="true">
      {seconds} s
    </span>
  );
}

function StatusChip({ item }: { item: QueueItem }) {
  switch (item.status) {
    case "queued":
      return <span className="chip chip--queued">En cola</span>;
    case "transcribing":
      return (
        <span className="chip chip--running">
          <span>Transcribiendo</span>
        </span>
      );
    case "done":
      return (
        <span
          className={
            (item.result?.findings_count ?? 0) > 0 ? "chip chip--finding" : "chip chip--done"
          }
        >
          {findingsLabel(item.result?.findings_count ?? 0)}
        </span>
      );
    case "error":
      return (
        <span className="chip chip--error">
          <span>{item.rejected ? "Rechazada" : "Error"}</span>
        </span>
      );
  }
}

/** Si la imagen ya es una sesión del listado: entonces la lámina de la sesión ocupa su sitio. */
function becameSession(item: QueueItem, listed: ReadonlySet<string>): boolean {
  return item.status === "done" && item.result !== undefined && listed.has(item.result.session_id);
}

interface QueuePanelProps {
  /** Las sesiones que el diario ya enseña. */
  listed: ReadonlySet<string>;
}

/**
 * La cola en el día de hoy (#370): sin columna propia, solo existe mientras hay imágenes. Cada
 * imagen es una lámina que cambia de estado en su sitio; al aparecer su sesión en el listado, la
 * lámina de la sesión la sustituye, y el recuento sigue contándola hasta «Limpiar terminadas».
 */
export function QueuePanel({ listed }: QueuePanelProps) {
  const items = useQueueStore((state) => state.items);
  const remove = useQueueStore((state) => state.remove);
  const retry = useQueueStore((state) => state.retry);
  const clearFinished = useQueueStore((state) => state.clearFinished);
  const paused = useQueueStore((state) => state.paused);
  const resume = useQueueStore((state) => state.resume);
  const finished = items.filter((item) => item.status === "done" || item.status === "error").length;
  const visible = items.filter((item) => !becameSession(item, listed));

  // Las acciones hacen desaparecer su propio botón: el foco pasa a un elemento de la cola
  // (o al título, si ya no queda ninguno) en lugar de perderse en el documento. Lo mismo si el
  // botón desaparece solo, como «Quitar» cuando la imagen empieza a transcribirse, y si la
  // lámina deja su sitio a la de su sesión: el foco pasa a esa.
  const headingRef = useRef<HTMLHeadingElement>(null);
  const itemRefs = useRef(new Map<string, HTMLLIElement>());
  const focusAfterUpdate = useRef<string | null>(null);
  const focusIfLost = useRef<string | null>(null);
  const lastFocused = useRef<string | null>(null);
  useEffect(
    () =>
      useQueueStore.subscribe(() => {
        // Antes de que React pinte el cambio: ¿qué elemento de la cola tiene el foco?
        focusIfLost.current = null;
        const active = document.activeElement;
        for (const [id, element] of itemRefs.current) {
          if (element.contains(active)) focusIfLost.current = id;
        }
      }),
    [],
  );
  useEffect(() => {
    const target = focusAfterUpdate.current;
    const owner = focusIfLost.current;
    focusAfterUpdate.current = null;
    focusIfLost.current = null;
    const lost = !document.activeElement || document.activeElement === document.body;
    if (target !== null) {
      (itemRefs.current.get(target) ?? headingRef.current)?.focus();
    } else if (owner !== null && lost) {
      (itemRefs.current.get(owner) ?? headingRef.current)?.focus();
    } else if (lost && lastFocused.current !== null) {
      const gone = items.find((item) => item.id === lastFocused.current);
      const sessionId = gone?.result?.session_id;
      if (gone && sessionId && becameSession(gone, listed)) {
        lastFocused.current = null;
        const plates = document.querySelectorAll<HTMLElement>("[data-session-id]");
        [...plates].find((plate) => plate.dataset.sessionId === sessionId)?.focus();
      }
    }
  });

  const removeItem = (id: string) => {
    const index = visible.findIndex((item) => item.id === id);
    const neighbour = visible[index + 1] ?? visible[index - 1];
    focusAfterUpdate.current = neighbour?.id ?? "";
    remove(id);
  };

  return (
    <section className="queue" aria-labelledby="queue-title">
      <div className="queue__head">
        <h3 id="queue-title" className="label queue__title" ref={headingRef} tabIndex={-1}>
          Cola
        </h3>
        <p className="label queue__summary" aria-live="polite">
          {summary(items)}
        </p>
        {finished > 0 && (
          <button
            type="button"
            className="link-button queue__clear"
            onClick={() => {
              focusAfterUpdate.current = "";
              clearFinished();
            }}
          >
            Limpiar terminadas
          </button>
        )}
      </div>
      {paused && items.some((item) => item.status === "queued") && (
        <div className="panel__error queue__paused" role="alert">
          <p>Se perdió la conexión con el servidor: la cola está en pausa.</p>
          <button
            type="button"
            className="link-button"
            onClick={() => {
              focusAfterUpdate.current = "";
              resume();
            }}
          >
            Reanudar
          </button>
        </div>
      )}
      {visible.length > 0 && (
        // role="list": sin viñetas, Safari y VoiceOver dejan de tratarla como lista.
        <ol
          className="plates"
          role="list"
          onFocus={(event) => {
            const plate = event.target.closest<HTMLElement>("[data-queue-id]");
            lastFocused.current = plate?.dataset.queueId ?? null;
          }}
          onBlur={(event) => {
            // Si el foco se va a otro sitio concreto, se olvida; si se pierde (la lámina
            // desaparece), se recuerda para pasarlo a la sesión.
            if (event.relatedTarget) lastFocused.current = null;
          }}
        >
          {visible.map((item) => (
            <QueuePlate
              key={item.id}
              item={item}
              plateRef={(node) => {
                if (node) itemRefs.current.set(item.id, node);
                else itemRefs.current.delete(item.id);
              }}
              onRemove={() => {
                removeItem(item.id);
              }}
              onRetry={() => {
                focusAfterUpdate.current = item.id;
                retry(item.id);
              }}
            />
          ))}
        </ol>
      )}
    </section>
  );
}

interface QueuePlateProps {
  item: QueueItem;
  plateRef: (node: HTMLLIElement | null) => void;
  onRemove: () => void;
  onRetry: () => void;
}

function QueuePlate({ item, plateRef, onRemove, onRetry }: QueuePlateProps) {
  const title = titleOf(item);
  const name = title ?? item.file.name;
  const findings = item.status === "done" ? (item.result?.findings_count ?? 0) : 0;
  const canRetry = item.status === "error" && !item.rejected;

  return (
    <li
      ref={plateRef}
      tabIndex={-1}
      className="plate plate--queue"
      data-queue-id={item.id}
      data-status={item.status}
      data-flagged={findings > 0}
    >
      <div className="plate__image">
        <QueueThumb item={item} />
        {/* La lectura: el único movimiento de la vista, mientras HOMR lee esta imagen. */}
        {item.status === "transcribing" && <span className="plate__reading" aria-hidden="true" />}
      </div>
      {/* Con nombre, la sesión se llamará así; sin él, como el archivo (#240). */}
      <p className="plate__name">{name}</p>
      <p className="plate__meta">
        {title !== null && <span className="queue__source">{item.file.name}</span>}
        <span>{formatSize(item.file.size)}</span>
      </p>
      <p className="plate__state">
        <StatusChip item={item} />
        {item.status === "transcribing" && item.startedAt !== undefined && (
          <Elapsed since={item.startedAt} />
        )}
      </p>
      {item.error && <p className="plate__error">{item.error}</p>}
      {(item.status === "queued" || canRetry || (item.status === "done" && item.result)) && (
        <p className="plate__actions">
          {item.status === "done" && item.result && (
            // Cada resultado lleva a su sesión, para verla o corregirla (#277).
            <Link
              className="label plate__open"
              to={`/sesiones/${encodeURIComponent(item.result.session_id)}`}
              aria-label={`Abrir la sesión de ${name}`}
            >
              Abrir la sesión
            </Link>
          )}
          {item.status === "queued" && (
            <button
              type="button"
              className="link-button"
              aria-label={`Quitar ${item.file.name}`}
              onClick={onRemove}
            >
              Quitar
            </button>
          )}
          {canRetry && (
            <button
              type="button"
              className="link-button"
              aria-label={`Reintentar ${item.file.name}`}
              onClick={onRetry}
            >
              Reintentar
            </button>
          )}
        </p>
      )}
    </li>
  );
}
