import type { ReactNode } from "react";
import type { DrawnBarRead, DrawnEventRead, FigureRead, FigureSymbolRead } from "../../types";
import {
  type Clef,
  clefOf,
  keySignaturePositions,
  parsePitch,
  type Pitch,
  staffPosition,
  writtenAccidentals,
} from "./drawing";

// El compás de un ejemplo de un corpus, dibujado desde los datos (#424), como en el informe local
// (`staffSvg`, `groupSvg` y `barHtml` de `ml/informe_tablas.html`): lo que leyó HOMR y lo correcto
// en dos pentagramas, con cabezas, plicas, corchetes, puntillos, alteraciones y silencios, sin
// barras de unión ni ligaduras. La nota del ejemplo va en violeta. La clave se escribe con su
// nombre sobre su línea y la armadura se desplaza según la clave. No es ninguna imagen del corpus.

const SP = 7;
const CLEF_WORD: Record<string, string> = { G: "sol", F: "fa", C: "do" };
const FLAGS: Record<string, number> = {
  corchea: 1,
  semicorchea: 2,
  fusa: 3,
  semifusa: 4,
  garrapatea: 5,
};
const HOLLOW = new Set(["blanca", "redonda", "cuadrada", "longa"]);
const NO_STEM = new Set(["redonda", "cuadrada"]);
const LINE = { stroke: "currentColor", fill: "none", strokeLinecap: "round" } as const;
const DEFAULT_FIGURE: FigureSymbolRead = { figure: "negra", dots: 0, tuplet: 0, grace: false };
/** Se dibuja a escala de pentagrama pequeño y se amplía para leerlo. */
const ZOOM = 1.4;
const LABEL_WIDTH = 64;

interface Context {
  clef: Clef;
  key: number;
  figures: Record<string, FigureRead>;
}

interface Placed {
  event: DrawnEventRead;
  index: number;
  /** Si la nota lleva escrita su alteración: cambia lo que rige en el compás. */
  accidental: boolean;
}

function figureOf(ctx: Context, beats: string): FigureSymbolRead {
  return ctx.figures[beats]?.symbol[0] ?? DEFAULT_FIGURE;
}

function accidental(alter: number, x: number, y: number, key: string): ReactNode {
  if (alter === 1) {
    return (
      <g key={key} {...LINE}>
        <line x1={x - 1.6} y1={y - 7} x2={x - 1.6} y2={y + 6} strokeWidth={1} />
        <line x1={x + 1.6} y1={y - 6} x2={x + 1.6} y2={y + 7} strokeWidth={1} />
        <line x1={x - 3.4} y1={y - 1.4} x2={x + 3.4} y2={y - 3} strokeWidth={1.9} />
        <line x1={x - 3.4} y1={y + 3} x2={x + 3.4} y2={y + 1.4} strokeWidth={1.9} />
      </g>
    );
  }
  if (alter === -1) {
    return (
      <g key={key} {...LINE}>
        <line x1={x - 2.4} y1={y - 9.5} x2={x - 2.4} y2={y + 3} strokeWidth={1.1} />
        <path
          d={`M${String(x - 2.4)} ${String(y - 0.4)} c2 -2.6 6.2 -2.4 5 0.6 c-0.7 1.6 -3 2.4 -5 2.8`}
          strokeWidth={1.5}
        />
      </g>
    );
  }
  if (alter === 0) {
    return (
      <g key={key} {...LINE}>
        <line x1={x - 2} y1={y - 7} x2={x - 2} y2={y + 3.4} strokeWidth={1} />
        <line x1={x + 2} y1={y - 3.4} x2={x + 2} y2={y + 7} strokeWidth={1} />
        <line x1={x - 2} y1={y - 1.6} x2={x + 2} y2={y - 2.8} strokeWidth={1.9} />
        <line x1={x - 2} y1={y + 2.8} x2={x + 2} y2={y + 1.6} strokeWidth={1.9} />
      </g>
    );
  }
  if (alter === 2) {
    return (
      <g key={key} {...LINE} strokeWidth={1.7}>
        <line x1={x - 2.8} y1={y - 2.8} x2={x + 2.8} y2={y + 2.8} />
        <line x1={x - 2.8} y1={y + 2.8} x2={x + 2.8} y2={y - 2.8} />
      </g>
    );
  }
  if (alter === -2) {
    return (
      <g key={key}>
        {accidental(-1, x - 2.6, y, "a")}
        {accidental(-1, x + 2.6, y, "b")}
      </g>
    );
  }
  return null;
}

