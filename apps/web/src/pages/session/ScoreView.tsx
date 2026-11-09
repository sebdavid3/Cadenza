import {
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type KeyboardEvent,
  type MouseEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import type { ScoreIRPayload } from "../../types";
import { measureSlot, slotKey, type MeasureMark, type MeasureSlot } from "./findings";
import {
  activeClef,
  activeFifths,
  editCommand,
  eventAt,
  staffPitch,
  staffSteps,
  type EditCommand,
  type EditTarget,
} from "./edits";
import { writeSpotAt, type WriteSpot, type WritingMode } from "./writing";
import { WriteGhost } from "./WriteGhost";
import {
  anchorKey,
  buildNoteMap,
  moveSelection,
  nearestEvent,
  type Move,
  type SelectableEvent,
} from "./noteMap";
import { describeEvent } from "./noteNames";
import { markDrawn, timeStage } from "./marks";
import { createScoreRenderer, type Box, type RenderedScore, type ScoreRenderer } from "./osmd";
import { useSelectionStore } from "./selection";
import { SelectionBar } from "./SelectionBar";
import type { SelectionControls, SelectionStatus } from "./selectionControls";

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
  /**
   * Estado que se dibuja: al cambiar, se dibuja el nuevo en la misma instancia de OSMD antes de
   * pintar, y lo anterior sigue a la vista hasta entonces (#276).
   */
  snapshot: ScoreSnapshot;
  /** Sesión de la partitura: la selección vale solo para ella y para el `seq` de su estado. */
  sessionId: string;
  marks: readonly MeasureMark[];
  /** Compases de cada pentagrama en el `ScoreIR`: si OSMD dibuja otros, no se marca nada. */
  expectedMeasures: readonly number[];
  selectedKey: string | null;
  /** Avisa de si las marcas se pudieron situar sobre la partitura dibujada. */
  onPlacement?: (placed: boolean) => void;
  /**
   * Si la vista lista los posibles errores. En una sesión no asistida no los hay, y la vista no
   * habla de ellos (ADR-0040 §13.2).
   */
  findingsListed?: boolean;
  /** Compás que suena y dónde se dibuja en cada pentagrama; null si no suena nada. */
  playing?: { measure: number; slots: readonly MeasureSlot[] } | null;
  /**
   * Barra de corrección (ADR-0030), encima de la partitura y con la selección dentro: recibe el evento
   * elegido en el estado actual (o null si no hay ninguno que se pueda corregir), si se pueden
   * elegir notas y cómo llevar el foco a la partitura. Sigue aunque la partitura no se pueda
   * dibujar, para que se vea qué pasó con la última corrección.
   */
  editor?: EditorRender;
  /** Órdenes de corrección con el teclado sobre la partitura; sin ella, las teclas no editan. */
  onCommand?: (command: EditCommand, target: EditTarget | null) => void;
  /** Leyenda de las teclas de corrección, que también describe la partitura. */
  editKeysId?: string;
  /** El modo «Escribir» (#350): con él, el puntero lleva una nota fantasma y el clic escribe. */
  writing?: WritingMode | null;
  /**
   * Si se pueden elegir notas sobre la partitura (ADR-0027). Sin ello es una imagen con nombre y
   * no hay barra de selección: el resultado de la portada solo se mira (#277, ADR-0053).
   */
  notesSelectable?: boolean;
}

/** Lo que la partitura da a la barra de corrección. */
interface EditorContext {
  available: boolean;
  focusScore: () => boolean;
  /**
   * La selección de notas, si la partitura la ofrece: con barra de corrección, sus pasos van en la
   * primera fila de la barra y la nota elegida en su barra de estado (#363).
   */
  selection?: SelectionControls;
}

type EditorRender = (target: EditTarget | null, context: EditorContext) => ReactNode;

/**
 * Dibuja la barra de corrección como un componente: sus órdenes (moverse, quitar la selección)
 * usan referencias de la partitura, y así no se leen durante el dibujo de esta.
 */
