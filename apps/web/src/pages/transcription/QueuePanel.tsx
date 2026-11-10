import { useEffect, useRef } from "react";
import { Link } from "react-router";
import { api } from "../../api/instance";
import { Elapsed } from "./Elapsed";
import { findingsLabel, formatSize, queueProgress, queueSummary } from "./format";
import { JobProgressLine } from "./JobProgressLine";
import { useQueueStore, type QueueItem, type UploadHold } from "./queue";
import { nonBlank } from "./scoreData";
import { QueueThumb } from "./SessionThumb";

/** El nombre que se dio a la partitura de una imagen, o null si no se dio ninguno. */
function titleOf(item: QueueItem): string | null {
  return nonBlank(item.data?.title ?? item.title ?? undefined);
}

/** Por qué las imágenes que esperan no se suben todavía (#375). */
const HOLD_NOTICE: Record<UploadHold, string> = {
  "own-limit":
    "Tienes el máximo de transcripciones en curso: las demás imágenes se subirán cuando termine alguna.",
  "queue-full": "La cola del servidor está llena: se volverá a probar en un minuto.",
};

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
          <span>{item.rejected ? "Rechazada" : item.interrupted ? "Interrumpida" : "Error"}</span>
        </span>
      );
  }
}

/** Si la imagen ya es una sesión del listado: entonces la lámina de la sesión ocupa su sitio. */
function becameSession(item: QueueItem, listed: ReadonlySet<string>): boolean {
  return item.status === "done" && item.result !== undefined && listed.has(item.result.session_id);
}

/** La lámina de una sesión del diario. */
function sessionPlate(sessionId: string): HTMLElement | undefined {
  const plates = document.querySelectorAll<HTMLElement>("[data-session-id]");
  return [...plates].find((plate) => plate.dataset.sessionId === sessionId);
}

/**
 * Cuando una acción vacía la cola, la cola desaparece con su título: el foco pasa antes a
 * «Nueva transcripción», que sigue ahí.
 */
function leaveQueue() {
  document.getElementById("new-transcription")?.focus();
}

interface QueuePanelProps {
  /** Las sesiones que el diario ya enseña. */
  listed: ReadonlySet<string>;
}

/**
 * La cola en el día de hoy (#370): sin columna propia, solo existe mientras hay imágenes. Cada
 * imagen es una lámina que cambia de estado en su sitio; al aparecer su sesión en el listado, la
 * lámina de la sesión la sustituye, y el recuento sigue contándola hasta «Limpiar terminadas».
 * El recuento se anuncia desde la vista (TranscriptionPage), que existe aunque no haya cola.
 */
