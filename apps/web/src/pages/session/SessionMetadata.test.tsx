import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { routes } from "../../router";
import {
  ANA,
  deferred,
  jsonResponse,
  mockApi,
  resetAuth,
  signInAs,
  type Route,
} from "../../test/auth-helpers";
import type {
  EditEventRead,
  SessionDetailRead,
  SessionMetadataRead,
  SessionMetadataUpdate,
  TimingMapRead,
  UserRead,
} from "../../types";

// La partitura no se dibuja en jsdom: un dibujante falso que recuerda cada MusicXML que recibe.
const drawn = vi.hoisted(() => ({ xml: [] as string[] }));
vi.mock("./osmd", () => ({
  createScoreRenderer: () =>
    Promise.resolve({
      draw(xml: string) {
        drawn.xml.push(xml);
        return {
          measuresPerStaff: () => [0, 0, 0],
          measureBox: () => null,
          measureFigures: () => null,
        };
      },
      relayout: () => undefined,
      dispose: () => undefined,
    }),
}));
vi.mock("./toneEngine", () => ({ createToneEngine: vi.fn() }));

const LUIS: UserRead = { ...ANA, id: "0b7f6c1e-1111-4bbb-8ccc-000000000002", username: "luis" };
const INVESTIGADORA: UserRead = {
  ...ANA,
  id: "0b7f6c1e-2222-4bbb-8ccc-000000000003",
  username: "inv",
  role: "investigador",
};
const ID = "3e951fef-8a58-489e-abc9-68cfc3cd405b";

/** Una voz de un pentagrama y un piano de dos, sin compases: basta para nombrar las partes. */
function detail(changes: Partial<SessionDetailRead> = {}): SessionDetailRead {
  const staff = (id: string) => ({ id, measures: [] });
  return {
    session_id: ID,
    document_id: "homr-1",
    omr_engine: "homr",
    document: {} as SessionDetailRead["document"],
    findings: [],
    edits: [],
    current_score: {
      parts: [
        { id: "part-0", staves: [staff("part-0-staff-0")] },
        { id: "part-1", staves: [staff("part-1-staff-0"), staff("part-1-staff-1")] },
      ],
    },
    current_seq: 0,
    anchor_index: null,
    image_artifact: "img",
    status: "transcribed",
    condition: "unassisted",
    test_score_id: "TS-02",
    owner_id: ANA.id,
    title: null,
    composer: null,
    instruments: [],
    source_filename: null,
    ...changes,
  };
}

const TIMING: TimingMapRead = {
  session_id: ID,
  total_beats: "0",
  measure_offsets: {},
  events: [],
};

const png = () =>
  new Response(new Uint8Array([1, 2]), { headers: { "Content-Type": "image/png" } });

/** La API de la sesión; cada `/export` devuelve un MusicXML distinto, numerado. */
function api(
  start: SessionDetailRead,
  patch?: (body: SessionMetadataUpdate) => Response | Promise<Response>,
  extra: Record<string, Route> = {},
) {
  let exports = 0;
  return mockApi({
    [`GET /sessions/${ID}`]: () => jsonResponse(start),
    [`GET /sessions/${ID}/findings`]: () => jsonResponse([]),
    [`GET /sessions/${ID}/export`]: () => {
      exports += 1;
      return new Response(`<score-partwise>exportación ${String(exports)}</score-partwise>`, {
        headers: { "Content-Type": "application/vnd.recordare.musicxml+xml" },
      });
    },
    [`GET /sessions/${ID}/image`]: png,
    [`GET /sessions/${ID}/timing`]: () => jsonResponse(TIMING),
    "GET /users": () => jsonResponse([ANA, LUIS, INVESTIGADORA]),
    ...(patch
      ? {
          [`PATCH /sessions/${ID}`]: (init: RequestInit | undefined) =>
            patch(JSON.parse(init?.body as string) as SessionMetadataUpdate),
        }
      : {}),
    ...extra,
  });
}

function renderPage(user: UserRead = ANA) {
  signInAs(user);
  const router = createMemoryRouter(routes, { initialEntries: [`/sesiones/${ID}`] });
  render(<RouterProvider router={router} />);
  return router;
}

/** Abre «Exportar / Datos» (#363) si está cerrado y da el botón de esa acción. */
async function sessionAction(name: string) {
  const toggle = await screen.findByRole("button", { name: "Exportar / Datos" });
  if (toggle.getAttribute("aria-expanded") !== "true") fireEvent.click(toggle);
  return screen.findByRole("button", { name });
}

