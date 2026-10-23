import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
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

  it("lista las sesiones con fecha, estado, hallazgos y miniatura autenticada, sin enlaces a edición", async () => {
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
    expect(within(table).getAllByText("Transcrita")).toHaveLength(2);
    expect(within(table).queryByRole("columnheader", { name: /propietario/i })).toBeNull();
    await waitFor(() => {
      expect(createObjectURL).toHaveBeenCalledTimes(2);
    });
    for (const link of screen.getAllByRole("link")) {
      expect(link.getAttribute("href")).not.toMatch(/sesion|session|editor/i);
    }
  });

  it("revoca las URL de las miniaturas al salir de la vista", async () => {
    mockApi({
      "GET /sessions": () => jsonResponse([session("aaaaaaaa-1111")]),
      "GET /sessions/aaaaaaaa-1111/image": () => new Response(new Uint8Array([1])),
    });
    const router = renderPage();
    await waitFor(() => {
      expect(createObjectURL).toHaveBeenCalledOnce();
    });

    await router.navigate("/");

    await waitFor(() => {
      expect(revokeObjectURL).toHaveBeenCalledWith("blob:miniatura");
    });
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
    expect(screen.getByRole("button", { name: "Cargar más" })).toBeEnabled();
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
    mockApi({ "GET /sessions": () => jsonResponse({ detail: "boom" }, 500) });
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent(/servidor/i);
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeVisible();
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

    expect(within(screen.getByRole("region", { name: "Cola" })).getByText("12 s")).toBeVisible();
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
});
