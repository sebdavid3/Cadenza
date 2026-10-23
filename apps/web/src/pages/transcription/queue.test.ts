import { onlineManager, QueryClient } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createApiClient } from "../../api/client";
import { useAuthStore } from "../../auth/store";
import {
  ANA,
  deferred,
  hangUntilAborted,
  jsonResponse,
  mockApi,
  resetAuth,
  signInAs,
} from "../../test/auth-helpers";
import type { UserRead } from "../../types";
import { MAX_UPLOAD_BYTES, precheck, useQueueStore } from "./queue";
import {
  createLimiter,
  formatDay,
  formatTime,
  isoUtc,
  parseUtc,
  refreshSessions,
  SESSIONS_QUERY_KEY,
  shrinkForThumbnail,
  statusLabel,
  thumbnailSize,
} from "./sessions";

// Sin getToken: la cola manda en cada envío el token de quien la llenó.
const api = createApiClient({ baseUrl: "/api" });

const BRUNO: UserRead = { ...ANA, id: "b7c1a3f0-0000-4000-8000-000000000002", username: "bruno" };

function authorization(init: RequestInit | undefined): string | null {
  return new Headers(init?.headers).get("Authorization");
}

const statuses = () => useQueueStore.getState().items.map((item) => item.status);

function png(name = "incipit.png", size = 1024) {
  return new File([new Uint8Array(size)], name, { type: "image/png" });
}

function transcribed(id: string, findings = 0) {
  return {
    session_id: id,
    document_id: `doc-${id}`,
    omr_engine: "homr",
    findings_count: findings,
    condition: "assisted",
    test_score_id: null,
  };
}

let anaToken = "";

