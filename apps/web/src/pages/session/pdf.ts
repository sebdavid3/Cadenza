import { parseMusicXml } from "./osmd";

/** Página A4 vertical en puntos, la unidad del PDF: la misma que jsPDF da a «a4». */
export const PDF_PAGE_PT = { width: 595.28, height: 841.89 } as const;

/**
 * Ancho del contenedor en el que OSMD maqueta el PDF. OSMD mide la página con él, a 10 px por
 * unidad, y una unidad es el espacio entre dos líneas del pentagrama: 1200 px son 120 unidades en
 * los 210 mm del A4, y el pentagrama mide 7 mm de alto, como en una partitura impresa. Así el
 * tamaño de la notación en el papel no depende de la ventana.
 */
export const PDF_SCORE_WIDTH_PX = 1200;

/**
 * Márgenes de la página en unidades de OSMD: 8 de las 120 del ancho son 14 mm, como en una
 * partitura impresa. Los de OSMD (5, casi 9 mm) quedan justos para muchas impresoras.
 */
export const PDF_MARGIN_UNITS = 8;

/**
 * Letra de los textos (título, compositor, números de compás): la Helvetica del PDF, que no hay
 * que incrustar, es el grotesco más cercano al Hanken Grotesk de la vista (DESIGN.md). OSMD mide
 * los textos con ella (o con Arial, de métrica igual) y svg2pdf.js la lleva a la del PDF.
 */
const PDF_FONT = "Helvetica, Arial, sans-serif";

/**
 * Lo que la Helvetica del PDF escribe además de Latin-1: los caracteres de cp1252 entre 0x80 y
 * 0x9F, que jsPDF lleva a WinAnsi (su tabla de las fuentes estándar).
 */
const WIN_ANSI_EXTRA = new Set("ƒ–—‘’‚“”„†‡•…€‰‹›ˆ™ŒœŠšŸŽž˜");

function writable(char: string): boolean {
  const code = char.codePointAt(0) ?? 0;
  return code < 0x80 || (code >= 0xa0 && code <= 0xff) || WIN_ANSI_EXTRA.has(char);
}

/**
 * Un texto que la Helvetica del PDF puede escribir: una letra fuera de WinAnsi pierde su
 * diacrítico (ř → r, č → c) y, si ni así cabe (otro alfabeto), pasa a «?». Con una sola letra
 * fuera, jsPDF escribía la línea entera letra a letra, separadas, y se salía de la hoja.
 */
export function pdfText(text: string): string {
  return [...text]
    .map((char) => {
      if (writable(char)) return char;
      const bare = char.normalize("NFD").replace(/\p{M}/gu, "");
      return bare && [...bare].every(writable) ? bare : "?";
    })
    .join("");
}

/** Los textos de una página (título, compositor, partes, letra) en lo que el PDF puede escribir. */
function withWritableText(svg: Element) {
  for (const text of svg.querySelectorAll("text")) {
    const walker = document.createTreeWalker(text, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      node.nodeValue = pdfText(node.nodeValue ?? "");
    }
  }
}

/** Un hexadecimal con alfa: `#RGBA` o `#RRGGBBAA`. */
const ALPHA_HEX = /^#([0-9a-f]{4}|[0-9a-f]{8})$/i;

/**
 * El mismo color sin el hexadecimal con alfa, que svg2pdf.js no lee (lo pintaría opaco): sin alfa,
 * `none`; con alfa parcial, `rgba(...)`, que sí lee. Lo demás no se toca (null).
 */
function readablePaint(value: string): string | null {
  const match = ALPHA_HEX.exec(value.trim());
  const digits = match?.[1];
  if (!digits) return null;
  const hex = digits.length === 4 ? [...digits].map((digit) => digit + digit).join("") : digits;
  const [red, green, blue, alpha] = [0, 2, 4, 6].map((at) => parseInt(hex.slice(at, at + 2), 16));
  if (!alpha) return "none";
  return `rgba(${String(red)}, ${String(green)}, ${String(blue)}, ${String(Math.round((alpha / 255) * 1000) / 1000)})`;
}

/**
 * Lo invisible sigue invisible en el PDF: VexFlow pinta las claves y los silencios que no se ven
 * (los huecos de una voz, ADR-0032) con un hexadecimal de alfa 0 en `fill` y `stroke`, y
 * svg2pdf.js los pintaría de color. En `style` no hace falta: el navegador ya lo da en `rgba`.
 */
function withReadablePaint(svg: Element) {
  for (const element of [svg, ...svg.querySelectorAll("*")]) {
    for (const name of ["fill", "stroke"]) {
      const paint = readablePaint(element.getAttribute(name) ?? "");
      if (paint) element.setAttribute(name, paint);
    }
  }
}

