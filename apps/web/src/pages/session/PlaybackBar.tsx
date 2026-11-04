import { useRef } from "react";
import "../../components/button.css";
import { PixelIcon } from "../../components/PixelIcon";
import { beatsToSeconds, MAX_TEMPO, MIN_TEMPO, TEMPO_STEP } from "./playback";
import type { PlayerStatus } from "./player";

interface PlaybackBarProps {
  status: PlayerStatus;
  /** Compás que suena o en el que se pausó. */
  measure: number | null;
  announcement: string;
  tempo: number;
  /** Duración de la partitura en negras, o null mientras se prepara el mapa de tiempos. */
  totalBeats: number | null;
  measureCount: number;
  /** Hay mapa de tiempos pero ninguna nota que suene. */
  silent: boolean;
  /** No llegó el mapa de tiempos o el trozo de Tone.js; `onRetry` lo vuelve a pedir. */
  failure: "timing" | "load" | null;
  onRetry: () => void;
  onPlay: () => void;
  onPause: () => void;
  onStop: () => void;
  onTempo: (bpm: number) => void;
}

function formatDuration(seconds: number): string {
  const total = Math.round(seconds);
  return `${String(Math.floor(total / 60))}:${String(total % 60).padStart(2, "0")}`;
}

/**
 * Transporte de la partitura: reproducir o pausar, detener y tempo, con el compás que suena. Los
 * cambios de estado se anuncian en una región `aria-live`; el compás, no (cambiaría sin parar).
 */
export function PlaybackBar({
  status,
  measure,
  announcement,
  tempo,
  totalBeats,
  measureCount,
  silent,
  failure,
  onRetry,
  onPlay,
  onPause,
  onStop,
  onTempo,
}: PlaybackBarProps) {
  const playButton = useRef<HTMLButtonElement>(null);
  const playing = status === "playing";
  const ready = failure === null && !silent && totalBeats !== null && status !== "loading";
  const stopped = status === "stopped" || status === "error" || status === "loading";

  let readout: string;
  if (failure === "timing") readout = "No se pudo preparar el audio.";
  else if (failure === "load") readout = "No se pudo cargar el audio.";
  else if (silent) readout = "Sin notas que sonar.";
  else if (totalBeats === null || status === "loading") readout = "Preparando el audio…";
  else if (status === "error") readout = "El audio no arrancó en este navegador.";
  else if (measure !== null) readout = `${playing ? "" : "En pausa · "}Compás ${String(measure)}`;
  else
    readout = `${String(measureCount)} ${measureCount === 1 ? "compás" : "compases"} · ${formatDuration(beatsToSeconds(totalBeats, tempo))}`;

  return (
    <div className="playback" data-status={status}>
      <div className="playback__transport" role="group" aria-label="Reproducción">
        <button
          ref={playButton}
          type="button"
          className="playback__button"
          aria-disabled={!ready}
          data-active={playing}
          onClick={() => {
            if (!ready) return;
            if (playing) onPause();
            else onPlay();
          }}
        >
          <PixelIcon name={playing ? "pause" : "play"} />
          {playing ? "Pausa" : "Reproducir"}
        </button>
        <button
          type="button"
          className="playback__button"
          aria-disabled={stopped}
          onClick={() => {
            if (!stopped) onStop();
          }}
        >
          <PixelIcon name="stop" />
          Detener
        </button>
      </div>

      <div className="playback__tempo" role="group" aria-label="Tempo">
        <span className="label playback__tempo-label" aria-hidden="true">
          Tempo
        </span>
        <button
          type="button"
          className="playback__step"
          aria-label="Bajar el tempo"
          aria-disabled={tempo <= MIN_TEMPO}
          onClick={() => {
            if (tempo > MIN_TEMPO) onTempo(tempo - TEMPO_STEP);
          }}
        >
          <PixelIcon name="minus" />
        </button>
        <output className="playback__tempo-value" aria-live="polite">
          {tempo}
          <span className="visually-hidden"> negras por minuto</span>
        </output>
        <button
          type="button"
          className="playback__step"
          aria-label="Subir el tempo"
          aria-disabled={tempo >= MAX_TEMPO}
          onClick={() => {
            if (tempo < MAX_TEMPO) onTempo(tempo + TEMPO_STEP);
          }}
        >
          <PixelIcon name="plus" />
        </button>
      </div>

      <p className="label playback__readout">
        {readout}
        {failure !== null && (
          <>
            {" "}
            <button
              type="button"
              className="link-button"
              onClick={() => {
                // El botón desaparece al reintentar: el foco pasa a «Reproducir», que se queda.
                playButton.current?.focus();
                onRetry();
              }}
            >
              Reintentar el audio
            </button>
          </>
        )}
      </p>
      <p className="visually-hidden" role="status">
        {announcement}
      </p>
    </div>
  );
}
