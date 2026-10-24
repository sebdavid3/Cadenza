import type { GraphicalMeasure, GraphicalNote } from "opensheetmusicdisplay";
import type { MeasureSlot } from "./findings";

/** Caja en píxeles, relativa a la esquina superior izquierda de la partitura. */
export interface Box {
  left: number;
  top: number;
  width: number;
  height: number;
}

/** Nota o silencio dibujado: su altura, si es nota, y la caja de su cabeza o de su glifo. */
export interface DrawnNote {
  /** Altura como número MIDI; null en un silencio. */
  midi: number | null;
  /** Nombre de la nota sin alteración («C»…«B»), para distinguir enarmonías. */
  step: string | null;
  box: Box | null;
}

/** Figura de una voz: una nota, un acorde o un silencio, con su duración en negras. */
export interface DrawnFigure {
  rest: boolean;
  grace: boolean;
  /** Duración en negras como fracción exacta: numerador y denominador. */
  beats: readonly [number, number];
  notes: readonly DrawnNote[];
}

/** Figuras de una voz de un compás, en orden. */
export type DrawnVoice = readonly DrawnFigure[];

/** Partitura dibujada por OSMD, reducida a lo que la vista necesita (ADR-0006, ADR-0021). */
export interface RenderedScore {
  /** Compases dibujados de cada pentagrama, en el orden global de OSMD. */
  measuresPerStaff(): number[];
  measureBox(slot: MeasureSlot): Box | null;
  /** Figuras dibujadas en un compás, por voces en el orden de su número (ADR-0027). */
  measureFigures(slot: MeasureSlot): DrawnVoice[] | null;
  /** Vuelve a maquetar al ancho actual del contenedor. */
  relayout(width: number): void;
  dispose(): void;
}

/** OSMD mide en unidades de 10 px a zoom 1; las cinco líneas ocupan 4 unidades. */
const UNIT_PX = 10;
const STAFF_HEIGHT_UNITS = 4;
/**
 * Margen de la marca por encima y por debajo de las cinco líneas, en unidades. Todas las marcas
 * de un sistema tienen así la misma altura, aunque un compás tenga notas más agudas.
 */
const MARK_PADDING_UNITS = 2;
/** Margen inferior de la página: OSMD reserva espacio para un pie que aquí no hay. */
const PAGE_BOTTOM_MARGIN_UNITS = 2;

/** Por debajo de este ancho la notación se dibuja más pequeña para que quepan más compases. */
const NARROW_WIDTH = 640;
const zoomFor = (width: number) => (width < NARROW_WIDTH ? 0.75 : 1);

/** Nombre de cada nota natural según el semitono de `NoteEnum` de OSMD. */
const STEP_NAMES: Record<number, string> = {
  0: "C",
  2: "D",
  4: "E",
  5: "F",
  7: "G",
  9: "A",
  11: "B",
};
/** OSMD cuenta la octava del do central como la 1: su semitono 48 es el MIDI 60. */
const OSMD_HALF_TONE_TO_MIDI = 12;

function relativeBox(element: Element, origin: DOMRect): Box {
  const rect = element.getBoundingClientRect();
  return {
    left: rect.left - origin.left,
    top: rect.top - origin.top,
    width: rect.width,
    height: rect.height,
  };
}

/** Elemento SVG que dibuja una nota: lo da la nota de VexFlow, con el backend SVG. */
function noteElement(note: GraphicalNote): SVGGElement | null {
  const drawn = note as GraphicalNote & { getSVGGElement?: () => SVGGElement | undefined };
  return drawn.getSVGGElement?.() ?? null;
}

/**
 * Cabezas propias del elemento de una nota: no las de sus modificadores. VexFlow anida en ellos
 * las notas de adorno que la preceden, y sus puntillos.
 */
function ownHeads(element: SVGGElement): Element[] {
  return [...element.querySelectorAll(".vf-notehead")].filter(
    (head) => head.closest(".vf-stavenote") === element,
  );
}

/**
 * Altura y caja de una nota dibujada. La caja es la de su cabeza en el SVG: en un acorde, la
 * cabeza más cercana a la altura en que OSMD sitúa la nota, que es el centro de su cabeza. En un
 * silencio, la de su glifo, que VexFlow dibuja también como cabeza; sin ella, el elemento entero.
 */
