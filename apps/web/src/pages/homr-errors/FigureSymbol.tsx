import type { ReactNode } from "react";
import type { FigureRead, FigureSymbolRead } from "../../types";

// El símbolo de cada figura, dibujado en vectores sin fuentes (#418): cabeza, plica, corchetes,
// puntillos, el número de un grupo irregular y, en las de adorno, la raya. Usa currentColor.

const FLAGS: Record<string, number> = {
  corchea: 1,
  semicorchea: 2,
  fusa: 3,
  semifusa: 4,
  garrapatea: 5,
};
const HEIGHT = 32;
const LINE = {
  stroke: "currentColor",
  fill: "none",
  strokeLinecap: "round",
} as const;

interface Drawn {
  parts: ReactNode[];
  width: number;
}

/** Una figura escrita, en una caja de 32 de alto con la cabeza abajo. */
function drawFigure(part: FigureSymbolRead, key: string): Drawn {
  const parts: ReactNode[] = [];
  let width: number;
  let dotY = 25;
  if (part.figure === "cuadrada" || part.figure === "longa") {
    parts.push(
      <rect key={`${key}h`} x={3} y={13} width={8} height={7} {...LINE} strokeWidth={1.7} />,
      <line key={`${key}l`} x1={1.5} y1={10.5} x2={1.5} y2={22.5} {...LINE} strokeWidth={1.5} />,
      <line key={`${key}r`} x1={12.5} y1={10.5} x2={12.5} y2={22.5} {...LINE} strokeWidth={1.5} />,
    );
    if (part.figure === "longa") {
      parts.push(
        <line key={`${key}c`} x1={12.5} y1={20} x2={12.5} y2={30} {...LINE} strokeWidth={1.5} />,
      );
    }
    width = 14;
    dotY = 16.5;
  } else if (part.figure === "redonda") {
    parts.push(
      <ellipse
        key={`${key}h`}
        cx={6.5}
        cy={17}
        rx={5.3}
        ry={3.7}
        transform="rotate(-12 6.5 17)"
        {...LINE}
        strokeWidth={2.2}
      />,
    );
    width = 13;
    dotY = 16;
  } else {
    const hollow = part.figure === "blanca";
    parts.push(
      <ellipse
        key={`${key}h`}
        cx={5.4}
        cy={26}
        rx={4.6}
        ry={3.3}
        transform="rotate(-22 5.4 26)"
        fill={hollow ? "none" : "currentColor"}
        stroke="currentColor"
        strokeWidth={hollow ? 1.7 : 0}
      />,
      <line key={`${key}s`} x1={9.6} y1={25.2} x2={9.6} y2={1.5} {...LINE} strokeWidth={1.4} />,
    );
    width = 11;
    const flags = FLAGS[part.figure] ?? 0;
    for (let i = 0; i < flags; i++) {
      parts.push(
        <path
          key={`${key}f${String(i)}`}
          d={`M9.6 ${String(1.5 + i * 4.4)} c0.5 2.6 5.4 3.2 4.6 7.4`}
          {...LINE}
          strokeWidth={1.6}
        />,
      );
    }
    if (flags) width = 15.5;
  }
  for (let i = 0; i < part.dots; i++) {
    parts.push(
      <circle
        key={`${key}d${String(i)}`}
        cx={width + 1.8 + i * 3.6}
        cy={dotY}
        r={1.5}
        fill="currentColor"
      />,
    );
  }
  if (part.dots) width += 1.8 + part.dots * 3.6;
  if (part.tuplet) {
    parts.push(
      <text key={`${key}t`} x={0} y={8} className="figure-symbol__tuplet">
        {part.tuplet}
      </text>,
    );
  }
  if (part.grace) {
    parts.push(
      <line key={`${key}g`} x1={4.5} y1={14} x2={16} y2={5} {...LINE} strokeWidth={1.5} />,
    );
  }
  return { parts, width };
}

/** El símbolo de una duración: sus figuras ligadas, una tras otra. Decorativo: su nombre va al
 * lado en texto. Nada si no se escribe con figuras. */
export function FigureSymbol({ figure }: { figure: FigureRead | undefined }) {
  if (!figure?.symbol.length) return null;
  const drawn = figure.symbol.map((part, index) => drawFigure(part, String(index)));
  // Cada figura empieza tras la anterior, con 3 de aire entre las ligadas.
  const offsets: number[] = [];
  let total = 0;
  for (const [index, part] of drawn.entries()) {
    offsets.push(total);
    total += part.width + (index < drawn.length - 1 ? 3 : 0);
  }
  const groups = drawn.map((part, index) => (
    <g key={index} transform={`translate(${(offsets[index] ?? 0).toFixed(1)} 0)`}>
      {part.parts}
    </g>
  ));
  const width = total.toFixed(1);
  return (
    <svg
      className="figure-symbol"
      viewBox={`0 0 ${width} ${String(HEIGHT)}`}
      width={width}
      height={HEIGHT}
      aria-hidden="true"
      focusable="false"
    >
      {groups}
    </svg>
  );
}
