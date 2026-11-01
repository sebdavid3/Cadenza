import { useId, useLayoutEffect, useRef, useState } from "react";
import "../../components/button.css";
import { PixelIcon } from "../../components/PixelIcon";
import { midiFile, musicXmlFile, saveFile } from "./download";

/**
 * Tras un reintento, solo se descarga si el archivo llega poco después del clic: es lo que dura
 * la activación del gesto en Chrome, y una descarga que llega minutos después (por ejemplo, al
 * volver la conexión) sería inesperada o el navegador la bloquearía.
 */
export const RETRY_DOWNLOAD_WINDOW_MS = 5_000;

/**
 * Si el botón sigue en la página. Con un efecto de diseño, y no uno pasivo: su limpieza corre al
 * quitar el botón de la página, en la misma confirmación. La de un efecto pasivo puede llegar en
 * otra tarea, y una respuesta que se resuelva en medio (#212) descargaría cuando la vista ya no
 * está.
 */
function useMounted() {
  const mounted = useRef(true);
  useLayoutEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  return mounted;
}

interface DownloadButtonProps {
  sessionId: string;
  /** MusicXML que la vista ya pidió para OSMD: descargar no lo vuelve a pedir. */
  xml: string | undefined;
  status: "loading" | "ready" | "error";
  /** Vuelve a pedir el MusicXML tras un fallo; da el texto, o undefined si falla otra vez. */
  onRetry: () => Promise<string | undefined>;
}

/**
 * «Descargar MusicXML» del estado que se ve. Mientras se prepara no descarga y lo dice; si la
 * exportación falló, pulsarlo la vuelve a pedir y descarga al llegar. El aviso describe el botón
 * y no es una alerta: el fallo ya lo anuncia la partitura.
 */
export function DownloadButton({ sessionId, xml, status, onRetry }: DownloadButtonProps) {
  const hintId = useId();
  const mounted = useMounted();

  async function download() {
    if (status === "ready" && xml !== undefined) {
      saveFile(musicXmlFile(sessionId, xml));
      return;
    }
    if (status !== "error") return;
    const clickedAt = performance.now();
    const fresh = await onRetry();
    // Si la persona ya se fue de la vista o el archivo tardó, no le llega una descarga
    // inesperada: el botón queda listo para pulsarlo otra vez.
    if (fresh === undefined || !mounted.current) return;
    if (performance.now() - clickedAt > RETRY_DOWNLOAD_WINDOW_MS) return;
    saveFile(musicXmlFile(sessionId, fresh));
  }

  const hint =
    status === "loading"
      ? "Preparando el MusicXML…"
      : status === "error"
        ? "No se pudo preparar el MusicXML. Pulsa «Descargar MusicXML» para volver a intentarlo."
        : null;

  return (
    <div className="score-download">
      <button
        type="button"
        className="button button--compact"
        aria-disabled={status === "loading"}
        aria-describedby={hint ? hintId : undefined}
        onClick={() => void download()}
      >
        <PixelIcon name="download" className="button__icon--down" />
        Descargar MusicXML
      </button>
      {hint && (
        <p className="score-download__hint" id={hintId}>
          {hint}
        </p>
      )}
    </div>
  );
}

interface MidiDownloadButtonProps {
  sessionId: string;
  /** Si ya se sabe qué estado se ve: hasta entonces, el botón no pide nada. */
  ready: boolean;
  /** Pide el MIDI del estado que se ve, o lo da de la caché si ya se pidió. */
  fetchMidi: () => Promise<Blob>;
}

type MidiStatus = "idle" | "loading" | "error" | "late";

const MIDI_HINTS: Record<MidiStatus, string | null> = {
  idle: null,
  loading: "Preparando el MIDI…",
  error: "No se pudo preparar el MIDI. Pulsa «Descargar MIDI» para volver a intentarlo.",
  late: "El MIDI ya está listo. Pulsa «Descargar MIDI» para guardarlo.",
};

/**
 * «Descargar MIDI» del estado que se ve (#189). La vista no usa el MIDI, así que solo se pide al
 * pulsarlo; mientras llega, el botón no lo vuelve a pedir y lo dice. Si falla, lo dice y pulsarlo
 * otra vez lo vuelve a pedir. Como en el MusicXML, lo que llega tarde o cuando la vista ya no
 * está no se descarga solo: el botón queda listo para pulsarlo. El fallo y el aviso de listo se
 * anuncian, porque nada más en la vista los dice.
 */
export function MidiDownloadButton({ sessionId, ready, fetchMidi }: MidiDownloadButtonProps) {
  const hintId = useId();
  const mounted = useMounted();
  const busy = useRef(false);
  const [status, setStatus] = useState<MidiStatus>("idle");

  async function download() {
    if (busy.current || !ready) return;
    busy.current = true;
    setStatus("loading");
    const clickedAt = performance.now();
    let midi: Blob;
    try {
      midi = await fetchMidi();
    } catch {
      if (mounted.current) setStatus("error");
      return;
    } finally {
      busy.current = false;
    }
    if (!mounted.current) return;
    if (performance.now() - clickedAt > RETRY_DOWNLOAD_WINDOW_MS) {
      setStatus("late");
      return;
    }
    setStatus("idle");
    saveFile(midiFile(sessionId, midi));
  }

  const hint = MIDI_HINTS[status];
  return (
    <div className="score-download">
      <button
        type="button"
        className="button button--compact"
        aria-disabled={!ready || status === "loading"}
        aria-describedby={hint ? hintId : undefined}
        onClick={() => void download()}
      >
        <PixelIcon name="download" className="button__icon--down" />
        Descargar MIDI
      </button>
      {hint && (
        <p className="score-download__hint" id={hintId}>
          {hint}
        </p>
      )}
      <p className="visually-hidden" role="status">
        {status === "error" || status === "late" ? hint : ""}
      </p>
    </div>
  );
}
