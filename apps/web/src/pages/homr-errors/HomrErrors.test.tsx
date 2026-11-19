import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { routes } from "../../router";
import type { HomrErrorStatsRead } from "../../types";
import { group, payload, rate, UNPUBLISHED, values } from "./fixtures";
import { HomrErrors, type StatsLoader } from "./HomrErrors";

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

describe("los errores de HOMR en la portada", () => {
  it("enseña lo que dicen los datos de Cadenza y cuándo se calcularon", async () => {
    render(<HomrErrors load={loader(payload([group("cadenza"), group("primus")]))} />);

    expect(await screen.findByText(/Calculadas el 19 de noviembre/)).toBeInTheDocument();
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
    await screen.findByText(/Calculadas el/);

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
    const groups = screen.getByRole("group", { name: "Qué cifras se ven" });
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
    await screen.findByText(/Calculadas el/);

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
    expect(await screen.findByText(/Calculadas el 19 de noviembre/)).toBeInTheDocument();
    const first = screen.getByText(/Calculadas el/).textContent;

    await act(async () => {
      vi.advanceTimersByTime(1000);
      await Promise.resolve();
    });
    expect(screen.getByText(/Calculadas el/).textContent).toBe(first);

    await act(async () => {
      vi.advanceTimersByTime(1000);
      await Promise.resolve();
    });
    expect(load).toHaveBeenCalledTimes(3);
    expect(screen.getByText(/Calculadas el/).textContent).not.toBe(first);
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
    await screen.findByText(/Calculadas el/);

    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).not.toMatch(/\b\d+\/\d+\b/);
    expect(container.textContent).not.toMatch(/ver más|pincha/i);

    const pager = screen.getByRole("navigation", { name: "Páginas de «Clave»" });
    expect(within(pager).getByText("Página 1 de 2")).toBeInTheDocument();
    expect(screen.queryByText("clave 9")).not.toBeInTheDocument();
    await userEvent.click(within(pager).getByRole("button", { name: "Siguiente" }));
    expect(within(pager).getByText("Página 2 de 2")).toBeInTheDocument();
    expect(screen.getByText("clave 9")).toBeInTheDocument();
    expect(within(pager).getByRole("button", { name: "Siguiente" })).toBeDisabled();
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

  it("es una página pública que pide las cifras sin cuenta", async () => {
    const statsCalls = stubStats();
    render(
      <RouterProvider
        router={createMemoryRouter(routes, { initialEntries: ["/errores-de-homr"] })}
      />,
    );

    expect(await screen.findByText(/Calculadas el/)).toBeInTheDocument();
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

    expect(screen.queryByRole("main", { name: "Errores de HOMR, en vivo" })).toBeNull();
    expect(statsCalls()).toHaveLength(0);
    const link = screen.getByRole("link", { name: "Errores de HOMR" });
    expect(link).toHaveAttribute("href", "/errores-de-homr");

    await userEvent.click(link);
    expect(router.state.location.pathname).toBe("/errores-de-homr");
    expect(await screen.findByText(/Calculadas el/)).toBeInTheDocument();
  });
});