function drawnNote(note: GraphicalNote, origin: DOMRect, unit: number): DrawnNote {
  const source = note.sourceNote;
  const element = noteElement(note);
  const heads = element ? ownHeads(element) : [];
  if (source.isRest()) {
    const glyph = heads[0] ?? element;
    return { midi: null, step: null, box: glyph ? relativeBox(glyph, origin) : null };
  }
  const centre = note.PositionAndShape.AbsolutePosition.y * unit;
  let box: Box | null = null;
  let distance = Infinity;
  for (const head of heads) {
    const candidate = relativeBox(head, origin);
    const offset = Math.abs(candidate.top + candidate.height / 2 - centre);
    if (offset < distance) {
      distance = offset;
      box = candidate;
    }
  }
  const pitch = source.Pitch;
  return {
    midi: pitch.getHalfTone() + OSMD_HALF_TONE_TO_MIDI,
    step: STEP_NAMES[pitch.FundamentalNote] ?? null,
    box,
  };
}

/**
 * Figuras de un compás dibujado, agrupadas por voz y en el orden del número de voz. Un silencio
 * invisible (`print-object="no"`, ADR-0032) no es una figura: OSMD lo guarda pero no lo dibuja.
 */
function measureFigures(measure: GraphicalMeasure, origin: DOMRect, unit: number): DrawnVoice[] {
  const voices = new Map<number, DrawnFigure[]>();
  for (const entry of measure.staffEntries) {
    for (const voiceEntry of entry.graphicalVoiceEntries) {
      const first = voiceEntry.notes[0];
      if (!first || voiceEntry.notes.every((note) => !note.sourceNote.PrintObject)) continue;
      // OSMD mide en redondas y guarda aparte la parte entera: 11/8 es 1 + 3/8.
      const length = first.sourceNote.Length;
      const figure: DrawnFigure = {
        rest: first.sourceNote.isRest(),
        grace: voiceEntry.parentVoiceEntry.IsGrace,
        beats: [length.GetExpandedNumerator() * 4, length.Denominator],
        notes: voiceEntry.notes.map((note) => drawnNote(note, origin, unit)),
      };
      const id = voiceEntry.parentVoiceEntry.ParentVoice.VoiceId;
      const figures = voices.get(id);
      if (figures) figures.push(figure);
      else voices.set(id, [figure]);
    }
  }
  return [...voices.entries()].sort(([a], [b]) => a - b).map(([, figures]) => figures);
}

