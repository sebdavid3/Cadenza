import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import { routes } from "../../router";
import { engineLoader } from "./player";
import { useSelectionStore } from "./selection";
import {
  ANA,
  deferred,
  hangUntilAborted,
  jsonResponse,
  mockApi,
  resetAuth,
  signInAs,
} from "../../test/auth-helpers";
import type {
  EditEventCreate,
  EditEventRead,
  FindingRead,
  ScoreEventPayload,
  SessionDetailRead,
  TimingMapRead,
  UserRead,
} from "../../types";

// OSMD no se puede dibujar en jsdom: un doble con la misma forma de lo que la vista lee. Cada
// compás mide 20 unidades desde x = 10 + 20 × compás; sus figuras se dibujan desde 5 unidades
// después, cada 5, con la cabeza (1,2 × 1,05 unidades) centrada en su posición, a 7 unidades de
// altura; en un acorde, cada nota siguiente, una unidad más arriba.
const osmd = vi.hoisted(() => ({
  measures: 3,
  fail: false,
  cleared: 0,
  /** Instancias de OSMD creadas: la vista usa una sola (#276). */
  instances: 0,
  zooms: [] as number[],
  /** Lo que OSMD ha leído: el elemento raíz y el texto de cada MusicXML. */
  loaded: [] as string[],
  texts: [] as string[],
  /**
   * Figuras de cada compás: altura (null, silencio), duración en redondas como OSMD, las otras
   * notas si es un acorde, el número de voz de OSMD (1 si no se dice), la nota de adorno que la
   * precede, si el silencio lleva puntillo y si es invisible.
   */
  figures: null as
    | {
        pitch: string | null;
        whole: [number, number];
        chord?: string[];
        voice?: number;
        grace?: string;
        dot?: boolean;
        hidden?: boolean;
      }[][]
    | null,
}));
vi.mock("opensheetmusicdisplay", () => {
  const STEPS: Record<string, number> = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
  const SVG = "http://www.w3.org/2000/svg";
  /** Elemento SVG con la caja que daría el navegador, en píxeles de la página. */
  function svgBox(parent: Element, className: string, box: DOMRect) {
    const element = document.createElementNS(SVG, "g");
    element.setAttribute("class", className);
    element.getBoundingClientRect = () => box;
    parent.appendChild(element);
    return element;
  }
  interface Drawn {
    pitch: string | null;
    whole: [number, number];
    chord?: string[];
    voice?: number;
    /** Nota de adorno que la precede: VexFlow la anida en los modificadores de esta figura. */
    grace?: string;
    /** Silencio con puntillo: su elemento es más ancho que su glifo. */
    dot?: boolean;
    /** Silencio invisible (`print-object="no"`): OSMD lo guarda, pero no lo dibuja. */
    hidden?: boolean;
  }
  /** Una entrada de voz de OSMD con su elemento SVG, dentro de `parent`. */
  function voiceEntry(parent: Element, drawn: Drawn, x: number, unit: number, grace: boolean) {
    const box = (left: number, top: number, width: number, height: number) =>
      DOMRect.fromRect({
        x: left * unit,
        y: top * unit,
        width: width * unit,
        height: height * unit,
      });
    const group = svgBox(parent, "vf-stavenote", box(x - 0.6, 6.5, drawn.dot ? 2.5 : 1.2, 3.5));
    const pitches = drawn.pitch === null ? [null] : [drawn.pitch, ...(drawn.chord ?? [])];
    const notes = pitches.map((pitch, position) => {
      const match = pitch === null ? null : /^([A-G])(#?)(\d)$/.exec(pitch);
      const midi = match
        ? 12 * (Number(match[3]) + 1) + (STEPS[match[1] ?? "C"] ?? 0) + (match[2] ?? "").length
        : 0;
      const y = 7 - position;
      // VexFlow dibuja también el glifo de un silencio como cabeza.
      svgBox(
        group,
        "vf-notehead",
        match ? box(x - 0.6, y - 0.5, 1.2, 1.05) : box(x - 0.6, 6.5, 1.2, 3),
      );
      return {
        sourceNote: {
          isRest: () => pitch === null,
          PrintObject: !drawn.hidden,
          Length: { GetExpandedNumerator: () => drawn.whole[0], Denominator: drawn.whole[1] },
          Pitch: match
            ? { getHalfTone: () => midi - 12, FundamentalNote: STEPS[match[1] ?? "C"] }
            : undefined,
        },
        PositionAndShape: { AbsolutePosition: { x, y } },
        getSVGGElement: () => group,
      };
    });
    const entry = {
      parentVoiceEntry: { ParentVoice: { VoiceId: drawn.voice ?? 1 }, IsGrace: grace },
      notes,
    };
    return { group, entry };
  }
  function figure(svg: Element, drawn: Drawn, x: number, zoom: number) {
    const unit = 10 * zoom;
    const main = voiceEntry(svg, drawn, x, unit, false);
    if (!drawn.grace) return { graphicalVoiceEntries: [main.entry] };
    // La nota de adorno va antes en la columna y, en el SVG, dentro de la nota que adorna. Sus
    // modificadores van aquí delante de la cabeza propia, al revés que en VexFlow: así la prueba
    // depende de que solo cuenten las cabezas propias de cada nota.
    const modifiers = svgBox(main.group, "vf-modifiers", DOMRect.fromRect());
    main.group.prepend(modifiers);
    const grace = voiceEntry(
      modifiers,
      { pitch: drawn.grace, whole: [1, 4], voice: drawn.voice },
      x - 1.5,
      unit,
      true,
    );
    return { graphicalVoiceEntries: [grace.entry, main.entry] };
  }
  return {
    OpenSheetMusicDisplay: class {
      zoom = 1;
      GraphicSheet = { MeasureList: [] as unknown[][] };
      EngravingRules = { PageBottomMargin: 10 };
      ready = false;
      constructor(readonly host: HTMLElement) {
        osmd.instances += 1;
      }
      // Como OSMD 2.2.1: un `Document` se lee sin esperas y vuelve al zoom 1.
      load(document: Document) {
        osmd.loaded.push(document.documentElement.nodeName);
        osmd.texts.push(document.documentElement.textContent);
        this.zoom = 1;
        this.ready = !osmd.fail;
        if (osmd.fail) return Promise.reject(new Error("MusicXML no válido"));
        return Promise.resolve({});
      }
      IsReadyToRender() {
        return this.ready;
      }
      render() {
        osmd.zooms.push(this.zoom);
        this.host.replaceChildren();
        const svg = document.createElementNS(SVG, "svg");
        this.host.appendChild(svg);
        this.GraphicSheet.MeasureList = Array.from({ length: osmd.measures }, (_unused, index) => {
          const left = 10 + index * 20;
          const figures: Drawn[] = osmd.figures?.[index] ?? [{ pitch: "C4", whole: [3, 4] }];
          return [
            {
              PositionAndShape: {
                AbsolutePosition: { x: left, y: 5 },
                BorderLeft: 0,
                BorderRight: 20,
                BorderTop: 0,
                BorderBottom: 4,
              },
              staffEntries: figures.map((drawn, position) =>
                figure(svg, drawn, left + 5 + position * 5, this.zoom),
              ),
            },
          ];
        });
      }
      clear() {
        osmd.cleared += 1;
        this.ready = false;
      }
    },
  };
});

// Tone.js no suena en jsdom: un motor con reloj falso que avisa de cada compás al avanzar.
const audio = vi.hoisted(() => {
  interface Span {
    number: number;
    start: number;
  }
  interface Handlers {
    onMeasure(measure: number): void;
    onEnd(): void;
  }
  class FakeEngine {
    position = 0;
    playing = false;
    disposed = false;
    tempos: number[] = [];
    constructor(
      public playback: { notes: unknown[]; measures: Span[]; totalBeats: number },
      readonly tempo: number,
      private readonly handlers: Handlers,
    ) {}
    play() {
      if (audio.failPlay) return Promise.reject(new Error("sin audio"));
      this.playing = true;
      return Promise.resolve();
    }
    pause() {
      this.playing = false;
    }
    stop() {
      this.playing = false;
      this.position = 0;
    }
    setTempo(bpm: number) {
      this.tempos.push(bpm);
    }
    /** Otra partitura desde el punto en que está, sin parar (#276). */
    update(playback: FakeEngine["playback"]) {
      this.updates.push(playback);
      this.playback = playback;
    }
    updates: FakeEngine["playback"][] = [];
    dispose() {
      this.disposed = true;
      this.playing = false;
    }
    /** Avanza el reloj `beats` negras y avisa de los compases que empiezan en ese tramo. */
    advance(beats: number) {
      if (!this.playing) return;
      const from = this.position;
      this.position += beats;
      for (const measure of this.playback.measures) {
        if (measure.start >= from && measure.start < this.position) {
          this.handlers.onMeasure(measure.number);
        }
      }
      if (this.position >= this.playback.totalBeats) {
        this.stop();
        this.handlers.onEnd();
      }
    }
  }
  const audio = {
    failPlay: false,
    engines: [] as FakeEngine[],
    create: (playback: FakeEngine["playback"], tempo: number, handlers: Handlers) => {
      const engine = new FakeEngine(playback, tempo, handlers);
      audio.engines.push(engine);
      return engine;
    },
  };
  return audio;
});
vi.mock("./toneEngine", () => ({ createToneEngine: audio.create }));

const LUIS: UserRead = { ...ANA, id: "0b7f6c1e-1111-4bbb-8ccc-000000000002", username: "luis" };
const INVESTIGADORA: UserRead = {
  ...ANA,
  id: "0b7f6c1e-2222-4bbb-8ccc-000000000003",
  username: "inv",
  role: "investigador",
};
const ID = "3e951fef-8a58-489e-abc9-68cfc3cd405b";

function measure(number: number) {
  return {
    number,
    events: [
      {
        kind: "note",
        voice: 0,
        pitch: "C4",
        duration_beats: "3",
        tie: null,
        is_chord: false,
        bbox: null,
        confidence: null,
        ir_handle: null,
      },
    ],
    time_signature: { beats: 3, beat_type: 4 },
  };
}

function detail(changes: Partial<SessionDetailRead> = {}): SessionDetailRead {
  const score = {
    parts: [{ id: "part-0", staves: [{ id: "part-0-staff-0", measures: [1, 2, 3].map(measure) }] }],
  };
  return {
    session_id: ID,
    document_id: "homr-1",
    omr_engine: "homr",
    document: {} as SessionDetailRead["document"],
    findings: [],
    edits: [],
    current_score: score as SessionDetailRead["current_score"],
    current_seq: 0,
    anchor_index: null,
    image_artifact: "img",
    status: "transcribed",
    condition: "assisted",
    test_score_id: "estudio-7",
    owner_id: ANA.id,
    ...changes,
  };
}

function finding(id: number, measureNumber: number, changes: Partial<FindingRead> = {}) {
  return {
    id,
    rule_id: "measure.balance",
    severity: "error",
    message: `El compás ${String(measureNumber)} suma 4 negras y su métrica 3/4 exige 3.`,
    suggested_fix: null,
    anchor: {
      part: 0,
      staff: 0,
      measure: measureNumber,
      voice: 0,
      event_index: 0,
      staff_id: "part-0-staff-0",
      bbox: null,
      confidence: null,
    },
    at_seq: 0,
    status: "active",
    dismissed_at: null,
    dismissed_by: null,
    dismissal_reason: null,
    ...changes,
  } satisfies FindingRead;
}

function timingMap(numbers = [1, 2, 3], kind = "note"): TimingMapRead {
  return {
    session_id: ID,
    total_beats: String(numbers.length * 3),
    measure_offsets: Object.fromEntries(numbers.map((n, i) => [String(n), String(i * 3)])),
    events: numbers.map((n, i) => ({
      anchor: {
        part: 0,
        staff: 0,
        measure: n,
        voice: 0,
        event_index: 0,
        staff_id: "part-0-staff-0",
        bbox: null,
        confidence: null,
      },
      kind,
      measure_number: n,
      voice: 0,
      offset_beats: String(i * 3),
      duration_beats: "3",
      measure_offset_beats: "0",
    })),
  };
}

const XML = "<score-partwise>…</score-partwise>";
/** El MusicXML de un estado: el del estado 0 es `XML`, y cada estado posterior tiene el suyo. */
const xmlOf = (state: SessionDetailRead) =>
  state.current_seq ? `<score-partwise>estado ${String(state.current_seq)}</score-partwise>` : XML;
const png = () =>
  new Response(new Uint8Array([1, 2]), { headers: { "Content-Type": "image/png" } });

function api(
  options: {
    detail?: SessionDetailRead;
    findings?: FindingRead[] | (() => Response);
    exportStatus?: number;
    status?: number;
    timing?: (init: RequestInit | undefined) => Response | Promise<Response>;
  } = {},
) {
  const findings = options.findings;
  return mockApi({
    [`GET /sessions/${ID}`]: () =>
      options.status
        ? jsonResponse({ detail: "Sesión no encontrada" }, options.status)
        : jsonResponse(options.detail ?? detail()),
    [`GET /sessions/${ID}/findings`]: () =>
      typeof findings === "function" ? findings() : jsonResponse(findings ?? []),
    [`GET /sessions/${ID}/export`]: () =>
      options.exportStatus
        ? jsonResponse({ detail: "fallo" }, options.exportStatus)
        : new Response(XML, { headers: { "Content-Type": "application/vnd.recordare.musicxml" } }),
    [`GET /sessions/${ID}/image`]: png,
    [`GET /sessions/${ID}/timing`]: options.timing ?? (() => jsonResponse(timingMap())),
    "GET /users": () => jsonResponse([ANA, LUIS, INVESTIGADORA]),
  });
}

function renderPage(user: UserRead = ANA) {
  signInAs(user);
  const router = createMemoryRouter(routes, { initialEntries: [`/sesiones/${ID}`] });
  render(<RouterProvider router={router} />);
  return router;
}

const xml = () =>
  new Response(XML, { headers: { "Content-Type": "application/vnd.recordare.musicxml+xml" } });

/** La API de una sesión sin hallazgos con otra respuesta para `/export`. */
function withExport(route: (init: RequestInit | undefined) => Response | Promise<Response>) {
  return mockApi({
    [`GET /sessions/${ID}`]: () => jsonResponse(detail()),
    [`GET /sessions/${ID}/findings`]: () => jsonResponse([]),
    [`GET /sessions/${ID}/export`]: route,
    [`GET /sessions/${ID}/image`]: png,
    [`GET /sessions/${ID}/timing`]: () => jsonResponse(timingMap()),
  });
}

/** Nombres de los archivos que la vista descarga (jsdom no navega a una URL de Blob). */
function captureDownloads() {
  const names: string[] = [];
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    names.push(this.download);
  });
  return { names };
}

/** Blobs de MusicXML entregados a `URL.createObjectURL` (la imagen original también pasa). */
function musicXmlBlobs() {
  return createObjectURL.mock.calls
    .map(([value]) => value)
    .filter(
      (value): value is Blob =>
        value instanceof Blob && value.type === "application/vnd.recordare.musicxml+xml",
    );
}

let createObjectURL: MockInstance<typeof URL.createObjectURL>;
let revokeObjectURL: MockInstance<typeof URL.revokeObjectURL>;
const scrollIntoView = vi.fn();

beforeEach(() => {
  resetAuth();
  Object.assign(osmd, {
    measures: 3,
    fail: false,
    cleared: 0,
    instances: 0,
    zooms: [],
    loaded: [],
    texts: [],
    figures: null,
  });
  useSelectionStore.getState().clear();
  audio.engines = [];
  audio.failPlay = false;
  createObjectURL = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:original");
  revokeObjectURL = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
  scrollIntoView.mockClear();
  Element.prototype.scrollIntoView = scrollIntoView;
  vi.stubGlobal("matchMedia", () => ({ matches: false }));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("vista de una sesión", () => {
  it("dibuja la partitura, marca los compases con posibles errores y los lista", async () => {
    const { calls } = api({ findings: [finding(1, 2), finding(2, 2, { rule_id: "pitch.range" })] });
    renderPage();

    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Sesión 3e951fef");
    const list = await screen.findByRole("list");
    const item = within(list).getByRole("button", { name: /^compás 2/i });
    expect(item).toHaveTextContent("Duración del compás");
    expect(item).toHaveTextContent("Altura fuera de registro");
    expect(item).toHaveTextContent("El compás 2 suma 4 negras y su métrica 3/4 exige 3.");
    expect(screen.getByText(/no garantiza que esté bien transcrito/i)).toBeVisible();

    // Una sola marca para el compás 2 (dos hallazgos), en la caja del segundo compás de OSMD.
    await waitFor(() => {
      expect(document.querySelectorAll(".notation__mark")).toHaveLength(1);
    });
    const mark = document.querySelector<HTMLElement>(".notation__mark");
    // Segundo compás de OSMD: x = 30 unidades; en jsdom el ancho es 0 y el zoom, el de móvil.
    expect(mark?.style.left).toBe("225px");
    expect(mark).toHaveTextContent("Compás 2");
    expect(screen.getByRole("application", { name: /posibles errores: 2/i })).toBeInTheDocument();
    // OSMD recibe el MusicXML ya analizado, no una cadena que podría tomar por una URL.
    expect(osmd.loaded).toEqual(["score-partwise"]);

    // Hallazgos de la última validación, también los descartados; nada del estudio.
    const findingsCall = calls.find((call) => call.key === `GET /sessions/${ID}/findings`);
    expect(findingsCall?.url.searchParams.get("latest_only")).toBe("true");
    expect(findingsCall?.url.searchParams.get("include_dismissed")).toBe("true");
    expect(screen.queryByText(/assisted|estudio-7/i)).toBeNull();
    expect(screen.queryByText(/^error$/i)).toBeNull();
  });

  it("muestra «Qué revisar» bajo el mensaje de cada posible error (ADR-0040 §2)", async () => {
    api({
      findings: [
        finding(1, 2, {
          message:
            "Al compás 2 le falta una corchea para completar el 3/4: las figuras se acaban antes de la segunda corchea del tiempo 3.",
          suggested_fix:
            "Revisa las figuras del compás: puede que alguna sea más larga de lo que se leyó, o que falte una nota o un silencio de corchea.",
        }),
        finding(2, 3, { rule_id: "accidental.repeated", suggested_fix: null }),
        finding(3, 1, { rule_id: "learned.accidental", suggested_fix: "Cambiar Si por Si♭." }),
      ],
    });
    renderPage();

    const list = await screen.findByRole("list");
    const second = within(list).getByRole("button", { name: /^compás 2/i });
    const fix = within(second).getByText(/^Qué revisar:/);
    expect(fix).toHaveTextContent(
      "Qué revisar: Revisa las figuras del compás: puede que alguna sea más larga de lo que se leyó, o que falte una nota o un silencio de corchea.",
    );
    // Bajo el mensaje, no antes.
    const message = within(second).getByText(/^Al compás 2 le falta una corchea/);
    expect(message.compareDocumentPosition(fix) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // Sin «Qué revisar», no se dice nada; el título es el del catálogo.
    const third = within(list).getByRole("button", { name: /^compás 3/i });
    expect(third).toHaveTextContent("Alteración repetida");
    expect(within(third).queryByText(/Qué revisar/)).toBeNull();
    // En los de la capa, `suggested_fix` es la edición propuesta, no qué revisar (#258).
    const first = within(list).getByRole("button", { name: /^compás 1/i });
    expect(first).toHaveTextContent("Alteración dudosa");
    expect(within(first).queryByText(/Qué revisar/)).toBeNull();
  });

  it("en una sesión no asistida no muestra nada del validador (ADR-0040 §13.2)", async () => {
    // Aunque la API devolviera posibles errores, la vista ni los pide.
    const { calls } = api({
      detail: detail({
        condition: "unassisted",
        edits: [
          {
            id: "edit-1",
            session_id: ID,
            seq: 1,
            op: "SetPitch",
            author: "ana",
            anchor: finding(1, 2).anchor,
            before: { pitch: "C4" },
            after: { pitch: "D4" },
            created_at: "2026-10-24T10:00:00Z",
          },
        ],
        current_seq: 1,
      }),
      findings: [finding(1, 2)],
    });
    renderPage();

    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Sesión 3e951fef");
    expect(await screen.findByAltText("Imagen original de la partitura")).toBeInTheDocument();
    await waitFor(() => {
      expect(osmd.loaded.length).toBeGreaterThan(0);
    });
    // Quedan la partitura, la imagen y el editor.
    expect(screen.getByRole("application", { name: /^partitura transcrita\./i })).toBeVisible();
    expect(screen.getByRole("button", { name: /^deshacer/i })).toBeInTheDocument();
    // Ni el panel, ni las marcas, ni «Revalidar», ni ningún aviso sobre la validación.
    expect(screen.queryByRole("heading", { name: /posibles errores/i })).toBeNull();
    expect(screen.queryByText(/validador|validación|posibles errores|tramados/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /revalidar/i })).toBeNull();
    expect(document.querySelector(".notation__mark")).toBeNull();
    expect(calls.some((call) => call.key === `GET /sessions/${ID}/findings`)).toBe(false);
  });

  it("en una sesión no asistida, si no se dibuja la partitura, no habla de posibles errores", async () => {
    osmd.fail = true;
    api({ detail: detail({ condition: "unassisted" }) });
    renderPage();

    expect(await screen.findByText("No se pudo dibujar la partitura.")).toBeVisible();
    expect(screen.getByText(/la imagen original sigue disponible/i)).toBeVisible();
    expect(screen.queryByText(/posibles errores/i)).toBeNull();
  });

  it("al elegir un compás de la lista lo resalta en la partitura", async () => {
    api({ findings: [finding(1, 1), finding(2, 3)] });
    renderPage();
    const button = await screen.findByRole("button", { name: /^compás 3/i });
    await waitFor(() => {
      expect(document.querySelectorAll(".notation__mark")).toHaveLength(2);
    });

    await userEvent.click(button);

    expect(button).toHaveAttribute("aria-pressed", "true");
    const selected = document.querySelector('.notation__mark[data-selected="true"]');
    expect(selected).toHaveTextContent("Compás 3");
    expect(scrollIntoView).toHaveBeenCalled();

    await userEvent.click(button);
    expect(button).toHaveAttribute("aria-pressed", "false");
  });

  it("dice que no hay posibles errores sin prometer que la transcripción sea correcta", async () => {
    api();
    renderPage();

    expect(
      await screen.findByText("El validador no señaló ningún compás en su última validación."),
    ).toBeVisible();
    expect(screen.queryByText(/puede que el resultado ya no esté al día/i)).toBeNull();
    expect(screen.getByText(/no lo detecta todo/i)).toBeVisible();
    expect(document.querySelector(".notation__mark")).toBeNull();
  });

  it("lista aparte los descartados y no los marca", async () => {
    api({
      findings: [
        finding(1, 1),
        finding(2, 3, {
          status: "dismissed",
          dismissed_by: "ana",
          dismissal_reason: "Así está en el original",
        }),
      ],
    });
    renderPage();

    const summary = await screen.findByText(/descartados como falso positivo · 1/i);
    await userEvent.click(summary);
    expect(screen.getByText("Motivo: Así está en el original")).toBeVisible();
    await waitFor(() => {
      expect(document.querySelectorAll(".notation__mark")).toHaveLength(1);
    });
    expect(document.querySelector(".notation__mark")).toHaveTextContent("Compás 1");
  });

  it("avisa si los posibles errores son de un estado anterior al actual", async () => {
    api({ detail: detail({ current_seq: 3 }), findings: [finding(1, 2, { at_seq: 1 })] });
    renderPage();

    expect(
      await screen.findByText(/tal como estaba tras 1 edición; después se editó/i),
    ).toBeVisible();
  });

  it("no marca nada si OSMD dibuja otros compases que el ScoreIR, y lo dice", async () => {
    osmd.measures = 2;
    api({ findings: [finding(1, 2)] });
    renderPage();

    expect(await screen.findByText(/no se pudieron situar los posibles errores/i)).toBeVisible();
    expect(document.querySelector(".notation__mark")).toBeNull();
    expect(screen.getByText("Compás 2")).toBeVisible();
  });

  it("si la partitura no se puede dibujar, la imagen y la lista siguen disponibles", async () => {
    osmd.fail = true;
    api({ findings: [finding(1, 2)] });
    renderPage();

    expect(await screen.findByText("No se pudo dibujar la partitura.")).toBeVisible();
    expect(screen.getByRole("button", { name: /^compás 2/i })).toBeVisible();
    expect(await screen.findByAltText("Imagen original de la partitura")).toBeInTheDocument();
  });

  it("si falla la exportación lo dice y permite reintentar", async () => {
    api({ exportStatus: 500 });
    renderPage();

    expect(await screen.findByText("No se pudo dibujar la partitura.")).toBeVisible();
    expect(screen.getByText(/el servidor tuvo un problema/i)).toBeVisible();
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeVisible();
  });

  it("lista y cuenta un posible error cuyo compás ya no está en la partitura", async () => {
    api({ findings: [finding(1, 2), finding(2, 9)] });
    renderPage();

    expect(await screen.findByText(/ese compás ya no está en la partitura/i)).toBeVisible();
    expect(document.querySelector(".findings__count")).toHaveTextContent("2");
    await waitFor(() => {
      expect(document.querySelectorAll(".notation__mark")).toHaveLength(1);
    });
  });

  it("sin posibles errores pero con ediciones, avisa de que puede no estar al día", async () => {
    const edit: EditEventRead = {
      id: "edit-1",
      session_id: ID,
      seq: 1,
      op: "SetPitch",
      author: "ana",
      anchor: finding(1, 2).anchor,
      before: { pitch: "C4" },
      after: { pitch: "D4" },
      created_at: "2026-10-24T10:00:00Z",
    };
    api({ detail: detail({ current_seq: 1, edits: [edit] }) });
    renderPage();

    expect(await screen.findByText(/puede que el resultado ya no esté al día/i)).toBeVisible();
  });

  it("si solo quedan descartados, no dice que el validador no señaló nada", async () => {
    api({ findings: [finding(1, 2, { status: "dismissed" })] });
    renderPage();

    expect(await screen.findByText(/se descartaron como falso positivo/i)).toBeVisible();
    expect(screen.queryByText(/no señaló ningún compás/i)).toBeNull();
  });

  it("si fallan los posibles errores lo dice y permite reintentar", async () => {
    let fail = true;
    api({
      findings: () =>
        fail ? jsonResponse({ detail: "fallo" }, 500) : jsonResponse([finding(1, 1)]),
    });
    renderPage();

    expect(await screen.findByText(/no se pudieron cargar los posibles errores/i)).toBeVisible();
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("button", { name: /^compás 1/i })).toBeVisible();
  });

  it("si falla el detalle de la sesión lo dice sin confundirlo con un 404", async () => {
    api({ status: 503 });
    renderPage();

    expect(
      await screen.findByRole("heading", { name: "No se pudo cargar la sesión" }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeVisible();
  });

  it("solo es una imagen con nombre cuando la partitura está dibujada", async () => {
    osmd.fail = true;
    api({ findings: [finding(1, 2)] });
    renderPage();

    expect(await screen.findByText("No se pudo dibujar la partitura.")).toBeVisible();
    expect(screen.queryByRole("img", { name: /partitura transcrita/i })).toBeNull();
  });

  it("si no se pueden situar las marcas, la lista no ofrece resaltarlas", async () => {
    osmd.measures = 2;
    api({ findings: [finding(1, 2)] });
    renderPage();

    expect(await screen.findByText(/no se pudieron situar/i)).toBeVisible();
    expect(screen.queryByRole("button", { name: /^compás 2/i })).toBeNull();
    expect(screen.getByText("Compás 2")).toBeVisible();
  });

  it("vuelve a maquetar la partitura al cambiar el ancho", async () => {
    let width = 1200;
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockImplementation(() => width);
    const observers: (() => void)[] = [];
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(callback: () => void) {
          observers.push(callback);
        }
        observe() {
          // El doble solo guarda el aviso; la prueba lo dispara a mano.
        }
        disconnect() {
          // Nada que soltar.
        }
      },
    );
    api({ findings: [finding(1, 2)] });
    renderPage();
    await waitFor(() => {
      expect(document.querySelector(".notation__mark")).not.toBeNull();
    });
    expect(osmd.zooms).toEqual([1]);
    expect(document.querySelector<HTMLElement>(".notation__mark")?.style.left).toBe("300px");

    width = 390;
    for (const notify of observers) notify();

    await waitFor(() => {
      expect(osmd.zooms).toEqual([1, 0.75]);
    });
    // La marca se recoloca con el zoom nuevo: x = 30 unidades × 10 px × 0,75.
    await waitFor(() => {
      expect(document.querySelector<HTMLElement>(".notation__mark")?.style.left).toBe("225px");
    });
  });

  it("responde igual a una sesión inexistente que a una ajena", async () => {
    // La API responde 404 a las dos (ADR-0012): la vista no puede ni debe distinguirlas.
    api({ status: 404 });
    const router = renderPage(LUIS);

    expect(await screen.findByRole("heading", { name: "Sesión no encontrada" })).toBeVisible();
    const { calls } = mockApi({ "GET /sessions/otra": () => jsonResponse({ detail: "no" }, 404) });
    await router.navigate("/sesiones/otra");
    await waitFor(() => {
      expect(calls.map((call) => call.key)).toContain("GET /sessions/otra");
    });
    expect(await screen.findByRole("heading", { name: "Sesión no encontrada" })).toBeVisible();
    expect(screen.getByText(/no existe o no tienes acceso/i)).toBeVisible();
    expect(screen.getByRole("link", { name: /sesiones/i })).toHaveAttribute(
      "href",
      "/transcripcion",
    );
  });

  it("muestra al investigador de quién es una sesión ajena", async () => {
    api({ detail: detail({ owner_id: LUIS.id }) });
    renderPage(INVESTIGADORA);

    const owner = await screen.findByText("luis");
    expect(owner.closest("div")).toHaveTextContent("Propietario");
  });

  it("descarga el MusicXML que ya tiene, con un nombre determinista y sin pedirlo otra vez", async () => {
    const { calls } = api();
    const saved = captureDownloads();
    renderPage();

    const button = await screen.findByRole("button", { name: "Descargar MusicXML" });
    await waitFor(() => {
      expect(button).not.toHaveAttribute("aria-disabled", "true");
    });
    await userEvent.click(button);

    expect(saved.names).toEqual(["cadenza-3e951fef.musicxml"]);
    const blob = musicXmlBlobs()[0];
    expect(blob?.type).toBe("application/vnd.recordare.musicxml+xml");
    expect(await blob?.text()).toBe(XML);
    expect(calls.filter((call) => call.key === `GET /sessions/${ID}/export`)).toHaveLength(1);
  });

  it("mientras prepara el MusicXML no descarga y lo dice", async () => {
    withExport(hangUntilAborted);
    const saved = captureDownloads();
    renderPage();

    const button = await screen.findByRole("button", { name: "Descargar MusicXML" });
    expect(button).toHaveAttribute("aria-disabled", "true");
    expect(button).toHaveAccessibleDescription("Preparando el MusicXML…");
    await userEvent.click(button);
    expect(saved.names).toEqual([]);
  });

  it("si la exportación falla lo dice y, al pulsar, la vuelve a pedir y descarga", async () => {
    let fail = true;
    const { calls } = withExport(() => (fail ? jsonResponse({ detail: "fallo" }, 500) : xml()));
    const saved = captureDownloads();
    renderPage();

    const button = await screen.findByRole("button", { name: "Descargar MusicXML" });
    await waitFor(() => {
      expect(button).toHaveAccessibleDescription(/no se pudo preparar el musicxml/i);
    });
    expect(button).not.toHaveAttribute("aria-disabled", "true");

    fail = false;
    await userEvent.click(button);

    await waitFor(() => {
      expect(saved.names).toEqual(["cadenza-3e951fef.musicxml"]);
    });
    const blob = musicXmlBlobs()[0];
    expect(blob?.type).toBe("application/vnd.recordare.musicxml+xml");
    expect(await blob?.text()).toBe(XML);
    expect(calls.filter((call) => call.key === `GET /sessions/${ID}/export`)).toHaveLength(2);
    expect(screen.queryByText(/no se pudo preparar el musicxml/i)).toBeNull();
  });

  it("si el reintento vuelve a fallar no descarga y lo sigue diciendo", async () => {
    withExport(() => jsonResponse({ detail: "fallo" }, 500));
    const saved = captureDownloads();
    renderPage();
    const button = await screen.findByRole("button", { name: "Descargar MusicXML" });
    await waitFor(() => {
      expect(button).toHaveAccessibleDescription(/no se pudo preparar el musicxml/i);
    });

    await userEvent.click(button);

    await waitFor(() => {
      expect(button).toHaveAccessibleDescription(/no se pudo preparar el musicxml/i);
    });
    expect(saved.names).toEqual([]);
  });

  it("si el reintento llega mucho después del clic, no descarga por sorpresa", async () => {
    let clock = 0;
    vi.spyOn(performance, "now").mockImplementation(() => clock);
    let fail = true;
    withExport(() => {
      if (fail) return jsonResponse({ detail: "fallo" }, 500);
      clock = 10_000;
      return xml();
    });
    const saved = captureDownloads();
    renderPage();
    const button = await screen.findByRole("button", { name: "Descargar MusicXML" });
    await waitFor(() => {
      expect(button).toHaveAccessibleDescription(/no se pudo preparar el musicxml/i);
    });

    fail = false;
    await userEvent.click(button);

    // El archivo ya está: el botón queda listo, pero no se descargó solo.
    await waitFor(() => {
      expect(button).not.toHaveAccessibleDescription(/no se pudo preparar/i);
    });
    expect(saved.names).toEqual([]);
    await userEvent.click(button);
    expect(saved.names).toEqual(["cadenza-3e951fef.musicxml"]);
  });

  it("si se sale de la vista durante el reintento, no descarga al llegar", async () => {
    let fail = true;
    const late = deferred<Response>();
    withExport(() => (fail ? jsonResponse({ detail: "fallo" }, 500) : late.promise));
    const saved = captureDownloads();
    const router = renderPage();
    const button = await screen.findByRole("button", { name: "Descargar MusicXML" });
    await waitFor(() => {
      expect(button).toHaveAccessibleDescription(/no se pudo preparar el musicxml/i);
    });

    fail = false;
    await userEvent.click(button);
    await router.navigate("/transcripcion");
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Descargar MusicXML" })).toBeNull();
    });
    // La respuesta llega cuando la vista ya no está.
    late.resolve(xml());

    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(saved.names).toEqual([]);
  });

  it("muestra la imagen original desde un Blob y revoca su URL al salir", async () => {
    api();
    const router = renderPage();

    const image = await screen.findByAltText("Imagen original de la partitura");
    await waitFor(() => {
      expect(image).toHaveAttribute("src", "blob:original");
    });
    expect(revokeObjectURL).not.toHaveBeenCalled();

    await router.navigate("/transcripcion");

    await waitFor(() => {
      expect(revokeObjectURL).toHaveBeenCalledWith("blob:original");
    });
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(osmd.cleared).toBeGreaterThan(0);
  });
});

