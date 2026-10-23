import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createApiClient } from "../api/client";
import { ApiError } from "../api/errors";
import { ANA, fakeJwt, jsonResponse, mockApi, resetAuth } from "../test/auth-helpers";
import { loginErrorMessage, logIn, restoreSession } from "./session";
import { TOKEN_STORAGE_KEY, useAuthStore } from "./store";
import { msUntilExpiry, tokenExpiresAt } from "./token";

const api = createApiClient({ baseUrl: "/api" });

beforeEach(() => {
  resetAuth();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("token", () => {
  it("lee el exp del JWT en milisegundos", () => {
    const token = fakeJwt(60_000);
    const expiresAt = tokenExpiresAt(token);

    expect(expiresAt).not.toBeNull();
    expect(Math.abs((expiresAt ?? 0) - (Date.now() + 60_000))).toBeLessThan(1500);
  });

  it("trata un token ilegible como caducado", () => {
    expect(tokenExpiresAt("no-es-un-jwt")).toBeNull();
    expect(msUntilExpiry("a.%%%.c")).toBe(0);
  });

  it("no devuelve tiempo negativo para un token vencido", () => {
    expect(msUntilExpiry(fakeJwt(-5_000))).toBe(0);
  });
});

describe("inicio de sesión", () => {
  it("envía el formulario urlencoded, pide el perfil con el token nuevo y guarda la sesión", async () => {
    const token = fakeJwt(30 * 60_000);
    const { calls } = mockApi({
      "POST /auth/login": () => jsonResponse({ access_token: token, token_type: "bearer" }),
      "GET /auth/me": () => jsonResponse(ANA),
    });

    await logIn(api, "ana", "secreta");

    const login = calls[0];
    expect(login?.key).toBe("POST /auth/login");
    expect(login?.init?.body).toBeInstanceOf(URLSearchParams);
    expect((login?.init?.body as URLSearchParams).toString()).toBe("username=ana&password=secreta");
    expect(new Headers(login?.init?.headers).has("Authorization")).toBe(false);
    expect(new Headers(calls[1]?.init?.headers).get("Authorization")).toBe(`Bearer ${token}`);
    expect(useAuthStore.getState()).toMatchObject({ status: "authenticated", token, user: ANA });
    expect(sessionStorage.getItem(TOKEN_STORAGE_KEY)).toBe(token);
  });

  it.each([
    [401, /usuario o contraseña incorrectos/i],
    [429, /demasiados intentos/i],
    [422, /escribe tu usuario y tu contraseña/i],
    [500, /servidor/i],
  ])("con %i muestra un mensaje propio", async (status, message) => {
    mockApi({ "POST /auth/login": () => jsonResponse({ detail: "en bruto" }, status) });

    const error = await logIn(api, "ana", "mal").catch((caught: unknown) => caught);

    expect(loginErrorMessage(error)).toMatch(message);
    expect(loginErrorMessage(error)).not.toContain("en bruto");
    expect(useAuthStore.getState().status).toBe("anonymous");
  });

  it("explica la falta de conexión", () => {
    expect(loginErrorMessage(new ApiError("network"))).toMatch(/no se pudo conectar/i);
  });
});

describe("recuperar la sesión de la pestaña", () => {
  it("sin token guardado queda sin sesión", async () => {
    useAuthStore.setState({ status: "restoring" });
    const { fetchMock } = mockApi({});

    await restoreSession(api);

    expect(useAuthStore.getState().status).toBe("anonymous");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("con un token vencido cierra la sesión como caducada sin llamar a la API", async () => {
    useAuthStore.setState({ status: "restoring" });
    sessionStorage.setItem(TOKEN_STORAGE_KEY, fakeJwt(-1_000));
    const { fetchMock } = mockApi({});

    await restoreSession(api);

    expect(useAuthStore.getState()).toMatchObject({ status: "anonymous", endReason: "expired" });
    expect(sessionStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("con un token vigente recupera el perfil", async () => {
    const token = fakeJwt(10 * 60_000);
    useAuthStore.setState({ status: "restoring" });
    sessionStorage.setItem(TOKEN_STORAGE_KEY, token);
    mockApi({ "GET /auth/me": () => jsonResponse(ANA) });

    await restoreSession(api);

    expect(useAuthStore.getState()).toMatchObject({ status: "authenticated", token, user: ANA });
  });

  it("dos recuperaciones simultáneas hacen una sola petición", async () => {
    useAuthStore.setState({ status: "restoring" });
    sessionStorage.setItem(TOKEN_STORAGE_KEY, fakeJwt(10 * 60_000));
    const { calls } = mockApi({ "GET /auth/me": () => jsonResponse(ANA) });

    await Promise.all([restoreSession(api), restoreSession(api)]);

    expect(calls.filter((call) => call.key === "GET /auth/me")).toHaveLength(1);
  });

  it("si la API rechaza el token, la sesión queda caducada", async () => {
    useAuthStore.setState({ status: "restoring" });
    sessionStorage.setItem(TOKEN_STORAGE_KEY, fakeJwt(10 * 60_000));
    mockApi({ "GET /auth/me": () => jsonResponse({ detail: "Not authenticated" }, 401) });

    await restoreSession(api);

    expect(useAuthStore.getState()).toMatchObject({ status: "anonymous", endReason: "expired" });
  });
});
