import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import { routes } from "../../router";
import { ANA, jsonResponse, mockApi, resetAuth, signInAs } from "../../test/auth-helpers";
import type { FindingRead, SessionDetailRead, UserRead } from "../../types";

// OSMD no se puede dibujar en jsdom: un doble con la misma forma de lo que la vista lee.
const osmd = vi.hoisted(() => ({ measures: 3, fail: false, cleared: 0, loaded: [] as string[] }));
vi.mock("opensheetmusicdisplay", () => ({
  OpenSheetMusicDisplay: class {
    zoom = 1;
    GraphicSheet = { MeasureList: [] as unknown[][] };
    EngravingRules = { PageBottomMargin: 10 };
    constructor(readonly host: HTMLElement) {}
    load(xml: string) {
      osmd.loaded.push(xml);
      return osmd.fail ? Promise.reject(new Error("MusicXML no válido")) : Promise.resolve({});
    }
    render() {
      this.host.appendChild(document.createElementNS("http://www.w3.org/2000/svg", "svg"));
      this.GraphicSheet.MeasureList = Array.from({ length: osmd.measures }, (_unused, index) => [
        {
          PositionAndShape: {
            AbsolutePosition: { x: 10 + index * 20, y: 5 },
            BorderLeft: 0,
            BorderRight: 20,
            BorderTop: 0,
            BorderBottom: 4,
          },
        },
      ]);
    }
    clear() {
      osmd.cleared += 1;
    }
  },
}));

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

const XML = "<score-partwise>…</score-partwise>";
const png = () =>
  new Response(new Uint8Array([1, 2]), { headers: { "Content-Type": "image/png" } });

function api(
  options: {
    detail?: SessionDetailRead;
    findings?: FindingRead[];
    exportStatus?: number;
    status?: number;
  } = {},
) {
  return mockApi({
    [`GET /sessions/${ID}`]: () =>
      options.status
        ? jsonResponse({ detail: "Sesión no encontrada" }, options.status)
        : jsonResponse(options.detail ?? detail()),
    [`GET /sessions/${ID}/findings`]: () => jsonResponse(options.findings ?? []),
    [`GET /sessions/${ID}/export`]: () =>
      options.exportStatus
        ? jsonResponse({ detail: "fallo" }, options.exportStatus)
        : new Response(XML, { headers: { "Content-Type": "application/vnd.recordare.musicxml" } }),
    [`GET /sessions/${ID}/image`]: png,
    "GET /users": () => jsonResponse([ANA, LUIS, INVESTIGADORA]),
  });
}

function renderPage(user: UserRead = ANA) {
  signInAs(user);
  const router = createMemoryRouter(routes, { initialEntries: [`/sesiones/${ID}`] });
  render(<RouterProvider router={router} />);
  return router;
}

let createObjectURL: MockInstance<typeof URL.createObjectURL>;
let revokeObjectURL: MockInstance<typeof URL.revokeObjectURL>;
const scrollIntoView = vi.fn();

beforeEach(() => {
  resetAuth();
  Object.assign(osmd, { measures: 3, fail: false, cleared: 0, loaded: [] });
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
    expect(screen.getByRole("img", { name: /posibles errores: 2/i })).toBeInTheDocument();
    expect(osmd.loaded).toEqual([XML]);

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

    expect(await screen.findByText("El validador no ha señalado ningún compás.")).toBeVisible();
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
    expect(screen.getByRole("button", { name: /compás 2/i })).toBeVisible();
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

  it("responde igual a una sesión inexistente que a una ajena", async () => {
    api({ status: 404 });
    renderPage(LUIS);

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
