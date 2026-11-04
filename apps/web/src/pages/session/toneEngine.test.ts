import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { deferred } from "../../test/auth-helpers";
import type { Playback } from "./playback";
import { SOUNDS, type Sound } from "./sounds";

// Tone.js sin audio. El transporte falso reproduce lo que hace el de Tone 15.1.22 (leído en
// `core/clock/Clock.js` y `Transport.js`): arranca en `now()` (el instante actual más el margen
// de anticipación), dispara lo programado hasta ese margen, no pausa en un instante anterior al
// arranque y, al reanudar, vuelve a disparar lo anticipado después de la pausa. Es un modelo:
// codifica esa lectura del código de Tone, no lo sustituye. Salvo una cosa, vista en el navegador
// y no leída en su código: el pulso 0 disparado antes de una parada por llegar (#299, en `stop`).
interface VoiceRecord {
  notes: [number, string, number][];
  disposed: boolean;
  fades: [number, number, number][];
  /** Lo que recibió el `PolySynth`, su volumen y si se liberó. */
  synth: {
    options?: { oscillator: unknown; envelope: unknown };
    volume: { value: number };
    disposed: boolean;
  };
  /** Filtros y vibratos entre el sintetizador y la ganancia, con sus opciones. */
  effects: { kind: "filter" | "vibrato"; options: Record<string, unknown>; disposed: boolean }[];
  /** Conexiones de la voz, de nodo a nodo: «synth», «filter», «vibrato», «gain», «destination». */
  links: [string, string][];
}

