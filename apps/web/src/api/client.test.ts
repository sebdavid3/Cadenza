import { afterEach, describe, expect, it, vi } from "vitest";
import { createApiClient } from "./client";
import { ApiError, type ApiErrorKind } from "./errors";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Un fetch que no responde nunca, salvo para rechazar cuando se aborta su señal. */
function hangingFetch(): typeof fetch {
  return vi.fn(
    (_input: RequestInfo | URL, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          reject(new DOMException("The operation was aborted.", "AbortError"));
        });
      }),
  );
}

function calledUrl(fetchMock: ReturnType<typeof vi.fn>): string {
  const call = fetchMock.mock.calls[0];
  if (!call) throw new Error("fetch no se llamó");
  return String(call[0]);
}

function calledInit(fetchMock: ReturnType<typeof vi.fn>): RequestInit {
  const call = fetchMock.mock.calls[0] as [unknown, RequestInit | undefined] | undefined;
  if (!call?.[1]) throw new Error("fetch no recibió opciones");
  return call[1];
}

async function caught(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof ApiError) return error;
    throw error;
  }
  throw new Error("la petición no falló");
}

afterEach(() => {
  vi.useRealTimers();
});

describe("URL base", () => {
  it("usa /api por defecto", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse({ status: "healthy" })));
    const client = createApiClient({ fetch: fetchMock });

    await client.request("/health");

    expect(calledUrl(fetchMock)).toBe("/api/health");
  });

  it("acepta una URL base configurada y quita la barra final", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse([])));
    const client = createApiClient({ baseUrl: "http://api.example.test/", fetch: fetchMock });

    await client.request("/sessions", { query: { limit: 20, offset: 0, status: undefined } });

    expect(calledUrl(fetchMock)).toBe("http://api.example.test/sessions?limit=20&offset=0");
  });
});

describe("autenticación", () => {
  it("envía Authorization: Bearer cuando hay token", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse({})));
    const client = createApiClient({ fetch: fetchMock, getToken: () => "abc.def.ghi" });

    await client.request("/auth/me");

    const headers = new Headers(calledInit(fetchMock).headers);
    expect(headers.get("Authorization")).toBe("Bearer abc.def.ghi");
  });

  it("no envía Authorization sin token ni en peticiones públicas", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse({})));
    const client = createApiClient({ fetch: fetchMock, getToken: () => "abc" });

    await client.request("/health", { auth: false });

    expect(new Headers(calledInit(fetchMock).headers).has("Authorization")).toBe(false);
  });

  it("avisa de un 401 cuando la petición llevaba token", async () => {
    const onUnauthorized = vi.fn();
    const fetchMock = vi.fn(() =>
      Promise.resolve(jsonResponse({ detail: "Not authenticated" }, 401)),
    );
    const client = createApiClient({
      fetch: fetchMock,
      getToken: () => "caducado",
      onUnauthorized,
    });

    const error = await caught(client.request("/sessions"));

    expect(error.kind).toBe("unauthorized");
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  it("no avisa de un 401 de una petición sin token (p. ej. credenciales inválidas)", async () => {
    const onUnauthorized = vi.fn();
    const fetchMock = vi.fn(() =>
      Promise.resolve(jsonResponse({ detail: "Credenciales inválidas" }, 401)),
    );
    const client = createApiClient({ fetch: fetchMock, getToken: () => null, onUnauthorized });

    await caught(client.request("/auth/login", { method: "POST", auth: false }));

    expect(onUnauthorized).not.toHaveBeenCalled();
  });
});

