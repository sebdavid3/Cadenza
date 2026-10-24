import { useId, useLayoutEffect, useRef } from "react";
import "../../components/button.css";
import { PixelIcon } from "../../components/PixelIcon";
import { musicXmlFile, saveFile } from "./download";

/**
 * Tras un reintento, solo se descarga si el archivo llega poco después del clic: es lo que dura
 * la activación del gesto en Chrome, y una descarga que llega minutos después (por ejemplo, al
 * volver la conexión) sería inesperada o el navegador la bloquearía.
 */
export const RETRY_DOWNLOAD_WINDOW_MS = 5_000;

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
  const mounted = useRef(true);
  // Con un efecto de diseño, y no uno pasivo: su limpieza corre al quitar el botón de la página,
  // en la misma confirmación. La de un efecto pasivo puede llegar en otra tarea, y una respuesta
  // que se resuelva en medio (#212) descargaría cuando la vista ya no está.
  useLayoutEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

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
