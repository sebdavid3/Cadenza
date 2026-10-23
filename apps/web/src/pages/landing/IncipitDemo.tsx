import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { CORRECTED, flagRegion, GEOMETRY, OMR_READING } from "./incipit";
import { IncipitStaff } from "./IncipitStaff";
import { IncipitScan } from "./IncipitScan";

type View = "image" | "notation";
type Phase = "waiting" | "reading" | "done";

const READ_DURATION_MS = 2400;
// La lectura avanza en saltos de columna, como un escáner, no en un deslizamiento continuo.
const READ_EASING = "steps(56, end)";

function motionAllowed(): boolean {
  if (typeof window.matchMedia !== "function") return false;
  return !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function canAnimate(element: Element | null): element is HTMLElement {
  return element instanceof HTMLElement && typeof element.animate === "function";
}

const flag = flagRegion();
const labelStyle = {
  left: `${String((flag.x / GEOMETRY.width) * 100)}%`,
  top: `${String((flag.y / GEOMETRY.height) * 100)}%`,
};

/**
 * Demostración de la landing: el mismo incipit sintético como imagen escaneada y como
 * notación. Al entrar en pantalla, una lectura recorre la imagen y la convierte en
 * notación; el compás 3 queda tramado porque suma cuatro tiempos en un 3/4.
 */
export function IncipitDemo() {
  const [view, setView] = useState<View>("notation");
  const [phase, setPhase] = useState<Phase>("done");
  const stageRef = useRef<HTMLDivElement>(null);
  const notationRef = useRef<HTMLDivElement>(null);
  const scanLineRef = useRef<HTMLDivElement>(null);

  const read = useCallback(() => {
    const notation = notationRef.current;
    const scanLine = scanLineRef.current;
    if (!motionAllowed() || !canAnimate(notation) || !canAnimate(scanLine)) {
      setPhase("done");
      return;
    }
    setPhase("reading");
    const timing = { duration: READ_DURATION_MS, easing: READ_EASING, fill: "forwards" as const };
    notation.animate([{ clipPath: "inset(0 100% 0 0)" }, { clipPath: "inset(0 0% 0 0)" }], timing);
    // La línea de lectura no se queda: al terminar vuelve a su estado oculto.
    const sweep = scanLine.animate(
      [
        { left: "0%", opacity: 1 },
        { left: "100%", opacity: 1 },
      ],
      { duration: READ_DURATION_MS, easing: READ_EASING },
    );
    sweep.onfinish = () => {
      setPhase("done");
    };
  }, []);

  // Antes del primer pintado: si hay movimiento, la notación espera a la lectura.
  useLayoutEffect(() => {
    if (motionAllowed() && "IntersectionObserver" in window && canAnimate(notationRef.current)) {
      setPhase("waiting");
    }
  }, []);

  useEffect(() => {
    if (phase !== "waiting") return;
    const stage = stageRef.current;
    if (!stage) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          observer.disconnect();
          read();
        }
      },
      { threshold: 0.4 },
    );
    observer.observe(stage);
    return () => {
      observer.disconnect();
    };
  }, [phase, read]);

  const show = (next: View) => {
    setView(next);
    if (next === "notation") read();
  };

  return (
    <section className="demo" aria-labelledby="demo-title" data-view={view} data-phase={phase}>
      <h2 id="demo-title" className="visually-hidden">
        Demostración con un incipit sintético
      </h2>
      <p className="visually-hidden">
        Ilustración, no una transcripción real: un incipit en 3/4 de cuatro compases. En «Imagen» se
        ve como una partitura escaneada; en «Notación», como lo transcribe el motor. El compás 3
        suma cuatro tiempos en un compás de tres y Cadenza lo señala para que lo revises.
      </p>
      <div className="demo__bar">
        <div className="demo__tabs" role="group" aria-label="Vista de la demostración">
          <button
            type="button"
            aria-pressed={view === "image"}
            onClick={() => {
              show("image");
            }}
          >
            Imagen
          </button>
          <button
            type="button"
            aria-pressed={view === "notation"}
            onClick={() => {
              show("notation");
            }}
          >
            Notación
          </button>
        </div>
        <span className="label demo__meta">Incipit sintético · ilustración</span>
      </div>
      <div className="demo__stage" ref={stageRef}>
        <IncipitScan className="demo__scan" measures={CORRECTED} />
        <div className="demo__notation" ref={notationRef}>
          <IncipitStaff measures={OMR_READING} flagged />
        </div>
        <div className="demo__scanline" ref={scanLineRef} aria-hidden="true" />
        <p className="label demo__finding" style={labelStyle} aria-hidden="true">
          Compás 3 · suma 4 tiempos en un 3/4
        </p>
      </div>
    </section>
  );
}