describe("reproducción de la partitura", () => {
  const engine = () => {
    const last = audio.engines.at(-1);
    if (!last) throw new Error("no se creó el motor de audio");
    return last;
  };
  const playButton = async () => {
    const button = await screen.findByRole("button", { name: "Reproducir" });
    await waitFor(() => {
      expect(button).not.toHaveAttribute("aria-disabled", "true");
    });
    return button;
  };
  const playhead = () => document.querySelector<HTMLElement>(".notation__playhead");

  it("reproduce con el compás que suena resaltado y anuncia cada cambio de estado", async () => {
    api();
    renderPage();
    await userEvent.click(await playButton());

    expect(screen.getByText("Reproduciendo.")).toBeInTheDocument();
    expect(engine().tempo).toBe(120);
    expect(engine().playback.notes).toHaveLength(3);
    act(() => {
      engine().advance(0.5);
    });
    // Compás 1 en la caja del primer compás de OSMD: x = 10 unidades × 10 px × 0,75.
    expect(playhead()?.style.left).toBe("75px");
    expect(screen.getByText("Compás 1")).toBeVisible();

    act(() => {
      engine().advance(3);
    });
    expect(playhead()?.style.left).toBe("225px");
    expect(screen.getByText("Compás 2")).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "Pausa" }));
    expect(screen.getByText("En pausa.")).toBeInTheDocument();
    expect(screen.getByText("En pausa · Compás 2")).toBeVisible();
    expect(playhead()?.style.left).toBe("225px");

    await userEvent.click(screen.getByRole("button", { name: "Reproducir" }));
    expect(audio.engines).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Detener" }));
    expect(screen.getByText("Detenido.")).toBeInTheDocument();
    expect(playhead()).toBeNull();
    expect(engine().position).toBe(0);
  });

  it("se maneja con el teclado y el foco sigue en el mismo botón", async () => {
    api();
    renderPage();
    const button = await playButton();

    button.focus();
    await userEvent.keyboard("{Enter}");
    expect(document.activeElement).toBe(button);
    expect(button).toHaveTextContent("Pausa");
    await userEvent.keyboard(" ");
    expect(button).toHaveTextContent("Reproducir");
    expect(screen.getByText("En pausa.")).toBeInTheDocument();
  });

  it("al terminar la partitura se detiene y lo dice", async () => {
    api();
    renderPage();
    await userEvent.click(await playButton());

    act(() => {
      engine().advance(9);
    });

    expect(screen.getByText("Fin de la partitura.")).toBeInTheDocument();
    expect(playhead()).toBeNull();
    expect(screen.getByRole("button", { name: "Reproducir" })).toBeVisible();
  });

  it("cambia el tempo, también mientras suena, sin salir del rango", async () => {
    api();
    renderPage();
    await playButton();
    expect(screen.getByText("3 compases · 0:05")).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "Subir el tempo" }));
    expect(screen.getByText(/^130/)).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Reproducir" }));
    expect(engine().tempo).toBe(130);
    await userEvent.click(screen.getByRole("button", { name: "Bajar el tempo" }));
    expect(engine().tempos).toEqual([120]);
  });

  it("se detiene al salir de la vista", async () => {
    api();
    const router = renderPage();
    await userEvent.click(await playButton());
    const first = engine();

    await router.navigate("/transcripcion");

    await waitFor(() => {
      expect(first.disposed).toBe(true);
    });
  });

  it("se detiene al cambiar de sesión y la nueva no hereda el compás", async () => {
    api();
    const router = renderPage();
    await userEvent.click(await playButton());
    const first = engine();
    act(() => {
      first.advance(0.5);
    });
    expect(playhead()).not.toBeNull();

    const OTRA = "9c1d2e3f-4a5b-4c6d-8e7f-001122334455";
    mockApi({
      [`GET /sessions/${OTRA}`]: () => jsonResponse(detail({ session_id: OTRA })),
      [`GET /sessions/${OTRA}/findings`]: () => jsonResponse([]),
      [`GET /sessions/${OTRA}/export`]: () => new Response(XML),
      [`GET /sessions/${OTRA}/image`]: png,
      [`GET /sessions/${OTRA}/timing`]: () => jsonResponse(timingMap()),
    });
    await router.navigate(`/sesiones/${OTRA}`);

    expect(
      await screen.findByRole("heading", { level: 1, name: /sesión 9c1d2e3f/i }),
    ).toBeVisible();
    await waitFor(() => {
      expect(first.disposed).toBe(true);
    });
    await playButton();
    expect(screen.getByText("3 compases · 0:05")).toBeVisible();
    expect(playhead()).toBeNull();
  });

  it("si no llega el audio (el trozo de Tone.js), lo dice y permite reintentar", async () => {
    vi.spyOn(engineLoader, "load").mockRejectedValueOnce(new Error("404"));
    api();
    renderPage();

    expect(
      await screen.findByText("No se pudo cargar el audio.", { selector: "p.label" }),
    ).toBeVisible();
    const play = screen.getByRole("button", { name: "Reproducir" });
    expect(play).toHaveAttribute("aria-disabled", "true");

    await userEvent.click(screen.getByRole("button", { name: "Reintentar el audio" }));

    // El foco pasa a «Reproducir», que sigue ahí cuando el reintento desaparece.
    expect(document.activeElement).toBe(play);
    await waitFor(() => {
      expect(play).not.toHaveAttribute("aria-disabled", "true");
    });
    await userEvent.click(play);
    expect(engine().playing).toBe(true);
  });

  it("no devuelve a la partitura a quien se fue a mirar la imagen o la lista", async () => {
    api();
    renderPage();
    await userEvent.click(await playButton());
    act(() => {
      engine().advance(0.5);
    });
    expect(scrollIntoView).toHaveBeenCalledTimes(1);

    // La persona baja: la partitura (y el compás que sonaba) queda por encima de la ventana.
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(
      DOMRect.fromRect({ x: 0, y: -5000, width: 300, height: 200 }),
    );
    act(() => {
      engine().advance(3);
    });

    expect(screen.getByText("Compás 2")).toBeVisible();
    expect(scrollIntoView).toHaveBeenCalledTimes(1);
  });

  it("se pausa si la página deja de verse", async () => {
    api();
    renderPage();
    await userEvent.click(await playButton());

    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });

    expect(engine().playing).toBe(false);
    expect(screen.getByText("En pausa.")).toBeInTheDocument();
  });

  it("con movimiento reducido trae el compás a la vista sin desplazamiento suave", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({ matches: query.includes("reduce") }));
    api();
    renderPage();
    await userEvent.click(await playButton());
    scrollIntoView.mockClear();

    act(() => {
      engine().advance(0.5);
    });

    expect(scrollIntoView).toHaveBeenCalledWith(expect.objectContaining({ behavior: "auto" }));
  });

  it("mientras prepara el audio no reproduce y lo dice", async () => {
    api({ timing: () => hangUntilAborted(undefined) });
    renderPage();

    const button = await screen.findByRole("button", { name: "Reproducir" });
    expect(button).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText("Preparando el audio…")).toBeVisible();
    await userEvent.click(button);
    expect(audio.engines).toHaveLength(0);
  });

  it("si falla el mapa de tiempos lo dice y permite reintentar", async () => {
    let fail = true;
    api({
      timing: () => (fail ? jsonResponse({ detail: "fallo" }, 500) : jsonResponse(timingMap())),
    });
    renderPage();

    expect(await screen.findByText("No se pudo preparar el audio.")).toBeVisible();
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Reintentar el audio" }));
    await playButton();
  });

  it("si la partitura no tiene notas que sonar, lo dice y no reproduce", async () => {
    api({ timing: () => jsonResponse(timingMap([1, 2, 3], "rest")) });
    renderPage();

    expect(await screen.findByText("Sin notas que sonar.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Reproducir" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
  });

  it("si el audio no arranca en el navegador, lo dice", async () => {
    audio.failPlay = true;
    api();
    renderPage();
    await userEvent.click(await playButton());

    expect(await screen.findByText("No se pudo iniciar el audio.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reproducir" })).toBeVisible();
  });
});

describe("elegir una nota sobre la partitura", () => {
  const findScore = () => screen.findByRole("application", { name: /partitura transcrita/i });
  const selection = () => document.querySelector<HTMLElement>(".notation__selection");
  const live = () => document.querySelector(".selection [role='status']");
  /** Centro de la cabeza de la primera figura de un compás (1, 2 o 3), con el zoom de jsdom. */
  const head = (measure: number) => ({
    clientX: (15 + (measure - 1) * 20) * 7.5,
    clientY: 7 * 7.5,
  });
  /** Ancho controlado por la prueba: devuelve con qué cambiarlo y avisar del cambio. */
  function observeResizes(initial: number) {
    let width = initial;
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockImplementation(() => width);
    const observers: (() => void)[] = [];
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(callback: () => void) {
          observers.push(callback);
        }
        observe() {
          // El doble solo guarda el aviso; la prueba lo dispara a mano.
        }
        disconnect() {
          // Nada que soltar.
        }
      },
    );
    return (next: number) => {
      width = next;
      for (const notify of observers) notify();
    };
  }

  it("elige con el ratón la nota tocada, la marca, la anuncia y guarda su ancla", async () => {
    api();
    renderPage();
    expect(
      await screen.findByText("Elige una nota o un silencio: tócalo o usa las flechas."),
    ).toBeVisible();
    const region = await findScore();

    fireEvent.click(region, head(2));

    // Cabeza de la nota del compás 2: x = (35 − 0,6) unidades × 7,5 px.
    expect(selection()?.style.left).toBe("258px");
    expect(selection()?.style.width).toBe("9px");
    expect(screen.getByText("Compás 2 · Voz 1")).toBeVisible();
    expect(screen.getByText("Do4 · blanca con puntillo")).toBeVisible();
    expect(useSelectionStore.getState().selection).toEqual({
      sessionId: ID,
      seq: 0,
      anchor: {
        part: 0,
        staff: 0,
        measure: 2,
        voice: 0,
        event_index: 0,
        staff_id: "part-0-staff-0",
        bbox: null,
        confidence: null,
      },
    });
    await waitFor(() => {
      expect(live()).toHaveTextContent("Compás 2, voz 1: Do 4, blanca con puntillo.");
    });
    // El clic deja el foco en la partitura para seguir con el teclado.
    expect(document.activeElement).toBe(region);
  });

  it("se mueve con el teclado y anuncia solo dónde se detiene", async () => {
    api();
    renderPage();
    const region = await findScore();
    region.focus();

    fireEvent.keyDown(region, { key: "ArrowRight" });
    fireEvent.keyDown(region, { key: "ArrowRight" });
    fireEvent.keyDown(region, { key: "ArrowRight" });
    expect(screen.getByText("Compás 3 · Voz 1")).toBeVisible();
    // Los pasos intermedios no se anuncian.
    expect(live()).toBeEmptyDOMElement();
    await waitFor(() => {
      expect(live()).toHaveTextContent("Compás 3, voz 1: Do 4, blanca con puntillo.");
    });

    fireEvent.keyDown(region, { key: "ArrowLeft", ctrlKey: true });
    expect(screen.getByText("Compás 2 · Voz 1")).toBeVisible();
    fireEvent.keyDown(region, { key: "PageUp" });
    expect(screen.getByText("Compás 1 · Voz 1")).toBeVisible();
    fireEvent.keyDown(region, { key: "PageDown" });
    expect(screen.getByText("Compás 2 · Voz 1")).toBeVisible();

    fireEvent.keyDown(region, { key: "Escape" });
    expect(selection()).toBeNull();
    expect(useSelectionStore.getState().selection).toBeNull();
    await waitFor(() => {
      expect(live()).toHaveTextContent("Sin nota elegida.");
    });
  });

  it("recorre las figuras de un compás con Inicio y Fin y distingue los silencios", async () => {
    osmd.figures = [
      [
        { pitch: "E4", whole: [1, 4] },
        { pitch: null, whole: [1, 4] },
        { pitch: "G4", whole: [1, 4] },
      ],
    ];
    const first = measure(1).events[0];
    const current = detail();
    const staff = current.current_score?.parts[0]?.staves[0];
    if (!first || !staff?.measures[0]) throw new Error("partitura de prueba incompleta");
    staff.measures[0].events = [
      { ...first, kind: "note", pitch: "E4", duration_beats: "1" },
      { ...first, kind: "rest", pitch: null, duration_beats: "1" },
      { ...first, kind: "note", pitch: "G4", duration_beats: "1" },
    ];
    api({ detail: current });
    renderPage();
    const region = await findScore();

    // Sin nada elegido, la primera tecla elige el primer evento.
    fireEvent.keyDown(region, { key: "End" });
    expect(screen.getByText("Mi4 · negra")).toBeVisible();
    fireEvent.keyDown(region, { key: "End" });
    expect(screen.getByText("Sol4 · negra")).toBeVisible();
    fireEvent.keyDown(region, { key: "ArrowLeft" });
    expect(screen.getByText("Silencio de negra")).toBeVisible();
    fireEvent.keyDown(region, { key: "Home" });
    expect(screen.getByText("Mi4 · negra")).toBeVisible();
  });

  it("anuncia también un evento que se describe igual que el anterior", async () => {
    osmd.figures = [
      [
        { pitch: "C4", whole: [1, 4] },
        { pitch: "C4", whole: [1, 4] },
        { pitch: "C4", whole: [1, 4] },
      ],
    ];
    const first = measure(1).events[0];
    const current = detail();
    const staff = current.current_score?.parts[0]?.staves[0];
    if (!first || !staff?.measures[0]) throw new Error("partitura de prueba incompleta");
    staff.measures[0].events = [1, 2, 3].map(() => ({
      ...first,
      kind: "note" as const,
      duration_beats: "1",
    }));
    api({ detail: current });
    renderPage();
    const region = await findScore();

    fireEvent.keyDown(region, { key: "ArrowRight" });
    await waitFor(() => {
      expect(live()).toHaveTextContent("Compás 1, voz 1: Do 4, negra.");
    });
    const before = live()?.textContent;
    fireEvent.keyDown(region, { key: "ArrowRight" });

    // El texto es el mismo: cambia lo justo para que el lector de pantalla lo vuelva a leer.
    await waitFor(() => {
      expect(live()?.textContent).not.toBe(before);
    });
    expect(live()).toHaveTextContent("Compás 1, voz 1: Do 4, negra.");
  });

  it("no trae la nota a la vista al volver a maquetar si la tecla no la movió", async () => {
    const resize = observeResizes(1200);
    api();
    renderPage();
    const region = await findScore();
    // A zoom 1, la cabeza del compás 3 está en x = 55 unidades × 10 px.
    fireEvent.click(region, { clientX: 550, clientY: 70 });
    // Es el último evento: la flecha no la mueve.
    fireEvent.keyDown(region, { key: "ArrowRight" });
    expect(screen.getByText("Compás 3 · Voz 1")).toBeVisible();
    scrollIntoView.mockClear();

    resize(390);

    await waitFor(() => {
      expect(selection()?.style.left).toBe("408px");
    });
    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it("los botones de la barra, la alternativa táctil, mueven la selección", async () => {
    api();
    renderPage();
    const region = await findScore();
    fireEvent.click(region, head(1));
    scrollIntoView.mockClear();

    await userEvent.click(screen.getByRole("button", { name: "Siguiente" }));
    expect(screen.getByText("Compás 2 · Voz 1")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Anterior" }));
    expect(screen.getByText("Compás 1 · Voz 1")).toBeVisible();
    // La nota elegida se trae a la vista al moverse.
    expect(scrollIntoView).toHaveBeenCalledWith(expect.objectContaining({ block: "nearest" }));

    await userEvent.click(screen.getByRole("button", { name: "Quitar" }));
    expect(selection()).toBeNull();
    expect(document.activeElement).toBe(region);
  });

  it("con movimiento reducido trae la nota a la vista sin desplazamiento suave", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({ matches: query.includes("reduce") }));
    api();
    renderPage();
    const region = await findScore();
    scrollIntoView.mockClear();

    fireEvent.keyDown(region, { key: "ArrowRight" });

    expect(scrollIntoView).toHaveBeenCalledWith(expect.objectContaining({ behavior: "auto" }));
  });

  it("convive con la marca del compás dudoso y con el compás que suena", async () => {
    api({ findings: [finding(1, 2)] });
    renderPage();
    const region = await findScore();
    const play = await screen.findByRole("button", { name: "Reproducir" });
    await waitFor(() => {
      expect(play).not.toHaveAttribute("aria-disabled", "true");
    });
    await userEvent.click(play);
    act(() => {
      audio.engines.at(-1)?.advance(3.5);
    });

    fireEvent.click(region, head(2));

    expect(document.querySelector(".notation__mark")).not.toBeNull();
    expect(document.querySelector<HTMLElement>(".notation__playhead")?.style.left).toBe("225px");
    expect(selection()?.style.left).toBe("258px");
    // Elegir una nota no detiene la reproducción.
    expect(audio.engines.at(-1)?.playing).toBe(true);
  });

  it("al volver a maquetar recoloca la nota elegida y la conserva", async () => {
    const resize = observeResizes(1200);
    api();
    renderPage();
    const region = await findScore();
    // A zoom 1, la cabeza del compás 2 está en x = 35 unidades × 10 px.
    fireEvent.click(region, { clientX: 350, clientY: 70 });
    expect(selection()?.style.left).toBe("344px");

    resize(390);

    await waitFor(() => {
      expect(selection()?.style.left).toBe("258px");
    });
    expect(screen.getByText("Compás 2 · Voz 1")).toBeVisible();
  });

  it("si lo dibujado no coincide con la transcripción, no ofrece elegir notas y lo dice", async () => {
    osmd.figures = [[{ pitch: "D4", whole: [3, 4] }]];
    api();
    renderPage();

    expect(
      await screen.findByText(
        "No se puede elegir nota a nota en esta partitura: 1 de los 3 eventos no coincide con lo dibujado.",
      ),
    ).toBeVisible();
    expect(screen.queryByRole("application")).toBeNull();
    expect(screen.getByRole("img", { name: /partitura transcrita/i })).toBeInTheDocument();
    expect(selection()).toBeNull();
  });

  it("si OSMD dibuja otros compases, tampoco ofrece elegir notas", async () => {
    osmd.measures = 2;
    api();
    renderPage();

    expect(
      await screen.findByText("No se puede elegir nota a nota en esta partitura."),
    ).toBeVisible();
    expect(screen.queryByRole("application")).toBeNull();
  });

  /** Sustituye los eventos del compás 1 de la sesión de prueba. */
  function firstMeasure(events: Partial<ScoreEventPayload>[]) {
    const base = measure(1).events[0];
    const current = detail();
    const staff = current.current_score?.parts[0]?.staves[0];
    if (!base || !staff?.measures[0]) throw new Error("partitura de prueba incompleta");
    staff.measures[0].events = events.map((changes) => ({ ...base, kind: "note", ...changes }));
    return current;
  }

  it("no muestra una nota elegida en otra sesión ni en otro estado de esta", async () => {
    const anchor = {
      part: 0,
      staff: 0,
      measure: 2,
      voice: 0,
      event_index: 0,
      staff_id: "part-0-staff-0",
      bbox: null,
      confidence: null,
    };
    useSelectionStore.getState().select({ sessionId: "otra", seq: 0, anchor });
    api();
    renderPage();
    await findScore();
    expect(selection()).toBeNull();

    act(() => {
      useSelectionStore.getState().select({ sessionId: ID, seq: 5, anchor });
    });
    expect(selection()).toBeNull();

    act(() => {
      useSelectionStore.getState().select({ sessionId: ID, seq: 0, anchor });
    });
    expect(selection()?.style.left).toBe("258px");
  });

  it("una partitura sin notas ni silencios no se ofrece como control", async () => {
    osmd.figures = [[], [], []];
    const current = detail();
    for (const staff of current.current_score?.parts[0]?.staves ?? []) {
      for (const empty of staff.measures) empty.events = [];
    }
    api({ detail: current });
    renderPage();

    expect(
      await screen.findByText("La partitura no tiene notas ni silencios que elegir."),
    ).toBeVisible();
    expect(screen.queryByRole("application")).toBeNull();
    expect(screen.getByRole("img", { name: /partitura transcrita/i })).toBeInTheDocument();
  });

  it("marca por separado cada figura de una nota partida en notas ligadas", async () => {
    osmd.figures = [
      [
        { pitch: "C4", whole: [1, 4] },
        { pitch: "C4", whole: [1, 16] },
      ],
    ];
    api({
      detail: detail({ current_score: firstMeasure([{ duration_beats: "5/4" }]).current_score }),
    });
    renderPage();
    const region = await findScore();

    fireEvent.keyDown(region, { key: "ArrowRight" });

    const marks = document.querySelectorAll<HTMLElement>(".notation__selection");
    expect([...marks].map((mark) => mark.style.left)).toEqual(["108px", "145.5px"]);
  });

  it("en un acorde elige la cabeza tocada y dice que es de acorde", async () => {
    osmd.figures = [[{ pitch: "C4", chord: ["E4"], whole: [3, 4] }]];
    api({
      detail: detail({
        current_score: firstMeasure([{ pitch: "C4" }, { pitch: "E4", is_chord: true }])
          .current_score,
      }),
    });
    renderPage();
    const region = await findScore();

    // Mi4 es la segunda nota del acorde: una unidad por encima de Do4.
    fireEvent.click(region, { clientX: 15 * 7.5, clientY: 6 * 7.5 });
    expect(screen.getByText("Mi4 · blanca con puntillo")).toBeVisible();
    fireEvent.click(region, { clientX: 15 * 7.5, clientY: 7 * 7.5 });
    expect(screen.getByText("Do4 · blanca con puntillo")).toBeVisible();
    await waitFor(() => {
      expect(live()).toHaveTextContent("Compás 1, voz 1: Do 4, blanca con puntillo, en acorde.");
    });
  });

  it("empareja las voces por su número aunque OSMD las dé en otro orden, y pasa de una a otra", async () => {
    osmd.figures = [
      [
        { pitch: "C4", whole: [3, 4], voice: 2 },
        { pitch: "E5", whole: [3, 4], voice: 1 },
      ],
    ];
    api({
      detail: detail({
        current_score: firstMeasure([{ pitch: "E5" }, { pitch: "C4", voice: 1 }]).current_score,
      }),
    });
    renderPage();
    const region = await findScore();

    fireEvent.keyDown(region, { key: "ArrowRight" });
    expect(screen.getByText("Mi5 · blanca con puntillo")).toBeVisible();
    fireEvent.keyDown(region, { key: "ArrowDown" });
    expect(screen.getByText("Compás 1 · Voz 2")).toBeVisible();
    expect(screen.getByText("Do4 · blanca con puntillo")).toBeVisible();
    // Ctrl con ↑ y Alt con → no son teclas de la partitura.
    fireEvent.keyDown(region, { key: "ArrowUp", ctrlKey: true });
    fireEvent.keyDown(region, { key: "ArrowRight", altKey: true });
    expect(screen.getByText("Compás 1 · Voz 2")).toBeVisible();
    fireEvent.keyDown(region, { key: "ArrowUp" });
    expect(screen.getByText("Compás 1 · Voz 1")).toBeVisible();
    // ⌘ con → salta de compás, como Ctrl.
    fireEvent.keyDown(region, { key: "ArrowRight", metaKey: true });
    expect(screen.getByText("Compás 2 · Voz 1")).toBeVisible();
  });

  it("no cuenta como figura el silencio invisible que OSMD guarda ni lo ofrece para elegir (ADR-0032)", async () => {
    osmd.figures = [
      [
        { pitch: "E5", whole: [3, 4], voice: 1 },
        { pitch: null, whole: [1, 4], voice: 2, hidden: true },
        { pitch: "C4", whole: [2, 4], voice: 2 },
      ],
    ];
    api({
      detail: detail({
        current_score: firstMeasure([
          { pitch: "E5", duration_beats: "3" },
          { kind: "rest", pitch: null, duration_beats: "1", voice: 1, hidden: true },
          { pitch: "C4", duration_beats: "2", voice: 1 },
        ]).current_score,
      }),
    });
    renderPage();
    const region = await findScore();

    fireEvent.keyDown(region, { key: "ArrowRight" });
    expect(screen.getByText("Mi5 · blanca con puntillo")).toBeVisible();
    fireEvent.keyDown(region, { key: "ArrowDown" });
    expect(screen.getByText("Compás 1 · Voz 2")).toBeVisible();
    expect(screen.getByText("Do4 · blanca")).toBeVisible();
    // El silencio invisible no se elige: al principio de la voz está Do4.
    fireEvent.keyDown(region, { key: "Home" });
    expect(screen.getByText("Do4 · blanca")).toBeVisible();
  });

  it("elige por separado la nota de adorno y la nota a la que adorna (D60)", async () => {
    osmd.figures = [[{ pitch: "A4", whole: [3, 4], grace: "G#4" }]];
    api({
      detail: detail({
        current_score: firstMeasure([
          { pitch: "G#4", duration_beats: "0" },
          { pitch: "A4", duration_beats: "3" },
        ]).current_score,
      }),
    });
    renderPage();
    const region = await findScore();

    fireEvent.keyDown(region, { key: "ArrowRight" });
    expect(screen.getByText("Sol#4 · sin duración")).toBeVisible();
    // La nota de adorno, 1,5 unidades a la izquierda: (15 − 1,5 − 0,6) unidades × 7,5 px.
    expect(selection()?.style.left).toBe("96.75px");
    fireEvent.keyDown(region, { key: "ArrowRight" });
    expect(screen.getByText("La4 · blanca con puntillo")).toBeVisible();
    // Solo su cabeza, sin la de la nota de adorno que lleva dentro.
    expect(selection()?.style.left).toBe("108px");
    expect(selection()?.style.width).toBe("9px");
  });

  it("ante un silencio, la nota de adorno y el silencio tienen cada uno su caja", async () => {
    osmd.figures = [[{ pitch: null, whole: [3, 4], grace: "G4" }]];
    api({
      detail: detail({
        current_score: firstMeasure([
          { pitch: "G4", duration_beats: "0" },
          { kind: "rest", pitch: null, duration_beats: "3" },
        ]).current_score,
      }),
    });
    renderPage();
    const region = await findScore();

    fireEvent.keyDown(region, { key: "ArrowRight" });
    expect(screen.getByText("Sol4 · sin duración")).toBeVisible();
    expect(selection()?.style.left).toBe("96.75px");
    fireEvent.keyDown(region, { key: "ArrowRight" });
    expect(screen.getByText("Silencio de blanca con puntillo")).toBeVisible();
    // El glifo del silencio, no la cabeza de la nota de adorno que lleva dentro.
    expect(selection()?.style.left).toBe("108px");
  });

  it("marca el glifo del silencio, sin su puntillo", async () => {
    osmd.figures = [[{ pitch: null, whole: [3, 4], dot: true }]];
    api({
      detail: detail({
        current_score: firstMeasure([{ kind: "rest", pitch: null, duration_beats: "3" }])
          .current_score,
      }),
    });
    renderPage();

    fireEvent.keyDown(await findScore(), { key: "ArrowRight" });

    expect(screen.getByText("Silencio de blanca con puntillo")).toBeVisible();
    expect(selection()?.style.width).toBe("9px");
  });

  it("la leyenda nombra las teclas de compás de cada sistema", async () => {
    api();
    renderPage();
    await findScore();

    const keys = document.querySelector(".selection__keys");
    for (const label of ["Ctrl", "Cmd", "Re Pág", "Av Pág", "Inicio", "Fin", "Esc"]) {
      expect(keys).toHaveTextContent(label);
    }
  });

  it("al salir de la sesión olvida la nota elegida", async () => {
    api();
    const router = renderPage();
    fireEvent.click(await findScore(), head(1));
    expect(useSelectionStore.getState().selection).not.toBeNull();

    await router.navigate("/transcripcion");

    await waitFor(() => {
      expect(useSelectionStore.getState().selection).toBeNull();
    });
  });
});