export function QueuePanel({ listed }: QueuePanelProps) {
  const items = useQueueStore((state) => state.items);
  const remove = useQueueStore((state) => state.remove);
  const retry = useQueueStore((state) => state.retry);
  const clearFinished = useQueueStore((state) => state.clearFinished);
  const paused = useQueueStore((state) => state.paused);
  const hold = useQueueStore((state) => state.hold);
  const resume = useQueueStore((state) => state.resume);
  const isFinished = (item: QueueItem) => item.status === "done" || item.status === "error";
  const finished = items.filter(isFinished).length;
  const visible = items.filter((item) => !becameSession(item, listed));

  // Las acciones hacen desaparecer su propio botón: el foco pasa a un elemento de la cola
  // (o al título, si ya no queda ninguno) en lugar de perderse en el documento. Lo mismo si el
  // botón desaparece solo, como «Quitar» cuando la imagen empieza a transcribirse, y si la
  // lámina deja su sitio a la de su sesión: el foco pasa a esa.
  const headingRef = useRef<HTMLHeadingElement>(null);
  const itemRefs = useRef(new Map<string, HTMLLIElement>());
  const focusAfterUpdate = useRef<string | null>(null);
  const focusIfLost = useRef<string | null>(null);
  // La imagen que tenía el foco cuando este se perdió sin ir a otro sitio (su lámina salió).
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
    /** Adónde va el foco de una imagen: a su sesión si ya lo es; si no, a ella o al título. */
    const focusItem = (id: string) => {
      const item = items.find((candidate) => candidate.id === id);
      const sessionId = item?.result?.session_id;
      const plate =
        item && sessionId !== undefined && becameSession(item, listed)
          ? sessionPlate(sessionId)
          : undefined;
      (plate ?? itemRefs.current.get(id) ?? headingRef.current)?.focus();
    };
    const target = focusAfterUpdate.current;
    const owner = focusIfLost.current;
    focusAfterUpdate.current = null;
    focusIfLost.current = null;
    const lost = !document.activeElement || document.activeElement === document.body;
    if (target !== null) {
      focusItem(target);
    } else if (owner !== null && lost) {
      focusItem(owner);
    } else if (lost && lastFocused.current !== null) {
      const id = lastFocused.current;
      const item = items.find((candidate) => candidate.id === id);
      if (item && becameSession(item, listed)) {
        lastFocused.current = null;
        focusItem(id);
      }
    }
  });

  const removeItem = (id: string) => {
    if (items.length === 1) {
      leaveQueue();
      void remove(id, api);
      return;
    }
    const index = visible.findIndex((item) => item.id === id);
    const neighbour = visible[index + 1] ?? visible[index - 1];
    focusAfterUpdate.current = neighbour?.id ?? "";
    void remove(id, api);
  };

  return (
    <section className="queue" aria-labelledby="queue-title">
      <div className="queue__head">
        <h3 id="queue-title" className="label queue__title" ref={headingRef} tabIndex={-1}>
          Cola
        </h3>
        <p className="label queue__summary">{queueSummary(items)}</p>
        {finished > 0 && (
          <button
            type="button"
            className="link-button queue__clear"
            onClick={() => {
              if (items.every(isFinished)) leaveQueue();
              else focusAfterUpdate.current = "";
              clearFinished(api);
            }}
          >
            Limpiar terminadas
          </button>
        )}
      </div>
      {paused &&
        items.some((item) => item.status === "queued" || item.status === "transcribing") && (
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
      {hold && !paused && items.some((item) => item.status === "queued" && !item.job) && (
        <p className="queue__hold">{HOLD_NOTICE[hold]}</p>
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
            // Si el foco va a otro sitio, se olvida. Si se pierde porque la lámina sale del
            // documento, se recuerda para pasarlo a su sesión; el navegador puede avisar del
            // blur antes de quitarla, así que se mira un instante después.
            const left = event.target;
            if (event.relatedTarget) {
              lastFocused.current = null;
              return;
            }
            setTimeout(() => {
              if (left.isConnected) lastFocused.current = null;
            }, 0);
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
                retry(item.id, api);
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
  const name = title ?? item.name;
  const findings = item.status === "done" ? (item.result?.findings_count ?? 0) : 0;
  // Sin el archivo (recuperada del servidor o interrumpida) no se puede volver a subir desde aquí.
  const canRetry = item.status === "error" && !item.rejected && item.file !== undefined;
  const canRemove =
    (item.status === "queued" && !item.uploading) || (item.status === "error" && !canRetry);
  const progress = queueProgress(item);

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
        {title !== null && <span className="queue__source">{item.name}</span>}
        {item.size !== undefined && <span>{formatSize(item.size)}</span>}
      </p>
      <p className="plate__state">
        <StatusChip item={item} />
        {item.status === "transcribing" && item.startedAt !== undefined && (
          <Elapsed since={item.startedAt} />
        )}
      </p>
      {progress && <JobProgressLine progress={progress} />}
      {item.error && <p className="plate__error">{item.error}</p>}
      {(canRemove || canRetry || (item.status === "done" && item.result)) && (
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
          {canRemove && (
            <button
              type="button"
              className="link-button"
              aria-label={`Quitar ${item.name}`}
              onClick={onRemove}
            >
              Quitar
            </button>
          )}
          {canRetry && (
            <button
              type="button"
              className="link-button"
              aria-label={`Reintentar ${item.name}`}
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
