import { useEffect, useRef, useState } from "react";
import {
  choosePortrait,
  coverCrop,
  DOT_PITCH,
  dotRadius,
  EYE_LINE,
  portraitAt,
  type Portrait,
} from "./portraits";
import "./login.css";

// La impresión avanza por bandas de filas, a saltos, como el cabezal de una imprenta: el único
// momento animado de la vista.
const PRINT_DURATION_MS = 1400;
const PRINT_STEPS = 28;
// Por debajo de este radio el punto no se ve: se deja el papel.
const MIN_RADIUS = 0.15;

function mediaMatches(query: string): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(query).matches;
}

/** Sin `matchMedia` no se sabe si se pidió menos movimiento: se imprime de una vez. */
function motionAllowed(): boolean {
  return (
    typeof window.matchMedia === "function" && !mediaMatches("(prefers-reduced-motion: reduce)")
  );
}

function tokenColor(element: Element, name: string, fallback: string): string {
  return getComputedStyle(element).getPropertyValue(name).trim() || fallback;
}

/** A qué altura del panel caen los ojos: la hoja lo fija con `--portrait-eye-line`. */
function eyeLine(element: Element): number {
  const value = Number.parseFloat(
    getComputedStyle(element).getPropertyValue("--portrait-eye-line"),
  );
  return Number.isFinite(value) && value > 0 && value < 1 ? value : EYE_LINE;
}

/** La luminancia (0–1) de cada celda: la imagen recortada al panel, reducida a un píxel por punto. */
function sampleCells(
  image: HTMLImageElement,
  portrait: Portrait,
  cols: number,
  rows: number,
  eyes: number,
): Float32Array | null {
  const sampler = document.createElement("canvas");
  sampler.width = cols;
  sampler.height = rows;
  const context = sampler.getContext("2d", { willReadFrequently: true });
  if (!context) return null;
  const crop = coverCrop(
    cols * DOT_PITCH,
    rows * DOT_PITCH,
    image.naturalWidth,
    image.naturalHeight,
    portrait.focus,
    eyes,
  );
  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = "high";
  context.drawImage(image, crop.sx, crop.sy, crop.sw, crop.sh, 0, 0, cols, rows);
  const { data } = context.getImageData(0, 0, cols, rows);
  const cells = new Float32Array(cols * rows);
  for (let cell = 0; cell < cells.length; cell += 1) cells[cell] = (data[cell * 4] ?? 255) / 255;
  return cells;
}

/**
 * El panel del acceso (#392): la trama de tinta de siempre, que un lienzo encima imprime, banda a
 * banda, como el retrato de un compositor en semitono, uno por visita y en rotación, con su pie de
 * lámina. El retrato es decorativo: el titular sigue siendo el `h1` de la vista. Lo que no se ha
 * impreso deja ver la trama de CSS; sin canvas o sin la imagen, queda la trama, y con colores
 * forzados no se descarga el retrato.
 */
