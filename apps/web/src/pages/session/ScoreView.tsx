import { useEffect, useMemo, useRef, useState } from "react";
import { slotKey, type MeasureMark } from "./findings";
import { renderScore, type Box, type RenderedScore } from "./osmd";

type RenderState =
  | { status: "rendering" }
  // `layout` cambia cada vez que OSMD vuelve a maquetar, para recolocar las marcas.
  | { status: "ready"; score: RenderedScore; layout: number }
  | { status: "failed" };

interface ScoreViewProps {
  /** MusicXML de un estado de la sesión: la vista se monta de nuevo si cambia. */
  xml: string;
  marks: readonly MeasureMark[];
  /** Compases de cada pentagrama en el `ScoreIR`: si OSMD dibuja otros, no se marca nada. */
  expectedMeasures: readonly number[];
  selectedKey: string | null;
  /** Avisa de si las marcas se pudieron situar sobre la partitura dibujada. */
  onPlacement?: (placed: boolean) => void;
}

function sameCounts(a: readonly number[], b: readonly number[]) {
  return a.length === b.length && a.every((count, index) => count === b[index]);
}

/** Cajas de los compases marcados, o null si no se pueden situar con seguridad (ADR-0021). */
function placeMarks(
  score: RenderedScore,
  marks: readonly MeasureMark[],
  expected: readonly number[],
): Map<string, Box> | null {
  if (!sameCounts(score.measuresPerStaff(), expected)) return null;
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
  marks,
  expectedMeasures,
  selectedKey,
  onPlacement,
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
  const boxes = useMemo(
    () => (score && layout >= 0 ? placeMarks(score, marks, expectedMeasures) : null),
    [score, layout, marks, expectedMeasures],
  );

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

  const flagged = marks.map((mark) => mark.measureNumber).join(", ");
  const label =
    boxes && marks.length > 0
      ? `Partitura transcrita. Compases con posibles errores: ${flagged}.`
      : "Partitura transcrita.";

  return (
    <div className="notation" data-state={state.status}>
      <div className="notation__stage">
        {boxes && (
          <div className="notation__marks" ref={marksRef} aria-hidden="true">
            {marks.map((mark) => {
              const box = boxes.get(mark.key);
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
          </div>
        )}
        {/* Solo es una imagen con nombre cuando hay partitura dibujada. */}
        <div
          className="notation__host"
          ref={hostRef}
          role={state.status === "ready" ? "img" : undefined}
          aria-label={state.status === "ready" ? label : undefined}
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
          No se pudieron situar los posibles errores sobre la partitura dibujada: están en la lista.
        </p>
      )}
    </div>
  );
}
