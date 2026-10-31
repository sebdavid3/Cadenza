import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { routes } from "../../router";
import { ANA, deferred, jsonResponse, mockApi, resetAuth, signInAs } from "../../test/auth-helpers";
import type { UserRead } from "../../types";

const INV: UserRead = {
  ...ANA,
  id: "inv-0001",
  username: "inv",
  role: "investigador",
  self_registered: false,
};
// Del registro: entra en el momento, sin activación (ADR-0025).
const REGISTERED: UserRead = {
  id: "u-reg",
  username: "nuevo",
  role: "transcriptor",
  active: true,
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

function names() {
  return within(screen.getByRole("list"))
    .getAllByRole("listitem")
    .map((item) => item.querySelector(".accounts__name")?.textContent);
}

beforeEach(() => {
  resetAuth();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("cuentas", () => {
  it("con el registro abierto en el build, dice que cualquiera puede crear una cuenta", async () => {
    vi.stubEnv("VITE_REGISTRATION_ENABLED", "true");
    mockApi({ "GET /users": () => jsonResponse([STUDY, INV, REGISTERED]) });
    renderAt(INV);

    expect(await screen.findByText(/cualquiera puede crear una cuenta/i)).toBeVisible();
  });

  it("con el registro cerrado, dice que está cerrado y que las del registro siguen entrando (#248)", async () => {
    vi.stubEnv("VITE_REGISTRATION_ENABLED", "");
    mockApi({ "GET /users": () => jsonResponse([STUDY, INV, REGISTERED]) });
    renderAt(INV);

    expect(await screen.findByText(/el registro está cerrado/i)).toBeVisible();
    expect(screen.getByText(/desactívalas/i)).toBeVisible();
    expect(screen.queryByText(/cualquiera puede crear una cuenta/i)).toBeNull();
  });

  it("lista por fecha de alta y distingue las del registro de las del estudio", async () => {
    mockApi({ "GET /users": () => jsonResponse([STUDY, INV, REGISTERED]) });
    renderAt(INV);

    const list = await screen.findByRole("list");
    const items = within(list).getAllByRole("listitem");
    expect(names()).toEqual(["nuevo", "inv", "participante_07"]);
    expect(items[0]).toHaveTextContent(/registro/i);
    expect(items[0]).toHaveTextContent("Activa");
    expect(screen.getByText("3 cuentas, 1 del registro")).toBeVisible();
    expect(screen.queryByText(/sin activar|pendiente/i)).toBeNull();
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

  it("desactiva una cuenta con PATCH /users/{id}, sin moverla, y lo anuncia", async () => {
    const { calls } = mockApi({
      "GET /users": () => jsonResponse([INV, STUDY, REGISTERED]),
      "PATCH /users/u-reg": () => jsonResponse({ ...REGISTERED, active: false }),
    });
    renderAt(INV);
    // El nombre accesible se calcula despacio en jsdom: primero se espera al listado.
    await screen.findByRole("list");
    const before = names();

    await userEvent.click(screen.getByRole("button", { name: /^desactivar la cuenta nuevo/i }));

    expect(await screen.findByText("Cuenta nuevo desactivada.")).toBeInTheDocument();
    expect(names()).toEqual(before);
    const row = within(screen.getByRole("list")).getAllByRole("listitem")[0];
    expect(row).toHaveTextContent("Desactivada");
    expect(screen.getByRole("button", { name: /^activar la cuenta nuevo/i })).toBeVisible();
    const call = calls.find((entry) => entry.key === "PATCH /users/u-reg");
    expect(JSON.parse(call?.init?.body as string)).toEqual({ active: false });
  });

  it("no la ve un transcriptor", async () => {
    mockApi({ "GET /sessions": () => jsonResponse([]) });
    renderAt(ANA);

    expect(await screen.findByRole("heading", { name: /esta página no existe/i })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Cuentas" })).toBeNull();
  });

  it("mientras se guarda un cambio no admite otro, y un fallo dice qué cuenta", async () => {
    const patch = deferred<Response>();
    mockApi({
      "GET /users": () => jsonResponse([INV, STUDY, REGISTERED]),
      "PATCH /users/u-est": () => patch.promise,
    });
    renderAt(INV);
    await screen.findByRole("list");

    await userEvent.click(
      screen.getByRole("button", { name: /^desactivar la cuenta participante_07/i }),
    );

    expect(screen.getByRole("button", { name: "Guardando…" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.getByRole("button", { name: /^desactivar la cuenta nuevo/i })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    patch.resolve(jsonResponse({ detail: "fallo" }, 500));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /no se pudo cambiar la cuenta participante_07/i,
    );
  });
});