describe("cuerpos y respuestas", () => {
  it("serializa JSON y devuelve la respuesta tipada", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse({ id: "1" }, 201)));
    const client = createApiClient({ fetch: fetchMock });

    const result = await client.request<{ id: string }>("/x", { method: "POST", json: { a: 1 } });

    const init = calledInit(fetchMock);
    expect(result).toEqual({ id: "1" });
    expect(init.method).toBe("POST");
    expect(init.body).toBe('{"a":1}');
    expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
  });

  it("envía FormData y URLSearchParams sin forzar Content-Type", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse({})));
    const client = createApiClient({ fetch: fetchMock });
    const form = new URLSearchParams({ username: "ana", password: "x" });

    await client.request("/auth/login", { method: "POST", body: form, auth: false });

    const init = calledInit(fetchMock);
    expect(init.body).toBe(form);
    expect(new Headers(init.headers).has("Content-Type")).toBe(false);
  });

  it("devuelve un Blob cuando se pide", async () => {
    const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47]);
    const fetchMock = vi.fn(() =>
      Promise.resolve(new Response(png, { headers: { "Content-Type": "image/png" } })),
    );
    const client = createApiClient({ fetch: fetchMock });

    const blob = await client.request<Blob>("/sessions/s1/image", { responseType: "blob" });

    expect(blob).toBeInstanceOf(Blob);
    expect(blob.size).toBe(4);
  });

  it("devuelve undefined en un 204", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response(null, { status: 204 })));
    const client = createApiClient({ fetch: fetchMock });

    await expect(client.request("/x", { method: "DELETE" })).resolves.toBeUndefined();
  });

  it("consulta la salud de la API sin token", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse({ status: "healthy" })));
    const client = createApiClient({ fetch: fetchMock, getToken: () => "abc" });

    await expect(client.health()).resolves.toEqual({ status: "healthy" });
    expect(new Headers(calledInit(fetchMock).headers).has("Authorization")).toBe(false);
  });
});

describe("errores por código de estado", () => {
  const cases: [number, ApiErrorKind, RegExp][] = [
    [401, "unauthorized", /vuelve a entrar/i],
    [403, "forbidden", /permiso/i],
    [404, "not-found", /no se encontró/i],
    [409, "conflict", /cambió/i],
    [413, "payload-too-large", /20 MB/],
    [415, "unsupported-media-type", /PNG o JPEG/],
    [422, "validation", /no son válidos/i],
    [429, "rate-limited", /demasiados intentos/i],
    [500, "server", /servidor/i],
    [503, "server", /servidor/i],
    [418, "unexpected", /inesperada/i],
  ];

  it.each(cases)("%i → %s con mensaje propio", async (status, kind, message) => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(jsonResponse({ detail: "texto del backend en bruto" }, status)),
    );
    const client = createApiClient({ fetch: fetchMock });

    const error = await caught(client.request("/x"));

    expect(error.kind).toBe(kind);
    expect(error.status).toBe(status);
    expect(error.message).toMatch(message);
    expect(error.message).not.toContain("texto del backend en bruto");
    expect(error.detail).toBe("texto del backend en bruto");
  });

  it("tolera un error sin cuerpo JSON", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response("Bad Gateway", { status: 502 })));
    const client = createApiClient({ fetch: fetchMock });

    const error = await caught(client.request("/x"));

    expect(error.kind).toBe("server");
    expect(error.detail).toBeNull();
  });
});

describe("red, timeout y cancelación", () => {
  it("convierte un fallo de red en un error propio", async () => {
    const fetchMock = vi.fn(() => Promise.reject(new TypeError("Failed to fetch")));
    const client = createApiClient({ fetch: fetchMock });

    const error = await caught(client.request("/x"));

    expect(error.kind).toBe("network");
    expect(error.status).toBeNull();
    expect(error.message).toMatch(/no se pudo conectar/i);
  });

  it("aborta la petición al vencer el timeout", async () => {
    vi.useFakeTimers();
    const client = createApiClient({ fetch: hangingFetch(), timeoutMs: 15_000 });

    const pending = caught(client.request("/x"));
    await vi.advanceTimersByTimeAsync(15_000);
    const error = await pending;

    expect(error.kind).toBe("timeout");
    expect(error.message).toMatch(/tardó demasiado/i);
  });

  it("respeta un timeout propio por petición", async () => {
    vi.useFakeTimers();
    const client = createApiClient({ fetch: hangingFetch(), timeoutMs: 15_000 });

    const pending = caught(client.request("/transcribe", { method: "POST", timeoutMs: 30_000 }));
    await vi.advanceTimersByTimeAsync(15_000);
    let settled = false;
    void pending.then(() => (settled = true));
    await vi.advanceTimersByTimeAsync(0);
    expect(settled).toBe(false);

    await vi.advanceTimersByTimeAsync(15_000);
    expect((await pending).kind).toBe("timeout");
  });

  it("distingue la cancelación del usuario del timeout", async () => {
    const controller = new AbortController();
    const client = createApiClient({ fetch: hangingFetch() });

    const pending = caught(client.request("/x", { signal: controller.signal }));
    controller.abort();

    expect((await pending).kind).toBe("aborted");
  });
});
