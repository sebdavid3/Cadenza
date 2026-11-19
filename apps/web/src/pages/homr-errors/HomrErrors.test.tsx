import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, onTestFinished, vi } from "vitest";
import { useAuthStore } from "../../auth/store";
import { ApiError } from "../../api/errors";
import { routes } from "../../router";
import type { HomrErrorStatsRead } from "../../types";
import {
  group,
  payload,
  rate,
  scoreDetail,
  UNPUBLISHED,
  values,
  withExamples,
  withHistory,
} from "./fixtures";
import { HomrErrors, type StatsLoader } from "./HomrErrors";
import type { ScoreLoader } from "./selection";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function loader(...answers: (HomrErrorStatsRead | Error)[]) {
  const queue = [...answers];
  return vi.fn<StatsLoader>(() => {
    const next = queue.length > 1 ? queue.shift() : queue[0];
    return next instanceof Error || next === undefined
      ? Promise.reject(next ?? new Error("sin respuesta"))
      : Promise.resolve(next);
  });
}

function section() {
  return screen.getByRole("main", { name: "Errores de HOMR, en vivo" });
}

describe("la página de los errores de HOMR", () => {
  it("enseña lo que dicen los datos de Cadenza y cuándo se calcularon", async () => {
    render(<HomrErrors load={loader(payload([group("cadenza"), group("primus")]))} />);

    expect(await screen.findByText(/calculadas el/)).toBeInTheDocument();
    expect(screen.getByText(/19 de noviembre/)).toBeInTheDocument();
    const region = section();
    expect(within(region).getByRole("button", { name: "Cadenza" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(within(region).getByText("12 transcripciones")).toBeInTheDocument();
    expect(within(region).getByText(/es lo que más se corrige/)).toBeInTheDocument();
    expect(within(region).getByText(/es la figura que peor lee/)).toBeInTheDocument();
    // Qué significa cada palabra de «Qué pasó con cada nota leída».
    for (const word of ["Corregida", "Sobraba", "Sin alinear", "Bien leída"]) {
      expect(within(region).getByText(word)).toBeInTheDocument();
    }
    expect(within(region).getByText("Nota que HOMR no leyó")).toBeInTheDocument();
    expect(within(region).getByRole("table")).toBeInTheDocument();
  });

  it("explica qué son HOMR, PrIMuS y Camera-PrIMuS, con sus enlaces", async () => {
    render(<HomrErrors load={loader(payload([group("primus")]))} />);
    await screen.findByText(/calculadas el/);

    expect(screen.getByRole("link", { name: "github.com/liebharc/homr" })).toHaveAttribute(
      "href",
      "https://github.com/liebharc/homr",
    );
    expect(screen.getByRole("link", { name: "grfia.dlsi.ua.es/primus" })).toHaveAttribute(
      "href",
      "https://grfia.dlsi.ua.es/primus/",
    );
    expect(screen.getByText(/Calvo-Zaragoza y Rizo, 2018/)).toBeInTheDocument();
    expect(screen.getByText(/Camera-PrIMuS son los mismos/)).toBeInTheDocument();
  });

  it("dice en llano que aún no hay cifras de Cadenza y enseña las de los corpus", async () => {
    const data = payload([
      group("cadenza", UNPUBLISHED),
      group("pruebas", UNPUBLISHED),
      group("primus", { sessions: 1877 }),
      group("camera-primus", { sessions: 1877 }),
    ]);
    render(<HomrErrors load={loader(data)} />);

    expect(await screen.findByText("Aún no hay cifras de Cadenza")).toBeInTheDocument();
    expect(
      screen.getByText(/Mientras, estas son las de PrIMuS y Camera-PrIMuS\./),
    ).toBeInTheDocument();
    const groups = screen.getByRole("navigation", { name: "Qué cifras se ven" });
    expect(
      within(groups)
        .getAllByRole("button")
        .map((b) => b.textContent),
    ).toEqual(["PrIMuS", "Camera-PrIMuS"]);
    expect(screen.getByText("1877 íncipits")).toBeInTheDocument();
  });

  it("cambia de grupo con el conmutador", async () => {
    const data = payload([
      group("cadenza"),
      group("primus", {
        sessions: 1877,
        stats: values({ scores: 1877, ops: { SetPitch: 500 }, reordered: 66 }),
      }),
    ]);
    render(<HomrErrors load={loader(data)} />);
    await screen.findByText(/calculadas el/);

    await userEvent.click(screen.getByRole("button", { name: "PrIMuS" }));

    expect(screen.getByRole("button", { name: "PrIMuS" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/tenían mal la altura/)).toBeInTheDocument();
    expect(screen.getByText(/66 notas de acordes/)).toBeInTheDocument();
  });

  it("se actualiza sola y, si una petición falla, se queda con las últimas cifras", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const load = loader(
      payload([group("primus")], "2026-11-19T12:00:00Z"),
      new Error("caída"),
      payload([group("primus")], "2026-11-19T12:10:00Z"),
    );
    render(<HomrErrors load={load} refreshMs={1000} />);
    expect(await screen.findByText(/calculadas el/)).toBeInTheDocument();
    const when = () => screen.getByText(/calculadas el/).textContent;
    const first = when();

    await act(async () => {
      vi.advanceTimersByTime(1000);
      await Promise.resolve();
    });
    expect(when()).toBe(first);

    await act(async () => {
      vi.advanceTimersByTime(1000);
      await Promise.resolve();
    });
    expect(load).toHaveBeenCalledTimes(3);
    expect(when()).not.toBe(first);
  });

  it("avisa si no puede cargar las cifras", async () => {
    render(<HomrErrors load={loader(new Error("caída"))} />);

    expect(await screen.findByText(/Ahora no se pueden cargar las cifras/)).toBeInTheDocument();
  });

  it("no enseña ninguna imagen, fracción ni «ver más», y pagina las listas largas", async () => {
    const many = Array.from({ length: 10 }, (_, i) =>
      rate(`clef:X${String(i)}`, `clave ${String(i)}`, 100 + i, 10),
    );
    const { container } = render(
      <HomrErrors
        load={loader(payload([group("primus", { stats: values({ by_clef: many }) })]))}
      />,
    );
    await screen.findByText(/calculadas el/);

    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).not.toMatch(/\b\d+\/\d+\b/);
    expect(container.textContent).not.toMatch(/ver más|pincha/i);

    const pager = screen.getByRole("navigation", { name: "Páginas de «Clave»" });
    const page = (n: number) =>
      within(pager).getByRole("button", { name: `Página ${String(n)} de 2` });
    expect(page(1)).toHaveAttribute("aria-current", "page");
    expect(screen.queryByText("clave 9")).not.toBeInTheDocument();
    await userEvent.click(within(pager).getByRole("button", { name: "Siguiente" }));
    expect(page(2)).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("clave 9")).toBeInTheDocument();
    const next = within(pager).getByRole("button", { name: "Siguiente" });
    expect(next).toHaveAttribute("aria-disabled", "true");
    expect(next).toHaveFocus();
    await userEvent.click(next);
    expect(page(2)).toHaveAttribute("aria-current", "page");
    await userEvent.click(page(1));
    expect(page(1)).toHaveAttribute("aria-current", "page");
  });

  it("vuelve a la primera página de cada lista al cambiar de grupo", async () => {
    const many = Array.from({ length: 10 }, (_, i) =>
      rate(`clef:X${String(i)}`, `clave ${String(i)}`, 100 + i, 10),
    );
    const stats = values({ by_clef: many });
    render(
      <HomrErrors
        load={loader(payload([group("primus", { stats }), group("camera-primus", { stats })]))}
      />,
    );
    await screen.findByText(/Calculadas una vez/);
    const pagerOf = () => screen.getByRole("navigation", { name: "Páginas de «Clave»" });

    const current = () =>
      within(pagerOf())
        .getAllByRole("button")
        .find((b) => b.getAttribute("aria-current"));
    await userEvent.click(within(pagerOf()).getByRole("button", { name: "Siguiente" }));
    expect(current()).toHaveAccessibleName("Página 2 de 2");
    await userEvent.click(screen.getByRole("button", { name: "Camera-PrIMuS" }));

    expect(current()).toHaveAccessibleName("Página 1 de 2");
  });

  it("al pasar sobre una cifra, un rótulo dice lo que es", async () => {
    const { container } = render(<HomrErrors load={loader(payload([group("primus")]))} />);
    await screen.findByText(/Calculadas una vez/);

    const bar = screen.getByText("Altura equivocada");
    await userEvent.hover(bar);

    expect(container.querySelector(".homr__tip")).toHaveTextContent(
      "Altura equivocada · 60 correcciones, 6 por cada 100 notas",
    );
    await userEvent.unhover(bar);
    await userEvent.hover(screen.getByRole("heading", { level: 1 }));
    expect(container.querySelector(".homr__tip")).toBeNull();
  });

  it("no pide nada con la pestaña oculta y, al volver tras el plazo, pide en el momento", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] });
    let visibility: DocumentVisibilityState = "visible";
    vi.spyOn(document, "visibilityState", "get").mockImplementation(() => visibility);
    const load = loader(payload([group("primus")]));
    render(<HomrErrors load={load} refreshMs={1000} />);
    await screen.findByText(/Calculadas una vez/);
    expect(load).toHaveBeenCalledTimes(1);

    visibility = "hidden";
    await act(async () => {
      vi.advanceTimersByTime(3000);
      await Promise.resolve();
    });
    expect(load).toHaveBeenCalledTimes(1);

    visibility = "visible";
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
      await Promise.resolve();
    });
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("no hace caso de una respuesta que llega después de cerrar la página", async () => {
    let resolve: (data: HomrErrorStatsRead) => void = () => undefined;
    const load = vi.fn<StatsLoader>(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    const { unmount } = render(<HomrErrors load={load} />);
    const signal = load.mock.calls[0]?.[0];
    unmount();

    expect(signal?.aborted).toBe(true);
    await act(async () => {
      resolve(payload([group("primus")]));
      await Promise.resolve();
    });
    expect(screen.queryByText(/calculadas/)).toBeNull();
  });
});

