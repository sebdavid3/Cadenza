import { beforeEach, describe, expect, it, vi } from "vitest";
import { deferred } from "../../test/auth-helpers";
import {
  createPdfMaker,
  PDF_MARGIN_UNITS,
  PDF_PAGE_PT,
  PDF_SCORE_WIDTH_PX,
  renderScorePdf,
} from "./pdf";

// Ni OSMD ni jsPDF dibujan en jsdom: dobles que guardan lo que se les pide. OSMD da una página
// SVG por cada `<measure>` del MusicXML, como si cada compás llenara una hoja.
const fake = vi.hoisted(() => ({
  options: [] as Record<string, unknown>[],
  loads: [] as Document[],
  hostWidths: [] as string[],
  hostsInPage: [] as boolean[],
  cleared: 0,
  rules: [] as Record<string, number>[],
  /** Lo que OSMD dibuja en cada página, además de su SVG. */
  pageContent: "",
  title: "",
  composer: "",
  failRender: false,
  pdfs: [] as {
    options: unknown;
    pages: number;
    properties: Record<string, string>[];
    svgs: { page: number; svg: Element; options: unknown }[];
  }[],
}));

vi.mock("opensheetmusicdisplay", () => ({
  OpenSheetMusicDisplay: class {
    pages: HTMLElement[] = [];
    EngravingRules: Record<string, number> = {};
    constructor(
      readonly host: HTMLElement,
      options: Record<string, unknown>,
    ) {
      fake.options.push(options);
      fake.rules.push(this.EngravingRules);
    }
    load(document: Document) {
      fake.loads.push(document);
      return Promise.resolve({});
    }
    IsReadyToRender() {
      return true;
    }
    render() {
      if (fake.failRender) throw new Error("VexFlow");
      fake.hostWidths.push(this.host.style.width);
      fake.hostsInPage.push(this.host.isConnected);
      const measures = fake.loads.at(-1)?.getElementsByTagName("measure").length ?? 1;
      // Como el backend SVG de OSMD: un `div` por página con su SVG dentro.
      this.pages = Array.from({ length: measures }, () => {
        const page = document.createElement("div");
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.innerHTML = fake.pageContent;
        page.appendChild(svg);
        this.host.appendChild(page);
        return page;
      });
    }
    get Drawer() {
      return { Backends: this.pages.map((page) => ({ getInnerElement: () => page })) };
    }
    get Sheet() {
      return { TitleString: fake.title, ComposerString: fake.composer };
    }
    clear() {
      fake.cleared += 1;
    }
  },
}));

vi.mock("jspdf", () => ({
  jsPDF: class {
    record = {
      options: undefined as unknown,
      pages: 1,
      properties: [] as Record<string, string>[],
      svgs: [] as { page: number; svg: Element; options: unknown }[],
    };
    constructor(options: unknown) {
      this.record.options = options;
      fake.pdfs.push(this.record);
    }
    addPage() {
      this.record.pages += 1;
      return this;
    }
    setProperties(properties: Record<string, string>) {
      this.record.properties.push(properties);
      return this;
    }
    output(type: string) {
      if (type !== "blob") throw new Error(`salida ${type}`);
      return new Blob(["%PDF-1.3"], { type: "application/pdf" });
    }
  },
}));

vi.mock("svg2pdf.js", () => ({
  svg2pdf: (svg: Element, pdf: { record: (typeof fake.pdfs)[number] }, options: unknown) => {
    pdf.record.svgs.push({ page: pdf.record.pages, svg, options });
    return Promise.resolve(pdf);
  },
}));

const score = (measures: number, extra = "") =>
  `<score-partwise version="4.0">${extra}<part id="P1">${"<measure/>".repeat(measures)}</part></score-partwise>`;

beforeEach(() => {
  Object.assign(fake, {
    options: [],
    loads: [],
    hostWidths: [],
    hostsInPage: [],
    cleared: 0,
    rules: [],
    pageContent: "",
    title: "",
    composer: "",
    failRender: false,
    pdfs: [],
  });
});

