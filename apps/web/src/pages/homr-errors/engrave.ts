// Grabar un pentagrama con OSMD, con las mismas opciones que el editor (`pages/session/osmd.ts`):
// sin título, partes ni números de compás, y aquí sin la métrica, que no se sabe. OSMD se carga
// solo cuando hace falta, como en el editor.

/** Si el navegador sabe medir SVG: OSMD lo necesita (jsdom, en las pruebas, no). */
export function canEngrave(): boolean {
  return typeof SVGGraphicsElement !== "undefined" && "getBBox" in SVGGraphicsElement.prototype;
}

function cssColor(name: string, fallback: string): string {
  if (typeof document === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

/** El violeta del acento, con el que va la nota del ejemplo. */
export function accentColor(): string {
  return cssColor("--color-accent", "#7a2cf0");
}

const cancelled = (signal: AbortSignal) => signal.aborted;

/** Lo grabado no pasa de esta anchura (en px): un compás no necesita más. */
const MAX_WIDTH = 520;
/** Márgenes de la página de OSMD, en sus unidades (10 px a zoom 1): casi ninguno, es un compás. */
const MARGIN_UNITS = 0.5;

/** Graba `xml` en `host`. Si `signal` se cancela antes de cargar OSMD, no graba nada. */
export async function engrave(host: HTMLElement, xml: string, signal: AbortSignal): Promise<void> {
  const { OpenSheetMusicDisplay } = await import("opensheetmusicdisplay");
  if (signal.aborted) return;
  host.replaceChildren();
  // La anchura de su celda, que OSMD llena estirando el compás.
  host.style.width = `${String(Math.min(MAX_WIDTH, host.clientWidth || MAX_WIDTH))}px`;
  const osmd = new OpenSheetMusicDisplay(host, {
    backend: "svg",
    autoResize: false,
    autoBeam: true,
    drawTitle: false,
    drawSubtitle: false,
    drawComposer: false,
    drawLyricist: false,
    drawCredits: false,
    drawPartNames: false,
    drawPartAbbreviations: false,
    drawMeasureNumbers: false,
    drawTimeSignatures: false,
    stretchLastSystemLine: true,
    colorStemsLikeNoteheads: true,
    defaultColorMusic: cssColor("--color-ink", "#0a0a0a"),
    defaultFontFamily: "Hanken Grotesk, system-ui, sans-serif",
  });
  const document_ = new DOMParser().parseFromString(xml, "application/xml");
  if (document_.getElementsByTagName("parsererror").length > 0) {
    throw new Error("El MusicXML del compás no es válido");
  }
  await osmd.load(document_);
  // Mientras cargaba, quien lo pidió pudo desmontarse.
  if (cancelled(signal)) return;
  const rules = osmd.EngravingRules;
  rules.PageTopMargin = MARGIN_UNITS;
  rules.PageTopMarginNarrow = MARGIN_UNITS;
  rules.PageBottomMargin = MARGIN_UNITS;
  rules.PageLeftMargin = MARGIN_UNITS;
  rules.PageRightMargin = MARGIN_UNITS;
  rules.SystemLeftMargin = 0;
  rules.SystemRightMargin = 0;
  osmd.zoom = 0.9;
  osmd.render();
}
