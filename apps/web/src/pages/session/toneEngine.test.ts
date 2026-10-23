import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { deferred } from "../../test/auth-helpers";
import type { Playback } from "./playback";

// Tone.js sin audio. El transporte falso reproduce lo que hace el de Tone 15.1.22 (leído en
// `core/clock/Clock.js` y `Transport.js`): arranca en `now()` (el instante actual más el margen
// de anticipación), dispara lo programado hasta ese margen, no pausa en un instante anterior al
// arranque y, al reanudar, vuelve a disparar lo anticipado después de la pausa. Es un modelo:
// codifica esa lectura del código de Tone, no lo sustituye.
const tone = vi.hoisted(() => {
  const LOOK_AHEAD = 0.1;
  const state = {
    contexts: [] as { options: unknown; disposed: boolean }[],
    voices: [] as {
      notes: [number, string, number][];
      disposed: boolean;
      fades: [number, number, number][];
    }[],
    setContext: [] as unknown[],
    resumed: 0,
    resume: null as null | (() => Promise<void>),
  };

  class FakeBpm {
    constructor(private readonly transport: FakeTransport) {}
    get value() {
      return this.transport.tempo;
    }
    set value(bpm: number) {
      this.transport.tempo = bpm;
    }
  }

  class FakeTransport {
    PPQ = 192;
    state: "started" | "paused" | "stopped" = "stopped";
    /** Instante de audio en que arranca el tramo actual y pulsos ya recorridos antes. */
    private startedAt = 0;
    private ticksBefore = 0;
    private beatsPerMinute = 120;
    events: { tick: number; callback: (time: number) => void; fired: boolean }[] = [];
    constructor(private readonly context: FakeContext) {}
    // Como un `Param` de Tone: el valor nuevo rige desde `now()`.
    bpm = new FakeBpm(this);
    get tempo() {
      return this.beatsPerMinute;
    }
    set tempo(bpm: number) {
      const at = this.context.now();
      if (this.state === "started" && at >= this.startedAt) {
        this.ticksBefore = this.ticksAt(at);
        this.startedAt = at;
      }
      this.beatsPerMinute = bpm;
    }
    private ticksAt(time: number) {
      if (this.state !== "started" || time < this.startedAt) return this.ticksBefore;
      return this.ticksBefore + ((time - this.startedAt) * this.tempo * this.PPQ) / 60;
    }
    private timeOf(tick: number) {
      return this.startedAt + ((tick - this.ticksBefore) * 60) / (this.tempo * this.PPQ);
    }
    schedule(callback: (time: number) => void, time: string) {
      this.events.push({ tick: Number.parseInt(time, 10), callback, fired: false });
      return this.events.length;
    }
    cancel() {
      this.events = [];
    }
    start(time = this.context.now()) {
      this.startedAt = time;
      this.state = "started";
    }
    pause(time = this.context.now()) {
      // `Clock.pause` solo actúa si en `time` el transporte ya estaba en marcha.
      if (this.state !== "started" || time < this.startedAt) return;
      this.ticksBefore = this.ticksAt(time);
      this.state = "paused";
      for (const event of this.events) if (event.tick >= this.ticksBefore) event.fired = false;
    }
    stop() {
      this.state = "stopped";
      this.ticksBefore = 0;
      for (const event of this.events) event.fired = false;
    }
    /** Lo que el reloj de Tone haría en un tic: disparar lo que cae antes del margen. */
    tick() {
      if (this.state !== "started") return;
      const horizon = this.ticksAt(this.context.now());
      for (const event of this.events) {
        if (!event.fired && event.tick >= this.ticksBefore - 1e-6 && event.tick <= horizon) {
          event.fired = true;
          event.callback(this.timeOf(event.tick));
        }
      }
    }
  }

  class FakeContext {
    currentTime = 0;
    state = "suspended";
    transport: FakeTransport;
    record: { options: unknown; disposed: boolean };
    constructor(options: unknown) {
      this.record = { options, disposed: false };
      state.contexts.push(this.record);
      this.transport = new FakeTransport(this);
    }
    now() {
      return this.currentTime + LOOK_AHEAD;
    }
    immediate() {
      return this.currentTime;
    }
    resume() {
      state.resumed += 1;
      const done = state.resume ? state.resume() : Promise.resolve();
      return done.then(() => {
        this.state = "running";
      });
    }
    dispose() {
      this.record.disposed = true;
    }
  }

  // Cada voz es una ganancia propia con su sintetizador: se anotan sus notas y sus fundidos.
  let current: (typeof state.voices)[number] | null = null;
  class FakeGain {
    record = {
      notes: [] as [number, string, number][],
      disposed: false,
      fades: [] as [number, number, number][],
    };
    gain = {
      rampTo: (value: number, ramp: number, start: number) => {
        this.record.fades.push([value, ramp, start]);
      },
    };
    constructor() {
      state.voices.push(this.record);
      current = this.record;
    }
    toDestination() {
      return this;
    }
    dispose() {
      this.record.disposed = true;
    }
  }
  class FakePolySynth {
    volume = { value: 0 };
    private readonly record = current;
    connect() {
      return this;
    }
    triggerAttackRelease(frequency: number, duration: string, time: number) {
      this.record?.notes.push([frequency, duration, time]);
    }
    dispose() {
      // La voz se da por liberada con su ganancia.
    }
  }

  return { state, FakeContext, FakeGain, FakePolySynth };
});

