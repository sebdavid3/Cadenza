import { vi } from "vitest";
import { useAuthStore } from "../auth/store";
import type { UserRead } from "../types";

export const ANA: UserRead = {
  id: "7a6d519d-92e9-41de-bf1c-49a1ba7c4c1c",
  username: "ana",
  role: "transcriptor",
  active: true,
  created_at: "2026-10-22T20:00:00",
};

function base64url(value: unknown): string {
  return btoa(JSON.stringify(value)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/** JWT de prueba (sin firma válida) que caduca dentro de `ms` milisegundos. */
export function fakeJwt(ms: number, sub = ANA.id): string {
  const exp = Math.floor((Date.now() + ms) / 1000);
  return `${base64url({ alg: "HS256", typ: "JWT" })}.${base64url({ sub, exp })}.firma`;
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

type Route = (init: RequestInit | undefined) => Response | Promise<Response>;

/** Sustituye `fetch` por un enrutador de respuestas por «MÉTODO /ruta» (sin el prefijo /api). */
export function mockApi(routes: Record<string, Route>) {
  const calls: { key: string; init: RequestInit | undefined }[] = [];
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const href = input instanceof Request ? input.url : input instanceof URL ? input.href : input;
    const url = new URL(href, "http://localhost");
    const path = url.pathname.replace(/^\/api/, "");
    const key = `${init?.method ?? "GET"} ${path}`;
    calls.push({ key, init });
    const route = routes[key];
    if (!route) return Promise.resolve(jsonResponse({ detail: `sin ruta: ${key}` }, 404));
    return Promise.resolve(route(init));
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, calls };
}

export function resetAuth() {
  sessionStorage.clear();
  useAuthStore.setState({ status: "anonymous", token: null, user: null, endReason: null });
}
