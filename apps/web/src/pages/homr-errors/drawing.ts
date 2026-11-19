// Lo que decide cómo se dibuja un compás de un ejemplo (#424), como en el informe local: dónde va
// cada nota según la clave, qué alteraciones se escriben y dónde va la armadura.

import type { DrawnEventRead } from "../../types";

const STEPS = "CDEFGAB";
const SHARPS = "FCGDAEB";
const FLATS = "BEADGCF";
const CLEF_REF: Record<string, number> = { G: 4 * 7 + 4, F: 3 * 7 + 3, C: 4 * 7 };

export interface Pitch {
  step: string;
  alter: number;
  /** Posición diatónica: octava × 7 + nota. */
  d: number;
}

export interface Clef {
  sign: string;
  /** La línea de la clave, en medios espacios desde la línea de abajo. */
  linePos: number;
  d: number;
}

export function parsePitch(pitch: string): Pitch | null {
  const match = /^([A-G])([#b]*)(-?\d+)$/.exec(pitch);
  if (!match) return null;
  const [, step = "C", marks = "", octave = "0"] = match;
  const alter = (marks.match(/#/g)?.length ?? 0) - (marks.match(/b/g)?.length ?? 0);
  return { step, alter, d: Number(octave) * 7 + STEPS.indexOf(step) };
}

/** La clave («G2», «F4», «C3», «G2-1»): su signo, su línea y la nota que marca. Sin clave, la
 * de sol. */
export function clefOf(clef: string): Clef {
  const match = /^([GFC])(\d)([+-]\d)?$/.exec(clef);
  const sign = match?.[1] ?? "G";
  const line = Number(match?.[2] ?? "2");
  const octave = match?.[3];
  return {
    sign,
    linePos: 2 * (line - 1),
    d: (CLEF_REF[sign] ?? 32) + (octave ? Number(octave) * 7 : 0),
  };
}

/** Dónde cae una nota en el pentagrama, en medios espacios desde la línea de abajo. */
export function staffPosition(pitch: Pitch, clef: Clef): number {
  return clef.linePos + (pitch.d - clef.d);
}

/** La alteración que pone la armadura a una nota. */
export function keyAlter(step: string, fifths: number): number {
  if (fifths > 0) return SHARPS.slice(0, fifths).includes(step) ? 1 : 0;
  if (fifths < 0) return FLATS.slice(0, -fifths).includes(step) ? -1 : 0;
  return 0;
}

/** Qué notas llevan escrita su alteración: la que cambia lo que rige en el compás para esa letra
 * y octava, que es la armadura y, después, la última alteración escrita, como en una partitura. */
export function writtenAccidentals(events: DrawnEventRead[], fifths: number): boolean[] {
  const carry = new Map<number, number>();
  return events.map((event) => {
    const pitch = event.kind === "note" ? parsePitch(event.pitch) : null;
    if (!pitch) return false;
    const written = pitch.alter !== (carry.get(pitch.d) ?? keyAlter(pitch.step, fifths));
    carry.set(pitch.d, pitch.alter);
    return written;
  });
}

/** Dónde va cada alteración de la armadura, en medios espacios desde la línea de abajo: las de la
 * clave de sol, desplazadas por la clave (en la de fa, dos posiciones más abajo; en la de do en
 * 3.ª, una) y dentro del pentagrama. */
export function keySignaturePositions(clef: Clef, fifths: number): number[] {
  const model = fifths > 0 ? [38, 35, 39, 36, 33, 37, 34] : [34, 37, 33, 36, 32, 35, 31];
  let shift = (((clef.linePos - clef.d + 30) % 7) + 7) % 7;
  if (shift > 3) shift -= 7;
  const positions: number[] = [];
  for (let i = 0; i < Math.min(7, Math.abs(fifths)); i++) {
    let pos = 2 + ((model[i] ?? 32) - 32) + shift;
    if (pos > 9) pos -= 7;
    if (pos < -1) pos += 7;
    positions.push(pos);
  }
  return positions;
}