describe("renderScorePdf", () => {
  it("maqueta el MusicXML en A4 con el título y el compositor, en negro y en vectores", async () => {
    const xml = score(1, "<work><work-title>Romanza</work-title></work>");

    const pdf = await renderScorePdf(xml);

    expect(pdf.type).toBe("application/pdf");
    expect(await pdf.text()).toBe("%PDF-1.3");
    expect(fake.options).toHaveLength(1);
    expect(fake.options[0]).toMatchObject({
      backend: "svg",
      autoResize: false,
      pageFormat: "A4_P",
      drawTitle: true,
      drawSubtitle: true,
      drawComposer: true,
      drawLyricist: true,
      drawMeasureNumbers: true,
      defaultColorMusic: "#000000",
    });
    // Lo que se lee es el mismo MusicXML que se descarga, tal como lo prepara la vista.
    expect(fake.loads[0]?.getElementsByTagName("work-title")[0]?.textContent).toBe("Romanza");
    // OSMD mide la página con el ancho de su contenedor: fijo, para que la notación tenga en el
    // papel el tamaño de una partitura impresa y no dependa de la ventana.
    expect(fake.hostWidths).toEqual([`${String(PDF_SCORE_WIDTH_PX)}px`]);
    expect(fake.pdfs[0]?.options).toEqual({
      orientation: "portrait",
      unit: "pt",
      format: "a4",
      compress: true,
    });
  });

  it("da una página del PDF por cada página que dibuja OSMD, cada una a página completa", async () => {
    await renderScorePdf(score(3));

    const [record] = fake.pdfs;
    if (!record) throw new Error("no se creó ningún PDF");
    expect(record.pages).toBe(3);
    expect(record.svgs.map((entry) => entry.page)).toEqual([1, 2, 3]);
    expect(new Set(record.svgs.map((entry) => entry.svg)).size).toBe(3);
    for (const entry of record.svgs) {
      expect(entry.options).toEqual({
        x: 0,
        y: 0,
        width: PDF_PAGE_PT.width,
        height: PDF_PAGE_PT.height,
      });
    }
    expect(PDF_PAGE_PT.height / PDF_PAGE_PT.width).toBeCloseTo(297 / 210, 3);
  });

  it("deja a la página márgenes de partitura impresa", async () => {
    await renderScorePdf(score(1));

    expect(fake.rules[0]).toEqual({
      PageLeftMargin: PDF_MARGIN_UNITS,
      PageRightMargin: PDF_MARGIN_UNITS,
      PageTopMargin: PDF_MARGIN_UNITS,
      PageBottomMargin: PDF_MARGIN_UNITS,
    });
    // 8 unidades de las 120 del ancho: 14 mm en los 210 del A4.
    expect((PDF_MARGIN_UNITS / (PDF_SCORE_WIDTH_PX / 10)) * 210).toBeCloseTo(14, 0);
  });

  it("lo invisible sigue invisible: los colores con alfa pasan a uno que svg2pdf.js entiende", async () => {
    // VexFlow pinta las claves y los silencios invisibles con un hexadecimal de 8 cifras de alfa
    // 0, y svg2pdf.js no lee el alfa de un hexadecimal: los pintaría de color en el PDF.
    fake.pageContent = [
      '<path class="clave" fill="#12345600" stroke="none"/>',
      '<path class="hueco" fill="#00000000" stroke="#0000"/>',
      '<path class="media" fill="#00000080" stroke="#f008"/>',
      '<path class="tinta" fill="#000000" stroke="#0a0a0a"/>',
    ].join("");

    await renderScorePdf(score(1));

    const svg = fake.pdfs[0]?.svgs[0]?.svg;
    if (!svg) throw new Error("no se convirtió ninguna página");
    const paint = (name: string) => {
      const path = svg.querySelector(`.${name}`);
      return [path?.getAttribute("fill"), path?.getAttribute("stroke")];
    };
    expect(paint("clave")).toEqual(["none", "none"]);
    expect(paint("hueco")).toEqual(["none", "none"]);
    expect(paint("media")).toEqual(["rgba(0, 0, 0, 0.502)", "rgba(255, 0, 0, 0.533)"]);
    expect(paint("tinta")).toEqual(["#000000", "#0a0a0a"]);
  });

  it("los textos dibujados que la Helvetica del PDF no puede escribir pierden el diacrítico, no la línea", async () => {
    // La Helvetica del PDF (sin incrustar) escribe WinAnsi: Latin-1 y unos pocos más (š, ž, Œ,
    // –, ’, €). Con una letra fuera, jsPDF escribía la línea letra a letra y se salía de la hoja.
    fake.pageContent = [
      '<text class="autor">Antonín Dvořák · Leoš Janáček – Œuvre ’1’ €</text>',
      '<text class="otro">Ωδή</text>',
      '<text class="nada">Ünsere Straße, ¿señor?</text>',
    ].join("");
    fake.title = "Ballade für Dvořák";
    fake.composer = "Leoš Janáček";

    await renderScorePdf(score(1));

    const svg = fake.pdfs[0]?.svgs[0]?.svg;
    if (!svg) throw new Error("no se convirtió ninguna página");
    expect(svg.querySelector(".autor")?.textContent).toBe(
      "Antonín Dvorák · Leoš Janácek – Œuvre ’1’ €",
    );
    expect(svg.querySelector(".otro")?.textContent).toBe("???");
    expect(svg.querySelector(".nada")?.textContent).toBe("Ünsere Straße, ¿señor?");
    // Las propiedades no se dibujan: jsPDF las escribe en UTF-16 y conservan el nombre.
    expect(fake.pdfs[0]?.properties).toEqual([
      { title: "Ballade für Dvořák", author: "Leoš Janáček", creator: "Cadenza" },
    ]);
  });

  it("pone el título y el compositor que lee OSMD en las propiedades del PDF", async () => {
    fake.title = "Romanza";
    fake.composer = "Clara Schumann";

    await renderScorePdf(score(1));

    expect(fake.pdfs[0]?.properties).toEqual([
      { title: "Romanza", author: "Clara Schumann", creator: "Cadenza" },
    ]);
  });

  it("sin título ni compositor, las propiedades solo dicen que lo hizo Cadenza", async () => {
    fake.title = "  ";

    await renderScorePdf(score(1));

    expect(fake.pdfs[0]?.properties).toEqual([{ creator: "Cadenza" }]);
  });

  it("dibuja fuera de la vista y lo quita de la página al terminar", async () => {
    await renderScorePdf(score(2));

    expect(fake.hostsInPage).toEqual([true]);
    expect(fake.cleared).toBe(1);
    expect(document.body.querySelector("svg")).toBeNull();
    expect(document.body.children).toHaveLength(0);
  });

  it("si OSMD no puede dibujar, falla y no deja nada en la página", async () => {
    fake.failRender = true;

    await expect(renderScorePdf(score(1))).rejects.toThrow("VexFlow");

    expect(fake.pdfs).toHaveLength(0);
    expect(document.body.children).toHaveLength(0);
  });

  it("si el MusicXML no es XML válido, falla sin crear el PDF", async () => {
    await expect(renderScorePdf("<score-partwise>")).rejects.toThrow("XML válido");

    expect(fake.options).toHaveLength(0);
    expect(document.body.children).toHaveLength(0);
  });
});

