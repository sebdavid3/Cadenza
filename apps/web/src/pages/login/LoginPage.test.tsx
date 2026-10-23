import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "../../auth/store";
import { routes } from "../../router";
import { ANA, fakeJwt, jsonResponse, mockApi, resetAuth } from "../../test/auth-helpers";

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(<RouterProvider router={router} />);
  return router;
}

async function fillAndSubmit(username: string, password: string) {
  await userEvent.type(screen.getByLabelText("Usuario"), username);
  await userEvent.type(screen.getByLabelText("Contraseña"), password);
  await userEvent.click(screen.getByRole("button", { name: /^entrar/i }));
}

beforeEach(() => {
  resetAuth();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("vista de acceso", () => {
  it("tiene campos etiquetados y no ofrece registro ni recuperación por correo", () => {
    renderAt("/entrar");

    expect(screen.getByRole("heading", { level: 1, name: /entrar/i })).toBeVisible();
    expect(screen.getByLabelText("Usuario")).toHaveAttribute("autocomplete", "username");
    expect(screen.getByLabelText("Contraseña")).toHaveAttribute("type", "password");
    expect(screen.queryByText(/regístrate|crear cuenta|olvidaste/i)).not.toBeInTheDocument();
    expect(screen.getByText(/las cuentas las crea un investigador/i)).toBeVisible();
  });

  it("pide los dos campos antes de llamar a la API", async () => {
    const { fetchMock } = mockApi({});
    renderAt("/entrar");

    await userEvent.click(screen.getByRole("button", { name: /^entrar/i }));

    expect(screen.getByRole("alert")).toHaveTextContent(/escribe tu usuario y tu contraseña/i);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("con credenciales correctas entra y lleva a la transcripción", async () => {
    mockApi({
      "POST /auth/login": () => jsonResponse({ access_token: fakeJwt(1_800_000) }),
      "GET /auth/me": () => jsonResponse(ANA),
    });
    const router = renderAt("/entrar");

    await fillAndSubmit("ana", "secreta");

    expect(router.state.location.pathname).toBe("/transcripcion");
    expect(await screen.findByText("ana")).toBeVisible();
    expect(screen.getByText("Transcriptor")).toBeVisible();
  });

  it("con credenciales incorrectas avisa con un mensaje propio y vacía la contraseña", async () => {
    mockApi({
      "POST /auth/login": () => jsonResponse({ detail: "Credenciales inválidas" }, 401),
    });
    const router = renderAt("/entrar");

    await fillAndSubmit("ana", "mala");

    expect(await screen.findByRole("alert")).toHaveTextContent(/usuario o contraseña incorrectos/i);
    expect(screen.queryByText("Credenciales inválidas")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Contraseña")).toHaveValue("");
    expect(router.state.location.pathname).toBe("/entrar");
  });

  it("tras demasiados intentos pide esperar", async () => {
    mockApi({ "POST /auth/login": () => jsonResponse({ detail: "Too many" }, 429) });
    renderAt("/entrar");

    await fillAndSubmit("ana", "mala");

    expect(await screen.findByRole("alert")).toHaveTextContent(/demasiados intentos fallidos/i);
  });
});

describe("rutas privadas y caducidad", () => {
  it("sin sesión, la zona privada lleva al acceso y, al entrar, vuelve adonde se iba", async () => {
    mockApi({
      "POST /auth/login": () => jsonResponse({ access_token: fakeJwt(1_800_000) }),
      "GET /auth/me": () => jsonResponse(ANA),
    });
    const router = renderAt("/transcripcion?pagina=2");

    expect(router.state.location.pathname).toBe("/entrar");
    await fillAndSubmit("ana", "secreta");

    expect(router.state.location.pathname).toBe("/transcripcion");
    expect(router.state.location.search).toBe("?pagina=2");
  });

  it("al vencer el token cierra la sesión y vuelve al acceso con un aviso", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    useAuthStore.getState().signIn(fakeJwt(60_000), ANA);
    const router = renderAt("/transcripcion");
    expect(router.state.location.pathname).toBe("/transcripcion");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(61_000);
    });

    expect(router.state.location.pathname).toBe("/entrar");
    expect(screen.getByRole("status")).toHaveTextContent(/tu sesión caducó/i);
  });

  it("un 401 de la API en la zona privada cierra la sesión como caducada", async () => {
    const { api } = await import("../../api/instance");
    useAuthStore.getState().signIn(fakeJwt(1_800_000), ANA);
    mockApi({ "GET /sessions": () => jsonResponse({ detail: "Not authenticated" }, 401) });
    const router = renderAt("/transcripcion");

    await act(async () => {
      await api.request("/sessions").catch(() => undefined);
    });

    expect(router.state.location.pathname).toBe("/entrar");
    expect(screen.getByRole("status")).toHaveTextContent(/tu sesión caducó/i);
  });

  it("«Salir» cierra la sesión y lleva al acceso sin aviso de caducidad", async () => {
    useAuthStore.getState().signIn(fakeJwt(1_800_000), ANA);
    const router = renderAt("/transcripcion");

    await userEvent.click(screen.getByRole("button", { name: "Salir" }));

    expect(router.state.location.pathname).toBe("/entrar");
    expect(useAuthStore.getState().token).toBeNull();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
