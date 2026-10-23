import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "../../auth/store";
import { routes } from "../../router";
import { ANA, fakeJwt, jsonResponse, mockApi, resetAuth } from "../../test/auth-helpers";
import type { SessionSummaryRead, UserRead } from "../../types";
import { useQueueStore } from "./queue";

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
  useAuthStore.getState().signIn(fakeJwt(1_800_000, user.id), user);
  const router = createMemoryRouter(routes, { initialEntries: ["/transcripcion"] });
  render(<RouterProvider router={router} />);
  return router;
}

const createObjectURL = vi.fn(() => "blob:miniatura");
const revokeObjectURL = vi.fn();

beforeEach(() => {
  resetAuth();
  useQueueStore.setState({ items: [], running: false, ownerId: null });
  createObjectURL.mockClear();
  revokeObjectURL.mockClear();
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL, revokeObjectURL }));
});

afterEach(() => {
  vi.unstubAllGlobals();
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
    expect(calls.filter((call) => call.key === "GET /sessions")).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Cargar más" })).not.toBeInTheDocument();
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

  it("sube varias imágenes, las transcribe en cola y actualiza el listado", async () => {
    let listed = 0;
    let transcribedCount = 0;
    mockApi({
      "GET /sessions": () => {
        listed += 1;
        return jsonResponse(
          transcribedCount === 0 ? [] : [session(`nueva-${String(transcribedCount)}`)],
        );
      },
      "POST /transcribe": () => {
        transcribedCount += 1;
        return jsonResponse(
          {
            session_id: `nueva-${String(transcribedCount)}`,
            document_id: "d",
            omr_engine: "homr",
            findings_count: 1,
            condition: "assisted",
            test_score_id: null,
          },
          201,
        );
      },
      "GET /sessions/nueva-2/image": () => new Response(new Uint8Array([1])),
      "GET /sessions/nueva-1/image": () => new Response(new Uint8Array([1])),
    });
    renderPage();
    await screen.findByText(/todavía no hay sesiones/i);
    const input = document.querySelector<HTMLInputElement>('input[type="file"]');
    if (!input) throw new Error("falta el selector de archivos");

    await userEvent.upload(input, [
      new File([new Uint8Array(8)], "uno.png", { type: "image/png" }),
      new File([new Uint8Array(8)], "dos.png", { type: "image/png" }),
    ]);

    const queue = screen.getByRole("region", { name: "Cola" });
    await waitFor(() => {
      expect(within(queue).getAllByText("1 hallazgo")).toHaveLength(2);
    });
    expect(transcribedCount).toBe(2);
    expect(listed).toBeGreaterThan(1);
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
});
