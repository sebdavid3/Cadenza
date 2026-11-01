// Tone.js por sus módulos, no por `tone`: su índice crea un contexto de audio al importarse, con
// el reloj en un Worker desde `blob:` que la CSP de producción bloquea sin avisar (ADR-0026).
import {
  Context,
  Filter,
  Gain,
  PolySynth,
  Synth,
  Vibrato,
  type ToneAudioNode,
} from "tone/build/esm/classes.js";
import { setContext } from "tone/build/esm/core/Global.js";
import type { EngineHandlers, PlaybackEngine } from "./player";
import { midiToFrequency, type Playback } from "./playback";
import { SOUNDS, type Sound } from "./sounds";

/** Fundido al pausar, detener o salir: corta sin chasquido lo que suena. */
const FADE_SECONDS = 0.03;

let shared: Context | null = null;

/**
 * Contexto de audio, creado dentro del gesto de «Reproducir» y cerrado al salir de la vista. El
 * reloj de Tone.js va por `setTimeout` (`clockSource: "timeout"`) y no por un Worker.
 */
function audioContext(): Context {
  if (!shared) {
    shared = new Context({ clockSource: "timeout", latencyHint: "interactive", lookAhead: 0.1 });
    setContext(shared);
  }
  return shared;
}

interface Voice {
  synth: PolySynth;
  /** Vibrato y filtro entre el sintetizador y la ganancia, si el sonido los tiene. */
  effects: ToneAudioNode[];
  output: Gain;
}

/**
 * Voz de un sonido (ADR-0046), sintetizada y sin muestras: su onda con su envolvente, por su
 * filtro de paso bajo y su vibrato si los tiene, y por una ganancia propia para poder fundirla.
 * El piano es la de ADR-0026: onda triangular con un ataque corto, sin efectos.
 */
function createVoice(context: Context, sound: Sound): Voice {
  const spec = SOUNDS[sound];
  const output = new Gain({ context, gain: 1 }).toDestination();
  const effects: ToneAudioNode[] = [];
  let input: ToneAudioNode = output;
  if (spec.vibrato) {
    const vibrato = new Vibrato({ context, ...spec.vibrato }).connect(input);
    effects.push(vibrato);
    input = vibrato;
  }
  if (spec.lowpass !== undefined) {
    const filter = new Filter({ context, type: "lowpass", frequency: spec.lowpass }).connect(input);
    effects.push(filter);
    input = filter;
  }
  const synth = new PolySynth({
    context,
    voice: Synth,
    maxPolyphony: 16,
    options: { oscillator: spec.oscillator, envelope: spec.envelope },
  }).connect(input);
  synth.volume.value = spec.volume;
  return { synth, effects, output };
}

/**
 * Funde unas voces y las libera: calla lo que suena y también las notas que el transporte ya
 * había programado dentro de su margen de anticipación.
 */
function fadeOut(context: Context, voices: Iterable<Voice>, then?: () => void) {
  const fading = [...voices];
  for (const voice of fading) voice.output.gain.rampTo(0, FADE_SECONDS, context.immediate());
  setTimeout(
    () => {
      for (const voice of fading) {
        voice.synth.dispose();
        for (const effect of voice.effects) effect.dispose();
        voice.output.dispose();
      }
      then?.();
    },
    FADE_SECONDS * 1000 + 50,
  );
}

/**
 * Reproductor de una partitura con Tone.js. Las notas y los cambios de compás se programan en el
 * transporte en pulsos (ticks), así que un cambio de tempo los recoloca sin volver a programar.
 * Cada nota suena con la voz de su sonido (el instrumento de su parte, ADR-0046): una voz por
 * sonido, creada al programar la primera nota que lo usa.
 */
