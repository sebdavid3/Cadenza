import { useRef, useState } from "react";
import { clampShare, SHARE_DEFAULT, SHARE_MAX, SHARE_MIN } from "./deskShare";

const STEP = 0.05;

interface DeskDividerProps {
  share: number;
  onShare: (share: number) => void;
  /** Al soltar o al terminar con el teclado: el reparto que se recuerda. */
  onCommit?: (share: number) => void;
  /** Id del panel de la imagen, cuyo ancho cambia. */
  controls: string;
}

/**
 * Divisor entre la imagen original y la partitura (#341): un separador de ARIA que se arrastra
 * con el puntero sobre el ancho de la mesa (su elemento padre) o se mueve con las flechas, Inicio
 * y Fin. Con doble clic vuelve al reparto inicial.
 */
export function DeskDivider({ share, onShare, onCommit, controls }: DeskDividerProps) {
  const pointer = useRef<number | null>(null);
  const [dragging, setDragging] = useState(false);
  const percent = Math.round(share * 100);

  const set = (next: number, commit: boolean) => {
    const value = clampShare(next);
    onShare(value);
    if (commit) onCommit?.(value);
  };

  const fromPointer = (element: HTMLElement, clientX: number) => {
    const desk = element.parentElement?.getBoundingClientRect();
    if (!desk || desk.width <= 0) return share;
    return (clientX - desk.left) / desk.width;
  };

  const stop = (element: HTMLElement, pointerId: number) => {
    pointer.current = null;
    if ("releasePointerCapture" in element && element.hasPointerCapture(pointerId)) {
      element.releasePointerCapture(pointerId);
    }
    setDragging(false);
  };

  return (
    <div
      className="desk-divider"
      role="separator"
      aria-orientation="vertical"
      aria-label="Ancho de la imagen"
      aria-controls={controls}
      aria-valuenow={percent}
      aria-valuemin={Math.round(SHARE_MIN * 100)}
      aria-valuemax={Math.round(SHARE_MAX * 100)}
      aria-valuetext={`La imagen ocupa el ${String(percent)} % del ancho`}
      tabIndex={0}
      title="Arrastra para repartir el ancho; doble clic para volver al inicial"
      data-dragging={dragging}
      onKeyDown={(event) => {
        const next =
          event.key === "ArrowLeft"
            ? share - STEP
            : event.key === "ArrowRight"
              ? share + STEP
              : event.key === "Home"
                ? SHARE_MIN
                : event.key === "End"
                  ? SHARE_MAX
                  : null;
        if (next === null) return;
        event.preventDefault();
        set(next, true);
      }}
      onPointerDown={(event) => {
        if (event.button !== 0) return;
        event.preventDefault();
        pointer.current = event.pointerId;
        const element = event.currentTarget;
        if ("setPointerCapture" in element) element.setPointerCapture(event.pointerId);
        setDragging(true);
      }}
      onPointerMove={(event) => {
        if (pointer.current !== event.pointerId) return;
        set(fromPointer(event.currentTarget, event.clientX), false);
      }}
      onPointerUp={(event) => {
        if (pointer.current !== event.pointerId) return;
        set(fromPointer(event.currentTarget, event.clientX), true);
        stop(event.currentTarget, event.pointerId);
      }}
      onPointerCancel={(event) => {
        if (pointer.current !== event.pointerId) return;
        onCommit?.(share);
        stop(event.currentTarget, event.pointerId);
      }}
      onDoubleClick={() => {
        set(SHARE_DEFAULT, true);
      }}
    >
      <span className="desk-divider__grip" aria-hidden="true" />
    </div>
  );
}
