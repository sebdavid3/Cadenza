import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
} from "react";
import type { ScoreIRPayload } from "../../types";
import { measureSlot, slotKey, type MeasureMark, type MeasureSlot } from "./findings";
import { editCommand, eventAt, type EditCommand, type EditTarget } from "./edits";
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

/** Un estado de la sesión, tal como se dibuja: su MusicXML, su `ScoreIR` y su `seq`. */
export interface ScoreSnapshot {
  xml: string;
  transcription: ScoreIRPayload;
  seq: number;
}

/** Dibujo de OSMD de un estado. `layout` cambia cada vez que se vuelve a maquetar. */
interface Drawing {
  score: RenderedScore;
  snapshot: ScoreSnapshot;
  layout: number;
}

interface RenderState {
  /** Lo que está a la vista; mientras se dibuja otro estado, sigue siendo el anterior. */
  drawing: Drawing | null;
  /** Estado que no se pudo dibujar. */
  failed: ScoreSnapshot | null;
}

interface ScoreViewProps {
  /** Estado que se dibuja: al cambiar, se dibuja el nuevo sin quitar el anterior hasta tenerlo. */
  snapshot: ScoreSnapshot;
  /** Sesión de la partitura: la selección vale solo para ella y para el `seq` de su estado. */
  sessionId: string;
  marks: readonly MeasureMark[];
  /** Compases de cada pentagrama en el `ScoreIR`: si OSMD dibuja otros, no se marca nada. */
  expectedMeasures: readonly number[];
  selectedKey: string | null;
  /** Avisa de si las marcas se pudieron situar sobre la partitura dibujada. */
  onPlacement?: (placed: boolean) => void;
  /** Compás que suena y dónde se dibuja en cada pentagrama; null si no suena nada. */
  playing?: { measure: number; slots: readonly MeasureSlot[] } | null;
  /**
   * Barra de corrección (ADR-0030), entre la de la selección y la partitura: recibe el evento
   * elegido en el estado actual, o null si no hay ninguno que se pueda corregir.
   */
  editor?: (target: EditTarget | null) => ReactNode;
  /** Órdenes de corrección con el teclado sobre la partitura; sin ella, las teclas no editan. */
  onCommand?: (command: EditCommand, target: EditTarget | null) => void;
  /** Leyenda de las teclas de corrección, que también describe la partitura. */
  editKeysId?: string;
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

/** Dibujo que está en la página: su contenedor, su partitura y lo que lo vuelve a maquetar. */
interface Shown {
  target: HTMLDivElement;
  score: RenderedScore;
  observer: ResizeObserver | null;
  timer: ReturnType<typeof setTimeout> | undefined;
}

function release(shown: Shown | null) {
  if (!shown) return;
  clearTimeout(shown.timer);
  shown.observer?.disconnect();
  shown.score.dispose();
  shown.target.remove();
}

/**
 * Notación dibujada con OSMD y, detrás, la trama violeta de los compases con posibles errores.
 * Se vuelve a maquetar cuando cambia el ancho. Si OSMD falla, lo dice sin arrastrar al resto de
 * la vista: la imagen y la lista siguen disponibles.
 */
export function ScoreView({
  snapshot,
  sessionId,
  marks,
  expectedMeasures,
  selectedKey,
  onPlacement,
  playing = null,
  editor,
  onCommand,
  editKeysId,
}: ScoreViewProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<RenderState>({ drawing: null, failed: null });
  const shownRef = useRef<Shown | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    // Cada estado se dibuja en su propio contenedor y cancela su dibujo si deja de hacer falta:
    // con el doble montaje de StrictMode, al salir mientras OSMD carga o si llega otro estado,
    // el dibujo descartado no pisa al que se queda y se libera. Mientras haya uno a la vista, el
    // nuevo se prepara oculto encima de él y lo sustituye al terminar: la página no salta ni la
    // partitura pierde el foco al editar (ADR-0030).
    const target = document.createElement("div");
    if (shownRef.current) target.className = "notation__next";
    host.appendChild(target);
    const controller = new AbortController();

    renderScore(target, snapshot.xml, controller.signal)
      .then((score) => {
        if (controller.signal.aborted) {
          score.dispose();
          return;
        }
        release(shownRef.current);
        target.removeAttribute("class");
        const shown: Shown = { target, score, observer: null, timer: undefined };
        shownRef.current = shown;
        setState({ drawing: { score, snapshot, layout: 0 }, failed: null });
        if (!("ResizeObserver" in window)) return;
        let width = target.clientWidth;
        shown.observer = new ResizeObserver(() => {
          if (target.clientWidth === width) return;
          width = target.clientWidth;
          clearTimeout(shown.timer);
          shown.timer = setTimeout(() => {
            try {
              score.relayout(width);
              setState((previous) =>
                previous.drawing?.score === score
                  ? {
                      ...previous,
                      drawing: { ...previous.drawing, layout: previous.drawing.layout + 1 },
                    }
                  : previous,
              );
            } catch {
              if (shownRef.current === shown) shownRef.current = null;
              release(shown);
              setState({ drawing: null, failed: snapshot });
            }
          }, RELAYOUT_DELAY_MS);
        });
        shown.observer.observe(target);
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        // Lo que quedaba a la vista es de otro estado: no se deja como si fuera este.
        release(shownRef.current);
        shownRef.current = null;
        target.remove();
        setState({ drawing: null, failed: snapshot });
      });

    return () => {
      controller.abort();
      // El dibujo a la vista se queda hasta que llegue el siguiente o se salga de la vista.
      if (shownRef.current?.target !== target) target.remove();
    };
  }, [snapshot]);

  useEffect(
    () => () => {
      release(shownRef.current);
      shownRef.current = null;
    },
    [],
  );

  const { drawing } = state;
  const status = drawing ? "ready" : state.failed === snapshot ? "failed" : "rendering";
  // Se está dibujando otro estado: lo que se ve sigue siendo el anterior.
  const redrawing = drawing !== null && drawing.snapshot !== snapshot;
  const layout = drawing ? drawing.layout : -1;
  const score = drawing?.score ?? null;
  const drawn = drawing?.snapshot ?? null;
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

  // Mapa ancla→caja por evento (ADR-0027), del estado dibujado y con la geometría de cada
  // maquetación.
  const noteMap = useMemo(
    () =>
      score && drawn && aligned && layout >= 0
        ? buildNoteMap(drawn.transcription, (slot) => score.measureFigures(slot))
        : null,
    [score, drawn, aligned, layout],
  );
  // Sin notas ni silencios no hay nada que elegir: la partitura sigue siendo una imagen.
  const selectable =
    noteMap?.status === "complete" && noteMap.events.length > 0 ? noteMap.events : null;

  // La nota elegida vale para esta sesión y un estado: las anclas son relativas a un estado.
  const stored = useSelectionStore((store) => store.selection);
  const select = useSelectionStore((store) => store.select);
  const clearSelection = useSelectionStore((store) => store.clear);
  const ours = stored !== null && stored.sessionId === sessionId ? stored : null;
  // Sobre el dibujo: la marca y los movimientos, con el estado que se ve.
  const noteKey = ours && ours.seq === drawn?.seq ? anchorKey(ours.anchor) : null;
  const chosen = selectable?.find((candidate) => candidate.key === noteKey) ?? null;
  // Lo que es la nota elegida sale del estado actual, también mientras se dibuja: tras corregirla
  // se lee su valor nuevo sin esperar al dibujo.
  const found =
    selectable && ours?.seq === snapshot.seq ? eventAt(snapshot.transcription, ours.anchor) : null;
  const target: EditTarget | null = ours && found ? { anchor: ours.anchor, ...found } : null;
  const multiStaff = expectedMeasures.length > 1;
  const description = target
    ? describeEvent(target.event, {
        measure: target.anchor.measure,
        staff: measureSlot(snapshot.transcription, target.anchor)?.staff ?? target.anchor.staff,
        multiStaff,
        chord: target.chord,
      })
    : null;

  const stageRef = useRef<HTMLDivElement>(null);
  const selectionRef = useRef<HTMLDivElement>(null);
  // Al moverse con el teclado o los botones, la nota elegida se trae a la vista; al tocarla, no.
  const revealRef = useRef(false);
  const choose = (candidate: SelectableEvent | null, reveal: boolean) => {
    if (!candidate || !drawn) return;
    // Si la tecla no movió la selección (un borde), no queda nada pendiente de traer a la vista.
    revealRef.current = reveal && candidate.key !== noteKey;
    select({ sessionId, seq: drawn.seq, anchor: candidate.anchor });
  };
  // Mientras se dibuja otro estado no se elige sobre el anterior.
  const move = (how: Move) => {
    if (selectable && !redrawing) choose(moveSelection(selectable, noteKey, how), true);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!selectable) return;
    const command = onCommand ? editCommand(event) : null;
    if (command) {
      event.preventDefault();
      onCommand?.(command, target);
      return;
    }
    const action = keyAction(event);
    if (!action) return;
    if (action === "clear") {
      if (!target) return;
      event.preventDefault();
      clearSelection();
      return;
    }
    event.preventDefault();
    move(action);
  };
  const onClick = (event: MouseEvent<HTMLDivElement>) => {
    if (!selectable || !score || redrawing) return;
    const stage = event.currentTarget;
    const origin = stage.getBoundingClientRect();
    const candidate = nearestEvent(
      selectable,
      event.clientX - origin.left,
      event.clientY - origin.top,
      (slot) => score.measureBox(slot),
    );
    if (!candidate) return;
    choose(candidate, false);
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

  // Se anuncia dónde se detiene la selección, no cada paso intermedio. Si la nota elegida cambia
  // de valor (se corrigió), no se vuelve a anunciar: lo dice la barra de corrección.
  const spoken = description?.spoken ?? null;
  const chosenKey = target ? anchorKey(target.anchor) : null;
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
  if (status !== "ready") selectionStatus = { kind: "pending" };
  else if (!aligned) selectionStatus = { kind: "unavailable" };
  else if (noteMap?.status === "incomplete") {
    selectionStatus = { kind: "unavailable", total: noteMap.total, unmatched: noteMap.unmatched };
  } else selectionStatus = { kind: "ready", empty: selectable === null };

  const placed = status === "ready" ? boxes !== null : null;
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
        "aria-label": onCommand
          ? `${label} Elige una nota o un silencio con las flechas y corrígelo con las teclas de la leyenda.`
          : `${label} Elige una nota o un silencio con las flechas.`,
        "aria-describedby": editKeysId ? `${keysId} ${editKeysId}` : keysId,
        "aria-busy": redrawing || undefined,
        onKeyDown,
        onClick,
      }
    : {};

  return (
    <>
      {status !== "failed" && (
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
      {status !== "failed" && editor?.(target)}
      <div className="notation" data-state={status}>
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
            role={status === "ready" && !selectable ? "img" : undefined}
            aria-label={status === "ready" && !selectable ? label : undefined}
          />
        </div>
        {status === "rendering" && (
          <p className="label notation__status" role="status">
            Dibujando la partitura…
          </p>
        )}
        {status === "failed" && (
          <div className="notation__failed" role="alert">
            <p className="notation__failed-title">No se pudo dibujar la partitura.</p>
            <p>
              La imagen original y la lista de posibles errores siguen disponibles. Puede que la
              transcripción contenga algo que el visor no sabe dibujar.
            </p>
          </div>
        )}
        {status === "ready" && !boxes && marks.length > 0 && (
          <p className="notation__note">
            No se pudieron situar los posibles errores sobre la partitura dibujada: están en la
            lista.
          </p>
        )}
      </div>
    </>
  );
}