function rest(figure: FigureSymbolRead, x: number, top: number): ReactNode[] {
  const mid = top + 2 * SP;
  const out: ReactNode[] = [];
  if (figure.figure === "redonda" || figure.figure === "cuadrada" || figure.figure === "longa") {
    out.push(
      <rect key="r" x={x - 4.5} y={top + SP} width={9} height={SP / 2 + 0.5} fill="currentColor" />,
    );
  } else if (figure.figure === "blanca") {
    out.push(
      <rect
        key="r"
        x={x - 4.5}
        y={mid - SP / 2 - 0.5}
        width={9}
        height={SP / 2 + 0.5}
        fill="currentColor"
      />,
    );
  } else if (figure.figure === "negra") {
    out.push(
      <path
        key="r"
        d={`M${String(x - 1.5)} ${String(top + 4)} l4 5 l-4 4 l4 5 c-3 -1.6 -5.4 0.6 -2 4`}
        {...LINE}
        strokeWidth={1.8}
      />,
    );
  } else {
    const flags = FLAGS[figure.figure] ?? 1;
    out.push(
      <line
        key="r"
        x1={x + 3}
        y1={top + SP - 1}
        x2={x - 1}
        y2={top + 3 * SP + 2}
        {...LINE}
        strokeWidth={1.3}
      />,
    );
    for (let i = 0; i < flags; i++) {
      const y = top + SP + 1 + i * SP * 0.8;
      const xs = x + 3 - i * 1.4;
      out.push(
        <circle key={`c${String(i)}`} cx={xs - 5} cy={y} r={1.7} fill="currentColor" />,
        <path
          key={`p${String(i)}`}
          d={`M${String(xs - 5)} ${String(y + 0.8)} c1.6 1 3.4 0.4 4.8 -1.6`}
          {...LINE}
          strokeWidth={1.2}
        />,
      );
    }
  }
  for (let i = 0; i < figure.dots; i++) {
    out.push(
      <circle
        key={`d${String(i)}`}
        cx={x + 8 + i * 3.6}
        cy={mid - SP / 2}
        r={1.4}
        fill="currentColor"
      />,
    );
  }
  return out;
}

