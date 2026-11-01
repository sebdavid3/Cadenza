import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import "../../components/button.css";
import type { PartInstrumentRead } from "../../types";
import { draftFromMetadata, type ScoreDataDraft } from "../transcription/scoreData";
import { ScoreDataFields, type PartField } from "../transcription/ScoreDataFields";
import type { MetadataMessage } from "./metadata";
import "./score-data-panel.css";

interface ScoreDataPanelProps {
  /** Los datos que se ven ahora. */
  metadata: {
    title?: string | null;
    composer?: string | null;
    instruments?: PartInstrumentRead[];
  };
  /** Pentagramas de cada parte de la partitura, en su orden. */
  staves: number[];
  /** Cómo se llama la sesión si se deja sin nombre. */
  fallbackName: string;
  saving: boolean;
  /**
   * Otra orden en curso (una corrección, una revalidación, finalizar): guardar espera, porque la
   * respuesta de esa orden traería el MusicXML con los datos de antes.
   */
  waiting: boolean;
  message: MetadataMessage;
  onSave: (draft: ScoreDataDraft) => Promise<boolean>;
  onDismissMessage: () => void;
}

const partFields = (staves: number[]): PartField[] =>
  staves.map((count, index) => ({
    label: `Parte ${String(index + 1)} · ${String(count)} ${count === 1 ? "pentagrama" : "pentagramas"}`,
  }));

/**
 * Cambiar el nombre, el compositor y los instrumentos de una sesión desde su vista (#240,
 * ADR-0045), con `PATCH /sessions/{id}`. Solo para quien la transcribió, también finalizada: no es
 * una corrección y no pasa por el log. El formulario se abre bajo el botón, como la confirmación
 * de finalizar, y lo escrito no se da por guardado sin la respuesta.
 */
export function ScoreDataPanel({
  metadata,
  staves,
  fallbackName,
  saving,
  waiting,
  message,
  onSave,
  onDismissMessage,
}: ScoreDataPanelProps) {
  const [draft, setDraft] = useState<ScoreDataDraft | null>(null);
  const formId = useId();
  const waitId = useId();
  const blocked = saving || waiting;
  const toggleRef = useRef<HTMLButtonElement>(null);
  const titleRef = useRef<HTMLInputElement>(null);
  const open = draft !== null;
  useEffect(() => {
    if (open) titleRef.current?.focus();
  }, [open]);

  function close() {
    setDraft(null);
    toggleRef.current?.focus();
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!draft || blocked) return;
    if (await onSave(draft)) close();
  }

  function onKeyDown(event: KeyboardEvent) {
    if (event.key !== "Escape" || saving) return;
    event.preventDefault();
    close();
  }

  return (
    <div className="score-data-panel">
      <button
        ref={toggleRef}
        type="button"
        className="button button--compact"
        aria-expanded={open}
        aria-controls={open ? formId : undefined}
        aria-disabled={(saving && open) || undefined}
        onClick={() => {
          if (saving) return;
          if (open) {
            close();
            return;
          }
          onDismissMessage();
          setDraft(draftFromMetadata(metadata, staves.length));
        }}
      >
        Cambiar los datos
      </button>
      {draft && (
        <form
          id={formId}
          className="score-data-panel__form"
          aria-label="Datos de la partitura"
          onSubmit={(event) => void onSubmit(event)}
          onKeyDown={onKeyDown}
          noValidate
        >
          <ScoreDataFields
            value={draft}
            onChange={setDraft}
            parts={partFields(staves)}
            titleRef={titleRef}
            titleHint={`Sin nombre, se llama «${fallbackName}».`}
            readOnly={saving}
          />
          <p className="score-data-panel__note">
            Los instrumentos son los que suenan al reproducirla y los que lleva lo descargado. No es
            una corrección: no cuenta como edición.
          </p>
          <div className="score-data-panel__actions">
            <button
              type="submit"
              className="button button--compact button--primary"
              aria-disabled={blocked || undefined}
              aria-describedby={waiting && !saving ? waitId : undefined}
            >
              {saving ? "Guardando…" : "Guardar"}
            </button>
            <button
              type="button"
              className="link-button"
              aria-disabled={saving || undefined}
              onClick={() => {
                if (!saving) close();
              }}
            >
              Cancelar
            </button>
          </div>
          {waiting && !saving && (
            <p id={waitId} className="score-data-panel__wait">
              Espera a que termine lo que está en curso.
            </p>
          )}
        </form>
      )}
      {message?.kind === "failed" ? (
        <p className="score-data-panel__error" role="alert">
          {message.text}
        </p>
      ) : (
        <p className="score-data-panel__status" role="status" aria-live="polite">
          {message?.text}
        </p>
      )}
    </div>
  );
}
