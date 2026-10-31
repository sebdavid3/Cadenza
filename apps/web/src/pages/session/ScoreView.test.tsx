import { act, render } from "@testing-library/react";
import { StrictMode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { deferred } from "../../test/auth-helpers";
import type { ScoreIRPayload } from "../../types";
import type { RenderedScore, ScoreRenderer } from "./osmd";
import { ScoreView, type ScoreSnapshot } from "./ScoreView";
import { useSelectionStore } from "./selection";

// El dibujo real no importa aquí: cuándo se crea la instancia de OSMD, qué estados se le piden
// dibujar y cuándo se libera.
const calls = vi.hoisted(() => ({
  pending: [] as {
    signal: AbortSignal;
    resolve: (renderer: ScoreRenderer) => void;
    reject: (reason: unknown) => void;
  }[],
}));
vi.mock("./osmd", () => ({
  createScoreRenderer: (_host: HTMLElement, signal: AbortSignal) => {
    const { promise, resolve, reject } = deferred<ScoreRenderer>();
    calls.pending.push({ signal, resolve, reject });
    return promise;
  },
}));

function fakeScore(): RenderedScore {
  return {
    measuresPerStaff: () => [1],
    measureBox: () => ({ left: 0, top: 0, width: 10, height: 10 }),
    measureFigures: () => [],
  };
}

/** Instancia que dibuja cada MusicXML en un dibujo nuevo, salvo los que `fails` rechaza. */
function fakeRenderer(fails: (xml: string) => boolean = () => false) {
  const drawn: { xml: string; seq: number; score: RenderedScore }[] = [];
  const renderer = {
    draw: vi.fn((xml: string, state: { seq: number }) => {
      if (fails(xml)) throw new Error("MusicXML no válido");
      const score = fakeScore();
      drawn.push({ xml, seq: state.seq, score });
      return score;
    }),
    relayout: vi.fn(),
    dispose: vi.fn(),
  } satisfies ScoreRenderer;
  return { renderer, drawn };
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
  it("con el doble montaje de StrictMode libera la instancia descartada y la que se queda", async () => {
    const rendered = render(<StrictMode>{view()}</StrictMode>);
    expect(calls.pending).toHaveLength(2);
    expect(calls.pending[0]?.signal.aborted).toBe(true);
    expect(calls.pending[1]?.signal.aborted).toBe(false);

    const discarded = fakeRenderer();
    const kept = fakeRenderer();
    await act(async () => {
      calls.pending[0]?.resolve(discarded.renderer);
      calls.pending[1]?.resolve(kept.renderer);
      await Promise.resolve();
    });
    expect(discarded.renderer.dispose).toHaveBeenCalledTimes(1);
    expect(discarded.renderer.draw).not.toHaveBeenCalled();
    expect(kept.drawn.map((entry) => entry.seq)).toContain(0);
    expect(kept.renderer.dispose).not.toHaveBeenCalled();

    rendered.unmount();
    expect(kept.renderer.dispose).toHaveBeenCalledTimes(1);
  });

  it("mientras se carga OSMD no invita a elegir notas", () => {
    const rendered = render(view());

    expect(rendered.getByText("Preparando la selección de notas…")).toBeInTheDocument();
    expect(rendered.queryByText(/elige una nota/i)).toBeNull();
    expect(rendered.queryByRole("button", { name: "Siguiente" })).toBeNull();
  });

  it("dibuja cada estado nuevo en la misma instancia de OSMD, sin crear otra (#276)", async () => {
    const rendered = render(view());
    const { renderer, drawn } = fakeRenderer();
    await act(async () => {
      calls.pending[0]?.resolve(renderer);
      await Promise.resolve();
    });
    expect(drawn.map((entry) => entry.seq)).toEqual([0]);

    rendered.rerender(view({ ...FIRST, xml: "<score-partwise>1</score-partwise>", seq: 1 }));
    rendered.rerender(view({ ...FIRST, xml: "<score-partwise>2</score-partwise>", seq: 2 }));

    // Sin esperas: cada estado se dibuja antes de pintar, y no hay un dibujo intermedio.
    expect(calls.pending).toHaveLength(1);
    expect(drawn.map((entry) => [entry.seq, entry.xml])).toEqual([
      [0, "<score-partwise/>"],
      [1, "<score-partwise>1</score-partwise>"],
      [2, "<score-partwise>2</score-partwise>"],
    ]);
    expect(rendered.queryByText("Dibujando la partitura…")).toBeNull();
    expect(renderer.dispose).not.toHaveBeenCalled();

    rendered.unmount();
    expect(renderer.dispose).toHaveBeenCalledTimes(1);
  });

  it("si un estado no se puede dibujar lo dice, y el siguiente se dibuja en la misma instancia", async () => {
    const rendered = render(view());
    const { renderer, drawn } = fakeRenderer((xml) => xml.includes("roto"));
    await act(async () => {
      calls.pending[0]?.resolve(renderer);
      await Promise.resolve();
    });

    rendered.rerender(view({ ...FIRST, xml: "<roto/>", seq: 1 }));
    expect(rendered.getByText("No se pudo dibujar la partitura.")).toBeInTheDocument();

    rendered.rerender(view({ ...FIRST, seq: 2 }));
    expect(rendered.queryByText("No se pudo dibujar la partitura.")).toBeNull();
    expect(drawn.map((entry) => entry.seq)).toEqual([0, 2]);
    expect(calls.pending).toHaveLength(1);
  });

  it("si OSMD no se puede cargar, lo dice", async () => {
    const rendered = render(view());
    await act(async () => {
      calls.pending[0]?.reject(new Error("sin el trozo de OSMD"));
      await Promise.resolve();
    });

    expect(rendered.getByText("No se pudo dibujar la partitura.")).toBeInTheDocument();
  });

  it("al salir mientras OSMD carga, cancela la carga y libera lo que llegue", async () => {
    const rendered = render(view());
    rendered.unmount();
    expect(calls.pending[0]?.signal.aborted).toBe(true);

    const late = fakeRenderer();
    await act(async () => {
      calls.pending[0]?.resolve(late.renderer);
      await Promise.resolve();
    });
    expect(late.renderer.dispose).toHaveBeenCalledTimes(1);
    expect(late.renderer.draw).not.toHaveBeenCalled();
  });

  it("si la selección pasa a un estado que aún no está dibujado, su marca se queda hasta que llega (#276)", async () => {
    // Un compás con una nota (Do4, blanca con puntillo) que el doble dibuja en una caja fija.
    const note = {
      kind: "note",
      voice: 0,
      pitch: "C4",
      duration_beats: "3",
      tie: null,
      is_chord: false,
      bbox: null,
      confidence: null,
      ir_handle: null,
    };
    const transcription = {
      parts: [
        {
          id: "part-0",
          staves: [{ id: "part-0-staff-0", measures: [{ number: 1, events: [note] }] }],
        },
      ],
    } as unknown as ScoreIRPayload;
    const drawnAt = (left: number): RenderedScore => ({
      ...fakeScore(),
      measureFigures: () => [
        [
          {
            rest: false,
            grace: false,
            beats: [3, 1],
            notes: [{ midi: 60, step: "C", box: { left, top: 0, width: 5, height: 5 } }],
          },
        ],
      ],
    });
    let left = 10;
    const renderer = {
      draw: vi.fn(() => drawnAt(left)),
      relayout: vi.fn(),
      dispose: vi.fn(),
    } satisfies ScoreRenderer;
    const anchor = {
      part: 0,
      staff: 0,
      measure: 1,
      voice: 0,
      event_index: 0,
      staff_id: "part-0-staff-0",
      bbox: null,
      confidence: null,
    };
    vi.stubGlobal("matchMedia", () => ({ matches: false }));
    Element.prototype.scrollIntoView = vi.fn();
    const first: ScoreSnapshot = { xml: "<a/>", transcription, seq: 0 };
    const rendered = render(view(first));
    await act(async () => {
      calls.pending[0]?.resolve(renderer);
      await Promise.resolve();
    });
    act(() => {
      useSelectionStore.getState().select({ sessionId: "sesion", seq: 0, anchor });
    });
    const mark = () => rendered.container.querySelector<HTMLElement>(".notation__selection");
    expect(mark()?.style.left).toBe("10px");

    // Una orden guardada deja elegido su evento en el estado 1 antes de que llegue su dibujo.
    act(() => {
      useSelectionStore.getState().select({ sessionId: "sesion", seq: 1, anchor, placedBy: 1 });
    });
    expect(mark()?.style.left).toBe("10px");

    // Llega el estado 1, dibujado en otro sitio: la marca pasa a la nota que le corresponde.
    left = 30;
    rendered.rerender(view({ xml: "<b/>", transcription, seq: 1 }));
    expect(mark()?.style.left).toBe("30px");
    useSelectionStore.getState().clear();
    vi.unstubAllGlobals();
  });
});
