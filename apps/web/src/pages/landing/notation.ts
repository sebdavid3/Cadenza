import { TIME_SIGNATURE_DIGITS, TREBLE_CLEF_PATH, type DigitGlyph } from "./glyphs";
import {
  GEOMETRY,
  measureX,
  placeNotes,
  STAFF_BOTTOM,
  stemUp,
  type Measure,
  type PlacedNote,
} from "./incipit";

const { staffTop, space, firstBarX } = GEOMETRY;

const STEM_LENGTH = space * 3.4;
const STEM_OFFSET = space * 0.56;
export const HEAD_RX = space * 0.62;
export const HEAD_RY = space * 0.44;
const DIGIT_STROKE = 100;

/** Fin del pentagrama: el borde derecho de la doble barra final. */
export const STAFF_END = measureX(4);

export interface GlyphPlacement {
  path: string;
  tx: number;
  ty: number;
  scale: number;
  /** Trazo en unidades de la fuente para engrosar las cifras de compás. */
  stroke: number;
}

export interface NoteLayout {
  note: PlacedNote;
  open: boolean;
  stem: { x: number; y1: number; y2: number } | null;
  dot: { cx: number; cy: number } | null;
}

export interface Layout {
  staffLines: number[];
  barlines: { x: number; width: number }[];
  glyphs: GlyphPlacement[];
  notes: NoteLayout[];
  beams: [number, number][][];
}

function digitPlacement(glyph: DigitGlyph, baseline: number, centerX: number): GlyphPlacement {
  const [x0, y0, x1, y1] = glyph.bounds;
  // Cada cifra ocupa exactamente dos espacios, trazo incluido.
  const scale = (2 * space) / (y1 - y0 + DIGIT_STROKE);
  return {
    path: glyph.path,
    tx: centerX - ((x0 + x1) / 2) * scale,
    ty: baseline - (DIGIT_STROKE / 2) * scale + y0 * scale,
    scale,
    stroke: DIGIT_STROKE,
  };
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

export function layoutIncipit(measures: Measure[]): Layout {
  const placed = placeNotes(measures);
  const notes = placed.map((note): NoteLayout => {
    const up = stemUp(note.pitch);
    const x = up ? note.x + STEM_OFFSET : note.x - STEM_OFFSET;
    return {
      note,
      open: note.beats >= 2,
      // Todas llevan plica salvo la redonda (4 tiempos), que no aparece en el incipit.
      stem:
        note.beats < 4
          ? { x, y1: note.y, y2: up ? note.y - STEM_LENGTH : note.y + STEM_LENGTH }
          : null,
      dot: note.beats === 3 ? { cx: note.x + space * 1.1, cy: note.y - space * 0.25 } : null,
    };
  });

  const beams = beamGroups(placed).map((group) => {
    const ends = group
      .map((note) => notes.find((layout) => layout.note === note)?.stem)
      .filter((stem): stem is NonNullable<typeof stem> => Boolean(stem));
    const first = ends[0];
    const last = ends.at(-1);
    if (!first || !last) return [];
    const down = first.y2 > first.y1;
    const thickness = space * 0.5 * (down ? -1 : 1);
    return [
      [first.x - 2, first.y2],
      [last.x + 2, last.y2],
      [last.x + 2, last.y2 + thickness],
      [first.x - 2, first.y2 + thickness],
    ] as [number, number][];
  });

  return {
    staffLines: [0, 1, 2, 3, 4].map((line) => staffTop + line * space),
    // Sin barra tras la cifra de compás: el primer compás empieza en ella.
    barlines: [
      { x: measureX(1), width: 3 },
      { x: measureX(2), width: 3 },
      { x: measureX(3), width: 3 },
      { x: STAFF_END - 16, width: 3 },
      { x: STAFF_END - 4.5, width: 9 },
    ],
    glyphs: [
      {
        path: TREBLE_CLEF_PATH,
        tx: 12,
        ty: staffTop + 3 * space,
        scale: (space * 4.1) / 1000,
        stroke: 0,
      },
      digitPlacement(TIME_SIGNATURE_DIGITS["3"], staffTop + 2 * space, firstBarX - 54),
      digitPlacement(TIME_SIGNATURE_DIGITS["4"], STAFF_BOTTOM, firstBarX - 54),
    ],
    notes,
    beams,
  };
}
