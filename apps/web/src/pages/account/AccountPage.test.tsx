import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "../../auth/store";
import { routes } from "../../router";
import { ANA, deferred, jsonResponse, mockApi, resetAuth, signInAs } from "../../test/auth-helpers";
import { DATA_CONSENT_VERSION } from "../consent/consent";

// Contraseñas generadas en cada ejecución: ninguna prueba depende de su valor (GitGuardian).
const CURRENT = crypto.randomUUID();
const NEXT = crypto.randomUUID();
const SHORT = crypto.randomUUID().slice(0, 5);

const OK = { status: "success", message: "Contraseña actualizada" };

function renderAt(path = "/cuenta") {
  signInAs(ANA);
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(<RouterProvider router={router} />);
  return router;
}

/** El formulario del cambio, por su nombre accesible. */
const form = () => screen.getByRole("form", { name: "Cambiar la contraseña" });

async function fill(current: string, next: string, confirmation = next) {
  const user = userEvent.setup();
  const scope = within(await screen.findByRole("form", { name: "Cambiar la contraseña" }));
  if (current) await user.type(scope.getByLabelText("Contraseña actual"), current);
  if (next) await user.type(scope.getByLabelText("Contraseña nueva"), next);
  if (confirmation)
    await user.type(scope.getByLabelText("Repite la contraseña nueva"), confirmation);
  await user.click(scope.getByRole("button", { name: "Cambiar la contraseña" }));
}

const posts = (calls: { key: string; init: RequestInit | undefined }[]) =>
  calls.filter((call) => call.key === "POST /auth/password");

