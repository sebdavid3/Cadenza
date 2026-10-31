import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { routes } from "../../router";
import { ANA, fakeJwt, jsonResponse, mockApi, resetAuth, signInAs } from "../../test/auth-helpers";
import type { UserRead } from "../../types";

// Contraseñas generadas en cada ejecución: ninguna prueba depende de su valor.
const PASSWORD = crypto.randomUUID();
const OTHER_PASSWORD = crypto.randomUUID();
const SHORT_PASSWORD = PASSWORD.slice(0, 5);

function renderAt(path = "/registro") {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(<RouterProvider router={router} />);
  return router;
}

async function fill(username: string, password: string, confirmation = password) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Usuario"), username);
  await user.type(screen.getByLabelText("Contraseña"), password);
  await user.type(screen.getByLabelText("Repite la contraseña"), confirmation);
  await user.click(screen.getByRole("button", { name: /crear cuenta/i }));
}

// La cuenta nace activa (ADR-0025).
const CREATED: UserRead = {
  id: "u-1",
  username: "ana",
  role: "transcriptor",
  active: true,
  self_registered: true,
  created_at: "2026-10-23T10:00:00",
};

beforeEach(() => {
  resetAuth();
  // La vista ofrece el formulario solo si el build declara el registro abierto (#248).
  vi.stubEnv("VITE_REGISTRATION_ENABLED", "true");
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("registro de cuentas", () => {
  it("crea la cuenta, entra con ella y lleva a la transcripción", async () => {
    const { calls } = mockApi({
      "POST /auth/register": () => jsonResponse(CREATED, 201),
      "POST /auth/login": () => jsonResponse({ access_token: fakeJwt(1_800_000, CREATED.id) }),
      "GET /auth/me": () => jsonResponse(CREATED),
      "GET /sessions": () => jsonResponse([]),
    });
    const router = renderAt();

    await fill("ana", PASSWORD);

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/transcripcion");
    });
    const call = calls.find((entry) => entry.key === "POST /auth/register");
    expect(JSON.parse(call?.init?.body as string)).toEqual({
      username: "ana",
      password: PASSWORD,
    });
    expect(new Headers(call?.init?.headers).get("Authorization")).toBeNull();
    const login = calls.find((entry) => entry.key === "POST /auth/login");
    expect((login?.init?.body as URLSearchParams).get("username")).toBe("ana");
  });

  it("comprueba la contraseña antes de enviar", async () => {
    const { fetchMock } = mockApi({});
    renderAt();

    await fill("ana", SHORT_PASSWORD);
    expect(await screen.findByRole("alert")).toHaveTextContent(/al menos 8 caracteres/i);
    expect(screen.getByLabelText("Contraseña")).toHaveFocus();

    await userEvent.clear(screen.getByLabelText("Contraseña"));
    await userEvent.clear(screen.getByLabelText("Repite la contraseña"));
    await userEvent.type(screen.getByLabelText("Contraseña"), PASSWORD);
    await userEvent.type(screen.getByLabelText("Repite la contraseña"), OTHER_PASSWORD);
    await userEvent.click(screen.getByRole("button", { name: /crear cuenta/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/no coinciden/i);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("dice que el nombre está ocupado y conserva la contraseña", async () => {
    mockApi({
      "POST /auth/register": () => jsonResponse({ detail: "El usuario 'ana' ya existe" }, 409),
    });
    renderAt();

    await fill("ana", PASSWORD);

    expect(await screen.findByRole("alert")).toHaveTextContent(/ya existe\. elige otro/i);
    expect(screen.getByLabelText("Usuario")).toHaveFocus();
    expect(screen.getByLabelText("Contraseña")).toHaveValue(PASSWORD);
    expect(screen.queryByText(/El usuario 'ana' ya existe/)).toBeNull();
  });

  it("traduce un 422 de esquema al campo que falló", async () => {
    mockApi({
      "POST /auth/register": () =>
        jsonResponse(
          {
            detail: [{ type: "string_too_long", loc: ["body", "username"], msg: "x", input: "a" }],
          },
          422,
        ),
    });
    renderAt();

    await fill("ana", PASSWORD);

    expect(await screen.findByRole("alert")).toHaveTextContent(/usuario no válido/i);
    expect(screen.getByLabelText("Usuario")).toHaveFocus();
    expect(screen.getByLabelText("Usuario")).toHaveAttribute("aria-invalid", "true");
  });

  it("dice cuánto esperar con un 429", async () => {
    mockApi({
      "POST /auth/register": () =>
        new Response(JSON.stringify({ detail: "Demasiados" }), {
          status: 429,
          headers: { "Content-Type": "application/json", "Retry-After": "1500" },
        }),
    });
    renderAt();

    await fill("ana", PASSWORD);

    expect(await screen.findByRole("alert")).toHaveTextContent(/vuelve a probar en 25 minutos/i);
  });

  it("avisa si el registro no está abierto en el servidor", async () => {
    mockApi({ "POST /auth/register": () => jsonResponse({ detail: "Not Found" }, 404) });
    renderAt();

    await fill("ana", PASSWORD);

    expect(await screen.findByRole("alert")).toHaveTextContent(/no está abierto/i);
  });

  it("lleva a la zona privada si ya hay sesión", async () => {
    mockApi({ "GET /sessions": () => jsonResponse([]) });
    signInAs(ANA);
    const router = renderAt();

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/transcripcion");
    });
  });

  it("comprueba el nombre antes de enviar y marca el campo", async () => {
    const { fetchMock } = mockApi({});
    renderAt();

    await fill("Ana ", PASSWORD);

    expect(await screen.findByRole("alert")).toHaveTextContent(/usuario no válido/i);
    const field = screen.getByLabelText("Usuario");
    expect(field).toHaveFocus();
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(field.getAttribute("aria-describedby")).toContain("register-error");
    expect(field.getAttribute("aria-describedby")).toContain("register-username-help");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("un fallo que no es de un campo lleva el foco al aviso y conserva las contraseñas", async () => {
    mockApi({ "POST /auth/register": () => jsonResponse({ detail: "fallo" }, 503) });
    renderAt();

    await fill("ana", PASSWORD);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/el servidor tuvo un problema/i);
    expect(alert).toHaveFocus();
    expect(screen.getByLabelText("Usuario")).toHaveAttribute("aria-invalid", "false");
    expect(screen.getByLabelText("Contraseña")).toHaveValue(PASSWORD);
    expect(screen.getByLabelText("Repite la contraseña")).toHaveValue(PASSWORD);
  });

  it("sin conexión avisa de que la cuenta pudo crearse", async () => {
    mockApi({ "POST /auth/register": () => Promise.reject(new TypeError("Failed to fetch")) });
    renderAt();

    await fill("ana", PASSWORD);

    expect(await screen.findByRole("alert")).toHaveTextContent(/si la cuenta llegó a crearse/i);
  });

  it("si /auth/me falla tras crearla, no deja sesión a medias y enlaza a entrar", async () => {
    mockApi({
      "POST /auth/register": () => jsonResponse(CREATED, 201),
      "POST /auth/login": () => jsonResponse({ access_token: fakeJwt(1_800_000, CREATED.id) }),
      "GET /auth/me": () => jsonResponse({ detail: "fallo" }, 500),
    });
    const router = renderAt();

    await fill("ana", PASSWORD);

    expect(await screen.findByRole("heading", { name: "Cuenta creada" })).toHaveFocus();
    expect(router.state.location.pathname).toBe("/registro");
    expect(screen.getByRole("link", { name: /ir a entrar/i })).toHaveAttribute("href", "/entrar");
  });

  it("con el límite de accesos agotado, dice que la cuenta existe y cuándo entrar", async () => {
    mockApi({
      "POST /auth/register": () => jsonResponse(CREATED, 201),
      "POST /auth/login": () => jsonResponse({ detail: "Demasiados intentos" }, 429),
    });
    renderAt();

    await fill("ana", PASSWORD);

    const heading = await screen.findByRole("heading", { name: "Cuenta creada" });
    expect(heading).toHaveAccessibleDescription(/demasiados intentos de acceso/i);
  });

  it("si no puede entrar tras crearla, dice que la cuenta existe y enlaza a entrar", async () => {
    mockApi({
      "POST /auth/register": () => jsonResponse(CREATED, 201),
      "POST /auth/login": () => jsonResponse({ detail: "fallo" }, 500),
    });
    renderAt();

    await fill("ana", PASSWORD);

    expect(await screen.findByRole("heading", { name: "Cuenta creada" })).toHaveFocus();
    expect(screen.getByText("ana", { selector: "strong" })).toBeVisible();
    expect(screen.getByRole("link", { name: /ir a entrar/i })).toHaveAttribute("href", "/entrar");
    expect(screen.queryByText(/pendiente|activarla/i)).toBeNull();
    expect(screen.queryByDisplayValue(PASSWORD)).toBeNull();
  });
});

describe("registro cerrado en el build (#248)", () => {
  it("no ofrece el formulario, dice que está cerrado y enlaza a entrar", async () => {
    vi.stubEnv("VITE_REGISTRATION_ENABLED", "");
    const { fetchMock } = mockApi({});
    renderAt();

    expect(
      await screen.findByRole("heading", { level: 1, name: /registro cerrado/i }),
    ).toBeVisible();
    expect(screen.getByText(/las cuentas las crea un investigador/i)).toBeVisible();
    expect(screen.getByRole("link", { name: /ir a entrar/i })).toHaveAttribute("href", "/entrar");
    expect(screen.queryByLabelText("Usuario")).toBeNull();
    expect(screen.queryByRole("button", { name: /crear cuenta/i })).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("con sesión iniciada sigue llevando a la zona privada", async () => {
    vi.stubEnv("VITE_REGISTRATION_ENABLED", "false");
    mockApi({ "GET /sessions": () => jsonResponse([]) });
    signInAs(ANA);
    const router = renderAt();

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/transcripcion");
    });
  });
});
