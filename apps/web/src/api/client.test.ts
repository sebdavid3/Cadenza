import { afterEach, describe, expect, it, vi } from "vitest";
import { createApiClient } from "./client";
import { resolveBaseUrl, TRANSCRIBE_TIMEOUT_MS } from "./config";
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
  vi.unstubAllEnvs();
});

describe("URL base", () => {
  it("usa /api por defecto", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "");
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse({ status: "healthy" })));
    const client = createApiClient({ fetch: fetchMock });

    await client.request("/health");

    expect(calledUrl(fetchMock)).toBe("/api/health");
  });

  it("toma VITE_API_BASE_URL cuando está configurada", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "http://127.0.0.1:8000");
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse({ status: "healthy" })));
    const client = createApiClient({ fetch: fetchMock });

    await client.request("/health");

    expect(calledUrl(fetchMock)).toBe("http://127.0.0.1:8000/health");
  });

  it.each([
    [undefined, "/api"],
    ["", "/api"],
    ["   ", "/api"],
    [" https://api.ejemplo.org ", "https://api.ejemplo.org"],
  ])("resolveBaseUrl(%j) devuelve %s", (configured, expected) => {
    expect(resolveBaseUrl(configured)).toBe(expected);
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

  it("no envía Authorization sin sesión", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse({})));
    const client = createApiClient({ fetch: fetchMock, getToken: () => null });

    await client.request("/sessions");

    expect(new Headers(calledInit(fetchMock).headers).has("Authorization")).toBe(false);
  });

  it("no envía Authorization en peticiones públicas aunque haya sesión", async () => {
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
    expect(onUnauthorized).toHaveBeenCalledExactlyOnceWith("caducado");
  });

  it("no avisa de un 401 cuando la ruta le da otro sentido (contraseña actual equivocada)", async () => {
    const onUnauthorized = vi.fn();
    const fetchMock = vi.fn(() =>
      Promise.resolve(jsonResponse({ detail: "La contraseña actual es incorrecta" }, 401)),
    );
    const client = createApiClient({ fetch: fetchMock, getToken: () => "vigente", onUnauthorized });

    const error = await caught(
      client.request("/auth/password", { method: "POST", json: {}, notifyUnauthorized: false }),
    );

    expect(error.kind).toBe("unauthorized");
    expect(onUnauthorized).not.toHaveBeenCalled();
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

  it.each([
    ["URLSearchParams", new URLSearchParams({ username: "ana", password: "x" })],
    ["FormData", new FormData()],
  ])("envía %s sin forzar Content-Type", async (_name, form) => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse({})));
    const client = createApiClient({ fetch: fetchMock });

    await client.request("/x", { method: "POST", body: form, auth: false });

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

  it("conserva el diagnóstico del 503 de /health", async () => {
    const report = { status: "unhealthy", database: "disconnected" };
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse(report, 503)));
    const client = createApiClient({ fetch: fetchMock });

    const error = await caught(client.health());

    expect(error.kind).toBe("server");
    expect(error.detail).toEqual(report);
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
    [413, "payload-too-large", /tamaño máximo/i],
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

    const pending = caught(
      client.request("/transcribe", { method: "POST", timeoutMs: TRANSCRIBE_TIMEOUT_MS }),
    );
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

  it("clasifica como cancelación lo que se cancela mientras se lee un cuerpo de error", async () => {
    const controller = new AbortController();
    const slowErrorBody = {
      ok: false,
      status: 500,
      json: () =>
        new Promise((_resolve, reject) => {
          controller.signal.addEventListener("abort", () => {
            reject(new DOMException("The operation was aborted.", "AbortError"));
          });
        }),
    } as unknown as Response;
    const client = createApiClient({ fetch: vi.fn(() => Promise.resolve(slowErrorBody)) });

    const pending = caught(client.request("/x", { signal: controller.signal }));
    await Promise.resolve();
    controller.abort();

    expect((await pending).kind).toBe("aborted");
  });
});

describe("limpieza", () => {
  it("no deja temporizadores ni oyentes pendientes al terminar", async () => {
    vi.useFakeTimers();
    const controller = new AbortController();
    const removeListener = vi.spyOn(controller.signal, "removeEventListener");
    const client = createApiClient({ fetch: vi.fn(() => Promise.resolve(jsonResponse({}))) });

    await client.request("/x", { signal: controller.signal });

    expect(vi.getTimerCount()).toBe(0);
    expect(removeListener).toHaveBeenCalledWith("abort", expect.any(Function));
  });

  it("no deja temporizadores si la preparación falla", async () => {
    vi.useFakeTimers();
    const client = createApiClient({
      fetch: vi.fn(),
      getToken: () => {
        throw new Error("almacenamiento bloqueado");
      },
    });

    await expect(client.request("/x")).rejects.toThrow("almacenamiento bloqueado");
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe("Retry-After", () => {
  it.each([
    ["120", 120],
    [null, null],
    ["0", null],
    ["Wed, 21 Oct 2026 07:28:00 GMT", null],
  ])("Retry-After %s → %s", async (header, expected) => {
    const headers = new Headers({ "Content-Type": "application/json" });
    if (header !== null) headers.set("Retry-After", header);
    const fetchMock = vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify({ detail: "x" }), { status: 429, headers })),
    );
    const client = createApiClient({ fetch: fetchMock });

    const error = await caught(client.request("/x"));

    expect(error.kind).toBe("rate-limited");
    expect(error.retryAfterSeconds).toBe(expected);
  });
});

describe("X-Request-ID (#275)", () => {
  const sentId = (fetchMock: ReturnType<typeof vi.fn>, index = 0) => {
    const call = fetchMock.mock.calls[index] as [unknown, RequestInit | undefined] | undefined;
    return new Headers(call?.[1]?.headers).get("X-Request-ID");
  };

  it("cada petición lleva un identificador propio con la forma que acepta la API", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse({})));
    const client = createApiClient({ fetch: fetchMock });

    await client.request("/a");
    await client.request("/b");

    const first = sentId(fetchMock, 0);
    const second = sentId(fetchMock, 1);
    expect(first).toMatch(/^web-[0-9a-f]{20}$/);
    expect(second).toMatch(/^web-[0-9a-f]{20}$/);
    expect(first).not.toBe(second);
  });

  it("usa el identificador que se le dé", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse({})));
    const client = createApiClient({ fetch: fetchMock });

    await client.request("/a", { requestId: "web-orden-7" });

    expect(sentId(fetchMock)).toBe("web-orden-7");
  });
});
