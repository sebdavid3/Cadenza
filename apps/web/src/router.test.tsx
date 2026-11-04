import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it } from "vitest";
import { routes } from "./router";

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(<RouterProvider router={router} />);
  return router;
}

describe("enrutado", () => {
  it("sirve la página pública en /", () => {
    renderAt("/");

    expect(screen.getByRole("heading", { level: 1, name: /de píxel a nota/i })).toBeVisible();
    expect(document.title).toBe("Cadenza");
  });

  it("muestra una 404 propia en una ruta desconocida, con vuelta al inicio", () => {
    renderAt("/no-existe");

    expect(screen.getByRole("heading", { level: 1, name: /esta página no existe/i })).toBeVisible();
    expect(screen.getByRole("link", { name: /volver al inicio/i })).toHaveAttribute("href", "/");
    expect(document.title).toMatch(/no encontrada/i);
  });
});