beforeEach(() => {
  resetAuth();
  useQueueStore.getState().reset();
  anaToken = signInAs(ANA);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("comprobación previa", () => {
  it("acepta PNG y JPEG", () => {
    expect(precheck(png())).toBeNull();
    expect(precheck(new File(["x"], "a.jpg", { type: "image/jpeg" }))).toBeNull();
  });

  it("rechaza lo que no es PNG ni JPEG, lo vacío y lo que supera 20 MB", () => {
    expect(precheck(new File(["hola"], "notas.txt", { type: "text/plain" }))).toMatch(
      /no es una imagen png o jpeg/i,
    );
    expect(precheck(new File([], "vacia.png", { type: "image/png" }))).toMatch(/vacío/i);
    const big = png("grande.png");
    Object.defineProperty(big, "size", { value: MAX_UPLOAD_BYTES + 1 });
    expect(precheck(big)).toMatch(/20 MB/);
  });
});

describe("cola secuencial", () => {
  it("envía las imágenes de una en una, como multipart con el campo file y el token de quien la llenó", async () => {
    let inFlight = 0;
    let maxInFlight = 0;
    let n = 0;
    const { calls } = mockApi({
      "POST /transcribe": async () => {
        inFlight += 1;
        maxInFlight = Math.max(maxInFlight, inFlight);
        await new Promise((resolve) => setTimeout(resolve, 5));
        inFlight -= 1;
        n += 1;
        return jsonResponse(transcribed(`s${String(n)}`, n), 201);
      },
    });
    const store = useQueueStore.getState();
    store.add([png("a.png"), png("b.png"), png("c.png")]);

    await store.run(api);

    expect(maxInFlight).toBe(1);
    expect(useQueueStore.getState().items.map((item) => item.result?.session_id)).toEqual([
      "s1",
      "s2",
      "s3",
    ]);
    expect(statuses()).toEqual(["done", "done", "done"]);
    const body = calls[0]?.init?.body;
    expect(body).toBeInstanceOf(FormData);
    expect((body as FormData).get("file")).toBeInstanceOf(File);
    expect([...(body as FormData).keys()]).toEqual(["file"]);
    expect(calls.map((call) => authorization(call.init))).toEqual([
      `Bearer ${anaToken}`,
      `Bearer ${anaToken}`,
      `Bearer ${anaToken}`,
    ]);
  });

  it("guarda cuándo empezó cada imagen para que el contador no se reinicie", async () => {
    const response = deferred<Response>();
    mockApi({ "POST /transcribe": () => response.promise });
    const store = useQueueStore.getState();
    store.add([png()]);
    const before = Date.now();

    const running = store.run(api);
    const [item] = useQueueStore.getState().items;
    expect(item?.status).toBe("transcribing");
    expect(item?.startedAt).toBeGreaterThanOrEqual(before);

    response.resolve(jsonResponse(transcribed("s1"), 201));
    await running;
  });

  it("acepta imágenes nuevas con la cola en marcha y las envía en el mismo recorrido", async () => {
    const first = deferred<Response>();
    let n = 0;
    const { calls } = mockApi({
      "POST /transcribe": () => {
        n += 1;
        return n === 1 ? first.promise : jsonResponse(transcribed(`s${String(n)}`), 201);
      },
    });
    const store = useQueueStore.getState();
    store.add([png("a.png")]);

    const running = store.run(api);
    store.add([png("b.png"), png("c.png")]);
    expect(statuses()).toEqual(["transcribing", "queued", "queued"]);
    // Una segunda llamada mientras corre no abre otro recorrido en paralelo.
    await store.run(api);
    first.resolve(jsonResponse(transcribed("s1"), 201));
    await running;

    expect(statuses()).toEqual(["done", "done", "done"]);
    expect(calls).toHaveLength(3);
  });

  it("espera 30 s a la transcripción y avisa de que la sesión puede haberse creado", async () => {
    vi.useFakeTimers();
    mockApi({ "POST /transcribe": hangUntilAborted });
    const store = useQueueStore.getState();
    store.add([png()]);

    const running = store.run(api);
    await vi.advanceTimersByTimeAsync(29_999);
    expect(statuses()).toEqual(["transcribing"]);

    await vi.advanceTimersByTimeAsync(1);
    await running;
    const [item] = useQueueStore.getState().items;
    expect(item?.status).toBe("error");
    expect(item?.error).toMatch(/más de 30 s/);
    expect(item?.error).toMatch(/puede que se haya creado; revisa el listado antes de reintentar/i);
  });

  it("un fallo de red deja un mensaje propio", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))),
    );
    const store = useQueueStore.getState();
    store.add([png()]);

    await store.run(api);

    expect(useQueueStore.getState().items[0]?.error).toMatch(
      /no se pudo conectar con el servidor/i,
    );
  });

  it("tras cada envío, salga bien o mal, avisa para actualizar el listado", async () => {
    let n = 0;
    mockApi({
      "POST /transcribe": () => {
        n += 1;
        return n === 1
          ? jsonResponse({ detail: "x" }, 500)
          : jsonResponse(transcribed(`s${String(n)}`), 201);
      },
    });
    const settled = vi.fn();
    const store = useQueueStore.getState();
    store.add([png("a.png"), png("b.png")]);

    await store.run(api, settled);

    expect(settled).toHaveBeenCalledTimes(2);
  });

  it("no envía los archivos rechazados en la comprobación previa", async () => {
    const { fetchMock } = mockApi({});
    const store = useQueueStore.getState();
    store.add([new File(["hola"], "notas.txt", { type: "text/plain" })]);

    await store.run(api);

    expect(fetchMock).not.toHaveBeenCalled();
    expect(useQueueStore.getState().items[0]).toMatchObject({ status: "error", rejected: true });
  });

  it.each([
    [415, /no la reconoce como imagen/i],
    [413, /tamaño máximo/i],
    [422, /no se reconoció ninguna partitura/i],
    [500, /servidor/i],
  ])(
    "un %i deja el archivo en error con mensaje propio y sigue con el resto",
    async (status, message) => {
      let n = 0;
      mockApi({
        "POST /transcribe": () => {
          n += 1;
          return n === 1
            ? jsonResponse({ detail: "en bruto" }, status)
            : jsonResponse(transcribed("s2"), 201);
        },
      });
      const store = useQueueStore.getState();
      store.add([png("mala.png"), png("buena.png")]);

      await store.run(api);

      const [bad, good] = useQueueStore.getState().items;
      expect(bad).toMatchObject({ status: "error" });
      expect(bad?.error).toMatch(message);
      expect(bad?.error).not.toContain("en bruto");
      expect(good).toMatchObject({ status: "done" });
    },
  );

  it.each([
    ["un fallo de red", () => Promise.reject(new TypeError("Failed to fetch"))],
    ["un 503", () => jsonResponse({ detail: "x" }, 503)],
    ["un 502", () => jsonResponse({ detail: "x" }, 502)],
  ])("con %s se pausa, deja el resto en cola y sigue al reanudar", async (_label, failure) => {
    let n = 0;
    const { calls } = mockApi({
      "POST /transcribe": () => {
        n += 1;
        return n === 1 ? failure() : jsonResponse(transcribed(`s${String(n)}`), 201);
      },
    });
    const store = useQueueStore.getState();
    store.add([png("a.png"), png("b.png")]);

    await store.run(api);
    expect(statuses()).toEqual(["error", "queued"]);
    expect(useQueueStore.getState().paused).toBe(true);
    await store.run(api);
    expect(calls).toHaveLength(1);

    useQueueStore.getState().resume();
    await store.run(api);
    expect(statuses()).toEqual(["error", "done"]);
    expect(useQueueStore.getState().paused).toBe(false);
  });

  it("reintentar, añadir imágenes o volver a entrar quitan la pausa", async () => {
    mockApi({ "POST /transcribe": () => Promise.reject(new TypeError("Failed to fetch")) });
    const store = useQueueStore.getState();
    const pause = async () => {
      store.add([png()]);
      await store.run(api);
      expect(useQueueStore.getState().paused).toBe(true);
    };

    await pause();
    const failed = useQueueStore.getState().items.at(-1);
    store.retry(failed?.id ?? "");
    expect(useQueueStore.getState().paused).toBe(false);

    await store.run(api);
    expect(useQueueStore.getState().paused).toBe(true);
    store.add([png("otra.png")]);
    expect(useQueueStore.getState().paused).toBe(false);

    await store.run(api);
    expect(useQueueStore.getState().paused).toBe(true);
    useAuthStore.getState().signOut("expired");
    signInAs(ANA);
    expect(useQueueStore.getState().paused).toBe(false);
  });

  it("un 500 de una imagen no pausa la cola", async () => {
    let n = 0;
    mockApi({
      "POST /transcribe": () => {
        n += 1;
        return n === 1
          ? jsonResponse({ detail: "x" }, 500)
          : jsonResponse(transcribed(`s${String(n)}`), 201);
      },
    });
    const store = useQueueStore.getState();
    store.add([png("a.png"), png("b.png")]);

    await store.run(api);

    expect(statuses()).toEqual(["error", "done"]);
    expect(useQueueStore.getState().paused).toBe(false);
  });

  it("ante un 401 se detiene y deja el resto en cola", async () => {
    const { calls } = mockApi({
      "POST /transcribe": () => jsonResponse({ detail: "Not authenticated" }, 401),
    });
    const store = useQueueStore.getState();
    store.add([png("a.png"), png("b.png")]);

    await store.run(api);

    expect(statuses()).toEqual(["error", "queued"]);
    expect(useQueueStore.getState().items[0]?.error).toMatch(/sesión/i);
    expect(calls).toHaveLength(1);
  });

  it("si la sesión caduca con una imagen en vuelo, la siguiente espera en cola y no sale sin token", async () => {
    const first = deferred<Response>();
    const { calls } = mockApi({ "POST /transcribe": () => first.promise });
    const store = useQueueStore.getState();
    store.add([png("a.png"), png("b.png")]);

    const running = store.run(api);
    useAuthStore.getState().signOut("expired");
    first.resolve(jsonResponse(transcribed("s1"), 201));
    await running;

    expect(statuses()).toEqual(["done", "queued"]);
    expect(calls).toHaveLength(1);
    expect(useQueueStore.getState().running).toBe(false);
  });

  it("al volver a entrar la misma persona, la cola se conserva y se reanuda", async () => {
    let n = 0;
    const { calls } = mockApi({
      "POST /transcribe": () => {
        n += 1;
        return jsonResponse(transcribed(`s${String(n)}`), 201);
      },
    });
    const store = useQueueStore.getState();
    store.add([png("a.png")]);
    useAuthStore.getState().signOut("expired");
    await store.run(api);
    expect(statuses()).toEqual(["queued"]);
    expect(calls).toHaveLength(0);

    const newToken = signInAs(ANA);
    await store.run(api);

    expect(statuses()).toEqual(["done"]);
    expect(authorization(calls[0]?.init)).toBe(`Bearer ${newToken}`);
  });

  it("si entra otra persona con una imagen en vuelo, se cancela y nada sale con su token", async () => {
    const signals: AbortSignal[] = [];
    const { calls } = mockApi({
      "POST /transcribe": (init) => {
        if (init?.signal) signals.push(init.signal);
        return hangUntilAborted(init);
      },
    });
    const store = useQueueStore.getState();
    store.add([png("a.png"), png("b.png")]);

    const running = store.run(api);
    const brunoToken = signInAs(BRUNO);
    await running;

    expect(signals.map((signal) => signal.aborted)).toEqual([true]);
    expect(useQueueStore.getState()).toMatchObject({
      items: [],
      ownerId: BRUNO.id,
      running: false,
    });
    expect(calls).toHaveLength(1);
    expect(authorization(calls[0]?.init)).toBe(`Bearer ${anaToken}`);
    expect(calls.some((call) => authorization(call.init) === `Bearer ${brunoToken}`)).toBe(false);
  });

  it("una respuesta tardía de un recorrido cancelado no toca la cola nueva", async () => {
    const late = deferred<Response>();
    let n = 0;
    mockApi({
      "POST /transcribe": () => {
        n += 1;
        return n === 1 ? late.promise : jsonResponse(transcribed("de-bruno"), 201);
      },
    });
    const store = useQueueStore.getState();
    store.add([png("de-ana.png")]);
    const oldRun = store.run(api);

    signInAs(BRUNO);
    store.add([png("de-bruno.png")]);
    await store.run(api);
    late.resolve(jsonResponse(transcribed("de-ana"), 201));
    await oldRun;

    const items = useQueueStore.getState().items;
    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({ status: "done", result: { session_id: "de-bruno" } });
    expect(useQueueStore.getState().running).toBe(false);
  });

  it("al salir se cancela la petición en vuelo y se vacía la cola", async () => {
    const signals: AbortSignal[] = [];
    const { calls } = mockApi({
      "POST /transcribe": (init) => {
        if (init?.signal) signals.push(init.signal);
        return hangUntilAborted(init);
      },
    });
    const store = useQueueStore.getState();
    store.add([png("a.png"), png("b.png")]);

    const running = store.run(api);
    useAuthStore.getState().signOut("signed-out");
    await running;

    expect(signals.map((signal) => signal.aborted)).toEqual([true]);
    expect(useQueueStore.getState()).toMatchObject({ items: [], ownerId: null, running: false });
    expect(calls).toHaveLength(1);
  });

  it("quita pendientes, reintenta fallidos y limpia terminados", async () => {
    let n = 0;
    mockApi({
      "POST /transcribe": () => {
        n += 1;
        return n === 1
          ? jsonResponse({ detail: "x" }, 500)
          : jsonResponse(transcribed(`s${String(n)}`), 201);
      },
    });
    const store = useQueueStore.getState();
    store.add([png("a.png"), png("b.png")]);
    const [first, second] = useQueueStore.getState().items;
    if (!first || !second) throw new Error("faltan elementos");
    store.remove(second.id);
    await store.run(api);
    expect(useQueueStore.getState().items).toHaveLength(1);
    expect(useQueueStore.getState().items[0]?.status).toBe("error");

    store.retry(first.id);
    await store.run(api);
    expect(useQueueStore.getState().items[0]?.status).toBe("done");

    store.clearFinished();
    expect(useQueueStore.getState().items).toHaveLength(0);
  });

  it("vacía la cola si entra otra persona en la pestaña, pero no si vuelve la misma", () => {
    const store = useQueueStore.getState();
    store.add([png()]);
    useAuthStore.getState().signOut("expired");
    signInAs(ANA);
    expect(useQueueStore.getState().items).toHaveLength(1);

    signInAs(BRUNO);
    expect(useQueueStore.getState().items).toHaveLength(0);
  });
});