function cssColor(name: string, fallback: string): string {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

/** Se cancela un dibujo que ya no hace falta (la vista se desmontó mientras cargaba). */
function abortError() {
  return new DOMException("Dibujo cancelado", "AbortError");
}

/**
 * Analiza el MusicXML antes de dárselo a OSMD: con una cadena corta que no empieza por `<?xml`,
 * OSMD la trataría como una URL que descargar.
 */
function parseMusicXml(xml: string): Document {
  const document = new DOMParser().parseFromString(xml, "application/xml");
  if (document.getElementsByTagName("parsererror").length > 0) {
    throw new Error("El MusicXML no es XML válido");
  }
  return withInitialAttributes(document);
}

/** Hijos de `<attributes>` que van antes que la armadura, y los que van después de la clave. */
const BEFORE_KEY = new Set(["footnote", "level", "divisions"]);
const AFTER_CLEF = new Set([
  "staff-details",
  "transpose",
  "for-part",
  "directive",
  "measure-style",
]);

const childrenNamed = (parent: Element, name: string) =>
  [...parent.children].filter((child) => child.localName === name);

/** Pentagrama de una clave: el de su `number`, o el primero (MusicXML). */
const clefStaff = (clef: Element) => clef.getAttribute("number") ?? "1";

/**
 * Escribe en el primer compás de cada parte la armadura y la clave que el MusicXML deja sin
 * escribir cuando otro compás las cambia. Sin ellas, OSMD 2.2.1 toma la primera que encuentra y
 * la dibuja desde el principio: un cambio de armadura en el compás 2 de una partitura sin
 * armadura salía en el compás 1, y sus notas con becuadros (ADR-0033). Sin armadura es «sin
 * alteraciones» y sin clave, la de sol, como las entiende la vista (`activeFifths`, `activeClef`).
 * Solo cambia lo que se dibuja: la descarga es el MusicXML exportado tal cual.
 */
export function withInitialAttributes(document: Document): Document {
  const namespace = document.documentElement.namespaceURI;
  const create = (name: string, children: Record<string, string>) => {
    const element = document.createElementNS(namespace, name);
    for (const [child, text] of Object.entries(children)) {
      const node = document.createElementNS(namespace, child);
      node.textContent = text;
      element.appendChild(node);
    }
    return element;
  };
  for (const part of [...document.getElementsByTagName("part")]) {
    const [first, ...later] = childrenNamed(part, "measure");
    if (!first) continue;
    const attributesOf = (measure: Element) => childrenNamed(measure, "attributes");
    const laterAttributes = later.flatMap(attributesOf);
    const firstAttributes = attributesOf(first);
    const has = (name: string, attributes: Element[]) =>
      attributes.flatMap((element) => childrenNamed(element, name));
    const missingKey =
      has("key", firstAttributes).length === 0 && has("key", laterAttributes).length > 0;
    const firstClefs = new Set(has("clef", firstAttributes).map(clefStaff));
    const missingClefs = [...new Set(has("clef", laterAttributes).map(clefStaff))].filter(
      (staff) => !firstClefs.has(staff),
    );
    if (!missingKey && missingClefs.length === 0) continue;

    let attributes = firstAttributes[0];
    if (!attributes) {
      attributes = document.createElementNS(namespace, "attributes");
      const print = childrenNamed(first, "print")[0];
      first.insertBefore(attributes, print ? print.nextSibling : first.firstChild);
    }
    if (missingKey) {
      const after = [...attributes.children].find((child) => !BEFORE_KEY.has(child.localName));
      attributes.insertBefore(create("key", { fifths: "0" }), after ?? null);
    }
    const staves = Number(childrenNamed(attributes, "staves")[0]?.textContent ?? "1");
    for (const staff of missingClefs) {
      const clef = create("clef", { sign: "G", line: "2" });
      if (staves > 1) clef.setAttribute("number", staff);
      const before = [...attributes.children].find((child) => AFTER_CLEF.has(child.localName));
      attributes.insertBefore(clef, before ?? null);
    }
  }
  return document;
}

/**
 * Carga OSMD bajo demanda (pesa más que el resto de la interfaz junta) y dibuja el MusicXML en
 * `host`. Sin título, compositor ni nombres de parte, que el exportador no tiene, y sin agrupar
 * los silencios de compás en un multicompás, que rompería la correspondencia de compases. Si
 * `signal` se cancela antes de dibujar, no se dibuja y se libera lo cargado.
 */
export async function renderScore(
  host: HTMLElement,
  xml: string,
  signal: AbortSignal,
): Promise<RenderedScore> {
  // Función y no propiedad: TypeScript no sabe que la señal puede cambiar durante un await.
  const cancelled = () => signal.aborted;
  const document = parseMusicXml(xml);
  const { OpenSheetMusicDisplay } = await import("opensheetmusicdisplay");
  if (cancelled()) throw abortError();
  const ink = cssColor("--color-ink", "#0a0a0a");
  const osmd = new OpenSheetMusicDisplay(host, {
    backend: "svg",
    autoResize: false,
    drawTitle: false,
    drawSubtitle: false,
    drawComposer: false,
    drawLyricist: false,
    drawCredits: false,
    drawPartNames: false,
    drawPartAbbreviations: false,
    drawMeasureNumbers: true,
    autoGenerateMultipleRestMeasuresFromRestMeasures: false,
    defaultColorMusic: ink,
    defaultFontFamily: "Hanken Grotesk, system-ui, sans-serif",
  });
  osmd.EngravingRules.PageBottomMargin = PAGE_BOTTOM_MARGIN_UNITS;
  await osmd.load(document);
  if (cancelled()) {
    osmd.clear();
    throw abortError();
  }
  osmd.zoom = zoomFor(host.clientWidth);
  osmd.render();

  return {
    measuresPerStaff() {
      const rows = osmd.GraphicSheet.MeasureList;
      const staves = Math.max(0, ...rows.map((row) => row.length));
      return Array.from(
        { length: staves },
        (_unused, staff) => rows.filter((row) => row[staff] !== undefined).length,
      );
    },
    measureBox(slot) {
      const measure = osmd.GraphicSheet.MeasureList[slot.measure]?.[slot.staff];
      if (!measure) return null;
      const shape = measure.PositionAndShape;
      const unit = UNIT_PX * osmd.zoom;
      // La posición absoluta del compás es la de la línea superior del pentagrama.
      const top = shape.AbsolutePosition.y - MARK_PADDING_UNITS;
      const bottom = shape.AbsolutePosition.y + STAFF_HEIGHT_UNITS + MARK_PADDING_UNITS;
      return {
        left: (shape.AbsolutePosition.x + shape.BorderLeft) * unit,
        top: top * unit,
        width: (shape.BorderRight - shape.BorderLeft) * unit,
        height: (bottom - top) * unit,
      };
    },
    measureFigures(slot) {
      const measure = osmd.GraphicSheet.MeasureList[slot.measure]?.[slot.staff];
      if (!measure) return null;
      return measureFigures(measure, host.getBoundingClientRect(), UNIT_PX * osmd.zoom);
    },
    relayout(width) {
      osmd.zoom = zoomFor(width);
      osmd.render();
    },
    dispose() {
      osmd.clear();
    },
  };
}
