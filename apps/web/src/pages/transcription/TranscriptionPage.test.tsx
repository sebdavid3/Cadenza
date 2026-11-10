import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import { api } from "../../api/instance";
import { useAuthStore } from "../../auth/store";
import { routes } from "../../router";
import { ANA, deferred, fakeJwt, jsonResponse, resetAuth, signInAs } from "../../test/auth-helpers";
import { job, mockApiWithInstantJobs } from "../../test/jobs";
import type { SessionSummaryRead, UserRead } from "../../types";
import { JOB_POLLING, remember, useQueueStore, type QueueItem } from "./queue";

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

/** Elige las imágenes y las envía sin indicar ningún dato (#240: antes se preparan). */
async function chooseAndTranscribe(files: File[]) {
  await userEvent.upload(fileInput(), files);
  await userEvent.click(screen.getByRole("button", { name: /^transcribir/i }));
}

/** Deja la cola en un estado dado sin enviar nada (la cola «corriendo» no arranca otra). */
function setQueue(items: QueueItem[]) {
  act(() => {
    useQueueStore.setState({ items, running: true });
  });
}

function item(id: string, name: string, changes: Partial<QueueItem> = {}): QueueItem {
  return { id, file: png(name), name, status: "queued", ...changes };
}

/** El diario de sesiones (#370), una vez que enseña al menos una lámina. */
async function findDiary(): Promise<HTMLElement> {
  const diary = screen.getByRole("region", { name: "Sesiones" });
  await waitFor(() => {
    expect(diary.querySelector("[data-session-id]")).not.toBeNull();
  });
  return diary;
}

/** Las láminas de las sesiones, en el orden en que se ven. */
function plates(diary: HTMLElement): HTMLElement[] {
  return [...diary.querySelectorAll<HTMLElement>("[data-session-id]")];
}

