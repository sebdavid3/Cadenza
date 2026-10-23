import { GEOMETRY, STAFF_BOTTOM, measureX, placeNotes, stemUp, type Measure } from "./incipit";

const { width, height, staffTop, space } = GEOMETRY;

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
 * Dibuja el incipit como una imagen escaneada a baja resolución: tinta umbralizada a un
 * bit con un ruido determinista, para que se lean los píxeles. Devuelve false si el
 * navegador no ofrece un contexto 2D.
 */
export function drawScan(canvas: HTMLCanvasElement, measures: Measure[]): boolean {
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return false;
  canvas.width = SCAN_WIDTH;
  canvas.height = SCAN_HEIGHT;

  const styles = getComputedStyle(canvas);
  const paper = parseHex(styles.getPropertyValue("--color-paper"), { r: 240, g: 239, b: 242 });
  const ink = parseHex(styles.getPropertyValue("--color-ink"), { r: 10, g: 10, b: 10 });

  ctx.save();
  ctx.scale(SCAN_SCALE, SCAN_SCALE);
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, width, height);
  ctx.fillStyle = "#000";
  ctx.strokeStyle = "#000";

  ctx.lineWidth = 7;
  for (let line = 0; line < 5; line += 1) {
    ctx.beginPath();
    ctx.moveTo(0, staffTop + line * space);
    ctx.lineTo(width, staffTop + line * space);
    ctx.stroke();
  }
  for (let bar = 0; bar <= 4; bar += 1) {
    ctx.lineWidth = bar === 4 ? 12 : 7;
    const x = measureX(bar) - (bar === 4 ? 6 : 0);
    ctx.beginPath();
    ctx.moveTo(x, staffTop);
    ctx.lineTo(x, STAFF_BOTTOM);
    ctx.stroke();
  }

  ctx.font = `${String(space * 4.1)}px "Noto Music"`;
  ctx.fillText("\u{1D11E}", 12, staffTop + 3 * space + 4);
  ctx.font = `700 ${String(space * 2.2)}px "Pixelify Sans"`;
  ctx.fillText("3", 116, staffTop + 2 * space - 4);
  ctx.fillText("4", 116, STAFF_BOTTOM - 2);

  const notes = placeNotes(measures);
  for (const note of notes) {
    const open = note.beats >= 2;
    ctx.beginPath();
    ctx.ellipse(note.x, note.y, space * 0.62, space * 0.44, (-20 * Math.PI) / 180, 0, Math.PI * 2);
    if (open) {
      ctx.lineWidth = 7;
      ctx.stroke();
    } else {
      ctx.fill();
    }
    if (note.beats < 3) {
      const up = stemUp(note.pitch);
      const x = up ? note.x + space * 0.56 : note.x - space * 0.56;
      ctx.lineWidth = 8;
      ctx.beginPath();
      ctx.moveTo(x, note.y);
      ctx.lineTo(x, up ? note.y - space * 3.4 : note.y + space * 3.4);
      ctx.stroke();
    } else {
      ctx.beginPath();
      ctx.arc(note.x + space * 1.1, note.y - space * 0.25, 7, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  const eighths = notes.filter((note) => note.beats === 0.5);
  const first = eighths[0];
  const last = eighths.at(-1);
  if (first && last && first !== last) {
    const up = stemUp(first.pitch);
    const x1 = up ? first.x + space * 0.56 : first.x - space * 0.56;
    const x2 = up ? last.x + space * 0.56 : last.x - space * 0.56;
    const y1 = up ? first.y - space * 3.4 : first.y + space * 3.4;
    const y2 = up ? last.y - space * 3.4 : last.y + space * 3.4;
    const t = space * 0.55 * (up ? 1 : -1);
    ctx.beginPath();
    ctx.moveTo(x1 - 3, y1);
    ctx.lineTo(x2 + 3, y2);
    ctx.lineTo(x2 + 3, y2 + t);
    ctx.lineTo(x1 - 3, y1 + t);
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
    const on = value + (random() - 0.5) * 70 < 170;
    const color = on ? ink : paper;
    data[i] = color.r;
    data[i + 1] = color.g;
    data[i + 2] = color.b;
    data[i + 3] = 255;
  }
  ctx.putImageData(image, 0, 0);
  return true;
}
