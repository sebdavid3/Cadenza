import { beforeEach, describe, expect, it, vi } from "vitest";
import { createScoreRenderer, withInitialAttributes } from "./osmd";

// OSMD no dibuja en jsdom: un doble que cuenta las instancias, las lecturas y los dibujos, y que
// lee el `Document` sin esperas, como OSMD 2.2.1.
const fake = vi.hoisted(() => ({
  instances: 0,
  loads: [] as string[],
  renders: 0,
  zooms: [] as number[],
  failLoad: false,
  failRender: false,
}));
vi.mock("opensheetmusicdisplay", () => ({
  OpenSheetMusicDisplay: class {
    zoom = 1;
    graphic: { MeasureList: unknown[][] } | undefined;
    EngravingRules = { PageBottomMargin: 10 };
    constructor(readonly host: HTMLElement) {
      fake.instances += 1;
    }
    get GraphicSheet() {
      return this.graphic;
    }
    load(document: Document) {
      fake.loads.push(document.documentElement.textContent);
      this.zoom = 1;
      this.graphic = undefined;
      if (fake.failLoad) return Promise.reject(new Error("no es MusicXML"));
      const measures = Number(document.documentElement.getAttribute("compases") ?? "1");
      this.graphic = {
        MeasureList: Array.from({ length: measures }, () => [
          {
            PositionAndShape: {
              AbsolutePosition: { x: 1, y: 2 },
              BorderLeft: 0,
              BorderRight: 20,
            },
            staffEntries: [],
          },
        ]),
      };
      return Promise.resolve({});
    }
    IsReadyToRender() {
      return this.graphic !== undefined;
    }
    render() {
      if (fake.failRender) throw new Error("VexFlow");
      fake.renders += 1;
      fake.zooms.push(this.zoom);
      this.host.replaceChildren(document.createElementNS("http://www.w3.org/2000/svg", "svg"));
    }
    clear() {
      this.graphic = undefined;
    }
  },
}));

beforeEach(() => {
  Object.assign(fake, {
    instances: 0,
    loads: [],
    renders: 0,
    zooms: [],
    failLoad: false,
    failRender: false,
  });
});

const xml = (text: string, measures = 1) =>
  `<?xml version="1.0"?><score-partwise compases="${String(measures)}">${text}</score-partwise>`;
const STATE = { sessionId: "s1", seq: 0 };

describe("una sola instancia de OSMD por vista (#276)", () => {
  it("dibuja cada estado en la misma instancia, de forma síncrona", async () => {
    const host = document.createElement("div");
    const renderer = await createScoreRenderer(host, new AbortController().signal);

    const first = renderer.draw(xml("a", 2), STATE);
    expect(first.measuresPerStaff()).toEqual([2]);
    const second = renderer.draw(xml("b", 3), { ...STATE, seq: 1 });

    expect(fake.instances).toBe(1);
    expect(fake.loads).toEqual(["a", "b"]);
    expect(fake.renders).toBe(2);
    expect(second.measuresPerStaff()).toEqual([3]);
    // Un dibujo anterior ya no describe lo que se ve.
    expect(first.measuresPerStaff()).toEqual([]);
    expect(first.measureBox({ staff: 0, measure: 0 })).toBeNull();
    expect(host.querySelectorAll("svg")).toHaveLength(1);
  });

  it("no vuelve a leer ni a dibujar el MusicXML que ya está dibujado", async () => {
    const renderer = await createScoreRenderer(
      document.createElement("div"),
      new AbortController().signal,
    );
    const first = renderer.draw(xml("a"), STATE);
    const again = renderer.draw(xml("a"), { ...STATE, seq: 1 });

    expect(again).toBe(first);
    expect(fake.loads).toEqual(["a"]);
    expect(fake.renders).toBe(1);
  });

  it("vuelve a maquetar sin volver a leer el MusicXML, con el zoom del ancho", async () => {
    const renderer = await createScoreRenderer(
      document.createElement("div"),
      new AbortController().signal,
    );
    renderer.draw(xml("a"), STATE);
    renderer.relayout(390);

    expect(fake.loads).toEqual(["a"]);
    expect(fake.zooms).toEqual([0.75, 0.75]);
    renderer.relayout(1200);
    expect(fake.zooms.at(-1)).toBe(1);
  });

  it("si un estado no se puede leer o dibujar, no deja nada dibujado y el siguiente se dibuja", async () => {
    const host = document.createElement("div");
    const renderer = await createScoreRenderer(host, new AbortController().signal);
    renderer.draw(xml("a"), STATE);

    fake.failLoad = true;
    expect(() => renderer.draw(xml("b"), { ...STATE, seq: 1 })).toThrow();
    expect(host.children).toHaveLength(0);
    fake.failLoad = false;
    fake.failRender = true;
    expect(() => renderer.draw(xml("c"), { ...STATE, seq: 2 })).toThrow("VexFlow");
    expect(host.children).toHaveLength(0);

    fake.failRender = false;
    // Tras un fallo, el mismo MusicXML de antes se vuelve a leer: ya no está dibujado.
    renderer.draw(xml("a"), { ...STATE, seq: 3 });
    expect(fake.loads).toEqual(["a", "b", "c", "a"]);
    expect(host.querySelectorAll("svg")).toHaveLength(1);
    expect(fake.instances).toBe(1);
  });

  it("si se cancela mientras carga OSMD, no crea la instancia", async () => {
    const controller = new AbortController();
    const pending = createScoreRenderer(document.createElement("div"), controller.signal);
    controller.abort();

    await expect(pending).rejects.toThrow("Dibujo cancelado");
    expect(fake.instances).toBe(0);
  });
});

