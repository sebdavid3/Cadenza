import { act, render } from "@testing-library/react";
import { StrictMode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { deferred } from "../../test/auth-helpers";
import type { ScoreIRPayload } from "../../types";
import type { RenderedScore } from "./osmd";
import { ScoreView, type ScoreSnapshot } from "./ScoreView";

// El dibujo real no importa aquí: solo cuándo se pide, cuándo termina y cuándo se libera.
const calls = vi.hoisted(() => ({
  pending: [] as {
    signal: AbortSignal;
    resolve: (score: RenderedScore) => void;
    reject: (reason: unknown) => void;
  }[],
}));
vi.mock("./osmd", () => ({
  renderScore: (_host: HTMLElement, _xml: string, signal: AbortSignal) => {
    const { promise, resolve, reject } = deferred<RenderedScore>();
    calls.pending.push({ signal, resolve, reject });
    return promise;
  },
}));

function fakeScore() {
  return {
    measuresPerStaff: () => [1],
    measureBox: () => ({ left: 0, top: 0, width: 10, height: 10 }),
    measureFigures: () => [],
    relayout: vi.fn(),
    dispose: vi.fn(),
  } satisfies RenderedScore;
}

/** Un compás vacío: la selección no importa aquí. */
const TRANSCRIPTION = {
  parts: [
    { id: "part-0", staves: [{ id: "part-0-staff-0", measures: [{ number: 1, events: [] }] }] },
  ],
} as unknown as ScoreIRPayload;

const FIRST: ScoreSnapshot = { xml: "<score-partwise/>", transcription: TRANSCRIPTION, seq: 0 };

function view(snapshot = FIRST) {
  return (
    <ScoreView
      snapshot={snapshot}
      sessionId="sesion"
      marks={[]}
      expectedMeasures={[1]}
      selectedKey={null}
    />
  );
}

beforeEach(() => {
  calls.pending = [];
});

describe("ScoreView", () => {
  it("con el doble montaje de StrictMode libera el dibujo descartado y el que se queda", async () => {
    const rendered = render(<StrictMode>{view()}</StrictMode>);
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

    rendered.unmount();
    expect(kept.dispose).toHaveBeenCalledTimes(1);
  });

  it("mientras se dibuja no invita a elegir notas", () => {
    const rendered = render(view());

    expect(rendered.getByText("Preparando la selección de notas…")).toBeInTheDocument();
    expect(rendered.queryByText(/elige una nota/i)).toBeNull();
    expect(rendered.queryByRole("button", { name: "Siguiente" })).toBeNull();
  });

  it("al cambiar de estado deja a la vista el dibujo anterior hasta tener el nuevo", async () => {
    const rendered = render(view());
    const first = fakeScore();
    await act(async () => {
      calls.pending[0]?.resolve(first);
      await Promise.resolve();
    });
    const host = rendered.container.querySelector(".notation__host");
    expect(host?.children).toHaveLength(1);

    rendered.rerender(view({ ...FIRST, seq: 1 }));
    // El nuevo se prepara oculto encima del anterior, que sigue entero.
    expect(calls.pending).toHaveLength(2);
    expect(host?.children).toHaveLength(2);
    expect(host?.lastElementChild).toHaveClass("notation__next");
    expect(first.dispose).not.toHaveBeenCalled();
    expect(rendered.queryByText("Dibujando la partitura…")).toBeNull();

    const second = fakeScore();
    await act(async () => {
      calls.pending[1]?.resolve(second);
      await Promise.resolve();
    });
    expect(first.dispose).toHaveBeenCalledTimes(1);
    expect(host?.children).toHaveLength(1);
    expect(host?.firstElementChild).not.toHaveClass("notation__next");

    rendered.unmount();
    expect(second.dispose).toHaveBeenCalledTimes(1);
  });

  it("si llega otro estado mientras se dibuja uno, descarta ese y deja el de antes hasta el último", async () => {
    const rendered = render(view());
    const first = fakeScore();
    await act(async () => {
      calls.pending[0]?.resolve(first);
      await Promise.resolve();
    });
    const host = rendered.container.querySelector(".notation__host");

    rendered.rerender(view({ ...FIRST, seq: 1 }));
    rendered.rerender(view({ ...FIRST, seq: 2 }));
    // El del estado 1 se cancela y su contenedor se va; el del 0 sigue a la vista.
    expect(calls.pending[1]?.signal.aborted).toBe(true);
    expect(calls.pending[2]?.signal.aborted).toBe(false);
    expect(host?.children).toHaveLength(2);
    expect(first.dispose).not.toHaveBeenCalled();

    const late = fakeScore();
    const last = fakeScore();
    await act(async () => {
      calls.pending[1]?.resolve(late);
      calls.pending[2]?.resolve(last);
      await Promise.resolve();
    });
    expect(late.dispose).toHaveBeenCalledTimes(1);
    expect(first.dispose).toHaveBeenCalledTimes(1);
    expect(last.dispose).not.toHaveBeenCalled();
    expect(host?.children).toHaveLength(1);
    expect(host?.firstElementChild).not.toHaveClass("notation__next");
  });

  it("si el estado nuevo no se puede dibujar, no deja a la vista el anterior", async () => {
    const rendered = render(view());
    const first = fakeScore();
    await act(async () => {
      calls.pending[0]?.resolve(first);
      await Promise.resolve();
    });

    rendered.rerender(view({ ...FIRST, seq: 1 }));
    await act(async () => {
      calls.pending[1]?.reject(new Error("MusicXML no válido"));
      await Promise.resolve();
    });

    expect(first.dispose).toHaveBeenCalledTimes(1);
    expect(rendered.getByText("No se pudo dibujar la partitura.")).toBeInTheDocument();
    expect(rendered.container.querySelector(".notation__host")?.children).toHaveLength(0);
  });

  it("al salir mientras OSMD carga, cancela el dibujo y lo libera cuando termina", async () => {
    const rendered = render(view());
    rendered.unmount();
    expect(calls.pending[0]?.signal.aborted).toBe(true);

    const late = fakeScore();
    await act(async () => {
      calls.pending[0]?.resolve(late);
      await Promise.resolve();
    });
    expect(late.dispose).toHaveBeenCalledTimes(1);
  });
});
