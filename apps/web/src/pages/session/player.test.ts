import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Playback } from "./playback";
import { engineLoader, usePlayer, type EngineHandlers, type PlaybackEngine } from "./player";

function playback(totalBeats: number): Playback {
  return {
    notes: [{ start: 0, duration: 1, midi: 60, measure: 1 }],
    measures: [{ number: 1, start: 0, end: totalBeats }],
    totalBeats,
  };
}

/** Motor que solo anota: el reloj no importa aquí, sino cuándo se crea y se libera. */
function fakeEngines() {
  const created: { playback: Playback; handlers: EngineHandlers; dispose: () => void }[] = [];
  vi.spyOn(engineLoader, "load").mockResolvedValue((played, _tempo, handlers) => {
    const dispose = vi.fn();
    const engine: PlaybackEngine = {
      play: vi.fn(() => Promise.resolve()),
      pause: vi.fn(),
      stop: vi.fn(),
      setTempo: vi.fn(),
      dispose,
    };
    created.push({ playback: played, handlers, dispose });
    return engine;
  });
  return created;
}

describe("usePlayer", () => {
  it("otro estado de la misma sesión libera el motor y no hereda el compás", async () => {
    const created = fakeEngines();
    const first = playback(3);
    const { result, rerender } = renderHook(({ played }) => usePlayer(played), {
      initialProps: { played: first },
    });
    await waitFor(() => {
      expect(result.current.status).toBe("stopped");
    });
    act(() => {
      result.current.play();
    });
    act(() => {
      created[0]?.handlers.onMeasure(1);
    });
    expect(result.current.measure).toBe(1);

    rerender({ played: playback(6) });

    expect(created[0]?.dispose).toHaveBeenCalledTimes(1);
    expect(result.current.status).toBe("stopped");
    expect(result.current.measure).toBeNull();
    act(() => {
      result.current.play();
    });
    expect(created).toHaveLength(2);
    expect(created[1]?.playback.totalBeats).toBe(6);
  });

  it("no carga Tone.js si no hay nada que sonar", () => {
    const load = vi.spyOn(engineLoader, "load");
    renderHook(() => usePlayer({ notes: [], measures: [], totalBeats: 3 }));

    expect(load).not.toHaveBeenCalled();
  });
});