beforeEach(() => {
  resetAuth();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("cambiar la contraseña (#190)", () => {
  it("se llega desde la cabecera de la zona privada", async () => {
    mockApi({ "GET /sessions": () => jsonResponse([]) });
    const router = renderAt("/transcripcion");

    const link = await screen.findByRole("link", { name: /tu cuenta/i });
    expect(link).toHaveTextContent("ana");
    await userEvent.click(link);

    expect(router.state.location.pathname).toBe("/cuenta");
    expect(await screen.findByRole("heading", { level: 1, name: "Tu cuenta" })).toBeVisible();
    expect(document.title).toBe("Tu cuenta · Cadenza");
    expect(screen.getByRole("link", { name: /tu cuenta/i })).toHaveAttribute(
      "aria-current",
      "page",
    );
    const scope = within(form());
    expect(scope.getByLabelText("Contraseña actual")).toHaveAttribute(
      "autocomplete",
      "current-password",
    );
    expect(scope.getByLabelText("Contraseña nueva")).toHaveAttribute(
      "autocomplete",
      "new-password",
    );
    expect(scope.getByLabelText("Repite la contraseña nueva")).toHaveAttribute(
      "autocomplete",
      "new-password",
    );
  });

  it("cambia la contraseña, vacía el formulario y dice qué pasa con la sesión abierta", async () => {
    const { calls } = mockApi({ "POST /auth/password": () => jsonResponse(OK) });
    renderAt();

    await fill(CURRENT, NEXT);

    const done = await screen.findByRole("status");
    expect(done).toHaveTextContent("Contraseña cambiada.");
    // Comprobado contra la API: el token emitido antes del cambio sigue valiendo hasta que vence.
    expect(done).toHaveTextContent(/sigues dentro/i);
    expect(done).toHaveTextContent(/la próxima vez que entres, usa la contraseña nueva/i);
    // Dice hasta cuándo dura esta sesión: la hora en que vence su token.
    const { expiresAt } = useAuthStore.getState();
    if (expiresAt === null) throw new Error("la sesión de prueba no tiene vencimiento");
    const until = new Intl.DateTimeFormat("es", { hour: "2-digit", minute: "2-digit" }).format(
      expiresAt,
    );
    expect(done).toHaveTextContent(`hasta las ${until}`);
    expect(done).toHaveFocus();
    expect(posts(calls)).toHaveLength(1);
    expect(JSON.parse(posts(calls)[0]?.init?.body as string)).toEqual({
      current_password: CURRENT,
      new_password: NEXT,
    });
    const scope = within(form());
    expect(scope.getByLabelText("Contraseña actual")).toHaveValue("");
    expect(scope.getByLabelText("Contraseña nueva")).toHaveValue("");
    expect(scope.getByLabelText("Repite la contraseña nueva")).toHaveValue("");
    expect(useAuthStore.getState().status).toBe("authenticated");
  });

  it("comprueba antes de enviar lo mismo que el registro", async () => {
    const { calls } = mockApi({ "POST /auth/password": () => jsonResponse(OK) });
    renderAt();

    await fill("", NEXT);
    expect(await screen.findByRole("alert")).toHaveTextContent("Escribe tu contraseña actual.");
    expect(within(form()).getByLabelText("Contraseña actual")).toHaveFocus();
    expect(within(form()).getByLabelText("Contraseña actual")).toHaveAttribute(
      "aria-invalid",
      "true",
    );

    await userEvent.clear(within(form()).getByLabelText("Contraseña nueva"));
    await userEvent.clear(within(form()).getByLabelText("Repite la contraseña nueva"));
    await fill(CURRENT, SHORT);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "La contraseña nueva debe tener al menos 8 caracteres.",
    );
    expect(within(form()).getByLabelText("Contraseña nueva")).toHaveFocus();

    await userEvent.clear(within(form()).getByLabelText("Contraseña actual"));
    await userEvent.clear(within(form()).getByLabelText("Contraseña nueva"));
    await userEvent.clear(within(form()).getByLabelText("Repite la contraseña nueva"));
    await fill(CURRENT, NEXT, `${NEXT}x`);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Las dos contraseñas nuevas no coinciden.",
    );
    expect(within(form()).getByLabelText("Repite la contraseña nueva")).toHaveFocus();

    expect(posts(calls)).toHaveLength(0);
  });

  it("no envía una contraseña nueva igual a la actual", async () => {
    // El aviso de después («la anterior ya no vale») sería falso.
    const { calls } = mockApi({ "POST /auth/password": () => jsonResponse(OK) });
    renderAt();

    await fill(CURRENT, CURRENT);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "La contraseña nueva es igual a la actual.",
    );
    expect(within(form()).getByLabelText("Contraseña nueva")).toHaveFocus();
    expect(posts(calls)).toHaveLength(0);
  });

  it("con la contraseña actual equivocada (401) lo dice y no cierra la sesión", async () => {
    const { calls } = mockApi({
      "POST /auth/password": () => jsonResponse({ detail: "incorrecta" }, 401),
      "GET /auth/me": () => jsonResponse(ANA),
    });
    const router = renderAt();

    await fill(CURRENT, NEXT);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "La contraseña actual no es correcta.",
    );
    const field = within(form()).getByLabelText<HTMLInputElement>("Contraseña actual");
    expect(field).toHaveFocus();
    // Queda elegida: lo que se escriba la sustituye.
    expect([field.selectionStart, field.selectionEnd]).toEqual([0, CURRENT.length]);
    expect(useAuthStore.getState().status).toBe("authenticated");
    expect(router.state.location.pathname).toBe("/cuenta");
    // Lo escrito en la nueva se conserva: solo hay que corregir la actual.
    expect(within(form()).getByLabelText("Contraseña nueva")).toHaveValue(NEXT);
    // Antes de decirlo, comprueba que la sesión sigue valiendo.
    expect(calls.some((call) => call.key === "GET /auth/me")).toBe(true);
  });

  it("si el 401 es porque la sesión ya no vale, la cierra como cualquier otro", async () => {
    mockApi({
      "POST /auth/password": () => jsonResponse({ detail: "Token inválido o expirado" }, 401),
      "GET /auth/me": () => jsonResponse({ detail: "Token inválido o expirado" }, 401),
    });
    const router = renderAt();

    await fill(CURRENT, NEXT);

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/entrar");
    });
    // Como una sesión caducada: el acceso lo dice.
    expect(useAuthStore.getState().status).toBe("anonymous");
    expect(await screen.findByText(/tu sesión caducó/i)).toBeVisible();
  });

  it("un 422 de la nueva lo dice en su campo", async () => {
    mockApi({
      "POST /auth/password": () =>
        jsonResponse(
          { detail: [{ type: "string_too_short", loc: ["body", "new_password"], msg: "corta" }] },
          422,
        ),
    });
    renderAt();

    await fill(CURRENT, NEXT);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "La contraseña nueva debe tener al menos 8 caracteres.",
    );
    expect(within(form()).getByLabelText("Contraseña nueva")).toHaveFocus();
  });

  it("si tras el 401 no se puede comprobar la sesión, lo dice igual y no la cierra", async () => {
    mockApi({
      "POST /auth/password": () => jsonResponse({ detail: "incorrecta" }, 401),
      "GET /auth/me": () => Promise.reject(new TypeError("Failed to fetch")),
    });
    renderAt();

    await fill(CURRENT, NEXT);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "La contraseña actual no es correcta.",
    );
    expect(useAuthStore.getState().status).toBe("authenticated");
  });

  it("un 422 de la actual lo dice en su campo, sin preguntar por la sesión", async () => {
    const { calls } = mockApi({
      "POST /auth/password": () =>
        jsonResponse(
          { detail: [{ type: "string_too_short", loc: ["body", "current_password"], msg: "x" }] },
          422,
        ),
    });
    renderAt();

    await fill(CURRENT, NEXT);

    expect(await screen.findByRole("alert")).toHaveTextContent("Escribe tu contraseña actual.");
    expect(within(form()).getByLabelText("Contraseña actual")).toHaveFocus();
    expect(calls.some((call) => call.key === "GET /auth/me")).toBe(false);
  });

  it("un 429 tiene su propio mensaje, con el plazo si se sabe", async () => {
    mockApi({
      "POST /auth/password": () =>
        new Response(JSON.stringify({ detail: "Demasiados intentos" }), {
          status: 429,
          headers: { "Content-Type": "application/json", "Retry-After": "120" },
        }),
    });
    renderAt();

    await fill(CURRENT, NEXT);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Demasiados intentos. Vuelve a probar en 2 minutos.");
    expect(alert).toHaveFocus();
    expect(useAuthStore.getState().status).toBe("authenticated");
  });

  it("mientras se envía no se envía otra vez y lo dice", async () => {
    const pending = deferred<Response>();
    const { calls } = mockApi({ "POST /auth/password": () => pending.promise });
    renderAt();

    await fill(CURRENT, NEXT);

    const button = await within(form()).findByRole("button", { name: "Cambiando la contraseña…" });
    expect(button).toBeDisabled();
    // Intro en un campo tampoco lo envía otra vez.
    await userEvent.type(within(form()).getByLabelText("Contraseña nueva"), "{Enter}");
    expect(posts(calls)).toHaveLength(1);

    pending.resolve(jsonResponse(OK));
    expect(await screen.findByRole("status")).toHaveTextContent("Contraseña cambiada.");
    expect(posts(calls)).toHaveLength(1);
  });

  it("sin conexión dice que puede que llegara a cambiarse", async () => {
    mockApi({ "POST /auth/password": () => Promise.reject(new TypeError("Failed to fetch")) });
    renderAt();

    await fill(CURRENT, NEXT);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /puede que la contraseña llegara a cambiarse/i,
    );
  });
});