const tone = vi.hoisted(() => {
  const LOOK_AHEAD = 0.1;
  const state = {
    contexts: [] as { options: unknown; disposed: boolean }[],
    voices: [] as VoiceRecord[],
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
    /** Como `Transport.ticks` de Tone: los pulsos en `now()`, con el margen de anticipación. */
    get ticks() {
      return this.ticksAt(this.context.now());
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
    /** Parada en un instante por llegar, con el transporte en marcha (ver `stop`). */
    private stopping: number | null = null;
    stop(time = this.context.now()) {
      // Visto en el navegador con Tone 15.1.22 (#299), no leído en su código: parado en marcha
      // en un instante por llegar (`stop()` sin instante para en `now()`, el margen por delante),
      // el reloj puede disparar lo programado en el pulso 0 en su tic anterior a la parada. No
      // pasa siempre; el modelo lo hace siempre.
      if (this.state === "started" && time > this.context.currentTime) this.stopping = time;
      this.state = "stopped";
      this.ticksBefore = 0;
      for (const event of this.events) event.fired = false;
    }
    /** Lo que el reloj de Tone haría en un tic: disparar lo que cae antes del margen. */
    tick() {
      if (this.stopping !== null) {
        const at = this.stopping;
        this.stopping = null;
        for (const event of this.events) if (event.tick === 0) event.callback(at);
      }
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
  let current: VoiceRecord | null = null;
  class FakeGain {
    record: VoiceRecord = {
      notes: [],
      disposed: false,
      fades: [],
      synth: { volume: { value: 0 }, disposed: false },
      effects: [],
      links: [],
    };
    readonly label = "gain";
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
      this.record.links.push([this.label, "destination"]);
      return this;
    }
    dispose() {
      this.record.disposed = true;
    }
  }
  class FakePolySynth {
    volume = { value: 0 };
    readonly label = "synth";
    private readonly record = current;
    constructor(options: { options: { oscillator: unknown; envelope: unknown } }) {
      if (this.record) {
        this.record.synth = { options: options.options, volume: this.volume, disposed: false };
      }
    }
    connect(target: { label: string }) {
      this.record?.links.push([this.label, target.label]);
      return this;
    }
    triggerAttackRelease(frequency: number, duration: string, time: number) {
      this.record?.notes.push([frequency, duration, time]);
    }
    dispose() {
      if (this.record) this.record.synth.disposed = true;
    }
  }

  // Filtro y vibrato: se anotan en la voz que se está montando (se crean tras su ganancia).
  const effect = (kind: "filter" | "vibrato") =>
    class {
      readonly label = kind;
      private readonly record: VoiceRecord["effects"][number];
      private readonly voice = current;
      constructor(options: Record<string, unknown>) {
        this.record = { kind, options, disposed: false };
        this.voice?.effects.push(this.record);
      }
      connect(target: { label: string }) {
        this.voice?.links.push([this.label, target.label]);
        return this;
      }
      dispose() {
        this.record.disposed = true;
      }
    };

  return {
    state,
    FakeContext,
    FakeGain,
    FakePolySynth,
    FakeFilter: effect("filter"),
    FakeVibrato: effect("vibrato"),
  };
});

vi.mock("tone/build/esm/classes.js", () => ({
  Context: tone.FakeContext,
  Gain: tone.FakeGain,
  PolySynth: tone.FakePolySynth,
  Filter: tone.FakeFilter,
  Vibrato: tone.FakeVibrato,
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
    { start: 0, duration: 1, midi: 60, measure: 1, sound: "piano" },
    { start: 1, duration: 1, midi: 64, measure: 1, sound: "piano" },
    { start: 2, duration: 2, midi: 67, measure: 2, sound: "piano" },
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

  it("tras el final no vuelve al compás 1 aunque Tone dispare el pulso 0 antes de parar (#299)", async () => {
    const onMeasure = vi.fn();
    const onEnd = vi.fn();
    const engine = createToneEngine(PLAYBACK, 120, { onMeasure, onEnd });
    const played = voice();
    await engine.play();
    // El final llega hacia 2,05 s y para en `now()`, 2,15 s; el tic de 2,1 s dispara el pulso 0.
    advance(2.4);
    expect(onEnd).toHaveBeenCalledTimes(1);

    // Ni el aviso del compás 1 ni su primera nota, tampoco más tarde: lo que dispara el transporte
    // ya parado no suena ni avisa.
    expect(onMeasure.mock.calls).toEqual([[1], [2]]);
    expect(played?.notes).toHaveLength(3);
    advance(1);
    expect(onMeasure.mock.calls).toEqual([[1], [2]]);
    expect(played?.notes).toHaveLength(3);
    release(engine);
  });

  it("tras el final, reproducir empieza desde el principio (#299)", async () => {
    const onMeasure = vi.fn();
    const onEnd = vi.fn();
    const engine = createToneEngine(PLAYBACK, 120, { onMeasure, onEnd });
    const played = voice();
    await engine.play();
    advance(3);
    expect(onEnd).toHaveBeenCalledTimes(1);
    onMeasure.mockClear();

    await engine.play();
    advance(0.6);

    expect(onMeasure.mock.calls).toEqual([[1]]);
    expect(played?.notes.slice(3).map(([frequency]) => Math.round(frequency))).toEqual([262, 330]);
    advance(2);
    expect(onMeasure.mock.calls).toEqual([[1], [2]]);
    expect(onEnd).toHaveBeenCalledTimes(2);
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

  it("con otra partitura mientras suena, sigue desde el mismo punto con las notas nuevas (#276)", async () => {
    const onMeasure = vi.fn();
    const onEnd = vi.fn();
    const engine = createToneEngine(PLAYBACK, 120, { onMeasure, onEnd });
    const contextBefore = context();
    await engine.play();
    advance(0.3);
    expect(onMeasure.mock.calls).toEqual([[1]]);

    // Una edición sube un tono la segunda nota y la tercera: el transporte no se detiene.
    engine.update({
      ...PLAYBACK,
      notes: [
        { start: 0, duration: 1, midi: 60, measure: 1, sound: "piano" },
        { start: 1, duration: 1, midi: 66, measure: 1, sound: "piano" },
        { start: 2, duration: 2, midi: 69, measure: 2, sound: "piano" },
      ],
    });
    advance(1.2);

    expect(context()).toBe(contextBefore);
    expect(context().transport.state).toBe("started");
    // La primera nota ya sonó; las siguientes suenan con su altura nueva y en su instante.
    expect(voice()?.notes.map(([frequency]) => Math.round(frequency))).toEqual([262, 370, 440]);
    expect(onMeasure.mock.calls).toEqual([[1], [2]]);
    advance(1);
    expect(onEnd).toHaveBeenCalledTimes(1);
    release(engine);
  });

  it("si la partitura nueva acaba antes del punto que suena, termina", async () => {
    const onEnd = vi.fn();
    const engine = createToneEngine(PLAYBACK, 120, { onMeasure: vi.fn(), onEnd });
    await engine.play();
    advance(1.5);

    engine.update({
      notes: [{ start: 0, duration: 1, midi: 60, measure: 1, sound: "piano" }],
      measures: [{ number: 1, start: 0, end: 1 }],
      totalBeats: 1,
    });
    vi.advanceTimersByTime(10);

    expect(onEnd).toHaveBeenCalledTimes(1);
    expect(context().transport.state).toBe("stopped");
    release(engine);
  });

  it("tras seguir con otra partitura, detener y reproducir la empieza entera", async () => {
    const onMeasure = vi.fn();
    const engine = createToneEngine(PLAYBACK, 120, { onMeasure, onEnd: vi.fn() });
    await engine.play();
    advance(1.3);
    engine.update(PLAYBACK);

    engine.stop();
    onMeasure.mockClear();
    await engine.play();
    advance(0.6);

    expect(onMeasure.mock.calls).toEqual([[1]]);
    expect(voice()?.notes.map(([frequency]) => Math.round(frequency))).toEqual([262, 330]);
    release(engine);
  });

  it("si el hilo estuvo ocupado, no pierde lo que aún no sonó entre el último tic y now()", async () => {
    const engine = createToneEngine(PLAYBACK, 120, { onMeasure: vi.fn(), onEnd: vi.fn() });
    await engine.play();
    advance(0.3);
    // El dibujo de la partitura ocupa el hilo 0,4 s: el reloj no da ningún tic y `now()` pasa ya
    // la segunda nota, que aún no se disparó.
    context().currentTime += 0.4;

    engine.update({
      ...PLAYBACK,
      notes: [
        { start: 0, duration: 1, midi: 60, measure: 1, sound: "piano" },
        { start: 1, duration: 1, midi: 66, measure: 1, sound: "piano" },
        { start: 2, duration: 2, midi: 69, measure: 2, sound: "piano" },
      ],
    });
    advance(0.8);

    expect(voice()?.notes.map(([frequency]) => Math.round(frequency))).toEqual([262, 370, 440]);
    release(engine);
  });

  it("un final ya anticipado de la partitura vieja no la detiene si la edición la alarga", async () => {
    const onEnd = vi.fn();
    const engine = createToneEngine(PLAYBACK, 120, { onMeasure: vi.fn(), onEnd });
    await engine.play();
    // Justo antes del final (2,1 s): el transporte ya disparó su aviso dentro del margen.
    advance(2.05);
    expect(onEnd).not.toHaveBeenCalled();

    engine.update({
      ...PLAYBACK,
      measures: [...PLAYBACK.measures, { number: 3, start: 4, end: 6 }],
      totalBeats: 6,
    });
    advance(0.2);
    expect(onEnd).not.toHaveBeenCalled();
    expect(context().transport.state).toBe("started");
    advance(1);
    expect(onEnd).toHaveBeenCalledTimes(1);
    release(engine);
  });

  it("en pausa, sigue con la partitura nueva desde el punto de la pausa al reanudar", async () => {
    const onMeasure = vi.fn();
    const engine = createToneEngine(PLAYBACK, 120, { onMeasure, onEnd: vi.fn() });
    await engine.play();
    advance(0.3);
    engine.pause();
    engine.update({
      ...PLAYBACK,
      notes: PLAYBACK.notes.map((note) => ({ ...note, midi: note.midi + 2 })),
    });

    await engine.play();
    advance(1.5);

    // La primera ya sonó antes de la pausa; las demás, con la altura nueva.
    expect(voice()?.notes.map(([frequency]) => Math.round(frequency))).toEqual([370, 440]);
    expect(onMeasure.mock.calls).toEqual([[1], [2]]);
    release(engine);
  });
});

describe("cada parte con su instrumento (#242, ADR-0046)", () => {
  // Dos partes que suenan a la vez: la voz arriba y el piano abajo, en dos compases de 2/4.
  const DUO: Playback = {
    notes: [
      { start: 0, duration: 2, midi: 72, measure: 1, sound: "voice" },
      { start: 0, duration: 1, midi: 48, measure: 1, sound: "piano" },
      { start: 1, duration: 1, midi: 55, measure: 1, sound: "piano" },
      { start: 2, duration: 2, midi: 74, measure: 2, sound: "voice" },
      { start: 2, duration: 2, midi: 43, measure: 2, sound: "piano" },
    ],
    measures: PLAYBACK.measures,
    totalBeats: 4,
  };
  /** Las voces de un sonido creadas desde `from`, reconocidas por lo que recibió su sintetizador. */
  const voicesOf = (sound: Sound, from: number) =>
    tone.state.voices.slice(from).filter(
      (record) =>
        JSON.stringify(record.synth.options) ===
        JSON.stringify({
          oscillator: SOUNDS[sound].oscillator,
          envelope: SOUNDS[sound].envelope,
        }),
    );
  const pitches = (record: VoiceRecord | undefined) =>
    record?.notes.map(([frequency]) => Math.round(frequency));

  it("cada nota suena con el sintetizador de su parte, con su onda, su filtro y su vibrato", async () => {
    const from = tone.state.voices.length;
    const engine = createToneEngine(DUO, 120, { onMeasure: vi.fn(), onEnd: vi.fn() });
    await engine.play();
    advance(2.2);

    expect(tone.state.voices.length - from).toBe(2);
    const [voice] = voicesOf("voice", from);
    const [piano] = voicesOf("piano", from);
    expect(pitches(voice)).toEqual([523, 587]);
    expect(pitches(piano)).toEqual([131, 196, 98]);
    expect(voice?.synth.volume.value).toBe(SOUNDS.voice.volume);
    expect(piano?.synth.volume.value).toBe(SOUNDS.piano.volume);
    // La voz pasa por su filtro de paso bajo y su vibrato; el piano, por nada (ADR-0026).
    expect(voice?.effects.map(({ kind, options }) => [kind, options])).toEqual([
      ["vibrato", expect.objectContaining(SOUNDS.voice.vibrato)],
      ["filter", expect.objectContaining({ type: "lowpass", frequency: SOUNDS.voice.lowpass })],
    ]);
    const chain = (record: VoiceRecord | undefined) => {
      const next = new Map(record?.links);
      const path = ["synth"];
      for (let node = next.get("synth"); node; node = next.get(node)) path.push(node);
      return path;
    };
    expect(chain(voice)).toEqual(["synth", "filter", "vibrato", "gain", "destination"]);
    expect(voice?.links).toHaveLength(4);
    expect(piano?.effects).toEqual([]);
    expect(chain(piano)).toEqual(["synth", "gain", "destination"]);
    release(engine);
  });

  it("los instrumentos no cambian el compás que suena ni el final", async () => {
    const timeline = async (playback: Playback) => {
      const onMeasure = vi.fn();
      const onEnd = vi.fn();
      const engine = createToneEngine(playback, 120, { onMeasure, onEnd });
      await engine.play();
      const seen: number[][] = [];
      for (let step = 0; step < 50; step += 1) {
        advance(0.05);
        seen.push([onMeasure.mock.calls.length, onEnd.mock.calls.length]);
      }
      release(engine);
      return { seen, measures: onMeasure.mock.calls, ends: onEnd.mock.calls.length };
    };

    const asPiano = {
      ...DUO,
      notes: DUO.notes.map((note) => ({ ...note, sound: "piano" as const })),
    };
    const dressed = await timeline(DUO);
    expect(dressed).toEqual(await timeline(asPiano));
    expect(dressed.measures).toEqual([[1], [2]]);
    expect(dressed.ends).toBe(1);
  });

  it("al pausar funde todas las voces; al reanudar cada parte sigue con su sonido", async () => {
    const from = tone.state.voices.length;
    const engine = createToneEngine(DUO, 120, { onMeasure: vi.fn(), onEnd: vi.fn() });
    await engine.play();
    advance(0.3);
    const [voiceBefore] = voicesOf("voice", from);
    const [pianoBefore] = voicesOf("piano", from);

    // Pausar funde las voces y prepara otras para lo que sigue.
    const resumedFrom = tone.state.voices.length;
    engine.pause();
    advance(0.2);
    expect(voiceBefore?.fades).toHaveLength(1);
    expect(pianoBefore?.fades).toHaveLength(1);
    expect(voiceBefore?.disposed).toBe(true);
    expect(voiceBefore?.synth.disposed).toBe(true);
    expect(voiceBefore?.effects.every((effect) => effect.disposed)).toBe(true);

    await engine.play();
    advance(2);
    expect(pitches(voicesOf("voice", resumedFrom)[0])).toEqual([587]);
    expect(pitches(voicesOf("piano", resumedFrom)[0])).toEqual([196, 98]);
    release(engine);
  });

  it("si cambia el instrumento mientras suena, lo que sigue suena con el nuevo sin cortar", async () => {
    const from = tone.state.voices.length;
    const onMeasure = vi.fn();
    const engine = createToneEngine(DUO, 120, { onMeasure, onEnd: vi.fn() });
    await engine.play();
    advance(0.3);

    // La parte de arriba pasa de voz a violín (otro estado de la sesión): sigue desde el punto.
    engine.update({
      ...DUO,
      notes: DUO.notes.map((note) =>
        note.sound === "voice" ? { ...note, sound: "violin" as const } : note,
      ),
    });
    expect(context().transport.state).toBe("started");
    advance(2);

    expect(pitches(voicesOf("voice", from)[0])).toEqual([523]);
    expect(pitches(voicesOf("violin", from)[0])).toEqual([587]);
    expect(pitches(voicesOf("piano", from)[0])).toEqual([131, 196, 98]);
    // La voz que ya sonaba no se corta: termina con su caída.
    expect(voicesOf("voice", from)[0]?.fades).toEqual([]);
    expect(onMeasure.mock.calls).toEqual([[1], [2]]);
    release(engine);
  });

  it("la voz de un instrumento que ya no se usa se libera al pausar y no se vuelve a crear", async () => {
    const from = tone.state.voices.length;
    const engine = createToneEngine(DUO, 120, { onMeasure: vi.fn(), onEnd: vi.fn() });
    await engine.play();
    advance(0.3);
    engine.update({
      ...DUO,
      notes: DUO.notes.map((note) =>
        note.sound === "voice" ? { ...note, sound: "violin" as const } : note,
      ),
    });
    advance(0.2);
    const [unused] = voicesOf("voice", from);
    const afterUpdate = tone.state.voices.length;

    engine.pause();
    vi.advanceTimersByTime(200);

    expect(unused?.disposed).toBe(true);
    expect(unused?.synth.disposed).toBe(true);
    expect(unused?.effects.every((effect) => effect.disposed)).toBe(true);
    // Pausar prepara las voces de lo que sigue: el violín y el piano, no la voz.
    expect(voicesOf("voice", afterUpdate)).toEqual([]);
    expect(voicesOf("violin", afterUpdate)).toHaveLength(1);
    expect(voicesOf("piano", afterUpdate)).toHaveLength(1);
    release(engine);
  });

  it("al liberarse funde y libera todas las voces con sus efectos", () => {
    const from = tone.state.voices.length;
    const engine = createToneEngine(DUO, 120, { onMeasure: vi.fn(), onEnd: vi.fn() });

    engine.dispose();
    vi.advanceTimersByTime(200);

    const created = tone.state.voices.slice(from);
    expect(created).toHaveLength(2);
    for (const record of created) {
      expect(record.fades).toHaveLength(1);
      expect(record.disposed).toBe(true);
      expect(record.synth.disposed).toBe(true);
      expect(record.effects.every((effect) => effect.disposed)).toBe(true);
    }
  });
});
