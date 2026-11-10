import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "../../auth/store";
import { routes } from "../../router";
import {
  ANA,
  deferred,
  fakeJwt,
  hangUntilAborted,
  jsonResponse,
  mockApi,
  resetAuth,
  signInAs,
} from "../../test/auth-helpers";
import type { SessionDetailRead, TimingMapRead } from "../../types";
import { PENDING_UPLOAD_KEY, useLandingUpload } from "./uploadStore";

// OSMD no dibuja en jsdom: la partitura es un doble que dice qué estado recibe y si deja elegir.
vi.mock("../session/ScoreView", () => ({
  ScoreView: (props: { snapshot: { xml: string; seq: number }; notesSelectable?: boolean }) => (
    <div
      data-testid="partitura"
      data-xml={props.snapshot.xml}
      data-seq={props.snapshot.seq}
      data-selectable={String(props.notesSelectable ?? true)}
    />
  ),
}));
// Tone.js no suena en jsdom.
vi.mock("../session/toneEngine", () => ({
  createToneEngine: () => ({
    play: () => Promise.resolve(),
    pause: () => undefined,
    stop: () => undefined,
    setTempo: () => undefined,
    update: () => undefined,
    dispose: () => undefined,
  }),
}));

const ID = "5c1f0e8e-2b7d-4a52-9e0c-3f4a5b6c7d8e";
const XML = "<score-partwise>portada</score-partwise>";

function detail(changes: Partial<SessionDetailRead> = {}): SessionDetailRead {
  const measure = {
    number: 1,
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
  return {
    session_id: ID,
    document_id: "homr-1",
    omr_engine: "homr",
    document: {} as SessionDetailRead["document"],
    findings: [],
    edits: [],
    current_score: {
      parts: [{ id: "part-0", staves: [{ id: "part-0-staff-0", measures: [measure] }] }],
    } as SessionDetailRead["current_score"],
    current_seq: 0,
    anchor_index: null,
    image_artifact: "img",
    status: "transcribed",
    condition: "assisted",
    test_score_id: null,
    owner_id: ANA.id,
    title: "Minueto",
    source_filename: "minueto.png",
    ...changes,
  };
}

const timing: TimingMapRead = {
  session_id: ID,
  total_beats: "3",
  measure_offsets: { "1": "0" },
  events: [
    {
      anchor: {
        part: 0,
        staff: 0,
        measure: 1,
        voice: 0,
        event_index: 0,
        staff_id: "part-0-staff-0",
        bbox: null,
        confidence: null,
      },
      kind: "note",
      measure_number: 1,
      voice: 0,
      offset_beats: "0",
      duration_beats: "3",
      measure_offset_beats: "0",
    },
  ],
};

function transcribed(changes: Record<string, unknown> = {}) {
  return {
    session_id: ID,
    document_id: "homr-1",
    omr_engine: "homr",
    findings_count: 2,
    condition: "assisted",
    test_score_id: null,
    ...changes,
  };
}

/** Lo que la portada pide de la sesión recién creada para enseñarla. */
const sessionRoutes = (state: SessionDetailRead = detail()) => ({
  [`GET /sessions/${ID}`]: () => jsonResponse(state),
  [`GET /sessions/${ID}/export`]: () =>
    new Response(XML, { headers: { "Content-Type": "application/vnd.recordare.musicxml+xml" } }),
  [`GET /sessions/${ID}/timing`]: () => jsonResponse(timing),
});

/** Contraseña de prueba generada en cada uso: ninguna va escrita en el código. */
const secret = () => `p-${crypto.randomUUID()}`;

function png(name = "minueto.png", size = 8) {
  return new File([new Uint8Array(size)], name, { type: "image/png" });
}

function renderAt(path = "/") {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(<RouterProvider router={router} />);
  return router;
}

function box() {
  return screen.getByRole("region", { name: /transcribe una partitura/i });
}

/** El resultado, cuando se vuelve a la portada tras entrar (la vista tarda un paso en montarse). */
async function resultAfterReturn() {
  const landing = await screen.findByRole("region", { name: /transcribe una partitura/i });
  return within(landing).findByRole("region", { name: "Minueto" });
}

function fileInput(): HTMLInputElement {
  const input = box().querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) throw new Error("falta el selector de archivos de la portada");
  return input;
}

