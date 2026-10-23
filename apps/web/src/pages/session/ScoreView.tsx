import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
} from "react";
import type { ScoreIRPayload } from "../../types";
import { slotKey, type MeasureMark, type MeasureSlot } from "./findings";
import {
  anchorKey,
  buildNoteMap,
  moveSelection,
  nearestEvent,
  type Move,
  type SelectableEvent,
} from "./noteMap";
import { describeEvent } from "./noteNames";
import { renderScore, type Box, type RenderedScore } from "./osmd";
import { useSelectionStore } from "./selection";
import { SelectionBar, type SelectionStatus } from "./SelectionBar";

type RenderState =
  | { status: "rendering" }
  // `layout` cambia cada vez que OSMD vuelve a maquetar, para recolocar las marcas.
  | { status: "ready"; score: RenderedScore; layout: number }
  | { status: "failed" };

interface ScoreViewProps {
  /** MusicXML de un estado de la sesión: la vista se monta de nuevo si cambia. */
  xml: string;
  /** `ScoreIR` del mismo estado: de él salen las anclas de las notas que se eligen. */
  transcription: ScoreIRPayload;
  /** Sesión y estado (`seq`) de los que es la partitura: la selección vale solo para ellos. */
  sessionId: string;
  seq: number;
  marks: readonly MeasureMark[];
  /** Compases de cada pentagrama en el `ScoreIR`: si OSMD dibuja otros, no se marca nada. */
  expectedMeasures: readonly number[];
  selectedKey: string | null;
  /** Avisa de si las marcas se pudieron situar sobre la partitura dibujada. */
  onPlacement?: (placed: boolean) => void;
  /** Compás que suena y dónde se dibuja en cada pentagrama; null si no suena nada. */
  playing?: { measure: number; slots: readonly MeasureSlot[] } | null;
}

/** Tecla pulsada sobre la partitura: un movimiento, quitar la selección o nada. */
function keyAction(event: KeyboardEvent): Move | "clear" | null {
  if (event.altKey) return null;
  const jump = event.ctrlKey || event.metaKey;
  switch (event.key) {
    case "ArrowRight":
      return jump ? "next-measure" : "next";
    case "ArrowLeft":
      return jump ? "previous-measure" : "previous";
    case "PageDown":
      return "next-measure";
    case "PageUp":
      return "previous-measure";
    case "Home":
      return "measure-start";
    case "End":
      return "measure-end";
    case "ArrowDown":
      return jump ? null : "down";
    case "ArrowUp":
      return jump ? null : "up";
    case "Escape":
      return "clear";
    default:
      return null;
  }
}

/** Espera antes de anunciar la nota elegida: al moverse deprisa solo se anuncia la última. */
const ANNOUNCE_DELAY_MS = 300;
const HARD_SPACE = String.fromCharCode(0xa0);

function sameCounts(a: readonly number[], b: readonly number[]) {
  return a.length === b.length && a.every((count, index) => count === b[index]);
}

/** Cajas de los compases marcados, o null si no se pueden situar con seguridad (ADR-0021). */
function placeMarks(score: RenderedScore, marks: readonly MeasureMark[]): Map<string, Box> | null {
  const boxes = new Map<string, Box>();
  for (const mark of marks) {
    const box = score.measureBox(mark.slot);
    if (!box) return null;
    boxes.set(slotKey(mark.slot), box);
  }
  return boxes;
}

const RELAYOUT_DELAY_MS = 150;

/**
 * Notación dibujada con OSMD y, detrás, la trama violeta de los compases con posibles errores.
 * Se vuelve a maquetar cuando cambia el ancho. Si OSMD falla, lo dice sin arrastrar al resto de
 * la vista: la imagen y la lista siguen disponibles.
 */
