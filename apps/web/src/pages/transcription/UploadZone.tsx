import { useRef, useState, type DragEvent, type Ref } from "react";
import "../../components/button.css";
import { useBlockStrayDrops } from "./useBlockStrayDrops";

interface UploadZoneProps {
  onFiles: (files: File[]) => void;
  buttonRef?: Ref<HTMLButtonElement>;
  /** Si se pueden elegir varias a la vez; la portada pide una sola (#277). */
  multiple?: boolean;
  buttonLabel?: string;
  hint?: string;
  className?: string;
}

const BATCH_HINT =
  "o arrástralas aquí. PNG o JPEG de partituras impresas, de hasta 20 MB; cada imagen crea una sesión. Antes de transcribirlas podrás darles nombre e instrumentos.";

/** Zona para elegir o soltar imágenes. Por defecto acepta varias a la vez. */
export function UploadZone({
  onFiles,
  buttonRef,
  multiple = true,
  buttonLabel = "Elegir imágenes",
  hint = BATCH_HINT,
  className = "upload",
}: UploadZoneProps) {
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
      className={className}
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
        multiple={multiple}
        tabIndex={-1}
        aria-hidden="true"
        onChange={(event) => {
          const files = [...(event.target.files ?? [])];
          if (files.length > 0) onFiles(files);
          event.target.value = "";
        }}
      />
      <button
        ref={buttonRef}
        type="button"
        className="button button--primary"
        onClick={() => inputRef.current?.click()}
      >
        {buttonLabel}
      </button>
      <p className="upload__hint">{hint}</p>
    </div>
  );
}
