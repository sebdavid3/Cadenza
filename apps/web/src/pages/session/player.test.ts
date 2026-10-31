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
  const created: {
    playback: Playback;
    handlers: EngineHandlers;
    dispose: () => void;
    updates: Playback[];
  }[] = [];
  vi.spyOn(engineLoader, "load").mockResolvedValue((played, _tempo, handlers) => {
    const dispose = vi.fn();
    const updates: Playback[] = [];
    const engine: PlaybackEngine = {
      update: (next) => {
        updates.push(next);
      },
      play: vi.fn(() => Promise.resolve()),
      pause: vi.fn(),
      stop: vi.fn(),
      setTempo: vi.fn(),
      dispose,
    };
    created.push({ playback: played, handlers, dispose, updates });
    return engine;
  });
  return created;
}

describe("usePlayer", () => {
  it("otro estado de la misma sesión no corta lo que suena: el motor sigue con la partitura nueva (#276)", async () => {
    const created = fakeEngines();
    const first = playback(3);
    const { result, rerender, unmount } = renderHook(({ played }) => usePlayer(played), {
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

    const second = playback(6);
    rerender({ played: second });

    expect(created).toHaveLength(1);
    expect(created[0]?.dispose).not.toHaveBeenCalled();
    expect(created[0]?.updates).toEqual([second]);
    expect(result.current.status).toBe("playing");
    expect(result.current.measure).toBe(1);

    // Al salir de la vista sí se libera.
    unmount();
    expect(created[0]?.dispose).toHaveBeenCalledTimes(1);
  });

  it("si el estado nuevo no tiene nada que sonar, se detiene", async () => {
    const created = fakeEngines();
    const { result, rerender } = renderHook(({ played }) => usePlayer(played), {
      initialProps: { played: playback(3) },
    });
    await waitFor(() => {
      expect(result.current.status).toBe("stopped");
    });
    act(() => {
      result.current.play();
    });

    rerender({ played: { notes: [], measures: [], totalBeats: 3 } });

    expect(created[0]?.dispose).toHaveBeenCalledTimes(1);
    expect(result.current.status).toBe("stopped");
    expect(result.current.measure).toBeNull();
  });

  it("no carga Tone.js si no hay nada que sonar", () => {
    const load = vi.spyOn(engineLoader, "load");
    renderHook(() => usePlayer({ notes: [], measures: [], totalBeats: 3 }));

    expect(load).not.toHaveBeenCalled();
  });
});