/** La fecha de hoy en la API: UTC sin zona. */
function nowUtc(): string {
  return new Date().toISOString().replace("Z", "");
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
    mockApiWithInstantJobs({ "GET /sessions": () => jsonResponse([]) });
    renderPage();

    expect(await screen.findByText(/todavía no hay sesiones/i)).toBeVisible();
    expect(screen.getByText(/se transcriben de una en una/i)).toBeVisible();
    // El vacío va en el día de hoy: la vista enseña su forma desde el principio.
    const today = screen.getByRole("group", { name: /^hoy, /i });
    expect(within(today).getByText(/todavía no hay sesiones/i)).toBeVisible();
    // Sin imágenes no hay cola.
    expect(screen.queryByRole("region", { name: "Cola" })).toBeNull();
  });

  it("enseña cada sesión como lámina de su día, con hora, estado, posibles errores, miniatura y enlace", async () => {
    mockApiWithInstantJobs({
      "GET /sessions": () => jsonResponse([session("aaaaaaaa-1111"), session("bbbbbbbb-2222")]),
      "GET /sessions/aaaaaaaa-1111/image": () =>
        new Response(new Uint8Array([1, 2]), { headers: { "Content-Type": "image/png" } }),
      "GET /sessions/bbbbbbbb-2222/image": () =>
        new Response(new Uint8Array([1, 2]), { headers: { "Content-Type": "image/png" } }),
    });
    renderPage();

    const diary = await findDiary();
    expect(plates(diary)).toHaveLength(2);
    // Un solo día, con su fecha en el margen.
    expect(within(diary).getAllByRole("heading", { level: 2 })).toHaveLength(1);
    expect(
      within(diary).getByRole("heading", { level: 2, name: "jueves, 22 de octubre de 2026" }),
    ).toBeVisible();
    expect(within(diary).getByText("Sesión aaaaaaaa")).toBeVisible();
    expect(plates(diary)[0]?.querySelector("time")).toHaveAttribute(
      "datetime",
      "2026-10-22T20:15:00.000Z",
    );
    // 20:15 UTC es 15:15 en Bogotá (TZ de las pruebas).
    expect(within(diary).getAllByText("15:15")).toHaveLength(2);
    expect(screen.queryByText(/assisted/i)).toBeNull();
    expect(within(diary).getAllByText("Transcrita")).toHaveLength(2);
    expect(within(diary).getAllByText("2 posibles errores")).toHaveLength(2);
    // Quien transcribe solo ve las suyas: no se dice de quién son.
    expect(screen.getByText(/^tus sesiones/i)).toBeVisible();
    expect(within(diary).queryByText("Tú")).toBeNull();
    await waitFor(() => {
      expect(createObjectURL).toHaveBeenCalledTimes(2);
    });
    // Cada sesión enlaza con su vista de solo lectura; no hay enlaces a una edición.
    expect(within(diary).getByRole("link", { name: "Sesión aaaaaaaa" })).toHaveAttribute(
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
    mockApiWithInstantJobs({
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
    const { calls } = mockApiWithInstantJobs({
      "GET /sessions": () => {
        page += 1;
        return jsonResponse(page === 1 ? first : [session("ultima-0000")]);
      },
    });
    renderPage();
    await findDiary();

    await userEvent.click(screen.getByRole("button", { name: "Cargar más" }));

    expect(await screen.findByText("Sesión ultima-0")).toBeVisible();
    const pages = calls.filter((call) => call.key === "GET /sessions");
    expect(pages.map((call) => call.url.searchParams.get("offset"))).toEqual(["0", "20"]);
    expect(pages.map((call) => call.url.searchParams.get("limit"))).toEqual(["20", "20"]);
    expect(screen.queryByRole("button", { name: "Cargar más" })).not.toBeInTheDocument();
  });

  it("no repite filas si una sesión nueva desplaza la página siguiente", async () => {
    const first = Array.from({ length: 20 }, (_, i) => session(`s-${String(i).padStart(4, "0")}`));
    let page = 0;
    mockApiWithInstantJobs({
      "GET /sessions": () => {
        page += 1;
        // Se creó una sesión entre páginas: la última de la primera vuelve a salir.
        return jsonResponse(page === 1 ? first : [first[19], session("ultima-0000")]);
      },
    });
    renderPage();
    const diary = await findDiary();

    await userEvent.click(screen.getByRole("button", { name: "Cargar más" }));

    expect(await within(diary).findByText("Sesión ultima-0")).toBeVisible();
    expect(within(diary).getAllByText("Sesión s-0019")).toHaveLength(1);
    expect(plates(diary)).toHaveLength(21);
  });

  it("si falla «Cargar más» avisa una sola vez y conserva las filas", async () => {
    const first = Array.from({ length: 20 }, (_, i) => session(`s-${String(i).padStart(4, "0")}`));
    let page = 0;
    mockApiWithInstantJobs({
      "GET /sessions": () => {
        page += 1;
        return page === 1 ? jsonResponse(first) : jsonResponse({ detail: "boom" }, 500);
      },
    });
    renderPage();
    const diary = await findDiary();

    await userEvent.click(screen.getByRole("button", { name: "Cargar más" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/no se pudieron cargar más/i);
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(plates(diary)).toHaveLength(20);
    expect(screen.getByRole("button", { name: "Cargar más" })).toHaveAttribute(
      "aria-disabled",
      "false",
    );
  });

  it("un investigador ve el propietario de cada sesión", async () => {
    const investigador: UserRead = { ...ANA, id: "inv-1", username: "irene", role: "investigador" };
    mockApiWithInstantJobs({
      "GET /sessions": () =>
        jsonResponse([
          session("aaaaaaaa-1", { owner_id: ANA.id }),
          session("bbbbbbbb-2", { owner_id: "inv-1" }),
        ]),
      "GET /users": () => jsonResponse([ANA, investigador]),
    });
    renderPage(investigador);

    const diary = await findDiary();
    expect(screen.getByText(/^todas las sesiones/i)).toBeVisible();
    const [deAna, propia] = plates(diary);
    if (!deAna || !propia) throw new Error("faltan láminas");
    expect(await within(deAna).findByText("ana")).toBeVisible();
    expect(within(propia).getByText("Tú")).toBeVisible();
  });

  it("muestra un error del listado con reintento", async () => {
    let fail = true;
    mockApiWithInstantJobs({
      "GET /sessions": () =>
        fail ? jsonResponse({ detail: "boom" }, 500) : jsonResponse([session("aaaaaaaa-1")]),
    });
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent(/servidor/i);
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByText("Sesión aaaaaaaa")).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("muestra el estado de carga mientras llega el listado", async () => {
    const response = deferred<Response>();
    mockApiWithInstantJobs({ "GET /sessions": () => response.promise });
    renderPage();

    expect(await screen.findByText(/cargando sesiones/i)).toHaveAttribute("role", "status");
    response.resolve(jsonResponse([]));
    expect(await screen.findByText(/todavía no hay sesiones/i)).toBeVisible();
    expect(screen.queryByText(/cargando sesiones/i)).not.toBeInTheDocument();
  });

  it("sube varias imágenes, las transcribe en cola y sus sesiones ocupan su sitio en el día de hoy", async () => {
    const created: SessionSummaryRead[] = [];
    mockApiWithInstantJobs({
      // La más reciente primero, como la API.
      "GET /sessions": () => jsonResponse([...created].reverse()),
      "POST /transcribe": () => {
        const id = `nueva000-${String(created.length + 1)}`;
        created.push(session(id, { findings_count: 1, created_at: nowUtc() }));
        return jsonResponse(transcribed(id), 201);
      },
      "GET /sessions/nueva000-1/image": image,
      "GET /sessions/nueva000-2/image": image,
    });
    renderPage();
    await screen.findByText(/todavía no hay sesiones/i);

    await chooseAndTranscribe([png("uno.png"), png("dos.png")]);

    const today = screen.getByRole("group", { name: /^hoy, /i });
    const queue = within(today).getByRole("region", { name: "Cola" });
    const diary = screen.getByRole("region", { name: "Sesiones" });
    await waitFor(() => {
      expect(plates(diary)).toHaveLength(2);
    });
    expect(within(today).getAllByText("Sesión nueva000")).toHaveLength(2);
    expect(within(today).getAllByText("1 posible error")).toHaveLength(2);
    // Las imágenes ya son sesiones: la cola no las repite, pero el recuento las sigue contando.
    expect(within(queue).queryAllByRole("listitem")).toHaveLength(0);
    expect(within(queue).getByText(/0 en cola · 2 transcritas · 0 con error/)).toBeVisible();
  });

  it("si «Limpiar terminadas» vacía la cola, el foco pasa a «Nueva transcripción»", async () => {
    mockApiWithInstantJobs({ "GET /sessions": () => jsonResponse([]) });
    renderPage();
    await screen.findByText(/todavía no hay sesiones/i);
    setQueue([
      item("a", "a.png", { status: "done", result: transcribed("s1", 0) }),
      item("b", "b.png", { status: "error", error: "El servidor tuvo un problema." }),
    ]);
    const queue = screen.getByRole("region", { name: "Cola" });

    await userEvent.click(within(queue).getByRole("button", { name: /limpiar terminadas/i }));

    expect(screen.queryByRole("region", { name: "Cola" })).toBeNull();
    expect(screen.getByRole("button", { name: "Nueva transcripción" })).toHaveFocus();
  });

  it("si se quita la única imagen, el foco pasa a «Nueva transcripción»", async () => {
    mockApiWithInstantJobs({ "GET /sessions": () => jsonResponse([]) });
    renderPage();
    await screen.findByText(/todavía no hay sesiones/i);
    setQueue([item("a", "a.png")]);
    const queue = screen.getByRole("region", { name: "Cola" });

    await userEvent.click(within(queue).getByRole("button", { name: "Quitar a.png" }));

    expect(screen.queryByRole("region", { name: "Cola" })).toBeNull();
    expect(screen.getByRole("button", { name: "Nueva transcripción" })).toHaveFocus();
  });

  it("el foco no salta a la sesión si la persona ya había dejado la cola", async () => {
    const refresh = deferred<Response>();
    let listed = 0;
    mockApiWithInstantJobs({
      "GET /sessions": () => {
        listed += 1;
        return listed === 1 ? jsonResponse([]) : refresh.promise;
      },
      "POST /transcribe": () => jsonResponse(transcribed("dejada00-1", 0), 201),
    });
    renderPage();
    await screen.findByText(/todavía no hay sesiones/i);
    await chooseAndTranscribe([png("uno.png")]);
    const queue = screen.getByRole("region", { name: "Cola" });
    const open = await within(queue).findByRole("link", { name: "Abrir la sesión de uno.png" });

    // La persona pasa por la lámina y se va a otra parte de la página (el foco, a ninguna).
    act(() => {
      open.focus();
      open.blur();
    });
    await act(() => new Promise((resolve) => setTimeout(resolve, 0)));
    refresh.resolve(jsonResponse([session("dejada00-1", { created_at: nowUtc() })]));

    expect(await screen.findByText("Sesión dejada00")).toBeVisible();
    expect(document.body).toHaveFocus();
  });

  it("si la sesión ya estaba en el listado al terminar, el foco pasa a su lámina", async () => {
    mockApiWithInstantJobs({
      "GET /sessions": () =>
        jsonResponse([session("lista000-1", { created_at: nowUtc(), findings_count: 0 })]),
    });
    renderPage();
    const diary = await findDiary();
    setQueue([item("a", "a.png", { status: "transcribing", startedAt: Date.now() })]);
    const queue = screen.getByRole("region", { name: "Cola" });
    act(() => {
      within(queue).getByText("a.png").closest("li")?.focus();
    });

    act(() => {
      useQueueStore.setState((state) => ({
        items: state.items.map((entry) => ({
          ...entry,
          status: "done" as const,
          result: transcribed("lista000-1", 0),
        })),
      }));
    });

    expect(within(queue).queryAllByRole("listitem")).toHaveLength(0);
    expect(within(diary).getByText("Sesión lista000").closest("li")).toHaveFocus();
  });

  it("anuncia la cola aunque aparezca por una imagen rechazada", async () => {
    mockApiWithInstantJobs({ "GET /sessions": () => jsonResponse([]) });
    renderPage();
    await screen.findByText(/todavía no hay sesiones/i);
    // La región viva existe antes de que haya cola: así se anuncia lo que cambie.
    const live = screen
      .getAllByRole("status")
      .find((element) => element.classList.contains("visually-hidden"));
    if (!live) throw new Error("falta la región viva de la cola");
    expect(live).toHaveTextContent("");

    await userEvent.upload(fileInput(), new File(["hola"], "notas.txt", { type: "text/plain" }), {
      applyAccept: false,
    });

    expect(live).toHaveTextContent("Cola: 0 en cola · 0 transcritas · 1 con error");
    // Los límites se ven antes de elegir.
    expect(screen.getByText("PNG o JPEG, de hasta 20 MB.")).toBeVisible();
  });

  it("una imagen transcrita deja su sitio a la lámina de su sesión, y el foco pasa con ella", async () => {
    const refresh = deferred<Response>();
    let listed = 0;
    mockApiWithInstantJobs({
      "GET /sessions": () => {
        listed += 1;
        return listed === 1 ? jsonResponse([]) : refresh.promise;
      },
      "POST /transcribe": () => jsonResponse(transcribed("hecha000-1", 2), 201),
    });
    renderPage();
    await screen.findByText(/todavía no hay sesiones/i);

    await chooseAndTranscribe([png("uno.png")]);
    const queue = screen.getByRole("region", { name: "Cola" });
    const open = await within(queue).findByRole("link", { name: "Abrir la sesión de uno.png" });
    expect(within(queue).getByText("2 posibles errores")).toBeVisible();
    act(() => {
      open.focus();
    });

    refresh.resolve(
      jsonResponse([session("hecha000-1", { findings_count: 2, created_at: nowUtc() })]),
    );

    const diary = screen.getByRole("region", { name: "Sesiones" });
    await waitFor(() => {
      expect(within(diary).getByText("Sesión hecha000").closest("li")).toHaveFocus();
    });
    expect(within(queue).queryAllByRole("listitem")).toHaveLength(0);
    expect(within(queue).getByText("0 en cola · 1 transcrita · 0 con error")).toBeVisible();
  });

  it("agrupa las sesiones por día local, con hoy y ayer señalados en el margen", async () => {
    const at = (daysAgo: number) => {
      const date = new Date();
      date.setDate(date.getDate() - daysAgo);
      date.setHours(12, 0, 0, 0);
      return date.toISOString().replace("Z", "");
    };
    mockApiWithInstantJobs({
      "GET /sessions": () =>
        jsonResponse([
          session("hoy00000-1", { created_at: at(0) }),
          session("ayer0000-1", { created_at: at(1) }),
          session("ayer0000-2", { created_at: at(1) }),
          session("antes000-1", { created_at: at(9) }),
        ]),
    });
    renderPage();

    const diary = await findDiary();
    const days = within(diary).getAllByRole("group");
    expect(days.map((day) => plates(day).length)).toEqual([1, 2, 1]);
    const [today, yesterday, before] = days;
    if (!today || !yesterday || !before) throw new Error("faltan días");
    expect(today).toHaveAccessibleName(/^hoy, /i);
    expect(yesterday).toHaveAccessibleName(/^ayer, /i);
    expect(before).not.toHaveAccessibleName(/^(hoy|ayer), /i);
    expect(within(yesterday).getByText("Ayer")).toBeVisible();
  });

  it("la cola solo aparece con imágenes, en el día de hoy aunque no tenga sesiones", async () => {
    mockApiWithInstantJobs({ "GET /sessions": () => jsonResponse([session("antes000-1")]) });
    renderPage();
    const diary = await findDiary();
    expect(within(diary).getAllByRole("heading", { level: 2 })).toHaveLength(1);
    expect(screen.queryByRole("region", { name: "Cola" })).toBeNull();

    setQueue([item("a", "a.png")]);

    const days = within(diary).getAllByRole("group");
    expect(days).toHaveLength(2);
    const [today] = days;
    if (!today) throw new Error("falta el día de hoy");
    expect(today).toHaveAccessibleName(/^hoy, /i);
    expect(within(today).getByRole("region", { name: "Cola" })).toBeVisible();
    expect(plates(today)).toHaveLength(0);
  });

  it("si la sesión caduca a mitad del lote, lleva al acceso, conserva la cola y la reanuda al volver", async () => {
    let posts = 0;
    const created: SessionSummaryRead[] = [];
    mockApiWithInstantJobs({
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

    await chooseAndTranscribe([png("uno.png"), png("dos.png")]);

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
    // La vista se carga bajo demanda: puede no estar dibujada aún al cambiar la ruta.
    const queue = await screen.findByRole("region", { name: "Cola" });
    expect(await screen.findByText("Sesión retomada")).toBeVisible();
    expect(within(queue).getByText("0 en cola · 1 transcrita · 1 con error")).toBeVisible();
    expect(within(queue).getByText(/vuelve a entrar/i)).toBeVisible();
    expect(within(queue).getByRole("button", { name: /reintentar uno\.png/i })).toBeVisible();
    expect(posts).toBe(2);
  });

  it("rechaza en el navegador un archivo que no es imagen", async () => {
    const { calls } = mockApiWithInstantJobs({ "GET /sessions": () => jsonResponse([]) });
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
    expect(calls.some((call) => call.key === "POST /transcription-jobs")).toBe(false);
  });

  it("marca en violeta las sesiones con posibles errores y no las que no tienen", async () => {
    mockApiWithInstantJobs({
      "GET /sessions": () =>
        jsonResponse([
          session("aaaaaaaa-1", { findings_count: 3 }),
          session("bbbbbbbb-2", { findings_count: 0 }),
        ]),
    });
    renderPage();

    const diary = await findDiary();
    const [withFindings, without] = plates(diary);
    if (!withFindings || !without) throw new Error("faltan láminas");
    expect(within(withFindings).getByText("3 posibles errores")).toHaveClass("chip--finding");
    // La imagen lleva la trama del compás dudoso.
    expect(withFindings).toHaveAttribute("data-flagged", "true");
    expect(without.querySelector(".chip--finding")).toBeNull();
    expect(without).toHaveAttribute("data-flagged", "false");
  });

  it("distingue una sesión finalizada de las que siguen abiertas (#187)", async () => {
    mockApiWithInstantJobs({
      "GET /sessions": () =>
        jsonResponse([
          session("aaaaaaaa-1", { status: "finalized" }),
          session("bbbbbbbb-2", { status: "correcting" }),
        ]),
    });
    renderPage();

    const diary = await findDiary();
    const [finalized, open] = plates(diary);
    if (!finalized || !open) throw new Error("faltan láminas");
    expect(within(finalized).getByText("Finalizada")).toHaveClass("chip--finalized");
    expect(within(open).getByText("En corrección")).not.toHaveClass("chip--finalized");
  });

  it("con un lote en curso pide confirmación al cerrar la pestaña y al salir", async () => {
    mockApiWithInstantJobs({ "GET /sessions": () => jsonResponse([]) });
    const router = renderPage();
    await screen.findByText(/todavía no hay sesiones/i);
    act(() => {
      useQueueStore.setState({
        items: [
          {
            id: "x",
            file: new File([new Uint8Array(4)], "pendiente.png", { type: "image/png" }),
            name: "pendiente.png",
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
    mockApiWithInstantJobs({ "GET /sessions": () => jsonResponse([]) });
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
      useQueueStore.getState().clearFinished(api);
      void useQueueStore.getState().remove("x", api);
    });
    const later = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(later);
    expect(later.defaultPrevented).toBe(false);
  });

  it("separa en el recuento las transcritas de las que fallaron", async () => {
    mockApiWithInstantJobs({ "GET /sessions": () => jsonResponse([]) });
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

  it("cada imagen transcrita enlaza a su sesión (#277)", async () => {
    mockApiWithInstantJobs({ "GET /sessions": () => jsonResponse([]) });
    renderPage();
    await screen.findByText(/todavía no hay sesiones/i);

    setQueue([
      item("a", "a.png", {
        status: "done",
        result: transcribed("abcdef12-1"),
        data: { title: "Minueto", composer: "", parts: [] },
      }),
      item("b", "b.png", { status: "error", error: "No se reconoció ninguna partitura." }),
    ]);

    const queue = screen.getByRole("region", { name: "Cola" });
    const links = within(queue).getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAccessibleName("Abrir la sesión de Minueto");
    expect(links[0]).toHaveAttribute("href", "/sesiones/abcdef12-1");
  });

  it("el contador de la imagen en curso cuenta desde que empezó, aunque se vuelva a la vista", async () => {
    mockApiWithInstantJobs({ "GET /sessions": () => jsonResponse([]) });
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
    mockApiWithInstantJobs({ "GET /sessions": () => jsonResponse([]) });
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

  it("el selector oculto no es una parada de foco y soltar nada no abre nada en la pestaña", async () => {
    mockApiWithInstantJobs({ "GET /sessions": () => jsonResponse([]) });
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

    // Fuera de las vistas con zona de subida (esta y el recuadro de la portada, #277).
    await act(() => router.navigate("/no-existe"));
    expect(dropOutside().defaultPrevented).toBe(false);
  });

  it("descarga a lo sumo tres miniaturas a la vez", async () => {
    const pending = new Map<string, ReturnType<typeof deferred<Response>>>();
    const ids = Array.from({ length: 5 }, (_, i) => `img00000-${String(i)}`);
    mockApiWithInstantJobs({
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
    await findDiary();

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
    const { calls } = mockApiWithInstantJobs({
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
    const { calls } = mockApiWithInstantJobs({
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
    const diary = await findDiary();
    act(() => {
      useQueueStore.getState().add([png("uno.png")]);
    });
    await waitFor(() => {
      expect(calls.some((call) => call.key === "POST /transcription-jobs")).toBe(true);
    });

    await userEvent.click(screen.getByRole("button", { name: "Cargar más" }));
    created.push(session("nueva000-1"));
    post.resolve(jsonResponse(transcribed("nueva000-1"), 201));
    await waitFor(() => {
      expect(screen.getByRole("region", { name: "Cola" })).toHaveTextContent(/1 transcrita/);
    });
    nextPage.resolve(undefined);

    await waitFor(() => {
      expect(within(diary).getByText("Sesión nueva000")).toBeVisible();
    });
    expect(within(diary).getByText("Sesión ultima-0")).toBeVisible();
    expect(plates(diary)).toHaveLength(22);
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
    const { calls } = mockApiWithInstantJobs({
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
    const diary = await findDiary();
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
      expect(within(diary).getByText("Sesión nueva000")).toBeVisible();
    });
    await waitFor(() => {
      expect(more).toHaveAttribute("aria-disabled", "false");
    });
    await userEvent.click(more);

    await waitFor(() => {
      expect(within(diary).getByText("Sesión ultima-0")).toBeVisible();
    });
    expect(offsets()).toEqual(["0", "0", "20"]);
  });

  it("tras «Cargar más» el foco pasa a la primera sesión nueva", async () => {
    const first = Array.from({ length: 20 }, (_, i) => session(`s-${String(i).padStart(4, "0")}`));
    let page = 0;
    mockApiWithInstantJobs({
      "GET /sessions": () => {
        page += 1;
        return jsonResponse(page === 1 ? first : [session("ultima-0000")]);
      },
    });
    renderPage();
    const diary = await findDiary();

    await userEvent.click(screen.getByRole("button", { name: "Cargar más" }));

    await waitFor(() => {
      expect(within(diary).getByText("Sesión ultima-0").closest("li")).toHaveFocus();
    });
    expect(screen.queryByRole("button", { name: "Cargar más" })).not.toBeInTheDocument();
  });

  it("si la imagen cuyo «Quitar» tiene el foco empieza a transcribirse, el foco sigue en ella", async () => {
    mockApiWithInstantJobs({ "GET /sessions": () => jsonResponse([]) });
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
    mockApiWithInstantJobs({
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

    await chooseAndTranscribe([png("uno.png"), png("dos.png")]);

    const queue = screen.getByRole("region", { name: "Cola" });
    expect(await within(queue).findByText(/la cola está en pausa/i)).toBeVisible();
    expect(within(queue).getByText(/no se pudo conectar con el servidor/i)).toBeVisible();
    expect(within(queue).getByText("En cola")).toBeVisible();
    expect(posts).toBe(1);

    await userEvent.click(within(queue).getByRole("button", { name: "Reanudar" }));

    await waitFor(() => {
      expect(within(queue).getByText("1 posible error")).toBeVisible();
    });
    expect(posts).toBe(2);
    expect(within(queue).queryByText(/la cola está en pausa/i)).not.toBeInTheDocument();
    expect(within(queue).getByRole("heading", { name: "Cola" })).toHaveFocus();
  });

  it("acepta imágenes soltadas en cualquier parte de la vista y avisa mientras se arrastran", async () => {
    mockApiWithInstantJobs({
      "GET /sessions": () => jsonResponse([]),
      "POST /transcribe": () => jsonResponse(transcribed("soltada0-1"), 201),
    });
    renderPage();
    await screen.findByText(/todavía no hay sesiones/i);
    const page = screen.getByRole("main");
    const empty = screen.getByText(/todavía no hay sesiones/i);

    expect(screen.queryByText("Suelta las imágenes")).toBeNull();
    fireEvent.dragEnter(empty, { dataTransfer: { files: [], types: ["Files"] } });
    expect(screen.getByText("Suelta las imágenes")).toBeInTheDocument();
    // Un texto arrastrado no es una imagen: no cambia nada.
    fireEvent.dragEnter(page, { dataTransfer: { files: [], types: ["text/plain"] } });
    fireEvent.dragLeave(empty, { dataTransfer: { files: [], types: ["Files"] } });
    expect(screen.queryByText("Suelta las imágenes")).toBeNull();

    fireEvent.dragEnter(empty, { dataTransfer: { files: [], types: ["Files"] } });
    fireEvent.drop(empty, { dataTransfer: { files: [png("soltada.png")], types: ["Files"] } });
    expect(screen.queryByText("Suelta las imágenes")).toBeNull();
    // Antes de enviar se piden los datos: el foco va al primero (#240). Con el selector no se
    // comprueba aquí: user-event devuelve el foco al campo de archivo al cerrar el diálogo.
    expect(screen.getByLabelText("Nombre de la partitura")).toHaveFocus();
    await userEvent.click(screen.getByRole("button", { name: /^transcribir/i }));

    const queue = screen.getByRole("region", { name: "Cola" });
    expect(within(queue).getByText("soltada.png")).toBeVisible();
    await waitFor(() => {
      expect(within(queue).getByText("1 posible error")).toBeVisible();
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
    mockApiWithInstantJobs({
      "GET /sessions": () => {
        listed += 1;
        return listed === 1 ? jsonResponse([session("deana000-1")]) : brunoPage.promise;
      },
    });
    const router = renderPage();
    expect(await screen.findByText("Sesión deana000")).toBeVisible();

    // Sale una y entra otra sin que React llegue a pintar la pestaña sin sesión.
    act(() => {
      useAuthStore.getState().signOut("signed-out");
      signInAs(bruno);
    });
    expect(router.state.location.pathname).toBe("/transcripcion");

    expect(await screen.findByText(/cargando sesiones/i)).toBeVisible();
    expect(screen.queryByText("Sesión deana000")).not.toBeInTheDocument();
    brunoPage.resolve(jsonResponse([]));
    expect(await screen.findByText(/todavía no hay sesiones/i)).toBeVisible();
  });

  it("tras «Cargar más» no mueve el foco si la persona ya está en otro sitio", async () => {
    const first = Array.from({ length: 20 }, (_, i) => session(`s-${String(i).padStart(4, "0")}`));
    const nextPage = deferred<Response>();
    let page = 0;
    mockApiWithInstantJobs({
      "GET /sessions": () => {
        page += 1;
        return page === 1 ? jsonResponse(first) : nextPage.promise;
      },
    });
    renderPage();
    const diary = await findDiary();

    await userEvent.click(screen.getByRole("button", { name: "Cargar más" }));
    const exit = screen.getByRole("button", { name: "Salir" });
    exit.focus();
    nextPage.resolve(jsonResponse([session("ultima-0000")]));

    expect(await within(diary).findByText("Sesión ultima-0")).toBeVisible();
    expect(exit).toHaveFocus();
  });

  it("si «Cargar más» falla con una actualización pendiente, avisa de la página y luego la actualiza", async () => {
    const first = Array.from({ length: 20 }, (_, i) => session(`s-${String(i).padStart(4, "0")}`));
    const created: SessionSummaryRead[] = [];
    const all = () => [...[...created].reverse(), ...first, session("ultima-0000")];
    const nextPage = deferred<undefined>();
    const post = deferred<Response>();
    let secondPages = 0;
    const { calls } = mockApiWithInstantJobs({
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
    const diary = await findDiary();
    act(() => {
      useQueueStore.getState().add([png("uno.png")]);
    });
    await waitFor(() => {
      expect(calls.some((call) => call.key === "POST /transcription-jobs")).toBe(true);
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
      expect(within(diary).getByText("Sesión nueva000")).toBeVisible();
    });
    expect(within(diary).getByText("Sesión ultima-0")).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("no avisa de la pausa si ya no queda nada en cola", async () => {
    mockApiWithInstantJobs({ "GET /sessions": () => jsonResponse([]) });
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
    const { calls } = mockApiWithInstantJobs({
      "GET /sessions": () => jsonResponse([]),
      "POST /transcribe": () => jsonResponse({ detail: "Not authenticated" }, 401),
    });
    renderPage();
    await screen.findByText(/todavía no hay sesiones/i);

    await chooseAndTranscribe([png("uno.png")]);

    expect(await screen.findByText(/tu sesión caducó/i)).toBeVisible();
    await new Promise((resolve) => setTimeout(resolve, 30));
    const anonymous = calls.filter(
      (call) =>
        call.key === "GET /sessions" && !new Headers(call.init?.headers).has("Authorization"),
    );
    expect(anonymous).toHaveLength(0);
  });
});

describe("datos de la partitura antes de transcribir (#240)", () => {
  /** Escribe de una vez (pegando): letra a letra, bajo carga, la prueba pasaría del límite. */
  async function fill(element: HTMLElement, text: string) {
    await userEvent.click(element);
    await userEvent.paste(text);
  }

  /** Los campos del formulario de `POST /transcribe`, sin el archivo. */
  function sentData(call: { init: RequestInit | undefined } | undefined) {
    const body = call?.init?.body;
    if (!(body instanceof FormData)) throw new Error("no es un formulario");
    return [...body.entries()]
      .filter(([key]) => key !== "file")
      .map(([key, value]) => [key, typeof value === "string" ? value : value.name]);
  }

  it("pide el nombre, el compositor y los instrumentos antes de enviar, y los envía con la imagen", async () => {
    const { calls } = mockApiWithInstantJobs({
      "GET /sessions": () => jsonResponse([]),
      "POST /transcribe": () => jsonResponse(transcribed("nombrada-1"), 201),
    });
    renderPage();
    await screen.findByText(/todavía no hay sesiones/i);

    await userEvent.upload(fileInput(), [png("mondnacht.png")]);

    // Nada sale hasta pulsar «Transcribir».
    const form = screen.getByRole("form", { name: /antes de transcribir/i });
    const title = within(form).getByLabelText("Nombre de la partitura");
    expect(title).toHaveAttribute("maxlength", "200");
    expect(within(form).getByText(/se llama como el archivo/i)).toBeVisible();
    expect(within(form).getByText("mondnacht.png")).toBeVisible();
    expect(calls.some((call) => call.key === "POST /transcription-jobs")).toBe(false);
    expect(useQueueStore.getState().items).toEqual([]);
    // Valores por defecto: sin nombre, sin compositor y los instrumentos sin indicar.
    const upper = within(form).getByLabelText("Parte de arriba");
    const second = within(form).getByLabelText("Segunda parte");
    expect(upper).toHaveValue("");
    expect(second).toHaveValue("");

    await fill(title, "  Mondnacht ");
    await fill(within(form).getByLabelText("Compositor"), "Robert Schumann");
    await userEvent.selectOptions(upper, "Voz");
    await userEvent.selectOptions(second, "Piano");
    await userEvent.click(within(form).getByRole("button", { name: "Transcribir la imagen" }));

    const queue = screen.getByRole("region", { name: "Cola" });
    await waitFor(() => {
      expect(within(queue).getByText("1 posible error")).toBeVisible();
    });
    expect(sentData(calls.find((call) => call.key === "POST /transcription-jobs"))).toEqual([
      ["title", "Mondnacht"],
      ["composer", "Robert Schumann"],
      ["instruments", "voice"],
      ["part_names", ""],
      ["instruments", "piano"],
      ["part_names", ""],
    ]);
    // La cola dice con qué nombre se crea la sesión, y el formulario desaparece.
    expect(within(queue).getByText("Mondnacht")).toBeVisible();
    expect(screen.queryByRole("form", { name: /antes de transcribir/i })).toBeNull();
    expect(within(queue).getByRole("heading", { name: "Cola" })).toHaveFocus();
  });

  it("al volver a la vista con imágenes preparadas, el foco no salta al formulario", async () => {
    mockApiWithInstantJobs({ "GET /sessions": () => jsonResponse([]) });
    // Las imágenes ya esperaban (la cola es de quien entró): se sale y se vuelve a la vista.
    signInAs(ANA);
    act(() => {
      useQueueStore.getState().prepare([png("uno.png")]);
    });
    renderPage();
    await screen.findByText(/todavía no hay sesiones/i);

    expect(screen.getByRole("form", { name: /antes de transcribir/i })).toBeVisible();
    expect(screen.getByLabelText("Nombre de la partitura")).not.toHaveFocus();
  });

  it("en un lote, los datos valen para todas las imágenes o se cambian en cada una", async () => {
    const { calls } = mockApiWithInstantJobs({
      "GET /sessions": () => jsonResponse([]),
      "POST /transcribe": () => jsonResponse(transcribed(`lote0000-${String(calls.length)}`), 201),
    });
    renderPage();
    await screen.findByText(/todavía no hay sesiones/i);

    await userEvent.upload(fileInput(), [png("uno.png"), png("dos.png")]);

    const form = screen.getByRole("form", { name: /antes de transcribir/i });
    const common = within(form).getByRole("group", { name: "Datos para todas las imágenes" });
    await fill(within(common).getByLabelText("Compositor"), "Clara Schumann");
    await userEvent.selectOptions(within(common).getByLabelText("Parte de arriba"), "Violín");

    await userEvent.click(
      within(form).getByRole("button", { name: "Cambiar los datos de dos.png" }),
    );
    const own = within(form).getByRole("group", { name: "Datos de dos.png" });
    // Empiezan siendo los comunes.
    expect(within(own).getByLabelText("Compositor")).toHaveValue("Clara Schumann");
    await fill(within(own).getByLabelText("Nombre de la partitura"), "Romanze");
    await userEvent.selectOptions(within(own).getByLabelText("Parte de arriba"), "Otro");
    const other = within(own).getByLabelText("Nombre del instrumento");
    expect(other).toHaveAttribute("maxlength", "100");
    await fill(other, "Viola");
    await userEvent.click(within(form).getByRole("button", { name: "Transcribir 2 imágenes" }));

    const queue = screen.getByRole("region", { name: "Cola" });
    await waitFor(() => {
      expect(within(queue).getAllByText("1 posible error")).toHaveLength(2);
    });
    const posts = calls.filter((call) => call.key === "POST /transcription-jobs");
    expect(posts.map(sentData)).toEqual([
      [
        ["composer", "Clara Schumann"],
        ["instruments", "violin"],
        ["part_names", ""],
      ],
      [
        ["title", "Romanze"],
        ["composer", "Clara Schumann"],
        ["instruments", "other"],
        ["part_names", "Viola"],
      ],
    ]);
  });

  it("sin datos envía solo la imagen; quitar y descartar no envían nada", async () => {
    const { calls } = mockApiWithInstantJobs({
      "GET /sessions": () => jsonResponse([]),
      "POST /transcribe": () => jsonResponse(transcribed("sindatos-1"), 201),
    });
    renderPage();
    await screen.findByText(/todavía no hay sesiones/i);

    await userEvent.upload(fileInput(), [png("uno.png"), png("dos.png")]);
    const form = screen.getByRole("form", { name: /antes de transcribir/i });
    await userEvent.click(within(form).getByRole("button", { name: "Quitar uno.png" }));
    expect(within(form).queryByText("uno.png")).toBeNull();
    // El recuento se anuncia al cambiar.
    expect(within(form).getByText("1 imagen")).toHaveAttribute("aria-live", "polite");
    await userEvent.click(within(form).getByRole("button", { name: "Descartar" }));

    expect(screen.queryByRole("form", { name: /antes de transcribir/i })).toBeNull();
    expect(screen.getByRole("button", { name: "Nueva transcripción" })).toHaveFocus();
    expect(calls.some((call) => call.key === "POST /transcription-jobs")).toBe(false);

    await chooseAndTranscribe([png("tres.png")]);
    await waitFor(() => {
      expect(calls.filter((call) => call.key === "POST /transcription-jobs")).toHaveLength(1);
    });
    expect(sentData(calls.find((call) => call.key === "POST /transcription-jobs"))).toEqual([]);
  });

  it("nombra cada sesión del listado por su título, su archivo o su identificador", async () => {
    mockApiWithInstantJobs({
      "GET /sessions": () =>
        jsonResponse([
          session("aaaaaaaa-1111", {
            title: "Mondnacht",
            composer: "Robert Schumann",
            source_filename: "mondnacht.png",
            condition: "unassisted",
            test_score_id: "TS-03",
          }),
          session("bbbbbbbb-2222", { title: null, source_filename: "pagina-2.png" }),
          session("cccccccc-3333"),
        ]),
      "GET /sessions/aaaaaaaa-1111/image": image,
      "GET /sessions/bbbbbbbb-2222/image": image,
      "GET /sessions/cccccccc-3333/image": image,
    });
    renderPage();

    const diary = await findDiary();
    expect(within(diary).getByRole("link", { name: "Mondnacht" })).toHaveAttribute(
      "href",
      "/sesiones/aaaaaaaa-1111",
    );
    // El compositor va con la hora, bajo el nombre.
    expect(within(diary).getByText("Robert Schumann")).toBeVisible();
    expect(within(diary).getByRole("link", { name: "pagina-2.png" })).toHaveAttribute(
      "href",
      "/sesiones/bbbbbbbb-2222",
    );
    expect(within(diary).getByRole("link", { name: "Sesión cccccccc" })).toBeVisible();
    // Nada de los datos del estudio.
    expect(screen.queryByText(/unassisted|TS-03/i)).toBeNull();
  });
});

describe("la lámina dice en qué está la transcripción (#375)", () => {
  afterEach(() => {
    JOB_POLLING.intervalMs = 1000;
    localStorage.clear();
  });

  /** La lámina de la cola de una imagen, por el nombre que enseña. */
  function queuePlate(queue: HTMLElement, name: string): HTMLElement {
    const plate = within(queue).getByText(name).closest("li");
    if (!plate) throw new Error(`falta la lámina de ${name}`);
    return plate;
  }

  function meterWidth(plate: HTMLElement): string | null {
    return plate.querySelector<HTMLElement>(".job-progress__meter > span")?.style.width ?? null;
  }

  it("en cola con las que van delante, leyendo el pentagrama X de N, la segunda lectura y revisando", async () => {
    mockApiWithInstantJobs({
      "GET /sessions": () => jsonResponse([]),
      "GET /transcription-jobs": () => jsonResponse([]),
    });
    renderPage();
    await screen.findByText(/todavía no hay sesiones/i);
    const reading = (id: string, kind: "first" | "piano", staff: number, staffs: number) =>
      job({ id, stage: "reading", ahead: null, reading: kind, staff, staffs });
    setQueue([
      item("a", "a.png", { job: job({ id: "j-a", ahead: 2 }) }),
      item("b", "b.png", {
        status: "transcribing",
        startedAt: Date.now(),
        job: reading("j-b", "first", 3, 8),
      }),
      item("c", "c.png", {
        status: "transcribing",
        startedAt: Date.now(),
        job: reading("j-c", "piano", 2, 6),
      }),
      item("d", "d.png", {
        status: "transcribing",
        startedAt: Date.now(),
        job: job({ id: "j-d", stage: "reviewing", ahead: null }),
      }),
      item("e", "e.png", { job: job({ id: "j-e", ahead: 0 }) }),
    ]);
    const queue = screen.getByRole("region", { name: "Cola" });

    const queued = queuePlate(queue, "a.png");
    expect(within(queued).getByText("En cola")).toBeVisible();
    expect(within(queued).getByText("2 por delante")).toBeVisible();
    expect(within(queuePlate(queue, "e.png")).getByText("Es la siguiente")).toBeVisible();
    // La barra solo cuenta los pentagramas ya leídos de la lectura en curso: 2 de 8.
    const first = queuePlate(queue, "b.png");
    expect(within(first).getByText("Leyendo el pentagrama 3 de 8")).toBeVisible();
    expect(meterWidth(first)).toBe("25%");
    // La segunda lectura se nombra: la barra vuelve a empezar con una explicación.
    const piano = queuePlate(queue, "c.png");
    expect(
      within(piano).getByText("Segunda lectura, con el piano por separado: pentagrama 2 de 6"),
    ).toBeVisible();
    expect(meterWidth(piano)).toMatch(/^16\.6/);
    const reviewing = queuePlate(queue, "d.png");
    expect(within(reviewing).getByText("Revisando el compás y los posibles errores")).toBeVisible();
    expect(meterWidth(reviewing)).toBeNull();
    expect(within(queue).queryByText(/%/)).toBeNull();
  });

  it("al recargar la página, enseña las que siguen en el servidor y las que se interrumpieron", async () => {
    JOB_POLLING.intervalMs = 50;
    remember(ANA.id, { id: "perdida", name: "perdida.png" });
    mockApiWithInstantJobs({
      "GET /sessions": () => jsonResponse([]),
      "GET /transcription-jobs": () =>
        jsonResponse([
          job({
            id: "j1",
            stage: "reading",
            ahead: null,
            reading: "first",
            staff: 1,
            staffs: 4,
            source_filename: "TS-02.png",
            started_at: new Date().toISOString(),
          }),
        ]),
      "GET /sessions/perdida": () => jsonResponse({ detail: "no" }, 404),
    });
    renderPage();

    const queue = await screen.findByRole("region", { name: "Cola" });
    const running = queuePlate(queue, "TS-02.png");
    expect(await within(running).findByText("Leyendo el pentagrama 1 de 4")).toBeVisible();
    // Sin el archivo en el navegador, la miniatura lo dice.
    expect(within(running).getByText("Sin imagen")).toBeVisible();
    const lost = await waitFor(() => queuePlate(queue, "perdida.png"));
    expect(within(lost).getByText("Interrumpida")).toBeVisible();
    expect(within(lost).getByText(/se interrumpió porque el servidor se reinició/i)).toBeVisible();
    // Sin la imagen no se puede reintentar desde aquí: se quita.
    expect(within(lost).getByRole("button", { name: "Quitar perdida.png" })).toBeVisible();
    expect(within(lost).queryByRole("button", { name: /reintentar/i })).toBeNull();
  });
});
