import { useEffect, useRef, useState, type DragEvent } from "react";
import "../../components/button.css";

interface UploadZoneProps {
  onFiles: (files: File[]) => void;
}

/**
 * Mientras la vista está montada, soltar archivos fuera de la zona no hace nada: el navegador
 * los abriría en la pestaña y la cola se perdería. La zona cancela antes el suyo.
 */
function useBlockStrayDrops() {
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

/** Zona para elegir o soltar imágenes. Acepta varias a la vez. */
export function UploadZone({ onFiles }: UploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  useBlockStrayDrops();

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    const files = [...event.dataTransfer.files];
    if (files.length > 0) onFiles(files);
  };

  return (
    <div
      className="upload"
      data-dragging={dragging}
      onDragEnter={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragOver={(event) => {
        event.preventDefault();
      }}
      onDragLeave={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false);
      }}
      onDrop={handleDrop}
    >
      {/* Lo abre el botón: el campo no es una parada de foco ni se anuncia por separado. */}
      <input
        ref={inputRef}
        className="visually-hidden"
        type="file"
        accept="image/png,image/jpeg"
        multiple
        tabIndex={-1}
        aria-hidden="true"
        onChange={(event) => {
          const files = [...(event.target.files ?? [])];
          if (files.length > 0) onFiles(files);
          event.target.value = "";
        }}
      />
      <button
        type="button"
        className="button button--primary"
        onClick={() => inputRef.current?.click()}
      >
        Elegir imágenes
      </button>
      <p className="upload__hint">
        o arrástralas aquí. PNG o JPEG de partituras impresas, de hasta 20 MB; cada imagen crea una
        sesión.
      </p>
    </div>
  );
}
