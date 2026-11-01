import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiClient } from "../../api/client";
import { ApiError } from "../../api/errors";
import { EFFORT_IDLE_THRESHOLD_MS } from "../../config";
import type { EffortSegmentUpdate } from "../../types";
import { EFFORT_FLUSH_INTERVAL_MS, EffortMeter, useEffortMeter } from "./effort";

const SESSION = "sesion-1";
const MINUTE = 60_000;

interface Sent {
  segmentId: string;
  body: EffortSegmentUpdate;
  keepalive: boolean;
}

/** Un reloj que avanza a mano y un envío que se apunta (y que puede fallar). */
function harness(options: { fail?: () => Error | undefined } = {}) {
  let t = 0;
  const sent: Sent[] = [];
  const send = vi.fn((segmentId: string, body: EffortSegmentUpdate, keepalive: boolean) => {
    sent.push({ segmentId, body, keepalive });
    const error = options.fail?.();
    return error ? Promise.reject(error) : Promise.resolve({});
  });
  const meter = () => new EffortMeter({ sessionId: SESSION, send, now: () => t });
  return {
    sent,
    send,
    meter,
    advance(ms: number) {
      t += ms;
    },
  };
}

/** Una medición en marcha: quien la transcribió, con la página a la vista. */
function running(h: ReturnType<typeof harness>) {
  const meter = h.meter();
  meter.attach(true);
  meter.setMeasuring(true);
  return meter;
}

beforeEach(() => {
  sessionStorage.clear();
});

describe("EffortMeter (#188, ADR-0050)", () => {
  it("envía el tiempo del tramo con el umbral con que se midió", async () => {
    const h = harness();
    const meter = running(h);
    await meter.flush(); // el tramo vacío, al empezar
    h.advance(30_000);
    meter.activity();
    h.advance(5_000);

    expect(await meter.flush()).toBe("saved");

    expect(h.sent.at(-1)?.body).toEqual({
      active_ms: 35_000,
      first_edit_ms: null,
      idle_threshold_ms: EFFORT_IDLE_THRESHOLD_MS,
    });
    expect(h.sent.at(-1)?.keepalive).toBe(false);
  });

  it("ocultar la pestaña no suma tiempo, y al ocultarla se envía con keepalive", () => {
    const h = harness();
    const meter = running(h);
    h.advance(10_000);
    meter.activity();

    meter.setVisible(false);
    expect(h.sent.at(-1)).toMatchObject({ body: { active_ms: 10_000 }, keepalive: true });
    h.advance(10 * MINUTE); // oculta: nada
    meter.activity(); // un evento en segundo plano tampoco
    meter.setVisible(true);
    h.advance(20_000);
    meter.activity();

    expect(meter.activeMs()).toBe(30_000);
  });

  it("de una pausa sin actividad más larga que el umbral solo cuenta el umbral", () => {
    const h = harness();
    const meter = running(h);
    h.advance(15 * MINUTE);
    meter.activity();
    expect(meter.activeMs()).toBe(EFFORT_IDLE_THRESHOLD_MS);
  });

  it("una recarga sigue el mismo tramo desde lo medido", async () => {
    const h = harness();
    const first = running(h);
    h.advance(30_000);
    first.activity();
    first.detach(); // la página se recarga

    const second = running(h);
    h.advance(10_000);
    second.activity();
    await second.flush();

    const ids = new Set(h.sent.map((s) => s.segmentId));
    expect(ids.size).toBe(1);
    expect(h.sent.at(-1)?.body.active_ms).toBe(40_000);
  });

  it("sin sessionStorage legible, otra carga es otro tramo", async () => {
    const h = harness();
    const first = running(h);
    h.advance(1_000);
    await first.flush();
    sessionStorage.setItem(`cadenza:effort:${SESSION}`, "{roto");

    const second = running(h);
    await second.flush();

    expect(new Set(h.sent.map((s) => s.segmentId)).size).toBe(2);
    expect(h.sent.at(-1)?.body.active_ms).toBe(0);
  });

  it("apunta la primera edición del log (seq 1) y la envía al momento", async () => {
    const h = harness();
    const meter = running(h);
    h.advance(12_000);
    meter.activity();

    meter.saved(1);
    await vi.waitFor(() => {
      expect(h.sent.at(-1)?.body.first_edit_ms).toBe(12_000);
    });
    h.advance(3_000);
    meter.activity();
    meter.saved(2);
    meter.saved(1); // una recarga de un estado posterior no la cambia
    await meter.flush();

    expect(h.sent.at(-1)?.body).toMatchObject({ active_ms: 15_000, first_edit_ms: 12_000 });
  });

  it("finalizar para el reloj y envía lo medido; si no se finaliza, sigue", async () => {
    const h = harness();
    const meter = running(h);
    h.advance(20_000);
    meter.activity();

    expect(await meter.finish()).toBe("saved");
    expect(h.sent.at(-1)?.body.active_ms).toBe(20_000);
    h.advance(30_000); // finalizando: no cuenta
    meter.activity();
    expect(meter.activeMs()).toBe(20_000);

    meter.resume();
    h.advance(5_000);
    meter.activity();
    expect(meter.activeMs()).toBe(25_000);
  });

  it("dice si el envío antes de finalizar falló sin respuesta o lo rechazó el servidor", async () => {
    let error: Error | undefined = new ApiError("network");
    const h = harness({ fail: () => error });
    const meter = running(h);
    h.advance(1_000);
    meter.activity();

    expect(await meter.finish()).toBe("failed");
    meter.resume();
    h.advance(1_000);
    meter.activity();
    error = new ApiError("conflict", 409);
    expect(await meter.finish()).toBe("refused");
  });

  it("tras un rechazo no vuelve a enviar hasta que se vuelve a medir (reabrir)", async () => {
    let error: Error | undefined = new ApiError("conflict", 409);
    const h = harness({ fail: () => error });
    const meter = running(h);
    h.advance(1_000);
    meter.activity();
    expect(await meter.flush()).toBe("refused");
    const count = h.sent.length;
    h.advance(1_000);
    meter.activity();
    expect(await meter.flush()).toBe("refused");
    meter.setVisible(false);
    expect(h.sent).toHaveLength(count);

    // Tras el rechazo tampoco cuenta: lo de después no es corrección.
    expect(meter.activeMs()).toBe(1_000);
    h.advance(5_000);
    meter.setVisible(true);
    meter.activity();
    expect(meter.activeMs()).toBe(1_000);

    error = undefined;
    meter.setMeasuring(false); // finalizada
    meter.setMeasuring(true); // reabierta
    await vi.waitFor(() => {
      expect(h.sent.length).toBeGreaterThan(count);
    });
  });

  it("sin medir (otra persona, o finalizada) ni cuenta ni envía", async () => {
    const h = harness();
    const meter = h.meter();
    meter.attach(true);
    h.advance(30_000);
    meter.activity();

    expect(await meter.flush()).toBe("saved");
    expect(await meter.finish()).toBe("saved");
    meter.setVisible(false);
    meter.detach();

    expect(h.send).not.toHaveBeenCalled();
    expect(meter.activeMs()).toBe(0);
  });

  it("no repite un envío igual, y envía de uno en uno", async () => {
    let release: () => void = () => undefined;
    const h = harness();
    h.send.mockImplementationOnce((segmentId, body, keepalive) => {
      h.sent.push({ segmentId, body, keepalive });
      return new Promise((resolve) => {
        release = () => {
          resolve({});
        };
      });
    });
    const meter = running(h); // el primer envío queda pendiente
    h.advance(1_000);
    meter.activity();
    const second = meter.flush();
    await Promise.resolve();
    expect(h.sent).toHaveLength(1);

    release();
    await second;
    expect(h.sent).toHaveLength(2);
    await meter.flush();
    expect(h.sent).toHaveLength(2);
  });
});

