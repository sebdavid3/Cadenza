// Incipit sintético de la landing: una ilustración, no la salida de una transcripción real.
// En 3/4 y clave de sol. La «lectura del motor» confunde dos corcheas con negras en el
// compás 3, que suma así cuatro tiempos: es el compás que el validador señala.

export type Pitch = "C4" | "D4" | "E4" | "F4" | "G4" | "A4" | "B4" | "C5" | "D5" | "E5" | "F5";

export interface IncipitNote {
  pitch: Pitch;
  /** Duración en negras: 0.5 corchea, 1 negra, 2 blanca, 3 blanca con puntillo. */
  beats: number;
}

export type Measure = IncipitNote[];

export const BEATS_PER_MEASURE = 3;

/** Lo que «lee» el motor: el compás 3 suma 4 tiempos. */
export const OMR_READING: Measure[] = [
  [
    { pitch: "E5", beats: 1 },
    { pitch: "D5", beats: 1 },
    { pitch: "C5", beats: 1 },
  ],
  [
    { pitch: "G4", beats: 2 },
    { pitch: "A4", beats: 1 },
  ],
  [
    { pitch: "B4", beats: 1 },
    { pitch: "C5", beats: 1 },
    { pitch: "D5", beats: 1 },
    { pitch: "E5", beats: 1 },
  ],
  [{ pitch: "C5", beats: 3 }],
];

/** Tras dos correcciones de duración: las dos primeras notas del compás 3 son corcheas. */
export const CORRECTED: Measure[] = OMR_READING.map((measure, index) =>
  index === 2
    ? [
        { pitch: "B4", beats: 0.5 },
        { pitch: "C5", beats: 0.5 },
        { pitch: "D5", beats: 1 },
        { pitch: "E5", beats: 1 },
      ]
    : measure,
);

/** Índice (desde 0) del compás que el validador señala. */
export const FLAGGED_MEASURE = 2;

const STEPS: Record<Pitch, number> = {
  C4: -2,
  D4: -1,
  E4: 0,
  F4: 1,
  G4: 2,
  A4: 3,
  B4: 4,
  C5: 5,
  D5: 6,
  E5: 7,
  F5: 8,
};

// Geometría en unidades del viewBox.
export const GEOMETRY = {
  width: 1360,
  height: 262,
  staffTop: 64,
  space: 34,
  firstBarX: 190,
} as const;

const { width, staffTop, space, firstBarX } = GEOMETRY;
export const MEASURE_WIDTH = (width - firstBarX - 20) / 4;
export const STAFF_BOTTOM = staffTop + 4 * space;

/** Altura de la nota: E4 en la línea inferior, cada paso medio espacio. */
export function pitchY(pitch: Pitch): number {
  return STAFF_BOTTOM - STEPS[pitch] * (space / 2);
}

/** La plica sube por debajo de la tercera línea (B4) y baja desde ella. */
export function stemUp(pitch: Pitch): boolean {
  return STEPS[pitch] < STEPS.B4;
}

export interface PlacedNote extends IncipitNote {
  measure: number;
  x: number;
  y: number;
}

export function measureX(index: number): number {
  return firstBarX + index * MEASURE_WIDTH;
}

export function placeNotes(measures: Measure[]): PlacedNote[] {
  return measures.flatMap((notes, index) => {
    const total = Math.max(
      notes.reduce((sum, note) => sum + note.beats, 0),
      BEATS_PER_MEASURE,
    );
    const inner = MEASURE_WIDTH - 2 * 30;
    let elapsed = 0;
    return notes.map((note) => {
      const placed = {
        ...note,
        measure: index,
        x: measureX(index) + 30 + (elapsed / total) * inner,
        y: pitchY(note.pitch),
      };
      elapsed += note.beats;
      return placed;
    });
  });
}

/** Recuadro del compás señalado, en unidades del viewBox. */
export function flagRegion() {
  return {
    x: measureX(FLAGGED_MEASURE) + 6,
    y: staffTop - space * 1.7,
    width: MEASURE_WIDTH - 12,
    height: space * 7.4,
  };
}
