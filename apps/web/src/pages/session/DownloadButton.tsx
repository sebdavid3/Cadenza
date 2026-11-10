import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import "../../components/button.css";
import { PixelIcon } from "../../components/PixelIcon";
import { midiFile, musicXmlFile, pdfFile, saveFile, type DownloadFile } from "./download";

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

interface PreparedDownloadProps {
  sessionId: string;
  /** Estado que se ve: el aviso de un estado anterior no pasa a este. */
  seq: number;
  /** Si ya se sabe qué estado se ve: hasta entonces, el botón no pide nada. */
  ready: boolean;
  /**
   * Si el archivo se está preparando (#363): la vista deja abierto el panel que lo contiene, para
   * que su aviso se vea y se anuncie al llegar.
   */
  onPreparing?: (preparing: boolean) => void;
}

interface OnDemandDownloadButtonProps extends PreparedDownloadProps {
  /** Cómo se llama lo que se descarga, con artículo masculino: «MIDI», «PDF». */
  noun: string;
  /** Prepara el archivo del estado que se ve, o lo da hecho si ya se preparó. */
  prepare: () => Promise<Blob>;
  /** El archivo que se guarda, con su nombre y su tipo. */
  toFile: (sessionId: string, blob: Blob) => DownloadFile;
}

type PreparedStatus = "idle" | "loading" | "error" | "late";

function preparedHint(noun: string, status: PreparedStatus): string | null {
  switch (status) {
    case "idle":
      return null;
    case "loading":
      return `Preparando el ${noun}…`;
    case "error":
      return `No se pudo preparar el ${noun}. Pulsa «Descargar ${noun}» para volver a intentarlo.`;
    case "late":
      return `El ${noun} ya está listo. Pulsa «Descargar ${noun}» para guardarlo.`;
  }
}

/**
 * Una descarga que solo se prepara al pulsarla (el MIDI, #189; el PDF, #376): mientras llega, el
 * botón no la vuelve a pedir y lo dice. Si falla, lo dice y pulsarlo otra vez la vuelve a pedir.
 * Como en el MusicXML, lo que llega tarde o cuando la vista ya no está no se descarga solo: el
 * botón queda listo para pulsarlo. El fallo y el aviso de listo se anuncian, porque nada más en la
 * vista los dice.
 */
function OnDemandDownloadButton({
  sessionId,
  seq,
  ready,
  onPreparing,
  noun,
  prepare,
  toFile,
}: OnDemandDownloadButtonProps) {
  const hintId = useId();
  const mounted = useMounted();
  const busy = useRef(false);
  const [status, setStatus] = useState<PreparedStatus>("idle");
  // Con otro estado, «listo» o «no se pudo» ya no hablan de lo que se ve: el botón vuelve a
  // estar sin aviso. Lo que se está preparando sigue y se descarga al llegar.
  const [statusSeq, setStatusSeq] = useState(seq);
  if (statusSeq !== seq) {
    setStatusSeq(seq);
    if (status !== "loading") setStatus("idle");
  }

  async function download() {
    if (busy.current || !ready) return;
    busy.current = true;
    setStatus("loading");
    const clickedAt = performance.now();
    let blob: Blob;
    try {
      blob = await prepare();
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
    saveFile(toFile(sessionId, blob));
  }

  const preparing = status === "loading";
  useEffect(() => {
    onPreparing?.(preparing);
  }, [onPreparing, preparing]);
  useEffect(
    () => () => {
      onPreparing?.(false);
    },
    [onPreparing],
  );

  const hint = preparedHint(noun, status);
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
        Descargar {noun}
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

interface MidiDownloadButtonProps extends PreparedDownloadProps {
  /** Pide el MIDI del estado que se ve, o lo da de la caché si ya se pidió. */
  fetchMidi: () => Promise<Blob>;
}

/** «Descargar MIDI» del estado que se ve (#189). La vista no usa el MIDI: se pide al pulsarlo. */
export function MidiDownloadButton({ fetchMidi, ...props }: MidiDownloadButtonProps) {
  return <OnDemandDownloadButton {...props} noun="MIDI" prepare={fetchMidi} toFile={midiFile} />;
}

interface PdfDownloadButtonProps extends PreparedDownloadProps {
  /** Dibuja el PDF del estado que se ve, o lo da hecho si ya se dibujó (#376). */
  makePdf: () => Promise<Blob>;
}

/** «Descargar PDF» del estado que se ve (#376): se dibuja en el navegador al pulsarlo. */
export function PdfDownloadButton({ makePdf, ...props }: PdfDownloadButtonProps) {
  return <OnDemandDownloadButton {...props} noun="PDF" prepare={makePdf} toFile={pdfFile} />;
}