export function ScoreView({
  xml,
  transcription,
  sessionId,
  seq,
  marks,
  expectedMeasures,
  selectedKey,
  onPlacement,
  playing = null,
}: ScoreViewProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<RenderState>({ status: "rendering" });

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    // Cada montaje dibuja en su propio contenedor y cancela su dibujo al irse: con el doble
    // montaje de StrictMode, o al salir mientras OSMD carga, el dibujo descartado no pisa al que
    // se queda y se libera.
    const target = document.createElement("div");
    host.appendChild(target);
    const controller = new AbortController();
    let rendered: RenderedScore | null = null;
    let observer: ResizeObserver | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;

    renderScore(target, xml, controller.signal)
      .then((score) => {
        if (controller.signal.aborted) {
          score.dispose();
          return;
        }
        rendered = score;
        setState({ status: "ready", score, layout: 0 });
        if (!("ResizeObserver" in window)) return;
        let width = target.clientWidth;
        observer = new ResizeObserver(() => {
          if (target.clientWidth === width) return;
          width = target.clientWidth;
          clearTimeout(timer);
          timer = setTimeout(() => {
            try {
              score.relayout(width);
              setState((previous) =>
                previous.status === "ready"
                  ? { ...previous, layout: previous.layout + 1 }
                  : previous,
              );
            } catch {
              setState({ status: "failed" });
            }
          }, RELAYOUT_DELAY_MS);
        });
        observer.observe(target);
      })
      .catch(() => {
        if (!controller.signal.aborted) setState({ status: "failed" });
      });

    return () => {
      controller.abort();
      clearTimeout(timer);
      observer?.disconnect();
      rendered?.dispose();
      target.remove();
    };
  }, [xml]);

  const layout = state.status === "ready" ? state.layout : -1;
  const score = state.status === "ready" ? state.score : null;
  // Solo se dibuja sobre la partitura si OSMD dibujó los mismos compases que el `ScoreIR`.
  const aligned = useMemo(
    () => score !== null && layout >= 0 && sameCounts(score.measuresPerStaff(), expectedMeasures),
    [score, layout, expectedMeasures],
  );
  // `layout` cambia al volver a maquetar: las cajas se recalculan con la geometría nueva.
  const boxes = useMemo(
    () => (score && aligned && layout >= 0 ? placeMarks(score, marks) : null),
    [score, aligned, layout, marks],
  );
  // El compás que suena, con la misma geometría que las marcas (en cada pentagrama donde está).
  const playheadBoxes = useMemo(() => {
    if (!score || !aligned || layout < 0 || !playing) return [];
    return playing.slots.flatMap((slot) => {
      const box = score.measureBox(slot);
      return box ? [{ key: slotKey(slot), box }] : [];
    });
  }, [score, aligned, layout, playing]);

  // Mapa ancla→caja por evento (ADR-0027), con la geometría de cada maquetación.
  const noteMap = useMemo(
    () =>
      score && aligned && layout >= 0
        ? buildNoteMap(transcription, (slot) => score.measureFigures(slot))
        : null,
    [score, aligned, layout, transcription],
  );
  // Sin notas ni silencios no hay nada que elegir: la partitura sigue siendo una imagen.
  const selectable =
    noteMap?.status === "complete" && noteMap.events.length > 0 ? noteMap.events : null;

  // La nota elegida vale para esta sesión y este estado: las anclas son relativas a un estado.
  const stored = useSelectionStore((store) => store.selection);
  const select = useSelectionStore((store) => store.select);
  const clearSelection = useSelectionStore((store) => store.clear);
  const noteKey =
    stored !== null && stored.sessionId === sessionId && stored.seq === seq
      ? anchorKey(stored.anchor)
      : null;
  const chosen = selectable?.find((candidate) => candidate.key === noteKey) ?? null;
  const multiStaff = expectedMeasures.length > 1;
  const description = chosen
    ? describeEvent(chosen.event, {
        measure: chosen.anchor.measure,
        staff: chosen.slot.staff,
        multiStaff,
        chord: chosen.chord,
      })
    : null;

  const stageRef = useRef<HTMLDivElement>(null);
  const selectionRef = useRef<HTMLDivElement>(null);
  // Al moverse con el teclado o los botones, la nota elegida se trae a la vista; al tocarla, no.
  const revealRef = useRef(false);
  const choose = (target: SelectableEvent | null, reveal: boolean) => {
    if (!target) return;
    // Si la tecla no movió la selección (un borde), no queda nada pendiente de traer a la vista.
    revealRef.current = reveal && target.key !== noteKey;
    select({ sessionId, seq, anchor: target.anchor });
  };
  const move = (how: Move) => {
    if (selectable) choose(moveSelection(selectable, noteKey, how), true);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const action = keyAction(event);
    if (!selectable || !action) return;
    if (action === "clear") {
      if (!chosen) return;
      event.preventDefault();
      clearSelection();
      return;
    }
    event.preventDefault();
    move(action);
  };
  const onClick = (event: MouseEvent<HTMLDivElement>) => {
    if (!selectable || !score) return;
    const stage = event.currentTarget;
    const origin = stage.getBoundingClientRect();
    const target = nearestEvent(
      selectable,
      event.clientX - origin.left,
      event.clientY - origin.top,
      (slot) => score.measureBox(slot),
    );
    if (!target) return;
    choose(target, false);
    stage.focus({ preventScroll: true });
  };

  useEffect(() => {
    if (!chosen || !revealRef.current) return;
    revealRef.current = false;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    selectionRef.current?.scrollIntoView({
      block: "nearest",
      inline: "nearest",
      behavior: reduce ? "auto" : "smooth",
    });
  }, [chosen]);

  // Se anuncia dónde se detiene la selección, no cada paso intermedio.
  const spoken = description?.spoken ?? null;
  const chosenKey = chosen?.key ?? null;
  const [announcement, setAnnouncement] = useState("");
  const lastAnnounced = useRef<string | null>(null);
  useEffect(() => {
    if (chosenKey === lastAnnounced.current) return;
    const timer = setTimeout(() => {
      lastAnnounced.current = chosenKey;
      const text = spoken ?? "Sin nota elegida.";
      // Un texto igual al anterior (dos Do4 negras seguidas) no se volvería a leer: un espacio
      // duro al final lo distingue sin cambiar lo que se oye.
      setAnnouncement((previous) => (previous === text ? `${text}${HARD_SPACE}` : text));
    }, ANNOUNCE_DELAY_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [chosenKey, spoken]);

  const keysId = useId();
  let selectionStatus: SelectionStatus;
  if (state.status !== "ready") selectionStatus = { kind: "pending" };
  else if (!aligned) selectionStatus = { kind: "unavailable" };
  else if (noteMap?.status === "incomplete") {
    selectionStatus = { kind: "unavailable", total: noteMap.total, unmatched: noteMap.unmatched };
  } else selectionStatus = { kind: "ready", empty: selectable === null };

  const placed = state.status === "ready" ? boxes !== null : null;
  useEffect(() => {
    if (placed !== null) onPlacement?.(placed);
  }, [placed, onPlacement]);

  // Al elegir un posible error en la lista, su compás se trae a la vista una sola vez: volver a
  // maquetar al cambiar el ancho no vuelve a desplazar la página.
  const marksRef = useRef<HTMLDivElement>(null);
  const scrolledRef = useRef<string | null>(null);
  useEffect(() => {
    if (!selectedKey) {
      scrolledRef.current = null;
      return;
    }
    if (!boxes || scrolledRef.current === selectedKey) return;
    const element = marksRef.current?.querySelector(`[data-key="${selectedKey}"]`);
    if (!element) return;
    scrolledRef.current = selectedKey;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    element.scrollIntoView({
      block: "nearest",
      inline: "center",
      behavior: reduce ? "auto" : "smooth",
    });
  }, [selectedKey, boxes]);

  // El compás que suena se trae a la vista si sale de ella, pero solo si el anterior estaba a la
  // vista: si la persona se fue a mirar la imagen o la lista, no se la devuelve a la partitura.
  // Con movimiento reducido, sin desplazamiento suave.
  const playingMeasure = playheadBoxes.length > 0 ? (playing?.measure ?? null) : null;
  const followed = useRef<{ measure: number; box: Box } | null>(null);
  useEffect(() => {
    const box = playheadBoxes[0]?.box ?? null;
    if (playingMeasure === null || !box) {
      followed.current = null;
      return;
    }
    const previous = followed.current;
    followed.current = { measure: playingMeasure, box };
    // El mismo compás con otra geometría (se volvió a maquetar): no se desplaza nada.
    if (previous?.measure === playingMeasure) return;
    const layer = marksRef.current;
    const element = layer?.querySelector(".notation__playhead");
    if (!layer || !element) return;
    if (previous) {
      const top = layer.getBoundingClientRect().top + previous.box.top;
      if (top + previous.box.height <= 0 || top >= window.innerHeight) return;
    }
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    element.scrollIntoView({
      block: "nearest",
      inline: "nearest",
      behavior: reduce ? "auto" : "smooth",
    });
  }, [playingMeasure, playheadBoxes]);

  const flagged = marks.map((mark) => mark.measureNumber).join(", ");
  const label =
    boxes && marks.length > 0
      ? `Partitura transcrita. Compases con posibles errores: ${flagged}.`
      : "Partitura transcrita.";

  // Con notas que elegir, la partitura es un control con sus propias teclas (`application`, para
  // que el lector de pantalla le pase las flechas) y su nombre dice lo que decía la imagen.
  const stageProps = selectable
    ? {
        role: "application",
        tabIndex: 0,
        "aria-roledescription": "partitura",
        "aria-label": `${label} Elige una nota o un silencio con las flechas.`,
        "aria-describedby": keysId,
        onKeyDown,
        onClick,
      }
    : {};

  return (
    <>
      {state.status !== "failed" && (
        <SelectionBar
          status={selectionStatus}
          description={description}
          announcement={announcement}
          keysId={keysId}
          onPrevious={() => {
            move("previous");
          }}
          onNext={() => {
            move("next");
          }}
          onClear={() => {
            stageRef.current?.focus({ preventScroll: true });
            clearSelection();
          }}
        />
      )}
      <div className="notation" data-state={state.status}>
        <div className="notation__stage" ref={stageRef} {...stageProps}>
          {aligned && (
            <div className="notation__marks" ref={marksRef} aria-hidden="true">
              {marks.map((mark) => {
                const box = boxes?.get(mark.key);
                if (!box) return null;
                return (
                  <div
                    key={mark.key}
                    data-key={mark.key}
                    className="notation__mark"
                    data-selected={mark.key === selectedKey}
                    style={{ left: box.left, top: box.top, width: box.width, height: box.height }}
                  >
                    <span className="label notation__tag">
                      <span className="notation__tag-word">Compás </span>
                      {mark.measureNumber}
                    </span>
                  </div>
                );
              })}
              {playheadBoxes.map(({ key, box }) => (
                // Cada compás nuevo monta su resaltado, para que entre con su barrido.
                <div
                  key={`${String(playingMeasure)}:${key}`}
                  className="notation__playhead"
                  style={{ left: box.left, top: box.top, width: box.width, height: box.height }}
                />
              ))}
              {/* Una marca por figura: la de una nota partida no abarca lo que hay entre medias. */}
              {chosen?.boxes.map((box, index) => (
                <div
                  key={`${chosen.key}:${String(index)}`}
                  ref={index === 0 ? selectionRef : undefined}
                  className="notation__selection"
                  style={{ left: box.left, top: box.top, width: box.width, height: box.height }}
                />
              ))}
            </div>
          )}
          {/* Solo es una imagen con nombre cuando hay partitura dibujada y no se eligen notas. */}
          <div
            className="notation__host"
            ref={hostRef}
            role={state.status === "ready" && !selectable ? "img" : undefined}
            aria-label={state.status === "ready" && !selectable ? label : undefined}
          />
        </div>
        {state.status === "rendering" && (
          <p className="label notation__status" role="status">
            Dibujando la partitura…
          </p>
        )}
        {state.status === "failed" && (
          <div className="notation__failed" role="alert">
            <p className="notation__failed-title">No se pudo dibujar la partitura.</p>
            <p>
              La imagen original y la lista de posibles errores siguen disponibles. Puede que la
              transcripción contenga algo que el visor no sabe dibujar.
            </p>
          </div>
        )}
        {state.status === "ready" && !boxes && marks.length > 0 && (
          <p className="notation__note">
            No se pudieron situar los posibles errores sobre la partitura dibujada: están en la
            lista.
          </p>
        )}
      </div>
    </>
  );
}
