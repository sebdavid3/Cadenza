import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { routes } from "../../router";
import { ANA, jsonResponse, mockApi, resetAuth, signInAs } from "../../test/auth-helpers";

// Contraseñas generadas en cada ejecución: ninguna prueba depende de su valor.
const PASSWORD = `p-${crypto.randomUUID()}`;
const OTHER_PASSWORD = `q-${crypto.randomUUID()}`;
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

beforeEach(() => {
  resetAuth();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("registro de cuentas", () => {
  it("crea la cuenta y explica que queda pendiente de activación", async () => {
    const { calls } = mockApi({
      "POST /auth/register": () =>
        jsonResponse(
          {
            id: "u-1",
            username: "ana",
            role: "transcriptor",
            active: false,
            self_registered: true,
            created_at: "2026-10-23T10:00:00",
          },
          201,
        ),
    });
    renderAt();

    await fill("ana", PASSWORD);

    expect(await screen.findByRole("heading", { name: "Cuenta creada" })).toHaveFocus();
    expect(screen.getByText("ana", { selector: "strong" })).toBeVisible();
    expect(screen.getByText(/pendiente de activación/i)).toBeVisible();
    expect(screen.getByRole("link", { name: /ir a entrar/i })).toHaveAttribute("href", "/entrar");
    const call = calls.find((entry) => entry.key === "POST /auth/register");
    expect(JSON.parse(call?.init?.body as string)).toEqual({
      username: "ana",
      password: PASSWORD,
    });
    expect(new Headers(call?.init?.headers).get("Authorization")).toBeNull();
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
});
