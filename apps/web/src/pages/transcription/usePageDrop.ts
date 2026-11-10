import { useEffect, useRef, useState } from "react";

/**
 * Mientras se arrastra sobre la página, el navegador repite `dragover` al menos cada 350 ms
 * (±200 ms), aunque el puntero no se mueva. Si deja de llegar, el arrastre se fue: salió de la
 * ventana, se canceló con Esc o se perdió un `dragleave` de un elemento que desapareció.
 */
export const DRAG_IDLE_MS = 1000;

function carriesFiles(event: globalThis.DragEvent): boolean {
  return event.dataTransfer?.types.includes("Files") ?? false;
}

/**
 * Mientras la vista está montada, toda la página recibe las imágenes que se suelten (#370): no
 * hace falta apuntar a una zona. Devuelve si se están arrastrando archivos sobre ella, para
 * avisar. Lo que no son archivos (un texto, un enlace) sigue su curso.
 */
export function usePageDrop(onFiles: (files: File[]) => void): boolean {
  const [dragging, setDragging] = useState(false);
  // Los oyentes se ponen una vez: si cambiara la función, el contador volvería a cero a mitad
  // de un arrastre.
  const onFilesRef = useRef(onFiles);
  useEffect(() => {
    onFilesRef.current = onFiles;
  }, [onFiles]);

  useEffect(() => {
    // dragenter y dragleave llegan por cada elemento que se cruza: se cuentan.
    let depth = 0;
    let idle: ReturnType<typeof setTimeout> | undefined;
    const stop = () => {
      depth = 0;
      clearTimeout(idle);
      setDragging(false);
    };
    const keepAlive = () => {
      clearTimeout(idle);
      idle = setTimeout(stop, DRAG_IDLE_MS);
    };
    const enter = (event: globalThis.DragEvent) => {
      if (!carriesFiles(event)) return;
      depth += 1;
      setDragging(true);
      keepAlive();
    };
    const leave = (event: globalThis.DragEvent) => {
      if (!carriesFiles(event)) return;
      depth = Math.max(0, depth - 1);
      if (depth === 0) stop();
    };
    const over = (event: globalThis.DragEvent) => {
      if (!carriesFiles(event) || !event.dataTransfer) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "copy";
      keepAlive();
    };
    // El navegador abriría el archivo en la pestaña y se perdería lo elegido: se cancela siempre.
    const drop = (event: globalThis.DragEvent) => {
      if (!carriesFiles(event)) return;
      event.preventDefault();
      stop();
      const files = [...(event.dataTransfer?.files ?? [])];
      if (files.length > 0) onFilesRef.current(files);
    };
    window.addEventListener("dragenter", enter);
    window.addEventListener("dragleave", leave);
    window.addEventListener("dragover", over);
    window.addEventListener("drop", drop);
    return () => {
      clearTimeout(idle);
      window.removeEventListener("dragenter", enter);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("dragover", over);
      window.removeEventListener("drop", drop);
    };
  }, []);

  return dragging;
}