describe("datos de sesiones", () => {
  it("interpreta created_at sin zona horaria como UTC", () => {
    expect(parseUtc("2026-10-22T20:15:00").toISOString()).toBe("2026-10-22T20:15:00.000Z");
    expect(parseUtc("2026-10-22T20:15:00Z").toISOString()).toBe("2026-10-22T20:15:00.000Z");
    expect(parseUtc("2026-10-22T20:15:00+02:00").toISOString()).toBe("2026-10-22T18:15:00.000Z");
  });

  it("reduce la miniatura lo justo para cubrir el hueco de 96 × 48 a doble densidad", () => {
    // Un incipit apaisado manda la altura; una página escaneada, la anchura.
    expect(thumbnailSize(1200, 200)).toEqual({ width: 576, height: 96 });
    expect(thumbnailSize(2480, 3508)).toEqual({ width: 192, height: 272 });
    // Lo que ya es pequeño no se toca (ni se amplía).
    expect(thumbnailSize(180, 90)).toBeNull();
    expect(thumbnailSize(192, 96)).toBeNull();
  });

  it("da a <time> la fecha en ISO con zona y no falla con una fecha ilegible", () => {
    expect(isoUtc("2026-10-22T20:15:00")).toBe("2026-10-22T20:15:00.000Z");
    expect(isoUtc("no-es-fecha")).toBe("no-es-fecha");
  });

  it("formatea la fecha en la hora local y en español, y traduce el estado", () => {
    // Las pruebas corren con TZ=America/Bogota (UTC-5, vite.config.ts).
    expect(formatTime("2026-10-22T20:15:00")).toBe("15:15");
    expect(formatDay("2026-10-23T02:00:00")).toBe("22 oct 2026");
    expect(statusLabel("transcribed")).toBe("Transcrita");
    expect(statusLabel("finalized")).toBe("Finalizada");
  });
});

