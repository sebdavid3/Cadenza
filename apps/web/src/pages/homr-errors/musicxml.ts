// El compás de un ejemplo de un corpus como un MusicXML mínimo, para grabarlo con OSMD como el
// editor (#424): un pentagrama con su clave, su armadura y sus eventos, sin compás escrito (no se
// sabe) y con la nota del ejemplo en violeta. Lo que no se puede escribir con figuras da null, y
// entonces se dibuja como en el informe (`DrawnBar`).

import type { DrawnEventRead, FigureRead } from "../../types";
import { parsePitch } from "./drawing";

/** Una fracción de negra: numerador y denominador, positivos y reducidos. */
type Fraction = readonly [number, number];

const gcd = (a: number, b: number): number => (b === 0 ? a : gcd(b, a % b));
const lcm = (a: number, b: number) => (a / gcd(a, b)) * b;

function reduce([n, d]: Fraction): Fraction {
  const g = gcd(n, d) || 1;
  return [n / g, d / g];
}

const add = (a: Fraction, b: Fraction): Fraction =>
  reduce([a[0] * b[1] + b[0] * a[1], a[1] * b[1]]);
const times = (a: Fraction, b: Fraction): Fraction => reduce([a[0] * b[0], a[1] * b[1]]);

/** Cada figura, por su nombre en la página: su tipo en MusicXML y lo que dura en negras. */
const FIGURES: Record<string, { type: string; value: Fraction }> = {
  longa: { type: "long", value: [16, 1] },
  cuadrada: { type: "breve", value: [8, 1] },
  redonda: { type: "whole", value: [4, 1] },
  blanca: { type: "half", value: [2, 1] },
  negra: { type: "quarter", value: [1, 1] },
  corchea: { type: "eighth", value: [1, 2] },
  semicorchea: { type: "16th", value: [1, 4] },
  fusa: { type: "32nd", value: [1, 8] },
  semifusa: { type: "64th", value: [1, 16] },
  garrapatea: { type: "128th", value: [1, 32] },
};
const DOTS: readonly Fraction[] = [
  [1, 1],
  [3, 2],
  [7, 4],
];
/** Grupos irregulares: notas del grupo → notas normales que ocupan (como `TUPLETS` del informe). */
const NORMAL_NOTES: Record<number, number> = { 3: 2, 5: 4, 7: 4 };

/** Una figura escrita de un evento: su tipo, sus puntillos, su grupo irregular y lo que dura. */
interface Written {
  type: string;
  dots: number;
  tuplet: number;
  grace: boolean;
  value: Fraction;
}

/** Las figuras que escriben una duración (ligadas si son varias), o null si no se puede. */
function written(beats: string, figures: Record<string, FigureRead>): Written[] | null {
  const symbol = figures[beats]?.symbol ?? [];
  if (!symbol.length) return null;
  const parts: Written[] = [];
  for (const part of symbol) {
    const figure = FIGURES[part.figure];
    const dots = DOTS[part.dots];
    const normal = part.tuplet ? NORMAL_NOTES[part.tuplet] : 1;
    if (!figure || !dots || normal === undefined) return null;
    const value = times(times(figure.value, dots), [normal, part.tuplet || 1]);
    parts.push({
      type: figure.type,
      dots: part.dots,
      tuplet: part.tuplet,
      grace: part.grace,
      value,
    });
  }
  return parts;
}

/** La clave («G2», «F4», «C3», «G2-1»); sin clave, la de sol. */
function clefXml(clef: string): string {
  const match = /^([GFC])(\d)([+-]\d)?$/.exec(clef);
  const [, sign = "G", line = "2", octave] = match ?? [];
  const change = octave ? `<clef-octave-change>${String(Number(octave))}</clef-octave-change>` : "";
  return `<clef><sign>${sign}</sign><line>${line}</line>${change}</clef>`;
}

/** La métrica (oculta) que suma lo que dura el compás: 7/2 negras, 7/8. */
function timeXml(total: Fraction): string {
  const [n, d] = total;
  const power = (d & (d - 1)) === 0;
  const [beats, beatType] = n > 0 && power ? [n, 4 * d] : [4, 4];
  return `<time print-object="no"><beats>${String(beats)}</beats><beat-type>${String(beatType)}</beat-type></time>`;
}

/** Un evento y lo que suena con él (sus notas de acorde), con las figuras que lo escriben. */
interface Chord {
  members: { event: DrawnEventRead; focus: boolean }[];
  parts: Written[];
}

