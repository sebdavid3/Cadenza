import {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import { PixelIcon } from "../../components/PixelIcon";

/** Una imagen mucho más ancha que alta (un incipit de un pentagrama) no se encoge en móvil. */
const WIDE_RATIO = 3;

/** Acercamientos sobre el ajuste al ancho; por debajo del ancho, la página entera. */
const ZOOMS = [1, 1.5, 2, 3, 4] as const;
type Zoom = "page" | (typeof ZOOMS)[number];

interface ScanFigureProps {
  blob: Blob | null;
  status: "loading" | "ready" | "error";
  /** Id del panel, para el divisor que cambia su ancho. */
  id?: string;
}

function zoomIn(zoom: Zoom): Zoom {
  if (zoom === "page") return 1;
  return ZOOMS.find((step) => step > zoom) ?? zoom;
}

function zoomOut(zoom: Zoom): Zoom {
  if (zoom === "page") return zoom;
  return [...ZOOMS].reverse().find((step) => step < zoom) ?? "page";
}

const readout = (zoom: Zoom) => (zoom === "page" ? "Página" : `${String(zoom * 100)} %`);

/** El punto del marco que se ve en el centro, en proporción de lo que se puede desplazar. */
function centerOf(frame: HTMLElement): { x: number; y: number } | null {
  if (frame.scrollWidth <= 0 || frame.scrollHeight <= 0) return null;
  return {
    x: (frame.scrollLeft + frame.clientWidth / 2) / frame.scrollWidth,
    y: (frame.scrollTop + frame.clientHeight / 2) / frame.scrollHeight,
  };
}

/** Si el marco tiene algo que mover: la imagen acercada no cabe en él. */
function overflows(frame: HTMLElement): boolean {
  return frame.scrollWidth > frame.clientWidth || frame.scrollHeight > frame.clientHeight;
}

interface ScanToolProps {
  label: string;
  enabled: boolean;
  pressed?: boolean;
  onRun: () => void;
  children: ReactNode;
}

/** Un botón del zoom: lo que no se puede ahora lleva el filete discontinuo y no hace nada. */
function ScanTool({ label, enabled, pressed, onRun, children }: ScanToolProps) {
  return (
    <button
      type="button"
      className="scan__tool"
      aria-label={label}
      title={label}
      aria-disabled={!enabled}
      aria-pressed={pressed}
      onClick={() => {
        if (enabled) onRun();
      }}
    >
      {children}
    </button>
  );
}

/**
 * Imagen original de la sesión, en su panel de la mesa de corrección (#341). `GET
 * /sessions/{id}/image` exige Bearer, así que llega como Blob (handoff §5.6); la URL se crea al
 * montar y se revoca al desmontar. Es una referencia global: HOMR no da coordenadas, así que no se
 * marca nada sobre ella (INV-0001).
 *
 * Se ve ajustada al ancho, a página entera o acercada hasta el 400 %; se mueve arrastrándola o, con
 * el marco enfocado, con las flechas, y + y − acercan y alejan, como Ctrl y la rueda. En una
 * columna se puede ocultar para dejar sitio a la partitura.
 */
export function ScanFigure({ blob, status, id }: ScanFigureProps) {
  const captionId = useId();
  const frameId = useId();
  const imageRef = useRef<HTMLImageElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const [wide, setWide] = useState(false);
  const [zoom, setZoom] = useState<Zoom>(1);
  const [collapsed, setCollapsed] = useState(false);
  const [dragging, setDragging] = useState(false);
  const ready = status === "ready" && blob !== null;

  useLayoutEffect(() => {
    const element = imageRef.current;
    if (!blob || !element) return;
    const url = URL.createObjectURL(blob);
    element.src = url;
    return () => {
      element.removeAttribute("src");
      URL.revokeObjectURL(url);
    };
  }, [blob]);

  // Al acercar o alejar, el punto del centro sigue en el centro: se apunta antes de cambiar y se
  // vuelve a él cuando la imagen tiene su tamaño nuevo.
  const center = useRef<{ x: number; y: number } | null>(null);
  const change = (next: Zoom) => {
    const frame = frameRef.current;
    center.current = frame ? centerOf(frame) : null;
    setZoom(next);
  };
  useLayoutEffect(() => {
    const frame = frameRef.current;
    const point = center.current;
    center.current = null;
    if (!frame || !point) return;
    frame.scrollLeft = point.x * frame.scrollWidth - frame.clientWidth / 2;
    frame.scrollTop = point.y * frame.scrollHeight - frame.clientHeight / 2;
  }, [zoom]);

  // Ctrl (o Cmd) y la rueda acercan y alejan; sin ellos, la rueda desplaza la imagen. React
  // registra la rueda como pasiva, así que se escucha a mano para poder evitar el zoom de página.
  useEffect(() => {
    const frame = frameRef.current;
    if (!frame || !ready) return;
    const onWheel = (event: WheelEvent) => {
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      if (event.deltaY === 0) return;
      center.current = centerOf(frame);
      setZoom((current) => (event.deltaY < 0 ? zoomIn(current) : zoomOut(current)));
    };
    frame.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      frame.removeEventListener("wheel", onWheel);
    };
  }, [ready]);

  // Arrastrar con el ratón mueve la imagen acercada; con el dedo, la desplaza el navegador.
  const drag = useRef<{ id: number; x: number; y: number } | null>(null);
  const endDrag = (frame: HTMLElement, pointerId: number) => {
    drag.current = null;
    if ("releasePointerCapture" in frame && frame.hasPointerCapture(pointerId)) {
      frame.releasePointerCapture(pointerId);
    }
    setDragging(false);
  };

  let body: ReactNode;
  if (status === "error") {
    body = (
      <div className="scan scan--empty" id={frameId}>
        <p>No se pudo cargar la imagen original.</p>
      </div>
    );
  } else if (!blob) {
    body = (
      <div className="scan scan--empty" id={frameId} aria-busy="true">
        <p className="label">Cargando la imagen…</p>
      </div>
    );
  } else {
    body = (
      <div
        ref={frameRef}
        id={frameId}
        className="scan"
        data-wide={wide}
        data-zoom={zoom === "page" ? "page" : zoom === 1 ? "width" : "zoom"}
        data-dragging={dragging}
        style={
          zoom === "page" || zoom === 1
            ? undefined
            : ({ "--scan-zoom": String(zoom) } as CSSProperties)
        }
        tabIndex={0}
        role="group"
        aria-label="Imagen original: se mueve con las flechas o arrastrándola; + y − acercan y alejan"
        onKeyDown={(event) => {
          if (event.ctrlKey || event.metaKey || event.altKey) return;
          const next =
            event.key === "+" || event.key === "="
              ? zoomIn(zoom)
              : event.key === "-" || event.key === "_"
                ? zoomOut(zoom)
                : event.key === "0"
                  ? 1
                  : null;
          if (next === null) return;
          event.preventDefault();
          if (next !== zoom) change(next);
        }}
        onPointerDown={(event) => {
          const frame = event.currentTarget;
          if (event.pointerType !== "mouse" || event.button !== 0 || !overflows(frame)) return;
          drag.current = { id: event.pointerId, x: event.clientX, y: event.clientY };
          if ("setPointerCapture" in frame) frame.setPointerCapture(event.pointerId);
          setDragging(true);
        }}
        onPointerMove={(event) => {
          const start = drag.current;
          if (start?.id !== event.pointerId) return;
          const frame = event.currentTarget;
          frame.scrollLeft -= event.clientX - start.x;
          frame.scrollTop -= event.clientY - start.y;
          drag.current = { id: start.id, x: event.clientX, y: event.clientY };
        }}
        onPointerUp={(event) => {
          if (drag.current?.id !== event.pointerId) return;
          endDrag(event.currentTarget, event.pointerId);
        }}
        onPointerCancel={(event) => {
          endDrag(event.currentTarget, event.pointerId);
        }}
      >
        <img
          ref={imageRef}
          alt="Imagen original de la partitura"
          decoding="async"
          draggable={false}
          onLoad={(event) => {
            const { naturalWidth, naturalHeight } = event.currentTarget;
            setWide(naturalHeight > 0 && naturalWidth / naturalHeight > WIDE_RATIO);
          }}
        />
      </div>
    );
  }

  return (
    <section
      id={id}
      className="sheet sheet--scan"
      aria-labelledby={captionId}
      data-collapsed={collapsed}
    >
      <div className="sheet__head">
        <h2 className="label sheet__caption" id={captionId}>
          Imagen original
        </h2>
        <div className="scan__tools" role="group" aria-label="Zoom de la imagen">
          <ScanTool
            label="Alejar"
            enabled={ready && zoomOut(zoom) !== zoom}
            onRun={() => {
              change(zoomOut(zoom));
            }}
          >
            <PixelIcon name="minus" />
          </ScanTool>
          <span className="label scan__zoom" role="status">
            {readout(zoom)}
          </span>
          <ScanTool
            label="Acercar"
            enabled={ready && zoomIn(zoom) !== zoom}
            onRun={() => {
              change(zoomIn(zoom));
            }}
          >
            <PixelIcon name="plus" />
          </ScanTool>
          <ScanTool
            label="Ajustar al ancho"
            enabled={ready}
            pressed={zoom === 1}
            onRun={() => {
              change(1);
            }}
          >
            <span className="scan__tool-word">Ancho</span>
          </ScanTool>
          <ScanTool
            label="Página entera"
            enabled={ready}
            pressed={zoom === "page"}
            onRun={() => {
              change("page");
            }}
          >
            <span className="scan__tool-word">Página</span>
          </ScanTool>
        </div>
        <button
          type="button"
          className="scan__toggle"
          aria-expanded={!collapsed}
          aria-controls={frameId}
          aria-label={collapsed ? "Ver la imagen" : "Ocultar la imagen"}
          onClick={() => {
            setCollapsed((value) => !value);
          }}
        >
          {collapsed ? "Ver" : "Ocultar"}
        </button>
      </div>
      {body}
    </section>
  );
}