vi.mock("tone/build/esm/classes.js", () => ({
  Context: tone.FakeContext,
  Gain: tone.FakeGain,
  PolySynth: tone.FakePolySynth,
  // El doble de PolySynth no usa la voz: basta con algo que pasarle.
  Synth: { name: "Synth" },
}));
vi.mock("tone/build/esm/core/Global.js", () => ({
  setContext: (context: unknown) => tone.state.setContext.push(context),
}));

const { createToneEngine } = await import("./toneEngine");

// Dos compases de 2/4 a 120 negras por minuto: cada negra dura medio segundo.
const PLAYBACK: Playback = {
  notes: [
    { start: 0, duration: 1, midi: 60, measure: 1 },
    { start: 1, duration: 1, midi: 64, measure: 1 },
    { start: 2, duration: 2, midi: 67, measure: 2 },
  ],
  measures: [
    { number: 1, start: 0, end: 2 },
    { number: 2, start: 2, end: 4 },
  ],
  totalBeats: 4,
};

type Context = InstanceType<typeof tone.FakeContext>;
const context = () => tone.state.setContext.at(-1) as Context;
const voice = () => tone.state.voices.at(-1);

/**
 * Reloj falso: un tic del transporte cada 50 ms, y el audio y los temporizadores avanzan juntos
 * hasta el siguiente.
 */
function advance(seconds: number) {
  for (let elapsed = 0; elapsed < seconds - 1e-9; elapsed += 0.05) {
    context().transport.tick();
    vi.advanceTimersByTime(50);
    context().currentTime += 0.05;
  }
}

/** Libera el motor y deja correr el fundido, para que la prueba siguiente empiece de cero. */
function release(engine: { dispose(): void }) {
  engine.dispose();
  vi.advanceTimersByTime(200);
}

beforeEach(() => {
  vi.useFakeTimers();
  tone.state.resume = null;
});

afterEach(() => {
  vi.useRealTimers();
});