describe("la vista de los errores de HOMR", () => {
  function stubStats() {
    const fetchMock = vi.fn<typeof fetch>(() =>
      Promise.resolve(
        new Response(JSON.stringify(payload([group("cadenza"), group("primus")])), {
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const urlOf = (input: RequestInfo | URL) =>
      typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const statsCalls = () =>
      fetchMock.mock.calls.filter(([input]) => urlOf(input).endsWith("/stats/homr-errors"));
    return statsCalls;
  }

  it("es una página pública que pide las cifras sin token, también con la sesión abierta", async () => {
    const statsCalls = stubStats();
    const before = useAuthStore.getState();
    useAuthStore.setState({ status: "authenticated", token: "token-de-prueba" });
    onTestFinished(() => {
      useAuthStore.setState(before, true);
    });
    render(
      <RouterProvider
        router={createMemoryRouter(routes, { initialEntries: ["/errores-de-homr"] })}
      />,
    );

    expect(await screen.findByText(/calculadas el/)).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 1, name: "Errores de HOMR, en vivo" }),
    ).toBeInTheDocument();
    expect(document.title).toBe("Errores de HOMR · Cadenza");
    expect(statsCalls()).toHaveLength(1);
    expect(new Headers(statsCalls()[0]?.[1]?.headers).has("Authorization")).toBe(false);
  });

  it("no está en la portada: la portada la enlaza desde la cabecera", async () => {
    const statsCalls = stubStats();
    const router = createMemoryRouter(routes, { initialEntries: ["/"] });
    render(<RouterProvider router={router} />);
    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.queryByRole("main", { name: "Errores de HOMR, en vivo" })).toBeNull();
    expect(statsCalls()).toHaveLength(0);
    const link = screen.getByRole("link", { name: "Errores de HOMR" });
    expect(link).toHaveAttribute("href", "/errores-de-homr");

    await userEvent.click(link);
    expect(router.state.location.pathname).toBe("/errores-de-homr");
    expect(await screen.findByText(/calculadas el/)).toBeInTheDocument();
  });
});

