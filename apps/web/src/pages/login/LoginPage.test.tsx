import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EXPIRY_STORAGE_KEY, TOKEN_STORAGE_KEY, useAuthStore } from "../../auth/store";
import { localExpiry } from "../../auth/token";
import { routes } from "../../router";
import { ANA, fakeJwt, jsonResponse, mockApi, resetAuth, signInAs } from "../../test/auth-helpers";

function renderAt(path: string, state?: unknown) {
  const router = createMemoryRouter(routes, { initialEntries: [{ pathname: path, state }] });
  render(<RouterProvider router={router} />);
  return router;
}

function renderUrl(url: string) {
  const router = createMemoryRouter(routes, { initialEntries: [url] });
  render(<RouterProvider router={router} />);
  return router;
}

async function fill(username: string, password: string) {
  await userEvent.type(screen.getByLabelText("Usuario"), username);
  await userEvent.type(screen.getByLabelText("Contraseña"), password);
}

async function fillAndSubmit(username: string, password: string) {
  await fill(username, password);
  await userEvent.click(screen.getByRole("button", { name: /^entrar/i }));
}

const loginOk = () =>
  mockApi({
    "POST /auth/login": () => jsonResponse({ access_token: fakeJwt(1_800_000) }),
    "GET /auth/me": () => jsonResponse(ANA),
  });

