import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import { useAuthStore } from "../../auth/store";
import { routes } from "../../router";
import {
  ANA,
  deferred,
  fakeJwt,
  jsonResponse,
  mockApi,
  resetAuth,
  signInAs,
} from "../../test/auth-helpers";
import type { SessionSummaryRead, UserRead } from "../../types";
import { useQueueStore, type QueueItem } from "./queue";

function session(id: string, overrides: Partial<SessionSummaryRead> = {}): SessionSummaryRead {
  return {
    session_id: id,
    document_id: `doc-${id}`,
    omr_engine: "homr",
    model_version: null,
    status: "transcribed",
    created_at: "2026-10-22T20:15:00",
    findings_count: 2,
    edits_count: 0,
    condition: "assisted",
    test_score_id: null,
    owner_id: ANA.id,
    ...overrides,
  };
}

function renderPage(user: UserRead = ANA) {
  signInAs(user);
  const router = createMemoryRouter(routes, { initialEntries: ["/transcripcion"] });
  render(<RouterProvider router={router} />);
  return router;
}

function transcribed(id: string, findings = 1) {
  return {
    session_id: id,
    document_id: `doc-${id}`,
    omr_engine: "homr",
    findings_count: findings,
    condition: "assisted",
    test_score_id: null,
  };
}

const image = () => new Response(new Uint8Array([1]), { headers: { "Content-Type": "image/png" } });

function png(name: string) {
  return new File([new Uint8Array(8)], name, { type: "image/png" });
}

function fileInput(): HTMLInputElement {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) throw new Error("falta el selector de archivos");
  return input;
}

/** Deja la cola en un estado dado sin enviar nada (la cola «corriendo» no arranca otra). */
function setQueue(items: QueueItem[]) {
  act(() => {
    useQueueStore.setState({ items, running: true });
  });
}

function item(id: string, name: string, changes: Partial<QueueItem> = {}): QueueItem {
  return { id, file: png(name), status: "queued", ...changes };
}

let createObjectURL: MockInstance<typeof URL.createObjectURL>;
let revokeObjectURL: MockInstance<typeof URL.revokeObjectURL>;

beforeEach(() => {
  resetAuth();
  useQueueStore.getState().reset();
  createObjectURL = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:miniatura");
  revokeObjectURL = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
});

afterEach(() => {
  vi.unstubAllGlobals();
  useQueueStore.getState().reset();
});

