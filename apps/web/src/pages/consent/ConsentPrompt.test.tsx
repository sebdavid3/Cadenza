import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/instance";
import { restoreSession } from "../../auth/session";
import { useAuthStore } from "../../auth/store";
import { routes } from "../../router";
import { ANA, deferred, jsonResponse, mockApi, resetAuth, signInAs } from "../../test/auth-helpers";
import { DATA_CONSENT_VERSION } from "./consent";

/** Una cuenta del registro con el permiso de la versión anterior del texto (#427). */
const OUTDATED = {
  ...ANA,
  self_registered: true,
  data_consent: false,
  data_consent_at: null,
  data_consent_version: "2026-11-09",
};
/** Otra cuenta del registro en la misma situación. */
const BEA = { ...OUTDATED, id: "0b1c6a8e-5c0f-4a55-9f0e-2d7c2f0a9b11", username: "bea" };
/** Lo retiró: retirarlo borra la fecha y la versión. */
const WITHDRAWN = { ...OUTDATED, data_consent_version: null };
/** Con el permiso vigente. */
const GIVEN = {
  ...OUTDATED,
  data_consent: true,
  data_consent_at: "2026-11-19T10:00:00Z",
  data_consent_version: DATA_CONSENT_VERSION,
};

const PROMPT = { name: "Tu permiso de uso de los datos" };
const GRANT = { name: "Doy mi permiso" };
const LATER = { name: "Ahora no" };
const THANKS = /gracias: has dado tu permiso/i;

function enter(user: typeof ANA, path = "/transcripcion", ms?: number) {
  signInAs(user, ms);
  return show(path);
}

function show(path = "/transcripcion") {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(<RouterProvider router={router} />);
}

const sessions = { "GET /sessions": () => jsonResponse([]) };

/** El título de la página de transcripción, adonde vuelve el foco al quitar la banda. */
const pageTitle = () => screen.findByRole("heading", { level: 1 });

