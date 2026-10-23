import { vi } from "vitest";
import { useAuthStore } from "../auth/store";
import { localExpiry } from "../auth/token";
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

/**
 * JWT de prueba (sin firma válida) que dura `ms` milisegundos, emitido como la API (`iat` y
 * `exp`). `serverSkewMs` simula un servidor con el reloj desplazado respecto al del equipo.
 */
export function fakeJwt(ms: number, sub = ANA.id, serverSkewMs = 0): string {
  const iat = Math.floor((Date.now() + serverSkewMs) / 1000);
  const exp = iat + Math.floor(ms / 1000);
  return `${base64url({ alg: "HS256", typ: "JWT" })}.${base64url({ sub, iat, exp })}.firma`;
}

/** Abre una sesión en el almacén como lo haría el inicio de sesión. */
export function signInAs(user: UserRead, ms = 1_800_000): string {
  const token = fakeJwt(ms, user.id);
  useAuthStore.getState().signIn(token, user, localExpiry(token));
  return token;
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Promesa que el test resuelve o rechaza cuando quiere (una respuesta «en vuelo»). */
export function deferred<T>() {
  let resolve: (value: T) => void = () => undefined;
  let reject: (reason: unknown) => void = () => undefined;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/** Respuesta que no llega nunca: solo termina, como fetch, si se cancela la petición. */
export function hangUntilAborted(init: RequestInit | undefined): Promise<Response> {
  return new Promise((_resolve, reject) => {
    const abort = () => {
      reject(new DOMException("La petición se canceló.", "AbortError"));
    };
    if (init?.signal?.aborted) abort();
    init?.signal?.addEventListener("abort", abort);
  });
}

type Route = (init: RequestInit | undefined) => Response | Promise<Response>;

/** Sustituye `fetch` por un enrutador de respuestas por «MÉTODO /ruta» (sin el prefijo /api). */
export function mockApi(routes: Record<string, Route>) {
  const calls: { key: string; url: URL; init: RequestInit | undefined }[] = [];
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const href = input instanceof Request ? input.url : input instanceof URL ? input.href : input;
    const url = new URL(href, "http://localhost");
    const path = url.pathname.replace(/^\/api/, "");
    const key = `${init?.method ?? "GET"} ${path}`;
    calls.push({ key, url, init });
    const route = routes[key];
    if (!route) return Promise.resolve(jsonResponse({ detail: `sin ruta: ${key}` }, 404));
    return Promise.resolve(route(init));
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, calls };
}

export function resetAuth() {
  sessionStorage.clear();
  useAuthStore.setState({
    status: "anonymous",
    token: null,
    user: null,
    expiresAt: null,
    endReason: null,
  });
}
