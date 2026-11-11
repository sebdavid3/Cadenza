import bach from "./retratos/bach.jpg";
import beethoven from "./retratos/beethoven.jpg";
import chopin from "./retratos/chopin.jpg";
import claraSchumann from "./retratos/clara-schumann.jpg";
import mozart from "./retratos/mozart.jpg";

/**
 * Un retrato del panel del acceso (#392): una imagen en gris reducida, servida desde el proyecto,
 * que el panel imprime en semitono con la trama de 5 px. `focus` es dónde están los ojos, en
 * fracciones de la imagen, para recortarla sin cortar la cara. Fuentes y licencias en
 * `retratos/README.md`.
 */
export interface Portrait {
  name: string;
  lifespan: string;
  credit: string;
  src: string;
  focus: { x: number; y: number };
}

const BACH: Portrait = {
  name: "Johann Sebastian Bach",
  lifespan: "1685–1750",
  credit: "Óleo de Elias Gottlob Haussmann, 1748",
  src: bach,
  focus: { x: 0.49, y: 0.26 },
};

export const PORTRAITS: readonly Portrait[] = [
  BACH,
  {
    name: "Wolfgang Amadeus Mozart",
    lifespan: "1756–1791",
    credit: "Óleo de Barbara Krafft, 1819",
    src: mozart,
    focus: { x: 0.5, y: 0.34 },
  },
  {
    name: "Ludwig van Beethoven",
    lifespan: "1770–1827",
    credit: "Óleo de Joseph Karl Stieler, 1820",
    src: beethoven,
    focus: { x: 0.57, y: 0.31 },
  },
  {
    name: "Frédéric Chopin",
    lifespan: "1810–1849",
    credit: "Daguerrotipo de Louis-Auguste Bisson, 1849",
    src: chopin,
    focus: { x: 0.44, y: 0.23 },
  },
  {
    name: "Clara Schumann",
    lifespan: "1819–1896",
    credit: "Pastel de Franz von Lenbach, 1878",
    src: claraSchumann,
    focus: { x: 0.5, y: 0.37 },
  },
];

/** Dónde recuerda el navegador el último retrato mostrado: una comodidad, no un dato. */
export const PORTRAIT_STORAGE_KEY = "cadenza.acceso.retrato";
/** El retrato de esta visita (la sesión de la pestaña): ir de entrar al registro no lo cambia. */
export const VISIT_PORTRAIT_KEY = "cadenza.acceso.retrato-de-la-visita";

/**
 * El retrato de esta visita: el siguiente al último que se mostró y, en la primera visita (o si
 * lo guardado no sirve), uno al azar, para que no todos empiecen por el mismo.
 */
export function pickPortraitIndex(stored: string | null, count: number, random: () => number) {
  const last = stored === null || !/^\d+$/.test(stored) ? Number.NaN : Number(stored);
  if (Number.isInteger(last) && last >= 0 && last < count) return (last + 1) % count;
  return Math.min(count - 1, Math.floor(random() * count));
}

export function portraitAt(index: number): Portrait {
  return PORTRAITS[index] ?? BACH;
}

export function readLastPortrait(): string | null {
  try {
    return window.localStorage.getItem(PORTRAIT_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function rememberPortrait(index: number): void {
  try {
    window.localStorage.setItem(PORTRAIT_STORAGE_KEY, String(index));
  } catch {
    // Sin almacenamiento, cada visita empieza al azar.
  }
}

/**
 * El retrato de esta visita: el que ya se eligió en esta pestaña o, si es la primera vista del
 * acceso en ella, el siguiente de la rotación, que se recuerda para la próxima visita. Se puede
 * llamar más de una vez (los efectos dobles de React en desarrollo): devuelve el mismo.
 */
export function choosePortrait(random: () => number = Math.random): number {
  let visit: string | null;
  try {
    visit = window.sessionStorage.getItem(VISIT_PORTRAIT_KEY);
  } catch {
    visit = null;
  }
  if (visit !== null && /^\d+$/.test(visit) && Number(visit) < PORTRAITS.length) {
    return Number(visit);
  }
  const index = pickPortraitIndex(readLastPortrait(), PORTRAITS.length, random);
  rememberPortrait(index);
  try {
    window.sessionStorage.setItem(VISIT_PORTRAIT_KEY, String(index));
  } catch {
    // Sin almacenamiento de sesión, cada vista del acceso avanza la rotación.
  }
  return index;
}

/** Paso de la trama: el mismo de `--halftone-ink`, para que el retrato salga de ella. */
export const DOT_PITCH = 5;
/**
 * Radio del punto en el negro: medio paso, de modo que los puntos se tocan sin cerrar un bloque
 * macizo y ninguno invade la fila de al lado (la impresión pinta una banda de filas cada vez).
 */
export const DOT_MAX_RADIUS = DOT_PITCH / 2;
/** Altura del panel (en fracción) a la que caen los ojos, salvo que la hoja diga otra. */
export const EYE_LINE = 0.36;

/**
 * El radio de un punto según la luminancia de su celda (0 negro, 1 blanco): el área del punto es
 * proporcional a la sombra, como en un semitono de imprenta.
 */
export function dotRadius(luminance: number): number {
  const shade = 1 - Math.min(1, Math.max(0, luminance));
  return DOT_MAX_RADIUS * Math.sqrt(shade);
}

export interface Crop {
  sx: number;
  sy: number;
  sw: number;
  sh: number;
}

/**
 * Qué parte de la imagen cubre un panel de `width` × `height` sin deformarla: la imagen llena el
 * panel y el recorte pone los ojos centrados y a la altura `eyeLine` (por defecto, a un tercio
 * largo del alto), sin salirse de ella.
 */
export function coverCrop(
  width: number,
  height: number,
  imageWidth: number,
  imageHeight: number,
  focus: { x: number; y: number },
  eyeLine = EYE_LINE,
): Crop {
  const scale = Math.max(width / imageWidth, height / imageHeight);
  const sw = width / scale;
  const sh = height / scale;
  const clamp = (value: number, max: number) => Math.min(Math.max(value, 0), max);
  return {
    sx: clamp(focus.x * imageWidth - sw / 2, imageWidth - sw),
    sy: clamp(focus.y * imageHeight - eyeLine * sh, imageHeight - sh),
    sw,
    sh,
  };
}
