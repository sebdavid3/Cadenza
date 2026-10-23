import { useEffect, useId, useRef } from "react";
import "../../components/button.css";
import { PixelIcon } from "../../components/PixelIcon";
import { musicXmlFile, saveFile } from "./download";

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
 * exportación falló, pulsarlo la vuelve a pedir y descarga al llegar.
 */
export function DownloadButton({ sessionId, xml, status, onRetry }: DownloadButtonProps) {
  const hintId = useId();
  const mounted = useRef(true);
  useEffect(() => {
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
    const fresh = await onRetry();
    // Si la persona ya se fue de la vista, no le llega una descarga inesperada.
    if (fresh !== undefined && mounted.current) saveFile(musicXmlFile(sessionId, fresh));
  }

  const hint =
    status === "loading"
      ? "Preparando el MusicXML…"
      : status === "error"
        ? "No se pudo preparar el MusicXML. Púlsalo para volver a intentarlo."
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
        <PixelIcon name="download" />
        Descargar MusicXML
      </button>
      {hint && (
        <p
          className="score-download__hint"
          id={hintId}
          role={status === "error" ? "alert" : undefined}
        >
          {hint}
        </p>
      )}
    </div>
  );
}
