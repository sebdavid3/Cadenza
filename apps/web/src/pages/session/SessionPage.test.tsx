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
import type { FindingRead, SessionDetailRead, TimingMapRead, UserRead } from "../../types";

// OSMD no se puede dibujar en jsdom: un doble con la misma forma de lo que la vista lee. Cada
// compás mide 20 unidades desde x = 10 + 20 × compás; sus figuras se dibujan desde 5 unidades
// después, cada 5, con la cabeza (1,2 × 1,05 unidades) centrada en su posición.
const osmd = vi.hoisted(() => ({
  measures: 3,
  fail: false,
  cleared: 0,
  zooms: [] as number[],
  loaded: [] as string[],
  /** Figuras de cada compás: altura (null, silencio) y duración en redondas, como OSMD. */
  figures: null as { pitch: string | null; whole: [number, number] }[][] | null,
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
  function figure(
    svg: Element,
    pitch: string | null,
    whole: [number, number],
    x: number,
    zoom: number,
  ) {
    const match = pitch === null ? null : /^([A-G])(#?)(\d)$/.exec(pitch);
    const midi = match
      ? 12 * (Number(match[3]) + 1) + (STEPS[match[1] ?? "C"] ?? 0) + (match[2] ?? "").length
      : 0;
    const y = 7;
    const unit = 10 * zoom;
    const group = svgBox(
      svg,
      "vf-stavenote",
      DOMRect.fromRect({
        x: (x - 0.6) * unit,
        y: (y - 0.5) * unit,
        width: 1.2 * unit,
        height: 3.5 * unit,
      }),
    );
    if (match) {
      svgBox(
        group,
        "vf-notehead",
        DOMRect.fromRect({
          x: (x - 0.6) * unit,
          y: (y - 0.5) * unit,
          width: 1.2 * unit,
          height: 1.05 * unit,
        }),
      );
    }
    const note = {
      sourceNote: {
        isRest: () => pitch === null,
        Length: { GetExpandedNumerator: () => whole[0], Denominator: whole[1] },
        Pitch: match
          ? { getHalfTone: () => midi - 12, FundamentalNote: STEPS[match[1] ?? "C"] }
          : undefined,
      },
      PositionAndShape: { AbsolutePosition: { x, y } },
      getSVGGElement: () => group,
    };
    return {
      graphicalVoiceEntries: [
        { parentVoiceEntry: { ParentVoice: { VoiceId: 1 }, IsGrace: false }, notes: [note] },
      ],
    };
  }
  return {
    OpenSheetMusicDisplay: class {
      zoom = 1;
      GraphicSheet = { MeasureList: [] as unknown[][] };
      EngravingRules = { PageBottomMargin: 10 };
      constructor(readonly host: HTMLElement) {}
      load(document: Document) {
        osmd.loaded.push(document.documentElement.nodeName);
        return osmd.fail ? Promise.reject(new Error("MusicXML no válido")) : Promise.resolve({});
      }
      render() {
        osmd.zooms.push(this.zoom);
        this.host.replaceChildren();
        const svg = document.createElementNS(SVG, "svg");
        this.host.appendChild(svg);
        this.GraphicSheet.MeasureList = Array.from({ length: osmd.measures }, (_unused, index) => {
          const left = 10 + index * 20;
          const figures = osmd.figures?.[index] ?? [{ pitch: "C4", whole: [3, 4] }];
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
                figure(svg, drawn.pitch, drawn.whole, left + 5 + position * 5, this.zoom),
              ),
            },
          ];
        });
      }
      clear() {
        osmd.cleared += 1;
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
      readonly playback: { notes: unknown[]; measures: Span[]; totalBeats: number },
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
    zooms: [],
    loaded: [],
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
    const item = within(list).getByRole("button", { name: /compás 2/i });
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

  it("al elegir un compás de la lista lo resalta en la partitura", async () => {
    api({ findings: [finding(1, 1), finding(2, 3)] });
    renderPage();
    const button = await screen.findByRole("button", { name: /compás 3/i });
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
    expect(screen.getByRole("button", { name: /compás 2/i })).toBeVisible();
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
    api({ detail: detail({ current_seq: 4, edits: [{} as SessionDetailRead["edits"][number]] }) });
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
    expect(await screen.findByRole("button", { name: /compás 1/i })).toBeVisible();
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
    expect(screen.queryByRole("button", { name: /compás 2/i })).toBeNull();
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
    staff.measures[0].events = [1, 2, 3].map(() => ({ ...first, duration_beats: "1" }));
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

  it("los botones de la barra mueven la selección en una pantalla táctil", async () => {
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