describe("permiso de uso de los datos en «Tu cuenta» (#378)", () => {
  const SWITCH = { name: "Permitir que se usen mis datos así" };
  const REGISTERED = { ...ANA, self_registered: true };

  function renderAs(user: typeof ANA) {
    signInAs(user);
    const router = createMemoryRouter(routes, { initialEntries: ["/cuenta"] });
    render(<RouterProvider router={router} />);
  }

  /** Lo que dice el estado del permiso, en su región viva. */
  function consentState(panel: HTMLElement): HTMLElement {
    const state = panel.querySelector<HTMLElement>("#account-consent-state");
    if (!state) throw new Error("falta el estado del permiso");
    expect(state).toHaveAttribute("aria-live", "polite");
    return state;
  }

  it("se da y se retira con el mismo interruptor, y el perfil de la sesión cambia", async () => {
    const given = {
      ...REGISTERED,
      data_consent: true,
      data_consent_at: "2026-11-09T18:30:00Z",
      data_consent_version: DATA_CONSENT_VERSION,
    };
    const bodies: unknown[] = [];
    let granted = false;
    mockApi({
      "PUT /auth/data-consent": (init) => {
        bodies.push(JSON.parse(init?.body as string));
        granted = !granted;
        return jsonResponse(
          granted
            ? given
            : {
                ...REGISTERED,
                data_consent: false,
                data_consent_at: null,
                data_consent_version: null,
              },
        );
      },
    });
    renderAs(REGISTERED);
    const panel = await screen.findByRole("region", { name: "Uso de tus datos" });
    const toggle = within(panel).getByRole("switch", SWITCH);
    expect(toggle).not.toBeChecked();
    expect(consentState(panel)).toHaveTextContent("No has dado tu permiso.");
    const full = within(panel).getByRole("link", { name: "Leer el texto completo" });
    expect(full).toBeVisible();
    // Desde «Tu cuenta» no hay formulario que perder: enlaza a la página (#397).
    expect(full).toHaveAttribute("href", "/uso-de-los-datos");
    expect(full).not.toHaveAttribute("target");

    await userEvent.click(toggle);
    await waitFor(() => {
      expect(toggle).toBeChecked();
    });
    expect(consentState(panel)).toHaveTextContent("Has dado tu permiso.");
    expect(useAuthStore.getState().user?.data_consent).toBe(true);
    // El foco sigue en el interruptor: no se deshabilita mientras guarda.
    expect(toggle).toHaveFocus();

    await userEvent.click(toggle);
    await waitFor(() => {
      expect(toggle).not.toBeChecked();
    });
    expect(consentState(panel)).toHaveTextContent(/has retirado tu permiso/i);
    expect(bodies).toEqual([{ granted: true, version: DATA_CONSENT_VERSION }, { granted: false }]);
  });

  it("mientras guarda, un segundo toque no envía otra petición ni quita el foco", async () => {
    const pending = deferred<Response>();
    const { calls } = mockApi({ "PUT /auth/data-consent": () => pending.promise });
    renderAs(REGISTERED);
    const panel = await screen.findByRole("region", { name: "Uso de tus datos" });
    const toggle = within(panel).getByRole("switch", SWITCH);

    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-disabled", "true");
    expect(toggle).toBeEnabled();
    await userEvent.click(toggle);

    expect(calls.filter((call) => call.key === "PUT /auth/data-consent")).toHaveLength(1);
    expect(toggle).toHaveFocus();
    pending.resolve(jsonResponse({ ...REGISTERED, data_consent: true }));
    await waitFor(() => {
      expect(toggle).toHaveAttribute("aria-disabled", "false");
    });
  });

  it("no se ofrece a las cuentas que crea el equipo: les rige el consentimiento del estudio", async () => {
    mockApi({});
    renderAs(ANA);

    expect(await screen.findByRole("heading", { name: "Tu cuenta" })).toBeVisible();
    expect(screen.queryByRole("region", { name: "Uso de tus datos" })).toBeNull();
    expect(screen.queryByRole("switch")).toBeNull();
  });

  it("un permiso dado para un texto anterior no está vigente y se pide releerlo", async () => {
    mockApi({});
    renderAs({ ...REGISTERED, data_consent: false, data_consent_version: "2020-01-01" });

    const panel = await screen.findByRole("region", { name: "Uso de tus datos" });

    expect(within(panel).getByRole("switch", SWITCH)).not.toBeChecked();
    expect(consentState(panel)).toHaveTextContent(/versión anterior de este texto/i);
  });

  it("si no se puede guardar, lo dice y el interruptor no cambia", async () => {
    mockApi({
      "PUT /auth/data-consent": () => jsonResponse({ detail: "stale_data_consent" }, 409),
    });
    renderAs(REGISTERED);
    const panel = await screen.findByRole("region", { name: "Uso de tus datos" });
    const toggle = within(panel).getByRole("switch", SWITCH);

    await userEvent.click(toggle);

    expect(await within(panel).findByRole("alert")).toHaveTextContent(
      /el texto del permiso ha cambiado/i,
    );
    expect(toggle).not.toBeChecked();
  });
});