beforeEach(() => {
  resetAuth();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("pedir el permiso al entrar (#430)", () => {
  it("si el texto cambió, lo dice y se da con un gesto: el perfil cambia y se anuncia", async () => {
    const bodies: unknown[] = [];
    mockApi({
      ...sessions,
      "PUT /auth/data-consent": (init) => {
        bodies.push(JSON.parse(init?.body as string));
        return jsonResponse(GIVEN);
      },
    });
    enter(OUTDATED);

    const prompt = await screen.findByRole("region", PROMPT);
    expect(prompt).toHaveTextContent(/el texto del permiso ha cambiado/i);
    expect(prompt).toHaveTextContent(/puedes seguir usando cadenza igual/i);
    // Rótulo, no encabezado: la banda va antes del h1 de la página.
    expect(within(prompt).queryByRole("heading")).toBeNull();
    expect(within(prompt).getByRole("link", { name: "Leer el texto completo" })).toHaveAttribute(
      "href",
      "/uso-de-los-datos",
    );
    // La región viva existe antes de que llegue el agradecimiento, para que se anuncie.
    const live = prompt.querySelector('[aria-live="polite"]');
    expect(live).not.toBeNull();
    expect(live).toBeEmptyDOMElement();

    await userEvent.click(within(prompt).getByRole("button", GRANT));

    await waitFor(() => {
      expect(live).toHaveTextContent(THANKS);
    });
    expect(screen.queryByRole("button", GRANT)).toBeNull();
    expect(bodies).toEqual([{ granted: true, version: DATA_CONSENT_VERSION }]);
    expect(useAuthStore.getState().user?.data_consent).toBe(true);
    // El botón que tenía el foco desaparece: el foco pasa a «Cerrar».
    const close = within(prompt).getByRole("button", { name: "Cerrar" });
    expect(close).toHaveFocus();

    // «Cerrar» quita la banda y devuelve el foco al título de la página.
    await userEvent.click(close);
    expect(screen.queryByRole("region", PROMPT)).toBeNull();
    const title = await pageTitle();
    await waitFor(() => {
      expect(title).toHaveFocus();
    });
  });

  it("a quien lo retiró no se le insiste: lo vuelve a dar en «Tu cuenta» si quiere", async () => {
    mockApi(sessions);
    enter(WITHDRAWN);

    expect(await pageTitle()).toBeVisible();
    expect(screen.queryByRole("region", PROMPT)).toBeNull();
  });

  it("«Ahora no» lo oculta en esta entrada, también al recargar, y vuelve en la siguiente", async () => {
    mockApi({ ...sessions, "GET /auth/me": () => jsonResponse(OUTDATED) });
    const first = enter(OUTDATED);
    await userEvent.click(
      within(await screen.findByRole("region", PROMPT)).getByRole("button", LATER),
    );
    expect(screen.queryByRole("region", PROMPT)).toBeNull();
    const title = await pageTitle();
    await waitFor(() => {
      expect(title).toHaveFocus();
    });
    first.unmount();

    // Recargar la página: la memoria se vacía y la sesión se restaura de la pestaña.
    useAuthStore.setState({ status: "restoring", token: null, user: null, expiresAt: null });
    await restoreSession(api);
    expect(useAuthStore.getState().status).toBe("authenticated");
    const reloaded = show();
    expect(await pageTitle()).toBeVisible();
    expect(screen.queryByRole("region", PROMPT)).toBeNull();
    reloaded.unmount();

    // Salir y volver a entrar (otro token, que vence en otro momento): se pide otra vez.
    useAuthStore.getState().signOut();
    enter(OUTDATED, "/transcripcion", 1_700_000);
    expect(await screen.findByRole("region", PROMPT)).toBeVisible();
  });

  it("el «Ahora no» de una cuenta no se lo oculta a otra en la misma pestaña", async () => {
    mockApi(sessions);
    const first = enter(OUTDATED);
    await userEvent.click(
      within(await screen.findByRole("region", PROMPT)).getByRole("button", LATER),
    );
    first.unmount();
    useAuthStore.getState().signOut();

    enter(BEA);
    expect(await screen.findByRole("region", PROMPT)).toBeVisible();
  });

  it("mientras guarda, ni un segundo toque ni «Ahora no» hacen nada", async () => {
    const pending = deferred<Response>();
    const { calls } = mockApi({ ...sessions, "PUT /auth/data-consent": () => pending.promise });
    enter(OUTDATED);
    const prompt = await screen.findByRole("region", PROMPT);
    const grant = within(prompt).getByRole("button", GRANT);
    const later = within(prompt).getByRole("button", LATER);

    await userEvent.click(grant);
    expect(grant).toHaveAttribute("aria-disabled", "true");
    expect(later).toHaveAttribute("aria-disabled", "true");
    await userEvent.click(grant);
    await userEvent.click(later);

    expect(calls.filter((call) => call.key === "PUT /auth/data-consent")).toHaveLength(1);
    expect(screen.getByRole("region", PROMPT)).toBeVisible();
    pending.resolve(jsonResponse(GIVEN));
    expect(await within(prompt).findByText(THANKS)).toBeVisible();
  });

  it("si no se puede guardar, lo dice con el mismo mensaje que «Tu cuenta»", async () => {
    mockApi({
      ...sessions,
      "PUT /auth/data-consent": () => jsonResponse({ detail: "stale_data_consent" }, 409),
    });
    enter(OUTDATED);
    const prompt = await screen.findByRole("region", PROMPT);

    await userEvent.click(within(prompt).getByRole("button", GRANT));

    expect(await within(prompt).findByRole("alert")).toHaveTextContent(
      /el texto del permiso ha cambiado/i,
    );
    expect(within(prompt).getByRole("button", GRANT)).toBeVisible();
  });

  it.each([
    ["con el permiso vigente", GIVEN, "/transcripcion"],
    ["a una cuenta del equipo", ANA, "/transcripcion"],
    ["en «Tu cuenta», que tiene su interruptor", OUTDATED, "/cuenta"],
  ])("no aparece %s", async (_, user, path) => {
    mockApi(sessions);
    enter(user, path);

    expect(await pageTitle()).toBeVisible();
    expect(screen.queryByRole("region", PROMPT)).toBeNull();
  });

  it("no aparece en la vista de una sesión, que necesita todo su alto", async () => {
    mockApi({});
    vi.stubGlobal("matchMedia", () => ({ matches: false }));
    enter(OUTDATED, "/sesiones/7f2c");

    expect(await screen.findByRole("heading", { name: "Sesión no encontrada" })).toBeVisible();
    expect(screen.queryByRole("region", PROMPT)).toBeNull();
  });
});
