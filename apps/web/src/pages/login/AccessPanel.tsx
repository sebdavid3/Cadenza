import { useEffect, useRef, useState } from "react";
import {
  coverCrop,
  DOT_PITCH,
  dotRadius,
  EYE_LINE,
  FIELD_DOT_RADIUS,
  pickPortraitIndex,
  PORTRAITS,
  portraitAt,
  readLastPortrait,
  rememberPortrait,
  type Portrait,
} from "./portraits";
import "./login.css";

// La impresión avanza por bandas de filas, a saltos, como el cabezal de una imprenta: el único
// momento animado de la vista.
const PRINT_DURATION_MS = 1400;
const PRINT_STEPS = 28;
// Por debajo de este radio el punto no se ve: se deja el papel.
const MIN_RADIUS = 0.15;

function motionAllowed(): boolean {
  if (typeof window.matchMedia !== "function") return false;
  return !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
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
 * El panel del acceso (#392): la trama de tinta de siempre, cuyos puntos crecen con la sombra
 * hasta formar el retrato de un compositor, uno por visita y en rotación, con su pie de lámina.
 * El retrato es decorativo: el titular sigue siendo el `h1` de la vista. Sin canvas, sin la
 * imagen o con colores forzados, queda la trama de CSS.
 */
export function AccessPanel({ title }: { title: string }) {
  const [index] = useState(() =>
    pickPortraitIndex(readLastPortrait(), PORTRAITS.length, Math.random),
  );
  const portrait = portraitAt(index);
  const [printed, setPrinted] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    rememberPortrait(index);
  }, [index]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;

    const image = new Image();
    const paper = tokenColor(canvas, "--color-paper", "#f0eff2");
    const ink = tokenColor(canvas, "--color-ink", "#0a0a0a");
    let loaded = false;
    let disposed = false;
    let cells: Float32Array | null = null;
    let grid = "";
    let progress = 0;
    let printFrame = 0;
    let resizeFrame = 0;

    // Dibuja la trama entera: las filas ya impresas con el retrato y el resto con el punto fijo.
    const paint = () => {
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      if (width === 0 || height === 0) return;
      const cols = Math.ceil(width / DOT_PITCH);
      const rows = Math.ceil(height / DOT_PITCH);
      const eyes = eyeLine(canvas);
      const layout = `${String(cols)}×${String(rows)}@${String(eyes)}`;
      if (grid !== layout) {
        grid = layout;
        cells = sampleCells(image, portrait, cols, rows, eyes);
      }
      if (!cells) return;
      const ratio = window.devicePixelRatio || 1;
      const pixelWidth = Math.round(width * ratio);
      const pixelHeight = Math.round(height * ratio);
      if (canvas.width !== pixelWidth) canvas.width = pixelWidth;
      if (canvas.height !== pixelHeight) canvas.height = pixelHeight;
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.fillStyle = paper;
      context.fillRect(0, 0, width, height);
      context.fillStyle = ink;
      context.beginPath();
      const printedRows = Math.ceil(rows * progress);
      for (let row = 0; row < rows; row += 1) {
        const y = row * DOT_PITCH + DOT_PITCH / 2;
        for (let col = 0; col < cols; col += 1) {
          const radius =
            row < printedRows ? dotRadius(cells[row * cols + col] ?? 1) : FIELD_DOT_RADIUS;
          if (radius < MIN_RADIUS) continue;
          const x = col * DOT_PITCH + DOT_PITCH / 2;
          context.moveTo(x + radius, y);
          context.arc(x, y, radius, 0, Math.PI * 2);
        }
      }
      context.fill();
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
        paint();
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
      paint();
      setPrinted(true);
    };

    const observer =
      typeof ResizeObserver === "function"
        ? new ResizeObserver(() => {
            if (!loaded) return;
            cancelAnimationFrame(resizeFrame);
            resizeFrame = requestAnimationFrame(paint);
          })
        : null;
    observer?.observe(canvas);
    image.decoding = "async";
    image.src = portrait.src;

    return () => {
      disposed = true;
      image.onload = null;
      cancelAnimationFrame(printFrame);
      cancelAnimationFrame(resizeFrame);
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