describe("useEffortMeter", () => {
  const visibility = { state: "visible" as DocumentVisibilityState };

  beforeEach(() => {
    vi.useFakeTimers({
      toFake: ["setInterval", "clearInterval", "setTimeout", "clearTimeout", "performance"],
    });
    visibility.state = "visible";
    vi.spyOn(document, "visibilityState", "get").mockImplementation(() => visibility.state);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  function setup(measuring = true) {
    const request = vi.fn((path: string, options: unknown) => Promise.resolve({ path, options }));
    const api = { request } as unknown as ApiClient;
    const hook = renderHook(({ on }) => useEffortMeter(api, SESSION, on), {
      initialProps: { on: measuring },
    });
    const bodies = () =>
      request.mock.calls.map(([path, options]) => ({
        path,
        ...(options as { json: EffortSegmentUpdate; keepalive: boolean; method: string }),
      }));
    return { hook, request, bodies };
  }

  function move() {
    window.dispatchEvent(new Event("pointermove"));
  }

  it("envía cada tanto lo medido con la actividad de la página", async () => {
    const { bodies } = setup();
    for (let i = 0; i < 4; i += 1) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(EFFORT_FLUSH_INTERVAL_MS / 2);
        move();
      });
    }
    await act(async () => {
      await vi.advanceTimersByTimeAsync(EFFORT_FLUSH_INTERVAL_MS / 2);
    });

    const last = bodies().at(-1);
    expect(last?.method).toBe("PUT");
    expect(last?.path).toMatch(/^\/sessions\/sesion-1\/effort\/segments\/[0-9a-f]{32}$/);
    // El último envío es el del segundo turno; lo de después espera al siguiente.
    expect(last?.json.active_ms).toBe(2 * EFFORT_FLUSH_INTERVAL_MS);
  });

  it("la pestaña oculta no suma tiempo", async () => {
    const { hook } = setup();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
      move();
      visibility.state = "hidden";
      document.dispatchEvent(new Event("visibilitychange"));
      await vi.advanceTimersByTimeAsync(10 * MINUTE);
      visibility.state = "visible";
      document.dispatchEvent(new Event("visibilitychange"));
      await vi.advanceTimersByTimeAsync(3_000);
      move();
    });

    expect(hook.result.current.activeMs()).toBe(8_000);
  });

  it("al dejar la página envía lo medido con keepalive", async () => {
    const { bodies } = setup();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4_000);
      move();
      window.dispatchEvent(new Event("pagehide"));
    });

    expect(bodies().at(-1)).toMatchObject({ keepalive: true, json: { active_ms: 4_000 } });
  });

  it("sin medir no envía nada", async () => {
    const { request, hook } = setup(false);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3 * EFFORT_FLUSH_INTERVAL_MS);
      move();
      window.dispatchEvent(new Event("pagehide"));
    });
    hook.unmount();

    expect(request).not.toHaveBeenCalled();
  });
});