describe("los ejemplos de los corpus", () => {
  it("enseñan de entrada los de lo primero que dicen los datos, con su compás dibujado", async () => {
    const stats = withExamples(values());
    const { container } = render(
      <HomrErrors load={loader(payload([group("primus", { stats })]))} />,
    );
    await screen.findByText(/Calculadas una vez/);

    const panel = screen.getByRole("region", { name: "Figura equivocada" });
    expect(within(panel).getByText(/Calvo-Zaragoza y Rizo, 2018/)).toBeInTheDocument();
    expect(within(panel).getByText(/Cada compás lo graba Cadenza desde los datos/)).toBeVisible();
    expect(
      within(panel).getAllByRole("img", { name: /^Compás \d+: lo que leyó HOMR/ }),
    ).toHaveLength(4);
    expect(
      within(panel).getByText("000100130-1_1_1 · compás 1 · pentagrama 0-0"),
    ).toBeInTheDocument();
    // La nota del ejemplo va en violeta: su grupo, marcado en cada pentagrama.
    expect(panel.querySelectorAll(".homr__drawn-focus").length).toBeGreaterThan(0);
    // Sin historial que diga que su partitura tiene imagen, solo el compás dibujado (SVG).
    expect(container.querySelector("img")).toBeNull();
  });

  it("pagina los ejemplos y cambia al elegir otra cifra", async () => {
    const stats = withExamples(values());
    render(<HomrErrors load={loader(payload([group("primus", { stats })]))} />);
    await screen.findByText(/Calculadas una vez/);
    const pager = screen.getByRole("navigation", { name: "Páginas de los ejemplos" });

    await userEvent.click(within(pager).getByRole("button", { name: "Página 2 de 2" }));
    expect(screen.getByText("000100135-1_1_1 · compás 6 · pentagrama 0-0")).toBeInTheDocument();

    const bar = screen.getByRole("button", { name: /^Altura equivocada/ });
    await userEvent.click(bar);
    expect(bar).toHaveAttribute("aria-current", "true");
    const panel = screen.getByRole("region", { name: "Altura equivocada" });
    expect(
      within(panel).getByText("000100200-1_1_1 · compás 3 · pentagrama 0-0"),
    ).toBeInTheDocument();
    expect(within(panel).queryByRole("navigation")).toBeNull();
    expect(within(panel).getByText("Bb4 negra")).toHaveClass("homr__tok--del");
  });

  it("no salen en los grupos de Cadenza, que solo enseñan cifras de conjunto", async () => {
    // Aunque llegaran (la API ya los quita), un grupo de Cadenza no los enseña.
    const stats = withExamples(values());
    render(<HomrErrors load={loader(payload([group("cadenza", { stats })]))} />);
    await screen.findByText(/calculadas el/);

    expect(screen.queryByRole("region", { name: /equivocada/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Altura equivocada/ })).toBeNull();
    expect(screen.getByText(/solo se enseñan de los corpus públicos/)).toBeInTheDocument();
  });
});