describe("limitador de descargas", () => {
  it("no pasa del máximo y una tarea cancelada en espera no ocupa hueco", async () => {
    const limit = createLimiter(2);
    const gates = [deferred<string>(), deferred<string>(), deferred<string>(), deferred<string>()];
    const started: number[] = [];
    const task = (i: number) => () => {
      started.push(i);
      return gates[i]?.promise ?? Promise.reject(new Error("sin puerta"));
    };
    const cancelled = new AbortController();

    const results = [
      limit(task(0)),
      limit(task(1)),
      limit(task(2), cancelled.signal),
      limit(task(3)),
    ];
    cancelled.abort();
    await expect(results[2]).rejects.toMatchObject({ kind: "aborted" });
    expect(started).toEqual([0, 1]);

    gates[0]?.resolve("a");
    await results[0];
    await vi.waitFor(() => {
      expect(started).toEqual([0, 1, 3]);
    });
    gates[1]?.resolve("b");
    gates[3]?.resolve("d");
    await expect(Promise.all([results[1], results[3]])).resolves.toEqual(["b", "d"]);
  });

  it("la actualización del listado espera también a una petición en pausa por falta de red", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    // Montado, como lo deja QueryClientProvider: así atiende a los cambios de conexión.
    client.mount();
    onlineManager.setOnline(false);
    try {
      void client.query({ queryKey: SESSIONS_QUERY_KEY, queryFn: () => Promise.resolve([]) });
      expect(client.getQueryCache().find({ queryKey: SESSIONS_QUERY_KEY })?.state.fetchStatus).toBe(
        "paused",
      );
      const invalidate = vi.spyOn(client, "invalidateQueries");

      refreshSessions(client);
      expect(invalidate).not.toHaveBeenCalled();

      onlineManager.setOnline(true);
      await vi.waitFor(() => {
        expect(invalidate).toHaveBeenCalledOnce();
      });
    } finally {
      onlineManager.setOnline(true);
      client.clear();
      client.unmount();
    }
  });
});

