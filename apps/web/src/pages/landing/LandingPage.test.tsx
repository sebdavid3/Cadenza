import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { routes } from "../../router";

function renderLanding() {
  const router = createMemoryRouter(routes, { initialEntries: ["/"] });
  render(<RouterProvider router={router} />);
  return router;
}

function demo() {
  const region = screen.getByRole("region", { name: /demostración/i });
  const section = region.closest("section");
  if (!section) throw new Error("falta la sección de la demostración");
  return { region, section };
}

/** Animaciones simuladas: se pueden terminar a mano. */
function mockMotion({ reduce }: { reduce: boolean }) {
  const animations: { finish: () => void; cancel: ReturnType<typeof vi.fn> }[] = [];
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: reduce && query.includes("reduce"),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
  let observerCallback: IntersectionObserverCallback | null = null;
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(callback: IntersectionObserverCallback) {
        observerCallback = callback;
      }
      observe = vi.fn();
      disconnect = vi.fn();
    },
  );
  const animate = vi.fn(function (this: HTMLElement) {
    const animation = {
      onfinish: null as (() => void) | null,
      cancel: vi.fn(),
      finish() {
        this.onfinish?.();
      },
    };
    animations.push(animation);
    return animation as unknown as Animation;
  });
  Object.defineProperty(HTMLElement.prototype, "animate", {
    value: animate,
    configurable: true,
    writable: true,
  });
  return {
    animate,
    animations,
    enterViewport: () => {
      act(() => {
        observerCallback?.(
          [{ isIntersecting: true } as IntersectionObserverEntry],
          {} as IntersectionObserver,
        );
      });
    },
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  Reflect.deleteProperty(HTMLElement.prototype, "animate");
});

describe("landing", () => {
  it("explica qué es Cadenza en el titular y la entradilla", () => {
    renderLanding();

    expect(screen.getByRole("heading", { level: 1, name: /de píxel a nota/i })).toBeVisible();
    expect(screen.getByText(/imagen de una partitura impresa en notación editable/i)).toBeVisible();
  });

  it("enlaza a /entrar desde el titular", async () => {
    const router = renderLanding();
    const hero = screen.getByRole("region", { name: /de píxel a nota/i });

    await userEvent.click(within(hero).getByRole("link", { name: /entrar/i }));

    expect(router.state.location.pathname).toBe("/entrar");
  });

  it("sin registro abierto en el build, explica quién crea las cuentas y no lo enlaza", () => {
    vi.stubEnv("VITE_REGISTRATION_ENABLED", "");
    renderLanding();

    expect(screen.queryByRole("link", { name: /créala|crear una cuenta/i })).toBeNull();
    expect(screen.getAllByText(/las cuentas las crea/i).length).toBeGreaterThan(0);
  });

  it("con registro abierto, lo enlaza, dice que se entra en el momento y no ofrece recuperación", () => {
    vi.stubEnv("VITE_REGISTRATION_ENABLED", "true");
    renderLanding();

    const links = screen.getAllByRole("link", { name: /créala|crear una cuenta/i });
    expect(links.length).toBeGreaterThan(0);
    for (const link of links) expect(link).toHaveAttribute("href", "/registro");
    expect(screen.getAllByText(/en el momento/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/pendiente|activarla/i)).toBeNull();
    expect(screen.queryByText(/olvidaste/i)).not.toBeInTheDocument();
  });

  it("enlaza al repositorio público", () => {
    renderLanding();

    const links = screen.getAllByRole("link", { name: /código/i });
    expect(links.length).toBeGreaterThan(0);
    for (const link of links) {
      expect(link).toHaveAttribute("href", "https://github.com/sebdavid3/Cadenza");
    }
  });

  it("separa lo probado de lo no evaluado, sin cifras de rendimiento", () => {
    renderLanding();

    const tested = screen.getByRole("region", { name: "Probado" });
    const untested = screen.getByRole("region", { name: "Sin evaluar" });
    const items = (region: HTMLElement) =>
      within(region)
        .getAllByRole("listitem")
        .map((item) => item.textContent);
    expect(items(tested)).toEqual(
      expect.arrayContaining(["Incipits y fragmentos impresos", "Una voz en un pentagrama"]),
    );
    expect(items(untested)).toEqual(
      expect.arrayContaining(["Manuscritos", "Más de una voz o varios pentagramas"]),
    );
    expect(items(tested).join(" ")).not.toMatch(/manuscrit|polifon|fotograf/i);
    expect(screen.getByText(/las reglas no lo detectan todo/i)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\d+\s?%|\d+[.,]\d+\s?s\b/);
  });

  it("presenta la demostración y las figuras de los pasos como ilustraciones", () => {
    renderLanding();

    expect(within(demo().region).getByText(/incipit sintético · ilustración/i)).toBeVisible();
    expect(screen.getByText(/las figuras son ilustraciones/i)).toBeVisible();
  });

  it("asoma los cuatro pasos en un índice que lleva a cada uno", () => {
    renderLanding();

    const index = screen.getByRole("navigation", { name: "Pasos" });
    const links = within(index).getAllByRole("link");
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "#paso-1",
      "#paso-2",
      "#paso-3",
      "#paso-4",
    ]);
    for (const n of [1, 2, 3, 4])
      expect(document.getElementById(`paso-${String(n)}`)).not.toBeNull();
    expect(screen.getAllByRole("list").length).toBeGreaterThan(1);
  });

  it("no enlaza a ninguna vista de edición", () => {
    renderLanding();

    for (const link of screen.getAllByRole("link")) {
      expect(link.getAttribute("href")).not.toMatch(/sesion|session|editor|correg/i);
    }
  });
});

