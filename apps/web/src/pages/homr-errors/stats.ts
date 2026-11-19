// Las cifras de la página de los errores de HOMR (#424, `/errores-de-homr`): lo que se calcula sobre lo que publica
// `GET /stats/homr-errors` (#423, ADR-0073). Son las del informe local (#418, ADR-0069), sin sus
// ejemplos: ni fotos ni nada de una partitura de usuario.

import type {
  DurationChangeRead,
  ErrorRateRead,
  HomrErrorStatsGroupRead,
  HomrErrorStatsRead,
  HomrErrorStatsValuesRead,
} from "../../types";

/** Cada cuánto se vuelven a pedir: el servicio las recalcula cada 5 minutos. */
export const REFRESH_MS = 5 * 60 * 1000;

/** Notas que necesita un grupo de contexto para salir en «Lo que dicen los datos». */
export const MIN_HEADLINE = 200;

/** El mínimo de sesiones de un grupo de Cadenza si la API aún no lo ha dicho (ADR-0073 §5). */
export const DEFAULT_MIN_SESSIONS = 5;

/** Cuentas distintas que necesita un grupo de Cadenza (ADR-0073 §5); la API no lo publica. */
export const MIN_ACCOUNTS = 3;

/** Filas por página en las listas de «Dónde se equivoca más». */
export const PAGE_SIZE = 8;

/** Ejemplos por página en el panel de los ejemplos de un corpus. */
export const EXAMPLES_PAGE_SIZE = 4;

export interface GroupInfo {
  /** Cómo se llama en el conmutador. */
  name: string;
  /** Qué es, para quien no lo sabe. */
  about: string;
}

const GROUPS: Record<string, GroupInfo> = {
  cadenza: {
    name: "Cadenza",
    about:
      "Las correcciones que hacen las personas en Cadenza: cada nota que leyó HOMR se compara con la partitura que dejó quien la corrigió.",
  },
  pruebas: {
    name: "Pruebas con público",
    about:
      "Solo las correcciones de las cuentas abiertas en el registro público, las de las pruebas con público.",
  },
  primus: {
    name: "PrIMuS",
    about:
      "Los íncipits de PrIMuS, leídos por HOMR y comparados con su partitura de referencia. No hay persona detrás: la corrección es la referencia.",
  },
  "camera-primus": {
    name: "Camera-PrIMuS",
    about:
      "Los mismos íncipits con las distorsiones de una foto, leídos por HOMR y comparados con su referencia.",
  },
};

export function groupInfo(id: string): GroupInfo {
  return GROUPS[id] ?? GROUPS[id.replace(/_/g, "-")] ?? { name: id, about: "" };
}

/** En qué orden van: los de Cadenza, PrIMuS y Camera-PrIMuS; otro corpus, después. */
const ORDER = ["cadenza", "pruebas", "primus", "camera-primus"];

function rank(id: string): number {
  const index = ORDER.indexOf(id.replace(/_/g, "-"));
  return index === -1 ? ORDER.length : index;
}

/** Los grupos que se pueden enseñar: los publicados, en el orden de `ORDER`. */
export function shownGroups(data: HomrErrorStatsRead): HomrErrorStatsGroupRead[] {
  return data.groups
    .filter((group) => group.published && group.stats !== null)
    .sort((a, b) => rank(a.id) - rank(b.id) || a.id.localeCompare(b.id));
}

/** Si el grupo de todas las sesiones de Cadenza aún no llega al mínimo para publicarse. */
export function cadenzaPending(data: HomrErrorStatsRead): boolean {
  const cadenza = data.groups.find((group) => group.id === "cadenza");
  return !cadenza?.published;
}

// --- Números ------------------------------------------------------------------------------------

const NUMBER = new Intl.NumberFormat("es");

export const fmt = (n: number): string => NUMBER.format(n);

/** Un porcentaje, con espacio fino que no parte la línea antes de «%»; una parte no nula que se
 * redondearía a cero sale como «< 0,1 %». */
export function pct(part: number, total: number, digits = 1): string {
  if (!total) return "—";
  const value = (100 * part) / total;
  if (part > 0 && value < 0.1) return "< 0,1\u00a0%";
  return `${value.toLocaleString("es", { maximumFractionDigits: digits })}\u00a0%`;
}