export function AccessPanel({ title }: { title: string }) {
  const [index] = useState(() => choosePortrait());
  const portrait = portraitAt(index);
  const [printed, setPrinted] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context || mediaMatches("(forced-colors: active)")) return;

    const image = new Image();
    const paper = tokenColor(canvas, "--color-paper", "#f0eff2");
    const ink = tokenColor(canvas, "--color-ink", "#0a0a0a");
    let loaded = false;
    let disposed = false;
    let cells: Float32Array | null = null;
    let layout = "";
    let progress = 0;
    let printedRows = 0;
    let printFrame = 0;
    let redrawFrame = 0;

    // Imprime las filas que tocan según `progress` y aún no están en el lienzo: papel en su banda
    // y, encima, sus puntos. Si el panel cambió de tamaño o de densidad de píxeles, vacía el lienzo
    // y vuelve a imprimir desde arriba.
    const draw = () => {
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      if (width === 0 || height === 0) return;
      const ratio = window.devicePixelRatio || 1;
      const cols = Math.ceil(width / DOT_PITCH);
      const rows = Math.ceil(height / DOT_PITCH);
      const eyes = eyeLine(canvas);
      const pixelWidth = Math.round(width * ratio);
      const pixelHeight = Math.round(height * ratio);
      const key = `${String(pixelWidth)}×${String(pixelHeight)}@${String(eyes)}`;
      if (key !== layout) {
        layout = key;
        cells = sampleCells(image, portrait, cols, rows, eyes);
        canvas.width = pixelWidth;
        canvas.height = pixelHeight;
        printedRows = 0;
      }
      if (!cells) return;
      const target = Math.ceil(rows * progress);
      if (target <= printedRows) return;
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.fillStyle = paper;
      context.fillRect(0, printedRows * DOT_PITCH, width, (target - printedRows) * DOT_PITCH);
      context.fillStyle = ink;
      context.beginPath();
      for (let row = printedRows; row < target; row += 1) {
        const y = row * DOT_PITCH + DOT_PITCH / 2;
        for (let col = 0; col < cols; col += 1) {
          const radius = dotRadius(cells[row * cols + col] ?? 1);
          if (radius < MIN_RADIUS) continue;
          const x = col * DOT_PITCH + DOT_PITCH / 2;
          context.moveTo(x + radius, y);
          context.arc(x, y, radius, 0, Math.PI * 2);
        }
      }
      context.fill();
      printedRows = target;
    };

    const redraw = () => {
      if (!loaded) return;
      cancelAnimationFrame(redrawFrame);
      redrawFrame = requestAnimationFrame(draw);
    };

    let start = 0;
    let lastStep = 0;
    const print = (now: number) => {
      if (disposed) return;
      start ||= now;
      const step = Math.min(
        PRINT_STEPS,
        Math.floor(((now - start) / PRINT_DURATION_MS) * PRINT_STEPS) + 1,
      );
      if (step !== lastStep) {
        lastStep = step;
        progress = step / PRINT_STEPS;
        draw();
      }
      if (step < PRINT_STEPS) printFrame = requestAnimationFrame(print);
      else setPrinted(true);
    };

    image.onload = () => {
      if (disposed) return;
      loaded = true;
      if (motionAllowed()) {
        printFrame = requestAnimationFrame(print);
        return;
      }
      progress = 1;
      draw();
      setPrinted(true);
    };

    // Al pasar la ventana a una pantalla de otra densidad, el tamaño no cambia: se vigila aparte.
    let ratioQuery: MediaQueryList | null = null;
    const watchRatio = () => {
      if (typeof window.matchMedia !== "function") return;
      ratioQuery = window.matchMedia(`(resolution: ${String(window.devicePixelRatio)}dppx)`);
      ratioQuery.addEventListener("change", onRatioChange);
    };
    const onRatioChange = () => {
      ratioQuery?.removeEventListener("change", onRatioChange);
      watchRatio();
      redraw();
    };
    watchRatio();

    const observer = typeof ResizeObserver === "function" ? new ResizeObserver(redraw) : null;
    observer?.observe(canvas);
    image.decoding = "async";
    image.src = portrait.src;

    return () => {
      disposed = true;
      image.onload = null;
      cancelAnimationFrame(printFrame);
      cancelAnimationFrame(redrawFrame);
      ratioQuery?.removeEventListener("change", onRatioChange);
      observer?.disconnect();
    };
  }, [portrait]);

  return (
    <div className="login__plate">
      <figure className="portrait" aria-hidden="true">
        <canvas ref={canvasRef} className="portrait__dots" />
        {printed && (
          <figcaption className="portrait__caption">
            <span className="portrait__name">{portrait.name}</span>
            <span className="portrait__credit">
              {portrait.lifespan} · {portrait.credit}
            </span>
          </figcaption>
        )}
      </figure>
      <h1 className="login__title">
        <span>{title}</span>
      </h1>
    </div>
  );
}
