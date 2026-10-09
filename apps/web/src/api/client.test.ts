import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Anchor } from "../types";
import {
  appendEdit,
  clearToken,
  fetchMe,
  fetchSession,
  getToken,
  login,
  logout,
  onUnauthorized,
  setToken,
} from "./client";

const ANCHOR: Anchor = {
  part: 0,
  staff: 0,
  measure: 1,
  voice: 0,
  event_index: 0,
  staff_id: "part-0-staff-0",
  bbox: null,
  confidence: null,
};

const createMockStorage = (): Storage => {
  let store: Record<string, string> = {};
  return {
    length: 0,
    clear: () => {
      store = {};
    },
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    key: (_index: number) => null,
  };
};

describe("api client", () => {
  let mockStorage: Storage;

  beforeEach(() => {
    mockStorage = createMockStorage();
    vi.stubGlobal("sessionStorage", mockStorage);
    clearToken();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    clearToken();
  });

  it("fetchSession consulta /sessions/{id} sin token si no ha iniciado sesión", async () => {
    const payload = { session_id: "s1" };
    const mock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => payload,
    });
    vi.stubGlobal("fetch", mock);

    const result = await fetchSession("s1");

    expect(mock).toHaveBeenCalled();
    const [url, init] = mock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/sessions/s1");
    const headers = new Headers(init?.headers);
    expect(headers.has("Authorization")).toBe(false);
    expect(result).toEqual(payload);
  });

  it("envía la cabecera Authorization: Bearer cuando hay token activo", async () => {
    setToken("test-bearer-token");
    const mock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: "u1", username: "transcriptor" }),
    });
    vi.stubGlobal("fetch", mock);

    await fetchMe();

    expect(mock).toHaveBeenCalled();
    const [url, init] = mock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/auth/me");
    const headers = new Headers(init?.headers);
    expect(headers.get("Authorization")).toBe("Bearer test-bearer-token");
  });

  it("lanza un error legible ante una respuesta no OK", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 404, text: async () => "nope" }),
    );

    await expect(fetchSession("x")).rejects.toThrow("API 404: nope");
  });

  it("appendEdit hace POST con JSON y sin campo author", async () => {
    const mock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: "e1" }),
    });
    vi.stubGlobal("fetch", mock);

    await appendEdit("s1", { base_seq: 0, op: "SetPitch", anchor: ANCHOR });

    const [url, init] = mock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/sessions/s1/edits");
    expect(init.method).toBe("POST");
    const headers = new Headers(init.headers);
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(JSON.parse(init.body as string)).toEqual({
      base_seq: 0,
      op: "SetPitch",
      anchor: ANCHOR,
    });
  });

  it("login realiza POST con x-www-form-urlencoded y guarda el token", async () => {
    const mock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ access_token: "new-token-123", token_type: "bearer" }),
    });
    vi.stubGlobal("fetch", mock);

    const tokenRes = await login("tester", "mypassword");

    expect(mock).toHaveBeenCalled();
    const [url, init] = mock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/auth/login");
    expect(init.method).toBe("POST");
    const headers = new Headers(init.headers);
    expect(headers.get("Content-Type")).toBe("application/x-www-form-urlencoded");
    expect(init.body).toBe("username=tester&password=mypassword");

    expect(tokenRes.access_token).toBe("new-token-123");
    expect(getToken()).toBe("new-token-123");
  });

  it("maneja respuesta 401 limpiando el token y notificando al listener", async () => {
    setToken("expired-token");
    const onUnauthorizedSpy = vi.fn();
    const unsubscribe = onUnauthorized(onUnauthorizedSpy);

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        text: async () => "Token expired",
      }),
    );

    await expect(fetchSession("s1")).rejects.toThrow("API 401: Token expired");

    expect(getToken()).toBeNull();
    expect(onUnauthorizedSpy).toHaveBeenCalledTimes(1);

    unsubscribe();
  });

  it("logout limpia el token y dispara listeners", () => {
    setToken("active-token");
    const spy = vi.fn();
    const unsubscribe = onUnauthorized(spy);

    logout();

    expect(getToken()).toBeNull();
    expect(spy).toHaveBeenCalledTimes(1);

    unsubscribe();
  });
});