/** Cuántas por cada 100 notas leídas, sin que una corrección rara se lea «0». */
export function perHundred(part: number, total: number): string {
  if (!total) return "—";
  const value = (100 * part) / total;
  if (part > 0 && value < 0.1) return "< 0,1";
  return value.toLocaleString("es", { maximumFractionDigits: 1 });
}

export function plural(n: number, one: string, many: string): string {
  return `${fmt(n)} ${n === 1 ? one : many}`;
}

const WHEN = new Intl.DateTimeFormat("es", {
  day: "numeric",
  month: "long",
  hour: "2-digit",
  minute: "2-digit",
});

/** «19 de noviembre, 12:05», en la hora de quien mira. */
export function whenText(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : WHEN.format(date);
}

// --- Nombres --------------------------------------------------------------------------------------

/** Los tipos de corrección, con nombres que se entienden solos (#418). */
export const OPS: Record<string, string> = {
  SetPitch: "Altura equivocada",
  SetDuration: "Figura equivocada",
  SetAccidental: "Alteración equivocada",
  DeleteEvent: "Nota que sobraba",
  InsertEvent: "Nota que HOMR no leyó",
  SetClef: "Clave equivocada",
  SetKey: "Armadura equivocada",
};

export const opName = (op: string): string => OPS[op] ?? op;

/** Cómo se dice en «Lo que dicen los datos» que una nota leída necesitó esta corrección. */
const OP_FINDING: Record<string, string> = {
  SetDuration: "tenían mal la figura",
  SetPitch: "tenían mal la altura",
  SetAccidental: "tenían mal la alteración",
  DeleteEvent: "sobraban: HOMR las leyó y no estaban en la partitura",
};

export interface Outcome {
  key: string;
  label: string;
  what: string;
}

/** Qué pasó con cada nota leída, con lo que significa cada palabra (#418). */
export const OUTCOMES: readonly Outcome[] = [
  {
    key: "corregida",
    label: "Corregida",
    what: "Está en la partitura correcta, pero hubo que cambiarle la altura, la alteración o la figura.",
  },
  {
    key: "borrada",
    label: "Sobraba",
    what: "HOMR leyó una nota o un silencio que no está en la partitura correcta: se borró.",
  },
  {
    key: "sin_alinear",
    label: "Sin alinear",
    what: "Está en un compás que HOMR leyó de más: no hay compás correcto con que compararla, así que no se sabe si estaba bien.",
  },
  {
    key: "bien",
    label: "Bien leída",
    what: "Quedó igual en la partitura correcta: no hubo que tocarla.",
  },
];

/** Una altura movida tantos pasos de pentagrama, en palabras. */
export function stepName(step: number): string {
  if (step === 0) return "la misma línea o espacio (solo cambió la alteración)";
  const n = Math.abs(step);
  const count = n === 8 ? "8 o más" : String(n);
  const unit = n === 1 ? "línea o espacio" : "líneas o espacios";
  const octave = n === 7 ? " (una octava)" : "";
  return `${count} ${unit} ${step > 0 ? "más arriba" : "más abajo"}${octave}`;
}

// --- Lo que dicen los datos ------------------------------------------------------------------------

export interface Finding {
  /** La cifra grande. */
  big: string;
  /** La frase que la explica. */
  text: string;
  /** La figura de la que habla: su duración en negras, para dibujar su símbolo junto a su
   * nombre (`label`), que está en `text`. */
  figure?: { beats: string; label: string };
  kicker: string;
  /** La cifra de la que habla, para elegir sus ejemplos (en los corpus): `op:SetPitch`,
   * `readdur:1/2`, `vs:against_key` o `clef:G2`. */
  key?: string;
  /** Cómo se llama esa cifra en el panel de los ejemplos. */
  title?: string;
}

/** Hasta cuatro frases calculadas de las cifras, como en el informe (#418). Los grupos de
 * menos de `MIN_HEADLINE` notas no salen: un 50 % de 30 notas dice poco. */