describe("reducción de miniaturas", () => {
  function bitmap(width: number, height: number) {
    return { width, height, close: vi.fn() };
  }

  function stubCanvas(context: { drawImage: (...args: unknown[]) => void } | null) {
    const small = new Blob(["pequeña"], { type: "image/png" });
    vi.stubGlobal(
      "OffscreenCanvas",
      class {
        constructor(
          readonly width: number,
          readonly height: number,
        ) {}
        getContext() {
          return context;
        }
        convertToBlob() {
          return Promise.resolve(small);
        }
      },
    );
    return small;
  }

  it("dibuja la imagen al tamaño reducido y cierra los dos bitmaps", async () => {
    const full = bitmap(1200, 200);
    const reduced = bitmap(576, 96);
    vi.stubGlobal(
      "createImageBitmap",
      vi.fn().mockResolvedValueOnce(full).mockResolvedValueOnce(reduced),
    );
    const drawImage = vi.fn();
    const small = stubCanvas({ drawImage });
    const original = new Blob(["original"], { type: "image/png" });

    await expect(shrinkForThumbnail(original)).resolves.toBe(small);

    expect(drawImage).toHaveBeenCalledWith(reduced, 0, 0, 576, 96);
    expect(full.close).toHaveBeenCalledOnce();
    expect(reduced.close).toHaveBeenCalledOnce();
  });

  it("si algo falla a mitad, devuelve la original sin dejar bitmaps abiertos", async () => {
    const original = new Blob(["original"], { type: "image/png" });

    const full = bitmap(1200, 200);
    vi.stubGlobal(
      "createImageBitmap",
      vi.fn().mockResolvedValueOnce(full).mockRejectedValueOnce(new Error("sin memoria")),
    );
    stubCanvas({ drawImage: vi.fn() });
    await expect(shrinkForThumbnail(original)).resolves.toBe(original);
    expect(full.close).toHaveBeenCalledOnce();

    const full2 = bitmap(1200, 200);
    const reduced = bitmap(576, 96);
    vi.stubGlobal(
      "createImageBitmap",
      vi.fn().mockResolvedValueOnce(full2).mockResolvedValueOnce(reduced),
    );
    stubCanvas(null);
    await expect(shrinkForThumbnail(original)).resolves.toBe(original);
    expect(full2.close).toHaveBeenCalledOnce();
    expect(reduced.close).toHaveBeenCalledOnce();
  });
});
