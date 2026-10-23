import { useId } from "react";
import { flagRegion, GEOMETRY, type Measure } from "./incipit";
import { HEAD_RX, HEAD_RY, layoutIncipit, STAFF_END } from "./notation";

const { width, height, staffTop, space } = GEOMETRY;
const STAFF_BOTTOM = staffTop + 4 * space;

interface IncipitStaffProps {
  measures: Measure[];
  /**
   * Marca del compás 3: «flagged» lo trama en violeta (el validador lo señala) y
   * «resolved» lo enmarca en tinta (la persona ya lo corrigió).
   */
  mark?: "flagged" | "resolved";
  className?: string;
}

/** Pentagrama vectorial del incipit sintético. Decorativo: el texto que lo acompaña lo describe. */
export function IncipitStaff({ measures, mark, className }: IncipitStaffProps) {
  const patternId = `trama-${useId().replace(/:/g, "")}`;
  const layout = layoutIncipit(measures);
  const region = flagRegion();

  return (
    <svg
      className={className}
      viewBox={`0 0 ${String(width)} ${String(height)}`}
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <pattern id={patternId} width="7" height="7" patternUnits="userSpaceOnUse">
          <circle cx="3.5" cy="3.5" r="1.8" style={{ fill: "var(--color-accent)" }} />
        </pattern>
      </defs>

      {mark === "flagged" && (
        <rect
          {...region}
          fill={`url(#${patternId})`}
          style={{ stroke: "var(--color-accent)" }}
          strokeWidth="4"
        />
      )}
      {mark === "resolved" && (
        <rect {...region} fill="none" style={{ stroke: "var(--color-ink)" }} strokeWidth="4" />
      )}

      <g style={{ stroke: "var(--color-ink)" }} strokeWidth="3">
        {layout.staffLines.map((y) => (
          <line key={y} x1="0" x2={STAFF_END} y1={y} y2={y} />
        ))}
        {layout.barlines.map((bar) => (
          <line
            key={bar.x}
            x1={bar.x}
            x2={bar.x}
            y1={staffTop}
            y2={STAFF_BOTTOM}
            strokeWidth={bar.width}
          />
        ))}
      </g>

      <g style={{ fill: "var(--color-ink)", stroke: "var(--color-ink)" }}>
        {layout.glyphs.map((glyph) => (
          <path
            key={glyph.tx}
            d={glyph.path}
            transform={`translate(${String(glyph.tx)} ${String(glyph.ty)}) scale(${String(glyph.scale)})`}
            strokeWidth={glyph.stroke}
            strokeLinejoin="round"
            paintOrder="stroke"
          />
        ))}

        {layout.notes.map(({ note, open, stem, dot }) => (
          <g key={`${String(note.measure)}-${String(note.x)}`}>
            <ellipse
              cx={note.x}
              cy={note.y}
              rx={HEAD_RX}
              ry={HEAD_RY}
              transform={`rotate(-20 ${String(note.x)} ${String(note.y)})`}
              style={open ? { fill: "none" } : { stroke: "none" }}
              strokeWidth={open ? 5 : 0}
            />
            {stem && <line x1={stem.x} x2={stem.x} y1={stem.y1} y2={stem.y2} strokeWidth="4" />}
            {dot && <circle cx={dot.cx} cy={dot.cy} r="5" style={{ stroke: "none" }} />}
          </g>
        ))}

        {layout.beams.map((points) => (
          <polygon
            key={points.map((point) => point.join(",")).join(" ")}
            points={points.map((point) => point.join(",")).join(" ")}
            style={{ stroke: "none" }}
          />
        ))}
      </g>
    </svg>
  );
}