describe("vista de transcripción", () => {
  it("muestra el estado vacío cuando no hay sesiones", async () => {
    mockApi({ "GET /sessions": () => jsonResponse([]) });
    renderPage();

    expect(await screen.findByText(/todavía no hay sesiones/i)).toBeVisible();
    expect(screen.getByText(/las imágenes que elijas aparecerán aquí/i)).toBeVisible();
  });

  it("lista las sesiones con fecha, estado, hallazgos, miniatura autenticada y enlace a su vista", async () => {
    mockApi({
      "GET /sessions": () => jsonResponse([session("aaaaaaaa-1111"), session("bbbbbbbb-2222")]),
      "GET /sessions/aaaaaaaa-1111/image": () =>
        new Response(new Uint8Array([1, 2]), { headers: { "Content-Type": "image/png" } }),
      "GET /sessions/bbbbbbbb-2222/image": () =>
        new Response(new Uint8Array([1, 2]), { headers: { "Content-Type": "image/png" } }),
    });
    renderPage();

    const table = await screen.findByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(within(table).getByText("aaaaaaaa")).toBeVisible();
    expect(table.querySelector("time")).toHaveAttribute("datetime", "2026-10-22T20:15:00.000Z");
    // 20:15 UTC es 15:15 en Bogotá (TZ de las pruebas).
    expect(within(table).getAllByText("15:15")).toHaveLength(2);
    expect(screen.queryByText(/assisted/i)).toBeNull();
    expect(within(table).getAllByText("Transcrita")).toHaveLength(2);
    expect(within(table).queryByRole("columnheader", { name: /propietario/i })).toBeNull();
    await waitFor(() => {
      expect(createObjectURL).toHaveBeenCalledTimes(2);
    });
    // Cada sesión enlaza con su vista de solo lectura; no hay enlaces a una edición.
    expect(within(table).getByRole("link", { name: "Ver la sesión aaaaaaaa" })).toHaveAttribute(
      "href",
      "/sesiones/aaaaaaaa-1111",
    );
    for (const link of screen.getAllByRole("link")) {
      expect(link.getAttribute("href")).not.toMatch(/editor|edicion|correccion/i);
    }
  });

  it("revoca cada URL de miniatura creada al salir de la vista", async () => {
    let n = 0;
    createObjectURL.mockImplementation(() => `blob:miniatura-${String(++n)}`);
    mockApi({
      "GET /sessions": () => jsonResponse([session("aaaaaaaa-1111"), session("bbbbbbbb-2222")]),
      "GET /sessions/aaaaaaaa-1111/image": image,
      "GET /sessions/bbbbbbbb-2222/image": image,
    });
    const router = renderPage();
    await waitFor(() => {
      expect(createObjectURL).toHaveBeenCalledTimes(2);
    });
    expect(revokeObjectURL).not.toHaveBeenCalled();

    await act(() => router.navigate("/"));

    const created = createObjectURL.mock.results.map((result) => result.value as string);
    const revoked = revokeObjectURL.mock.calls.map(([url]) => url);
    expect(new Set(revoked)).toEqual(new Set(created));
    expect(revoked).toHaveLength(2);
  });

  it("pagina con «Cargar más»", async () => {
    const first = Array.from({ length: 20 }, (_, i) => session(`s-${String(i).padStart(4, "0")}`));
    let page = 0;
    const { calls } = mockApi({
      "GET /sessions": () => {
        page += 1;
        return jsonResponse(page === 1 ? first : [session("ultima-0000")]);
      },
    });
    renderPage();
    await screen.findByRole("table");

    await userEvent.click(screen.getByRole("button", { name: "Cargar más" }));

    expect(await screen.findByText("ultima-0")).toBeVisible();
    const pages = calls.filter((call) => call.key === "GET /sessions");
    expect(pages.map((call) => call.url.searchParams.get("offset"))).toEqual(["0", "20"]);
    expect(pages.map((call) => call.url.searchParams.get("limit"))).toEqual(["20", "20"]);
    expect(screen.queryByRole("button", { name: "Cargar más" })).not.toBeInTheDocument();
  });

  it("no repite filas si una sesión nueva desplaza la página siguiente", async () => {
    const first = Array.from({ length: 20 }, (_, i) => session(`s-${String(i).padStart(4, "0")}`));
    let page = 0;
    mockApi({
      "GET /sessions": () => {
        page += 1;
        // Se creó una sesión entre páginas: la última de la primera vuelve a salir.
        return jsonResponse(page === 1 ? first : [first[19], session("ultima-0000")]);
      },
    });
    renderPage();
    const table = await screen.findByRole("table");

    await userEvent.click(screen.getByRole("button", { name: "Cargar más" }));

    expect(await within(table).findByText("ultima-0")).toBeVisible();
    expect(within(table).getAllByText("s-0019")).toHaveLength(1);
    expect(within(table).getAllByRole("row")).toHaveLength(1 + 21);
  });

  it("si falla «Cargar más» avisa una sola vez y conserva las filas", async () => {
    const first = Array.from({ length: 20 }, (_, i) => session(`s-${String(i).padStart(4, "0")}`));
    let page = 0;
    mockApi({
      "GET /sessions": () => {
        page += 1;
        return page === 1 ? jsonResponse(first) : jsonResponse({ detail: "boom" }, 500);
      },
    });
    renderPage();
    const table = await screen.findByRole("table");

    await userEvent.click(screen.getByRole("button", { name: "Cargar más" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/no se pudieron cargar más/i);
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(within(table).getAllByRole("row")).toHaveLength(21);
    expect(screen.getByRole("button", { name: "Cargar más" })).toHaveAttribute(
      "aria-disabled",
      "false",
    );
  });

  it("un investigador ve el propietario de cada sesión", async () => {
    const investigador: UserRead = { ...ANA, id: "inv-1", username: "irene", role: "investigador" };
    mockApi({
      "GET /sessions": () =>
        jsonResponse([
          session("aaaaaaaa-1", { owner_id: ANA.id }),
          session("bbbbbbbb-2", { owner_id: "inv-1" }),
        ]),
      "GET /users": () => jsonResponse([ANA, investigador]),
    });
    renderPage(investigador);

    const table = await screen.findByRole("table");
    expect(within(table).getByRole("columnheader", { name: /propietario/i })).toBeVisible();
    expect(await within(table).findByText("ana")).toBeVisible();
    expect(within(table).getByText("Tú")).toBeVisible();
  });

  it("muestra un error del listado con reintento", async () => {
    let fail = true;
    mockApi({
      "GET /sessions": () =>
        fail ? jsonResponse({ detail: "boom" }, 500) : jsonResponse([session("aaaaaaaa-1")]),
    });
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent(/servidor/i);
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByRole("table")).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("muestra el estado de carga mientras llega el listado", async () => {
    const response = deferred<Response>();
    mockApi({ "GET /sessions": () => response.promise });
    renderPage();

    expect(await screen.findByRole("status")).toHaveTextContent(/cargando sesiones/i);
    response.resolve(jsonResponse([]));
    expect(await screen.findByText(/todavía no hay sesiones/i)).toBeVisible();
    expect(screen.queryByText(/cargando sesiones/i)).not.toBeInTheDocument();
  });

  it("sube varias imágenes, las transcribe en cola y las sesiones nuevas aparecen en el listado", async () => {
    const created: SessionSummaryRead[] = [];
    mockApi({
      // La más reciente primero, como la API.
      "GET /sessions": () => jsonResponse([...created].reverse()),
      "POST /transcribe": () => {
        const id = `nueva000-${String(created.length + 1)}`;
        created.push(session(id, { findings_count: 1 }));
        return jsonResponse(transcribed(id), 201);
      },
      "GET /sessions/nueva000-1/image": image,
      "GET /sessions/nueva000-2/image": image,
    });
    renderPage();
    await screen.findByText(/todavía no hay sesiones/i);

    await userEvent.upload(fileInput(), [png("uno.png"), png("dos.png")]);

    const queue = screen.getByRole("region", { name: "Cola" });
    await waitFor(() => {
      expect(within(queue).getAllByText("1 hallazgo")).toHaveLength(2);
    });
    const table = await screen.findByRole("table");
    await waitFor(() => {
      expect(within(table).getAllByRole("row")).toHaveLength(3);
    });
    expect(within(table).getAllByText("nueva000")).toHaveLength(2);
    expect(within(queue).getByText(/0 en cola · 2 transcritas · 0 con error/)).toBeVisible();
  });

  it("si la sesión caduca a mitad del lote, lleva al acceso, conserva la cola y la reanuda al volver", async () => {
    let posts = 0;
    const created: SessionSummaryRead[] = [];
    mockApi({
      "GET /sessions": () => jsonResponse([...created].reverse()),
      "POST /transcribe": () => {
        posts += 1;
        if (posts === 1) return jsonResponse({ detail: "Not authenticated" }, 401);
        const id = `retomada-${String(posts)}`;
        created.push(session(id));
        return jsonResponse(transcribed(id), 201);
      },
      "POST /auth/login": () => jsonResponse({ access_token: fakeJwt(1_800_000) }),
      "GET /auth/me": () => jsonResponse(ANA),
      "GET /sessions/retomada-2/image": image,
    });
    const router = renderPage();
    await screen.findByText(/todavía no hay sesiones/i);

    await userEvent.upload(fileInput(), [png("uno.png"), png("dos.png")]);

    expect(await screen.findByText(/tu sesión caducó/i)).toBeVisible();
    expect(router.state.location.pathname).toBe("/entrar");
    expect(useQueueStore.getState().items.map((entry) => entry.status)).toEqual([
      "error",
      "queued",
    ]);
    expect(posts).toBe(1);

    await userEvent.type(screen.getByLabelText("Usuario"), "ana");
    await userEvent.type(screen.getByLabelText("Contraseña"), "secreta");
    await userEvent.click(screen.getByRole("button", { name: /^entrar/i }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/transcripcion");
    });
    const queue = screen.getByRole("region", { name: "Cola" });
    await waitFor(() => {
      expect(within(queue).getByText("1 hallazgo")).toBeVisible();
    });
    expect(within(queue).getByText(/vuelve a entrar/i)).toBeVisible();
    expect(within(queue).getByRole("button", { name: /reintentar uno\.png/i })).toBeVisible();
    expect(posts).toBe(2);
  });

  it("rechaza en el navegador un archivo que no es imagen", async () => {
    const { calls } = mockApi({ "GET /sessions": () => jsonResponse([]) });
    renderPage();
    await screen.findByText(/todavía no hay sesiones/i);
    const input = document.querySelector<HTMLInputElement>('input[type="file"]');
    if (!input) throw new Error("falta el selector de archivos");

    await userEvent.upload(input, new File(["hola"], "notas.txt", { type: "text/plain" }), {
      applyAccept: false,
    });

    const queue = screen.getByRole("region", { name: "Cola" });
    expect(within(queue).getByText("Rechazada")).toBeVisible();
    expect(within(queue).getByText(/no es una imagen png o jpeg/i)).toBeVisible();
    expect(within(queue).queryByRole("button", { name: /reintentar/i })).toBeNull();
    expect(calls.some((call) => call.key === "POST /transcribe")).toBe(false);
  });

  it("marca en violeta las sesiones con hallazgos y deja en contorno las que no tienen", async () => {
    mockApi({
      "GET /sessions": () =>
        jsonResponse([
          session("aaaaaaaa-1", { findings_count: 3 }),
          session("bbbbbbbb-2", { findings_count: 0 }),
        ]),
    });
    renderPage();

    const table = await screen.findByRole("table");
    const [, withFindings, without] = within(table).getAllByRole("row");
    if (!withFindings || !without) throw new Error("faltan filas");
    expect(within(withFindings).getByText("3")).toHaveClass("chip--finding");
    expect(without.querySelector(".chip--finding")).toBeNull();
  });

  it("con un lote en curso pide confirmación al cerrar la pestaña y al salir", async () => {
    mockApi({ "GET /sessions": () => jsonResponse([]) });
    const router = renderPage();
    await screen.findByText(/todavía no hay sesiones/i);
    act(() => {
      useQueueStore.setState({
        items: [
          {
            id: "x",
            file: new File([new Uint8Array(4)], "pendiente.png", { type: "image/png" }),
            status: "queued",
          },
        ],
        running: true,
      });
    });

    const unload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(true);

    const confirm = vi.fn(() => false);
    vi.stubGlobal("confirm", confirm);
    await userEvent.click(screen.getByRole("button", { name: "Salir" }));
    expect(confirm).toHaveBeenCalledOnce();
    expect(router.state.location.pathname).toBe("/transcripcion");

    confirm.mockReturnValue(true);
    await userEvent.click(screen.getByRole("button", { name: "Salir" }));
    expect(router.state.location.pathname).toBe("/entrar");
    expect(useQueueStore.getState().items).toHaveLength(0);
  });

  it("sigue pidiendo confirmación al cerrar la pestaña después de salir de la vista", async () => {
    mockApi({ "GET /sessions": () => jsonResponse([]) });
    const router = renderPage();
    await screen.findByText(/todavía no hay sesiones/i);
    setQueue([item("x", "pendiente.png")]);

    await act(() => router.navigate("/"));
    expect(screen.queryByRole("region", { name: "Cola" })).not.toBeInTheDocument();

    const unload = new Event("beforeunload", { cancelable: true });
    // jsdom no tiene BeforeUnloadEvent: se captura lo que se asigna a returnValue.
    let returnValue: unknown;
    Object.defineProperty(unload, "returnValue", {
      get: () => returnValue,
      set: (value: unknown) => {
        returnValue = value;
      },
    });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(true);
    expect(returnValue).toBe("");

    act(() => {
      useQueueStore.getState().clearFinished();
      useQueueStore.getState().remove("x");
    });
    const later = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(later);
    expect(later.defaultPrevented).toBe(false);
  });

  it("separa en el recuento las transcritas de las que fallaron", async () => {
    mockApi({ "GET /sessions": () => jsonResponse([]) });
    renderPage();
    await screen.findByText(/todavía no hay sesiones/i);

    setQueue([
      item("a", "a.png", { status: "done", result: transcribed("s1", 0) }),
      item("b", "b.png", { status: "error", error: "No se reconoció ninguna partitura." }),
      item("c", "c.png"),
    ]);

    const queue = screen.getByRole("region", { name: "Cola" });
    expect(within(queue).getByText("1 en cola · 1 transcrita · 1 con error")).toBeVisible();
  });

  it("el contador de la imagen en curso cuenta desde que empezó, aunque se vuelva a la vista", async () => {
    mockApi({ "GET /sessions": () => jsonResponse([]) });
    renderPage();
    await screen.findByText(/todavía no hay sesiones/i);

    setQueue([item("a", "a.png", { status: "transcribing", startedAt: Date.now() - 12_000 })]);

    const queue = screen.getByRole("region", { name: "Cola" });
    expect(within(queue).getByText("12 s")).toBeVisible();
    expect(
      within(queue).getByText("0 en cola · 1 en curso · 0 transcritas · 0 con error"),
    ).toBeVisible();
  });

  it("mantiene el foco en la cola tras reintentar, quitar y limpiar", async () => {
    mockApi({ "GET /sessions": () => jsonResponse([]) });
    renderPage();
    await screen.findByText(/todavía no hay sesiones/i);
    setQueue([
      item("a", "a.png", { status: "error", error: "El servidor tuvo un problema." }),
      item("b", "b.png"),
      item("c", "c.png"),
      item("d", "d.png", { status: "done", result: transcribed("s1", 0) }),
    ]);
    const queue = screen.getByRole("region", { name: "Cola" });

    await userEvent.click(within(queue).getByRole("button", { name: /reintentar a\.png/i }));
    const retried = within(queue).getByText("a.png").closest("li");
    expect(retried).toHaveFocus();

    await userEvent.click(within(queue).getByRole("button", { name: /quitar b\.png/i }));
    expect(within(queue).getByText("c.png").closest("li")).toHaveFocus();

    await userEvent.click(within(queue).getByRole("button", { name: /limpiar terminadas/i }));
    expect(within(queue).getByRole("heading", { name: "Cola" })).toHaveFocus();
  });

  it("el selector oculto no es una parada de foco y soltar fuera de la zona no abre la imagen", async () => {
    mockApi({ "GET /sessions": () => jsonResponse([]) });
    const router = renderPage();
    await screen.findByText(/todavía no hay sesiones/i);

    expect(fileInput()).toHaveAttribute("tabindex", "-1");
    expect(fileInput()).toHaveAttribute("aria-hidden", "true");

    const dropOutside = () => {
      const event = new Event("drop", { bubbles: true, cancelable: true });
      Object.defineProperty(event, "dataTransfer", { value: { types: ["Files"], files: [] } });
      document.body.dispatchEvent(event);
      return event;
    };
    expect(dropOutside().defaultPrevented).toBe(true);

    await act(() => router.navigate("/"));
    expect(dropOutside().defaultPrevented).toBe(false);
  });

  it("descarga a lo sumo tres miniaturas a la vez", async () => {
    const pending = new Map<string, ReturnType<typeof deferred<Response>>>();
    const ids = Array.from({ length: 5 }, (_, i) => `img00000-${String(i)}`);
    mockApi({
      "GET /sessions": () => jsonResponse(ids.map((id) => session(id))),
      ...Object.fromEntries(
        ids.map((id) => [
          `GET /sessions/${id}/image`,
          () => {
            const response = deferred<Response>();
            pending.set(id, response);
            return response.promise;
          },
        ]),
      ),
    });
    renderPage();
    await screen.findByRole("table");

    await waitFor(() => {
      expect(pending.size).toBe(3);
    });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(pending.size).toBe(3);

    for (const response of pending.values()) response.resolve(image());
    await waitFor(() => {
      expect(pending.size).toBe(5);
    });
    for (const response of pending.values()) response.resolve(image());
    await waitFor(() => {
      expect(createObjectURL).toHaveBeenCalledTimes(5);
    });
  });

  it("no vuelve a descargar las miniaturas al volver a la vista", async () => {
    const { calls } = mockApi({
      "GET /sessions": () => jsonResponse([session("aaaaaaaa-1111")]),
      "GET /sessions/aaaaaaaa-1111/image": image,
    });
    const router = renderPage();
    await waitFor(() => {
      expect(createObjectURL).toHaveBeenCalledOnce();
    });

    await act(() => router.navigate("/"));
    await act(() => router.navigate("/transcripcion"));

    await waitFor(() => {
      expect(createObjectURL).toHaveBeenCalledTimes(2);
    });
    expect(calls.filter((call) => call.key.endsWith("/image"))).toHaveLength(1);
    const img = document.querySelector(".thumb img");
    expect(img).toHaveAttribute("decoding", "async");
  });

  it("si una transcripción termina durante «Cargar más», no se pierden ni la página ni la sesión nueva", async () => {
    const first = Array.from({ length: 20 }, (_, i) => session(`s-${String(i).padStart(4, "0")}`));
    const created: SessionSummaryRead[] = [];
    const all = () => [...[...created].reverse(), ...first, session("ultima-0000")];
    const nextPage = deferred<undefined>();
    const post = deferred<Response>();
    let secondPages = 0;
    const { calls } = mockApi({
      "GET /sessions": () => {
        const offset = Number(calls.at(-1)?.url.searchParams.get("offset"));
        const page = () => jsonResponse(all().slice(offset, offset + 20));
        if (offset === 0) return page();
        secondPages += 1;
        return secondPages === 1 ? nextPage.promise.then(page) : page();
      },
      "POST /transcribe": () => post.promise,
    });
    renderPage();
    const table = await screen.findByRole("table");
    act(() => {
      useQueueStore.getState().add([png("uno.png")]);
    });
    await waitFor(() => {
      expect(calls.some((call) => call.key === "POST /transcribe")).toBe(true);
    });

    await userEvent.click(screen.getByRole("button", { name: "Cargar más" }));
    created.push(session("nueva000-1"));
    post.resolve(jsonResponse(transcribed("nueva000-1"), 201));
    await waitFor(() => {
      expect(screen.getByRole("region", { name: "Cola" })).toHaveTextContent(/1 transcrita/);
    });
    nextPage.resolve(undefined);

    await waitFor(() => {
      expect(within(table).getByText("nueva000")).toBeVisible();
    });
    expect(within(table).getByText("ultima-0")).toBeVisible();
    expect(within(table).getAllByRole("row")).toHaveLength(1 + 22);
    const offsets = calls
      .filter((call) => call.key === "GET /sessions")
      .map((call) => call.url.searchParams.get("offset"));
    expect(offsets).toEqual(["0", "20", "0", "20"]);
  });

  it("con el listado actualizándose, «Cargar más» espera y la sesión nueva aparece", async () => {
    const first = Array.from({ length: 20 }, (_, i) => session(`s-${String(i).padStart(4, "0")}`));
    const created: SessionSummaryRead[] = [];
    const all = () => [...[...created].reverse(), ...first, session("ultima-0000")];
    const refresh = deferred<undefined>();
    let firstPages = 0;
    const { calls } = mockApi({
      "GET /sessions": () => {
        const offset = Number(calls.at(-1)?.url.searchParams.get("offset"));
        const page = () => jsonResponse(all().slice(offset, offset + 20));
        if (offset !== 0) return page();
        firstPages += 1;
        return firstPages === 2 ? refresh.promise.then(page) : page();
      },
      "POST /transcribe": () => {
        created.push(session("nueva000-1"));
        return jsonResponse(transcribed("nueva000-1"), 201);
      },
    });
    renderPage();
    const table = await screen.findByRole("table");
    act(() => {
      useQueueStore.getState().add([png("uno.png")]);
    });
    await waitFor(() => {
      expect(firstPages).toBe(2);
    });

    const more = screen.getByRole("button", { name: "Cargar más" });
    expect(more).toHaveAttribute("aria-disabled", "true");
    await userEvent.click(more);
    const offsets = () =>
      calls
        .filter((call) => call.key === "GET /sessions")
        .map((call) => call.url.searchParams.get("offset"));
    expect(offsets()).toEqual(["0", "0"]);

    refresh.resolve(undefined);
    await waitFor(() => {
      expect(within(table).getByText("nueva000")).toBeVisible();
    });
    await waitFor(() => {
      expect(more).toHaveAttribute("aria-disabled", "false");
    });
    await userEvent.click(more);

    await waitFor(() => {
      expect(within(table).getByText("ultima-0")).toBeVisible();
    });
    expect(offsets()).toEqual(["0", "0", "20"]);
  });

  it("tras «Cargar más» el foco pasa a la primera sesión nueva", async () => {
    const first = Array.from({ length: 20 }, (_, i) => session(`s-${String(i).padStart(4, "0")}`));
    let page = 0;
    mockApi({
      "GET /sessions": () => {
        page += 1;
        return jsonResponse(page === 1 ? first : [session("ultima-0000")]);
      },
    });
    renderPage();
    const table = await screen.findByRole("table");

    await userEvent.click(screen.getByRole("button", { name: "Cargar más" }));

    await waitFor(() => {
      expect(within(table).getByText("ultima-0").closest("tr")).toHaveFocus();
    });
    expect(screen.queryByRole("button", { name: "Cargar más" })).not.toBeInTheDocument();
  });

  it("si la imagen cuyo «Quitar» tiene el foco empieza a transcribirse, el foco sigue en ella", async () => {
    mockApi({ "GET /sessions": () => jsonResponse([]) });
    renderPage();
    await screen.findByText(/todavía no hay sesiones/i);
    setQueue([
      item("a", "a.png", { status: "transcribing", startedAt: Date.now() }),
      item("b", "b.png"),
    ]);
    const queue = screen.getByRole("region", { name: "Cola" });
    within(queue).getByRole("button", { name: "Quitar b.png" }).focus();

    act(() => {
      useQueueStore.setState((state) => ({
        items: state.items.map((entry) =>
          entry.id === "a"
            ? { ...entry, status: "done", result: transcribed("s1", 0) }
            : { ...entry, status: "transcribing", startedAt: Date.now() },
        ),
      }));
    });

    expect(within(queue).getByText("b.png").closest("li")).toHaveFocus();
  });

  it("si se pierde la conexión, la cola se pausa y se reanuda a petición", async () => {
    let posts = 0;
    mockApi({
      "GET /sessions": () => jsonResponse([]),
      "POST /transcribe": () => {
        posts += 1;
        return posts === 1
          ? Promise.reject(new TypeError("Failed to fetch"))
          : jsonResponse(transcribed(`s${String(posts)}`), 201);
      },
    });
    renderPage();
    await screen.findByText(/todavía no hay sesiones/i);

    await userEvent.upload(fileInput(), [png("uno.png"), png("dos.png")]);

    const queue = screen.getByRole("region", { name: "Cola" });
    expect(await within(queue).findByText(/la cola está en pausa/i)).toBeVisible();
    expect(within(queue).getByText(/no se pudo conectar con el servidor/i)).toBeVisible();
    expect(within(queue).getByText("En cola")).toBeVisible();
    expect(posts).toBe(1);

    await userEvent.click(within(queue).getByRole("button", { name: "Reanudar" }));

    await waitFor(() => {
      expect(within(queue).getByText("1 hallazgo")).toBeVisible();
    });
    expect(posts).toBe(2);
    expect(within(queue).queryByText(/la cola está en pausa/i)).not.toBeInTheDocument();
    expect(within(queue).getByRole("heading", { name: "Cola" })).toHaveFocus();
  });

  it("acepta imágenes soltadas sobre la zona de subida", async () => {
    mockApi({
      "GET /sessions": () => jsonResponse([]),
      "POST /transcribe": () => jsonResponse(transcribed("soltada0-1"), 201),
    });
    renderPage();
    await screen.findByText(/todavía no hay sesiones/i);
    const zone = screen.getByText(/o arrástralas aquí/i).parentElement;
    if (!zone) throw new Error("falta la zona de subida");

    fireEvent.drop(zone, { dataTransfer: { files: [png("soltada.png")], types: ["Files"] } });

    const queue = screen.getByRole("region", { name: "Cola" });
    expect(within(queue).getByText("soltada.png")).toBeVisible();
    await waitFor(() => {
      expect(within(queue).getByText("1 hallazgo")).toBeVisible();
    });
  });

  it("no enseña a la siguiente persona de la pestaña las sesiones que vio la anterior", async () => {
    const bruno: UserRead = {
      ...ANA,
      id: "b7c1a3f0-0000-4000-8000-000000000002",
      username: "bruno",
    };
    const brunoPage = deferred<Response>();
    let listed = 0;
    mockApi({
      "GET /sessions": () => {
        listed += 1;
        return listed === 1 ? jsonResponse([session("deana000-1")]) : brunoPage.promise;
      },
    });
    const router = renderPage();
    expect(await screen.findByText("deana000")).toBeVisible();

    // Sale una y entra otra sin que React llegue a pintar la pestaña sin sesión.
    act(() => {
      useAuthStore.getState().signOut("signed-out");
      signInAs(bruno);
    });
    expect(router.state.location.pathname).toBe("/transcripcion");

    expect(await screen.findByText(/cargando sesiones/i)).toBeVisible();
    expect(screen.queryByText("deana000")).not.toBeInTheDocument();
    brunoPage.resolve(jsonResponse([]));
    expect(await screen.findByText(/todavía no hay sesiones/i)).toBeVisible();
  });

  it("tras «Cargar más» no mueve el foco si la persona ya está en otro sitio", async () => {
    const first = Array.from({ length: 20 }, (_, i) => session(`s-${String(i).padStart(4, "0")}`));
    const nextPage = deferred<Response>();
    let page = 0;
    mockApi({
      "GET /sessions": () => {
        page += 1;
        return page === 1 ? jsonResponse(first) : nextPage.promise;
      },
    });
    renderPage();
    const table = await screen.findByRole("table");

    await userEvent.click(screen.getByRole("button", { name: "Cargar más" }));
    const exit = screen.getByRole("button", { name: "Salir" });
    exit.focus();
    nextPage.resolve(jsonResponse([session("ultima-0000")]));

    expect(await within(table).findByText("ultima-0")).toBeVisible();
    expect(exit).toHaveFocus();
  });

  it("si «Cargar más» falla con una actualización pendiente, avisa de la página y luego la actualiza", async () => {
    const first = Array.from({ length: 20 }, (_, i) => session(`s-${String(i).padStart(4, "0")}`));
    const created: SessionSummaryRead[] = [];
    const all = () => [...[...created].reverse(), ...first, session("ultima-0000")];
    const nextPage = deferred<undefined>();
    const post = deferred<Response>();
    let secondPages = 0;
    const { calls } = mockApi({
      "GET /sessions": () => {
        const offset = Number(calls.at(-1)?.url.searchParams.get("offset"));
        const page = () => jsonResponse(all().slice(offset, offset + 20));
        if (offset === 0) return page();
        secondPages += 1;
        return secondPages === 1
          ? nextPage.promise.then(() => jsonResponse({ detail: "boom" }, 500))
          : page();
      },
      "POST /transcribe": () => post.promise,
    });
    renderPage();
    const table = await screen.findByRole("table");
    act(() => {
      useQueueStore.getState().add([png("uno.png")]);
    });
    await waitFor(() => {
      expect(calls.some((call) => call.key === "POST /transcribe")).toBe(true);
    });

    await userEvent.click(screen.getByRole("button", { name: "Cargar más" }));
    created.push(session("nueva000-1"));
    post.resolve(jsonResponse(transcribed("nueva000-1"), 201));
    await waitFor(() => {
      expect(screen.getByRole("region", { name: "Cola" })).toHaveTextContent(/1 transcrita/);
    });
    nextPage.resolve(undefined);

    expect(await screen.findByRole("alert")).toHaveTextContent(/no se pudieron cargar más/i);
    await new Promise((resolve) => setTimeout(resolve, 30));
    expect(screen.getByRole("alert")).toHaveTextContent(/no se pudieron cargar más/i);

    await userEvent.click(screen.getByRole("button", { name: "Cargar más" }));
    await waitFor(() => {
      expect(within(table).getByText("nueva000")).toBeVisible();
    });
    expect(within(table).getByText("ultima-0")).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("no avisa de la pausa si ya no queda nada en cola", async () => {
    mockApi({ "GET /sessions": () => jsonResponse([]) });
    renderPage();
    await screen.findByText(/todavía no hay sesiones/i);
    act(() => {
      useQueueStore.setState({
        paused: true,
        items: [
          item("a", "a.png", { status: "error", error: "No se pudo conectar con el servidor." }),
        ],
      });
    });

    const queue = screen.getByRole("region", { name: "Cola" });
    expect(within(queue).queryByText(/la cola está en pausa/i)).not.toBeInTheDocument();
  });

  it("tras un 401 no pide el listado sin token", async () => {
    const { calls } = mockApi({
      "GET /sessions": () => jsonResponse([]),
      "POST /transcribe": () => jsonResponse({ detail: "Not authenticated" }, 401),
    });
    renderPage();
    await screen.findByText(/todavía no hay sesiones/i);

    await userEvent.upload(fileInput(), [png("uno.png")]);

    expect(await screen.findByText(/tu sesión caducó/i)).toBeVisible();
    await new Promise((resolve) => setTimeout(resolve, 30));
    const anonymous = calls.filter(
      (call) =>
        call.key === "GET /sessions" && !new Headers(call.init?.headers).has("Authorization"),
    );
    expect(anonymous).toHaveLength(0);
  });
});
