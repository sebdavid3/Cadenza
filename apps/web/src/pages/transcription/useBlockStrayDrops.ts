import { useEffect } from "react";

/**
 * Mientras la vista está montada, soltar archivos fuera de la zona no hace nada: el navegador
 * los abriría en la pestaña y se perdería lo elegido (la cola, o la imagen y el resultado de la
 * portada). La zona cancela antes el suyo.
 */
export function useBlockStrayDrops() {
  useEffect(() => {
    const block = (event: globalThis.DragEvent) => {
      if (event.defaultPrevented || !event.dataTransfer?.types.includes("Files")) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "none";
    };
    window.addEventListener("dragover", block);
    window.addEventListener("drop", block);
    return () => {
      window.removeEventListener("dragover", block);
      window.removeEventListener("drop", block);
    };
  }, []);
}
