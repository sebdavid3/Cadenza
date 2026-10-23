import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createApiClient } from "../../api/client";
import { TRANSCRIBE_TIMEOUT_MS } from "../../api/config";
import { jsonResponse, mockApi } from "../../test/auth-helpers";
import { MAX_UPLOAD_BYTES, precheck, useQueueStore } from "./queue";
import { formatDate, parseUtc, statusLabel } from "./sessions";

const api = createApiClient({ baseUrl: "/api" });

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

beforeEach(() => {
  useQueueStore.setState({ items: [], running: false, ownerId: null });
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
  it("envía las imágenes de una en una, como multipart con el campo file y 30 s de timeout", async () => {
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
    const transcribedIds: string[] = [];
    const store = useQueueStore.getState();
    store.add([png("a.png"), png("b.png"), png("c.png")]);

    await store.run(api, (result) => transcribedIds.push(result.session_id));

    expect(maxInFlight).toBe(1);
    expect(transcribedIds).toEqual(["s1", "s2", "s3"]);
    expect(useQueueStore.getState().items.map((item) => item.status)).toEqual([
      "done",
      "done",
      "done",
    ]);
    const body = calls[0]?.init?.body;
    expect(body).toBeInstanceOf(FormData);
    expect((body as FormData).get("file")).toBeInstanceOf(File);
    expect([...(body as FormData).keys()]).toEqual(["file"]);
    expect(TRANSCRIBE_TIMEOUT_MS).toBe(30_000);
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

  it("ante un 401 se detiene y deja el resto en cola", async () => {
    mockApi({ "POST /transcribe": () => jsonResponse({ detail: "Not authenticated" }, 401) });
    const store = useQueueStore.getState();
    store.add([png("a.png"), png("b.png")]);

    await store.run(api);

    expect(useQueueStore.getState().items.map((item) => item.status)).toEqual(["error", "queued"]);
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

  it("vacía la cola si entra otra persona en la pestaña", () => {
    const store = useQueueStore.getState();
    store.claim("ana");
    store.add([png()]);
    store.claim("ana");
    expect(useQueueStore.getState().items).toHaveLength(1);

    store.claim("bruno");
    expect(useQueueStore.getState().items).toHaveLength(0);
  });
});

describe("datos de sesiones", () => {
  it("interpreta created_at sin zona horaria como UTC", () => {
    expect(parseUtc("2026-10-22T20:15:00").toISOString()).toBe("2026-10-22T20:15:00.000Z");
    expect(parseUtc("2026-10-22T20:15:00Z").toISOString()).toBe("2026-10-22T20:15:00.000Z");
    expect(parseUtc("2026-10-22T20:15:00+02:00").toISOString()).toBe("2026-10-22T18:15:00.000Z");
  });

  it("formatea la fecha en español y traduce el estado", () => {
    expect(formatDate("2026-10-22T20:15:00")).toMatch(/2026/);
    expect(statusLabel("transcribed")).toBe("Transcrita");
    expect(statusLabel("finalized")).toBe("Finalizada");
  });
});
