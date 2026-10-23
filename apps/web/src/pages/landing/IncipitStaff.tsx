import { useId } from "react";
import {
  flagRegion,
  GEOMETRY,
  STAFF_BOTTOM,
  measureX,
  placeNotes,
  stemUp,
  type Measure,
  type PlacedNote,
} from "./incipit";

const { width, height, staffTop, space, firstBarX } = GEOMETRY;
const STEM = space * 3.4;
const HEAD_RX = space * 0.62;
const HEAD_RY = space * 0.44;
const STEM_OFFSET = space * 0.56;
const TREBLE_CLEF = "\u{1D11E}";

function stemX(note: PlacedNote, up: boolean) {
  return up ? note.x + STEM_OFFSET : note.x - STEM_OFFSET;
}

/** Corcheas consecutivas del mismo compás, que se unen con una barra. */
function beamGroups(notes: PlacedNote[]): PlacedNote[][] {
  const groups: PlacedNote[][] = [];
  let current: PlacedNote[] = [];
  for (const note of notes) {
    const previous = current.at(-1);
    if (note.beats === 0.5 && (!previous || previous.measure === note.measure)) {
      current.push(note);
    } else {
      if (current.length > 1) groups.push(current);
      current = note.beats === 0.5 ? [note] : [];
    }
  }
  if (current.length > 1) groups.push(current);
  return groups;
}

interface IncipitStaffProps {
  measures: Measure[];
  /** Trama el compás que el validador señala. */
  flagged?: boolean;
  className?: string;
}

/** Pentagrama vectorial del incipit sintético. Decorativo: el texto que lo acompaña lo describe. */
export function IncipitStaff({ measures, flagged = false, className }: IncipitStaffProps) {
  const patternId = `trama-${useId().replace(/:/g, "")}`;
  const notes = placeNotes(measures);
  const beamed = beamGroups(notes);
  const beamedNotes = new Set(beamed.flat());
  const flag = flagRegion();

  return (
    <svg
      className={className}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <pattern id={patternId} width="7" height="7" patternUnits="userSpaceOnUse">
          <circle cx="3.5" cy="3.5" r="1.8" style={{ fill: "var(--color-accent)" }} />
        </pattern>
      </defs>

      {flagged && (
        <rect
          x={flag.x}
          y={flag.y}
          width={flag.width}
          height={flag.height}
          fill={`url(#${patternId})`}
          style={{ stroke: "var(--color-accent)" }}
          strokeWidth="4"
        />
      )}

      <g style={{ stroke: "var(--color-ink)" }} strokeWidth="3">
        {[0, 1, 2, 3, 4].map((line) => (
          <line
            key={line}
            x1="0"
            x2={width}
            y1={staffTop + line * space}
            y2={staffTop + line * space}
          />
        ))}
        {[0, 1, 2, 3].map((bar) => (
          <line key={bar} x1={measureX(bar)} x2={measureX(bar)} y1={staffTop} y2={STAFF_BOTTOM} />
        ))}
        <line
          x1={measureX(4) - 4}
          x2={measureX(4) - 4}
          y1={staffTop}
          y2={STAFF_BOTTOM}
          strokeWidth="9"
        />
      </g>

      <g style={{ fill: "var(--color-ink)" }}>
        <text x="12" y={staffTop + 3 * space + 4} fontFamily="'Noto Music'" fontSize={space * 4.1}>
          {TREBLE_CLEF}
        </text>
        <text
          x={firstBarX - 74}
          y={staffTop + 2 * space - 4}
          fontFamily="'Pixelify Sans'"
          fontWeight="700"
          fontSize={space * 2.2}
        >
          3
        </text>
        <text
          x={firstBarX - 74}
          y={STAFF_BOTTOM - 2}
          fontFamily="'Pixelify Sans'"
          fontWeight="700"
          fontSize={space * 2.2}
        >
          4
        </text>

        {notes.map((note) => {
          const open = note.beats >= 2;
          const up = stemUp(note.pitch);
          const sx = stemX(note, up);
          return (
            <g key={`${note.measure}-${note.x}`}>
              <ellipse
                cx={note.x}
                cy={note.y}
                rx={HEAD_RX}
                ry={HEAD_RY}
                transform={`rotate(-20 ${note.x} ${note.y})`}
                style={
                  open ? { fill: "none", stroke: "var(--color-ink)" } : { fill: "var(--color-ink)" }
                }
                strokeWidth={open ? 5 : 0}
              />
              {note.beats < 3 && (
                <line
                  x1={sx}
                  x2={sx}
                  y1={note.y}
                  y2={up ? note.y - STEM : note.y + STEM}
                  style={{ stroke: "var(--color-ink)" }}
                  strokeWidth="4"
                />
              )}
              {note.beats === 3 && (
                <circle cx={note.x + space * 1.1} cy={note.y - space * 0.25} r="5" />
              )}
              {note.beats === 0.5 && !beamedNotes.has(note) && (
                <path
                  d={`M${sx} ${up ? note.y - STEM : note.y + STEM} q ${space * 0.9} ${up ? space * 1.1 : -space * 1.1} ${space * 0.5} ${up ? space * 2.2 : -space * 2.2}`}
                  style={{ fill: "none", stroke: "var(--color-ink)" }}
                  strokeWidth="4"
                />
              )}
            </g>
          );
        })}

        {beamed.map((group) => {
          const first = group[0];
          const last = group.at(-1);
          if (!first || !last) return null;
          const up = stemUp(first.pitch);
          const x1 = stemX(first, up) - (up ? 0 : 2);
          const x2 = stemX(last, up) + (up ? 2 : 0);
          const y1 = up ? first.y - STEM : first.y + STEM;
          const y2 = up ? last.y - STEM : last.y + STEM;
          const thickness = space * 0.5 * (up ? 1 : -1);
          return (
            <polygon
              key={`beam-${first.measure}-${first.x}`}
              points={`${x1},${y1} ${x2},${y2} ${x2},${y2 + thickness} ${x1},${y1 + thickness}`}
            />
          );
        })}
      </g>
    </svg>
  );
}