describe("createPdfMaker", () => {
  it("el mismo MusicXML da el mismo PDF sin volver a dibujarlo; otro, uno nuevo", async () => {
    const render = vi.fn((xml: string) => Promise.resolve(new Blob([xml])));
    const make = createPdfMaker(render);

    const first = await make("<a/>");
    const again = await make("<a/>");
    const other = await make("<b/>");

    expect(again).toBe(first);
    expect(other).not.toBe(first);
    expect(render.mock.calls).toEqual([["<a/>"], ["<b/>"]]);
  });

  it("mientras se prepara, pedirlo otra vez espera al mismo", async () => {
    const pending = deferred<Blob>();
    const render = vi.fn(() => pending.promise);
    const make = createPdfMaker(render);

    const first = make("<a/>");
    const second = make("<a/>");
    pending.resolve(new Blob(["%PDF"]));

    expect(await second).toBe(await first);
    expect(render).toHaveBeenCalledTimes(1);
  });

  it("un fallo no se guarda: pedirlo otra vez lo vuelve a preparar", async () => {
    const render = vi
      .fn<(xml: string) => Promise<Blob>>()
      .mockRejectedValueOnce(new Error("fallo"))
      .mockResolvedValueOnce(new Blob(["%PDF"]));
    const make = createPdfMaker(render);

    await expect(make("<a/>")).rejects.toThrow("fallo");
    await expect(make("<a/>")).resolves.toBeInstanceOf(Blob);

    expect(render).toHaveBeenCalledTimes(2);
  });
});