/**
 * Lo que el PDF dice de sí mismo; lo vacío no se dice. Aquí no hace falta `pdfText`: jsPDF escribe
 * estas cadenas en UTF-16 si no caben en PDFDocEncoding.
 */
function properties(title: string, composer: string): Record<string, string> {
  return {
    ...(title.trim() ? { title: title.trim() } : {}),
    ...(composer.trim() ? { author: composer.trim() } : {}),
    creator: "Cadenza",
  };
}

/**
 * Dibuja en PDF el MusicXML de un estado (#376, ADR-0063): OSMD lo maqueta en páginas A4 con el
 * título y el compositor, fuera de la vista, y svg2pdf.js pasa cada página SVG a una del PDF, en
 * vectores. Es lo mismo que dibuja la vista, con las correcciones aplicadas, y el mismo MusicXML
 * que baja «Descargar MusicXML». OSMD, jsPDF y svg2pdf.js se cargan al pedir el PDF: la vista no
 * los paga si no se usa.
 */
export async function renderScorePdf(xml: string): Promise<Blob> {
  const sheet = parseMusicXml(xml);
  const [{ OpenSheetMusicDisplay }, { jsPDF }, { svg2pdf }] = await Promise.all([
    import("opensheetmusicdisplay"),
    import("jspdf"),
    import("svg2pdf.js"),
  ]);

  // OSMD necesita un contenedor en la página para medir: fuera de la vista, sin que se vea ni
  // se lea, y a un ancho fijo.
  const host = document.createElement("div");
  host.setAttribute("aria-hidden", "true");
  Object.assign(host.style, {
    position: "fixed",
    top: "0",
    left: "-100000px",
    width: `${String(PDF_SCORE_WIDTH_PX)}px`,
    visibility: "hidden",
    pointerEvents: "none",
  });
  document.body.appendChild(host);
  let osmd: InstanceType<typeof OpenSheetMusicDisplay> | null = null;
  try {
    osmd = new OpenSheetMusicDisplay(host, {
      backend: "svg",
      autoResize: false,
      pageFormat: "A4_P",
      drawTitle: true,
      drawSubtitle: true,
      drawComposer: true,
      drawLyricist: true,
      drawMeasureNumbers: true,
      autoGenerateMultipleRestMeasuresFromRestMeasures: false,
      defaultColorMusic: "#000000",
      defaultFontFamily: PDF_FONT,
    });
    Object.assign(osmd.EngravingRules, {
      PageLeftMargin: PDF_MARGIN_UNITS,
      PageRightMargin: PDF_MARGIN_UNITS,
      PageTopMargin: PDF_MARGIN_UNITS,
      PageBottomMargin: PDF_MARGIN_UNITS,
    });
    await osmd.load(sheet);
    if (!osmd.IsReadyToRender()) throw new Error("OSMD no pudo leer el MusicXML");
    osmd.render();
    const pages = osmd.Drawer.Backends.map((backend) =>
      backend.getInnerElement().querySelector("svg"),
    );
    if (pages.length === 0) throw new Error("OSMD no dibujó ninguna página");

    const pdf = new jsPDF({ orientation: "portrait", unit: "pt", format: "a4", compress: true });
    for (const [index, page] of pages.entries()) {
      if (!page) throw new Error("Una página de OSMD no tiene SVG");
      if (index > 0) pdf.addPage("a4", "portrait");
      withReadablePaint(page);
      withWritableText(page);
      await svg2pdf(page, pdf, { x: 0, y: 0, ...PDF_PAGE_PT });
    }
    pdf.setProperties(properties(osmd.Sheet.TitleString, osmd.Sheet.ComposerString));
    return pdf.output("blob");
  } finally {
    osmd?.clear();
    host.remove();
  }
}

/**
 * Prepara el PDF de un MusicXML y guarda el último: pedirlo otra vez con el mismo MusicXML (tras
 * el aviso de que ya está listo, o mientras se prepara) da el mismo sin volver a dibujarlo. Un
 * MusicXML distinto (otro estado, u otros datos de la sesión) da uno nuevo, y un fallo no se
 * guarda.
 */
export function createPdfMaker(render: (xml: string) => Promise<Blob> = renderScorePdf) {
  let last: { xml: string; pdf: Promise<Blob> } | null = null;
  return (xml: string): Promise<Blob> => {
    if (last?.xml === xml) return last.pdf;
    const entry = { xml, pdf: render(xml) };
    last = entry;
    entry.pdf.catch(() => {
      if (last === entry) last = null;
    });
    return entry.pdf;
  };
}