export function findings(stats: HomrErrorStatsValuesRead): Finding[] {
  const out: Finding[] = [];
  const read = stats.read;
  const top = Object.entries(stats.ops)
    .filter(([op, n]) => n > 0 && op in OP_FINDING)
    .sort((a, b) => b[1] - a[1])[0];
  if (read && top) {
    const [op, n] = top;
    out.push({
      big: pct(n, read, 0),
      text: `de las notas que leyó HOMR ${OP_FINDING[op] ?? ""}: es lo que más se corrige (${fmt(n)} de ${fmt(read)}).`,
      kicker: "Qué se corrige",
      key: `op:${op}`,
      title: opName(op),
    });
  }
  const big = (rows: ErrorRateRead[]) => rows.filter((r) => r.n >= MIN_HEADLINE && r.wrong > 0);
  const figure = big(stats.by_duration)[0];
  if (figure) {
    out.push({
      big: pct(figure.wrong, figure.n, 0),
      text: `de las notas leídas como ${figure.label} tienen alguna corrección (${fmt(figure.wrong)} de ${fmt(figure.n)}): es la figura que peor lee.`,
      figure: { beats: figure.key.slice("readdur:".length), label: figure.label },
      kicker: "Figura leída",
      key: figure.key,
      title: figure.label,
    });
  }
  const against = stats.by_vs_key.find((r) => r.key === "vs:against_key");
  const inKey = stats.by_vs_key.find((r) => r.key === "vs:in_key");
  if (against && inKey && against.n >= MIN_HEADLINE && inKey.n >= MIN_HEADLINE) {
    out.push({
      big: pct(against.wrong, against.n, 0),
      text: `de las notas con una alteración contra la armadura se corrigen (${fmt(against.wrong)} de ${fmt(against.n)}), frente al ${pct(inKey.wrong, inKey.n, 0)} de las que van según la armadura.`,
      kicker: "Alteración y armadura",
      key: against.key,
      title: against.label,
    });
  }
  const clef = big(stats.by_clef)[0];
  if (clef && out.length < 4) {
    out.push({
      big: pct(clef.wrong, clef.n, 0),
      text: `de las notas en ${clef.label} tienen alguna corrección (${fmt(clef.wrong)} de ${fmt(clef.n)}): la clave en que más falla.`,
      kicker: "Clave",
      key: clef.key,
      title: clef.label,
    });
  }
  if (out.length < 4 && stats.scores) {
    out.push({
      big: pct(stats.clean_scores, stats.scores, 0),
      text: `de las partituras salieron sin ninguna corrección (${fmt(stats.clean_scores)} de ${fmt(stats.scores)}).`,
      kicker: "Sin errores",
    });
  }
  return out.slice(0, 4);
}

// --- Figura leída y correcta -----------------------------------------------------------------------

/** Una duración en negras («3/2») como número, para ordenar de la más corta a la más larga. */
export function beatsValue(beats: string): number {
  const [a = "", b] = beats.split("/");
  const value = b === undefined ? Number(a) : Number(a) / Number(b);
  return Number.isFinite(value) ? value : Number.POSITIVE_INFINITY;
}

export interface DurationMatrix {
  reads: string[];
  fixes: string[];
  names: Record<string, string>;
  count: (read: string, fix: string) => number;
  max: number;
}

export function durationMatrix(durations: DurationChangeRead[]): DurationMatrix {
  const names: Record<string, string> = {};
  const counts = new Map<string, number>();
  for (const cell of durations) {
    names[cell.read] = cell.read_name;
    names[cell.fix] = cell.fix_name;
    counts.set(`${cell.read}>${cell.fix}`, cell.n);
  }
  const order = (values: Iterable<string>) =>
    [...new Set(values)].sort((a, b) => beatsValue(a) - beatsValue(b));
  return {
    reads: order(durations.map((c) => c.read)),
    fixes: order(durations.map((c) => c.fix)),
    names,
    count: (read, fix) => counts.get(`${read}>${fix}`) ?? 0,
    max: Math.max(1, ...durations.map((c) => c.n)),
  };
}

/** Hasta esta opacidad, el número de la celda va en tinta; desde `STRONG_ALPHA`, en papel. Entre
 * las dos, ninguno de los dos llega a 4,5:1 sobre el violeta: ninguna celda cae ahí. */
const INK_TEXT_MAX = 0.78;
export const STRONG_ALPHA = 0.9;

/** La opacidad del violeta de una celda de la matriz: cuanto más violeta, más casos (#418). */
export function cellAlpha(n: number, max: number): number {
  const alpha = 0.12 + 0.88 * Math.sqrt(n / max);
  if (alpha <= INK_TEXT_MAX || alpha >= STRONG_ALPHA) return alpha;
  return alpha < (INK_TEXT_MAX + STRONG_ALPHA) / 2 ? INK_TEXT_MAX : STRONG_ALPHA;
}
