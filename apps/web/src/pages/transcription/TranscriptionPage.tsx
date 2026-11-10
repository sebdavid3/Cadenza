import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type Ref } from "react";
import { api } from "../../api/instance";
import { useAuthStore } from "../../auth/store";
import "../../components/button.css";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { PreparePanel } from "./PreparePanel";
import { queueSummary } from "./format";
import { useQueueStore } from "./queue";
import { refreshSessions } from "./sessions";
import { SessionsDiary } from "./SessionsDiary";
import "./transcription.css";
import { usePageDrop } from "./usePageDrop";

interface PickImagesProps {
  onFiles: (files: File[]) => void;
  buttonRef: Ref<HTMLButtonElement>;
}

/** «Nueva transcripción»: abre el selector de imágenes; también se pueden soltar en la página. */
function PickImages({ onFiles, buttonRef }: PickImagesProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <div className="transcription__pick">
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
      {/* Lo que se admite se ve antes de elegir; soltar solo se ofrece con ratón. */}
      <p className="transcription__hint">
        <span className="transcription__drop-hint">
          o suéltalas en cualquier parte de la página.{" "}
        </span>
        <span id="pick-hint">PNG o JPEG, de hasta 20 MB.</span>
      </p>
      <button
        ref={buttonRef}
        id="new-transcription"
        type="button"
        className="button button--primary"
        aria-describedby="pick-hint"
        onClick={() => inputRef.current?.click()}
      >
        Nueva transcripción
      </button>
    </div>
  );
}

export function TranscriptionPage() {
  useDocumentTitle("Transcripción");
  const queryClient = useQueryClient();
  const isResearcher = useAuthStore((state) => state.user?.role === "investigador");
  const prepare = useQueueStore((state) => state.prepare);
  const preparing = useQueueStore((state) => state.prepared.length > 0);
  const uploadRef = useRef<HTMLButtonElement>(null);
  const dragging = usePageDrop(prepare);
  // Imágenes que ya esperaban al montar la vista (se salió y se volvió): el foco no salta a ellas.
  // Se ajusta al dibujar, no en un efecto: en cuanto se vacía, lo siguiente que se prepare es nuevo.
  const [restored, setRestored] = useState(preparing);
  if (restored && !preparing) setRestored(false);
  const running = useQueueStore((state) => state.running);
  const paused = useQueueStore((state) => state.paused);
  // Imágenes por subir o transcripciones que siguen en el servidor (#375).
  const hasWork = useQueueStore((state) =>
    state.items.some((item) => item.status === "queued" || item.status === "transcribing"),
  );
  const ownerId = useAuthStore((state) => state.user?.id ?? null);
  // El recuento de la cola se anuncia desde aquí: la cola solo existe con imágenes, y una región
  // viva que aparece ya llena no se anuncia (una imagen rechazada con la cola vacía).
  const summary = useQueueStore((state) =>
    state.items.length > 0 ? queueSummary(state.items) : "",
  );
  // Tras enviar el lote, el foco pasa a la cola, que aparece en el día de hoy al dibujarse.
  const focusQueue = useRef(false);
  useEffect(() => {
    if (!focusQueue.current) return;
    const title = document.getElementById("queue-title");
    if (!title) return;
    focusQueue.current = false;
    title.focus();
  });

  // Al entrar en la vista, o con otra persona dentro: las transcripciones suyas que siguen en el
  // servidor, también las de antes de recargar la página o de la portada (#375).
  useEffect(() => {
    if (ownerId === null) return;
    void useQueueStore.getState().restore(api);
  }, [ownerId]);

  // La cola avanza sola mientras haya pendientes; la interfaz sigue disponible entretanto. Cada
  // vez que una transcripción termina se actualiza el listado, también si falló.
  useEffect(() => {
    if (!hasWork || running || paused) return;
    void useQueueStore.getState().run(api, () => {
      refreshSessions(queryClient);
    });
  }, [hasWork, running, paused, queryClient]);

  return (
    <main className="transcription" aria-labelledby="transcription-title">
      <div className="transcription__bar">
        <div className="transcription__heading">
          <h1 id="transcription-title" className="transcription__title" tabIndex={-1}>
            Transcripciones
          </h1>
          <p className="label transcription__scope">
            {isResearcher ? "Todas las sesiones" : "Tus sesiones"} · la más reciente primero
          </p>
        </div>
        <PickImages onFiles={prepare} buttonRef={uploadRef} />
      </div>
      {preparing && (
        <div className="transcription__prepare">
          <PreparePanel
            focusOnOpen={!restored}
            onSent={() => {
              focusQueue.current = true;
            }}
            onClosed={() => {
              uploadRef.current?.focus();
            }}
          />
        </div>
      )}
      <p className="visually-hidden" role="status">
        {summary && `Cola: ${summary}`}
      </p>
      <SessionsDiary />
      {/* El aviso cubre la página sin recibir el arrastre: lo recibe la ventana. */}
      {dragging && (
        <div className="transcription__drop" aria-hidden="true">
          <div className="transcription__drop-card">
            <p className="transcription__drop-title">Suelta las imágenes</p>
            <p>
              PNG o JPEG de partituras impresas, de hasta 20 MB; cada imagen crea una sesión. Antes
              de transcribirlas podrás darles nombre e instrumentos.
            </p>
          </div>
        </div>
      )}
    </main>
  );
}