export function createToneEngine(
  playback: Playback,
  tempo: number,
  handlers: EngineHandlers,
): PlaybackEngine {
  const context = audioContext();
  const transport = context.transport;
  transport.stop();
  transport.cancel(0);
  transport.bpm.value = tempo;
  // Las voces en uso, una por sonido. Fundir las libera; las siguientes notas crean otras.
  let voices = new Map<Sound, Voice>();
  const voiceFor = (sound: Sound) => {
    let voice = voices.get(sound);
    if (!voice) {
      voice = createVoice(context, sound);
      voices.set(sound, voice);
    }
    return voice;
  };
  // Lo último que pidió la persona: «Pausa» o «Detener» mientras el audio se reanuda gana.
  let intent: "playing" | "paused" | "stopped" = "stopped";
  // Función y no variable: TypeScript no sabe que `intent` puede cambiar durante un await.
  const wanted = () => intent;
  // Instante de audio en que arrancó (o arrancará) el transporte.
  let startAt = 0;
  const ticks = (beats: number) => `${String(Math.round(beats * transport.PPQ))}i`;

  // Los avisos a la vista se dan cuando suena el instante, no cuando se programa (el transporte
  // programa un poco antes, `lookAhead`). Pausar o detener cancela los que siguen pendientes.
  const timers = new Set<ReturnType<typeof setTimeout>>();
  const atTime = (time: number, callback: () => void) => {
    const delay = Math.max(0, (time - context.currentTime) * 1000);
    const timer = setTimeout(() => {
      timers.delete(timer);
      callback();
    }, delay);
    timers.add(timer);
  };
  const clearTimers = () => {
    for (const timer of timers) clearTimeout(timer);
    timers.clear();
  };
  const silence = () => {
    clearTimers();
    fadeOut(context, voices.values());
    voices = new Map();
    for (const note of current.notes) voiceFor(note.sound);
  };

  let current = playback;
  const endTick = () => Math.round(current.totalBeats * transport.PPQ);
  // Si lo programado empieza en un punto de la partitura (tras `update` mientras suena), al volver
  // al principio hay que programarla entera.
  let partial = false;
  // Último pulso que el transporte ya disparó (-1 si ninguno desde que arrancó o se reanudó). No
  // es `transport.ticks`: ese es el pulso en `now()`, por delante de lo disparado, y si el hilo
  // estuvo ocupado (dibujando la partitura) lo que cae entre medias aún no ha sonado.
  let fired = -1;
  /** Termina como al llegar al final: la última nota acaba con su caída, sin fundir la voz. */
  const finish = () => {
    intent = "stopped";
    transport.stop();
    clearTimers();
    fired = -1;
    if (partial) program(0);
    handlers.onEnd();
  };
  /**
   * Programa la partitura a partir del pulso `from`: lo anterior ya sonó. Con el transporte en
   * marcha, `from` es el último pulso disparado y no se vuelve a programar; en pausa o detenido,
   * es el pulso en que seguirá.
   *
   * Solo suena y avisa mientras la persona reproduce. Al terminar, el transporte para en `now()`,
   * el margen por delante, y Tone puede disparar entre tanto lo programado en el pulso 0: la
   * primera nota y el compás 1, que devolvía la lectura a «En pausa · Compás 1» (#299).
   */
  function program(from: number) {
    transport.cancel(0);
    partial = from > 0;
    const running = transport.state === "started";
    const at = (tick: number, callback: (time: number) => void) => {
      if (running ? tick <= from : tick < from) return;
      transport.schedule(
        (time) => {
          if (wanted() !== "playing") return;
          fired = Math.max(fired, tick);
          callback(time);
        },
        `${String(tick)}i`,
      );
    };
    for (const note of current.notes) {
      const frequency = midiToFrequency(note.midi);
      const duration = ticks(note.duration);
      // La voz se crea al programar, no al sonar; se busca al sonar porque pausar la renueva.
      voiceFor(note.sound);
      at(Math.round(note.start * transport.PPQ), (time) => {
        voiceFor(note.sound).synth.triggerAttackRelease(frequency, duration, time);
      });
    }
    for (const measure of current.measures) {
      at(Math.round(measure.start * transport.PPQ), (time) => {
        atTime(time, () => {
          handlers.onMeasure(measure.number);
        });
      });
    }
    const end = endTick();
    transport.schedule(
      (time) => {
        if (wanted() !== "playing") return;
        atTime(time, () => {
          // Un final ya anticipado de una partitura que una edición alargó no termina nada.
          if (end === endTick()) finish();
        });
      },
      `${String(end)}i`,
    );
  }
  program(0);

  return {
    async play() {
      intent = "playing";
      // `resume` se llama antes de cualquier espera, dentro del gesto de la persona.
      if (context.state !== "running") await context.resume();
      if (wanted() !== "playing") return;
      startAt = context.now();
      transport.start(startAt);
    },
    // Se pausa en el instante actual, no en el que el transporte ya anticipó (`lookAhead`): al
    // reanudar vuelve a programar la nota y el compás de ese margen. Si el transporte aún no ha
    // arrancado (justo después de «Reproducir»), se pausa en su arranque: Tone no pausa antes.
    pause() {
      intent = "paused";
      transport.pause(Math.max(context.immediate(), startAt));
      silence();
      // Al reanudar, el transporte vuelve a disparar desde el pulso de la pausa.
      fired = -1;
    },
    stop() {
      intent = "stopped";
      transport.stop(context.immediate());
      silence();
      fired = -1;
      if (partial) program(0);
    },
    // Otra partitura (una edición) con el transporte donde está: lo que sigue suena con las notas
    // nuevas, sin cortar lo que ya suena. Si la nueva acaba antes de ese punto, termina.
    update(next) {
      current = next;
      const state = transport.state;
      const position = state === "started" ? fired : state === "paused" ? transport.ticks : 0;
      if (state !== "stopped" && position >= endTick()) {
        finish();
        return;
      }
      program(position);
    },
    setTempo(bpm) {
      transport.bpm.value = bpm;
    },
    dispose() {
      intent = "stopped";
      transport.stop();
      transport.cancel(0);
      clearTimers();
      // El contexto se cierra tras el fundido; la próxima vista crea otro en su gesto.
      if (shared === context) shared = null;
      fadeOut(context, voices.values(), () => {
        context.dispose();
      });
      voices = new Map();
    },
  };
}
