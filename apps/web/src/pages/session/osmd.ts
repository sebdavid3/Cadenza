import type { MeasureSlot } from "./findings";

/** Caja de un compás en píxeles, relativa a la esquina superior izquierda de la partitura. */
export interface Box {
  left: number;
  top: number;
  width: number;
  height: number;
}

/** Partitura dibujada por OSMD, reducida a lo que la vista necesita (ADR-0006, ADR-0021). */
export interface RenderedScore {
  /** Compases dibujados de cada pentagrama, en el orden global de OSMD. */
  measuresPerStaff(): number[];
  measureBox(slot: MeasureSlot): Box | null;
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
    relayout(width) {
      osmd.zoom = zoomFor(width);
      osmd.render();
    },
    dispose() {
      osmd.clear();
    },
  };
}
