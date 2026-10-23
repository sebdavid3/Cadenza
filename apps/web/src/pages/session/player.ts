import { useCallback, useEffect, useRef, useState } from "react";
import { DEFAULT_TEMPO, MAX_TEMPO, MIN_TEMPO, type Playback } from "./playback";

/** Avisos del motor de audio a la vista, cuando suena cada instante. */
export interface EngineHandlers {
  onMeasure(measure: number): void;
  onEnd(): void;
}

/** Motor de audio de una partitura (ADR-0026). La implementación real es la de Tone.js. */
export interface PlaybackEngine {
  /** Arranca o reanuda. Se llama dentro del gesto de la persona: el audio no arranca sin él. */
  play(): Promise<void>;
  pause(): void;
  /** Vuelve al principio y calla lo que suene. */
  stop(): void;
  setTempo(bpm: number): void;
  dispose(): void;
}

export type CreateEngine = (
  playback: Playback,
  tempo: number,
  handlers: EngineHandlers,
) => PlaybackEngine;

/**
 * Tone.js se carga bajo demanda, cuando la vista tiene algo que reproducir. Antes se le pide que
 * no escriba su versión en la consola: lo comprueba al evaluarse, y va en su propio trozo. Es un
 * objeto para que las pruebas puedan simular que el trozo no llega.
 */
export const engineLoader = {
  load(): Promise<CreateEngine> {
    (globalThis as { TONE_SILENCE_LOGGING?: boolean }).TONE_SILENCE_LOGGING = true;
    return import("./toneEngine").then((module) => module.createToneEngine);
  },
};

export type PlayerStatus = "loading" | "stopped" | "playing" | "paused" | "error";

interface PlayerState {
  status: Exclude<PlayerStatus, "loading">;
  /** Compás que suena (o en el que se pausó); null si está detenido. */
  measure: number | null;
  /** Último cambio de estado, para la región `aria-live`. */
  announcement: string;
}

const STOPPED: PlayerState = { status: "stopped", measure: null, announcement: "" };

export function clampTempo(bpm: number): number {
  return Math.min(MAX_TEMPO, Math.max(MIN_TEMPO, Math.round(bpm)));
}

/**
 * Transporte de la vista de una sesión: reproducir, pausar, detener y tempo. El motor se crea
 * en el primer «Reproducir» (dentro del gesto) y se libera al salir de la vista o si cambia lo
 * que se reproduce. Si la página deja de verse, se pausa: con el reloj por `setTimeout`, el
 * navegador lo frena en segundo plano y las notas llegarían a destiempo.
 */
export function usePlayer(playback: Playback | null) {
  const [create, setCreate] = useState<CreateEngine | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  // Cada reintento de carga vuelve a pedir el trozo (tras un redespliegue, el viejo da 404).
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [state, setState] = useState<PlayerState>(STOPPED);
  const [tempo, setTempoState] = useState(DEFAULT_TEMPO);
  const engineRef = useRef<PlaybackEngine | null>(null);
  const tempoRef = useRef(tempo);

  const wanted = playback !== null && playback.notes.length > 0;
  const loaded = create !== null;
  useEffect(() => {
    if (!wanted || loaded) return;
    let active = true;
    engineLoader
      .load()
      .then((loaded) => {
        if (active) setCreate(() => loaded);
      })
      .catch(() => {
        if (active) setLoadFailed(true);
      });
    return () => {
      active = false;
    };
  }, [wanted, loaded, loadAttempt]);

  const retryLoad = useCallback(() => {
    setLoadFailed(false);
    setLoadAttempt((attempt) => attempt + 1);
  }, []);

  // Otra partitura (u otra vista) no hereda el motor ni lo que estaba sonando.
  useEffect(
    () => () => {
      engineRef.current?.dispose();
      engineRef.current = null;
      setState(STOPPED);
    },
    [playback],
  );

  const play = useCallback(() => {
    if (!playback || !create || playback.notes.length === 0) return;
    let engine = engineRef.current;
    if (!engine) {
      try {
        engine = create(playback, tempoRef.current, {
          onMeasure: (measure) => {
            setState((previous) => ({ ...previous, measure }));
          },
          onEnd: () => {
            setState({ status: "stopped", measure: null, announcement: "Fin de la partitura." });
          },
        });
      } catch {
        setState({ ...STOPPED, status: "error", announcement: "No se pudo iniciar el audio." });
        return;
      }
      engineRef.current = engine;
    }
    const started = engine;
    setState((previous) => ({ ...previous, status: "playing", announcement: "Reproduciendo." }));
    started.play().catch(() => {
      started.stop();
      setState({ ...STOPPED, status: "error", announcement: "No se pudo iniciar el audio." });
    });
  }, [playback, create]);

  const pause = useCallback(() => {
    engineRef.current?.pause();
    setState((previous) =>
      previous.status === "playing"
        ? { ...previous, status: "paused", announcement: "En pausa." }
        : previous,
    );
  }, []);

  const stop = useCallback(() => {
    engineRef.current?.stop();
    setState((previous) =>
      previous.status === "stopped" ? previous : { ...STOPPED, announcement: "Detenido." },
    );
  }, []);

  const setTempo = useCallback((bpm: number) => {
    const next = clampTempo(bpm);
    tempoRef.current = next;
    setTempoState(next);
    engineRef.current?.setTempo(next);
  }, []);

  const playing = state.status === "playing";
  useEffect(() => {
    if (!playing) return;
    const onVisibility = () => {
      if (document.visibilityState === "hidden") pause();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [playing, pause]);

  const status: PlayerStatus = wanted && !create && !loadFailed ? "loading" : state.status;
  return {
    status,
    measure: state.measure,
    announcement: loadFailed ? "No se pudo cargar el audio." : state.announcement,
    /** El trozo de Tone.js no llegó: no se puede reproducir hasta volver a pedirlo. */
    loadFailed,
    retryLoad,
    tempo,
    play,
    pause,
    stop,
    setTempo,
  };
}
