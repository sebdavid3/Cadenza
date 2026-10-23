import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { routes } from "../../router";
import { ANA, jsonResponse, mockApi, resetAuth, signInAs } from "../../test/auth-helpers";
import type { UserRead } from "../../types";

const INV: UserRead = {
  ...ANA,
  id: "inv-0001",
  username: "inv",
  role: "investigador",
  self_registered: false,
};
const PENDING: UserRead = {
  id: "u-pend",
  username: "nuevo",
  role: "transcriptor",
  active: false,
  self_registered: true,
  created_at: "2026-10-23T10:00:00",
};
const STUDY: UserRead = {
  id: "u-est",
  username: "participante_07",
  role: "transcriptor",
  active: true,
  self_registered: false,
  created_at: "2026-10-20T10:00:00",
};

function renderAt(user: UserRead, path = "/cuentas") {
  signInAs(user);
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(<RouterProvider router={router} />);
  return router;
}

beforeEach(() => {
  resetAuth();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("cuentas", () => {
  it("lista primero las pendientes y distingue las del registro de las del estudio", async () => {
    mockApi({ "GET /users": () => jsonResponse([INV, STUDY, PENDING]) });
    renderAt(INV);

    const list = await screen.findByRole("list");
    const items = within(list).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("nuevo");
    expect(items[0]).toHaveTextContent(/registro/i);
    expect(items[0]).toHaveTextContent("Pendiente");
    expect(screen.getByText(/1 pendiente de activar/i)).toBeVisible();
    const study = items.find((item) => item.textContent.includes("participante_07"));
    expect(study).toHaveTextContent(/creada por un investigador/i);
    // Nadie puede desactivar su propia cuenta desde aquí.
    const own = items.find(
      (item) => item.querySelector(".accounts__name")?.textContent === INV.username,
    );
    if (!own) throw new Error("falta la fila de la cuenta propia");
    expect(within(own).queryByRole("button")).toBeNull();
    expect(own).toHaveTextContent(/tu cuenta/i);
  });

  it("activa una cuenta pendiente con PATCH /users/{id}", async () => {
    const { calls } = mockApi({
      "GET /users": () => jsonResponse([INV, PENDING]),
      "PATCH /users/u-pend": () => jsonResponse({ ...PENDING, active: true }),
    });
    renderAt(INV);

    // El nombre accesible se calcula despacio en jsdom: primero se espera al listado.
    await screen.findByRole("list");
    await userEvent.click(screen.getByRole("button", { name: /^activar la cuenta nuevo/i }));

    expect(await screen.findByText(/ninguna pendiente/i)).toBeVisible();
    expect(screen.getByRole("button", { name: /desactivar la cuenta nuevo/i })).toBeVisible();
    const call = calls.find((entry) => entry.key === "PATCH /users/u-pend");
    expect(JSON.parse(call?.init?.body as string)).toEqual({ active: true });
  });

  it("no la ve un transcriptor", async () => {
    mockApi({ "GET /sessions": () => jsonResponse([]) });
    renderAt(ANA);

    expect(await screen.findByRole("heading", { name: /esta página no existe/i })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Cuentas" })).toBeNull();
  });
});