/** El formulario que se envió a `POST /transcribe`. */
function sentForm(calls: { key: string; init: RequestInit | undefined }[]): FormData {
  const call = calls.find((candidate) => candidate.key === "POST /transcribe");
  if (!call || !(call.init?.body instanceof FormData)) throw new Error("no se envió la imagen");
  return call.init.body;
}

const scrollIntoView = vi.fn();

beforeEach(() => {
  scrollIntoView.mockClear();
  resetAuth();
  useLandingUpload.getState().reset();
  // jsdom no desplaza: la vuelta de entrar trae la sección a la vista.
  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
    value: scrollIntoView,
    configurable: true,
    writable: true,
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
  useLandingUpload.getState().reset();
});

describe("recuadro de la portada (#277)", () => {
  it("con sesión, transcribe con el nombre y enseña la partitura en solo lectura, la reproducción, los posibles errores y «Editar»", async () => {
    const { calls } = mockApi({
      "POST /transcribe": () => jsonResponse(transcribed(), 201),
      ...sessionRoutes(),
    });
    signInAs(ANA);
    renderAt();

    // Soltada en la zona: con el selector, user-event devuelve el foco al campo de archivo.
    const zone = within(box()).getByText(/o arrástrala aquí/i).parentElement;
    if (!zone) throw new Error("falta la zona de subida");
    fireEvent.drop(zone, { dataTransfer: { files: [png()], types: ["Files"] } });
    const name = within(box()).getByLabelText(/nombre de la partitura/i);
    expect(name).toHaveFocus();
    await userEvent.type(name, "  Minueto ");
    await userEvent.click(within(box()).getByRole("button", { name: "Transcribir la imagen" }));

    const result = await within(box()).findByRole("region", { name: "Minueto" });
    const form = sentForm(calls);
    expect((form.get("file") as File).name).toBe("minueto.png");
    expect(form.get("title")).toBe("Minueto");
    expect(within(result).getByText("2 posibles errores")).toBeVisible();
    expect(within(result).getByText(/las reglas no lo detectan todo/i)).toBeVisible();
    const score = await within(result).findByTestId("partitura");
    expect(score).toHaveAttribute("data-xml", XML);
    expect(score).toHaveAttribute("data-selectable", "false");
    expect(within(result).getByRole("button", { name: /reproducir/i })).toBeVisible();
    expect(within(result).getByRole("link", { name: /editar/i })).toHaveAttribute(
      "href",
      `/sesiones/${ID}`,
    );
    expect(within(result).getByRole("heading", { name: "Minueto" })).toHaveFocus();
    // La imagen ya está en el servidor: no se guarda en la portada.
    expect(useLandingUpload.getState().file).toBeNull();
    expect(sessionStorage.getItem(PENDING_UPLOAD_KEY)).toBeNull();
  });

  it("en una sesión no asistida no habla de posibles errores (ADR-0040)", async () => {
    mockApi({
      "POST /transcribe": () =>
        jsonResponse(transcribed({ condition: "unassisted", findings_count: 0 }), 201),
      ...sessionRoutes(detail({ condition: "unassisted" })),
    });
    signInAs(ANA);
    renderAt();

    await userEvent.upload(fileInput(), png());
    await userEvent.click(within(box()).getByRole("button", { name: "Transcribir la imagen" }));

    const result = await within(box()).findByRole("region", { name: "Minueto" });
    await within(result).findByTestId("partitura");
    expect(within(result).queryByText(/posible/i)).toBeNull();
  });

  it("mientras HOMR trabaja, dice qué transcribe y que puede tardar hasta 30 s", async () => {
    const pending = deferred<Response>();
    mockApi({ "POST /transcribe": () => pending.promise, ...sessionRoutes() });
    signInAs(ANA);
    renderAt();

    await userEvent.upload(fileInput(), png());
    await userEvent.click(within(box()).getByRole("button", { name: "Transcribir la imagen" }));

    const progress = within(box()).getByRole("status");
    expect(progress).toHaveTextContent("Transcribiendo «minueto.png»");
    expect(progress).toHaveTextContent(/30/);
    expect(progress).toHaveFocus();
    expect(within(box()).queryByRole("button", { name: /elegir/i })).toBeNull();

    await act(async () => {
      pending.resolve(jsonResponse(transcribed(), 201));
      await pending.promise;
    });
    expect(await within(box()).findByRole("region", { name: "Minueto" })).toBeVisible();
  });

  it("«Transcribir otra imagen» vuelve a empezar", async () => {
    mockApi({ "POST /transcribe": () => jsonResponse(transcribed(), 201), ...sessionRoutes() });
    signInAs(ANA);
    renderAt();
    await userEvent.upload(fileInput(), png());
    await userEvent.click(within(box()).getByRole("button", { name: "Transcribir la imagen" }));
    await within(box()).findByRole("region", { name: "Minueto" });

    await userEvent.click(within(box()).getByRole("button", { name: "Transcribir otra imagen" }));

    expect(within(box()).queryByRole("region", { name: "Minueto" })).toBeNull();
    expect(within(box()).getByRole("button", { name: "Elegir una imagen" })).toHaveFocus();
  });

  it("rechaza antes de enviar lo que no es una imagen PNG o JPEG, o pasa de 20 MB", async () => {
    const { calls } = mockApi({});
    signInAs(ANA);
    renderAt();

    await userEvent.upload(fileInput(), new File(["x"], "notas.txt", { type: "text/plain" }), {
      applyAccept: false,
    });
    expect(within(box()).getByRole("alert")).toHaveTextContent("No es una imagen PNG o JPEG.");
    expect(within(box()).queryByRole("form")).toBeNull();

    await userEvent.upload(fileInput(), png("grande.png", 20 * 1024 * 1024 + 1));
    expect(within(box()).getByRole("alert")).toHaveTextContent("Supera el tamaño máximo de 20 MB.");
    expect(calls.filter((call) => call.key === "POST /transcribe")).toHaveLength(0);
  });

  it("rechaza varias imágenes soltadas a la vez y remite a la transcripción por lotes", () => {
    mockApi({});
    signInAs(ANA);
    renderAt();
    const zone = within(box()).getByText(/o arrástrala aquí/i).parentElement;
    if (!zone) throw new Error("falta la zona de subida");

    fireEvent.drop(zone, {
      dataTransfer: { files: [png("a.png"), png("b.png")], types: ["Files"] },
    });

    expect(within(box()).getByRole("alert")).toHaveTextContent(/una imagen cada vez/i);
    expect(useLandingUpload.getState().file).toBeNull();
  });

  it("si vence la espera, dice que la sesión puede existir y enlaza a las sesiones", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      mockApi({ "POST /transcribe": (init) => hangUntilAborted(init) });
      signInAs(ANA);
      renderAt();
      const zone = within(box()).getByText(/o arrástrala aquí/i).parentElement;
      if (!zone) throw new Error("falta la zona de subida");
      fireEvent.drop(zone, { dataTransfer: { files: [png()], types: ["Files"] } });
      fireEvent.click(within(box()).getByRole("button", { name: "Transcribir la imagen" }));

      await act(async () => {
        await vi.advanceTimersByTimeAsync(31_000);
      });

      const alert = within(box()).getByRole("alert");
      expect(alert).toHaveTextContent(/puede que la sesión se haya creado/i);
      expect(within(alert).getByRole("link", { name: "Ver tus sesiones" })).toHaveAttribute(
        "href",
        "/transcripcion",
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it.each([
    ["un 422", () => jsonResponse({ detail: "nada" }, 422), /no se reconoció ninguna partitura/i],
    [
      "un 503 con Retry-After",
      () =>
        new Response(JSON.stringify({ detail: "ocupado" }), {
          status: 503,
          headers: { "Content-Type": "application/json", "Retry-After": "10" },
        }),
      /ocupado con otras transcripciones\. Vuelve a probar en 10 s/,
    ],
    ["un 413", () => jsonResponse({ detail: "grande" }, 413), /tamaño máximo/],
    ["un 415", () => jsonResponse({ detail: "tipo" }, 415), /PNG o JPEG/],
    [
      "un fallo de red",
      () => Promise.reject(new TypeError("Failed to fetch")),
      /no se pudo conectar con el servidor/i,
    ],
  ])(
    "con %s lo dice, conserva la imagen y deja volver a intentarlo",
    async (_label, failure, message) => {
      let attempt = 0;
      const { calls } = mockApi({
        "POST /transcribe": () => {
          attempt += 1;
          return attempt === 1 ? failure() : jsonResponse(transcribed(), 201);
        },
        ...sessionRoutes(),
      });
      signInAs(ANA);
      renderAt();
      await userEvent.upload(fileInput(), png());
      await userEvent.click(within(box()).getByRole("button", { name: "Transcribir la imagen" }));

      const alert = await within(box()).findByRole("alert");
      expect(alert).toHaveTextContent(message);
      expect(alert).toHaveFocus();

      await userEvent.click(within(box()).getByRole("button", { name: "Volver a intentarlo" }));
      expect(await within(box()).findByRole("region", { name: "Minueto" })).toBeVisible();
      expect(calls.filter((call) => call.key === "POST /transcribe")).toHaveLength(2);
    },
  );

  it("si la sesión caducó al enviar, pide volver a entrar con la imagen conservada y sigue al volver", async () => {
    let attempt = 0;
    const { calls } = mockApi({
      "POST /transcribe": () => {
        attempt += 1;
        return attempt === 1
          ? jsonResponse({ detail: "caducado" }, 401)
          : jsonResponse(transcribed(), 201);
      },
      "POST /auth/login": () => jsonResponse({ access_token: fakeJwt(1_800_000) }),
      "GET /auth/me": () => jsonResponse(ANA),
      ...sessionRoutes(),
    });
    signInAs(ANA);
    const router = renderAt();
    await userEvent.upload(fileInput(), png());
    await userEvent.click(within(box()).getByRole("button", { name: "Transcribir la imagen" }));

    const notice = await within(box()).findByText(/tu sesión caducó antes de transcribirla/i);
    expect(notice).toBeVisible();
    // El bloque de espera desaparece: el aviso de volver a entrar se lleva el foco.
    expect(notice).toHaveFocus();
    expect(useAuthStore.getState().status).toBe("anonymous");

    await userEvent.click(within(box()).getByRole("link", { name: "Entrar y transcribir" }));
    expect(router.state.location.pathname).toBe("/entrar");
    await userEvent.type(screen.getByLabelText("Usuario"), "ana");
    await userEvent.type(screen.getByLabelText("Contraseña"), secret());
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));

    expect(await resultAfterReturn()).toBeVisible();
    expect(calls.filter((call) => call.key === "POST /transcribe")).toHaveLength(2);
  });
});