describe("corregir la nota elegida", () => {
  const findScore = () => screen.findByRole("application", { name: /partitura transcrita/i });
  const selection = () => document.querySelector<HTMLElement>(".notation__selection");
  const editor = () => screen.getByRole("region", { name: "Corregir la nota elegida" });
  const editStatus = () => document.querySelector(".editor__status");
  const button = (name: string) => within(editor()).getByRole("button", { name });
  /** Centro de la cabeza de la primera figura de un compás (1, 2 o 3), con el zoom de jsdom. */
  const head = (measure: number) => ({
    clientX: (15 + (measure - 1) * 20) * 7.5,
    clientY: 7 * 7.5,
  });
  const anchorOf = (measureNumber: number) => ({
    part: 0,
    staff: 0,
    measure: measureNumber,
    voice: 0,
    event_index: 0,
    staff_id: "part-0-staff-0",
    bbox: null,
    confidence: null,
  });

  /** Duración en negras («3/2») como la da OSMD: fracción de redonda. */
  function whole(beats: string): [number, number] {
    const [numerator = "0", denominator = "1"] = beats.split("/");
    return [Number(numerator), Number(denominator) * 4];
  }

  /**
   * Lo que dibujaría OSMD para un detalle: una figura por nota, acorde o silencio de cada compás,
   * con su voz; un silencio invisible, guardado pero sin dibujar (ADR-0032).
   */
  function draw(current: SessionDetailRead) {
    osmd.figures =
      current.current_score?.parts[0]?.staves[0]?.measures.map((measure) => {
        const figures: NonNullable<typeof osmd.figures>[number] = [];
        for (const event of measure.events) {
          const previous = figures.at(-1);
          if (
            event.is_chord &&
            event.pitch &&
            previous?.pitch &&
            previous.voice === event.voice + 1
          ) {
            previous.chord = [...(previous.chord ?? []), event.pitch];
            continue;
          }
          figures.push({
            pitch: event.pitch,
            whole: whole(event.duration_beats ?? "0"),
            voice: event.voice + 1,
            hidden: event.hidden === true,
          });
        }
        return figures;
      }) ?? null;
  }

  /** Marcas de un evento (ADR-0031) y su invisibilidad (ADR-0032), las que guarda un borrado. */
  const EVENT_EXTRAS = ["articulations", "fermata", "slurs", "hidden"] as const;

  /**
   * Aplica una edición al detalle como lo haría el servidor y devuelve el evento guardado, con la
   * instantánea del estado previo que fija el servidor (ADR-0017). `extra` completa lo guardado
   * (la edición que revierte una compensatoria).
   */
  function apply(
    current: SessionDetailRead,
    body: EditEventCreate,
    extra: Partial<EditEventRead> = {},
  ) {
    const next = structuredClone(current);
    const seq = (current.current_seq ?? 0) + 1;
    const measureNumber = body.anchor.measure;
    const measure = next.current_score?.parts[0]?.staves[0]?.measures.find(
      (candidate) => candidate.number === measureNumber,
    );
    if (!measure) throw new Error("ancla sin compás");
    // El `event_index` cuenta los eventos de su voz (ADR-0011).
    const positions = measure.events.flatMap((candidate, index) =>
      candidate.voice === body.anchor.voice ? [index] : [],
    );
    const position = positions[body.anchor.event_index];
    const event = position === undefined ? undefined : measure.events[position];
    const after = body.after ?? {};
    let before: Record<string, unknown> | null = null;
    if (body.op === "SetClef") {
      before = { clef: measure.clef ?? null };
      measure.clef =
        "clef" in after
          ? ((after.clef ?? null) as typeof measure.clef)
          : { sign: String(after.sign), line: Number(after.line) };
    } else if (body.op === "SetKey") {
      before = { key_signature: measure.key_signature ?? null };
      measure.key_signature =
        "key_signature" in after
          ? ((after.key_signature ?? null) as typeof measure.key_signature)
          : { fifths: Number(after.fifths) };
    } else if (body.op === "InsertEvent") {
      const extras = Object.fromEntries(
        EVENT_EXTRAS.filter((key) => key in after).map((key) => [key, after[key]]),
      );
      measure.events.splice(position ?? (positions.at(-1) ?? -1) + 1, 0, {
        kind: after.kind === "rest" ? "rest" : "note",
        voice: body.anchor.voice,
        pitch: typeof after.pitch === "string" ? after.pitch : null,
        duration_beats: String(after.duration_beats),
        tie: typeof after.tie === "string" ? after.tie : null,
        is_chord: after.is_chord === true,
        bbox: null,
        confidence: null,
        ir_handle: null,
        ...extras,
      });
    } else if (!event || position === undefined) {
      throw new Error("ancla sin evento");
    } else if (body.op === "DeleteEvent") {
      const { kind, pitch, duration_beats, tie, is_chord, bbox, confidence } = event;
      before = { kind, pitch, duration_beats, tie, is_chord, bbox, confidence };
      for (const key of EVENT_EXTRAS) if (key in event) before[key] = event[key];
      measure.events.splice(position, 1);
    }
    if (event && body.op === "SetPitch") {
      before = { pitch: event.pitch };
      event.pitch = String(after.pitch);
    }
    if (event && body.op === "SetDuration") {
      before = { duration_beats: event.duration_beats };
      event.duration_beats = String(after.duration_beats);
    }
    if (event && body.op === "SetAccidental") {
      before = { accidental: /^[A-G]([#b]*)\d$/.exec(event.pitch ?? "")?.[1] ?? null };
      const written = typeof after.accidental === "string" ? after.accidental : "";
      const accidental = written === "natural" ? "" : written;
      event.pitch = (event.pitch ?? "").replace(/^([A-G])[#b]*(\d)$/, `$1${accidental}$2`);
    }
    // Marcas de notación (ADR-0039), en el único pentagrama de estas partituras.
    if (event && body.op === "SetNoteMarks") {
      before = { articulations: event.articulations ?? [], fermata: event.fermata === true };
      event.articulations = after.articulations as typeof event.articulations;
      event.fermata = after.fermata === true;
    }
    if (body.op === "SetDynamic") {
      const offset = String(after.offset_beats);
      const dynamics = measure.dynamics ?? [];
      before = {
        offset_beats: offset,
        mark: dynamics.find((d) => d.offset_beats === offset)?.mark ?? null,
      };
      measure.dynamics = [
        ...dynamics.filter((d) => d.offset_beats !== offset),
        ...(typeof after.mark === "string"
          ? [
              {
                mark: after.mark as NonNullable<typeof measure.dynamics>[number]["mark"],
                offset_beats: offset,
              },
            ]
          : []),
      ];
    }
    const measures = next.current_score?.parts[0]?.staves[0]?.measures ?? [];
    const number = Number(after.number);
    if (body.op === "SetSlur") {
      const ends: Record<string, unknown> = { number, start: null, stop: null };
      for (const candidate of measures) {
        candidate.events.forEach((item, index) => {
          for (const slur of item.slurs ?? []) {
            if (slur.number !== number) continue;
            ends[slur.type] = { staff: 0, measure: candidate.number, voice: 0, event_index: index };
          }
          item.slurs = (item.slurs ?? []).filter((slur) => slur.number !== number);
        });
      }
      before = ends;
      for (const type of ["start", "stop"] as const) {
        const end = after[type] as { measure: number; event_index: number } | null;
        const target = end
          ? measures.find((candidate) => candidate.number === end.measure)?.events[end.event_index]
          : undefined;
        if (target) target.slurs = [...(target.slurs ?? []), { type, number }];
      }
    }
    if (body.op === "SetWedge") {
      const ends: Record<string, unknown> = { number, start: null, stop: null };
      for (const candidate of measures) {
        for (const wedge of candidate.wedges ?? []) {
          if (wedge.number !== number) continue;
          const at = { staff: 0, measure: candidate.number, offset_beats: wedge.offset_beats };
          if (wedge.type === "stop") ends.stop = at;
          else ends.start = { ...at, type: wedge.type };
        }
        candidate.wedges = (candidate.wedges ?? []).filter((wedge) => wedge.number !== number);
      }
      before = ends;
      for (const role of ["start", "stop"] as const) {
        const end = after[role] as { measure: number; offset_beats: string; type?: string } | null;
        const target = end ? measures.find((candidate) => candidate.number === end.measure) : null;
        if (target && end) {
          const type = (role === "stop" ? "stop" : end.type) as "crescendo" | "diminuendo" | "stop";
          target.wedges = [
            ...(target.wedges ?? []),
            { type, number, offset_beats: end.offset_beats },
          ];
        }
      }
    }
    const saved: EditEventRead = {
      id: `edit-${String(seq)}`,
      session_id: ID,
      seq,
      op: body.op,
      author: "ana",
      anchor: body.anchor,
      before,
      after: body.after ?? null,
      reverts_edit_id: null,
      // Sin zona, como lo da la API sobre SQLite: es UTC.
      created_at: "2026-10-24T10:00:00",
      ...extra,
    };
    next.current_seq = seq;
    next.edits = [...next.edits, saved];
    next.status = "correcting";
    return { next, saved };
  }

  /** Última edición vigente del log, como `get_last_active_edit` del servidor. */
  function lastActive(edits: readonly EditEventRead[]) {
    const active: EditEventRead[] = [];
    for (const edit of [...edits].sort((a, b) => a.seq - b.seq)) {
      if (!edit.reverts_edit_id) active.push(edit);
      else {
        const index = active.map((candidate) => candidate.id).lastIndexOf(edit.reverts_edit_id);
        if (index >= 0) active.splice(index, 1);
      }
    }
    return active.at(-1) ?? null;
  }

  /** Edición compensatoria de `edit`, como `create_inverse_edit` del servidor (ADR-0007). */
  function inverse(edit: EditEventRead, baseSeq: number): EditEventCreate {
    const op =
      edit.op === "InsertEvent"
        ? "DeleteEvent"
        : edit.op === "DeleteEvent"
          ? "InsertEvent"
          : edit.op;
    const after = edit.op === "InsertEvent" ? null : edit.before;
    return { base_seq: baseSeq, op, anchor: edit.anchor, before: null, after };
  }

  type EditRoute = (body: EditEventCreate) => Response | Promise<Response>;
  type FindingRoute = (key: string, body: unknown) => Response | Promise<Response>;
  type UndoRoute = () => Response | Promise<Response>;

  /**
   * API de una sesión editable: guarda los cuerpos de las ediciones y, por defecto, las acepta
   * con un 201 y cambia el detalle y el dibujo. `respond` cambia la respuesta de la siguiente.
   * `POST /undo` deshace la última edición vigente con su compensatoria (`respondUndo`, igual).
   */
  function editableApi(
    start: SessionDetailRead = detail(),
    options: {
      /** Hallazgos de la última validación, también los descartados. */
      findings?: FindingRead[];
      /** Lo que señala el validador sobre un estado (`POST /validate`). */
      validate?: (current: SessionDetailRead) => FindingRead[];
    } = {},
  ) {
    let current = start;
    let findings = options.findings ?? [];
    let findingsStatus: number | null = null;
    const findingCalls: { key: string; body: unknown }[] = [];
    const findingQueue: FindingRoute[] = [];
    const validateQueue: (() => Response | Promise<Response>)[] = [];
    /** Descarta o restaura como el servidor: 404 si el hallazgo no está, 409 si está finalizada. */
    const acceptFinding = (key: string, body: unknown) => {
      const match = /findings\/(\d+)\/(dismiss|restore)$/.exec(key);
      const target = findings.find((candidate) => candidate.id === Number(match?.[1]));
      if (!target) return jsonResponse({ detail: "finding not found" }, 404);
      if (current.status === "finalized") return jsonResponse({ detail: "Sesión cerrada" }, 409);
      const reason = (body as { reason?: string | null } | null)?.reason ?? null;
      const updated: FindingRead =
        match?.[2] === "dismiss"
          ? {
              ...target,
              status: "dismissed",
              dismissed_at: "2026-10-24T11:00:00",
              dismissed_by: "ana",
              dismissal_reason: reason,
            }
          : {
              ...target,
              status: "active",
              dismissed_at: null,
              dismissed_by: null,
              dismissal_reason: null,
            };
      findings = findings.map((candidate) => (candidate.id === target.id ? updated : candidate));
      return jsonResponse(updated);
    };
    /** Revalida el estado actual: sus hallazgos pasan a ser los de la última validación. */
    const acceptValidate = () => {
      const seq = current.current_seq ?? 0;
      findings = (options.validate?.(current) ?? []).map((candidate) => ({
        ...candidate,
        at_seq: seq,
      }));
      return jsonResponse({
        session_id: ID,
        current_seq: seq,
        findings: findings.filter((candidate) => candidate.status !== "dismissed"),
      });
    };
    const findingRoutes = Object.fromEntries(
      Array.from({ length: 9 }, (_unused, index) => index + 1).flatMap((id) =>
        ["dismiss", "restore"].map((action) => {
          const key = `POST /sessions/${ID}/findings/${String(id)}/${action}`;
          const route = (init: RequestInit | undefined) => {
            const body: unknown = typeof init?.body === "string" ? JSON.parse(init.body) : null;
            findingCalls.push({ key, body });
            return (findingQueue.shift() ?? acceptFinding)(key, body);
          };
          return [key, route];
        }),
      ),
    );
    draw(current);
    const bodies: EditEventCreate[] = [];
    const queue: EditRoute[] = [];
    const undoBodies: unknown[] = [];
    const undoQueue: UndoRoute[] = [];
    let exportStatus: number | null = null;
    let exportOverride: ((init: RequestInit | undefined) => Promise<Response>) | null = null;
    // Como el servidor: un `base_seq` que no es el del estado actual es un 409 (ADR-0011).
    const stale = (baseSeq: number | null | undefined) =>
      baseSeq !== undefined && baseSeq !== null && baseSeq !== (current.current_seq ?? 0);
    // Lo que el servidor devuelve además del estado nuevo con la orden (#275): el MusicXML (null
    // si no lo pudo exportar) y los tiempos solo si cambian (aquí, al cambiar una duración o al
    // insertar o borrar).
    const extrasOf = (next: SessionDetailRead, op: string) => ({
      status: next.status ?? "correcting",
      musicxml: exportStatus ? null : xmlOf(next),
      timing: ["SetDuration", "InsertEvent", "DeleteEvent"].includes(op) ? timingMap() : null,
    });
    /** Guarda la edición como el servidor y responde 201; con `bare`, sin el estado nuevo. */
    const save = (body: EditEventCreate, bare: boolean) => {
      if (stale(body.base_seq)) return jsonResponse({ detail: "Conflicto de secuencia" }, 409);
      const { next, saved } = apply(current, body);
      current = next;
      draw(current);
      if (bare) return jsonResponse(saved, 201);
      return jsonResponse(
        {
          ...saved,
          current_seq: next.current_seq ?? 0,
          current_score: next.current_score,
          ...extrasOf(next, body.op),
        },
        201,
      );
    };
    const accept = (body: EditEventCreate) => save(body, false);
    /** Un 201 con la edición y sin el estado nuevo, como antes de #275. */
    const acceptBare = (body: EditEventCreate) => save(body, true);
    const acceptUndo = (body?: { base_seq?: number | null } | null) => {
      if (stale(body?.base_seq)) return jsonResponse({ detail: "Conflicto de secuencia" }, 409);
      const target = lastActive(current.edits);
      if (!target) return jsonResponse({ detail: "No hay ediciones activas para deshacer" }, 422);
      // Sin estado previo (anterior a ADR-0017), el servidor no la deshace.
      if (target.op !== "InsertEvent" && target.before === null) {
        return jsonResponse({ detail: "No guardó su estado previo completo" }, 422);
      }
      const { next, saved } = apply(current, inverse(target, current.current_seq ?? 0), {
        before: target.op === "DeleteEvent" ? null : target.after,
        reverts_edit_id: target.id,
      });
      current = next;
      draw(current);
      return jsonResponse({
        session_id: ID,
        current_seq: saved.seq,
        undone_edit_id: target.id,
        current_score: next.current_score,
        anchor_index: null,
        compensatory_edit_id: saved.id,
        compensatory_edit: saved,
        ...extrasOf(next, saved.op),
      });
    };
    let detailRoute: (() => Response | Promise<Response>) | null = null;
    const server = mockApi({
      [`GET /sessions/${ID}`]: () => (detailRoute ? detailRoute() : jsonResponse(current)),
      [`GET /sessions/${ID}/findings`]: () =>
        findingsStatus === null
          ? jsonResponse(findings)
          : jsonResponse({ detail: "fallo" }, findingsStatus),
      ...findingRoutes,
      [`POST /sessions/${ID}/validate`]: () => (validateQueue.shift() ?? acceptValidate)(),
      [`GET /sessions/${ID}/export`]: (init) =>
        exportOverride
          ? exportOverride(init)
          : exportStatus
            ? jsonResponse({ detail: "fallo" }, exportStatus)
            : new Response(xmlOf(current), {
                headers: { "Content-Type": "application/vnd.recordare.musicxml" },
              }),
      [`GET /sessions/${ID}/image`]: png,
      [`GET /sessions/${ID}/timing`]: () => jsonResponse(timingMap()),
      "GET /users": () => jsonResponse([ANA, LUIS, INVESTIGADORA]),
      [`POST /sessions/${ID}/edits`]: (init) => {
        const body = JSON.parse(typeof init?.body === "string" ? init.body : "") as EditEventCreate;
        bodies.push(body);
        return (queue.shift() ?? accept)(body);
      },
      [`POST /sessions/${ID}/undo`]: (init) => {
        const body = JSON.parse(typeof init?.body === "string" ? init.body : "null") as {
          base_seq?: number | null;
        } | null;
        undoBodies.push(body);
        return (undoQueue.shift() ?? (() => acceptUndo(body)))();
      },
    });
    return {
      ...server,
      bodies,
      undoBodies,
      findingCalls,
      accept,
      acceptBare,
      acceptUndo,
      acceptFinding,
      acceptValidate,
      /** Otra respuesta para el siguiente descarte o restauración. */
      respondFinding(route: FindingRoute) {
        findingQueue.push(route);
      },
      /** Otra respuesta para la siguiente revalidación. */
      respondValidate(route: () => Response | Promise<Response>) {
        validateQueue.push(route);
      },
      /** Cambia los hallazgos del servidor, como si se hubiera revalidado en otra pestaña. */
      setFindings(next: FindingRead[]) {
        findings = next;
      },
      /** Hace fallar la lista de posibles errores (o la arregla, con null). */
      failFindings(status: number | null) {
        findingsStatus = status;
      },
      respond(route: EditRoute) {
        queue.push(route);
      },
      respondUndo(route: UndoRoute) {
        undoQueue.push(route);
      },
      /** Hace fallar la exportación (o la arregla, con null). */
      failExport(status: number | null) {
        exportStatus = status;
      },
      /** Otra respuesta para la exportación (o la de siempre, con null). */
      exportRoute(route: ((init: RequestInit | undefined) => Promise<Response>) | null) {
        exportOverride = route;
      },
      /** Cambia el estado del servidor, como si se hubiera editado en otra pestaña. */
      replace(next: SessionDetailRead) {
        current = next;
        draw(current);
      },
      current: () => current,
      detailRoute(route: (() => Response | Promise<Response>) | null) {
        detailRoute = route;
      },
      count: (key: string) => server.calls.filter((call) => call.key === key).length,
    };
  }

  async function chooseMeasure(measure: number) {
    const region = await findScore();
    fireEvent.click(region, head(measure));
    return region;
  }

  it("guarda la altura con el base_seq del estado, sin darla por guardada antes del 201", async () => {
    const server = editableApi();
    renderPage();
    await chooseMeasure(2);
    const pending = deferred<Response>();
    server.respond(() => pending.promise);

    fireEvent.click(button("Subir un paso"));

    expect(server.bodies).toEqual([
      {
        base_seq: 0,
        op: "SetPitch",
        anchor: anchorOf(2),
        before: null,
        after: { pitch: "D4" },
      },
    ]);
    // Sin el 201 no se da nada por guardado: la nota sigue como estaba y los controles esperan.
    expect(screen.getByText("Do4 · blanca con puntillo")).toBeVisible();
    expect(editStatus()).toHaveTextContent("Guardando…");
    // La espera se dice en la barra sin cambiar el aspecto de sus botones (#276).
    expect(button("Subir un paso")).toHaveAttribute("aria-disabled", "false");

    const body = server.bodies[0];
    if (!body) throw new Error("sin edición");
    pending.resolve(server.accept(body));

    expect(await screen.findByText("Re4 · blanca con puntillo")).toBeVisible();
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent("Guardado: altura Re 4.");
    });
    expect(screen.getByText("Ediciones").nextElementSibling).toHaveTextContent("1");
    expect(screen.getByText("Estado").nextElementSibling).toHaveTextContent(/corrección/i);
  });

  it("tras el 201 muestra el estado nuevo que trae, sin pedir el detalle, el MusicXML, los tiempos ni los posibles errores", async () => {
    const server = editableApi();
    renderPage();
    await chooseMeasure(2);

    fireEvent.click(button("Subir un paso"));
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent("Guardado: altura Re 4.");
    });

    // Cada consulta del estado se pidió una vez, la del estado 0: el 201 trae el estado 1 (#275).
    expect(server.count(`GET /sessions/${ID}`)).toBe(1);
    expect(server.count(`GET /sessions/${ID}/export`)).toBe(1);
    expect(server.count(`GET /sessions/${ID}/findings`)).toBe(1);
    expect(server.count(`GET /sessions/${ID}/timing`)).toBe(1);
    // La vista pide el detalle sin el documento ni el índice de anclas.
    const detailCall = server.calls.find((call) => call.key === `GET /sessions/${ID}`);
    expect(detailCall?.url.searchParams.get("fields")).toBe("view");
    // El log que se ve es el del servidor: la edición nueva, sin el estado que la acompaña.
    expect(screen.getByText("Ediciones").nextElementSibling).toHaveTextContent("1");
    // La selección sigue en la misma ancla, ya en el estado nuevo, y se marca sobre la nota.
    expect(useSelectionStore.getState().selection).toEqual({
      sessionId: ID,
      seq: 1,
      anchor: anchorOf(2),
    });
    await waitFor(() => {
      expect(selection()).not.toBeNull();
    });
    // La descarga es la del estado nuevo, sin pedirla.
    captureDownloads();
    fireEvent.click(screen.getByRole("button", { name: /descargar musicxml/i }));
    expect(server.count(`GET /sessions/${ID}/export`)).toBe(1);
  });

  it("si el servidor no pudo exportar el estado nuevo, lo pide a /export y dice si falla", async () => {
    const server = editableApi();
    renderPage();
    await chooseMeasure(2);
    server.failExport(500);

    fireEvent.click(button("Subir un paso"));

    expect(await screen.findByText("No se pudo dibujar la partitura.")).toBeVisible();
    // Lo pide para ese estado (la vista vuelve a intentarlo al mostrarlo); el detalle, no.
    expect(server.count(`GET /sessions/${ID}/export`)).toBeGreaterThanOrEqual(2);
    expect(server.count(`GET /sessions/${ID}`)).toBe(1);
  });

  it("si cambian los tiempos, usa los que trae el 201; si no, los del estado anterior", async () => {
    const server = editableApi();
    renderPage();
    await chooseMeasure(2);

    fireEvent.click(button("Subir un paso"));
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent("Guardado: altura Re 4.");
    });
    fireEvent.click(button("Negra"));
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent(/Guardado: figura negra/);
    });

    // Ni la altura (los tiempos no cambian) ni la figura (vienen con el 201) los piden.
    expect(server.count(`GET /sessions/${ID}/timing`)).toBe(1);
    expect(screen.getByRole("button", { name: /reproducir/i })).toBeVisible();
  });

  it("si el 201 no trae el estado nuevo, lo pide entero", async () => {
    const server = editableApi();
    renderPage();
    await chooseMeasure(2);
    server.respond((body) => server.acceptBare(body));

    fireEvent.click(button("Subir un paso"));

    expect(await screen.findByText("Re4 · blanca con puntillo")).toBeVisible();
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent("Guardado: altura Re 4.");
    });
    expect(server.count(`GET /sessions/${ID}`)).toBe(2);
    expect(server.count(`GET /sessions/${ID}/export`)).toBe(2);
  });

  /**
   * Vigila que, desde que se da la orden, la marca de la nota elegida no falte en ningún momento:
   * un `MutationObserver` mira el DOM tras cada cambio.
   */
  function watchSelection() {
    let missing = 0;
    const observer = new MutationObserver(() => {
      if (!selection()) missing += 1;
    });
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    return {
      stop() {
        observer.disconnect();
        return missing;
      },
    };
  }

  it("al pasar al estado nuevo la marca de la nota elegida no desaparece, con el foco y la misma instancia de OSMD (#276)", async () => {
    const server = editableApi();
    renderPage();
    const region = await chooseMeasure(2);
    region.focus();
    const pending = deferred<Response>();
    server.respond(() => pending.promise);
    const watch = watchSelection();

    fireEvent.keyDown(region, { key: "ArrowUp", shiftKey: true });
    const body = server.bodies[0];
    if (!body) throw new Error("sin edición");
    pending.resolve(server.accept(body));
    expect(await screen.findByText("Re4 · blanca con puntillo")).toBeVisible();
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent("Guardado: altura Re 4.");
    });

    expect(watch.stop()).toBe(0);
    expect(selection()).not.toBeNull();
    expect(document.activeElement).toBe(region);
    // Una sola instancia de OSMD, que leyó el MusicXML del estado nuevo y lo dibujó una vez.
    expect(osmd.instances).toBe(1);
    expect(osmd.texts).toEqual(["…", "estado 1"]);
    expect(document.querySelectorAll(".notation__host svg")).toHaveLength(1);
    expect(server.bodies).toHaveLength(1);
  });

  it("una orden dada mientras se guarda la anterior espera y sale después, con el base_seq del estado nuevo (#276)", async () => {
    const server = editableApi();
    renderPage();
    const region = await chooseMeasure(2);
    const pending = deferred<Response>();
    server.respond(() => pending.promise);

    fireEvent.click(button("Subir un paso"));
    fireEvent.keyDown(region, { key: "ArrowUp", shiftKey: true });

    // No sale mientras se guarda la primera: su base_seq sería el de un estado que va a cambiar.
    expect(server.bodies).toHaveLength(1);
    expect(editStatus()).toHaveTextContent("Guardando… La orden siguiente espera su turno.");
    const body = server.bodies[0];
    if (!body) throw new Error("sin edición");
    pending.resolve(server.accept(body));

    // Se vuelve a planear sobre el estado nuevo (Re 4) y sale con su seq.
    await waitFor(() => {
      expect(server.bodies).toHaveLength(2);
    });
    expect(server.bodies[1]).toEqual({
      base_seq: 1,
      op: "SetPitch",
      anchor: anchorOf(2),
      before: null,
      after: { pitch: "E4" },
    });
    expect(await screen.findByText("Mi4 · blanca con puntillo")).toBeVisible();
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent("Guardado: altura Mi 4.");
    });
    expect(server.count(`GET /sessions/${ID}`)).toBe(1);
  });

  it("dos órdenes en el mismo instante, antes de que la vista se vuelva a pintar, no pierden la segunda", async () => {
    const server = editableApi();
    renderPage();
    const region = await chooseMeasure(2);

    // Las dos teclas llegan antes de que React vuelva a pintar la vista tras la primera.
    act(() => {
      for (let press = 0; press < 2; press += 1) {
        region.dispatchEvent(
          new KeyboardEvent("keydown", { key: "ArrowUp", shiftKey: true, bubbles: true }),
        );
      }
    });

    await waitFor(() => {
      expect(editStatus()).toHaveTextContent("Guardado: altura Mi 4.");
    });
    expect(server.bodies.map((sent) => [sent.base_seq, sent.after])).toEqual([
      [0, { pitch: "D4" }],
      [1, { pitch: "E4" }],
    ]);
  });

  it("una tercera orden mientras otra espera no se envía, y se dice", async () => {
    const server = editableApi();
    renderPage();
    await chooseMeasure(2);
    const pending = deferred<Response>();
    server.respond(() => pending.promise);

    fireEvent.click(button("Subir un paso"));
    fireEvent.click(button("Subir un paso"));
    fireEvent.click(button("Bajar un paso"));

    expect(
      screen.getByText("Ya hay una orden esperando a que se guarde la anterior: esta no se envió."),
    ).toBeInTheDocument();
    expect(editStatus()).toHaveTextContent("Guardando…");
    const body = server.bodies[0];
    if (!body) throw new Error("sin edición");
    pending.resolve(server.accept(body));
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent("Guardado: altura Mi 4.");
    });
    expect(server.bodies.map((sent) => sent.after)).toEqual([{ pitch: "D4" }, { pitch: "E4" }]);
  });

  it("si la orden en curso no se guarda, la que esperaba no se envía y se dice", async () => {
    const server = editableApi();
    renderPage();
    await chooseMeasure(2);
    const pending = deferred<Response>();
    server.respond(() => pending.promise);

    fireEvent.click(button("Subir un paso"));
    fireEvent.click(button("Negra"));
    pending.resolve(jsonResponse({ detail: "no" }, 422));

    expect(
      await screen.findByText("No se envió la orden que esperaba: la anterior no se guardó."),
    ).toBeInTheDocument();
    expect(editStatus()).toHaveTextContent(/El servidor no aceptó el cambio/);
    expect(server.bodies).toHaveLength(1);
  });

  it("tras un 409 la orden que esperaba no sale y se dice, sin reintentar ninguna", async () => {
    const server = editableApi();
    renderPage();
    await chooseMeasure(2);
    const pending = deferred<Response>();
    server.respond(() => pending.promise);

    fireEvent.click(button("Subir un paso"));
    fireEvent.click(button("Bajar un paso"));
    pending.resolve(jsonResponse({ detail: "Conflicto de secuencia" }, 409));

    expect(
      await screen.findByText("No se envió la orden que esperaba: la anterior no se guardó."),
    ).toBeInTheDocument();
    expect(editStatus()).toHaveTextContent(/La sesión cambió en otra pestaña o dispositivo/);
    expect(server.bodies).toHaveLength(1);
  });

  it("la orden que espera va a la nota elegida cuando sale, también si se eligió otra mientras se guardaba", async () => {
    const server = editableApi();
    renderPage();
    const region = await chooseMeasure(2);
    const pending = deferred<Response>();
    server.respond(() => pending.promise);

    fireEvent.click(button("Subir un paso"));
    fireEvent.click(button("Bajar un paso"));
    // Mientras se guarda, la persona elige la nota del compás 3.
    fireEvent.click(region, head(3));
    const body = server.bodies[0];
    if (!body) throw new Error("sin edición");
    pending.resolve(server.accept(body));

    await waitFor(() => {
      expect(server.bodies).toHaveLength(2);
    });
    expect(server.bodies[1]).toEqual({
      base_seq: 1,
      op: "SetPitch",
      anchor: anchorOf(3),
      before: null,
      after: { pitch: "B3" },
    });
  });

  it("una edición no corta la reproducción: el motor sigue con la partitura nueva (#276)", async () => {
    editableApi();
    renderPage();
    const play = await screen.findByRole("button", { name: "Reproducir" });
    await waitFor(() => {
      expect(play).not.toHaveAttribute("aria-disabled", "true");
    });
    await userEvent.click(play);
    const engine = () => {
      const last = audio.engines.at(-1);
      if (!last) throw new Error("no se creó el motor de audio");
      return last;
    };
    act(() => {
      engine().advance(3.5);
    });
    expect(screen.getByText("Compás 2")).toBeVisible();

    // Una corrección de altura en el compás 3 mientras suena el 2.
    await chooseMeasure(3);
    fireEvent.click(button("Subir un paso"));
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent("Guardado: altura Re 4.");
    });

    // El mismo motor, sin detenerse, con la partitura nueva; el compás que suena sigue.
    expect(audio.engines).toHaveLength(1);
    expect(engine().disposed).toBe(false);
    expect(engine().playing).toBe(true);
    expect(engine().updates).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Pausa" })).toBeVisible();
    expect(screen.getByText("Compás 2")).toBeVisible();
    act(() => {
      engine().advance(3);
    });
    expect(screen.getByText("Compás 3")).toBeVisible();
  });

  it("con el teclado: Mayús y flechas la altura, 1 a 7 la figura y + − = la alteración", async () => {
    const server = editableApi();
    renderPage();
    const region = await chooseMeasure(2);

    fireEvent.keyDown(region, { key: "ArrowUp", shiftKey: true });
    expect(await screen.findByText("Re4 · blanca con puntillo")).toBeVisible();
    fireEvent.keyDown(region, { key: "4" });
    expect(await screen.findByText("Re4 · corchea con puntillo")).toBeVisible();
    fireEvent.keyDown(region, { key: "." });
    expect(await screen.findByText("Re4 · corchea")).toBeVisible();
    fireEvent.keyDown(region, { key: "+", shiftKey: true });
    expect(await screen.findByText("Re#4 · corchea")).toBeVisible();
    fireEvent.keyDown(region, { key: "PageDown", shiftKey: true });
    expect(await screen.findByText("Re#3 · corchea")).toBeVisible();

    expect(server.bodies.map(({ base_seq, op, after }) => ({ base_seq, op, after }))).toEqual([
      { base_seq: 0, op: "SetPitch", after: { pitch: "D4" } },
      { base_seq: 1, op: "SetDuration", after: { duration_beats: "3/4" } },
      { base_seq: 2, op: "SetDuration", after: { duration_beats: "1/2" } },
      { base_seq: 3, op: "SetAccidental", after: { accidental: "#" } },
      { base_seq: 4, op: "SetPitch", after: { pitch: "D#3" } },
    ]);
    // La partitura no se volvió a montar: el foco sigue en ella y las flechas solas navegan.
    expect(document.activeElement).toBe(region);
    fireEvent.keyDown(region, { key: "ArrowRight" });
    expect(screen.getByText("Compás 3 · Voz 1")).toBeVisible();
    expect(server.bodies).toHaveLength(5);
  });

  it("los botones de figura y alteración muestran el valor de la nota elegida", async () => {
    editableApi();
    renderPage();
    await chooseMeasure(2);

    expect(button("Blanca")).toHaveAttribute("aria-pressed", "true");
    expect(button("Puntillo")).toHaveAttribute("aria-pressed", "true");
    expect(button("Negra")).toHaveAttribute("aria-pressed", "false");
    expect(button("Becuadro")).toHaveAttribute("aria-pressed", "true");
    expect(button("Sostenido")).toHaveAttribute("aria-pressed", "false");
  });

  it("sin nota elegida los controles esperan y lo dicen", async () => {
    const server = editableApi();
    renderPage();
    await findScore();

    expect(button("Subir un paso")).toHaveAttribute("aria-disabled", "true");
    expect(
      within(editor()).getByText("Elige una nota o un silencio para corregirlo."),
    ).toBeVisible();
    fireEvent.click(button("Negra"));
    expect(server.bodies).toHaveLength(0);
  });

  it("un silencio solo admite cambiar su figura", async () => {
    const start = detail();
    const rest = start.current_score?.parts[0]?.staves[0]?.measures[1]?.events[0];
    if (!rest) throw new Error("sin evento");
    Object.assign(rest, { kind: "rest", pitch: null });
    const server = editableApi(start);
    renderPage();
    const region = await chooseMeasure(2);

    expect(button("Subir un paso")).toHaveAttribute("aria-disabled", "true");
    expect(button("Sostenido")).toHaveAttribute("aria-disabled", "true");
    fireEvent.keyDown(region, { key: "ArrowUp", shiftKey: true });
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent(
        "Un silencio no tiene altura ni alteración: solo se puede cambiar su figura.",
      );
    });
    expect(server.bodies).toHaveLength(0);

    fireEvent.click(button("Negra"));
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent("Guardado: figura negra con puntillo.");
    });
    expect(server.bodies[0]).toMatchObject({
      op: "SetDuration",
      after: { duration_beats: "3/2" },
    });
  });

  it("ante un 409 recarga la sesión y avisa sin reintentar, con lo que se quería hacer", async () => {
    const server = editableApi();
    renderPage();
    await chooseMeasure(2);
    server.respond(() => {
      // Otra pestaña cambió el compás 1 mientras tanto.
      server.replace(
        apply(server.current(), {
          base_seq: 0,
          op: "SetPitch",
          anchor: anchorOf(1),
          before: null,
          after: { pitch: "E4" },
        }).next,
      );
      return jsonResponse({ detail: "Conflicto de secuencia: base_seq=0 …" }, 409);
    });

    fireEvent.click(button("Subir un paso"));

    await waitFor(() => {
      expect(editStatus()).toHaveTextContent(
        "No se guardó: altura Re 4 (compás 2, voz 1). La sesión cambió en otra pestaña o dispositivo antes de guardarlo; ya ves su estado actual.",
      );
    });
    expect(server.bodies).toHaveLength(1);
    expect(server.count(`GET /sessions/${ID}`)).toBe(2);
    expect(screen.queryByText(/Conflicto de secuencia/)).toBeNull();
    // Se ve el estado nuevo y la nota elegida sigue elegida en él.
    expect(screen.getByText("Ediciones").nextElementSibling).toHaveTextContent("1");
    expect(useSelectionStore.getState().selection).toMatchObject({ seq: 1, anchor: anchorOf(2) });
    expect(screen.getByText("Do4 · blanca con puntillo")).toBeVisible();

    // Volver a aplicarlo es otra edición, sobre el estado nuevo, y solo si la persona lo pide.
    fireEvent.click(within(editor()).getByRole("button", { name: "Volver a aplicar" }));
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent("Guardado: altura Re 4.");
    });
    expect(server.bodies[1]).toMatchObject({
      base_seq: 1,
      op: "SetPitch",
      anchor: anchorOf(2),
      after: { pitch: "D4" },
    });
  });

  it("no ofrece volver a aplicar lo que la nota ya tiene tras recargar", async () => {
    const server = editableApi();
    renderPage();
    await chooseMeasure(2);
    server.respond((body) => {
      server.replace(apply(server.current(), body).next);
      return jsonResponse({ detail: "conflicto" }, 409);
    });

    fireEvent.click(button("Subir un paso"));

    await waitFor(() => {
      expect(editStatus()).toHaveTextContent(/No se guardó: altura Re 4/);
    });
    expect(within(editor()).queryByRole("button", { name: "Volver a aplicar" })).toBeNull();
    expect(editStatus()).toHaveTextContent("La nota ya tiene ese valor.");
  });

  it("si el 409 es porque la sesión está finalizada, lo dice y la deja en solo lectura", async () => {
    const server = editableApi();
    renderPage();
    await chooseMeasure(2);
    server.respond(() => {
      server.replace({ ...server.current(), status: "finalized" });
      return jsonResponse({ detail: "La sesión está cerrada" }, 409);
    });

    fireEvent.click(button("Subir un paso"));

    await waitFor(() => {
      expect(editStatus()).toHaveTextContent(
        "No se guardó: altura Re 4 (compás 2, voz 1). La sesión está finalizada y ya no admite correcciones.",
      );
    });
    expect(within(editor()).queryByRole("button", { name: "Subir un paso" })).toBeNull();
    expect(screen.getByText(/sesión finalizada: solo lectura/i)).toBeVisible();
    expect(server.bodies).toHaveLength(1);
  });

  it("un 422 no guarda nada y lo dice con un mensaje propio, sin el detail", async () => {
    const server = editableApi();
    renderPage();
    await chooseMeasure(2);
    server.respond(() =>
      jsonResponse({ detail: "Contenido de 'after' no válido para SetPitch: …" }, 422),
    );

    fireEvent.click(button("Subir un paso"));

    await waitFor(() => {
      expect(editStatus()).toHaveTextContent(
        "El servidor no aceptó el cambio (altura Re 4, compás 2, voz 1): no se guardó nada.",
      );
    });
    expect(screen.queryByText(/Contenido de 'after'/)).toBeNull();
    expect(screen.getByText("Do4 · blanca con puntillo")).toBeVisible();
    expect(server.count(`GET /sessions/${ID}`)).toBe(1);
    // Se puede seguir corrigiendo sobre el mismo estado.
    expect(button("Subir un paso")).toHaveAttribute("aria-disabled", "false");
  });

  it("pone y quita articulaciones y el calderón con botones y teclas (#214)", async () => {
    const server = editableApi();
    renderPage();
    const region = await chooseMeasure(2);

    expect(button("Acento")).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(button("Acento"));
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent("Guardado: acento en Do 4.");
    });
    expect(button("Acento")).toHaveAttribute("aria-pressed", "true");
    fireEvent.keyDown(region, { key: "c" });
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent("Guardado: calderón en Do 4.");
    });
    fireEvent.keyDown(region, { key: "a" });
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent("Guardado: sin acento en Do 4.");
    });

    expect(server.bodies).toEqual([
      {
        base_seq: 0,
        op: "SetNoteMarks",
        anchor: anchorOf(2),
        before: null,
        after: { articulations: ["accent"], fermata: false },
      },
      {
        base_seq: 1,
        op: "SetNoteMarks",
        anchor: anchorOf(2),
        before: null,
        after: { articulations: ["accent"], fermata: true },
      },
      {
        base_seq: 2,
        op: "SetNoteMarks",
        anchor: anchorOf(2),
        before: null,
        after: { articulations: [], fermata: true },
      },
    ]);
    expect(button("Calderón")).toHaveAttribute("aria-pressed", "true");
    // Las marcas no mueven la nota elegida ni el foco.
    expect(document.activeElement).toBe(region);
    expect(useSelectionStore.getState().selection).toMatchObject({ seq: 3, anchor: anchorOf(2) });
  });

  it("pone y quita la dinámica de la posición elegida con el desplegable (#214)", async () => {
    const server = editableApi();
    renderPage();
    await chooseMeasure(2);
    const picker = within(editor()).getByRole("combobox", { name: "Dinámica" });

    expect(picker).toHaveValue("");
    expect(button("Poner dinámica")).toHaveAttribute("aria-disabled", "true");
    fireEvent.change(picker, { target: { value: "mf" } });
    fireEvent.click(button("Poner dinámica"));
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent("Guardado: dinámica mf en la nota del compás 2.");
    });
    expect(picker).toHaveValue("mf");
    fireEvent.change(picker, { target: { value: "" } });
    fireEvent.click(button("Quitar dinámica"));
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent(
        "Guardado: sin la dinámica mf en la nota del compás 2.",
      );
    });
    expect(
      server.bodies.map(({ base_seq, op, anchor, after }) => ({ base_seq, op, anchor, after })),
    ).toEqual([
      {
        base_seq: 0,
        op: "SetDynamic",
        anchor: anchorOf(2),
        after: { offset_beats: "0", mark: "mf" },
      },
      {
        base_seq: 1,
        op: "SetDynamic",
        anchor: anchorOf(2),
        after: { offset_beats: "0", mark: null },
      },
    ]);
  });

  it("crea una ligadura y un regulador desde el inicio marcado y los quita enteros (#214)", async () => {
    const server = editableApi();
    renderPage();
    const region = await chooseMeasure(1);

    // Sin inicio no se crea nada, y se dice cómo.
    fireEvent.keyDown(region, { key: "l" });
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent(/Marca antes el inicio/);
    });
    fireEvent.keyDown(region, { key: "i" });
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent("Inicio: Do 4, blanca con puntillo (compás 1).");
    });
    expect(button("Inicio de la ligadura o el regulador")).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(region, head(3));
    fireEvent.click(button("Ligadura de expresión hasta aquí"));
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent(
        "Guardado: ligadura de expresión de los compases 1 a 3.",
      );
    });
    // Creada la ligadura, el inicio se olvida.
    expect(button("Inicio de la ligadura o el regulador")).toHaveAttribute("aria-pressed", "false");

    // Un regulador sobre una sola nota (del compás 3), con el teclado.
    fireEvent.keyDown(region, { key: "i" });
    fireEvent.keyDown(region, { key: "<" });
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent("Guardado: crescendo en el compás 3.");
    });

    const removeSlur = button("Quitar la ligadura de expresión de los compases 1 a 3");
    removeSlur.focus();
    fireEvent.click(removeSlur);
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent(
        "Guardado: quitar la ligadura de expresión de los compases 1 a 3.",
      );
    });
    // El botón se va con la ligadura: el foco pasa a la partitura, no se queda en el documento.
    expect(document.activeElement).toBe(region);
    fireEvent.click(button("Quitar el crescendo en el compás 3"));
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent("Guardado: quitar el crescendo en el compás 3.");
    });

    const slot = (measureNumber: number) => ({
      staff: 0,
      measure: measureNumber,
      voice: 0,
      event_index: 0,
    });
    expect(
      server.bodies.map(({ base_seq, op, anchor, after }) => ({ base_seq, op, anchor, after })),
    ).toEqual([
      {
        base_seq: 0,
        op: "SetSlur",
        anchor: anchorOf(1),
        after: { number: 1, start: slot(1), stop: slot(3) },
      },
      {
        base_seq: 1,
        op: "SetWedge",
        anchor: anchorOf(3),
        after: {
          number: 1,
          start: { staff: 0, measure: 3, offset_beats: "0", type: "crescendo" },
          stop: { staff: 0, measure: 3, offset_beats: "3" },
        },
      },
      {
        base_seq: 2,
        op: "SetSlur",
        anchor: anchorOf(1),
        after: { number: 1, start: null, stop: null },
      },
      {
        base_seq: 3,
        op: "SetWedge",
        anchor: anchorOf(3),
        after: { number: 1, start: null, stop: null },
      },
    ]);
    expect(server.current().current_score?.parts[0]?.staves[0]?.measures[2]?.wedges).toEqual([]);
  });

  it("un inicio marcado mientras se guarda una ligadura no se olvida al guardarla (#214)", async () => {
    const server = editableApi();
    renderPage();
    const region = await chooseMeasure(1);
    fireEvent.keyDown(region, { key: "i" });
    fireEvent.click(region, head(2));
    const pending = deferred<Response>();
    server.respond(() => pending.promise);
    fireEvent.keyDown(region, { key: "l" });
    // Mientras se guarda, otro inicio: el del compás 2.
    fireEvent.keyDown(region, { key: "i" });
    const body = server.bodies[0];
    if (!body) throw new Error("sin edición");
    pending.resolve(server.accept(body));
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent(
        "Guardado: ligadura de expresión de los compases 1 a 2.",
      );
    });
    expect(button("Inicio de la ligadura o el regulador")).toHaveAttribute("aria-pressed", "true");
    expect(
      within(editor()).getByText("Inicio: Do 4, blanca con puntillo (compás 2)."),
    ).toBeVisible();
  });

  it("una marca rechazada (422) o que llega tarde (409) se dice como las demás correcciones (#214)", async () => {
    const server = editableApi();
    renderPage();
    await chooseMeasure(2);
    server.respond(() => jsonResponse({ detail: "Contenido de 'after' no válido" }, 422));

    fireEvent.click(button("Tenuto"));
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent(
        "El servidor no aceptó el cambio (tenuto en Do 4, compás 2, voz 1): no se guardó nada.",
      );
    });

    server.respond(() => {
      // Otra pestaña cambió el compás 1 mientras tanto.
      server.replace(
        apply(server.current(), {
          base_seq: 0,
          op: "SetPitch",
          anchor: anchorOf(1),
          before: null,
          after: { pitch: "E4" },
        }).next,
      );
      return jsonResponse({ detail: "Conflicto" }, 409);
    });
    fireEvent.click(button("Tenuto"));
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent(
        "No se guardó: tenuto en Do 4 (compás 2, voz 1). La sesión cambió en otra pestaña o dispositivo antes de guardarlo; ya ves su estado actual.",
      );
    });
    fireEvent.click(within(editor()).getByRole("button", { name: "Volver a aplicar" }));
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent("Guardado: tenuto en Do 4.");
    });
    expect(server.bodies.at(-1)).toMatchObject({
      base_seq: 1,
      op: "SetNoteMarks",
      anchor: anchorOf(2),
      after: { articulations: ["tenuto"], fermata: false },
    });
  });

  it("deshacer una marca la quita con la compensatoria del servidor (#214)", async () => {
    const server = editableApi();
    renderPage();
    await chooseMeasure(2);
    fireEvent.click(button("Marcato"));
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent("Guardado: marcato en Do 4.");
    });

    fireEvent.click(within(editor()).getByRole("button", { name: "Deshacer" }));
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent("Deshecho: marcato (compás 2, voz 1).");
    });
    expect(button("Marcato")).toHaveAttribute("aria-pressed", "false");
    expect(server.undoBodies).toEqual([{ base_seq: 1 }]);
  });

  it("un 403 lo dice sin guardar nada", async () => {
    const server = editableApi();
    renderPage();
    await chooseMeasure(2);
    server.respond(() => jsonResponse({ detail: "Un investigador solo puede editar…" }, 403));

    fireEvent.click(button("Subir un paso"));

    await waitFor(() => {
      expect(editStatus()).toHaveTextContent(
        "No se guardó: solo la persona que hizo la transcripción puede corregirla.",
      );
    });
    expect(screen.getByText("Do4 · blanca con puntillo")).toBeVisible();
  });

  it("sin respuesta del servidor no da nada por guardado y pide recargar antes de seguir", async () => {
    const server = editableApi();
    renderPage();
    await chooseMeasure(2);
    server.respond(() => Promise.reject(new TypeError("Failed to fetch")));

    fireEvent.click(button("Subir un paso"));

    await waitFor(() => {
      expect(editStatus()).toHaveTextContent(
        "No hubo respuesta del servidor: puede que el cambio (altura Re 4, compás 2, voz 1) no se guardara. Recarga la sesión para comprobarlo.",
      );
    });
    // Sin saber en qué estado quedó, no se edita encima.
    expect(button("Subir un paso")).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(button("Bajar un paso"));
    expect(server.bodies).toHaveLength(1);

    fireEvent.click(within(editor()).getByRole("button", { name: "Recargar la sesión" }));
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent("Sesión recargada.");
    });
    expect(server.count(`GET /sessions/${ID}`)).toBe(2);
    expect(button("Subir un paso")).toHaveAttribute("aria-disabled", "false");
  });

  it("si se guarda pero no se puede cargar el estado nuevo, lo dice y pide recargar", async () => {
    const server = editableApi();
    renderPage();
    await chooseMeasure(2);
    // El 201 no trae el estado nuevo y el detalle falla al pedirlo.
    server.respond((body) => {
      const response = server.acceptBare(body);
      server.detailRoute(() => jsonResponse({ detail: "fallo" }, 500));
      return response;
    });

    fireEvent.click(button("Subir un paso"));

    await waitFor(() => {
      expect(editStatus()).toHaveTextContent(
        "Se guardó el cambio (altura Re 4, compás 2, voz 1), pero no se pudo cargar la partitura nueva. Recarga la sesión para seguir corrigiendo.",
      );
    });
    expect(button("Subir un paso")).toHaveAttribute("aria-disabled", "true");

    server.detailRoute(null);
    fireEvent.click(within(editor()).getByRole("button", { name: "Recargar la sesión" }));
    expect(await screen.findByText("Re4 · blanca con puntillo")).toBeVisible();
  });

  it("un investigador ve en solo lectura una sesión ajena", async () => {
    const server = editableApi(detail({ owner_id: LUIS.id }));
    renderPage(INVESTIGADORA);
    const region = await chooseMeasure(2);

    expect(screen.queryByRole("region", { name: "Corregir la nota elegida" })).toBeNull();
    expect(screen.getByText(/solo lectura/i)).toBeVisible();
    fireEvent.keyDown(region, { key: "ArrowUp", shiftKey: true });
    fireEvent.keyDown(region, { key: "4" });
    expect(server.bodies).toHaveLength(0);
  });

  it("un investigador corrige sus propias sesiones", async () => {
    editableApi(detail({ owner_id: INVESTIGADORA.id }));
    renderPage(INVESTIGADORA);
    await chooseMeasure(2);

    expect(editor()).toBeVisible();
    expect(screen.queryByText(/solo lectura/i)).toBeNull();
  });

  it("una sesión finalizada es de solo lectura", async () => {
    const server = editableApi(detail({ status: "finalized" }));
    renderPage();
    const region = await chooseMeasure(2);

    expect(screen.queryByRole("region", { name: "Corregir la nota elegida" })).toBeNull();
    expect(screen.getByText(/sesión finalizada: solo lectura/i)).toBeVisible();
    fireEvent.keyDown(region, { key: "ArrowUp", shiftKey: true });
    expect(server.bodies).toHaveLength(0);
  });

  it("tras «Volver a aplicar», que desaparece al enviarse, el foco pasa a la partitura", async () => {
    const server = editableApi();
    renderPage();
    const region = await chooseMeasure(2);
    server.respond((body) => {
      server.replace(
        apply(server.current(), { ...body, anchor: anchorOf(1), after: { pitch: "E4" } }).next,
      );
      return jsonResponse({ detail: "conflicto" }, 409);
    });
    fireEvent.click(button("Subir un paso"));
    const again = await within(editor()).findByRole("button", { name: "Volver a aplicar" });
    again.focus();

    fireEvent.click(again);

    await waitFor(() => {
      expect(editStatus()).toHaveTextContent("Guardado: altura Re 4.");
    });
    expect(within(editor()).queryByRole("button", { name: "Volver a aplicar" })).toBeNull();
    expect(document.activeElement).toBe(region);
  });

  it("si el 409 deja la sesión finalizada, el foco del botón que se va pasa a la partitura", async () => {
    const server = editableApi();
    renderPage();
    const region = await chooseMeasure(2);
    server.respond(() => {
      server.replace({ ...server.current(), status: "finalized" });
      return jsonResponse({ detail: "cerrada" }, 409);
    });
    const up = button("Subir un paso");
    up.focus();

    fireEvent.click(up);

    await waitFor(() => {
      expect(editStatus()).toHaveTextContent(/está finalizada/);
    });
    expect(document.activeElement).toBe(region);
  });

  it("un rechazo no borra el aviso de un 409 ni lo que se puede volver a aplicar", async () => {
    const server = editableApi();
    renderPage();
    await chooseMeasure(2);
    server.respond((body) => {
      server.replace(
        apply(server.current(), { ...body, anchor: anchorOf(1), after: { pitch: "E4" } }).next,
      );
      return jsonResponse({ detail: "conflicto" }, 409);
    });
    fireEvent.click(button("Subir un paso"));
    await within(editor()).findByRole("button", { name: "Volver a aplicar" });

    // La nota ya es blanca con puntillo: pulsar «Blanca» no envía nada y lo dice aparte.
    fireEvent.click(button("Blanca"));

    expect(document.querySelector(".editor__refusal")).toHaveTextContent(
      "La nota ya tiene ese valor.",
    );
    expect(editStatus()).toHaveTextContent(/No se guardó: altura Re 4/);
    expect(within(editor()).getByRole("button", { name: "Volver a aplicar" })).toBeVisible();
    expect(server.bodies).toHaveLength(1);
  });

  it("un rechazo repetido se vuelve a anunciar", async () => {
    editableApi();
    renderPage();
    const region = await chooseMeasure(2);

    fireEvent.click(button("Blanca"));
    const first = editStatus()?.textContent;
    fireEvent.keyDown(region, { key: "6" });
    const second = editStatus()?.textContent;

    expect(first?.trim()).toBe("La nota ya tiene ese valor.");
    expect(second?.trim()).toBe("La nota ya tiene ese valor.");
    expect(second).not.toBe(first);
  });

  it("mantener una tecla pulsada no encadena ediciones", async () => {
    const server = editableApi();
    renderPage();
    const region = await chooseMeasure(2);

    fireEvent.keyDown(region, { key: "ArrowUp", shiftKey: true, repeat: true });
    expect(server.bodies).toHaveLength(0);
    fireEvent.keyDown(region, { key: "ArrowUp", shiftKey: true });
    expect(server.bodies).toHaveLength(1);
    expect(await screen.findByText("Re4 · blanca con puntillo")).toBeVisible();
  });

  it("un 5xx dice que el servidor no confirmó el cambio y pide recargar", async () => {
    const server = editableApi();
    renderPage();
    await chooseMeasure(2);
    server.respond(() => jsonResponse({ detail: "fallo interno" }, 500));

    fireEvent.click(button("Subir un paso"));

    await waitFor(() => {
      expect(editStatus()).toHaveTextContent(
        "El servidor no confirmó el cambio (altura Re 4, compás 2, voz 1): puede que no se guardara. Recarga la sesión para comprobarlo.",
      );
    });
    expect(button("Subir un paso")).toHaveAttribute("aria-disabled", "true");
    expect(within(editor()).getByRole("button", { name: "Recargar la sesión" })).toBeVisible();
  });

  it("tras un 403 no deja seguir enviando ediciones", async () => {
    const server = editableApi();
    renderPage();
    await chooseMeasure(2);
    server.respond(() => jsonResponse({ detail: "no" }, 403));

    fireEvent.click(button("Subir un paso"));
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent(/solo la persona que hizo la transcripción/);
    });

    expect(button("Bajar un paso")).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(button("Bajar un paso"));
    expect(server.bodies).toHaveLength(1);
  });

  it("un 404 lleva a la sesión no encontrada", async () => {
    const server = editableApi();
    renderPage();
    await chooseMeasure(2);
    server.respond(() => {
      server.detailRoute(() => jsonResponse({ detail: "Sesión no encontrada" }, 404));
      return jsonResponse({ detail: "Sesión no encontrada" }, 404);
    });

    fireEvent.click(button("Subir un paso"));

    expect(await screen.findByRole("heading", { name: "Sesión no encontrada" })).toBeVisible();
  });

  it("si tras un 409 no se puede cargar el estado actual, lo dice y pide recargar", async () => {
    const server = editableApi();
    renderPage();
    await chooseMeasure(2);
    server.respond(() => {
      server.detailRoute(() => Promise.reject(new TypeError("Failed to fetch")));
      return jsonResponse({ detail: "conflicto" }, 409);
    });

    fireEvent.click(button("Subir un paso"));

    await waitFor(() => {
      expect(editStatus()).toHaveTextContent(
        "No se guardó: altura Re 4 (compás 2, voz 1). La sesión cambió antes de guardarlo y no se pudo cargar su estado actual: recárgala para seguir.",
      );
    });
    expect(button("Subir un paso")).toHaveAttribute("aria-disabled", "true");

    // La recarga vuelve a fallar: lo dice y el botón sigue.
    fireEvent.click(within(editor()).getByRole("button", { name: "Recargar la sesión" }));
    await waitFor(() => {
      expect(editStatus()).toHaveTextContent(
        "No se pudo recargar la sesión. Comprueba la conexión e inténtalo de nuevo.",
      );
    });
    expect(within(editor()).getByRole("button", { name: "Recargar la sesión" })).toBeVisible();
    expect(server.bodies).toHaveLength(1);
  });

  it("tras un 409 por una inserción delante, vuelve a aplicar sobre el ancla desplazada", async () => {
    const server = editableApi();
    renderPage();
    await chooseMeasure(2);
    server.respond(() => {
      // Otra pestaña insertó una nota delante de la elegida (ADR-0011 §2: la retrasa una).
      const next = structuredClone(server.current());
      next.current_score?.parts[0]?.staves[0]?.measures[1]?.events.unshift({
        kind: "note",
        voice: 0,
        pitch: "E4",
        duration_beats: "1",
        tie: null,
        is_chord: false,
        bbox: null,
        confidence: null,
        ir_handle: null,
      });
      next.current_seq = 1;
      next.edits = [
        {
          id: "otra",
          session_id: ID,
          seq: 1,
          op: "InsertEvent",
          author: "ana",
          anchor: anchorOf(2),
          before: null,
          after: { kind: "note", pitch: "E4", duration_beats: "1" },
          created_at: "2026-10-24T10:00:00Z",
        },
      ];
      server.replace(next);
      return jsonResponse({ detail: "conflicto" }, 409);
    });

    fireEvent.click(button("Subir un paso"));
    fireEvent.click(await within(editor()).findByRole("button", { name: "Volver a aplicar" }));

    await waitFor(() => {
      expect(server.bodies).toHaveLength(2);
    });
    expect(server.bodies[1]).toMatchObject({
      base_seq: 1,
      anchor: { measure: 2, event_index: 1 },
      after: { pitch: "D4" },
    });
  });

  it("tras un 409 que borró la nota elegida, lo dice y no ofrece volver a aplicar", async () => {
    const server = editableApi();
    renderPage();
    await chooseMeasure(2);
    server.respond(() => {
      const next = structuredClone(server.current());
      const measure = next.current_score?.parts[0]?.staves[0]?.measures[1];
      if (measure) measure.events = [];
      next.current_seq = 1;
      next.edits = [
        {
          id: "otra",
          session_id: ID,
          seq: 1,
          op: "DeleteEvent",
          author: "ana",
          anchor: anchorOf(2),
          before: null,
          after: null,
          created_at: "2026-10-24T10:00:00Z",
        },
      ];
      server.replace(next);
      return jsonResponse({ detail: "conflicto" }, 409);
    });

    fireEvent.click(button("Subir un paso"));

    await waitFor(() => {
      expect(editStatus()).toHaveTextContent(
        "La nota que elegiste ya no está en el mismo sitio: elígela de nuevo si sigue haciendo falta.",
      );
    });
    expect(within(editor()).queryByRole("button", { name: "Volver a aplicar" })).toBeNull();
    expect(useSelectionStore.getState().selection).toBeNull();
  });

  it("al salir de la vista con una edición en curso, la cancela y no pide nada más", async () => {
    const server = editableApi();
    const router = renderPage();
    await chooseMeasure(2);
    let signal: AbortSignal | null | undefined;
    server.respond(() => {
      const call = server.calls.at(-1);
      signal = call?.init?.signal;
      return hangUntilAborted(call?.init);
    });

    fireEvent.click(button("Subir un paso"));
    await router.navigate("/transcripcion");

    await waitFor(() => {
      expect(signal?.aborted).toBe(true);
    });
    expect(server.count(`GET /sessions/${ID}`)).toBe(1);
  });

  describe("insertar, borrar y cambiar la clave y la armadura (#184)", () => {
    const live = () => document.querySelector(".selection [role='status']");
    const note = (
      pitch: string | null,
      duration: string,
      changes: Partial<ScoreEventPayload> = {},
    ) =>
      ({
        kind: pitch === null ? "rest" : "note",
        voice: 0,
        pitch,
        duration_beats: duration,
        tie: null,
        is_chord: false,
        bbox: null,
        confidence: null,
        ir_handle: null,
        ...changes,
      }) satisfies ScoreEventPayload;
    /** Detalle con los eventos dados en el compás 2. */
    function withSecond(events: ScoreEventPayload[]) {
      const start = detail();
      const second = start.current_score?.parts[0]?.staves[0]?.measures[1];
      if (!second) throw new Error("sin compás 2");
      second.events = events;
      return start;
    }

    it("inserta una nota antes de la elegida, sin darla por insertada antes del 201, y la elige", async () => {
      const server = editableApi();
      renderPage();
      await chooseMeasure(2);
      const pending = deferred<Response>();
      server.respond(() => pending.promise);

      fireEvent.click(button("Insertar una nota antes"));

      expect(server.bodies).toEqual([
        {
          base_seq: 0,
          op: "InsertEvent",
          anchor: anchorOf(2),
          before: null,
          after: { kind: "note", duration_beats: "3", pitch: "C4" },
        },
      ]);
      expect(editStatus()).toHaveTextContent("Guardando…");
      // Sin el 201 la vista no da nada por insertado: el mismo dibujo, el mismo estado.
      const figures = () => document.querySelectorAll(".notation__host .vf-stavenote").length;
      expect(figures()).toBe(3);
      expect(useSelectionStore.getState().selection).toMatchObject({ seq: 0 });
      expect(screen.getByText("Ediciones").nextElementSibling).toHaveTextContent("0");
      expect(server.count(`GET /sessions/${ID}`)).toBe(1);

      const body = server.bodies[0];
      if (!body) throw new Error("sin edición");
      pending.resolve(server.accept(body));

      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Guardado: inserción de Do 4, blanca con puntillo.");
      });
      expect(useSelectionStore.getState().selection).toEqual({
        sessionId: ID,
        seq: 1,
        anchor: anchorOf(2),
        placedBy: 1,
      });
      // El compás 2 dibuja ya las dos notas y la marca está sobre la nueva, la primera.
      await waitFor(() => {
        expect(selection()).not.toBeNull();
      });
      expect(figures()).toBe(4);
      expect(screen.getByText("Ediciones").nextElementSibling).toHaveTextContent("1");
      // La primera figura del compás 2 empieza en x = 35 unidades; la segunda, en 40.
      expect(Number.parseFloat(selection()?.style.left ?? "")).toBeLessThan(37 * 7.5);
    });

    it("al insertar, la marca de la nota elegida no desaparece y pasa a la nota insertada (#276)", async () => {
      editableApi();
      renderPage();
      await chooseMeasure(2);
      const before = selection()?.style.left;
      const watch = watchSelection();

      fireEvent.click(button("Insertar una nota antes"));
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Guardado: inserción de Do 4, blanca con puntillo.");
      });

      expect(watch.stop()).toBe(0);
      // Ahora marca la nota insertada, que ocupa el sitio de la que estaba elegida.
      expect(selection()?.style.left).toBe(before);
      expect(useSelectionStore.getState().selection).toMatchObject({ seq: 1, placedBy: 1 });
      expect(document.querySelectorAll(".notation__host .vf-stavenote")).toHaveLength(4);
    });

    it("con el teclado: N inserta una nota, S un silencio, y Supr y Retroceso borran", async () => {
      const server = editableApi();
      renderPage();
      const region = await chooseMeasure(2);

      fireEvent.keyDown(region, { key: "s" });
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent(
          "Guardado: inserción de un silencio de blanca con puntillo.",
        );
      });
      expect(screen.getByText("Silencio de blanca con puntillo")).toBeVisible();

      fireEvent.keyDown(region, { key: "Delete" });
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent(
          "Guardado: borrado de un silencio de blanca con puntillo.",
        );
      });
      expect(screen.getByText("Do4 · blanca con puntillo")).toBeVisible();

      fireEvent.keyDown(region, { key: "N", shiftKey: true });
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Guardado: inserción de Do 4, blanca con puntillo.");
      });
      fireEvent.keyDown(region, { key: "Backspace" });
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Guardado: borrado de Do 4, blanca con puntillo.");
      });

      expect(server.bodies.map(({ op, base_seq }) => [op, base_seq])).toEqual([
        ["InsertEvent", 0],
        ["DeleteEvent", 1],
        ["InsertEvent", 2],
        ["DeleteEvent", 3],
      ]);
      expect(server.bodies[0]?.after).toEqual({ kind: "rest", duration_beats: "3" });
      expect(document.activeElement).toBe(region);
      // Con Ctrl, ⌘ o Alt no es de la vista.
      fireEvent.keyDown(region, { key: "Backspace", altKey: true });
      fireEvent.keyDown(region, { key: "n", ctrlKey: true });
      expect(server.bodies).toHaveLength(4);
    });

    it("al borrar deja elegido el evento que ocupa su sitio y lo anuncia", async () => {
      const server = editableApi(withSecond([note("C4", "3/2"), note("D4", "3/2")]));
      renderPage();
      await chooseMeasure(2);
      expect(screen.getByText("Do4 · negra con puntillo")).toBeVisible();

      fireEvent.click(button("Borrar"));

      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Guardado: borrado de Do 4, negra con puntillo.");
      });
      expect(server.bodies[0]).toEqual({
        base_seq: 0,
        op: "DeleteEvent",
        anchor: anchorOf(2),
        before: null,
        after: null,
      });
      expect(useSelectionStore.getState().selection).toMatchObject({
        seq: 1,
        anchor: anchorOf(2),
        placedBy: 1,
      });
      expect(screen.getByText("Re4 · negra con puntillo")).toBeVisible();
      // Con la misma ancla es otro evento: se anuncia.
      await waitFor(() => {
        expect(live()).toHaveTextContent("Compás 2, voz 1: Re 4, negra con puntillo.");
      });
    });

    it("si se elige otra nota mientras se guarda el borrado, se respeta", async () => {
      const server = editableApi(withSecond([note("C4", "3/2"), note("D4", "3/2")]));
      renderPage();
      const region = await chooseMeasure(2);
      const pending = deferred<Response>();
      server.respond(() => pending.promise);

      fireEvent.click(button("Borrar"));
      fireEvent.keyDown(region, { key: "ArrowLeft" });
      expect(screen.getByText("Compás 1 · Voz 1")).toBeVisible();
      const body = server.bodies[0];
      if (!body) throw new Error("sin edición");
      pending.resolve(server.accept(body));

      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Guardado: borrado de Do 4, negra con puntillo.");
      });
      expect(useSelectionStore.getState().selection).toMatchObject({
        seq: 1,
        anchor: anchorOf(1),
      });
    });

    it("no borra la primera nota de un acorde y dice por qué", async () => {
      const server = editableApi(
        withSecond([note("C4", "3"), note("E4", "3", { is_chord: true })]),
      );
      renderPage();
      const region = await chooseMeasure(2);
      expect(screen.getByText("Do4 · blanca con puntillo")).toBeVisible();

      expect(button("Borrar")).toHaveAttribute("aria-disabled", "true");
      fireEvent.click(button("Borrar"));
      fireEvent.keyDown(region, { key: "Delete" });
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent(
          "La primera nota de un acorde lleva su figura y sus marcas: borra antes las demás notas del acorde.",
        );
      });
      expect(server.bodies).toHaveLength(0);

      // Mi4, la otra nota del acorde, sí se borra.
      fireEvent.click(region, { clientX: 35 * 7.5, clientY: 6 * 7.5 });
      expect(screen.getByText("Mi4 · blanca con puntillo")).toBeVisible();
      fireEvent.click(button("Borrar"));
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Guardado: borrado de Mi 4, blanca con puntillo.");
      });
      expect(server.bodies[0]).toMatchObject({ op: "DeleteEvent", anchor: { event_index: 1 } });
    });

    it("insertar ante una nota de un acorde inserta antes del acorde entero", async () => {
      const server = editableApi(
        withSecond([note("C4", "3"), note("E4", "3", { is_chord: true })]),
      );
      renderPage();
      const region = await chooseMeasure(2);
      fireEvent.click(region, { clientX: 35 * 7.5, clientY: 6 * 7.5 });

      fireEvent.click(button("Insertar un silencio antes"));

      await waitFor(() => {
        expect(server.bodies).toHaveLength(1);
      });
      expect(server.bodies[0]).toMatchObject({
        op: "InsertEvent",
        anchor: { measure: 2, event_index: 0 },
        after: { kind: "rest", duration_beats: "3" },
      });
    });

    it("al borrar una nota con ligadura de expresión dice que la ligadura ya no se dibuja", async () => {
      const start = withSecond([note("C4", "3", { slurs: [{ type: "start", number: 1 }] })]);
      const third = start.current_score?.parts[0]?.staves[0]?.measures[2]?.events[0];
      if (!third) throw new Error("sin compás 3");
      third.slurs = [{ type: "stop", number: 1 }];
      editableApi(start);
      renderPage();
      await chooseMeasure(2);

      fireEvent.click(button("Borrar"));

      await waitFor(() => {
        expect(editStatus()).toHaveTextContent(
          "Guardado: borrado de Do 4, blanca con puntillo. Su ligadura de expresión ya no se dibuja.",
        );
      });
    });

    it("en una voz secundaria inserta tras su hueco, antes de la nota elegida (ADR-0032)", async () => {
      const server = editableApi(
        withSecond([
          note("E5", "3"),
          note(null, "1", { voice: 1, hidden: true }),
          note("C4", "2", { voice: 1 }),
        ]),
      );
      renderPage();
      const region = await chooseMeasure(2);
      fireEvent.keyDown(region, { key: "ArrowDown" });
      expect(screen.getByText("Compás 2 · Voz 2")).toBeVisible();

      fireEvent.keyDown(region, { key: "n" });

      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Guardado: inserción de Do 4, blanca.");
      });
      expect(server.bodies[0]).toMatchObject({
        op: "InsertEvent",
        anchor: { measure: 2, voice: 1, event_index: 1 },
        after: { kind: "note", pitch: "C4", duration_beats: "2" },
      });
      expect(useSelectionStore.getState().selection).toMatchObject({
        anchor: { measure: 2, voice: 1, event_index: 1 },
      });
    });

    it("cambia la clave del compás elegido, dice hasta dónde llega y que las notas no cambian", async () => {
      const server = editableApi();
      renderPage();
      await chooseMeasure(2);
      expect(button("Clave de sol")).toHaveAttribute("aria-pressed", "true");
      expect(within(editor()).getByText("Clave · compases 2 a 3")).toBeVisible();

      fireEvent.click(button("Clave de fa"));

      await waitFor(() => {
        expect(editStatus()).toHaveTextContent(
          "Guardado: clave de fa en los compases 2 a 3. Las notas conservan su altura.",
        );
      });
      expect(server.bodies[0]).toEqual({
        base_seq: 0,
        op: "SetClef",
        anchor: anchorOf(2),
        before: null,
        after: { sign: "F", line: 4 },
      });
      expect(button("Clave de fa")).toHaveAttribute("aria-pressed", "true");
      expect(button("Clave de sol")).toHaveAttribute("aria-pressed", "false");
      // La nota elegida sigue elegida, con su altura.
      expect(useSelectionStore.getState().selection).toMatchObject({ seq: 1, anchor: anchorOf(2) });
      expect(screen.getByText("Do4 · blanca con puntillo")).toBeVisible();
    });

    it("cambia la armadura con el desplegable y «Cambiar armadura»", async () => {
      const server = editableApi();
      renderPage();
      await chooseMeasure(2);
      const picker = within(editor()).getByRole("combobox", { name: "Armadura · compases 2 a 3" });
      expect(picker).toHaveValue("0");
      expect(button("Cambiar armadura")).toHaveAttribute("aria-disabled", "true");
      fireEvent.click(button("Cambiar armadura"));
      expect(server.bodies).toHaveLength(0);

      fireEvent.change(picker, { target: { value: "2" } });
      expect(button("Cambiar armadura")).toHaveAttribute("aria-disabled", "false");
      button("Cambiar armadura").focus();
      fireEvent.click(button("Cambiar armadura"));

      await waitFor(() => {
        expect(editStatus()).toHaveTextContent(
          "Guardado: armadura de 2 sostenidos en los compases 2 a 3. Las notas conservan su altura.",
        );
      });
      expect(server.bodies[0]).toMatchObject({
        op: "SetKey",
        anchor: anchorOf(2),
        after: { fifths: 2 },
      });
      expect(
        within(editor()).getByRole("combobox", { name: "Armadura · compases 2 a 3" }),
      ).toHaveValue("2");
      expect(button("Cambiar armadura")).toHaveAttribute("aria-disabled", "true");
      // El botón no se monta de nuevo al cambiar la armadura: el foco sigue en él.
      expect(document.activeElement).toBe(button("Cambiar armadura"));
    });

    it("lo propuesto en el desplegable se olvida al pasar a otro compás, también al volver", async () => {
      const server = editableApi();
      renderPage();
      const region = await chooseMeasure(2);
      const picker = () => within(editor()).getByRole("combobox", { name: /^Armadura · comp/ });
      fireEvent.change(picker(), { target: { value: "3" } });
      expect(picker()).toHaveValue("3");

      fireEvent.keyDown(region, { key: "ArrowRight" });
      expect(screen.getByText("Compás 3 · Voz 1")).toBeVisible();
      expect(picker()).toHaveValue("0");
      fireEvent.keyDown(region, { key: "ArrowLeft" });
      expect(screen.getByText("Compás 2 · Voz 1")).toBeVisible();
      expect(picker()).toHaveValue("0");
      expect(button("Cambiar armadura")).toHaveAttribute("aria-disabled", "true");
      expect(server.bodies).toHaveLength(0);
    });

    it("sin nota elegida, insertar, borrar, la clave y la armadura esperan", async () => {
      const server = editableApi();
      renderPage();
      const region = await findScore();

      for (const name of [
        "Insertar una nota antes",
        "Insertar un silencio antes",
        "Borrar",
        "Clave de fa",
        "Cambiar armadura",
      ]) {
        expect(button(name)).toHaveAttribute("aria-disabled", "true");
      }
      fireEvent.keyDown(region, { key: "Delete" });
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Elige primero una nota o un silencio.");
      });
      expect(server.bodies).toHaveLength(0);
    });

    it("tras un 409, vuelve a aplicar el borrado sobre el ancla desplazada", async () => {
      const server = editableApi();
      renderPage();
      await chooseMeasure(2);
      server.respond(() => {
        // Otra pestaña insertó una nota delante de la elegida (ADR-0011 §2: la retrasa una).
        server.replace(
          apply(server.current(), {
            base_seq: 0,
            op: "InsertEvent",
            anchor: anchorOf(2),
            before: null,
            after: { kind: "note", pitch: "E4", duration_beats: "1" },
          }).next,
        );
        return jsonResponse({ detail: "conflicto" }, 409);
      });

      fireEvent.click(button("Borrar"));
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent(
          "No se guardó: borrado de Do 4, blanca con puntillo (compás 2, voz 1). La sesión cambió en otra pestaña o dispositivo antes de guardarlo; ya ves su estado actual.",
        );
      });
      fireEvent.click(within(editor()).getByRole("button", { name: "Volver a aplicar" }));

      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Guardado: borrado de Do 4, blanca con puntillo.");
      });
      expect(server.bodies[1]).toMatchObject({
        base_seq: 1,
        op: "DeleteEvent",
        anchor: { measure: 2, event_index: 1 },
        after: null,
      });
      // Queda elegida la nota anterior de su voz, la que insertó la otra pestaña.
      expect(useSelectionStore.getState().selection).toMatchObject({
        seq: 2,
        anchor: { measure: 2, event_index: 0 },
      });
    });

    it("tras un 409, volver a aplicar una inserción ante una nota de acorde elige el evento nuevo", async () => {
      const server = editableApi(
        withSecond([note("C4", "3"), note("E4", "3", { is_chord: true })]),
      );
      renderPage();
      const region = await chooseMeasure(2);
      fireEvent.click(region, { clientX: 35 * 7.5, clientY: 6 * 7.5 });
      expect(screen.getByText("Mi4 · blanca con puntillo")).toBeVisible();
      server.respond(() => {
        // Otra pestaña cambió el compás 3: el acorde no se mueve.
        server.replace(
          apply(server.current(), {
            base_seq: 0,
            op: "SetPitch",
            anchor: anchorOf(3),
            before: null,
            after: { pitch: "E4" },
          }).next,
        );
        return jsonResponse({ detail: "conflicto" }, 409);
      });

      fireEvent.click(button("Insertar un silencio antes"));
      fireEvent.click(await within(editor()).findByRole("button", { name: "Volver a aplicar" }));

      await waitFor(() => {
        expect(editStatus()).toHaveTextContent(
          "Guardado: inserción de un silencio de blanca con puntillo.",
        );
      });
      expect(server.bodies[1]).toMatchObject({
        base_seq: 1,
        op: "InsertEvent",
        anchor: { measure: 2, event_index: 0 },
      });
      // Queda elegido el silencio nuevo, aunque la nota elegida no fuera la que empieza el acorde.
      expect(useSelectionStore.getState().selection).toMatchObject({
        seq: 2,
        anchor: { measure: 2, event_index: 0 },
        placedBy: 2,
      });
    });

    it("si el estado nuevo no se carga, al recargar queda elegido el evento que dejó la edición", async () => {
      const server = editableApi(withSecond([note("C4", "3/2"), note("D4", "3/2")]));
      renderPage();
      await chooseMeasure(2);
      // El 201 no trae el estado nuevo y el detalle falla al pedirlo.
      server.respond((body) => {
        const response = server.acceptBare(body);
        server.detailRoute(() => jsonResponse({ detail: "fallo" }, 500));
        return response;
      });

      fireEvent.click(button("Borrar"));
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent(
          "Se guardó el cambio (borrado de Do 4, negra con puntillo, compás 2, voz 1), pero no se pudo cargar la partitura nueva.",
        );
      });

      server.detailRoute(null);
      fireEvent.click(within(editor()).getByRole("button", { name: "Recargar la sesión" }));
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Sesión recargada.");
      });
      expect(useSelectionStore.getState().selection).toMatchObject({
        seq: 1,
        anchor: anchorOf(2),
        placedBy: 1,
      });
      expect(screen.getByText("Re4 · negra con puntillo")).toBeVisible();
    });

    it("si un borrado lleva la selección a otro compás, la trae a la vista", async () => {
      editableApi();
      renderPage();
      await chooseMeasure(2);
      scrollIntoView.mockClear();

      fireEvent.click(button("Borrar"));

      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Guardado: borrado de Do 4, blanca con puntillo.");
      });
      expect(useSelectionStore.getState().selection).toMatchObject({ anchor: anchorOf(3) });
      await waitFor(() => {
        const revealed = scrollIntoView.mock.contexts as Element[];
        expect(revealed.some((element) => element.classList.contains("notation__selection"))).toBe(
          true,
        );
      });
      expect(scrollIntoView).toHaveBeenCalledWith(expect.objectContaining({ block: "nearest" }));
    });

    it("un 409 de la clave dice el compás, no la voz", async () => {
      const server = editableApi();
      renderPage();
      await chooseMeasure(2);
      server.respond(() => jsonResponse({ detail: "conflicto" }, 409));

      fireEvent.click(button("Clave de fa"));

      await waitFor(() => {
        expect(editStatus()).toHaveTextContent(
          "No se guardó: clave de fa en los compases 2 a 3 (compás 2).",
        );
      });
      expect(server.bodies).toHaveLength(1);
    });

    it("un 422 de una inserción no guarda nada y lo dice sin el detail", async () => {
      const server = editableApi();
      renderPage();
      await chooseMeasure(2);
      server.respond(() =>
        jsonResponse({ detail: "InsertEvent de una nota requiere 'pitch'" }, 422),
      );

      fireEvent.click(button("Insertar una nota antes"));

      await waitFor(() => {
        expect(editStatus()).toHaveTextContent(
          "El servidor no aceptó el cambio (inserción de Do 4, blanca con puntillo, compás 2, voz 1): no se guardó nada.",
        );
      });
      expect(screen.queryByText(/requiere/)).toBeNull();
      expect(useSelectionStore.getState().selection).toMatchObject({ seq: 0, anchor: anchorOf(2) });
      expect(server.count(`GET /sessions/${ID}`)).toBe(1);
    });

    it("en solo lectura no se inserta ni se borra, tampoco con el teclado", async () => {
      const server = editableApi(detail({ owner_id: LUIS.id }));
      renderPage(INVESTIGADORA);
      const region = await chooseMeasure(2);

      expect(screen.queryByRole("button", { name: "Borrar" })).toBeNull();
      fireEvent.keyDown(region, { key: "n" });
      fireEvent.keyDown(region, { key: "s" });
      fireEvent.keyDown(region, { key: "Delete" });
      fireEvent.keyDown(region, { key: "Backspace" });
      expect(server.bodies).toHaveLength(0);
      // La selección sigue: las teclas de edición no la tocan.
      expect(screen.getByText("Do4 · blanca con puntillo")).toBeVisible();
    });
  });

  describe("deshacer y rehacer (#185)", () => {
    const live = () => document.querySelector(".selection [role='status']");
    const undoButton = () => button("Deshacer");
    const redoButton = () => button("Rehacer");
    const historyNote = () => document.querySelector(".editor__history");
    const history = () => screen.getByRole("region", { name: "Historia" });
    const note = (
      pitch: string | null,
      duration: string,
      changes: Partial<ScoreEventPayload> = {},
    ) =>
      ({
        kind: pitch === null ? "rest" : "note",
        voice: 0,
        pitch,
        duration_beats: duration,
        tie: null,
        is_chord: false,
        bbox: null,
        confidence: null,
        ir_handle: null,
        ...changes,
      }) satisfies ScoreEventPayload;
    function withSecond(events: ScoreEventPayload[]) {
      const start = detail();
      const second = start.current_score?.parts[0]?.staves[0]?.measures[1];
      if (!second) throw new Error("sin compás 2");
      second.events = events;
      return start;
    }
    /** Sube un paso la nota del compás elegido y espera a que se guarde. */
    async function stepUp(expected: string) {
      fireEvent.click(button("Subir un paso"));
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent(`Guardado: altura ${expected}.`);
      });
    }
    const ctrl = (key: string, changes: Record<string, unknown> = {}) => ({
      key,
      ctrlKey: true,
      ...changes,
    });

    it("deshace con el botón: envía el base_seq y muestra el estado que devuelve el servidor", async () => {
      const server = editableApi();
      renderPage();
      await chooseMeasure(2);
      await stepUp("Re 4");
      expect(historyNote()).toHaveTextContent("Deshace: altura Re 4 (compás 2, voz 1).");
      expect(historyNote()).toHaveTextContent("Nada que rehacer.");
      const pending = deferred<Response>();
      server.respondUndo(() => pending.promise);

      fireEvent.click(undoButton());

      expect(server.undoBodies).toEqual([{ base_seq: 1 }]);
      expect(editStatus()).toHaveTextContent("Deshaciendo…");
      // Sin la respuesta no se da nada por deshecho; la espera no cambia el aspecto de la barra.
      expect(screen.getByText("Re4 · blanca con puntillo")).toBeVisible();
      expect(undoButton()).toHaveAttribute("aria-disabled", "false");

      pending.resolve(server.acceptUndo());

      expect(await screen.findByText("Do4 · blanca con puntillo")).toBeVisible();
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Deshecho: altura Re 4 (compás 2, voz 1).");
      });
      expect(screen.getByText("Ediciones").nextElementSibling).toHaveTextContent("2");
      // El estado nuevo entero llega con la respuesta: no se pide nada más (#275).
      expect(server.count(`GET /sessions/${ID}/export`)).toBe(1);
      expect(server.count(`GET /sessions/${ID}`)).toBe(1);
      // Ya no queda nada que deshacer; lo deshecho se puede rehacer.
      expect(undoButton()).toHaveAttribute("aria-disabled", "true");
      expect(redoButton()).toHaveAttribute("aria-disabled", "false");
      expect(historyNote()).toHaveTextContent(
        "Nada que deshacer. Rehace: altura Re 4 (compás 2, voz 1).",
      );
      expect(useSelectionStore.getState().selection).toEqual({
        sessionId: ID,
        seq: 2,
        anchor: anchorOf(2),
      });
    });

    it("Ctrl+Z mientras se guarda una corrección espera y deshace esa corrección (#276)", async () => {
      const server = editableApi();
      renderPage();
      await chooseMeasure(2);
      const pending = deferred<Response>();
      server.respond(() => pending.promise);

      fireEvent.click(button("Subir un paso"));
      fireEvent.keyDown(window, ctrl("z"));
      expect(server.undoBodies).toHaveLength(0);
      const body = server.bodies[0];
      if (!body) throw new Error("sin edición");
      pending.resolve(server.accept(body));

      await waitFor(() => {
        expect(server.undoBodies).toEqual([{ base_seq: 1 }]);
      });
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Deshecho: altura Re 4 (compás 2, voz 1).");
      });
      expect(screen.getByText("Do4 · blanca con puntillo")).toBeVisible();
    });

    it("con Ctrl+Z deshace, y con Ctrl+Mayús+Z o Ctrl+Y rehace lo deshecho como edición nueva", async () => {
      const server = editableApi();
      renderPage();
      const region = await chooseMeasure(2);
      await stepUp("Re 4");
      await stepUp("Mi 4");

      fireEvent.keyDown(region, ctrl("z"));
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Deshecho: altura Mi 4 (compás 2, voz 1).");
      });
      // También fuera de la partitura, y con ⌘ en un Mac.
      fireEvent.keyDown(document.body, { key: "z", metaKey: true });
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Deshecho: altura Re 4 (compás 2, voz 1).");
      });
      expect(server.undoBodies).toEqual([{ base_seq: 2 }, { base_seq: 3 }]);
      expect(screen.getByText("Do4 · blanca con puntillo")).toBeVisible();

      fireEvent.keyDown(region, ctrl("Z", { shiftKey: true }));
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Rehecho: altura Re 4 (compás 2, voz 1).");
      });
      fireEvent.keyDown(region, ctrl("y"));
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Rehecho: altura Mi 4 (compás 2, voz 1).");
      });

      // Rehacer vuelve a enviar la edición deshecha tal cual, con el base_seq del estado actual.
      expect(server.bodies.slice(2)).toEqual([
        { base_seq: 4, op: "SetPitch", anchor: anchorOf(2), before: null, after: { pitch: "D4" } },
        { base_seq: 5, op: "SetPitch", anchor: anchorOf(2), before: null, after: { pitch: "E4" } },
      ]);
      expect(screen.getByText("Mi4 · blanca con puntillo")).toBeVisible();
      expect(redoButton()).toHaveAttribute("aria-disabled", "true");
      expect(historyNote()).toHaveTextContent("Deshace: altura Mi 4 (compás 2, voz 1).");
      expect(document.activeElement).toBe(region);
    });

    it("una edición nueva vacía la pila de rehacer", async () => {
      const server = editableApi();
      renderPage();
      const region = await chooseMeasure(2);
      await stepUp("Re 4");
      fireEvent.keyDown(region, ctrl("z"));
      await waitFor(() => {
        expect(redoButton()).toHaveAttribute("aria-disabled", "false");
      });

      fireEvent.click(button("Bajar un paso"));
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Guardado: altura Si 3.");
      });

      expect(redoButton()).toHaveAttribute("aria-disabled", "true");
      expect(historyNote()).toHaveTextContent("Nada que rehacer.");
      fireEvent.keyDown(region, ctrl("y"));
      expect(editStatus()).toHaveTextContent("Nada que rehacer.");
      expect(server.bodies).toHaveLength(2);
    });

    it("sin nada que deshacer ni rehacer los controles no están disponibles y la vista lo dice", async () => {
      const server = editableApi();
      renderPage();
      const region = await chooseMeasure(2);

      expect(undoButton()).toHaveAttribute("aria-disabled", "true");
      expect(redoButton()).toHaveAttribute("aria-disabled", "true");
      expect(historyNote()).toHaveTextContent("Nada que deshacer ni rehacer.");
      expect(undoButton()).toHaveAttribute("title", "Nada que deshacer");
      fireEvent.click(undoButton());
      fireEvent.click(redoButton());
      expect(server.count(`POST /sessions/${ID}/undo`)).toBe(0);

      // Con el teclado se dice, sin enviar nada.
      fireEvent.keyDown(region, ctrl("z"));
      expect(editStatus()).toHaveTextContent("Nada que deshacer.");
      fireEvent.keyDown(region, ctrl("y"));
      expect(editStatus()).toHaveTextContent("Nada que rehacer.");
      expect(server.count(`POST /sessions/${ID}/undo`)).toBe(0);
      expect(server.bodies).toHaveLength(0);
      expect(screen.getByText("Ediciones").nextElementSibling).toHaveTextContent("0");
    });

    it("Ctrl+Z dentro de un campo de texto es el deshacer del navegador", async () => {
      const server = editableApi();
      renderPage();
      await chooseMeasure(2);
      await stepUp("Re 4");
      const field = document.createElement("textarea");
      document.body.appendChild(field);
      field.focus();

      const notPrevented = fireEvent.keyDown(field, ctrl("z"));
      fireEvent.keyDown(field, ctrl("y"));

      expect(notPrevented).toBe(true);
      expect(server.count(`POST /sessions/${ID}/undo`)).toBe(0);
      expect(editStatus()).toHaveTextContent("Guardado: altura Re 4.");
      field.remove();
    });

    it("mantener Ctrl+Z pulsado no encadena deshacer", async () => {
      const server = editableApi();
      renderPage();
      const region = await chooseMeasure(2);
      await stepUp("Re 4");

      fireEvent.keyDown(region, ctrl("z", { repeat: true }));

      expect(server.count(`POST /sessions/${ID}/undo`)).toBe(0);
    });

    it("un 409 al deshacer recarga la sesión y lo dice, sin reintentar", async () => {
      const server = editableApi();
      renderPage();
      await chooseMeasure(2);
      await stepUp("Re 4");
      // Otra pestaña corrige el compás 1 antes.
      server.accept({
        base_seq: 1,
        op: "SetPitch",
        anchor: anchorOf(1),
        before: null,
        after: { pitch: "G4" },
      });
      server.respondUndo(() =>
        jsonResponse({ detail: "Conflicto de secuencia al deshacer: base_seq=1" }, 409),
      );

      fireEvent.click(undoButton());

      await waitFor(() => {
        expect(editStatus()).toHaveTextContent(
          "No se deshizo: altura Re 4 (compás 2, voz 1). La sesión cambió en otra pestaña o dispositivo antes de deshacerlo; ya ves su estado actual.",
        );
      });
      expect(screen.queryByText(/Conflicto de secuencia/)).toBeNull();
      expect(within(editor()).queryByRole("button", { name: "Volver a aplicar" })).toBeNull();
      expect(server.undoBodies).toEqual([{ base_seq: 1 }]);
      // Ahora desharía la última edición, la de la otra pestaña.
      expect(historyNote()).toHaveTextContent("Deshace: altura Sol 4 (compás 1, voz 1).");
      expect(undoButton()).toHaveAttribute("aria-disabled", "false");
    });

    it("si el 409 es porque la sesión está finalizada, lo dice y la deja en solo lectura", async () => {
      const server = editableApi();
      renderPage();
      await chooseMeasure(2);
      await stepUp("Re 4");
      server.replace({ ...server.current(), status: "finalized" });
      server.respondUndo(() => jsonResponse({ detail: "Sesión finalizada" }, 409));

      fireEvent.click(undoButton());

      await waitFor(() => {
        expect(editStatus()).toHaveTextContent(
          "No se deshizo: altura Re 4 (compás 2, voz 1). La sesión está finalizada y ya no admite correcciones.",
        );
      });
      expect(within(editor()).queryByRole("button", { name: "Deshacer" })).toBeNull();
    });

    it("el 422 de una edición sin estado previo (anterior a ADR-0017) tiene su propio mensaje", async () => {
      const old = apply(detail(), {
        base_seq: 0,
        op: "SetPitch",
        anchor: anchorOf(2),
        before: null,
        after: { pitch: "D4" },
      });
      const server = editableApi({
        ...old.next,
        edits: [{ ...old.saved, before: null }],
      });
      renderPage();
      await chooseMeasure(2);

      fireEvent.click(undoButton());

      await waitFor(() => {
        expect(editStatus()).toHaveTextContent(
          "No se puede deshacer la edición 1 (altura Re 4, compás 2, voz 1): es de antes de que el servidor guardara el estado previo de cada edición, y deshacerla alteraría la partitura. No se cambió nada.",
        );
      });
      expect(screen.queryByText(/no guardó su estado previo completo/)).toBeNull();
      expect(screen.getByText("Re4 · blanca con puntillo")).toBeVisible();
      expect(server.count(`GET /sessions/${ID}`)).toBe(1);
    });

    it("otro 422 al deshacer dice que el servidor no lo aceptó, sin el detail", async () => {
      const server = editableApi();
      renderPage();
      await chooseMeasure(2);
      await stepUp("Re 4");
      server.respondUndo(() =>
        jsonResponse({ detail: "Evento compensatorio no aplicable: índice" }, 422),
      );

      fireEvent.click(undoButton());

      await waitFor(() => {
        expect(editStatus()).toHaveTextContent(
          "El servidor no aceptó deshacer (altura Re 4, compás 2, voz 1): no se cambió nada.",
        );
      });
      expect(screen.queryByText(/compensatorio/)).toBeNull();
    });

    it("un 409 al rehacer recarga y no reintenta; si se editó en otra parte, ya no hay nada que rehacer", async () => {
      const server = editableApi();
      renderPage();
      const region = await chooseMeasure(2);
      await stepUp("Re 4");
      fireEvent.keyDown(region, ctrl("z"));
      await waitFor(() => {
        expect(redoButton()).toHaveAttribute("aria-disabled", "false");
      });
      server.respond(() => {
        server.accept({
          base_seq: 2,
          op: "SetPitch",
          anchor: anchorOf(1),
          before: null,
          after: { pitch: "G4" },
        });
        return jsonResponse({ detail: "Conflicto de secuencia" }, 409);
      });

      fireEvent.click(redoButton());

      await waitFor(() => {
        expect(editStatus()).toHaveTextContent(
          "No se rehízo: altura Re 4 (compás 2, voz 1). La sesión cambió en otra pestaña o dispositivo antes de rehacerlo; ya ves su estado actual.",
        );
      });
      expect(server.bodies).toHaveLength(2);
      expect(redoButton()).toHaveAttribute("aria-disabled", "true");
      expect(within(editor()).queryByRole("button", { name: "Volver a aplicar" })).toBeNull();
    });

    it("un 422 al rehacer no guarda nada y lo dice", async () => {
      const server = editableApi();
      renderPage();
      const region = await chooseMeasure(2);
      await stepUp("Re 4");
      fireEvent.keyDown(region, ctrl("z"));
      await waitFor(() => {
        expect(redoButton()).toHaveAttribute("aria-disabled", "false");
      });
      server.respond(() => jsonResponse({ detail: "Contenido de 'after' no válido" }, 422));

      fireEvent.click(redoButton());

      await waitFor(() => {
        expect(editStatus()).toHaveTextContent(
          "El servidor no aceptó rehacer (altura Re 4, compás 2, voz 1): no se guardó nada.",
        );
      });
      expect(screen.queryByText(/after/)).toBeNull();
    });

    it("deshacer un borrado devuelve la nota con sus marcas y la deja elegida", async () => {
      const server = editableApi(
        withSecond([note("C4", "3/2", { articulations: ["staccato"] }), note("D4", "3/2")]),
      );
      renderPage();
      await chooseMeasure(2);
      fireEvent.click(button("Borrar"));
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Guardado: borrado de Do 4, negra con puntillo.");
      });
      expect(screen.getByText("Re4 · negra con puntillo")).toBeVisible();

      fireEvent.click(undoButton());

      await waitFor(() => {
        expect(editStatus()).toHaveTextContent(
          "Deshecho: borrado de Do 4, negra con puntillo (compás 2, voz 1).",
        );
      });
      // La vista no recompone la nota: muestra el estado que devuelve el servidor, cuya
      // compensatoria lleva la instantánea con las marcas (ADR-0031), y llega con la respuesta.
      expect(server.undoBodies).toEqual([{ base_seq: 1 }]);
      expect(server.count(`GET /sessions/${ID}/export`)).toBe(1);
      expect(useSelectionStore.getState().selection).toEqual({
        sessionId: ID,
        seq: 2,
        anchor: anchorOf(2),
        placedBy: 2,
      });
      expect(screen.getByText("Do4 · negra con puntillo")).toBeVisible();
      await waitFor(() => {
        expect(live()).toHaveTextContent("Compás 2, voz 1: Do 4, negra con puntillo.");
      });
    });

    it("deshacer una inserción deja elegido el evento que ocupa su sitio", async () => {
      editableApi();
      renderPage();
      await chooseMeasure(2);
      fireEvent.click(button("Insertar un silencio antes"));
      await waitFor(() => {
        expect(screen.getByText("Silencio de blanca con puntillo")).toBeVisible();
      });

      fireEvent.click(undoButton());

      await waitFor(() => {
        expect(editStatus()).toHaveTextContent(
          "Deshecho: inserción de un silencio de blanca con puntillo (compás 2, voz 1).",
        );
      });
      expect(useSelectionStore.getState().selection).toEqual({
        sessionId: ID,
        seq: 2,
        anchor: anchorOf(2),
        placedBy: 2,
      });
      expect(screen.getByText("Do4 · blanca con puntillo")).toBeVisible();
    });

    it("deshacer lleva la selección al evento que cambia y lo trae a la vista", async () => {
      editableApi();
      renderPage();
      const region = await chooseMeasure(2);
      await stepUp("Re 4");
      fireEvent.keyDown(region, { key: "ArrowLeft" });
      expect(screen.getByText("Compás 1 · Voz 1")).toBeVisible();
      scrollIntoView.mockClear();

      fireEvent.keyDown(region, ctrl("z"));

      await waitFor(() => {
        expect(useSelectionStore.getState().selection).toEqual({
          sessionId: ID,
          seq: 2,
          anchor: anchorOf(2),
          placedBy: 2,
        });
      });
      expect(screen.getByText("Do4 · blanca con puntillo")).toBeVisible();
      await waitFor(() => {
        expect(scrollIntoView).toHaveBeenCalled();
      });
    });

    it("si se elige otra nota mientras se deshace, se respeta", async () => {
      const server = editableApi();
      renderPage();
      const region = await chooseMeasure(2);
      await stepUp("Re 4");
      const pending = deferred<Response>();
      server.respondUndo(() => pending.promise);

      fireEvent.click(undoButton());
      fireEvent.keyDown(region, { key: "ArrowLeft" });
      pending.resolve(server.acceptUndo());

      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Deshecho: altura Re 4 (compás 2, voz 1).");
      });
      expect(useSelectionStore.getState().selection).toMatchObject({
        seq: 2,
        anchor: anchorOf(1),
      });
    });

    it("la clave deshecha no mueve la selección", async () => {
      editableApi();
      renderPage();
      const region = await chooseMeasure(2);
      fireEvent.click(button("Clave de fa"));
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent(/^Guardado: clave de fa/);
      });
      fireEvent.keyDown(region, { key: "ArrowRight" });
      expect(screen.getByText("Compás 3 · Voz 1")).toBeVisible();

      fireEvent.keyDown(region, ctrl("z"));

      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Deshecho: clave de fa (compás 2).");
      });
      expect(useSelectionStore.getState().selection).toEqual({
        sessionId: ID,
        seq: 2,
        anchor: anchorOf(3),
      });
    });

    it("la historia lista las ediciones con lo deshecho y lo rehecho distinguibles", async () => {
      editableApi();
      renderPage();
      const region = await chooseMeasure(2);
      await stepUp("Re 4");
      fireEvent.keyDown(region, ctrl("z"));
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Deshecho: altura Re 4 (compás 2, voz 1).");
      });
      fireEvent.keyDown(region, ctrl("y"));
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Rehecho: altura Re 4 (compás 2, voz 1).");
      });

      fireEvent.click(within(history()).getByText("Ver las 3 ediciones"));

      const items = within(history()).getAllByRole("listitem");
      // De la más reciente a la primera.
      expect(items.map((item) => item.textContent)).toEqual([
        expect.stringContaining("Rehace la 1: altura Re 4"),
        expect.stringContaining("Deshace la 1: altura Re 4"),
        expect.stringContaining("Altura Re 4"),
      ]);
      const [redone, compensatory, first] = items;
      expect(redone).toHaveTextContent("Compás 2, voz 1");
      expect(compensatory).not.toHaveTextContent("Deshecha");
      expect(first).toHaveTextContent("Deshecha en la 2");
      // La hora del servidor es UTC aunque llegue sin zona.
      expect(first?.querySelector("time")).toHaveAttribute("datetime", "2026-10-24T10:00:00.000Z");
      expect(first).toHaveAttribute("data-undone", "true");
      expect(redone).not.toHaveAttribute("data-undone", "true");
    });

    it("sin ediciones, la historia lo dice", async () => {
      editableApi();
      renderPage();
      await findScore();

      expect(history()).toHaveTextContent(
        "Sin ediciones: la partitura es la que transcribió HOMR.",
      );
    });

    it("en solo lectura se consulta la historia, pero no se deshace ni se rehace", async () => {
      const done = apply(detail({ owner_id: LUIS.id }), {
        base_seq: 0,
        op: "SetPitch",
        anchor: anchorOf(2),
        before: null,
        after: { pitch: "D4" },
      });
      const server = editableApi(done.next);
      renderPage(INVESTIGADORA);
      const region = await chooseMeasure(2);

      expect(screen.queryByRole("button", { name: "Deshacer" })).toBeNull();
      expect(screen.queryByRole("button", { name: "Rehacer" })).toBeNull();
      fireEvent.keyDown(region, ctrl("z"));
      fireEvent.keyDown(document.body, ctrl("y"));
      expect(server.count(`POST /sessions/${ID}/undo`)).toBe(0);
      expect(server.bodies).toHaveLength(0);

      fireEvent.click(within(history()).getByText("Ver la edición"));
      expect(within(history()).getByRole("listitem")).toHaveTextContent("Altura Re 4");
    });

    it("si la partitura nueva no se puede exportar, se puede deshacer la edición sin perder el foco", async () => {
      const server = editableApi();
      renderPage();
      await chooseMeasure(2);
      server.failExport(500);
      button("Subir un paso").focus();
      fireEvent.click(button("Subir un paso"));
      await screen.findByText("No se pudo dibujar la partitura.");
      // La barra pasa a otro sitio y no tiene ese botón: el foco va a lo que dice.
      expect(document.activeElement).toBe(document.querySelector(".editor__messages"));
      server.failExport(null);

      undoButton().focus();
      fireEvent.click(undoButton());

      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Deshecho: altura Re 4 (compás 2, voz 1).");
      });
      expect(await findScore()).toBeVisible();
      expect(server.undoBodies).toEqual([{ base_seq: 1 }]);
      // La barra de la partitura dibujada sustituye a la otra: el foco sigue en «Deshacer».
      expect(document.activeElement).toBe(undoButton());
    });

    it("mientras se carga la partitura, Ctrl+Z no deshace a ciegas", async () => {
      const done = apply(detail(), {
        base_seq: 0,
        op: "SetPitch",
        anchor: anchorOf(2),
        before: null,
        after: { pitch: "D4" },
      });
      const server = editableApi(done.next);
      server.exportRoute(hangUntilAborted);
      renderPage();
      await screen.findByText("Ediciones");

      fireEvent.keyDown(document.body, ctrl("z"));

      expect(server.count(`POST /sessions/${ID}/undo`)).toBe(0);
      expect(screen.queryByRole("button", { name: "Deshacer" })).toBeNull();
    });

    it("rehace inserciones y borrados en el orden inverso al deshecho, con su ancla y su after", async () => {
      const server = editableApi(withSecond([note("C4", "3/2"), note("D4", "3/2")]));
      renderPage();
      const region = await chooseMeasure(2);
      fireEvent.keyDown(region, { key: "n" });
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Guardado: inserción de Do 4, negra con puntillo.");
      });
      fireEvent.keyDown(region, { key: "Delete" });
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Guardado: borrado de Do 4, negra con puntillo.");
      });
      const [insert, remove] = server.bodies;

      // Se deshacen el borrado y después la inserción; cada uno deja elegido lo que cambia.
      fireEvent.keyDown(region, ctrl("z"));
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent(
          "Deshecho: borrado de Do 4, negra con puntillo (compás 2, voz 1).",
        );
      });
      expect(useSelectionStore.getState().selection).toMatchObject({
        seq: 3,
        anchor: anchorOf(2),
        placedBy: 3,
      });
      fireEvent.keyDown(region, ctrl("z"));
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent(
          "Deshecho: inserción de Do 4, negra con puntillo (compás 2, voz 1).",
        );
      });
      expect(historyNote()).toHaveTextContent(
        "Nada que deshacer. Rehace: inserción de Do 4, negra con puntillo (compás 2, voz 1).",
      );

      // Se rehacen en el orden inverso: primero la inserción, después el borrado, tal cual.
      fireEvent.keyDown(region, ctrl("y"));
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent(
          "Rehecho: inserción de Do 4, negra con puntillo (compás 2, voz 1).",
        );
      });
      expect(useSelectionStore.getState().selection).toMatchObject({
        seq: 5,
        anchor: anchorOf(2),
        placedBy: 5,
      });
      fireEvent.keyDown(region, ctrl("y"));
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent(
          "Rehecho: borrado de Do 4, negra con puntillo (compás 2, voz 1).",
        );
      });
      expect(server.bodies.slice(2)).toEqual([
        { ...insert, base_seq: 4 },
        { ...remove, base_seq: 5, after: null },
      ]);
      expect(useSelectionStore.getState().selection).toMatchObject({
        seq: 6,
        anchor: anchorOf(2),
        placedBy: 6,
      });
      expect(
        server
          .current()
          .current_score?.parts[0]?.staves[0]?.measures[1]?.events.map((event) => event.pitch),
      ).toEqual(["C4", "D4"]);
      expect(historyNote()).toHaveTextContent("Nada que rehacer.");
    });

    it("al salir de la vista deja de escuchar Ctrl+Z", async () => {
      const server = editableApi();
      const router = renderPage();
      await chooseMeasure(2);
      await stepUp("Re 4");

      await act(() => router.navigate("/transcripcion"));
      fireEvent.keyDown(document.body, ctrl("z"));

      expect(server.count(`POST /sessions/${ID}/undo`)).toBe(0);
    });
  });

  describe("descartar, restaurar y revalidar los posibles errores (#186)", () => {
    const panel = () => screen.getByRole("region", { name: "Posibles errores" });
    const findingsStatus = () => document.querySelector(".findings__status");
    const markCount = () => document.querySelectorAll(".notation__mark").length;
    const heading = () => screen.getByRole("heading", { name: "Posibles errores" });
    const dismissTrigger = (label: string) =>
      within(panel()).getByRole("button", { name: `Descartar como falso positivo · ${label}` });
    const submit = () =>
      within(panel()).getByRole("button", { name: "Descartar como falso positivo" });
    const reasonField = () => within(panel()).getByRole("textbox", { name: /motivo/i });
    const ctrlKey = (key: string) => ({ key, ctrlKey: true });
    const dismissedFinding = (id: number, measureNumber: number, reason: string | null = null) =>
      finding(id, measureNumber, {
        status: "dismissed",
        dismissed_at: "2026-10-24T11:00:00",
        dismissed_by: "ana",
        dismissal_reason: reason,
      });
    /** Una edición guardada que se puede deshacer, para empezar con la partitura ya editada. */
    function editedDetail(changes: Partial<SessionDetailRead> = {}) {
      const { next } = apply(detail(), {
        base_seq: 0,
        op: "SetPitch",
        anchor: anchorOf(1),
        before: null,
        after: { pitch: "D4" },
      });
      return { ...next, ...changes };
    }

    it("descarta con un motivo, sin darlo por descartado antes de la respuesta, y lo lista aparte", async () => {
      const server = editableApi(detail(), { findings: [finding(1, 1), finding(2, 3)] });
      renderPage();
      await waitFor(() => {
        expect(markCount()).toBe(2);
      });
      // Descartar no corrige nada: se dice antes de abrir el formulario.
      expect(within(panel()).getByText(/descartar un posible error no corrige/i)).toBeVisible();

      await userEvent.click(dismissTrigger("Duración del compás, compás 3"));
      expect(reasonField()).toHaveFocus();
      expect(within(panel()).getByText(/descartar no corrige la partitura/i)).toBeVisible();
      await userEvent.type(reasonField(), "Así está en el original");
      const pending = deferred<Response>();
      server.respondFinding(() => pending.promise);
      await userEvent.click(submit());

      expect(server.findingCalls).toEqual([
        {
          key: `POST /sessions/${ID}/findings/2/dismiss`,
          body: { reason: "Así está en el original" },
        },
      ]);
      // Sin la respuesta no se da por descartado: el compás sigue marcado y en la lista.
      expect(findingsStatus()).toHaveTextContent("Descartando…");
      expect(submit()).toHaveAttribute("aria-disabled", "true");
      expect(markCount()).toBe(2);

      pending.resolve(
        server.acceptFinding(`POST /sessions/${ID}/findings/2/dismiss`, {
          reason: "Así está en el original",
        }),
      );

      await waitFor(() => {
        expect(markCount()).toBe(1);
      });
      expect(document.querySelector(".notation__mark")).toHaveTextContent("Compás 1");
      expect(findingsStatus()).toHaveTextContent(
        "Descartado como falso positivo: Duración del compás, compás 3. La partitura no cambia.",
      );
      expect(within(panel()).queryByRole("textbox")).toBeNull();
      expect(within(panel()).queryByRole("button", { name: /^compás 3/i })).toBeNull();
      // El foco sigue en la lista: pasa al posible error que queda.
      expect(dismissTrigger("Duración del compás, compás 1")).toHaveFocus();
      await userEvent.click(within(panel()).getByText(/descartados como falso positivo · 1/i));
      expect(within(panel()).getByText("Motivo: Así está en el original")).toBeVisible();
      // Descartar no cambia la partitura: no se vuelve a pedir ni el detalle ni el MusicXML.
      expect(server.count(`GET /sessions/${ID}`)).toBe(1);
      expect(server.count(`GET /sessions/${ID}/export`)).toBe(1);
    });

    it("con varios posibles errores en un compás, numera cada uno y su botón, con su mensaje (ADR-0032)", async () => {
      // Con varias voces, `measure.balance` señala cada voz del compás por separado.
      const voice1 = finding(1, 2, { message: "El compás 2 (voz 0) suma 4 negras." });
      const voice2 = finding(2, 2, {
        message: "El compás 2 (voz 1) suma 2 negras.",
        anchor: { ...finding(2, 2).anchor, voice: 1 },
      });
      const server = editableApi(detail(), { findings: [voice1, voice2] });
      renderPage();
      const region = await screen.findByRole("region", { name: "Posibles errores" });
      const first = await within(region).findByRole("button", {
        name: "Descartar 1 como falso positivo · Duración del compás, compás 2",
      });
      const second = within(region).getByRole("button", {
        name: "Descartar 2 como falso positivo · Duración del compás, compás 2",
      });
      expect(first).toHaveAccessibleDescription("El compás 2 (voz 0) suma 4 negras.");
      expect(second).toHaveAccessibleDescription("El compás 2 (voz 1) suma 2 negras.");
      const toggle = within(region).getByRole("button", { name: /^compás 2/i });
      expect(toggle).toHaveTextContent("1 · Duración del compás");
      expect(toggle).toHaveTextContent("2 · Duración del compás");

      await userEvent.click(second);
      await userEvent.click(submit());

      expect(server.findingCalls).toEqual([
        { key: `POST /sessions/${ID}/findings/2/dismiss`, body: { reason: null } },
      ]);
      await waitFor(() => {
        expect(dismissTrigger("Duración del compás, compás 2")).toHaveFocus();
      });
      // Queda uno: sin número.
      expect(within(region).getByRole("button", { name: /^compás 2/i })).not.toHaveTextContent(
        "1 ·",
      );
      await userEvent.click(within(region).getByText(/descartados como falso positivo · 1/i));
      expect(
        within(region).getByRole("button", { name: "Restaurar · Duración del compás, compás 2" }),
      ).toHaveAccessibleDescription("El compás 2 (voz 1) suma 2 negras.");
    });

    it("con el teclado: Intro abre el formulario, Esc lo cierra y un motivo en blanco se envía como null", async () => {
      const server = editableApi(detail(), { findings: [finding(1, 2)] });
      renderPage();
      const trigger = await within(
        await screen.findByRole("region", { name: "Posibles errores" }),
      ).findByRole("button", {
        name: "Descartar como falso positivo · Duración del compás, compás 2",
      });
      expect(trigger).toHaveAttribute("aria-expanded", "false");

      trigger.focus();
      await userEvent.keyboard("{Enter}");
      expect(reasonField()).toHaveFocus();
      expect(trigger).toHaveAttribute("aria-expanded", "true");
      await userEvent.keyboard("{Escape}");
      expect(within(panel()).queryByRole("textbox")).toBeNull();
      expect(trigger).toHaveFocus();
      expect(trigger).toHaveAttribute("aria-expanded", "false");

      await userEvent.keyboard("{Enter}");
      await userEvent.keyboard("   {Enter}");

      expect(server.findingCalls).toEqual([
        { key: `POST /sessions/${ID}/findings/1/dismiss`, body: { reason: null } },
      ]);
      await waitFor(() => {
        expect(findingsStatus()).toHaveTextContent("Descartado como falso positivo");
      });
      // Sin posibles errores activos el foco pasa al título del panel, que lo dice con cautela.
      expect(heading()).toHaveFocus();
      expect(markCount()).toBe(0);
      expect(within(panel()).getByText(/no queda ningún posible error activo/i)).toBeVisible();
      expect(
        within(panel()).getByText(/no garantiza que la transcripción esté bien/i),
      ).toBeVisible();
    });

    it("restaura un descartado desde la lista, también con el teclado, y vuelve a marcar su compás", async () => {
      const server = editableApi(detail(), {
        findings: [finding(1, 1), dismissedFinding(2, 3, "Así está")],
      });
      renderPage();
      await waitFor(() => {
        expect(markCount()).toBe(1);
      });
      await userEvent.click(within(panel()).getByText(/descartados como falso positivo · 1/i));
      const restore = within(panel()).getByRole("button", {
        name: "Restaurar · Duración del compás, compás 3",
      });

      restore.focus();
      await userEvent.keyboard("{Enter}");

      expect(server.findingCalls).toEqual([
        { key: `POST /sessions/${ID}/findings/2/restore`, body: null },
      ]);
      await waitFor(() => {
        expect(markCount()).toBe(2);
      });
      expect(findingsStatus()).toHaveTextContent(
        "Restaurado: Duración del compás, compás 3 vuelve a señalarse.",
      );
      expect(within(panel()).queryByText(/descartados como falso positivo/i)).toBeNull();
      // El foco sigue al posible error restaurado, ya en la lista de los activos.
      expect(dismissTrigger("Duración del compás, compás 3")).toHaveFocus();
    });

    it("revalida tras corregir: las marcas y la lista pasan a ser las del estado nuevo", async () => {
      const server = editableApi(detail(), {
        findings: [finding(1, 2)],
        validate: () => [finding(7, 3, { rule_id: "pitch.range" })],
      });
      renderPage();
      await chooseMeasure(2);
      fireEvent.click(button("Subir un paso"));
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Guardado: altura Re 4.");
      });
      // Los posibles errores son de la transcripción: lo dice y ofrece revalidar.
      expect(
        await within(panel()).findByText(
          /corresponden a la partitura tal como la transcribió HOMR; después se editó/i,
        ),
      ).toBeVisible();
      const revalidate = within(panel()).getByRole("button", { name: "Revalidar" });
      const pending = deferred<Response>();
      server.respondValidate(() => pending.promise);

      await userEvent.click(revalidate);

      expect(findingsStatus()).toHaveTextContent("Revalidando…");
      expect(revalidate).toHaveAttribute("aria-disabled", "true");
      // Mientras tanto, la lista es la de antes: no se descarta nada que vaya a cambiar.
      expect(dismissTrigger("Duración del compás, compás 2")).toHaveAttribute(
        "aria-disabled",
        "true",
      );
      pending.resolve(server.acceptValidate());

      await waitFor(() => {
        expect(findingsStatus()).toHaveTextContent(
          "Revalidada la partitura actual: 1 posible error.",
        );
      });
      expect(server.count(`POST /sessions/${ID}/validate`)).toBe(1);
      expect(markCount()).toBe(1);
      expect(document.querySelector(".notation__mark")).toHaveTextContent("Compás 3");
      expect(within(panel()).getByRole("button", { name: /^compás 3/i })).toHaveTextContent(
        "Altura fuera de registro",
      );
      expect(within(panel()).queryByRole("button", { name: /^compás 2/i })).toBeNull();
      expect(within(panel()).queryByText(/después se editó/i)).toBeNull();
      expect(within(panel()).queryByRole("button", { name: "Revalidar" })).toBeNull();
      // El botón ya no está: el foco pasa al título del panel.
      expect(heading()).toHaveFocus();
      // Revalidar no cambia la partitura ni la nota elegida: el MusicXML es el que trajo el 201.
      expect(server.count(`GET /sessions/${ID}/export`)).toBe(1);
      expect(useSelectionStore.getState().selection).toMatchObject({ seq: 1, anchor: anchorOf(2) });
    });

    it("sin posibles errores y con ediciones ofrece revalidar; si no queda ninguno, no promete que esté bien", async () => {
      const server = editableApi(editedDetail(), { validate: () => [] });
      renderPage();
      expect(
        await within(await screen.findByRole("region", { name: "Posibles errores" })).findByText(
          /puede que el resultado ya no esté al día/i,
        ),
      ).toBeVisible();

      await userEvent.click(within(panel()).getByRole("button", { name: "Revalidar" }));

      await waitFor(() => {
        expect(findingsStatus()).toHaveTextContent(
          "Revalidada la partitura actual: el validador no señala ningún compás. Que no señale ninguno no garantiza que la transcripción esté bien.",
        );
      });
      expect(
        within(panel()).getByText("El validador no señala ningún compás en la partitura actual."),
      ).toBeVisible();
      expect(within(panel()).queryByText(/puede que el resultado ya no esté al día/i)).toBeNull();
      expect(within(panel()).queryByRole("button", { name: "Revalidar" })).toBeNull();
      expect(server.count(`POST /sessions/${ID}/validate`)).toBe(1);
    });

    it("si se editó en otra pestaña, revalida el estado actual de la sesión y lo muestra", async () => {
      const server = editableApi(editedDetail(), {
        findings: [finding(1, 2)],
        validate: () => [finding(9, 1)],
      });
      renderPage();
      await within(await screen.findByRole("region", { name: "Posibles errores" })).findByRole(
        "button",
        { name: "Revalidar" },
      );
      // Otra pestaña guarda una edición: el servidor pasa al estado 2.
      server.replace(
        apply(server.current(), {
          base_seq: 1,
          op: "SetPitch",
          anchor: anchorOf(3),
          before: null,
          after: { pitch: "E4" },
        }).next,
      );

      await userEvent.click(within(panel()).getByRole("button", { name: "Revalidar" }));

      await waitFor(() => {
        expect(findingsStatus()).toHaveTextContent(
          "La sesión iba por un estado posterior al que se veía: se revalidó ese estado, que ya ves. 1 posible error.",
        );
      });
      expect(screen.getByText("Ediciones").nextElementSibling).toHaveTextContent("2");
      expect(markCount()).toBe(1);
      expect(document.querySelector(".notation__mark")).toHaveTextContent("Compás 1");
      expect(within(panel()).queryByText(/después se editó/i)).toBeNull();
      expect(editStatus()).toHaveTextContent("Sesión recargada.");
    });

    it("mientras se revalida, las correcciones esperan: cambiarían el estado validado", async () => {
      const server = editableApi(editedDetail(), {
        findings: [finding(1, 2)],
        validate: () => [finding(9, 1)],
      });
      renderPage();
      const pending = deferred<Response>();
      server.respondValidate(() => pending.promise);
      await chooseMeasure(2);
      await userEvent.click(
        within(screen.getByRole("region", { name: "Posibles errores" })).getByRole("button", {
          name: "Revalidar",
        }),
      );

      expect(button("Subir un paso")).toHaveAttribute("aria-disabled", "true");
      fireEvent.click(button("Subir un paso"));
      fireEvent.keyDown(document.body, { key: "z", ctrlKey: true });
      expect(server.bodies).toEqual([]);
      expect(server.count(`POST /sessions/${ID}/undo`)).toBe(0);

      pending.resolve(server.acceptValidate());
      await waitFor(() => {
        expect(findingsStatus()).toHaveTextContent(
          "Revalidada la partitura actual: 1 posible error.",
        );
      });
      expect(button("Subir un paso")).not.toHaveAttribute("aria-disabled", "true");
      fireEvent.click(button("Subir un paso"));
      expect(server.bodies).toHaveLength(1);
    });

    it("el aviso de la última orden caduca al pasar a otro estado", async () => {
      editableApi(detail(), { findings: [finding(1, 2), finding(2, 3)] });
      renderPage();
      await userEvent.click(
        await within(await screen.findByRole("region", { name: "Posibles errores" })).findByRole(
          "button",
          { name: "Descartar como falso positivo · Duración del compás, compás 3" },
        ),
      );
      await userEvent.click(submit());
      await waitFor(() => {
        expect(findingsStatus()).toHaveTextContent("Descartado como falso positivo");
      });

      await chooseMeasure(1);
      fireEvent.click(button("Subir un paso"));
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Guardado: altura Re 4.");
      });

      expect(findingsStatus()).toBeEmptyDOMElement();
    });

    it("si el servidor va por delante y su estado no se puede cargar, no dice que ya se ve", async () => {
      const server = editableApi(editedDetail(), {
        findings: [finding(1, 2)],
        validate: () => [finding(9, 1)],
      });
      renderPage();
      const revalidate = await within(
        await screen.findByRole("region", { name: "Posibles errores" }),
      ).findByRole("button", { name: "Revalidar" });
      server.replace(
        apply(server.current(), {
          base_seq: 1,
          op: "SetPitch",
          anchor: anchorOf(3),
          before: null,
          after: { pitch: "E4" },
        }).next,
      );
      server.detailRoute(() => jsonResponse({ detail: "fallo" }, 500));

      await userEvent.click(revalidate);

      await waitFor(() => {
        expect(findingsStatus()).toHaveTextContent(
          "La sesión iba por un estado posterior al que se ve y se revalidó ese estado, pero no se pudo cargar: recarga la sesión para verlo.",
        );
      });
      expect(findingsStatus()).not.toHaveTextContent("que ya ves");
      expect(screen.getByText("Ediciones").nextElementSibling).toHaveTextContent("1");
      expect(editStatus()).toHaveTextContent("No se pudo recargar la sesión.");
      // La lista sigue siendo la vieja: ni se da por validada ni por posterior, y se puede revalidar.
      expect(within(panel()).queryByText(/posterior al que ves/i)).toBeNull();
      expect(revalidate).toBeVisible();
      expect(revalidate).toHaveFocus();

      // Tras recargar desde la barra, el aviso ya no vale: habla del estado anterior.
      server.detailRoute(null);
      await userEvent.click(button("Recargar la sesión"));
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Sesión recargada.");
      });
      expect(findingsStatus()).toBeEmptyDOMElement();
    });

    it("con una corrección guardada sin mostrar, revalidar carga su estado sin atribuirlo a otra pestaña", async () => {
      // La validación ya es de un estado anterior: se ofrece revalidar.
      const server = editableApi(editedDetail(), {
        findings: [finding(1, 2)],
        validate: () => [finding(9, 3)],
      });
      renderPage();
      await chooseMeasure(2);
      // Se guarda la corrección, pero el 201 no trae el estado nuevo y no se puede cargar.
      server.respond((body) => server.acceptBare(body));
      server.detailRoute(() => jsonResponse({ detail: "fallo" }, 500));
      fireEvent.click(button("Subir un paso"));
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent(/no se pudo cargar la partitura nueva/i);
      });
      server.detailRoute(null);
      const pending = deferred<Response>();
      server.respondValidate(() => pending.promise);
      const detailCalls = server.count(`GET /sessions/${ID}`);

      await userEvent.click(within(panel()).getByRole("button", { name: "Revalidar" }));

      // Mientras se revalida, la recarga de la barra espera: la hará la revalidación.
      expect(button("Recargar la sesión")).toHaveAttribute("aria-disabled", "true");
      fireEvent.click(button("Recargar la sesión"));
      expect(server.count(`GET /sessions/${ID}`)).toBe(detailCalls);
      pending.resolve(server.acceptValidate());

      await waitFor(() => {
        expect(findingsStatus()).toHaveTextContent(
          "La sesión iba por un estado posterior al que se veía: se revalidó ese estado, que ya ves. 1 posible error.",
        );
      });
      expect(findingsStatus()).not.toHaveTextContent(/otra pestaña/);
      expect(screen.getByText("Ediciones").nextElementSibling).toHaveTextContent("2");
      expect(document.querySelector(".notation__mark")).toHaveTextContent("Compás 3");
    });

    it("si mientras se revalida la sesión avanza otra vez, lo dice y vuelve a ofrecer revalidar", async () => {
      const server = editableApi(editedDetail(), {
        findings: [finding(1, 2)],
        validate: () => [finding(9, 1)],
      });
      renderPage();
      const pending = deferred<Response>();
      server.respondValidate(() => pending.promise);
      const edit = (base_seq: number, pitch: string) => {
        server.replace(
          apply(server.current(), {
            base_seq,
            op: "SetPitch",
            anchor: anchorOf(3),
            before: null,
            after: { pitch },
          }).next,
        );
      };
      // Otra pestaña edita (estado 2), el servidor valida ese estado y vuelve a editar (estado 3).
      edit(1, "E4");
      await userEvent.click(
        await within(await screen.findByRole("region", { name: "Posibles errores" })).findByRole(
          "button",
          { name: "Revalidar" },
        ),
      );
      const validated = server.acceptValidate();
      edit(2, "F4");
      pending.resolve(validated);

      await waitFor(() => {
        expect(findingsStatus()).toHaveTextContent(
          "Se revalidó la partitura tal como estaba tras 2 ediciones, pero la sesión ya va por un estado posterior: hay que volver a revalidar.",
        );
      });
      expect(screen.getByText("Ediciones").nextElementSibling).toHaveTextContent("3");
      expect(
        within(panel()).getByText(/tal como estaba tras 2 ediciones; después se editó/i),
      ).toBeVisible();
      expect(within(panel()).getByRole("button", { name: "Revalidar" })).toBeVisible();
    });

    it("si tras descartar no se puede volver a pedir la lista, no la tapa", async () => {
      const server = editableApi(detail(), { findings: [finding(1, 2), finding(2, 3)] });
      renderPage();
      await userEvent.click(
        await within(await screen.findByRole("region", { name: "Posibles errores" })).findByRole(
          "button",
          { name: "Descartar como falso positivo · Duración del compás, compás 3" },
        ),
      );
      server.failFindings(500);

      await userEvent.click(submit());

      await waitFor(() => {
        expect(findingsStatus()).toHaveTextContent(
          "Descartado como falso positivo: Duración del compás, compás 3. La partitura no cambia.",
        );
      });
      expect(within(panel()).queryByText(/no se pudieron cargar/i)).toBeNull();
      expect(within(panel()).getByText(/descartados como falso positivo · 1/i)).toBeVisible();
      expect(markCount()).toBe(1);
    });

    it("si el descartado era de una validación anterior a la última, lo dice con la lista nueva", async () => {
      const server = editableApi(detail(), { findings: [finding(1, 2)] });
      renderPage();
      await userEvent.click(
        await within(await screen.findByRole("region", { name: "Posibles errores" })).findByRole(
          "button",
          { name: "Descartar como falso positivo · Duración del compás, compás 2" },
        ),
      );
      // Otra pestaña revalidó: el servidor acepta el descarte del hallazgo viejo, pero la última
      // validación tiene otro.
      server.respondFinding(() =>
        jsonResponse(finding(1, 2, { status: "dismissed", dismissed_by: "ana" })),
      );
      server.setFindings([finding(4, 2)]);

      await userEvent.click(submit());

      await waitFor(() => {
        expect(findingsStatus()).toHaveTextContent(
          "Se descartó, pero ese posible error era de una validación anterior a la última, hecha en otra pestaña o dispositivo: ya ves la lista actual.",
        );
      });
      expect(dismissTrigger("Duración del compás, compás 2")).toHaveAttribute("data-dismiss", "4");
      expect(within(panel()).queryByText(/descartados como falso positivo/i)).toBeNull();
      expect(heading()).toHaveFocus();
    });

    it("si la lista es de un estado posterior al que se ve, lo dice y deja recargar la sesión", async () => {
      const server = editableApi(detail(), { findings: [finding(1, 2)] });
      renderPage();
      await userEvent.click(
        await within(await screen.findByRole("region", { name: "Posibles errores" })).findByRole(
          "button",
          { name: "Descartar como falso positivo · Duración del compás, compás 2" },
        ),
      );
      // Otra pestaña editó y revalidó: el hallazgo que se ve ya no está y la lista es del estado 1.
      server.replace(
        apply(server.current(), {
          base_seq: 0,
          op: "SetPitch",
          anchor: anchorOf(3),
          before: null,
          after: { pitch: "E4" },
        }).next,
      );
      server.setFindings([finding(5, 1, { at_seq: 1 })]);

      await userEvent.click(submit());

      expect(
        await within(panel()).findByText(/corresponden a un estado de la partitura posterior/i),
      ).toBeVisible();
      await userEvent.click(within(panel()).getByRole("button", { name: "Recargar la sesión" }));

      await waitFor(() => {
        expect(screen.getByText("Ediciones").nextElementSibling).toHaveTextContent("1");
      });
      expect(within(panel()).queryByText(/posterior al que ves/i)).toBeNull();
      expect(heading()).toHaveFocus();
    });

    it("un 409 al descartar porque la sesión se finalizó lo dice y la deja en solo lectura", async () => {
      const server = editableApi(detail(), { findings: [finding(1, 2)] });
      renderPage();
      await userEvent.click(
        await within(await screen.findByRole("region", { name: "Posibles errores" })).findByRole(
          "button",
          { name: "Descartar como falso positivo · Duración del compás, compás 2" },
        ),
      );
      server.replace({ ...server.current(), status: "finalized" });

      await userEvent.click(submit());

      await waitFor(() => {
        expect(findingsStatus()).toHaveTextContent(
          "No se descartó: la sesión está finalizada y sus posibles errores ya no se pueden cambiar.",
        );
      });
      await waitFor(() => {
        expect(within(panel()).queryByRole("button", { name: /^descartar/i })).toBeNull();
      });
      expect(screen.getByText(/sesión finalizada: solo lectura/i)).toBeVisible();
      expect(markCount()).toBe(1);
    });

    it("si el posible error ya no está (404), lo dice y vuelve a cargar la lista", async () => {
      const server = editableApi(detail(), { findings: [finding(1, 2)] });
      renderPage();
      await userEvent.click(
        await within(await screen.findByRole("region", { name: "Posibles errores" })).findByRole(
          "button",
          { name: "Descartar como falso positivo · Duración del compás, compás 2" },
        ),
      );
      // Otra pestaña revalidó el mismo estado: sus hallazgos tienen otro id.
      server.setFindings([finding(4, 2)]);

      await userEvent.click(submit());

      await waitFor(() => {
        expect(findingsStatus()).toHaveTextContent(
          "No se descartó: ese posible error ya no está en la última validación. Ya ves la lista actual.",
        );
      });
      expect(server.count(`GET /sessions/${ID}/findings`)).toBe(2);
      expect(within(panel()).queryByRole("textbox")).toBeNull();
      expect(dismissTrigger("Duración del compás, compás 2")).toBeVisible();
    });

    it("sin respuesta al descartar no lo da por descartado y conserva el motivo", async () => {
      const server = editableApi(detail(), { findings: [finding(1, 2)] });
      renderPage();
      await userEvent.click(
        await within(await screen.findByRole("region", { name: "Posibles errores" })).findByRole(
          "button",
          { name: "Descartar como falso positivo · Duración del compás, compás 2" },
        ),
      );
      await userEvent.type(reasonField(), "Igual que el original");
      server.respondFinding(() => Promise.reject(new TypeError("Failed to fetch")));

      await userEvent.click(submit());

      await waitFor(() => {
        expect(findingsStatus()).toHaveTextContent(
          "No llegó la confirmación: no se sabe si se descartó. No se pudo conectar con el servidor. Comprueba la conexión. Puedes volver a intentarlo.",
        );
      });
      expect(reasonField()).toHaveValue("Igual que el original");
      expect(markCount()).toBe(1);
      expect(submit()).not.toHaveAttribute("aria-disabled", "true");
    });

    it("un fallo al revalidar lo dice y deja volver a intentarlo", async () => {
      const server = editableApi(editedDetail(), { findings: [finding(1, 2)] });
      renderPage();
      server.respondValidate(() => jsonResponse({ detail: "fallo" }, 500));
      const revalidate = await within(
        await screen.findByRole("region", { name: "Posibles errores" }),
      ).findByRole("button", { name: "Revalidar" });

      await userEvent.click(revalidate);

      await waitFor(() => {
        expect(findingsStatus()).toHaveTextContent(
          "No llegó la confirmación: no se sabe si se revalidó. El servidor tuvo un problema. Inténtalo de nuevo en un momento. Puedes volver a intentarlo.",
        );
      });
      expect(revalidate).not.toHaveAttribute("aria-disabled", "true");
      expect(revalidate).toHaveFocus();
      expect(markCount()).toBe(1);
    });

    it("mientras se descarta no se restaura ni se revalida", async () => {
      const server = editableApi(editedDetail(), {
        findings: [finding(1, 2), dismissedFinding(2, 3)],
      });
      renderPage();
      await userEvent.click(
        await within(await screen.findByRole("region", { name: "Posibles errores" })).findByRole(
          "button",
          { name: "Descartar como falso positivo · Duración del compás, compás 2" },
        ),
      );
      const pending = deferred<Response>();
      server.respondFinding(() => pending.promise);
      await userEvent.click(submit());
      await userEvent.click(within(panel()).getByText(/descartados como falso positivo · 1/i));

      const restore = within(panel()).getByRole("button", {
        name: "Restaurar · Duración del compás, compás 3",
      });
      const revalidate = within(panel()).getByRole("button", { name: "Revalidar" });
      expect(restore).toHaveAttribute("aria-disabled", "true");
      expect(revalidate).toHaveAttribute("aria-disabled", "true");
      await userEvent.click(restore);
      await userEvent.click(revalidate);

      expect(server.findingCalls).toHaveLength(1);
      expect(server.count(`POST /sessions/${ID}/validate`)).toBe(0);
      pending.resolve(
        server.acceptFinding(`POST /sessions/${ID}/findings/1/dismiss`, { reason: null }),
      );
      await waitFor(() => {
        expect(restore).not.toHaveAttribute("aria-disabled", "true");
      });
    });

    it("si se sale de la vista con un descarte en curso, al volver la lista ya lo tiene", async () => {
      const server = editableApi(detail(), { findings: [finding(1, 2), finding(2, 3)] });
      const router = renderPage();
      await userEvent.click(
        await within(await screen.findByRole("region", { name: "Posibles errores" })).findByRole(
          "button",
          { name: "Descartar como falso positivo · Duración del compás, compás 3" },
        ),
      );
      const pending = deferred<Response>();
      server.respondFinding(() => pending.promise);
      await userEvent.click(submit());

      await act(() => router.navigate("/transcripcion"));
      pending.resolve(
        server.acceptFinding(`POST /sessions/${ID}/findings/2/dismiss`, { reason: null }),
      );
      await act(() => router.navigate(`/sesiones/${ID}`));

      const region = await screen.findByRole("region", { name: "Posibles errores" });
      expect(
        await within(region).findByText(/descartados como falso positivo · 1/i),
      ).toBeInTheDocument();
      expect(within(region).queryByRole("button", { name: /^compás 3/i })).toBeNull();
    });

    it("Ctrl+Z en el motivo es el deshacer del campo, no el de la partitura", async () => {
      const server = editableApi(editedDetail(), { findings: [finding(1, 2)] });
      renderPage();
      await userEvent.click(
        await within(await screen.findByRole("region", { name: "Posibles errores" })).findByRole(
          "button",
          { name: "Descartar como falso positivo · Duración del compás, compás 2" },
        ),
      );

      fireEvent.keyDown(reasonField(), ctrlKey("z"));

      expect(server.count(`POST /sessions/${ID}/undo`)).toBe(0);
      expect(reasonField()).toHaveFocus();
    });

    it("en solo lectura se ven los posibles errores, pero no se descartan, restauran ni revalidan", async () => {
      editableApi(editedDetail({ owner_id: LUIS.id }), {
        findings: [finding(1, 2), dismissedFinding(2, 3, "Así está")],
      });
      renderPage(INVESTIGADORA);
      expect(
        await within(await screen.findByRole("region", { name: "Posibles errores" })).findByText(
          /después se editó y todavía no se ha vuelto a validar/i,
        ),
      ).toBeVisible();
      await userEvent.click(within(panel()).getByText(/descartados como falso positivo · 1/i));

      expect(within(panel()).getByText("Motivo: Así está")).toBeVisible();
      expect(within(panel()).queryByRole("button", { name: /^descartar/i })).toBeNull();
      expect(within(panel()).queryByRole("button", { name: /^restaurar/i })).toBeNull();
      expect(within(panel()).queryByRole("button", { name: "Revalidar" })).toBeNull();
      expect(within(panel()).queryByText(/descartar un posible error no corrige/i)).toBeNull();
    });

    it("una sesión finalizada tampoco ofrece descartar ni revalidar", async () => {
      editableApi(editedDetail({ status: "finalized" }), { findings: [finding(1, 2)] });
      renderPage();
      expect(
        await within(await screen.findByRole("region", { name: "Posibles errores" })).findByText(
          /después se editó/i,
        ),
      ).toBeVisible();
      expect(within(panel()).queryByRole("button", { name: /^descartar/i })).toBeNull();
      expect(within(panel()).queryByRole("button", { name: "Revalidar" })).toBeNull();
    });
  });

  describe("finalizar y reabrir la sesión (#187)", () => {
    type LifecycleRoute = () => Response | Promise<Response>;
    const findingsPanel = () => screen.getByRole("region", { name: "Posibles errores" });
    const lifecycleStatus = () => document.querySelector(".lifecycle__status");
    const finalizeButton = () => screen.getByRole("button", { name: "Finalizar la corrección" });
    const confirmButton = () => screen.getByRole("button", { name: "Sí, finalizar" });
    const confirmation = () => screen.queryByRole("group", { name: "Confirmar la finalización" });
    const reopenButton = () => screen.getByRole("button", { name: "Reabrir la sesión" });
    const meta = () => document.querySelector(".session__meta");
    const dismissedFinding = (id: number, measureNumber: number) =>
      finding(id, measureNumber, {
        status: "dismissed",
        dismissed_at: "2026-10-24T11:00:00",
        dismissed_by: "ana",
        dismissal_reason: null,
      });

    /**
     * La API editable con finalizar y reabrir como el servidor: finalizar valida el estado actual
     * conservando los descartes (D65) y responde solo los activos, o 409 si ya está finalizada.
     */
    function lifecycleApi(
      start: SessionDetailRead = detail(),
      options: { findings?: FindingRead[] } = {},
    ) {
      const server = editableApi(start, { findings: options.findings });
      const inner = server.fetchMock.getMockImplementation();
      if (!inner) throw new Error("falta la API");
      const lifecycleCalls: string[] = [];
      const finalizeQueue: LifecycleRoute[] = [];
      const acceptFinalize = () => {
        const current = server.current();
        if (current.status === "finalized") {
          return jsonResponse({ detail: "La sesión está finalizada" }, 409);
        }
        const seq = current.current_seq ?? 0;
        const final = (options.findings ?? []).map((candidate) => ({ ...candidate, at_seq: seq }));
        server.setFindings(final);
        server.replace({ ...current, status: "finalized" });
        return jsonResponse({
          session_id: ID,
          status: "finalized",
          final_seq: seq,
          findings: final.filter((candidate) => candidate.status === "active"),
        });
      };
      const acceptReopen = () => {
        const current = server.current();
        const status = current.edits.length > 0 ? "correcting" : "transcribed";
        server.replace({ ...current, status });
        return jsonResponse({ session_id: ID, status, current_seq: current.current_seq ?? 0 });
      };
      vi.stubGlobal(
        "fetch",
        vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
          const href =
            input instanceof Request ? input.url : input instanceof URL ? input.href : input;
          const path = new URL(href, "http://localhost").pathname.replace(/^\/api/, "");
          if (init?.method === "POST" && path === `/sessions/${ID}/finalize`) {
            lifecycleCalls.push("finalize");
            return Promise.resolve((finalizeQueue.shift() ?? acceptFinalize)());
          }
          if (init?.method === "POST" && path === `/sessions/${ID}/reopen`) {
            lifecycleCalls.push("reopen");
            return Promise.resolve(acceptReopen());
          }
          return inner(input, init);
        }),
      );
      return {
        ...server,
        lifecycleCalls,
        acceptFinalize,
        respondFinalize(route: LifecycleRoute) {
          finalizeQueue.push(route);
        },
      };
    }

    async function finalize() {
      await userEvent.click(await screen.findByRole("button", { name: "Finalizar la corrección" }));
      await userEvent.click(confirmButton());
    }

    it("finaliza tras confirmarlo, con la validación final a la vista y en solo lectura", async () => {
      const server = lifecycleApi(detail(), {
        findings: [finding(1, 1), dismissedFinding(2, 3)],
      });
      renderPage();
      await chooseMeasure(2);
      expect(button("Subir un paso")).toBeVisible();

      // Nada sale sin confirmarlo, y la confirmación se puede cancelar con Esc.
      await userEvent.click(finalizeButton());
      expect(finalizeButton()).toHaveAttribute("aria-expanded", "true");
      expect(confirmButton()).toHaveFocus();
      expect(confirmation()).toHaveTextContent(
        "Se validará la partitura tal como está y la sesión quedará en solo lectura",
      );
      expect(confirmation()).toHaveTextContent("Si se te pasó algo, podrás reabrirla.");
      await userEvent.keyboard("{Escape}");
      expect(confirmation()).toBeNull();
      expect(finalizeButton()).toHaveFocus();
      expect(server.lifecycleCalls).toEqual([]);

      await userEvent.click(finalizeButton());
      const pending = deferred<Response>();
      server.respondFinalize(() => pending.promise);
      await userEvent.click(confirmButton());

      // Sin la respuesta no se da por finalizada; mientras tanto, nada más sale.
      expect(lifecycleStatus()).toHaveTextContent("Finalizando…");
      expect(meta()).toHaveTextContent("Transcrita");
      expect(confirmButton()).toHaveAttribute("aria-disabled", "true");
      expect(button("Subir un paso")).toHaveAttribute("aria-disabled", "true");
      expect(
        within(findingsPanel()).getByRole("button", {
          name: "Descartar como falso positivo · Duración del compás, compás 1",
        }),
      ).toHaveAttribute("aria-disabled", "true");
      fireEvent.click(button("Subir un paso"));

      pending.resolve(server.acceptFinalize());

      await waitFor(() => {
        expect(lifecycleStatus()).toHaveTextContent(
          "Sesión finalizada. Validación final: 1 posible error. 1 sigue descartado como falso positivo porque su nota no cambió. Si se te pasó algo, puedes reabrirla.",
        );
      });
      expect(meta()).toHaveTextContent("Finalizada");
      expect(screen.getByText(/reábrela para seguir corrigiendo/i)).toBeVisible();
      expect(screen.queryByRole("region", { name: "Corregir la nota elegida" })).toBeNull();
      expect(within(findingsPanel()).queryByRole("button", { name: /^descartar/i })).toBeNull();
      expect(
        within(findingsPanel()).getByText(/descartados como falso positivo · 1/i),
      ).toBeVisible();
      expect(screen.queryByRole("button", { name: "Finalizar la corrección" })).toBeNull();
      expect(reopenButton()).toHaveFocus();
      // Una sola finalización y ninguna corrección; no se recarga la sesión, solo su lista.
      expect(server.lifecycleCalls).toEqual(["finalize"]);
      expect(server.bodies).toHaveLength(0);
      expect(server.count(`GET /sessions/${ID}`)).toBe(1);
      expect(server.count(`GET /sessions/${ID}/findings`)).toBe(2);
    });

    it("tras finalizar, la barra deja de hablar de la última corrección; reabrir la vuelve editable", async () => {
      const server = lifecycleApi();
      renderPage();
      await chooseMeasure(2);
      fireEvent.click(button("Subir un paso"));
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent("Guardado: altura Re 4.");
      });

      await finalize();

      await waitFor(() => {
        expect(meta()).toHaveTextContent("Finalizada");
      });
      expect(lifecycleStatus()).toHaveTextContent(
        "Sesión finalizada. Validación final: el validador no señala ningún compás. Que no señale ninguno no garantiza que la transcripción esté bien.",
      );
      expect(screen.queryByRole("region", { name: "Corregir la nota elegida" })).toBeNull();
      expect(screen.queryByText(/Guardado/)).toBeNull();
      // Sin posibles errores, la lista es la de la partitura actual (ADR-0035 §7).
      expect(
        within(findingsPanel()).getByText(
          "El validador no señala ningún compás en la partitura actual.",
        ),
      ).toBeVisible();

      await userEvent.click(reopenButton());

      await waitFor(() => {
        expect(lifecycleStatus()).toHaveTextContent("Sesión reabierta: puedes seguir corrigiendo.");
      });
      expect(meta()).toHaveTextContent("En corrección");
      expect(finalizeButton()).toHaveFocus();
      expect(button("Subir un paso")).toHaveAttribute("aria-disabled", "false");
      expect(server.lifecycleCalls).toEqual(["finalize", "reopen"]);
      expect(server.count(`GET /sessions/${ID}`)).toBe(1);
    });

    it("tras un 409 de una corrección en una sesión finalizada, reabrir quita el aviso", async () => {
      const server = lifecycleApi();
      renderPage();
      await chooseMeasure(2);
      server.respond(() => {
        server.replace({ ...server.current(), status: "finalized" });
        return jsonResponse({ detail: "La sesión está cerrada" }, 409);
      });
      fireEvent.click(button("Subir un paso"));
      await waitFor(() => {
        expect(editStatus()).toHaveTextContent(
          "La sesión está finalizada y ya no admite correcciones.",
        );
      });

      await userEvent.click(reopenButton());

      await waitFor(() => {
        expect(lifecycleStatus()).toHaveTextContent("Sesión reabierta: puedes seguir corrigiendo.");
      });
      expect(screen.queryByText(/ya no admite correcciones/)).toBeNull();
      expect(button("Subir un paso")).toHaveAttribute("aria-disabled", "false");
    });

    it("si ya estaba finalizada en otra pestaña, lo dice con su mensaje y la deja en solo lectura", async () => {
      const server = lifecycleApi();
      renderPage();
      server.respondFinalize(() => {
        server.replace({ ...server.current(), status: "finalized" });
        return jsonResponse(
          { detail: "La sesión está finalizada y no admite más ediciones." },
          409,
        );
      });

      await finalize();

      await waitFor(() => {
        expect(lifecycleStatus()).toHaveTextContent(
          "No se volvió a finalizar: la sesión ya estaba finalizada, quizá desde otra pestaña o dispositivo. Ya ves su estado.",
        );
      });
      expect(meta()).toHaveTextContent("Finalizada");
      expect(screen.queryByText(/no admite más ediciones/)).toBeNull();
      expect(reopenButton()).toHaveFocus();
      expect(server.lifecycleCalls).toEqual(["finalize"]);
    });

    it("si el servidor iba por un estado posterior, finaliza ese estado y lo carga", async () => {
      const server = lifecycleApi();
      renderPage();
      await screen.findByRole("button", { name: "Finalizar la corrección" });
      server.respondFinalize(() => {
        // Otra pestaña editó: el servidor finaliza su estado, no el que se ve.
        server.replace(
          apply(server.current(), {
            base_seq: 0,
            op: "SetPitch",
            anchor: anchorOf(1),
            before: null,
            after: { pitch: "D4" },
          }).next,
        );
        return server.acceptFinalize();
      });

      await finalize();

      await waitFor(() => {
        expect(lifecycleStatus()).toHaveTextContent(
          "La sesión iba por un estado posterior al que se veía (tras 1 edición): se finalizó ese estado, que ya ves. Validación final: el validador no señala ningún compás.",
        );
      });
      expect(meta()).toHaveTextContent("Finalizada");
      expect(meta()).toHaveTextContent(/Ediciones\s*1/);
      expect(reopenButton()).toHaveFocus();
    });

    it("sin respuesta dice que no se sabe si se finalizó y deja volver a intentarlo", async () => {
      const server = lifecycleApi();
      renderPage();
      server.respondFinalize(() => Promise.reject(new TypeError("Failed to fetch")));

      await finalize();

      await waitFor(() => {
        expect(lifecycleStatus()).toHaveTextContent(
          "No llegó la confirmación: no se sabe si se finalizó.",
        );
      });
      expect(lifecycleStatus()).toHaveTextContent("Puedes volver a intentarlo.");
      // Se vuelve a pedir el detalle por si se finalizó: no, y sigue abierta.
      await waitFor(() => {
        expect(server.count(`GET /sessions/${ID}`)).toBe(2);
      });
      expect(meta()).toHaveTextContent("Transcrita");
      expect(finalizeButton()).toHaveFocus();
      expect(confirmation()).toBeNull();
    });

    it("tras el 409, la lista que se ve es la de la finalización que ya había, no la vieja", async () => {
      const server = lifecycleApi(detail(), { findings: [finding(1, 1)] });
      renderPage();
      await screen.findByRole("button", { name: /^compás 1/i });
      server.respondFinalize(() => {
        // Otra pestaña descartó el posible error y finalizó: su lista final tiene otro id.
        server.setFindings([dismissedFinding(7, 1)]);
        server.replace({ ...server.current(), status: "finalized" });
        return jsonResponse({ detail: "La sesión está finalizada" }, 409);
      });

      await finalize();

      await waitFor(() => {
        expect(lifecycleStatus()).toHaveTextContent("Ya ves su estado.");
      });
      expect(within(findingsPanel()).queryByRole("button", { name: /^compás 1/i })).toBeNull();
      expect(
        within(findingsPanel()).getByText(/descartados como falso positivo · 1/i),
      ).toBeVisible();
    });

    it("sin respuesta, si la sesión sí quedó finalizada, lo dice y muestra su lista final", async () => {
      const server = lifecycleApi(detail(), { findings: [finding(1, 1)] });
      renderPage();
      await screen.findByRole("button", { name: /^compás 1/i });
      server.respondFinalize(() => {
        server.setFindings([dismissedFinding(7, 1)]);
        server.replace({ ...server.current(), status: "finalized" });
        return Promise.reject(new TypeError("Failed to fetch"));
      });

      await finalize();

      await waitFor(() => {
        expect(lifecycleStatus()).toHaveTextContent(
          "No llegó la confirmación, pero la sesión está finalizada: ya ves su estado y la lista de su validación final.",
        );
      });
      expect(meta()).toHaveTextContent("Finalizada");
      expect(within(findingsPanel()).queryByRole("button", { name: /^compás 1/i })).toBeNull();
      expect(reopenButton()).toHaveFocus();
    });

    it("tras un 409 de otra pestaña, finalizar quita «Volver a aplicar»", async () => {
      const server = lifecycleApi();
      renderPage();
      await chooseMeasure(2);
      server.respond((body) => {
        server.replace(
          apply(server.current(), { ...body, anchor: anchorOf(1), after: { pitch: "E4" } }).next,
        );
        return jsonResponse({ detail: "conflicto" }, 409);
      });
      fireEvent.click(button("Subir un paso"));
      await within(editor()).findByRole("button", { name: "Volver a aplicar" });

      await finalize();

      await waitFor(() => {
        expect(meta()).toHaveTextContent("Finalizada");
      });
      expect(screen.queryByRole("button", { name: "Volver a aplicar" })).toBeNull();
      expect(screen.queryByRole("region", { name: "Corregir la nota elegida" })).toBeNull();
    });

    it("mientras se guarda una corrección, finalizar espera", async () => {
      const server = lifecycleApi();
      renderPage();
      await chooseMeasure(2);
      const pending = deferred<Response>();
      server.respond(() => pending.promise);
      fireEvent.click(button("Subir un paso"));
      await userEvent.click(finalizeButton());

      expect(confirmButton()).toHaveAttribute("aria-disabled", "true");
      expect(confirmation()).toHaveTextContent("Espera a que termine lo que está en curso.");
      await userEvent.click(confirmButton());
      expect(server.lifecycleCalls).toEqual([]);

      const [sent] = server.bodies;
      if (!sent) throw new Error("no salió la corrección");
      pending.resolve(server.accept(sent));
      await waitFor(() => {
        expect(confirmButton()).not.toHaveAttribute("aria-disabled");
      });
      await userEvent.click(confirmButton());
      await waitFor(() => {
        expect(meta()).toHaveTextContent("Finalizada");
      });
      expect(server.lifecycleCalls).toEqual(["finalize"]);
    });

    it("en una sesión no asistida no habla del validador (ADR-0040 §13)", async () => {
      const server = lifecycleApi(detail({ condition: "unassisted" }));
      renderPage();
      await userEvent.click(await screen.findByRole("button", { name: "Finalizar la corrección" }));
      expect(confirmation()).toHaveTextContent(
        "¿Das por terminada la corrección? La sesión quedará en solo lectura. Si se te pasó algo, podrás reabrirla.",
      );

      await userEvent.click(confirmButton());

      await waitFor(() => {
        expect(lifecycleStatus()).toHaveTextContent(
          /^Sesión finalizada\. Si se te pasó algo, puedes reabrirla\.\s?$/,
        );
      });
      expect(server.lifecycleCalls).toEqual(["finalize"]);
    });

    it("solo la persona que la transcribió puede finalizarla o reabrirla", async () => {
      lifecycleApi(detail({ status: "finalized" }));
      renderPage(INVESTIGADORA);
      await screen.findByText(/sesión de otra persona/i);
      expect(screen.queryByRole("button", { name: "Reabrir la sesión" })).toBeNull();
      expect(screen.queryByRole("button", { name: "Finalizar la corrección" })).toBeNull();
    });
  });
});