/** MusicXML de una parte con los compases dados (el contenido de cada `<measure>`). */
function score(...measures: string[]): Document {
  const body = measures
    .map((content, index) => `<measure number="${String(index + 1)}">${content}</measure>`)
    .join("");
  return new DOMParser().parseFromString(
    `<score-partwise version="4.0"><part id="P1">${body}</part></score-partwise>`,
    "application/xml",
  );
}

const NOTE = "<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration></note>";

/** Los hijos de `<attributes>` de un compás, con la quinta o el signo y la línea. */
function attributesOf(document: Document, measure: number): string[] {
  const element = document.getElementsByTagName("measure")[measure - 1];
  const attributes = element?.getElementsByTagName("attributes")[0];
  return [...(attributes?.children ?? [])].map((child) => {
    const number = child.getAttribute("number");
    const text = [...child.children].map((part) => part.textContent).join("");
    return `${child.localName}${number ? `#${number}` : ""}${text ? `:${text}` : ""}`;
  });
}

describe("armadura y clave del primer compás para OSMD (ADR-0033)", () => {
  it("escribe «sin alteraciones» en el primer compás si la primera armadura es de otro", () => {
    const document = withInitialAttributes(
      score(
        `<attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>${NOTE}`,
        `<attributes><key><fifths>2</fifths></key></attributes>${NOTE}`,
      ),
    );
    // En el orden de MusicXML: tras `divisions` y antes de `time`.
    expect(attributesOf(document, 1)).toEqual(["divisions", "key:0", "time:44", "clef:G2"]);
    expect(attributesOf(document, 2)).toEqual(["key:2"]);
  });

  it("no toca una partitura con armadura en el primer compás, ni una sin ninguna", () => {
    const withKey = score(
      `<attributes><divisions>1</divisions><key><fifths>-1</fifths></key><clef><sign>F</sign><line>4</line></clef></attributes>${NOTE}`,
      `<attributes><key><fifths>2</fifths></key></attributes>${NOTE}`,
    );
    expect(attributesOf(withInitialAttributes(withKey), 1)).toEqual([
      "divisions",
      "key:-1",
      "clef:F4",
    ]);
    const without = score(`<attributes><divisions>1</divisions></attributes>${NOTE}`, NOTE);
    expect(attributesOf(withInitialAttributes(without), 1)).toEqual(["divisions"]);
  });

  it("escribe la clave de sol en el primer compás si la primera clave es de otro", () => {
    const document = withInitialAttributes(
      score(
        `<print/><attributes><divisions>1</divisions><key><fifths>0</fifths></key></attributes>${NOTE}`,
        `<attributes><clef><sign>F</sign><line>4</line></clef></attributes>${NOTE}`,
      ),
    );
    expect(attributesOf(document, 1)).toEqual(["divisions", "key:0", "clef:G2"]);
  });

  it("crea `<attributes>` en el primer compás si no lo tiene, tras `<print>`", () => {
    const document = withInitialAttributes(
      score(`<print/>${NOTE}`, `<attributes><key><fifths>3</fifths></key></attributes>${NOTE}`),
    );
    const first = document.getElementsByTagName("measure")[0];
    expect([...(first?.children ?? [])].map((child) => child.localName)).toEqual([
      "print",
      "attributes",
      "note",
    ]);
    expect(attributesOf(document, 1)).toEqual(["key:0"]);
  });

  it("en un piano, solo la clave del pentagrama que no la tiene, con su número", () => {
    const document = withInitialAttributes(
      score(
        `<attributes><divisions>1</divisions><key><fifths>0</fifths></key><staves>2</staves><clef number="1"><sign>G</sign><line>2</line></clef></attributes>${NOTE}`,
        `<attributes><clef number="2"><sign>F</sign><line>4</line></clef></attributes>${NOTE}`,
      ),
    );
    expect(attributesOf(document, 1)).toEqual([
      "divisions",
      "key:0",
      "staves",
      "clef#1:G2",
      "clef#2:G2",
    ]);
  });
});
