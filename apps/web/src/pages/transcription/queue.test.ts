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
import { doneJob, job, mockApiWithInstantJobs } from "../../test/jobs";
import type { UserRead } from "../../types";
import {
  forget,
  hasPendingWork,
  INTERRUPTED_MESSAGE,
  JOB_POLLING,
  MAX_UPLOAD_BYTES,
  precheck,
  readRemembered,
  remember,
  useQueueStore,
} from "./queue";
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
  JOB_POLLING.intervalMs = 1000;
  localStorage.clear();
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
    const { calls } = mockApiWithInstantJobs({
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
    JOB_POLLING.intervalMs = 1;
    const started = "2026-11-09T10:00:01Z";
    const done = deferred<Response>();
    mockApi({
      "POST /transcription-jobs": () =>
        jsonResponse(job({ id: "j1", stage: "detecting", ahead: null, started_at: started }), 202),
      "GET /transcription-jobs": () => done.promise,
    });
    const store = useQueueStore.getState();
    store.add([png()]);

    const running = store.run(api);
    await vi.waitFor(() => {
      expect(statuses()).toEqual(["transcribing"]);
    });
    expect(useQueueStore.getState().items[0]?.startedAt).toBe(Date.parse(started));

    done.resolve(jsonResponse([doneJob(transcribed("j1"))]));
    await running;
    expect(statuses()).toEqual(["done"]);
  });

  it("acepta imágenes nuevas con la cola en marcha y las sube en el mismo recorrido", async () => {
    const first = deferred<Response>();
    let n = 0;
    const { calls } = mockApiWithInstantJobs({
      "POST /transcribe": () => {
        n += 1;
        return n === 1 ? first.promise : jsonResponse(transcribed(`s${String(n)}`), 201);
      },
    });
    const store = useQueueStore.getState();
    store.add([png("a.png")]);

    const running = store.run(api);
    store.add([png("b.png"), png("c.png")]);
    // Mientras sube, sigue en cola: aún no tiene transcripción en el servidor.
    expect(statuses()).toEqual(["queued", "queued", "queued"]);
    expect(useQueueStore.getState().items[0]?.uploading).toBe(true);
    // Una segunda llamada mientras corre no abre otro recorrido en paralelo.
    await store.run(api);
    first.resolve(jsonResponse(transcribed("s1"), 201));
    await running;

    expect(statuses()).toEqual(["done", "done", "done"]);
    expect(calls).toHaveLength(3);
  });

  it("la subida tiene su plazo, y si vence dice que se compruebe la conexión", async () => {
    vi.useFakeTimers();
    mockApi({ "POST /transcription-jobs": hangUntilAborted });
    const store = useQueueStore.getState();
    store.add([png()]);

    const running = store.run(api);
    await vi.advanceTimersByTimeAsync(119_999);
    expect(statuses()).toEqual(["queued"]);

    await vi.advanceTimersByTimeAsync(1);
    await running;
    const [item] = useQueueStore.getState().items;
    expect(item?.status).toBe("error");
    expect(item?.error).toMatch(/la subida tardó demasiado/i);
    expect(item?.error).not.toMatch(/30 s/);
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
    mockApiWithInstantJobs({
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
    const { fetchMock } = mockApiWithInstantJobs({});
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
      mockApiWithInstantJobs({
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

  it("con la cola del servidor llena (503), las imágenes esperan sin error y se suben después", async () => {
    vi.useFakeTimers();
    let n = 0;
    const { calls } = mockApiWithInstantJobs({
      "POST /transcribe": () => {
        n += 1;
        return n === 1
          ? new Response(JSON.stringify({ detail: "en bruto" }), {
              status: 503,
              headers: { "Content-Type": "application/json", "Retry-After": "60" },
            })
          : jsonResponse(transcribed(`s${String(n)}`), 201);
      },
    });
    const store = useQueueStore.getState();
    store.add([png("a.png")]);

    const running = store.run(api);
    await vi.advanceTimersByTimeAsync(0);
    expect(statuses()).toEqual(["queued"]);
    expect(useQueueStore.getState()).toMatchObject({ hold: "queue-full", paused: false });

    await vi.advanceTimersByTimeAsync(60_000);
    await running;
    expect(statuses()).toEqual(["done"]);
    expect(useQueueStore.getState().hold).toBeNull();
    expect(calls.filter((call) => call.key === "POST /transcription-jobs")).toHaveLength(2);
  });

  it.each([
    ["un fallo de red", () => Promise.reject(new TypeError("Failed to fetch"))],
    ["un 502", () => jsonResponse({ detail: "x" }, 502)],
  ])("con %s se pausa, deja el resto en cola y sigue al reanudar", async (_label, failure) => {
    let n = 0;
    const { calls } = mockApiWithInstantJobs({
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
    mockApiWithInstantJobs({
      "POST /transcribe": () => Promise.reject(new TypeError("Failed to fetch")),
    });
    const store = useQueueStore.getState();
    const pause = async () => {
      store.add([png()]);
      await store.run(api);
      expect(useQueueStore.getState().paused).toBe(true);
    };

    await pause();
    const failed = useQueueStore.getState().items.at(-1);
    store.retry(failed?.id ?? "", api);
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
    mockApiWithInstantJobs({
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
    const { calls } = mockApiWithInstantJobs({
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
    const { calls } = mockApiWithInstantJobs({ "POST /transcribe": () => first.promise });
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
    const { calls } = mockApiWithInstantJobs({
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
    const { calls } = mockApiWithInstantJobs({
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
    mockApiWithInstantJobs({
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
    const { calls } = mockApiWithInstantJobs({
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
    mockApiWithInstantJobs({
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
    void store.remove(second.id, api);
    await store.run(api);
    expect(useQueueStore.getState().items).toHaveLength(1);
    expect(useQueueStore.getState().items[0]?.status).toBe("error");

    store.retry(first.id, api);
    await store.run(api);
    expect(useQueueStore.getState().items[0]?.status).toBe("done");

    store.clearFinished(api);
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

describe("transcripción en segundo plano (#375)", () => {
  beforeEach(() => {
    JOB_POLLING.intervalMs = 1;
  });

  /** Las respuestas de `GET /transcription-jobs`, una por consulta; la última se repite. */
  function listings(...responses: unknown[][]) {
    let n = 0;
    return () => jsonResponse(responses[Math.min(n++, responses.length - 1)]);
  }

  it("sube la imagen, recibe su trabajo enseguida y sigue su avance hasta la sesión", async () => {
    const seen: unknown[] = [];
    const reading = (staff: number, staffs: number, kind: "first" | "piano" = "first") =>
      job({ id: "j1", stage: "reading", ahead: null, reading: kind, staff, staffs });
    mockApi({
      "POST /transcription-jobs": () => jsonResponse(job({ id: "j1", ahead: 2 }), 202),
      "GET /transcription-jobs": listings(
        [job({ id: "j1", ahead: 1 })],
        [job({ id: "j1", stage: "detecting", ahead: null, reading: "first" })],
        [reading(1, 3)],
        [reading(3, 3)],
        [job({ id: "j1", stage: "detecting", ahead: null, reading: "piano" })],
        [reading(2, 4, "piano")],
        [job({ id: "j1", stage: "reviewing", ahead: null })],
        [doneJob(transcribed("j1", 2))],
      ),
    });
    const unsubscribe = useQueueStore.subscribe((state) => {
      const [item] = state.items;
      if (item?.job) seen.push([item.status, item.job.stage, item.job.ahead, item.job.staff]);
    });
    const settled = vi.fn();
    const store = useQueueStore.getState();
    store.add([png()]);

    await store.run(api, settled);
    unsubscribe();

    expect(seen).toContainEqual(["queued", "queued", 2, null]);
    expect(seen).toContainEqual(["queued", "queued", 1, null]);
    expect(seen).toContainEqual(["transcribing", "detecting", null, null]);
    expect(seen).toContainEqual(["transcribing", "reading", null, 3]);
    expect(seen).toContainEqual(["transcribing", "reviewing", null, null]);
    expect(useQueueStore.getState().items[0]).toMatchObject({
      status: "done",
      result: { session_id: "j1", findings_count: 2 },
    });
    // El listado se actualiza una vez, cuando la transcripción termina.
    expect(settled).toHaveBeenCalledTimes(1);
    // Vista terminar, ya no se apunta.
    expect(readRemembered(ANA.id)).toEqual([]);
  });

  it("una transcripción fallida dice por qué con sus palabras", async () => {
    mockApi({
      "POST /transcription-jobs": () => jsonResponse(job({ id: "j1" }), 202),
      "GET /transcription-jobs": listings([
        job({ id: "j1", stage: "failed", ahead: null, failure: "unreadable" }),
      ]),
    });
    const store = useQueueStore.getState();
    store.add([png()]);

    await store.run(api);

    expect(useQueueStore.getState().items[0]).toMatchObject({
      status: "error",
      error: "No se reconoció ninguna partitura en la imagen.",
    });
  });

  it("si el servidor se reinicia y la transcripción desaparece, dice que se interrumpió", async () => {
    mockApi({
      "POST /transcription-jobs": () => jsonResponse(job({ id: "j1" }), 202),
      "GET /transcription-jobs": listings([]),
      "GET /sessions/j1": () => jsonResponse({ detail: "no" }, 404),
    });
    const store = useQueueStore.getState();
    store.add([png("perdida.png")]);

    await store.run(api);

    expect(useQueueStore.getState().items[0]).toMatchObject({
      status: "error",
      interrupted: true,
      error: INTERRUPTED_MESSAGE,
    });
    expect(INTERRUPTED_MESSAGE).toMatch(/se interrumpió.*vuelve a subirla/i);
    expect(useQueueStore.getState().running).toBe(false);
  });

  it("si desaparece pero ya había creado su sesión, queda lista", async () => {
    mockApi({
      "POST /transcription-jobs": () => jsonResponse(job({ id: "j1" }), 202),
      "GET /transcription-jobs": listings([]),
      "GET /sessions/j1": () =>
        jsonResponse({
          session_id: "j1",
          document_id: "doc-j1",
          omr_engine: "homr",
          findings: [{}, {}],
          edits: [],
          condition: "assisted",
          test_score_id: null,
        }),
    });
    const store = useQueueStore.getState();
    store.add([png()]);

    await store.run(api);

    expect(useQueueStore.getState().items[0]).toMatchObject({
      status: "done",
      result: { session_id: "j1", findings_count: 2 },
    });
  });

  it("con el tope de la persona (429), las demás esperan sin error y se suben al terminar una", async () => {
    let posts = 0;
    let finishedFirst = false;
    mockApi({
      "POST /transcription-jobs": () => {
        posts += 1;
        if (posts === 2 && !finishedFirst) return jsonResponse({ detail: "tope" }, 429);
        return jsonResponse(job({ id: `j${String(posts)}` }), 202);
      },
      "GET /transcription-jobs": () => {
        finishedFirst = true;
        return jsonResponse([
          doneJob(transcribed("j1")),
          ...(posts >= 3 ? [doneJob(transcribed("j3"))] : []),
        ]);
      },
    });
    const holds: unknown[] = [];
    const unsubscribe = useQueueStore.subscribe((state) => holds.push(state.hold));
    const store = useQueueStore.getState();
    store.add([png("a.png"), png("b.png")]);

    await store.run(api);
    unsubscribe();

    expect(holds).toContain("own-limit");
    expect(statuses()).toEqual(["done", "done"]);
    expect(useQueueStore.getState().hold).toBeNull();
  });

  it("quitar una en cola la retira del servidor; si ya empezó, se queda", async () => {
    const deletes: string[] = [];
    let conflict = false;
    mockApi({
      "DELETE /transcription-jobs/j1": () => {
        deletes.push("j1");
        return conflict ? jsonResponse({ detail: "ya" }, 409) : new Response(null, { status: 204 });
      },
    });
    const store = useQueueStore.getState();
    useQueueStore.setState({
      items: [{ id: "a", name: "a.png", status: "queued", job: job({ id: "j1", ahead: 1 }) }],
    });

    conflict = true;
    await store.remove("a", api);
    expect(useQueueStore.getState().items).toHaveLength(1);

    conflict = false;
    await store.remove("a", api);
    expect(useQueueStore.getState().items).toHaveLength(0);
    expect(deletes).toEqual(["j1", "j1"]);
  });

  it("al volver a la vista, recupera las suyas del servidor y dice cuáles se interrumpieron", async () => {
    remember(ANA.id, { id: "perdida", name: "perdida.png" });
    remember(ANA.id, { id: "creada", name: "creada.png" });
    mockApi({
      "GET /transcription-jobs": () =>
        jsonResponse([
          job({
            id: "j1",
            stage: "reading",
            ahead: null,
            reading: "first",
            staff: 2,
            staffs: 5,
            source_filename: "TS-02.png",
            title: "Lied",
            started_at: "2026-11-09T10:00:01Z",
          }),
          job({ id: "j2", stage: "failed", ahead: null, failure: "internal" }),
          doneJob(transcribed("j3")),
        ]),
      "GET /sessions/perdida": () => jsonResponse({ detail: "no" }, 404),
      "GET /sessions/creada": () =>
        jsonResponse({
          session_id: "creada",
          document_id: "d",
          omr_engine: "homr",
          findings: [],
          edits: [],
          condition: "assisted",
        }),
    });

    await useQueueStore.getState().restore(api);

    const items = useQueueStore.getState().items;
    // Las listas ya están en el diario: no vuelven a la cola.
    expect(items.map((item) => [item.name, item.status])).toEqual([
      ["TS-02.png", "transcribing"],
      ["pagina.png", "error"],
      ["perdida.png", "error"],
    ]);
    expect(items[0]?.title).toBe("Lied");
    expect(items[0]?.file).toBeUndefined();
    expect(items[1]?.error).toMatch(/algo falló en el servidor/i);
    expect(items[2]).toMatchObject({ interrupted: true, error: INTERRUPTED_MESSAGE });
    // Ya se sabe cómo acabaron las apuntadas: no se vuelven a buscar.
    expect(readRemembered(ANA.id)).toEqual([]);
  });

  it("lo apuntado es de cada persona y se olvida al terminar", () => {
    remember(ANA.id, { id: "j1", name: "a.png" });
    remember("otra", { id: "j2", name: "b.png" });

    forget(ANA.id, ["j1"]);

    expect(readRemembered(ANA.id)).toEqual([]);
    expect(readRemembered("otra")).toEqual([{ id: "j2", name: "b.png" }]);
  });

  it("solo avisa al salir si quedan imágenes sin subir", () => {
    useQueueStore.setState({
      items: [
        {
          id: "a",
          name: "a.png",
          status: "transcribing",
          job: job({ id: "j1", stage: "reading" }),
        },
      ],
    });
    expect(hasPendingWork(useQueueStore.getState().items)).toBe(false);
    useQueueStore.getState().add([png("b.png")]);
    expect(hasPendingWork(useQueueStore.getState().items)).toBe(true);
  });
});

describe("preparar el lote antes de transcribir (#240)", () => {
  const sent = (body: unknown) =>
    [...(body as FormData).entries()].map(([key, value]) => [
      key,
      typeof value === "string" ? value : value.name,
    ]);

  it("lo elegido espera a «Transcribir» con los datos comunes o los de cada imagen", async () => {
    const { calls } = mockApiWithInstantJobs({
      "POST /transcribe": () => jsonResponse(transcribed(`s${String(calls.length)}`), 201),
    });
    const store = useQueueStore.getState();
    store.prepare([png("a.png"), png("b.png"), png("c.png")]);

    // Preparar no envía nada ni pone nada en la cola.
    expect(useQueueStore.getState().items).toEqual([]);
    const [a, b] = useQueueStore.getState().prepared;
    if (!a || !b) throw new Error("faltan imágenes preparadas");
    store.setCommon({
      title: "",
      composer: "Schumann",
      parts: [
        { instrument: "voice", name: "" },
        { instrument: "piano", name: "" },
      ],
    });
    store.setOwn(b.id, {
      title: "Mondnacht",
      composer: "",
      parts: [
        { instrument: "other", name: "Arpa" },
        { instrument: "", name: "" },
      ],
    });
    store.submitPrepared();

    const state = useQueueStore.getState();
    expect(state.prepared).toEqual([]);
    // Tras enviar, el formulario vuelve a sus valores por defecto.
    expect(state.common).toEqual({
      title: "",
      composer: "",
      parts: [
        { instrument: "", name: "" },
        { instrument: "", name: "" },
      ],
    });
    expect(statuses()).toEqual(["queued", "queued", "queued"]);
    await store.run(api);

    expect(calls.map((call) => sent(call.init?.body))).toEqual([
      [
        ["file", "a.png"],
        ["composer", "Schumann"],
        ["instruments", "voice"],
        ["part_names", ""],
        ["instruments", "piano"],
        ["part_names", ""],
      ],
      [
        ["file", "b.png"],
        ["title", "Mondnacht"],
        ["instruments", "other"],
        ["part_names", "Arpa"],
      ],
      [
        ["file", "c.png"],
        ["composer", "Schumann"],
        ["instruments", "voice"],
        ["part_names", ""],
        ["instruments", "piano"],
        ["part_names", ""],
      ],
    ]);
  });

  it("lo rechazado en la comprobación previa va a la cola como rechazado, sin prepararse", () => {
    const store = useQueueStore.getState();
    store.prepare([new File(["x"], "notas.txt", { type: "text/plain" }), png("a.png")]);

    expect(useQueueStore.getState().prepared.map((item) => item.file.name)).toEqual(["a.png"]);
    expect(useQueueStore.getState().items).toMatchObject([
      { status: "error", rejected: true, file: { name: "notas.txt" } },
    ]);
  });

  it("quitar una imagen o descartar el lote no envía nada; volver a los datos comunes", () => {
    const store = useQueueStore.getState();
    store.prepare([png("a.png"), png("b.png")]);
    const [a, b] = useQueueStore.getState().prepared;
    if (!a || !b) throw new Error("faltan imágenes preparadas");
    store.setOwn(b.id, { title: "Propio", composer: "", parts: [] });
    store.setOwn(b.id, null);
    expect(useQueueStore.getState().prepared[1]?.own).toBeNull();

    store.unprepare(a.id);
    expect(useQueueStore.getState().prepared.map((item) => item.file.name)).toEqual(["b.png"]);
    store.setCommon({ title: "x", composer: "", parts: [] });
    store.discardPrepared();
    expect(useQueueStore.getState().prepared).toEqual([]);
    expect(useQueueStore.getState().common.title).toBe("");
    expect(useQueueStore.getState().items).toEqual([]);
  });

  it("si el lote queda en una imagen con datos propios, esos pasan a ser los que se ven", () => {
    const store = useQueueStore.getState();
    store.prepare([png("uno.png"), png("dos.png")]);
    const [uno, dos] = useQueueStore.getState().prepared;
    if (!uno || !dos) throw new Error("faltan imágenes preparadas");
    store.setCommon({ title: "", composer: "Clara", parts: [] });
    const own = {
      title: "Romanze",
      composer: "",
      parts: [{ instrument: "violin" as const, name: "" }],
    };
    store.setOwn(dos.id, own);
    store.unprepare(uno.id);

    // Con una sola imagen el recuadro enseña los comunes: son los suyos, y no quedan ocultos.
    expect(useQueueStore.getState().common).toEqual(own);
    expect(useQueueStore.getState().prepared[0]?.own).toBeNull();
  });

  it("quitar la última imagen deja el formulario con sus valores por defecto", () => {
    const store = useQueueStore.getState();
    store.prepare([png("uno.png")]);
    store.setCommon({ title: "Mondnacht", composer: "", parts: [] });
    const [uno] = useQueueStore.getState().prepared;
    if (!uno) throw new Error("falta la imagen preparada");
    store.unprepare(uno.id);

    expect(useQueueStore.getState().prepared).toEqual([]);
    expect(useQueueStore.getState().common.title).toBe("");
  });

  it("enviar el lote quita la pausa", () => {
    const store = useQueueStore.getState();
    useQueueStore.setState({ paused: true });
    store.prepare([png("a.png")]);
    expect(useQueueStore.getState().paused).toBe(true);
    store.submitPrepared();
    expect(useQueueStore.getState().paused).toBe(false);
  });

  it("si entra otra persona, lo preparado y sus datos se olvidan", () => {
    const store = useQueueStore.getState();
    store.prepare([png("a.png")]);
    store.setCommon({ title: "Mondnacht", composer: "", parts: [] });
    useAuthStore.getState().signOut("expired");
    signInAs(ANA);
    expect(useQueueStore.getState().prepared).toHaveLength(1);

    signInAs(BRUNO);
    expect(useQueueStore.getState().prepared).toEqual([]);
    expect(useQueueStore.getState().common.title).toBe("");
  });
});

describe("datos de sesiones", () => {
  it("interpreta created_at sin zona horaria como UTC", () => {
    expect(parseUtc("2026-10-22T20:15:00").toISOString()).toBe("2026-10-22T20:15:00.000Z");
    expect(parseUtc("2026-10-22T20:15:00Z").toISOString()).toBe("2026-10-22T20:15:00.000Z");
    expect(parseUtc("2026-10-22T20:15:00+02:00").toISOString()).toBe("2026-10-22T18:15:00.000Z");
  });

  it("reduce la miniatura lo justo para cubrir la imagen de una lámina del diario (#370)", () => {
    // Un incipit apaisado manda la altura; una página escaneada, la anchura.
    expect(thumbnailSize(3000, 500)).toEqual({ width: 1920, height: 320 });
    expect(thumbnailSize(2480, 3508)).toEqual({ width: 480, height: 679 });
    // Lo que ya es pequeño no se toca (ni se amplía).
    expect(thumbnailSize(400, 300)).toBeNull();
    expect(thumbnailSize(480, 320)).toBeNull();
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
    const full = bitmap(3000, 500);
    const reduced = bitmap(1920, 320);
    vi.stubGlobal(
      "createImageBitmap",
      vi.fn().mockResolvedValueOnce(full).mockResolvedValueOnce(reduced),
    );
    const drawImage = vi.fn();
    const small = stubCanvas({ drawImage });
    const original = new Blob(["original"], { type: "image/png" });

    await expect(shrinkForThumbnail(original)).resolves.toBe(small);

    expect(drawImage).toHaveBeenCalledWith(reduced, 0, 0, 1920, 320);
    expect(full.close).toHaveBeenCalledOnce();
    expect(reduced.close).toHaveBeenCalledOnce();
  });

  it("si algo falla a mitad, devuelve la original sin dejar bitmaps abiertos", async () => {
    const original = new Blob(["original"], { type: "image/png" });

    const full = bitmap(3000, 500);
    vi.stubGlobal(
      "createImageBitmap",
      vi.fn().mockResolvedValueOnce(full).mockRejectedValueOnce(new Error("sin memoria")),
    );
    stubCanvas({ drawImage: vi.fn() });
    await expect(shrinkForThumbnail(original)).resolves.toBe(original);
    expect(full.close).toHaveBeenCalledOnce();

    const full2 = bitmap(3000, 500);
    const reduced = bitmap(1920, 320);
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