/** Un grupo: un evento y las notas de su acorde, en la misma x. */
function group(placed: Placed[], x: number, top: number, ctx: Context): ReactNode[] {
  const first = placed[0];
  if (!first) return [];
  const figure = figureOf(ctx, first.event.beats);
  if (first.event.kind === "rest") return rest(figure, x, top);
  const bottom = top + 4 * SP;
  const yOf = (pos: number) => bottom - (pos * SP) / 2;
  const notes = placed.flatMap((p) => {
    const pitch = parsePitch(p.event.pitch);
    return pitch ? [{ placed: p, pitch }] : [];
  });
  if (!notes.length) return [];
  const positions = notes.map((n) => staffPosition(n.pitch, ctx.clef));
  const up = (Math.min(...positions) + Math.max(...positions)) / 2 < 4;
  const scale = figure.grace ? 0.7 : 1;
  const out: ReactNode[] = [];
  notes.forEach((note, i) => {
    const pos = positions[i] ?? 0;
    const y = yOf(pos);
    for (let l = -2; l >= pos; l -= 2) {
      out.push(
        <line
          key={`lb${String(i)}${String(l)}`}
          x1={x - 7}
          y1={yOf(l)}
          x2={x + 7}
          y2={yOf(l)}
          stroke="currentColor"
          strokeWidth={1}
        />,
      );
    }
    for (let l = 10; l <= pos; l += 2) {
      out.push(
        <line
          key={`la${String(i)}${String(l)}`}
          x1={x - 7}
          y1={yOf(l)}
          x2={x + 7}
          y2={yOf(l)}
          stroke="currentColor"
          strokeWidth={1}
        />,
      );
    }
    if (note.placed.accidental) out.push(accidental(note.pitch.alter, x - 10, y, `a${String(i)}`));
    const hollow = HOLLOW.has(figure.figure);
    out.push(
      <ellipse
        key={`h${String(i)}`}
        cx={x}
        cy={y}
        rx={4.3 * scale}
        ry={3.1 * scale}
        transform={`rotate(-20 ${String(x)} ${String(y)})`}
        fill={hollow ? "none" : "currentColor"}
        stroke="currentColor"
        strokeWidth={hollow ? 1.5 : 0}
      />,
    );
    for (let k = 0; k < figure.dots; k++) {
      out.push(
        <circle
          key={`d${String(i)}${String(k)}`}
          cx={x + 8 + k * 3.6}
          cy={pos % 2 === 0 ? y - SP / 2 : y}
          r={1.4}
          fill="currentColor"
        />,
      );
    }
  });
  if (!NO_STEM.has(figure.figure)) {
    const ys = positions.map(yOf);
    const length = 3.4 * SP * scale;
    const sx = up ? x + 3.9 * scale : x - 3.9 * scale;
    const from = up ? Math.max(...ys) : Math.min(...ys);
    const to = up ? Math.min(...ys) - length : Math.max(...ys) + length;
    out.push(<line key="s" x1={sx} y1={from} x2={sx} y2={to} {...LINE} strokeWidth={1.3} />);
    const flags = FLAGS[figure.figure] ?? 0;
    for (let i = 0; i < flags; i++) {
      const d = up
        ? `M${String(sx)} ${String(to + i * 4.2 * scale)} c0.5 2.6 5.4 3.2 4.6 7.4`
        : `M${String(sx)} ${String(to - i * 4.2 * scale)} c0.5 -2.6 5.4 -3.2 4.6 -7.4`;
      out.push(<path key={`f${String(i)}`} d={d} {...LINE} strokeWidth={1.5} />);
    }
    if (figure.grace) {
      out.push(
        <line
          key="g"
          x1={sx - 4}
          y1={up ? to + 9 : to - 9}
          x2={sx + 5}
          y2={up ? to + 2 : to - 2}
          {...LINE}
          strokeWidth={1.3}
        />,
      );
    }
  }
  return out;
}

/** Un pentagrama: la clave por su nombre, la armadura y los eventos, con el del ejemplo en
 * violeta. Las alteraciones solo se escriben si cambian lo que rige en el compás. */
