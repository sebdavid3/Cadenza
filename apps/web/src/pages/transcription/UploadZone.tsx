import { useId, useRef, useState, type DragEvent } from "react";
import "../../components/button.css";

interface UploadZoneProps {
  onFiles: (files: File[]) => void;
}

/** Zona para elegir o soltar imágenes. Acepta varias a la vez. */
export function UploadZone({ onFiles }: UploadZoneProps) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

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
      <input
        ref={inputRef}
        id={inputId}
        className="visually-hidden"
        type="file"
        accept="image/png,image/jpeg"
        multiple
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
        o arrástralas aquí. PNG o JPEG de partituras impresas, de hasta 20 MB y una página por
        imagen.
      </p>
    </div>
  );
}