describe("recuadro de la portada sin sesión (#277)", () => {
  it("al elegir la imagen pide entrar sin enviar nada; tras entrar vuelve a la portada y transcribe con la misma imagen y los mismos datos", async () => {
    const { calls } = mockApi({
      "POST /transcribe": () => jsonResponse(transcribed(), 201),
      "POST /auth/login": () => jsonResponse({ access_token: fakeJwt(1_800_000) }),
      "GET /auth/me": () => jsonResponse(ANA),
      ...sessionRoutes(),
    });
    const router = renderAt();

    await userEvent.upload(fileInput(), png());
    await userEvent.type(within(box()).getByLabelText(/nombre de la partitura/i), "Minueto");
    expect(within(box()).getByText(/para transcribir hace falta entrar/i)).toBeVisible();
    expect(within(box()).getByText(/si recargas la página/i)).toBeVisible();
    expect(within(box()).queryByRole("button", { name: "Transcribir la imagen" })).toBeNull();
    // Sin registro abierto no se ofrece crear la cuenta.
    expect(within(box()).queryByRole("link", { name: /crear una cuenta/i })).toBeNull();

    await userEvent.click(within(box()).getByRole("link", { name: "Entrar y transcribir" }));
    expect(router.state.location.pathname).toBe("/entrar");
    // Solo se apunta el nombre del archivo, para avisar si se recarga; la imagen no se guarda.
    expect(sessionStorage.getItem(PENDING_UPLOAD_KEY)).toBe("minueto.png");
    expect(calls.filter((call) => call.key === "POST /transcribe")).toHaveLength(0);

    await userEvent.type(screen.getByLabelText("Usuario"), "ana");
    await userEvent.type(screen.getByLabelText("Contraseña"), secret());
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/");
    });
    expect(router.state.location.hash).toBe("#transcribir");
    expect(await resultAfterReturn()).toBeVisible();
    const form = sentForm(calls);
    expect((form.get("file") as File).name).toBe("minueto.png");
    expect(form.get("title")).toBe("Minueto");
    expect(calls.filter((call) => call.key === "POST /transcribe")).toHaveLength(1);
    expect(sessionStorage.getItem(PENDING_UPLOAD_KEY)).toBeNull();
  });

  it("con el registro abierto, crear la cuenta también vuelve a la portada y transcribe", async () => {
    vi.stubEnv("VITE_REGISTRATION_ENABLED", "true");
    const { calls } = mockApi({
      "POST /transcribe": () => jsonResponse(transcribed(), 201),
      "POST /auth/register": () => jsonResponse(ANA, 201),
      "POST /auth/login": () => jsonResponse({ access_token: fakeJwt(1_800_000) }),
      "GET /auth/me": () => jsonResponse(ANA),
      ...sessionRoutes(),
    });
    const router = renderAt();

    await userEvent.upload(fileInput(), png());
    await userEvent.click(within(box()).getByRole("link", { name: "Crear una cuenta" }));
    expect(router.state.location.pathname).toBe("/registro");
    const password = secret();
    await userEvent.type(screen.getByLabelText("Usuario"), "ana");
    await userEvent.type(screen.getByLabelText("Contraseña"), password);
    await userEvent.type(screen.getByLabelText("Repite la contraseña"), password);
    // La casilla del permiso de uso de los datos es obligatoria (#378).
    await userEvent.click(
      screen.getByRole("checkbox", { name: "Doy mi permiso para que se usen mis datos así." }),
    );
    await userEvent.click(screen.getByRole("button", { name: /crear cuenta y entrar/i }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/");
    });
    expect(await resultAfterReturn()).toBeVisible();
    expect(calls.filter((call) => call.key === "POST /transcribe")).toHaveLength(1);
  });

  it("desde entrar, «Créala» conserva la vuelta a la portada", async () => {
    vi.stubEnv("VITE_REGISTRATION_ENABLED", "true");
    mockApi({});
    const router = renderAt();
    await userEvent.upload(fileInput(), png());
    await userEvent.click(within(box()).getByRole("link", { name: "Entrar y transcribir" }));

    await userEvent.click(screen.getByRole("link", { name: "Créala" }));

    expect(router.state.location.pathname).toBe("/registro");
    expect(router.state.location.state).toEqual({ from: "/#transcribir" });
  });

  it("si la página se recargó mientras se entraba, avisa de que hay que volver a elegir la imagen", async () => {
    sessionStorage.setItem(PENDING_UPLOAD_KEY, "minueto.png");
    signInAs(ANA);
    renderAt("/#transcribir");

    const notice = within(box()).getByRole("alert");
    expect(notice).toHaveTextContent("«minueto.png» se perdió");
    expect(notice).toHaveTextContent(/no la guarda en el navegador/i);
    expect(within(box()).getByRole("button", { name: "Elegir una imagen" })).toBeVisible();
    expect(sessionStorage.getItem(PENDING_UPLOAD_KEY)).toBeNull();

    await userEvent.click(within(notice).getByRole("button", { name: "Entendido" }));
    expect(within(box()).queryByRole("alert")).toBeNull();
  });

  it("descartar olvida la imagen y el aviso pendiente", async () => {
    mockApi({});
    const router = renderAt();
    await userEvent.upload(fileInput(), png());
    await userEvent.click(within(box()).getByRole("link", { name: "Entrar y transcribir" }));
    expect(sessionStorage.getItem(PENDING_UPLOAD_KEY)).toBe("minueto.png");
    await act(() => router.navigate(-1));

    await userEvent.click(within(box()).getByRole("button", { name: "Descartar" }));

    expect(useLandingUpload.getState().file).toBeNull();
    expect(sessionStorage.getItem(PENDING_UPLOAD_KEY)).toBeNull();
    expect(within(box()).queryByText(/hace falta entrar/i)).toBeNull();
    expect(within(box()).getByRole("button", { name: "Elegir una imagen" })).toHaveFocus();
  });

  it("si se entra por otro camino, no transcribe sin que se pulse", async () => {
    const { calls } = mockApi({
      "POST /transcribe": () => jsonResponse(transcribed(), 201),
      ...sessionRoutes(),
    });
    const router = renderAt();
    await userEvent.upload(fileInput(), png());
    await userEvent.click(within(box()).getByRole("link", { name: "Entrar y transcribir" }));

    // Vuelve atrás sin entrar y entra después por otro camino (otra pestaña de la misma sesión,
    // la cabecera): la portada, sin el ancla de la vuelta, no envía nada sola.
    await act(() => router.navigate(-1));
    expect(router.state.location.hash).toBe("");
    act(() => {
      signInAs(ANA);
    });

    expect(await screen.findByRole("button", { name: "Transcribir la imagen" })).toBeVisible();
    expect(calls.filter((call) => call.key === "POST /transcribe")).toHaveLength(0);
  });

  it("si entra otra persona tras caducar la sesión, la imagen que eligió la anterior se olvida", async () => {
    mockApi({});
    signInAs(ANA);
    renderAt();
    await userEvent.upload(fileInput(), png());
    act(() => {
      useAuthStore.getState().signOut("expired");
    });
    expect(useLandingUpload.getState().file).not.toBeNull();

    act(() => {
      signInAs({ ...ANA, id: "0b7f6c1e-1111-4bbb-8ccc-000000000002", username: "luis" });
    });

    expect(useLandingUpload.getState().file).toBeNull();
    expect(within(box()).queryByRole("form")).toBeNull();
  });

  it("al salir de la sesión se olvida el resultado", async () => {
    mockApi({ "POST /transcribe": () => jsonResponse(transcribed(), 201), ...sessionRoutes() });
    signInAs(ANA);
    renderAt();
    await userEvent.upload(fileInput(), png());
    await userEvent.click(within(box()).getByRole("button", { name: "Transcribir la imagen" }));
    await within(box()).findByRole("region", { name: "Minueto" });

    act(() => {
      useAuthStore.getState().signOut("signed-out");
    });

    expect(within(box()).queryByRole("region", { name: "Minueto" })).toBeNull();
  });
});