beforeEach(() => {
  resetAuth();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("vista de acceso", () => {
  it("tiene campos etiquetados, enlaza al registro y no ofrece recuperación por correo", () => {
    vi.stubEnv("VITE_REGISTRATION_ENABLED", "true");
    renderUrl("/entrar");

    expect(screen.getByRole("heading", { level: 1, name: /entrar/i })).toBeVisible();
    expect(screen.getByLabelText("Usuario")).toHaveAttribute("autocomplete", "username");
    expect(screen.getByLabelText("Contraseña")).toHaveAttribute("type", "password");
    expect(screen.getByRole("link", { name: "Créala" })).toHaveAttribute("href", "/registro");
    expect(screen.getByText(/queda pendiente hasta que un investigador/i)).toBeVisible();
    expect(screen.getByText(/no hay recuperación de contraseña por correo/i)).toBeVisible();
  });

  it("sin registro abierto en el build no lo enlaza", () => {
    vi.stubEnv("VITE_REGISTRATION_ENABLED", "");
    renderUrl("/entrar");

    expect(screen.queryByRole("link", { name: "Créala" })).toBeNull();
    expect(screen.getByText(/las cuentas las crea un investigador/i)).toBeVisible();
  });

  it("pide los dos campos antes de llamar a la API y lleva el foco al que falta", async () => {
    const { fetchMock } = mockApi({});
    renderUrl("/entrar");

    await userEvent.type(screen.getByLabelText("Usuario"), "ana");
    await userEvent.click(screen.getByRole("button", { name: /^entrar/i }));

    expect(screen.getByRole("alert")).toHaveTextContent(/escribe tu usuario y tu contraseña/i);
    expect(screen.getByLabelText("Contraseña")).toHaveFocus();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("se envía con Enter y muestra el estado de envío", async () => {
    let release: () => void = () => undefined;
    mockApi({
      "POST /auth/login": async () => {
        await new Promise<void>((resolve) => {
          release = resolve;
        });
        return jsonResponse({ access_token: fakeJwt(1_800_000) });
      },
      "GET /auth/me": () => jsonResponse(ANA),
    });
    const router = renderUrl("/entrar");

    await fill("ana", "secreta{Enter}");

    const button = screen.getByRole("button", { name: /entrando/i });
    expect(button).toBeDisabled();
    expect(screen.getByLabelText("Usuario")).toHaveAttribute("readonly");
    await act(async () => {
      release();
      await Promise.resolve();
    });
    expect(await screen.findByText("ana")).toBeVisible();
    expect(router.state.location.pathname).toBe("/transcripcion");
  });

  it("con credenciales correctas entra y lleva a la transcripción", async () => {
    loginOk();
    const router = renderUrl("/entrar");

    await fillAndSubmit("ana", "secreta");

    expect(router.state.location.pathname).toBe("/transcripcion");
    expect(await screen.findByText("ana")).toBeVisible();
    expect(screen.getByText("Transcriptor")).toBeVisible();
  });

  it("con credenciales incorrectas avisa, vacía la contraseña y la enfoca", async () => {
    mockApi({
      "POST /auth/login": () => jsonResponse({ detail: "Credenciales inválidas" }, 401),
    });
    const router = renderUrl("/entrar");

    await fillAndSubmit("ana", "mala");

    expect(await screen.findByRole("alert")).toHaveTextContent(/usuario o contraseña incorrectos/i);
    expect(screen.queryByText("Credenciales inválidas")).not.toBeInTheDocument();
    const password = screen.getByLabelText("Contraseña");
    expect(password).toHaveValue("");
    expect(password).toHaveFocus();
    expect(password).toHaveAttribute("aria-invalid", "true");
    expect(password).toHaveAttribute("aria-describedby", "login-error");
    expect(router.state.location.pathname).toBe("/entrar");
  });

  it("tras demasiados intentos pide esperar", async () => {
    mockApi({ "POST /auth/login": () => jsonResponse({ detail: "Too many" }, 429) });
    renderUrl("/entrar");

    await fillAndSubmit("ana", "mala");

    expect(await screen.findByRole("alert")).toHaveTextContent(/demasiados intentos fallidos/i);
  });

  it.each(["//evil.example", "/\\evil.example", "https://evil.example"])(
    "no vuelve a una ruta externa (%s)",
    async (from) => {
      loginOk();
      const router = renderAt("/entrar", { from });

      await fillAndSubmit("ana", "secreta");

      expect(router.state.location.pathname).toBe("/transcripcion");
    },
  );

  it("mientras comprueba la sesión guardada no deja enviar", async () => {
    const token = fakeJwt(1_800_000);
    sessionStorage.setItem(TOKEN_STORAGE_KEY, token);
    sessionStorage.setItem(EXPIRY_STORAGE_KEY, String(localExpiry(token)));
    useAuthStore.setState({ status: "restoring" });
    let answer: (response: Response) => void = () => undefined;
    mockApi({
      "GET /auth/me": () =>
        new Promise<Response>((resolve) => {
          answer = resolve;
        }),
    });
    renderUrl("/entrar");

    expect(screen.getByRole("button", { name: /comprobando la sesión/i })).toBeDisabled();

    // Cierra la comprobación para no dejarla pendiente para las pruebas siguientes.
    await act(async () => {
      answer(jsonResponse({ detail: "x" }, 401));
      await Promise.resolve();
    });
    expect(await screen.findByRole("button", { name: /^entrar/i })).toBeEnabled();
  });
});

describe("rutas privadas y caducidad", () => {
  it("sin sesión, la zona privada lleva al acceso y, al entrar, vuelve adonde se iba", async () => {
    loginOk();
    const router = renderUrl("/transcripcion?pagina=2");

    expect(router.state.location.pathname).toBe("/entrar");
    await fillAndSubmit("ana", "secreta");

    expect(router.state.location.pathname).toBe("/transcripcion");
    expect(router.state.location.search).toBe("?pagina=2");
  });

  it("al recargar con una sesión guardada vigente se queda en la ruta privada", async () => {
    const token = fakeJwt(1_800_000);
    sessionStorage.setItem(TOKEN_STORAGE_KEY, token);
    sessionStorage.setItem(EXPIRY_STORAGE_KEY, String(localExpiry(token)));
    useAuthStore.setState({ status: "restoring" });
    mockApi({ "GET /auth/me": () => jsonResponse(ANA) });
    const router = renderUrl("/transcripcion");

    expect(screen.getByRole("status")).toHaveTextContent(/comprobando la sesión/i);
    expect(await screen.findByText("ana")).toBeVisible();
    expect(router.state.location.pathname).toBe("/transcripcion");
  });

  it("si al recargar no hay conexión, conserva la sesión y ofrece reintentar", async () => {
    const token = fakeJwt(1_800_000);
    sessionStorage.setItem(TOKEN_STORAGE_KEY, token);
    sessionStorage.setItem(EXPIRY_STORAGE_KEY, String(localExpiry(token)));
    useAuthStore.setState({ status: "restoring" });
    let online = false;
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        if (!online) return Promise.reject(new TypeError("offline"));
        const href =
          input instanceof Request ? input.url : input instanceof URL ? input.href : input;
        return Promise.resolve(jsonResponse(href.includes("/auth/me") ? ANA : []));
      }),
    );
    const router = renderUrl("/transcripcion");

    expect(await screen.findByRole("alert")).toHaveTextContent(/no se pudo conectar/i);
    online = true;
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByText("ana")).toBeVisible();
    expect(router.state.location.pathname).toBe("/transcripcion");
  });

  it("al vencer el token cierra la sesión y vuelve al acceso con un aviso", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    signInAs(ANA, 60_000);
    const router = renderUrl("/transcripcion");
    expect(router.state.location.pathname).toBe("/transcripcion");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(61_000);
    });

    expect(router.state.location.pathname).toBe("/entrar");
    expect(screen.getByRole("status")).toHaveTextContent(/tu sesión caducó/i);
  });

  it("una caducidad lejana no cierra la sesión antes de tiempo (límite de setTimeout)", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    signInAs(ANA, 30 * 24 * 3600 * 1000);
    const router = renderUrl("/transcripcion");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });

    expect(router.state.location.pathname).toBe("/transcripcion");
  });

  it("un 401 de la API en la zona privada cierra la sesión como caducada", async () => {
    const { api } = await import("../../api/instance");
    signInAs(ANA);
    mockApi({ "GET /sessions": () => jsonResponse({ detail: "Not authenticated" }, 401) });
    const router = renderUrl("/transcripcion");

    await act(async () => {
      await api.request("/sessions").catch(() => undefined);
    });

    expect(router.state.location.pathname).toBe("/entrar");
    expect(screen.getByRole("status")).toHaveTextContent(/tu sesión caducó/i);
  });

  it("«Salir» cierra la sesión sin aviso y no recuerda la ruta para la siguiente persona", async () => {
    signInAs(ANA);
    const router = renderUrl("/transcripcion?pagina=2");

    await userEvent.click(screen.getByRole("button", { name: "Salir" }));

    expect(router.state.location.pathname).toBe("/entrar");
    expect(useAuthStore.getState().token).toBeNull();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    loginOk();
    await fillAndSubmit("bruno", "secreta");
    expect(router.state.location.pathname).toBe("/transcripcion");
    expect(router.state.location.search).toBe("");
  });
});
