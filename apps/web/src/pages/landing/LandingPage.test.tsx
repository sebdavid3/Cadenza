import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it } from "vitest";
import { routes } from "../../router";

function renderLanding() {
  const router = createMemoryRouter(routes, { initialEntries: ["/"] });
  render(<RouterProvider router={router} />);
  return router;
}

describe("landing", () => {
  it("explica qué es Cadenza en el titular y la entradilla", () => {
    renderLanding();

    expect(screen.getByRole("heading", { level: 1, name: /de píxel a nota/i })).toBeVisible();
    expect(screen.getByText(/imagen de una partitura impresa en notación editable/i)).toBeVisible();
  });

  it("lleva a la vista de acceso con «Entrar»", async () => {
    const router = renderLanding();
    const hero = screen.getByRole("region", { name: /de píxel a nota/i });

    await userEvent.click(within(hero).getByRole("link", { name: /entrar/i }));

    expect(router.state.location.pathname).toBe("/entrar");
  });

  it("no ofrece registro ni recuperación de contraseña y explica quién crea las cuentas", () => {
    renderLanding();

    expect(screen.queryByText(/regístrate|crear cuenta|olvidaste/i)).not.toBeInTheDocument();
    expect(screen.getAllByText(/las cuentas las crea/i).length).toBeGreaterThan(0);
  });

  it("enlaza al repositorio público", () => {
    renderLanding();

    const links = screen.getAllByRole("link", { name: /código/i });
    expect(links.length).toBeGreaterThan(0);
    for (const link of links) {
      expect(link).toHaveAttribute("href", "https://github.com/sebdavid3/Cadenza");
    }
  });

  it("dice el alcance con honestidad y sin cifras de rendimiento", () => {
    renderLanding();

    const scope = screen.getByRole("region", { name: /qué lee hoy/i });
    expect(within(scope).getByText(/manuscritos/i)).toBeVisible();
    expect(within(scope).getByText(/polifonía densa/i)).toBeVisible();
    expect(document.body.textContent).not.toMatch(/\d+\s?%|\d+[.,]\d+\s?s\b/);
  });

  it("presenta la demostración como ilustración sintética", () => {
    renderLanding();

    const demo = screen.getByRole("region", { name: /demostración/i });
    expect(within(demo).getByText(/incipit sintético · ilustración/i)).toBeVisible();
  });

  it("alterna entre la imagen y la notación en la demostración", async () => {
    renderLanding();
    const demo = screen.getByRole("region", { name: /demostración/i });
    const image = within(demo).getByRole("button", { name: "Imagen" });
    const notation = within(demo).getByRole("button", { name: "Notación" });

    await userEvent.click(image);

    expect(image).toHaveAttribute("aria-pressed", "true");
    expect(notation).toHaveAttribute("aria-pressed", "false");
  });

  it("no enlaza a ninguna vista de edición", () => {
    renderLanding();

    for (const link of screen.getAllByRole("link")) {
      expect(link.getAttribute("href")).not.toMatch(/sesion|session|editor|correg/i);
    }
  });
});