describe("motor de audio con Tone.js", () => {
  it("usa un reloj por setTimeout: el Worker desde blob: lo bloquea la CSP", () => {
    const engine = createToneEngine(PLAYBACK, 120, { onMeasure: vi.fn(), onEnd: vi.fn() });

    expect(tone.state.contexts.at(-1)?.options).toMatchObject({ clockSource: "timeout" });
    expect(tone.state.setContext.at(-1)).toBeInstanceOf(tone.FakeContext);
    release(engine);
  });

  it("programa cada nota en su pulso, con su frecuencia y su duración", async () => {
    const engine = createToneEngine(PLAYBACK, 120, { onMeasure: vi.fn(), onEnd: vi.fn() });
    const played = voice();
    const resumedBefore = tone.state.resumed;

    await engine.play();
    expect(tone.state.resumed).toBe(resumedBefore + 1);
    advance(2.2);

    const notes = played?.notes ?? [];
    expect(notes.map(([frequency, duration]) => [Math.round(frequency), duration])).toEqual([
      [262, "192i"],
      [330, "192i"],
      [392, "384i"],
    ]);
    // Cada nota, en su instante: medio segundo por negra desde que arrancó el transporte.
    const start = notes[0]?.[2] ?? 0;
    expect(notes.map(([, , time]) => Math.round((time - start) * 1000) / 1000)).toEqual([
      0, 0.5, 1,
    ]);
    release(engine);
  });

  it("avisa del compás cuando suena, no cuando lo programa, y del final", async () => {
    const onMeasure = vi.fn();
    const onEnd = vi.fn();
    const engine = createToneEngine(PLAYBACK, 120, { onMeasure, onEnd });
    await engine.play();

    advance(0.05);
    // El transporte ya programó el compás 1 (margen de 0,1 s), pero todavía no suena.
    expect(onMeasure).not.toHaveBeenCalled();
    advance(0.1);
    expect(onMeasure.mock.calls).toEqual([[1]]);
    advance(1);
    expect(onMeasure.mock.calls).toEqual([[1], [2]]);
    expect(onEnd).not.toHaveBeenCalled();
    advance(1);
    expect(onEnd).toHaveBeenCalledTimes(1);
    expect(context().transport.state).toBe("stopped");
    release(engine);
  });

  it("al terminar deja sonar la caída de la última nota", async () => {
    const onEnd = vi.fn();
    const engine = createToneEngine(PLAYBACK, 120, { onMeasure: vi.fn(), onEnd });
    const played = voice();
    await engine.play();

    advance(2.4);

    expect(onEnd).toHaveBeenCalledTimes(1);
    expect(played?.fades).toEqual([]);
    expect(played?.disposed).toBe(false);
    release(engine);
  });

  it("al pausar funde lo que suena y no avisa de compases pendientes; al reanudar sigue", async () => {
    const onMeasure = vi.fn();
    const engine = createToneEngine(PLAYBACK, 120, { onMeasure, onEnd: vi.fn() });
    await engine.play();
    advance(1.05);
    // Justo antes del compás 2: su nota y su aviso ya están programados dentro del margen.
    expect(onMeasure.mock.calls).toEqual([[1]]);
    const before = voice();
    const pausedAt = context().currentTime;

    engine.pause();
    advance(1);

    // Fundido de 30 ms desde el instante de la pausa, no desde el ya anticipado.
    expect(before?.fades).toEqual([[0, 0.03, pausedAt]]);
    expect(before?.disposed).toBe(true);
    expect(onMeasure.mock.calls).toEqual([[1]]);
    await engine.play();
    advance(0.6);
    expect(onMeasure.mock.calls).toEqual([[1], [2]]);
    expect(voice()?.notes.map(([frequency]) => Math.round(frequency))).toEqual([392]);
    release(engine);
  });

  it("una pausa justo después de «Reproducir» pausa de verdad", async () => {
    const onMeasure = vi.fn();
    const engine = createToneEngine(PLAYBACK, 120, { onMeasure, onEnd: vi.fn() });
    await engine.play();
    // Dentro del margen: el transporte arranca en 0,1 s y todavía no ha llegado.
    advance(0.05);

    engine.pause();
    advance(2);

    expect(context().transport.state).toBe("paused");
    expect(onMeasure).not.toHaveBeenCalled();
    expect(voice()?.notes).toEqual([]);
    // Al reanudar empieza desde el principio, sin saltarse el compás 1.
    await engine.play();
    advance(0.3);
    expect(onMeasure.mock.calls).toEqual([[1]]);
    release(engine);
  });

  it("si se detiene o pausa mientras el audio se reanuda, no arranca después", async () => {
    const pending = deferred<undefined>();
    tone.state.resume = () => pending.promise;
    const onMeasure = vi.fn();
    const engine = createToneEngine(PLAYBACK, 120, { onMeasure, onEnd: vi.fn() });
    context().state = "suspended";

    const playing = engine.play();
    engine.stop();
    pending.resolve(undefined);
    await playing;
    advance(2);

    expect(context().transport.state).toBe("stopped");
    expect(onMeasure).not.toHaveBeenCalled();
    release(engine);
  });

  it("cambia el tempo mientras suena sin volver a programar", async () => {
    const onMeasure = vi.fn();
    const engine = createToneEngine(PLAYBACK, 120, { onMeasure, onEnd: vi.fn() });
    await engine.play();
    advance(0.2);
    expect(onMeasure.mock.calls).toEqual([[1]]);

    engine.setTempo(60);
    // A 120 el compás 2 sonaría en menos de 1 s; a 60 desde aquí tarda unos 1,7 s.
    advance(1.5);
    expect(onMeasure.mock.calls).toEqual([[1]]);
    advance(0.4);
    expect(onMeasure.mock.calls).toEqual([[1], [2]]);
    release(engine);
  });

  it("detener vuelve al principio", async () => {
    const onMeasure = vi.fn();
    const engine = createToneEngine(PLAYBACK, 120, { onMeasure, onEnd: vi.fn() });
    await engine.play();
    advance(1.5);
    engine.stop();
    expect(context().transport.state).toBe("stopped");

    onMeasure.mockClear();
    await engine.play();
    advance(0.2);
    expect(onMeasure.mock.calls).toEqual([[1]]);
    release(engine);
  });

  it("al liberarse cancela lo programado, funde la voz y cierra el contexto", () => {
    const engine = createToneEngine(PLAYBACK, 120, { onMeasure: vi.fn(), onEnd: vi.fn() });
    const used = context();

    engine.dispose();
    expect(used.transport.events).toEqual([]);
    expect(voice()?.fades).toHaveLength(1);
    expect(used.record.disposed).toBe(false);
    vi.advanceTimersByTime(200);
    expect(voice()?.disposed).toBe(true);
    expect(used.record.disposed).toBe(true);

    // La siguiente vista crea otro contexto en su gesto.
    const next = createToneEngine(PLAYBACK, 120, { onMeasure: vi.fn(), onEnd: vi.fn() });
    expect(context()).not.toBe(used);
    release(next);
  });
});