function noteXml(
  event: DrawnEventRead,
  part: Written,
  options: {
    chord: boolean;
    first: boolean;
    last: boolean;
    divisions: number;
    color: string | null;
  },
): string | null {
  const color = options.color ? ` color="${options.color}"` : "";
  let body: string;
  if (event.kind === "rest") {
    body = "<rest/>";
  } else {
    const pitch = parsePitch(event.pitch);
    if (!pitch) return null;
    const alter = pitch.alter ? `<alter>${String(pitch.alter)}</alter>` : "";
    body = `<pitch><step>${pitch.step}</step>${alter}<octave>${String(Math.floor(pitch.d / 7))}</octave></pitch>`;
  }
  const tied = event.kind === "note" && !part.grace;
  const ties = [
    ...(tied && !options.first ? ["stop"] : []),
    ...(tied && !options.last ? ["start"] : []),
  ];
  const duration = part.grace
    ? ""
    : `<duration>${String((part.value[0] * options.divisions) / part.value[1])}</duration>`;
  const tuplet = part.tuplet
    ? `<time-modification><actual-notes>${String(part.tuplet)}</actual-notes><normal-notes>${String(NORMAL_NOTES[part.tuplet])}</normal-notes></time-modification>`
    : "";
  const notehead = options.color ? `<notehead color="${options.color}">normal</notehead>` : "";
  const notations = ties.length
    ? `<notations>${ties.map((type) => `<tied type="${type}"/>`).join("")}</notations>`
    : "";
  return (
    `<note${color}>${part.grace ? "<grace/>" : ""}${options.chord ? "<chord/>" : ""}${body}` +
    `${duration}${ties.map((type) => `<tie type="${type}"/>`).join("")}<voice>1</voice>` +
    `<type>${part.type}</type>${"<dot/>".repeat(part.dots)}${tuplet}${notehead}${notations}</note>`
  );
}

/**
 * El MusicXML de un pentagrama del compás de un ejemplo: `events` con su clave (`clef`) y su
 * armadura (`key`, en quintas), y el evento del ejemplo (`focus`) en `color`. Null si algún
 * evento no se puede escribir (una duración sin figuras o una altura que no se entiende).
 */
export function barMusicXml(
  clef: string,
  key: number,
  events: readonly DrawnEventRead[],
  focus: number | null | undefined,
  figures: Record<string, FigureRead>,
  color: string,
): string | null {
  const chords: Chord[] = [];
  for (const [index, event] of events.entries()) {
    const member = { event, focus: index === focus };
    const last = chords[chords.length - 1];
    if (event.chord && last) {
      last.members.push(member);
      continue;
    }
    const parts = written(event.beats, figures);
    if (!parts) return null;
    chords.push({ members: [member], parts });
  }
  let divisions = 1;
  let total: Fraction = [0, 1];
  for (const chord of chords) {
    for (const part of chord.parts) {
      divisions = lcm(divisions, part.value[1]);
      if (!part.grace) total = add(total, part.value);
    }
  }
  const notes: string[] = [];
  for (const chord of chords) {
    for (const [at, part] of chord.parts.entries()) {
      for (const [position, { event, focus: isFocus }] of chord.members.entries()) {
        const note = noteXml(event, part, {
          chord: position > 0,
          first: at === 0,
          last: at === chord.parts.length - 1,
          divisions,
          color: isFocus ? color : null,
        });
        if (note === null) return null;
        notes.push(note);
      }
    }
  }
  if (!notes.length) {
    // Un pentagrama vacío (HOMR no leyó nada): un silencio de compás que no se ve.
    notes.push(
      `<note print-object="no"><rest measure="yes"/><duration>${String(4 * divisions)}</duration><voice>1</voice></note>`,
    );
    total = [4, 1];
  }
  const attributes =
    `<attributes><divisions>${String(divisions)}</divisions>` +
    `<key><fifths>${String(Math.max(-7, Math.min(7, key)))}</fifths></key>` +
    `${timeXml(total)}${clefXml(clef)}</attributes>`;
  return (
    `<?xml version="1.0" encoding="UTF-8"?>` +
    `<score-partwise version="4.0"><part-list><score-part id="P1"><part-name print-object="no"></part-name></score-part></part-list>` +
    `<part id="P1"><measure number="1">${attributes}${notes.join("")}</measure></part></score-partwise>`
  );
}
