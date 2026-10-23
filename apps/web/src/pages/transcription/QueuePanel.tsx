import { useEffect, useRef, useSyncExternalStore } from "react";
import { useQueueStore, type QueueItem } from "./queue";

function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${String(Math.max(1, Math.round(bytes / 1024)))} KB`;
  return `${(bytes / (1024 * 1024)).toLocaleString("es", { maximumFractionDigits: 1 })} MB`;
}

function findingsLabel(count: number): string {
  if (count === 0) return "Sin hallazgos";
  return count === 1 ? "1 hallazgo" : `${String(count)} hallazgos`;
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
function Elapsed({ since }: { since: number }) {
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

export function QueuePanel() {
  const items = useQueueStore((state) => state.items);
  const remove = useQueueStore((state) => state.remove);
  const retry = useQueueStore((state) => state.retry);
  const clearFinished = useQueueStore((state) => state.clearFinished);
  const paused = useQueueStore((state) => state.paused);
  const resume = useQueueStore((state) => state.resume);
  const finished = items.filter((item) => item.status === "done" || item.status === "error").length;

  // Las acciones hacen desaparecer su propio botón: el foco pasa a un elemento de la cola
  // (o al título, si ya no queda ninguno) en lugar de perderse en el documento. Lo mismo si el
  // botón desaparece solo, como «Quitar» cuando la imagen empieza a transcribirse.
  const headingRef = useRef<HTMLHeadingElement>(null);
  const itemRefs = useRef(new Map<string, HTMLLIElement>());
  const focusAfterUpdate = useRef<string | null>(null);
  const focusIfLost = useRef<string | null>(null);
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
    if (target !== null) {
      (itemRefs.current.get(target) ?? headingRef.current)?.focus();
    } else if (
      owner !== null &&
      (!document.activeElement || document.activeElement === document.body)
    ) {
      (itemRefs.current.get(owner) ?? headingRef.current)?.focus();
    }
  });

  const removeItem = (index: number, id: string) => {
    const neighbour = items[index + 1] ?? items[index - 1];
    focusAfterUpdate.current = neighbour?.id ?? "";
    remove(id);
  };

  return (
    <section className="panel queue" aria-labelledby="queue-title">
      <div className="panel__head">
        <h2 id="queue-title" className="panel__title" ref={headingRef} tabIndex={-1}>
          Cola
        </h2>
        <p className="label panel__count" aria-live="polite">
          {items.length === 0 ? "Vacía" : summary(items)}
        </p>
      </div>
      {paused && items.some((item) => item.status === "queued") && (
        <div className="panel__error" role="alert">
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
      {items.length === 0 ? (
        <p className="panel__empty">
          Las imágenes que elijas aparecerán aquí y se transcribirán de una en una.
        </p>
      ) : (
        <>
          {/* role="list": sin viñetas, Safari y VoiceOver dejan de tratarla como lista. */}
          <ol className="queue__list" role="list">
            {items.map((item, index) => (
              <li
                key={item.id}
                ref={(node) => {
                  if (node) itemRefs.current.set(item.id, node);
                  else itemRefs.current.delete(item.id);
                }}
                tabIndex={-1}
                className="queue__item"
                data-status={item.status}
              >
                <div className="queue__file">
                  <span className="queue__name">{item.file.name}</span>
                  <span className="label queue__size">{formatSize(item.file.size)}</span>
                </div>
                <div className="queue__state">
                  <StatusChip item={item} />
                  {item.status === "transcribing" && item.startedAt !== undefined && (
                    <Elapsed since={item.startedAt} />
                  )}
                </div>
                {item.error && <p className="queue__error">{item.error}</p>}
                {item.status === "done" && item.result && (
                  <p className="label queue__session">
                    Sesión {item.result.session_id.slice(0, 8)}
                  </p>
                )}
                <div className="queue__actions">
                  {item.status === "queued" && (
                    <button
                      type="button"
                      className="link-button"
                      aria-label={`Quitar ${item.file.name}`}
                      onClick={() => {
                        removeItem(index, item.id);
                      }}
                    >
                      Quitar
                    </button>
                  )}
                  {item.status === "error" && !item.rejected && (
                    <button
                      type="button"
                      className="link-button"
                      aria-label={`Reintentar ${item.file.name}`}
                      onClick={() => {
                        focusAfterUpdate.current = item.id;
                        retry(item.id);
                      }}
                    >
                      Reintentar
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ol>
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
        </>
      )}
    </section>
  );
}
