import { useLayoutEffect, useRef, useState } from "react";

/** Una imagen mucho más ancha que alta (un incipit de un pentagrama) no se encoge en móvil. */
const WIDE_RATIO = 3;

interface ScanFigureProps {
  blob: Blob | null;
  status: "loading" | "ready" | "error";
}

/**
 * Imagen original de la sesión. `GET /sessions/{id}/image` exige Bearer, así que llega como Blob
 * (handoff §5.6); la URL se crea al montar y se revoca al desmontar. Es una referencia global:
 * HOMR no da coordenadas, así que no se marca nada sobre ella (INV-0001).
 */
export function ScanFigure({ blob, status }: ScanFigureProps) {
  const imageRef = useRef<HTMLImageElement>(null);
  const [wide, setWide] = useState(false);

  useLayoutEffect(() => {
    const element = imageRef.current;
    if (!blob || !element) return;
    const url = URL.createObjectURL(blob);
    element.src = url;
    return () => {
      element.removeAttribute("src");
      URL.revokeObjectURL(url);
    };
  }, [blob]);

  if (status === "error") {
    return (
      <div className="scan scan--empty">
        <p>No se pudo cargar la imagen original.</p>
      </div>
    );
  }
  if (!blob) {
    return (
      <div className="scan scan--empty" aria-busy="true">
        <p className="label">Cargando la imagen…</p>
      </div>
    );
  }
  return (
    // Un incipit ancho se desplaza en horizontal en móvil: el marco se puede enfocar para
    // desplazarlo con el teclado.
    <div
      className="scan"
      data-wide={wide}
      tabIndex={wide ? 0 : undefined}
      role={wide ? "group" : undefined}
      aria-label={wide ? "Imagen original, desplazable" : undefined}
    >
      <img
        ref={imageRef}
        alt="Imagen original de la partitura"
        decoding="async"
        onLoad={(event) => {
          const { naturalWidth, naturalHeight } = event.currentTarget;
          setWide(naturalHeight > 0 && naturalWidth / naturalHeight > WIDE_RATIO);
        }}
      />
    </div>
  );
}