function staff(
  events: DrawnEventRead[],
  focus: number | null | undefined,
  ctx: Context,
  top: number,
  x0: number,
): { nodes: ReactNode[]; width: number } {
  let x = x0;
  const clefY = top + 4 * SP - (ctx.clef.linePos * SP) / 2;
  const word = CLEF_WORD[ctx.clef.sign] ?? "sol";
  const clefNodes = [
    <rect
      key="cb"
      className="homr__drawn-paper"
      x={x - 1}
      y={clefY - 6}
      width={word.length * 6.6 + 4}
      height={12}
    />,
    <text key="ct" className="homr__drawn-clef" x={x + 1} y={clefY + 4}>
      {word}
    </text>,
  ];
  x += word.length * 6.6 + 10;
  // La armadura en las posiciones de la clave de sol, desplazadas por la clave (en la de fa, dos
  // posiciones más abajo; en la de do en 3.ª, una), y dentro del pentagrama.
  const keyNodes: ReactNode[] = [];
  keySignaturePositions(ctx.clef, ctx.key).forEach((pos, i) => {
    keyNodes.push(
      accidental(
        ctx.key > 0 ? 1 : -1,
        x + 3 + i * 7,
        top + 4 * SP - (pos * SP) / 2,
        `k${String(i)}`,
      ),
    );
  });
  x += keyNodes.length * 7;
  x += 14;
  // Solo se escribe la alteración que cambia lo que rige en el compás (`writtenAccidentals`).
  const written = writtenAccidentals(events, ctx.key);
  const groups: Placed[][] = [];
  events.forEach((event, index) => {
    const placed = { event, index, accidental: written[index] ?? false };
    const last = groups[groups.length - 1];
    if (event.chord && last) last.push(placed);
    else groups.push([placed]);
  });
  const noteNodes: ReactNode[] = [];
  groups.forEach((placed, g) => {
    const first = placed[0];
    if (!first) return;
    const figure = figureOf(ctx, first.event.beats);
    const needsAccidental = placed.some((p) => p.accidental);
    if (needsAccidental) x += 8;
    const drawn = group(placed, x, top, ctx);
    if (placed.some((p) => p.index === focus)) {
      const before = needsAccidental ? 16 : 9;
      noteNodes.push(
        <rect
          key={`hit${String(g)}`}
          className="homr__drawn-hit"
          x={x - before}
          y={top - 2.5 * SP}
          width={before + 15}
          height={9 * SP}
        />,
        <g key={`g${String(g)}`} className="homr__drawn-focus">
          {drawn}
        </g>,
      );
    } else {
      noteNodes.push(<g key={`g${String(g)}`}>{drawn}</g>);
    }
    x += (figure.grace ? 15 : 24) + figure.dots * 4;
  });
  const lines = [0, 1, 2, 3, 4].map((k) => (
    <line
      key={`l${String(k)}`}
      className="homr__drawn-line"
      x1={x0 - 4}
      y1={top + k * SP}
      x2={x + 4}
      y2={top + k * SP}
    />
  ));
  return { nodes: [...lines, ...noteNodes, ...clefNodes, ...keyNodes], width: x + 6 };
}

/** Hasta dónde llegan las notas por encima y por debajo de un pentagrama: las que se van lejos
 * (una clave mal leída) no se salen del dibujo ni se montan sobre el otro. */
function reach(events: DrawnEventRead[], clef: Clef): { above: number; below: number } {
  const positions = events
    .map((e) => parsePitch(e.pitch))
    .filter((p): p is Pitch => p !== null)
    .map((p) => staffPosition(p, clef));
  const above = Math.max(
    3.5 * SP,
    (Math.max(0, Math.max(8, ...positions) - 8) * SP) / 2 + 3.8 * SP,
  );
  const below = Math.max(3.5 * SP, (Math.max(0, -Math.min(0, ...positions)) * SP) / 2 + 3.8 * SP);
  return { above, below };
}

export function DrawnBar({
  bar,
  atRead,
  atFix,
  measure,
  figures,
}: {
  bar: DrawnBarRead;
  atRead: number | null | undefined;
  atFix: number | null | undefined;
  measure: string;
  figures: Record<string, FigureRead>;
}) {
  const ctx: Context = { clef: clefOf(bar.clef), key: bar.key, figures };
  const readReach = reach(bar.read, ctx.clef);
  const fixReach = reach(bar.fixed, ctx.clef);
  const top1 = readReach.above;
  const top2 = top1 + 4 * SP + readReach.below + fixReach.above;
  const height = top2 + 4 * SP + fixReach.below;
  const read = staff(bar.read, atRead, ctx, top1, LABEL_WIDTH);
  const fixed = staff(bar.fixed, atFix, ctx, top2, LABEL_WIDTH);
  const width = Math.max(read.width, fixed.width, 220);
  return (
    <div className="homr__drawn">
      <svg
        viewBox={`0 0 ${String(width)} ${height.toFixed(1)}`}
        width={(width * ZOOM).toFixed(0)}
        height={(height * ZOOM).toFixed(0)}
        role="img"
        aria-label={`Compás ${measure}: lo que leyó HOMR y lo correcto`}
      >
        <text className="homr__drawn-tag" x={0} y={top1 + 2 * SP + 4}>
          HOMR leyó
        </text>
        <text className="homr__drawn-tag" x={0} y={top2 + 2 * SP + 4}>
          Correcto
        </text>
        {read.nodes}
        {fixed.nodes}
      </svg>
    </div>
  );
}
