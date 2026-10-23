import { useEffect, useState } from "react";
import { useQueueStore, type QueueItem } from "./queue";

function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${String(Math.max(1, Math.round(bytes / 1024)))} KB`;
  return `${(bytes / (1024 * 1024)).toLocaleString("es", { maximumFractionDigits: 1 })} MB`;
}

function findingsLabel(count: number): string {
  if (count === 0) return "Sin hallazgos";
  return count === 1 ? "1 hallazgo" : `${String(count)} hallazgos`;
}

/** Segundos desde que empezó la transcripción en curso: progreso visible sin bloquear. */
function Elapsed() {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const timer = setInterval(() => {
      setSeconds(Math.floor((Date.now() - started) / 1000));
    }, 1000);
    return () => {
      clearInterval(timer);
    };
  }, []);
  return <span className="queue__elapsed">{seconds} s</span>;
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
        <span className="chip chip--done">{findingsLabel(item.result?.findings_count ?? 0)}</span>
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
  const pending = items.filter((item) => item.status === "queued").length;
  const finished = items.filter((item) => item.status === "done" || item.status === "error").length;

  return (
    <section className="panel queue" aria-labelledby="queue-title">
      <div className="panel__head">
        <h2 id="queue-title" className="panel__title">
          Cola
        </h2>
        <p className="label panel__count" aria-live="polite">
          {items.length === 0
            ? "Vacía"
            : `${String(pending)} en cola · ${String(finished)} terminadas`}
        </p>
      </div>
      {items.length === 0 ? (
        <p className="panel__empty">
          Las imágenes que elijas aparecerán aquí y se transcribirán de una en una.
        </p>
      ) : (
        <>
          <ol className="queue__list">
            {items.map((item) => (
              <li key={item.id} className="queue__item" data-status={item.status}>
                <div className="queue__file">
                  <span className="queue__name">{item.file.name}</span>
                  <span className="label queue__size">{formatSize(item.file.size)}</span>
                </div>
                <div className="queue__state" aria-live="polite">
                  <StatusChip item={item} />
                  {item.status === "transcribing" && <Elapsed />}
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
                      onClick={() => {
                        remove(item.id);
                      }}
                    >
                      Quitar<span className="visually-hidden"> {item.file.name}</span>
                    </button>
                  )}
                  {item.status === "error" && !item.rejected && (
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => {
                        retry(item.id);
                      }}
                    >
                      Reintentar<span className="visually-hidden"> {item.file.name}</span>
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ol>
          {finished > 0 && (
            <button type="button" className="link-button queue__clear" onClick={clearFinished}>
              Limpiar terminadas
            </button>
          )}
        </>
      )}
    </section>
  );
}