describe("demostración", () => {
  it("alterna entre la imagen y la notación y vuelve a leer al volver a la notación", async () => {
    const motion = mockMotion({ reduce: false });
    renderLanding();
    const { region, section } = demo();
    motion.enterViewport();
    act(() => {
      for (const animation of motion.animations) animation.finish();
    });
    const image = within(region).getByRole("button", { name: "Imagen" });
    const notation = within(region).getByRole("button", { name: "Notación" });

    await userEvent.click(image);
    expect(section).toHaveAttribute("data-view", "image");
    expect(image).toHaveAttribute("aria-pressed", "true");

    const before = motion.animate.mock.calls.length;
    await userEvent.click(notation);
    expect(section).toHaveAttribute("data-view", "notation");
    expect(section).toHaveAttribute("data-phase", "reading");
    expect(motion.animate.mock.calls.length).toBe(before + 2);
  });

  it("espera a entrar en pantalla, lee y termina con el compás señalado", () => {
    const motion = mockMotion({ reduce: false });
    renderLanding();
    const { section } = demo();

    expect(section).toHaveAttribute("data-phase", "waiting");
    motion.enterViewport();
    expect(section).toHaveAttribute("data-phase", "reading");

    act(() => {
      for (const animation of motion.animations) animation.finish();
    });
    expect(section).toHaveAttribute("data-phase", "done");
  });

  it("una lectura reemplazada no cierra la siguiente", async () => {
    const motion = mockMotion({ reduce: false });
    renderLanding();
    const { region, section } = demo();
    motion.enterViewport();
    const first = [...motion.animations];

    await userEvent.click(within(region).getByRole("button", { name: "Imagen" }));
    await userEvent.click(within(region).getByRole("button", { name: "Notación" }));
    act(() => {
      for (const animation of first) animation.finish();
    });

    expect(first.every((animation) => animation.cancel.mock.calls.length > 0)).toBe(true);
    expect(section).toHaveAttribute("data-phase", "reading");
  });

  it("con movimiento reducido muestra el estado final sin animar", () => {
    const motion = mockMotion({ reduce: true });
    renderLanding();

    expect(demo().section).toHaveAttribute("data-phase", "done");
    expect(motion.animate).not.toHaveBeenCalled();
  });
});