/** Escribe de una vez (pegando): letra a letra, bajo carga, la prueba pasaría del límite. */
async function fill(element: HTMLElement, text: string) {
  await userEvent.clear(element);
  await userEvent.click(element);
  await userEvent.paste(text);
}

beforeEach(() => {
  resetAuth();
  drawn.xml = [];
  vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:original");
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
  vi.stubGlobal("matchMedia", () => ({ matches: false }));
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("nombre y datos de la sesión en su vista (#240)", () => {
  it("se llama por su título en la cabecera y en la pestaña, y enseña el compositor y los instrumentos", async () => {
    api(
      detail({
        title: "Mondnacht",
        composer: "Robert Schumann",
        instruments: [
          { instrument: "voice", name: null },
          { instrument: "piano", name: null },
        ],
        source_filename: "mondnacht.png",
      }),
    );
    renderPage();

    expect(await screen.findByRole("heading", { level: 1, name: "Mondnacht" })).toBeVisible();
    await waitFor(() => {
      expect(document.title).toBe("Mondnacht · Cadenza");
    });
    const meta = (term: string) => screen.getByText(term, { selector: "dt" }).nextElementSibling;
    expect(meta("Compositor")).toHaveTextContent("Robert Schumann");
    expect(meta("Instrumentos")).toHaveTextContent("Voz · Piano");
    expect(meta("Archivo")).toHaveTextContent("mondnacht.png");
    // Nada de los datos del estudio.
    expect(screen.queryByText(/unassisted|TS-02/)).toBeNull();
  });

  it("sin título se llama como el archivo, y sin ninguno de los dos, por su identificador", async () => {
    api(detail({ source_filename: "pagina-2.png" }));
    renderPage();
    expect(await screen.findByRole("heading", { level: 1, name: "pagina-2.png" })).toBeVisible();
    await waitFor(() => {
      expect(document.title).toBe("pagina-2.png · Cadenza");
    });
    expect(screen.queryByText("Archivo", { selector: "dt" })).toBeNull();
    expect(screen.queryByText("Compositor", { selector: "dt" })).toBeNull();
  });

  it("sin título ni archivo, «Sesión» y el comienzo del identificador", async () => {
    api(detail());
    renderPage();
    expect(await screen.findByRole("heading", { level: 1, name: "Sesión 3e951fef" })).toBeVisible();
    await waitFor(() => {
      expect(document.title).toBe("Sesión 3e951fef · Cadenza");
    });
  });

  it("quien la transcribió cambia el nombre y los instrumentos; la vista y la descarga toman lo que devuelve", async () => {
    const sent: SessionMetadataUpdate[] = [];
    const { calls } = api(
      detail({ title: "Mondnacht", instruments: [{ instrument: "voice", name: "Soprano" }] }),
      (body) => {
        sent.push(body);
        return jsonResponse({
          session_id: ID,
          // El servidor normaliza el texto: se muestra lo que devuelve.
          title: "Mondnacht, op. 39",
          composer: "Robert Schumann",
          instruments: [
            { instrument: "voice", name: "Soprano" },
            { instrument: "other", name: "Arpa" },
          ],
          source_filename: null,
        } satisfies SessionMetadataRead);
      },
    );
    const saved: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      saved.push(this.download);
    });
    renderPage();

    const toggle = await sessionAction("Cambiar los datos");
    await waitFor(() => {
      expect(drawn.xml).toHaveLength(1);
    });
    await userEvent.click(toggle);
    const form = screen.getByRole("form", { name: "Datos de la partitura" });
    const title = within(form).getByLabelText("Nombre de la partitura");
    expect(title).toHaveValue("Mondnacht");
    expect(title).toHaveFocus();
    // Una parte por cada una de la partitura, con sus pentagramas.
    expect(within(form).getByLabelText("Parte 1 · 1 pentagrama")).toHaveValue("voice");
    const second = within(form).getByLabelText("Parte 2 · 2 pentagramas");
    expect(second).toHaveValue("");

    await fill(title, "Mondnacht,  op. 39");
    await fill(within(form).getByLabelText("Compositor"), "Robert Schumann");
    await userEvent.selectOptions(second, "Otro");
    await fill(within(form).getByLabelText("Nombre del instrumento"), "Arpa");
    await userEvent.click(within(form).getByRole("button", { name: "Guardar" }));

    expect(
      await screen.findByRole("heading", { level: 1, name: "Mondnacht, op. 39" }),
    ).toBeVisible();
    expect(sent).toEqual([
      {
        title: "Mondnacht,  op. 39",
        composer: "Robert Schumann",
        instruments: [
          { instrument: "voice", name: "Soprano" },
          { instrument: "other", name: "Arpa" },
        ],
      },
    ]);
    expect(screen.queryByRole("form", { name: "Datos de la partitura" })).toBeNull();
    expect(screen.getByText("Datos guardados.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Cambiar los datos" })).toHaveFocus();
    await waitFor(() => {
      expect(document.title).toBe("Mondnacht, op. 39 · Cadenza");
    });
    const meta = (term: string) => screen.getByText(term, { selector: "dt" }).nextElementSibling;
    expect(meta("Instrumentos")).toHaveTextContent("Soprano · Arpa");

    // El MusicXML que se ve y se descarga es el de los datos nuevos, con el mismo nombre de
    // archivo de siempre. No es una edición: no se envía nada al log.
    await waitFor(() => {
      expect(drawn.xml).toEqual([
        "<score-partwise>exportación 1</score-partwise>",
        "<score-partwise>exportación 2</score-partwise>",
      ]);
    });
    await userEvent.click(screen.getByRole("button", { name: "Descargar MusicXML" }));
    expect(saved).toEqual(["cadenza-3e951fef.musicxml"]);
    expect(calls.some((call) => call.key.endsWith("/edits"))).toBe(false);
  });

  it("tras guardar los datos, «Descargar MIDI» pide el MIDI otra vez: lleva el programa de cada parte", async () => {
    // Cada MIDI lleva su número en el último byte: el primero, con los datos de antes.
    let midis = 0;
    const midiRoute: Route = (_init, url) => {
      if (url.searchParams.get("format") !== "midi") {
        return new Response("<score-partwise/>", {
          headers: { "Content-Type": "application/vnd.recordare.musicxml+xml" },
        });
      }
      midis += 1;
      return new Response(new Uint8Array([0x4d, 0x54, 0x68, 0x64, midis]), {
        headers: { "Content-Type": "audio/midi" },
      });
    };
    api(
      detail({ instruments: [{ instrument: "piano", name: null }] }),
      () =>
        jsonResponse({
          session_id: ID,
          title: null,
          composer: null,
          instruments: [{ instrument: "violin", name: null }],
          source_filename: null,
        } satisfies SessionMetadataRead),
      { [`GET /sessions/${ID}/export`]: midiRoute },
    );
    const blobs: Blob[] = [];
    vi.spyOn(URL, "createObjectURL").mockImplementation((value) => {
      if (value instanceof Blob && value.type === "audio/midi") blobs.push(value);
      return "blob:archivo";
    });
    const saved: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      saved.push(this.download);
    });
    renderPage();
    const download = await sessionAction("Descargar MIDI");
    await waitFor(() => {
      expect(download).not.toHaveAttribute("aria-disabled", "true");
    });
    await userEvent.click(download);
    await waitFor(() => {
      expect(saved).toEqual(["cadenza-3e951fef.mid"]);
    });

    await userEvent.click(screen.getByRole("button", { name: "Cambiar los datos" }));
    const form = screen.getByRole("form", { name: "Datos de la partitura" });
    await userEvent.selectOptions(within(form).getByLabelText("Parte 1 · 1 pentagrama"), "violin");
    await userEvent.click(within(form).getByRole("button", { name: "Guardar" }));
    expect(await screen.findByText("Datos guardados.")).toBeVisible();

    // Mismo estado, datos nuevos: el MIDI de antes ya no vale y se vuelve a pedir.
    await userEvent.click(download);
    await waitFor(() => {
      expect(saved).toEqual(["cadenza-3e951fef.mid", "cadenza-3e951fef.mid"]);
    });
    expect(midis).toBe(2);
    const last = blobs.at(-1);
    if (!last) throw new Error("no se guardó ningún MIDI");
    expect(new Uint8Array(await last.arrayBuffer()).at(-1)).toBe(2);
  });

  it("también con la sesión finalizada, sin reabrirla", async () => {
    api(detail({ status: "finalized" }), () =>
      jsonResponse({
        session_id: ID,
        title: "Lied",
        composer: null,
        instruments: [],
        source_filename: null,
      } satisfies SessionMetadataRead),
    );
    renderPage();

    await userEvent.click(await sessionAction("Cambiar los datos"));
    await fill(screen.getByLabelText("Nombre de la partitura"), "Lied");
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Lied" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Reabrir la sesión" })).toBeVisible();
  });

  it("si no se guardan lo dice, conserva lo escrito y no cambia el nombre", async () => {
    let answer: Response = jsonResponse({ detail: "demasiado largo" }, 422);
    api(detail(), () => answer);
    renderPage();

    await userEvent.click(await sessionAction("Cambiar los datos"));
    const title = screen.getByLabelText("Nombre de la partitura");
    await fill(title, "Mondnacht");
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/no se guardaron los datos/i);
    expect(title).toHaveValue("Mondnacht");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Sesión 3e951fef");

    answer = jsonResponse({ detail: "no" }, 404);
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/ya no existe o no tienes acceso/i);
  });

  it("mientras se guarda no se envía otra vez, y «Cancelar» deja los datos como estaban", async () => {
    const pending = deferred<Response>();
    let patches = 0;
    api(detail({ title: "Mondnacht" }), () => {
      patches += 1;
      return pending.promise;
    });
    renderPage();

    await userEvent.click(await sessionAction("Cambiar los datos"));
    await fill(screen.getByLabelText("Nombre de la partitura"), "Otro nombre");
    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Mondnacht");
    await userEvent.click(screen.getByRole("button", { name: "Cambiar los datos" }));
    expect(screen.getByLabelText("Nombre de la partitura")).toHaveValue("Mondnacht");

    const save = screen.getByRole("button", { name: "Guardar" });
    await userEvent.click(save);
    await userEvent.click(save);
    expect(save).toHaveAttribute("aria-disabled", "true");
    expect(patches).toBe(1);
    pending.resolve(
      jsonResponse({
        session_id: ID,
        title: "Mondnacht",
        composer: null,
        instruments: [],
        source_filename: null,
      } satisfies SessionMetadataRead),
    );
    expect(await screen.findByText("Datos guardados.")).toBeVisible();
  });

  it("guardar los datos y corregir no se cruzan", async () => {
    const edit: EditEventRead = {
      id: "e1",
      session_id: ID,
      seq: 1,
      op: "SetPitch",
      author: ANA.id,
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
      before: { pitch: "C4" },
      after: { pitch: "D4" },
      created_at: "2026-11-01T10:00:00",
    };
    const patch = deferred<Response>();
    const undo = deferred<Response>();
    const { calls } = api(detail({ current_seq: 1, edits: [edit] }), () => patch.promise, {
      [`POST /sessions/${ID}/undo`]: () => undo.promise,
    });
    renderPage();
    const posts = () =>
      calls
        .map((call) => call.key)
        .filter((key) => key === `PATCH /sessions/${ID}` || key === `POST /sessions/${ID}/undo`)
        .map((key) => (key.startsWith("PATCH") ? "PATCH" : "UNDO"));

    // Mientras se guardan los datos, deshacer espera.
    await userEvent.click(await sessionAction("Cambiar los datos"));
    await waitFor(() => {
      expect(drawn.xml).toHaveLength(1);
    });
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));
    expect(posts()).toEqual(["PATCH"]);
    const undoButton = screen.getByRole("button", { name: /^deshacer/i });
    await userEvent.click(undoButton);
    expect(posts()).toEqual(["PATCH"]);
    patch.resolve(jsonResponse({ session_id: ID, title: null, instruments: [] }));
    expect(await screen.findByText("Datos guardados.")).toBeVisible();

    // Mientras se deshace, guardar espera.
    await userEvent.click(screen.getByRole("button", { name: /^deshacer/i }));
    await waitFor(() => {
      expect(posts()).toEqual(["PATCH", "UNDO"]);
    });
    // Deshacer se pulsó fuera de «Exportar / Datos», que se cerró al terminar de guardar (#363).
    await userEvent.click(await sessionAction("Cambiar los datos"));
    const save = screen.getByRole("button", { name: "Guardar" });
    expect(save).toHaveAttribute("aria-disabled", "true");
    expect(save).toHaveAccessibleDescription("Espera a que termine lo que está en curso.");
    await userEvent.click(save);
    expect(posts()).toEqual(["PATCH", "UNDO"]);
    undo.resolve(jsonResponse({ detail: "fallo" }, 500));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Guardar" })).not.toHaveAttribute("aria-disabled");
    });
  });

  it("nadie más que quien la transcribió puede cambiarlos", async () => {
    api(detail({ owner_id: LUIS.id, title: "Ajena" }));
    renderPage(INVESTIGADORA);

    expect(await screen.findByRole("heading", { level: 1, name: "Ajena" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Cambiar los datos" })).toBeNull();
  });
});
