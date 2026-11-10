import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { routes } from "../../router";
import { ANA, fakeJwt, jsonResponse, mockApi, resetAuth, signInAs } from "../../test/auth-helpers";
import type { UserRead } from "../../types";
import { DATA_CONSENT_VERSION } from "../consent/consent";

// Contraseñas generadas en cada ejecución: ninguna prueba depende de su valor.
const PASSWORD = crypto.randomUUID();
const OTHER_PASSWORD = crypto.randomUUID();
const SHORT_PASSWORD = PASSWORD.slice(0, 5);

function renderAt(path = "/registro") {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(<RouterProvider router={router} />);
  return router;
}

/** Rellena el registro y lo envía; por defecto, marcando la casilla del permiso (#378). */
async function fill(
  username: string,
  password: string,
  confirmation = password,
  { consent = true }: { consent?: boolean } = {},
) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Usuario"), username);
  await user.type(screen.getByLabelText("Contraseña"), password);
  await user.type(screen.getByLabelText("Repite la contraseña"), confirmation);
  if (consent) await user.click(screen.getByRole("checkbox", { name: CONSENT_LABEL }));
  await user.click(screen.getByRole("button", { name: /crear cuenta/i }));
}

const CONSENT_LABEL = "Doy mi permiso para que se usen mis datos así.";

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
    // Con el permiso, la versión del texto que se leyó (#378, ADR-0065).
    expect(JSON.parse(call?.init?.body as string)).toEqual({
      username: "ana",
      password: PASSWORD,
      data_consent_version: DATA_CONSENT_VERSION,
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

describe("permiso de uso de los datos al registrarse (#378)", () => {
  it("el aviso dice qué se guarda, para qué y con seudónimo, y ofrece el texto completo", async () => {
    mockApi({});
    renderAt();

    const consent = await screen.findByRole("group", { name: "Uso de tus datos" });
    expect(consent).toHaveTextContent(
      /con tu nombre de usuario \(puede ser un seudónimo\) y sin tu correo/i,
    );
    for (const stored of [
      "las imágenes de partituras que subes",
      "lo que HOMR leyó en ellas",
      "tus correcciones",
      "el tiempo que trabajas en cada partitura",
      "lo que respondes a las sugerencias",
    ]) {
      expect(consent).toHaveTextContent(stored);
    }
    expect(consent).toHaveTextContent(
      /investigar y para mejorar el modelo que transcribe y el que sugiere correcciones/i,
    );
    // Se despliega en el mismo formulario: ni otra pestaña ni navegación (#397).
    expect(screen.queryByRole("link", { name: /texto completo/i })).toBeNull();
    expect(screen.getByRole("button", { name: "Leer el texto completo" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    const checkbox = screen.getByRole("checkbox", { name: CONSENT_LABEL });
    expect(checkbox).not.toBeChecked();
    expect(checkbox).toHaveAccessibleDescription(/forma parte de una investigación/i);
    // Solo el aviso: ni el botón del texto completo ni el texto desplegado (#397).
    expect(checkbox).not.toHaveAccessibleDescription(/texto completo/i);
  });

  it("despliega el texto completo en el formulario sin perder lo escrito (#397)", async () => {
    mockApi({});
    renderAt();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Usuario"), "ana");

    const toggle = screen.getByRole("button", { name: "Leer el texto completo" });
    await user.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(toggle).toHaveAccessibleName("Ocultar el texto completo");
    const full = screen.getByRole("region", { name: "Texto completo del permiso" });
    expect(toggle).toHaveAttribute("aria-controls", full.id);
    // Con desplazamiento propio: se enfoca para recorrerlo con el teclado.
    expect(full).toHaveAttribute("tabindex", "0");
    expect(full).toHaveTextContent("Versión del 9 de noviembre de 2026");
    for (const section of [
      "Qué se guarda",
      "Para qué, con tu permiso",
      "Derechos de autor de las partituras",
      "Dar y retirar el permiso",
      "Dudas",
    ]) {
      expect(within(full).getByRole("heading", { name: section })).toBeVisible();
    }
    expect(full).toHaveTextContent(
      /de dominio público, tuyas o con permiso de quien tiene sus derechos/i,
    );
    expect(screen.getByLabelText("Usuario")).toHaveValue("ana");
    // La casilla se sigue describiendo con el aviso breve, no con el texto entero.
    expect(screen.getByRole("checkbox", { name: CONSENT_LABEL })).not.toHaveAccessibleDescription(
      /derechos de autor/i,
    );

    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveAccessibleName("Leer el texto completo");
    expect(screen.queryByRole("region", { name: "Texto completo del permiso" })).toBeNull();
  });

  it("sin marcar la casilla no envía nada, lo dice y lleva el foco a ella", async () => {
    const { fetchMock } = mockApi({});
    renderAt();

    await fill("ana", PASSWORD, PASSWORD, { consent: false });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Para crear la cuenta, marca la casilla del permiso de uso de los datos.",
    );
    expect(screen.getByRole("checkbox", { name: CONSENT_LABEL })).toHaveFocus();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("si el texto del permiso cambió en el servidor, pide recargar y releerlo", async () => {
    mockApi({
      "POST /auth/register": () => jsonResponse({ detail: "stale_data_consent" }, 409),
    });
    renderAt();

    await fill("ana", PASSWORD);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /el texto del permiso de uso de los datos ha cambiado/i,
    );
    expect(screen.getByRole("checkbox", { name: CONSENT_LABEL })).toHaveFocus();
  });

  it("el texto completo se lee sin cuenta y dice su versión", async () => {
    mockApi({});
    renderAt("/uso-de-los-datos");

    expect(
      await screen.findByRole("heading", { name: "Uso de tus datos", level: 1 }),
    ).toBeVisible();
    expect(screen.getByText("Versión del 9 de noviembre de 2026")).toBeVisible();
    for (const section of [
      "Qué se guarda",
      "Para qué, con tu permiso",
      "Derechos de autor de las partituras",
      "Dar y retirar el permiso",
    ]) {
      expect(screen.getByRole("heading", { name: section, level: 2 })).toBeVisible();
    }
    // Solo partituras que se puedan usar; subirlas no cede sus derechos.
    expect(
      screen.getByRole("region", { name: "Derechos de autor de las partituras" }),
    ).toHaveTextContent(/de dominio público, tuyas o con permiso de quien tiene sus derechos/i);
    expect(screen.getByRole("link", { name: "Volver a crear una cuenta" })).toHaveAttribute(
      "href",
      "/registro",
    );
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
