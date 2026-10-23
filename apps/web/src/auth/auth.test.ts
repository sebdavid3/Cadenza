import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createApiClient } from "../api/client";
import { ApiError } from "../api/errors";
import { api as appApi } from "../api/instance";
import { ANA, fakeJwt, jsonResponse, mockApi, resetAuth, signInAs } from "../test/auth-helpers";
import { loginErrorMessage, logIn, restoreSession } from "./session";
import { EXPIRY_STORAGE_KEY, TOKEN_STORAGE_KEY, useAuthStore } from "./store";
import { localExpiry, msUntil } from "./token";

const api = createApiClient({ baseUrl: "/api" });

beforeEach(() => {
  resetAuth();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("token", () => {
  it("cuenta la vida del token desde que se recibe", () => {
    const token = fakeJwt(60_000);
    const expiresAt = localExpiry(token, 1_000);

    expect(expiresAt).toBe(61_000);
  });

  it("no depende del reloj del equipo: un servidor adelantado 31 min da igualmente 30 min", () => {
    const token = fakeJwt(30 * 60_000, ANA.id, 31 * 60_000);

    expect(msUntil(localExpiry(token))).toBeGreaterThan(29 * 60_000);
  });

  it("trata un token ilegible como caducado", () => {
    expect(localExpiry("no-es-un-jwt")).toBeNull();
    expect(msUntil(localExpiry("a.%%%.c"))).toBe(0);
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
    expect(Number(sessionStorage.getItem(EXPIRY_STORAGE_KEY))).toBeGreaterThan(Date.now());
  });

  it.each([
    [401, /usuario o contraseña incorrectos/i],
    [429, /demasiados intentos/i],
    [422, /escribe tu usuario y tu contraseña/i],
    [500, /servidor/i],
  ])("con %i muestra un mensaje propio y no guarda nada", async (status, message) => {
    mockApi({ "POST /auth/login": () => jsonResponse({ detail: "en bruto" }, status) });

    const error = await logIn(api, "ana", "mal").catch((caught: unknown) => caught);

    expect(loginErrorMessage(error)).toMatch(message);
    expect(loginErrorMessage(error)).not.toContain("en bruto");
    expect(useAuthStore.getState().token).toBeNull();
    expect(sessionStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
  });

  it("explica la falta de conexión y el timeout", () => {
    expect(loginErrorMessage(new ApiError("network"))).toMatch(/no se pudo conectar/i);
    expect(loginErrorMessage(new ApiError("timeout"))).toMatch(/tardó demasiado/i);
  });
});

describe("recuperar la sesión de la pestaña", () => {
  function storeSession(token: string) {
    sessionStorage.setItem(TOKEN_STORAGE_KEY, token);
    sessionStorage.setItem(EXPIRY_STORAGE_KEY, String(localExpiry(token)));
  }

  it("sin token guardado queda sin sesión", async () => {
    useAuthStore.setState({ status: "restoring" });
    const { fetchMock } = mockApi({});

    await restoreSession(api);

    expect(useAuthStore.getState().status).toBe("anonymous");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("con un token vencido cierra la sesión como caducada sin llamar a la API", async () => {
    useAuthStore.setState({ status: "restoring" });
    storeSession(fakeJwt(-1_000));
    const { fetchMock } = mockApi({});

    await restoreSession(api);

    expect(useAuthStore.getState()).toMatchObject({ status: "anonymous", endReason: "expired" });
    expect(sessionStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("con un token vigente recupera el perfil", async () => {
    const token = fakeJwt(10 * 60_000);
    useAuthStore.setState({ status: "restoring" });
    storeSession(token);
    mockApi({ "GET /auth/me": () => jsonResponse(ANA) });

    await restoreSession(api);

    expect(useAuthStore.getState()).toMatchObject({ status: "authenticated", token, user: ANA });
  });

  it("dos recuperaciones simultáneas hacen una sola petición", async () => {
    useAuthStore.setState({ status: "restoring" });
    storeSession(fakeJwt(10 * 60_000));
    const { calls } = mockApi({ "GET /auth/me": () => jsonResponse(ANA) });

    await Promise.all([restoreSession(api), restoreSession(api)]);

    expect(calls.filter((call) => call.key === "GET /auth/me")).toHaveLength(1);
  });

  it("si la API rechaza el token, la sesión queda caducada", async () => {
    useAuthStore.setState({ status: "restoring" });
    storeSession(fakeJwt(10 * 60_000));
    mockApi({ "GET /auth/me": () => jsonResponse({ detail: "Not authenticated" }, 401) });

    await restoreSession(api);

    expect(useAuthStore.getState()).toMatchObject({ status: "anonymous", endReason: "expired" });
  });

  it("sin conexión conserva el token y queda pendiente de reintento", async () => {
    const token = fakeJwt(10 * 60_000);
    useAuthStore.setState({ status: "restoring" });
    storeSession(token);
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))),
    );

    await restoreSession(api);

    expect(useAuthStore.getState().status).toBe("unreachable");
    expect(sessionStorage.getItem(TOKEN_STORAGE_KEY)).toBe(token);
  });

  it.each([
    ["401", () => jsonResponse({ detail: "x" }, 401)],
    ["200 con otra cuenta", () => jsonResponse({ ...ANA, username: "otra" })],
  ])(
    "una recuperación lenta (%s) no pisa una sesión abierta mientras tanto",
    async (_case, slowAnswer) => {
      useAuthStore.setState({ status: "restoring" });
      storeSession(fakeJwt(10 * 60_000, "otra"));
      let release: () => void = () => undefined;
      const gate = new Promise<void>((resolve) => {
        release = resolve;
      });
      const fresh = fakeJwt(30 * 60_000);
      mockApi({
        "GET /auth/me": async (init) => {
          const auth = new Headers(init?.headers).get("Authorization");
          if (auth === `Bearer ${fresh}`) return jsonResponse(ANA);
          await gate;
          return slowAnswer();
        },
        "POST /auth/login": () => jsonResponse({ access_token: fresh }),
      });

      const pending = restoreSession(api);
      await logIn(api, "ana", "secreta");
      release();
      await pending;

      expect(useAuthStore.getState()).toMatchObject({
        status: "authenticated",
        token: fresh,
        user: ANA,
      });
    },
  );
});

describe("401 de la aplicación", () => {
  it("cierra la sesión solo si el token rechazado es el vigente", async () => {
    const old = fakeJwt(1_000, ANA.id);
    signInAs(ANA);
    let tokenSent = "";
    mockApi({
      "GET /sessions": (init) => {
        tokenSent = new Headers(init?.headers).get("Authorization") ?? "";
        return jsonResponse({ detail: "x" }, 401);
      },
    });

    // Una petición que llevaba un token anterior no cierra la sesión nueva.
    await appApi.request("/sessions", { token: old }).catch(() => undefined);
    expect(tokenSent).toBe(`Bearer ${old}`);
    expect(useAuthStore.getState().status).toBe("authenticated");

    await appApi.request("/sessions").catch(() => undefined);
    expect(useAuthStore.getState()).toMatchObject({ status: "anonymous", endReason: "expired" });
  });
});
