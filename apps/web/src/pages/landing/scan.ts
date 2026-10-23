import { GEOMETRY, STAFF_BOTTOM, type Measure } from "./incipit";
import { HEAD_RX, HEAD_RY, layoutIncipit, STAFF_END } from "./notation";

const { width, height, staffTop } = GEOMETRY;

/** Resolución del «escaneo»: una fracción de la geometría vectorial. */
export const SCAN_SCALE = 0.2;
export const SCAN_WIDTH = Math.round(width * SCAN_SCALE);
export const SCAN_HEIGHT = Math.round(height * SCAN_SCALE);

interface Rgb {
  r: number;
  g: number;
  b: number;
}

function parseHex(hex: string, fallback: Rgb): Rgb {
  const match = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex.trim());
  if (!match?.[1] || !match[2] || !match[3]) return fallback;
  return { r: parseInt(match[1], 16), g: parseInt(match[2], 16), b: parseInt(match[3], 16) };
}

/**
 * Dibuja el incipit como una imagen escaneada a baja resolución: la misma maqueta que la
 * notación vectorial, con trazos algo más gruesos (la tinta de imprenta engorda al escanear) y
 * umbralizada a un bit con un ruido determinista, para que se lean los píxeles. Devuelve false
 * si el navegador no ofrece un contexto 2D.
 */
export function drawScan(canvas: HTMLCanvasElement, measures: Measure[]): boolean {
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return false;
  canvas.width = SCAN_WIDTH;
  canvas.height = SCAN_HEIGHT;

  const styles = getComputedStyle(canvas);
  const paper = parseHex(styles.getPropertyValue("--color-paper"), { r: 240, g: 239, b: 242 });
  const ink = parseHex(styles.getPropertyValue("--color-ink"), { r: 10, g: 10, b: 10 });
  const layout = layoutIncipit(measures);

  ctx.save();
  ctx.scale(SCAN_SCALE, SCAN_SCALE);
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, width, height);
  ctx.fillStyle = "#000";
  ctx.strokeStyle = "#000";
  ctx.lineJoin = "round";

  const line = (x1: number, y1: number, x2: number, y2: number, lineWidth: number) => {
    ctx.lineWidth = lineWidth;
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
  };

  for (const y of layout.staffLines) line(0, y, STAFF_END, y, 7);
  for (const bar of layout.barlines) line(bar.x, staffTop, bar.x, STAFF_BOTTOM, bar.width + 3);

  for (const glyph of layout.glyphs) {
    ctx.save();
    ctx.translate(glyph.tx, glyph.ty);
    ctx.scale(glyph.scale, glyph.scale);
    const path = new Path2D(glyph.path);
    if (glyph.stroke) {
      ctx.lineWidth = glyph.stroke;
      ctx.stroke(path);
    }
    ctx.fill(path);
    ctx.restore();
  }

  for (const { note, open, stem, dot } of layout.notes) {
    ctx.beginPath();
    ctx.ellipse(note.x, note.y, HEAD_RX, HEAD_RY, (-20 * Math.PI) / 180, 0, Math.PI * 2);
    if (open) {
      ctx.lineWidth = 7;
      ctx.stroke();
    } else {
      ctx.fill();
    }
    if (stem) line(stem.x, stem.y1, stem.x, stem.y2, 8);
    if (dot) {
      ctx.beginPath();
      ctx.arc(dot.cx, dot.cy, 7, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  for (const points of layout.beams) {
    ctx.beginPath();
    points.forEach(([x, y], index) => {
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.fill();
  }
  ctx.restore();

  // Umbral a un bit con ruido determinista (generador congruencial con semilla fija).
  const image = ctx.getImageData(0, 0, SCAN_WIDTH, SCAN_HEIGHT);
  let seed = 7;
  const random = () => {
    seed = (seed * 16807) % 2147483647;
    return seed / 2147483647;
  };
  const data = image.data;
  for (let i = 0; i < data.length; i += 4) {
    const value =
      (data[i] ?? 255) * 0.3 + (data[i + 1] ?? 255) * 0.59 + (data[i + 2] ?? 255) * 0.11;
    const on = value + (random() - 0.5) * 50 < 190;
    const color = on ? ink : paper;
    data[i] = color.r;
    data[i + 1] = color.g;
    data[i + 2] = color.b;
    data[i + 3] = 255;
  }
  ctx.putImageData(image, 0, 0);
  return true;
}
