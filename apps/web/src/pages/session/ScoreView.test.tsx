import { act, render } from "@testing-library/react";
import { StrictMode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { deferred } from "../../test/auth-helpers";
import type { RenderedScore } from "./osmd";
import { ScoreView } from "./ScoreView";

// El dibujo real no importa aquí: solo cuándo se pide, cuándo termina y cuándo se libera.
const calls = vi.hoisted(() => ({
  pending: [] as {
    signal: AbortSignal;
    resolve: (score: RenderedScore) => void;
  }[],
}));
vi.mock("./osmd", () => ({
  renderScore: (_host: HTMLElement, _xml: string, signal: AbortSignal) => {
    const { promise, resolve } = deferred<RenderedScore>();
    calls.pending.push({ signal, resolve });
    return promise;
  },
}));

function fakeScore() {
  return {
    measuresPerStaff: () => [1],
    measureBox: () => ({ left: 0, top: 0, width: 10, height: 10 }),
    relayout: vi.fn(),
    dispose: vi.fn(),
  } satisfies RenderedScore;
}

beforeEach(() => {
  calls.pending = [];
});

describe("ScoreView", () => {
  it("con el doble montaje de StrictMode libera el dibujo descartado y el que se queda", async () => {
    const view = render(
      <StrictMode>
        <ScoreView xml="<score-partwise/>" marks={[]} expectedMeasures={[1]} selectedKey={null} />
      </StrictMode>,
    );
    expect(calls.pending).toHaveLength(2);
    expect(calls.pending[0]?.signal.aborted).toBe(true);
    expect(calls.pending[1]?.signal.aborted).toBe(false);

    const discarded = fakeScore();
    const kept = fakeScore();
    await act(async () => {
      calls.pending[0]?.resolve(discarded);
      calls.pending[1]?.resolve(kept);
      await Promise.resolve();
    });
    expect(discarded.dispose).toHaveBeenCalledTimes(1);
    expect(kept.dispose).not.toHaveBeenCalled();

    view.unmount();
    expect(kept.dispose).toHaveBeenCalledTimes(1);
  });

  it("al salir mientras OSMD carga, cancela el dibujo y lo libera cuando termina", async () => {
    const view = render(
      <ScoreView xml="<score-partwise/>" marks={[]} expectedMeasures={[1]} selectedKey={null} />,
    );
    view.unmount();
    expect(calls.pending[0]?.signal.aborted).toBe(true);

    const late = fakeScore();
    await act(async () => {
      calls.pending[0]?.resolve(late);
      await Promise.resolve();
    });
    expect(late.dispose).toHaveBeenCalledTimes(1);
  });
});