describe("volver a una cifra", () => {
  it("vuelve a la primera página de sus ejemplos", async () => {
    const stats = withExamples(values());
    render(<HomrErrors load={loader(payload([group("primus", { stats })]))} />);
    await screen.findByText(/Calculadas una vez/);
    const pager = () => screen.getByRole("navigation", { name: "Páginas de los ejemplos" });

    await userEvent.click(within(pager()).getByRole("button", { name: "Página 2 de 2" }));
    await userEvent.click(screen.getByRole("button", { name: /^Altura equivocada/ }));
    await userEvent.click(screen.getByRole("button", { name: /^Figura equivocada/ }));

    expect(within(pager()).getByRole("button", { name: "Página 1 de 2" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    // Cada casilla de la matriz dice qué es, no solo su número.
    expect(screen.getByRole("button", { name: "Leída corchea, correcta negra: 40" })).toBeVisible();
  });
});

describe("el historial de transcripciones de un corpus", () => {
  const corpus = () => payload([group("primus", { stats: withHistory(withExamples(values())) })]);
  const detailLoader = () =>
    vi.fn<ScoreLoader>((_group, score) => Promise.resolve(scoreDetail(score)));
  const table = () => screen.getByRole("region", { name: "Tabla del historial" });
  const rowNames = () =>
    within(table())
      .getAllByRole("rowheader")
      .map((cell) => cell.textContent);

  it("lista sus partituras con buscador, orden y páginas", async () => {
    render(<HomrErrors load={loader(corpus())} loadScore={detailLoader()} />);
    await screen.findByText(/Calculadas una vez/);

    expect(screen.getByRole("heading", { name: "Historial de transcripciones" })).toBeVisible();
    expect(screen.getByText("1–25 de 30 transcripciones")).toBeInTheDocument();
    // Más correcciones por nota primero, pero la de 4 notas no va delante aunque tenga un 100 %.
    expect(rowNames()[0]).toBe("00010104-1_1_1");
    expect(rowNames()).not.toContain("00010103-1_1_1");

    const pager = screen.getByRole("navigation", { name: "Páginas del historial" });
    await userEvent.click(within(pager).getByRole("button", { name: "Página 2 de 2" }));
    expect(rowNames()).toHaveLength(5);
    expect(rowNames()).toContain("00010103-1_1_1");

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Orden" }), "clean");
    expect(rowNames()[0]).toBe("00010107-1_1_1");
    expect(within(table()).getByText("ninguna")).toHaveClass("homr__clean");

    const search = screen.getByRole("searchbox", { name: "Buscar" });
    await userEvent.type(search, "0010112");
    expect(rowNames()).toEqual(["00010112-1_1_1"]);
    expect(screen.getByText("1 transcripción de 30")).toBeInTheDocument();
    await userEvent.clear(search);
    await userEvent.type(search, "zzz");
    expect(screen.getByText("Ninguna transcripción coincide con «zzz».")).toBeInTheDocument();
  });

  it("al elegir una partitura pide sus correcciones y las enseña", async () => {
    const loadScore = detailLoader();
    render(<HomrErrors load={loader(corpus())} loadScore={loadScore} />);
    await screen.findByText(/Calculadas una vez/);

    const pick = screen.getByRole("button", { name: "00010104-1_1_1" });
    await userEvent.click(pick);

    expect(loadScore).toHaveBeenCalledWith("primus", "primus:00010104-1_1_1", expect.anything());
    expect(pick).toHaveAttribute("aria-current", "true");
    const panel = screen.getByRole("region", { name: "00010104-1_1_1" });
    expect(
      await within(panel).findByText("00010104-1_1_1 · compás 3 · pentagrama 0-0"),
    ).toBeVisible();
    expect(within(panel).getByText("Historial de transcripciones")).toBeInTheDocument();
    expect(panel.querySelectorAll(".homr__drawn-focus").length).toBeGreaterThan(0);
  });

  it("una partitura sin correcciones lo dice sin pedir nada", async () => {
    const loadScore = detailLoader();
    render(<HomrErrors load={loader(corpus())} loadScore={loadScore} />);
    await screen.findByText(/Calculadas una vez/);

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Orden" }), "clean");
    await userEvent.click(screen.getByRole("button", { name: "00010107-1_1_1" }));

    const panel = screen.getByRole("region", { name: "00010107-1_1_1" });
    expect(within(panel).getByText("HOMR la leyó sin ninguna corrección.")).toBeVisible();
    expect(loadScore).not.toHaveBeenCalled();
  });

  it("si no se pueden cargar sus correcciones, deja volver a intentarlo", async () => {
    const loadScore = vi
      .fn<ScoreLoader>()
      .mockRejectedValueOnce(new Error("caída"))
      .mockImplementation((_group, score) => Promise.resolve(scoreDetail(score)));
    render(<HomrErrors load={loader(corpus())} loadScore={loadScore} />);
    await screen.findByText(/Calculadas una vez/);

    await userEvent.click(screen.getByRole("button", { name: "00010104-1_1_1" }));
    await userEvent.click(await screen.findByRole("button", { name: "Volver a intentarlo" }));

    // El botón desaparece: el foco queda en el título del panel, no en la página.
    expect(screen.getByRole("heading", { name: "00010104-1_1_1" })).toHaveFocus();
    expect(await screen.findByText("00010104-1_1_1 · compás 3 · pentagrama 0-0")).toBeVisible();
    expect(loadScore).toHaveBeenCalledTimes(2);
  });

  it("una partitura que ya no está lo dice, sin un reintento que no serviría", async () => {
    const loadScore = vi.fn<ScoreLoader>().mockRejectedValue(new ApiError("not-found", 404));
    render(<HomrErrors load={loader(corpus())} loadScore={loadScore} />);
    await screen.findByText(/Calculadas una vez/);

    await userEvent.click(screen.getByRole("button", { name: "00010104-1_1_1" }));

    expect(await screen.findByText(/ya no está en el historial/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Volver a intentarlo" })).toBeNull();
  });

  it("toda la fila elige la partitura", async () => {
    const loadScore = vi.fn<ScoreLoader>((_group, score) => Promise.resolve(scoreDetail(score)));
    render(<HomrErrors load={loader(corpus())} loadScore={loadScore} />);
    await screen.findByText(/Calculadas una vez/);

    const row = screen.getByRole("row", { name: /00010104-1_1_1/ });
    await userEvent.click(within(row).getAllByRole("cell")[0] ?? row);

    expect(within(row).getByRole("button")).toHaveAttribute("aria-current", "true");
    expect(loadScore).toHaveBeenCalledTimes(1);
  });

  it("los grupos de Cadenza no tienen historial", async () => {
    // Aunque llegara (la API ya lo quita), un grupo de Cadenza no enseña ninguna transcripción.
    const stats = withHistory(withExamples(values()));
    render(<HomrErrors load={loader(payload([group("cadenza", { stats })]))} />);
    await screen.findByText(/calculadas el/);

    expect(screen.queryByRole("heading", { name: "Historial de transcripciones" })).toBeNull();
    expect(screen.queryByText("00010104-1_1_1")).toBeNull();
    expect(screen.getByText(/nada de una transcripción concreta/)).toBeInTheDocument();
  });
});

describe("la imagen del corpus de cada ejemplo", () => {
  it("sale encima del compás dibujado si su partitura la tiene, como en el informe", async () => {
    const base = withHistory(withExamples(values()));
    // La partitura del primer ejemplo de «Figura equivocada» tiene imagen; las demás, no.
    const history = (base.history ?? []).map((row, index) =>
      index === 0 ? { ...row, label: "000100130-1_1_1", image: true } : row,
    );
    const stats = { ...base, history };
    render(<HomrErrors load={loader(payload([group("primus", { stats })]))} />);
    await screen.findByText(/Calculadas una vez/);

    const panel = screen.getByRole("region", { name: "Figura equivocada" });
    expect(within(panel).getAllByRole("img", { name: /^El íncipit/ })).toHaveLength(1);
    const image = within(panel).getByRole("img", { name: "El íncipit 000100130-1_1_1 en PrIMuS" });
    expect(image.getAttribute("src")).toMatch(
      /\/stats\/homr-errors\/primus\/scores\/primus%3A00010100-1_1_1\/image$/,
    );
    expect(within(panel).getByText(/Arriba, la imagen del íncipit en PrIMuS/)).toBeVisible();
  });

  it("sale en cada corrección de una partitura del historial que la tiene", async () => {
    const loadScore = vi.fn<ScoreLoader>((_group, score) =>
      Promise.resolve({ ...scoreDetail(score), image: true }),
    );
    const stats = withHistory(withExamples(values()));
    render(
      <HomrErrors load={loader(payload([group("primus", { stats })]))} loadScore={loadScore} />,
    );
    await screen.findByText(/Calculadas una vez/);

    await userEvent.click(screen.getByRole("button", { name: "00010104-1_1_1" }));

    const panel = screen.getByRole("region", { name: "00010104-1_1_1" });
    const image = await within(panel).findByRole("img", {
      name: "El íncipit 00010104-1_1_1 en PrIMuS",
    });
    expect(image.getAttribute("src")).toMatch(/scores\/primus%3A00010104-1_1_1\/image$/);
  });
});
