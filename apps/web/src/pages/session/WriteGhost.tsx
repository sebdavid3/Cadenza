import { FIGURES } from "./edits";
import { pitchName } from "./noteNames";
import { ledgerSteps, stepY, type WriteSpot } from "./writing";

/** La línea central del pentagrama: de ella hacia abajo, la plica sube (#350). */
const MIDDLE_LINE = 4;
/** Figuras de cabeza blanca: la blanca y la redonda; la redonda, sin plica. */
const HALF = 5;
const WHOLE = 6;
/** Una corchea lleva un corchete; cada figura más corta, uno más. */
const EIGHTH = 3;

interface WriteGhostProps {
  spot: WriteSpot;
  pitch: string;
  figure: number;
  dotted: boolean;
  /** Mayús + clic sobre una nota: la altura se añade a su acorde. */
  chord: boolean;
  /** Se está guardando otra corrección: el clic espera. */
  waiting: boolean;
}

/** Lo que dice la etiqueta del fantasma: qué se escribe y cómo. */
function ghostLabel({ spot, pitch, figure, dotted, chord, waiting }: WriteGhostProps): string {
  if (waiting) return "Espera: se está guardando";
  const name = pitchName(pitch)?.written ?? pitch;
  const value = `${(FIGURES[figure]?.name ?? "").toLowerCase()}${dotted ? " con puntillo" : ""}`;
  if (chord) return `${name} al acorde`;
  return `${spot.aim.kind === "insert" ? "Insertar " : ""}${name} · ${value}`;
}

/**
 * La nota fantasma del modo «Escribir» (#350): dónde y qué escribe un clic, en violeta translúcido
 * (pide una acción, DESIGN.md), por encima de la partitura y sin recibir el puntero. Sobre una
 * figura, en su columna; para insertar, con una línea de inserción. Una nota que se sale de las
 * cinco líneas lleva sus líneas adicionales.
 */
export function WriteGhost(props: WriteGhostProps) {
  const { spot, figure, dotted, chord, waiting } = props;
  const { lines, steps, aim } = spot;
  const { space } = lines;
  const x = aim.x;
  const y = stepY(steps, lines);
  const rx = 0.66 * space;
  const ry = 0.46 * space;
  // En un acorde se añade la cabeza: la figura es la del acorde, así que va sin plica.
  const stem = !chord && figure < WHOLE;
  const up = steps >= MIDDLE_LINE;
  const stemX = up ? x + rx * 0.92 : x - rx * 0.92;
  const tip = up ? y - 3.5 * space : y + 3.5 * space;
  const flags = !chord && figure <= EIGHTH ? EIGHTH + 1 - figure : 0;
  // El puntillo va en un espacio: si la nota está en una línea, en el de encima.
  const dotY = stepY(steps % 2 === 0 ? steps - 1 : steps, lines);
  return (
    <>
      <svg
        className="notation__ghost"
        aria-hidden="true"
        data-waiting={waiting}
        data-aim={chord ? "chord" : aim.kind}
      >
        {ledgerSteps(steps).map((step) => (
          <line
            key={step}
            className="notation__ghost-ledger"
            x1={x - 1.1 * space}
            x2={x + 1.1 * space}
            y1={stepY(step, lines)}
            y2={stepY(step, lines)}
          />
        ))}
        {aim.kind === "insert" && (
          <line
            className="notation__ghost-caret"
            x1={x}
            x2={x}
            y1={lines.top - space}
            y2={lines.top + 5 * space}
          />
        )}
        <ellipse
          className="notation__ghost-head"
          data-hollow={!chord && figure >= HALF}
          cx={x}
          cy={y}
          rx={rx}
          ry={ry}
          transform={`rotate(-20 ${String(x)} ${String(y)})`}
        />
        {stem && <line className="notation__ghost-stem" x1={stemX} x2={stemX} y1={y} y2={tip} />}
        {Array.from({ length: flags }, (_unused, index) => {
          const from = up ? tip + index * 0.7 * space : tip - index * 0.7 * space;
          return (
            <line
              key={index}
              className="notation__ghost-stem"
              x1={stemX}
              x2={stemX + 0.9 * space}
              y1={from}
              y2={up ? from + 1.2 * space : from - 1.2 * space}
            />
          );
        })}
        {!chord && dotted && (
          <circle
            className="notation__ghost-dot"
            cx={x + 1.25 * space}
            cy={dotY}
            r={0.17 * space}
          />
        )}
      </svg>
      <span
        className="label notation__ghost-tag"
        data-waiting={waiting}
        style={{ left: x + 1.7 * space, top: y }}
      >
        {ghostLabel(props)}
      </span>
    </>
  );
}