function EditorSlot({
  render,
  target,
  context,
}: {
  render: EditorRender;
  target: EditTarget | null;
  context: EditorContext;
}) {
  return render(target, context);
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
 * Lo que OSMD tiene dibujado, como almacén externo de la vista: cambia cuando la instancia dibuja
 * (antes de pintar, en un efecto de maquetación) y la vista se vuelve a pintar con ello en el
 * mismo paso (`useSyncExternalStore`).
 */
function drawingStore() {
  let value: RenderState = { drawing: null, failed: null };
  const listeners = new Set<() => void>();
  return {
    get: () => value,
    set: (update: (previous: RenderState) => RenderState) => {
      value = update(value);
      for (const listener of listeners) listener();
    },
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

/** La nota fantasma del modo «Escribir»: el sitio, la altura, si va al acorde y su clave. */
interface Ghost {
  spot: WriteSpot;
  pitch: string;
  chord: boolean;
  key: string;
  /** Estado dibujado en que se calculó: con otro, su geometría ya no vale. */
  seq: number;
  /** El punto del puntero, en px de la partitura. */
  at: { x: number; y: number };
}

/**
 * Cuánto puede separarse el clic del último movimiento del ratón y escribir aún lo que enseña el
 * fantasma, en px: el navegador puede redondear distinto el punto del clic y el del movimiento.
 */
const GHOST_SLACK_PX = 1.5;

/** La nota fantasma de un sitio y una altura; con Mayús sobre una nota, va a su acorde. */
function ghostOf(
  spot: WriteSpot,
  pitch: string,
  shift: boolean,
  seq: number,
  at: Ghost["at"],
): Ghost {
  const chord = shift && spot.aim.kind === "replace" && spot.aim.event.event.kind === "note";
  const end = spot.aim.kind === "insert" && spot.aim.end;
  return {
    spot,
    pitch,
    chord,
    key: [spot.aim.kind, spot.aim.event.key, String(end), pitch, String(chord)].join("|"),
    seq,
    at,
  };
}

/** Lo que se ve del primer antepasado que se desplaza o, si no lo hay, de la ventana. */
function scrollViewOf(element: Element): { top: number; bottom: number } {
  for (let node = element.parentElement; node; node = node.parentElement) {
    const { overflowY } = window.getComputedStyle(node);
    if ((overflowY === "auto" || overflowY === "scroll") && node.scrollHeight > node.clientHeight) {
      const rect = node.getBoundingClientRect();
      return { top: Math.max(0, rect.top), bottom: Math.min(window.innerHeight, rect.bottom) };
    }
  }
  // En una columna, la imagen original va fija arriba (#341): lo que queda debajo de ella no se ve.
  const pinned = document.querySelector(".sheet--scan");
  const top =
    pinned && window.getComputedStyle(pinned).position === "sticky"
      ? Math.max(0, pinned.getBoundingClientRect().bottom)
      : 0;
  return { top, bottom: window.innerHeight };
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
  findingsListed = true,
  playing = null,
  editor,
  onCommand,
  editKeysId,
  writing = null,
  notesSelectable = true,
}: ScoreViewProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [store] = useState(drawingStore);
  const state = useSyncExternalStore(store.subscribe, store.get);
  // Una sola instancia de OSMD para toda la vista (#276): se crea al montarla y cada estado se
  // dibuja en ella. Con el doble montaje de StrictMode, o al salir mientras OSMD carga, la carga
  // descartada no crea nada.
  const [renderer, setRenderer] = useState<ScoreRenderer | null>(null);
  // Si OSMD no llega a cargarse (un corte de red, el trozo de un despliegue anterior), ningún
  // estado se puede dibujar; con el estado siguiente se vuelve a intentar.
  const [loadFailed, setLoadFailed] = useState(false);
  // Estado que se veía cuando falló la carga, e intentos.
  const [failedAt, setFailedAt] = useState<ScoreSnapshot | null>(null);
  const [attempt, setAttempt] = useState(0);
  if (loadFailed && failedAt === null) setFailedAt(snapshot);
  else if (loadFailed && failedAt !== null && failedAt !== snapshot) {
    setLoadFailed(false);
    setFailedAt(null);
    setAttempt(attempt + 1);
  }
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const controller = new AbortController();
    let created: ScoreRenderer | null = null;
    createScoreRenderer(host, controller.signal)
      .then((ready) => {
        if (controller.signal.aborted) {
          ready.dispose();
          return;
        }
        created = ready;
        setRenderer(ready);
      })
      .catch(() => {
        if (!controller.signal.aborted) setLoadFailed(true);
      });
    return () => {
      controller.abort();
      created?.dispose();
      setRenderer(null);
    };
  }, [attempt]);

  // Cada estado se dibuja antes de pintar, en la misma instancia: lo que se ve pasa del estado
  // anterior al nuevo de una vez, sin parpadeo ni un fotograma con las marcas de otro dibujo, y
  // la partitura no pierde el foco al editar (ADR-0030).
  useLayoutEffect(() => {
    if (!renderer) return;
    let score: RenderedScore;
    try {
      score = renderer.draw(snapshot.xml, { sessionId, seq: snapshot.seq });
    } catch {
      store.set(() => ({ drawing: null, failed: snapshot }));
      return;
    }
    store.set((previous) => ({
      // El mismo dibujo (el MusicXML no cambió) conserva su maquetación.
      drawing: {
        score,
        snapshot,
        layout: previous.drawing?.score === score ? previous.drawing.layout : 0,
      },
      failed: null,
    }));
    // Fin de la orden que creó este estado, si la hubo (#275).
    markDrawn(sessionId, snapshot.seq);
  }, [renderer, snapshot, sessionId, store]);

  // Se vuelve a maquetar cuando cambia el ancho.
  useEffect(() => {
    const host = hostRef.current;
    if (!renderer || !host || !("ResizeObserver" in window)) return;
    let width = host.clientWidth;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const observer = new ResizeObserver(() => {
      if (host.clientWidth === width) return;
      width = host.clientWidth;
      clearTimeout(timer);
      timer = setTimeout(() => {
        try {
          renderer.relayout(width);
          store.set((previous) =>
            previous.drawing
              ? {
                  ...previous,
                  drawing: { ...previous.drawing, layout: previous.drawing.layout + 1 },
                }
              : previous,
          );
        } catch {
          store.set((previous) => ({ drawing: null, failed: previous.drawing?.snapshot ?? null }));
        }
      }, RELAYOUT_DELAY_MS);
    });
    observer.observe(host);
    return () => {
      clearTimeout(timer);
      observer.disconnect();
    };
  }, [renderer, store]);

  const { drawing } = state;
  const status = drawing
    ? "ready"
    : loadFailed || state.failed === snapshot
      ? "failed"
      : "rendering";
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
  // maquetación. Su medida (#276) va aquí, con el cálculo: un render que React descarta (o el
  // doble de StrictMode en desarrollo) la anota dos veces; el script de medida toma la última.
  const noteMap = useMemo(
    () =>
      notesSelectable && score && drawn && aligned && layout >= 0
        ? timeStage("mapa", sessionId, drawn.seq, () =>
            buildNoteMap(drawn.transcription, (slot) => score.measureFigures(slot)),
          )
        : null,
    [notesSelectable, score, drawn, aligned, layout, sessionId],
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
  const ownKey = ours && ours.seq === drawn?.seq ? anchorKey(ours.anchor) : null;
  // La última nota marcada sobre el dibujo. Si la selección pasa a un estado que aún no está
  // dibujado (una orden guardada deja elegido su evento antes de que llegue el dibujo nuevo), su
  // marca se queda donde estaba hasta que llega, y entonces pasa a la nota que corresponde (#276).
  const [held, setHeld] = useState<{ seq: number; key: string } | null>(null);
  if (ownKey !== null && drawn && (held?.seq !== drawn.seq || held.key !== ownKey)) {
    setHeld({ seq: drawn.seq, key: ownKey });
  }
  const ahead = ours !== null && drawn !== null && ours.seq > drawn.seq;
  const noteKey = ownKey ?? (ahead && held?.seq === drawn.seq ? held.key : null);
  const chosen = selectable?.find((candidate) => candidate.key === noteKey) ?? null;
  // Lo que es la nota elegida sale del estado actual. Si la selección ya va por delante de él (la
  // orden guardada eligió en el estado nuevo, que aún no llega a la vista), es la nota que sigue
  // marcada en el que se ve: la barra no se queda sin nota elegida ni un instante (#276).
  const shownAnchor =
    ours?.seq === snapshot.seq
      ? ours.anchor
      : ahead && drawn.seq === snapshot.seq
        ? (chosen?.anchor ?? null)
        : null;
  const located = selectable && shownAnchor ? eventAt(snapshot.transcription, shownAnchor) : null;
  // Un hueco solo se corrige si la vista lo ofrece, con su marca (ADR-0058): uno que OSMD no
  // guarda no se elige, aunque lo deje elegido un borrado o deshacer.
  const found =
    located?.event.hidden === true && shownAnchor
      ? selectable?.some((candidate) => candidate.key === anchorKey(shownAnchor))
        ? located
        : null
      : located;
  const target: EditTarget | null = shownAnchor && found ? { anchor: shownAnchor, ...found } : null;
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
  // Por su id y no por el ref: se entrega a la barra de corrección durante el render.
  const stageId = useId();
  /** Lleva el foco a la partitura, si es un control (con notas que elegir). */
  const focusScore = () => {
    const stage = document.getElementById(stageId);
    if (stage?.getAttribute("role") !== "application") return false;
    stage.focus({ preventScroll: true });
    return true;
  };
  const selectionRef = useRef<HTMLDivElement>(null);
  // Al moverse con el teclado o los botones, la nota elegida se trae a la vista; al tocarla, no.
  const revealRef = useRef(false);
  const choose = (candidate: SelectableEvent | null, reveal: boolean) => {
    if (!candidate || !drawn) return;
    // Si la tecla no movió la selección (un borde), no queda nada pendiente de traer a la vista.
    revealRef.current = reveal && candidate.key !== noteKey;
    select({ sessionId, seq: drawn.seq, anchor: candidate.anchor });
  };
  // Mientras llega el dibujo de otro estado se elige sobre el que se ve, en su estado: la vista
  // lleva después la selección al estado nuevo (ADR-0011 §2).
  const move = (how: Move) => {
    if (selectable) choose(moveSelection(selectable, noteKey, how), true);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!selectable) return;
    // Esc sale del modo «Escribir» antes que quitar la nota elegida (#350).
    if (writing && event.key === "Escape") {
      event.preventDefault();
      writing.onExit();
      return;
    }
    // Mayús, sin mover el ratón, ya cambia el fantasma: el clic añadirá la nota al acorde.
    if (writing && event.key === "Shift") {
      shiftGhost(true);
      return;
    }
    const command = onCommand ? editCommand(event) : null;
    if (command) {
      event.preventDefault();
      // Mantener la tecla pulsada no encadena ediciones: cuántas salieran dependería de lo que
      // tarde cada una en guardarse, y cada una cuenta en el log (D38).
      if (!event.repeat) onCommand?.(command, target);
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
  // Escribir con el ratón (#350): la nota fantasma sigue al puntero y el clic la escribe. Solo
  // sobre el estado que se ve dibujado: las anclas del mapa de notas son de ese estado.
  const [ghost, setGhost] = useState<Ghost | null>(null);
  // El último punto del puntero sobre la partitura, aunque el fantasma no cambiara al pasar por él.
  const pointerAt = useRef<Ghost["at"] | null>(null);
  // El puntero del último toque: donde el clic no es un PointerEvent, dice si fue el dedo.
  const pointerKind = useRef<string | null>(null);
  const shiftGhost = (shift: boolean) => {
    setGhost((previous) =>
      previous ? ghostOf(previous.spot, previous.pitch, shift, previous.seq, previous.at) : null,
    );
  };
  const onKeyUp = (event: KeyboardEvent<HTMLDivElement>) => {
    if (writing && event.key === "Shift") shiftGhost(false);
  };
  const writable =
    writing !== null &&
    selectable !== null &&
    score !== null &&
    drawn !== null &&
    drawn.seq === snapshot.seq;
  const ghostAt = (
    stage: HTMLElement,
    clientX: number,
    clientY: number,
    shift: boolean,
  ): Ghost | null => {
    if (!writable) return null;
    const origin = stage.getBoundingClientRect();
    const at = { x: clientX - origin.left, y: clientY - origin.top };
    // Las cabezas dibujadas, con su altura, ajustan las líneas de cada compás.
    const noteSteps = (event: SelectableEvent) =>
      event.event.kind === "note" && !event.grace
        ? staffSteps(activeClef(snapshot.transcription, event.anchor), event.event.pitch)
        : null;
    const spot = writeSpotAt(selectable, at.x, at.y, (slot) => score.measureBox(slot), noteSteps);
    if (!spot) return null;
    const place = spot.aim.event.anchor;
    const clef = activeClef(snapshot.transcription, place);
    // Sobre una nota, en su misma línea o espacio, se conserva su alteración: cambiar solo la
    // figura de un Fa#4 en Do mayor no lo deja en Fa4.
    const aimed = spot.aim.event.event;
    const own =
      spot.aim.kind === "replace" &&
      aimed.kind === "note" &&
      staffSteps(clef, aimed.pitch) === spot.steps
        ? aimed.pitch
        : null;
    const pitch = own ?? staffPitch(clef, activeFifths(snapshot.transcription, place), spot.steps);
    return pitch ? ghostOf(spot, pitch, shift, snapshot.seq, at) : null;
  };
  const onPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!writable || event.pointerType === "touch") return;
    const next = ghostAt(event.currentTarget, event.clientX, event.clientY, event.shiftKey);
    pointerAt.current = next?.at ?? null;
    setGhost((previous) =>
      previous?.key === next?.key &&
      previous?.seq === next?.seq &&
      previous?.spot.aim.x === next?.spot.aim.x
        ? previous
        : next,
    );
  };
  const onPointerLeave = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.pointerType === "touch") return;
    pointerAt.current = null;
    setGhost(null);
  };
  const onPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    pointerKind.current = event.pointerType;
  };
  const writeAt = (event: MouseEvent<HTMLDivElement>, mode: WritingMode) => {
    const stage = event.currentTarget;
    stage.focus({ preventScroll: true });
    let next = ghostAt(stage, event.clientX, event.clientY, event.shiftKey);
    if (!next) {
      setGhost(null);
      return;
    }
    const pointer = (event.nativeEvent as Partial<PointerEvent>).pointerType ?? pointerKind.current;
    // Con el ratón, el clic escribe lo que enseña el fantasma: en el borde entre dos alturas, el
    // punto del clic, redondeado de otra forma, podría dar la de al lado.
    const last = pointerAt.current;
    if (
      pointer !== "touch" &&
      ghost?.seq === next.seq &&
      last !== null &&
      Math.abs(last.x - next.at.x) <= GHOST_SLACK_PX &&
      Math.abs(last.y - next.at.y) <= GHOST_SLACK_PX
    ) {
      next = ghostOf(ghost.spot, ghost.pitch, event.shiftKey, ghost.seq, ghost.at);
    }
    // Con el dedo no hay fantasma antes de tocar: el primer toque lo enseña y el segundo, en el
    // mismo sitio, escribe.
    const shown = ghost?.key === next.key && ghost.seq === next.seq;
    setGhost(next);
    if ((pointer === "touch" && !shown) || mode.wait !== null) return;
    const found = eventAt(snapshot.transcription, next.spot.aim.event.anchor);
    if (!found) return;
    const target: EditTarget = { anchor: next.spot.aim.event.anchor, ...found };
    mode.onWrite(
      next.spot.aim.kind === "insert"
        ? { kind: "insert", target, pitch: next.pitch, end: next.spot.aim.end }
        : { kind: "replace", target, pitch: next.pitch, chord: next.chord },
    );
  };

  const onClick = (event: MouseEvent<HTMLDivElement>) => {
    if (!selectable || !score) return;
    if (writing) {
      writeAt(event, writing);
      return;
    }
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

  // Lo que deja elegido una inserción o un borrado (ADR-0033) se trae a la vista, como un
  // movimiento con el teclado: un borrado puede dejar elegida una nota de otro sistema. Si ya se
  // ve, no se mueve nada (`nearest`).
  const placedBy = ours?.placedBy;
  useEffect(() => {
    if (placedBy !== undefined) revealRef.current = true;
  }, [placedBy]);
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
  // de valor (se corrigió), no se vuelve a anunciar: lo dice la barra de corrección. Tras insertar
  // o borrar, la misma ancla puede ser otro evento: el que dejó elegido la edición se anuncia.
  const spoken = description?.spoken ?? null;
  const chosenKey = target ? `${anchorKey(target.anchor)}|${String(ours?.placedBy ?? "")}` : null;
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
  // La selección se ofrece mientras la partitura no falle y se puedan elegir notas.
  const selectionShown = status !== "failed" && notesSelectable;
  const selection: SelectionControls = {
    status: selectionStatus,
    description,
    announcement,
    keysId,
    onPrevious: () => {
      move("previous");
    },
    onNext: () => {
      move("next");
    },
    onClear: () => {
      stageRef.current?.focus({ preventScroll: true });
      clearSelection();
    },
  };

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
      // En la mesa (#341) la partitura se desplaza en su panel: se mira lo que se ve de él.
      const view = scrollViewOf(layer);
      if (top + previous.box.height <= view.top || top >= view.bottom) return;
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
        // La selección va por delante del dibujo: el estado nuevo está a punto de llegar.
        "aria-busy": ahead || undefined,
        onKeyDown,
        onClick,
        onKeyUp,
        onPointerMove,
        onPointerLeave,
        onPointerDown,
        "data-writing": writing ? "true" : undefined,
      }
    : {};

  return (
    <>
      {/* Sin barra de corrección, la selección va en su propia franja. */}
      {selectionShown && !editor && <SelectionBar {...selection} />}
      {editor && (
        <EditorSlot
          render={editor}
          target={target}
          context={{
            available: selectable !== null,
            focusScore,
            selection: selectionShown ? selection : undefined,
          }}
        />
      )}
      <div className="notation" data-state={status}>
        <div className="notation__stage" id={stageId} ref={stageRef} {...stageProps}>
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
              {/* Los huecos de una voz (ADR-0058): una trama de tinta donde OSMD guarda su silencio
                  transparente, para que se vean y se puedan elegir sin dibujarlos en la partitura. */}
              {selectable
                ?.filter((candidate) => candidate.gap)
                .flatMap((candidate) =>
                  candidate.boxes.map((box, index) => (
                    <div
                      key={`hueco:${candidate.key}:${String(index)}`}
                      className="notation__gap"
                      data-key={candidate.key}
                      style={{ left: box.left, top: box.top, width: box.width, height: box.height }}
                    />
                  )),
                )}
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
          {writing && writable && ghost?.seq === drawn.seq && (
            <WriteGhost
              spot={ghost.spot}
              pitch={ghost.pitch}
              figure={writing.figure}
              dotted={writing.dotted}
              chord={ghost.chord}
              wait={writing.wait}
            />
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
              {findingsListed
                ? "La imagen original y la lista de posibles errores siguen disponibles."
                : "La imagen original sigue disponible."}{" "}
              Puede que la transcripción contenga algo que el visor no sabe dibujar.
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
