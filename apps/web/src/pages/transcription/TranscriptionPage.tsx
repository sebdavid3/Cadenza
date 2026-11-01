import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api } from "../../api/instance";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { PreparePanel } from "./PreparePanel";
import { useQueueStore } from "./queue";
import { QueuePanel } from "./QueuePanel";
import { refreshSessions } from "./sessions";
import { SessionsPanel } from "./SessionsPanel";
import "./transcription.css";
import { UploadZone } from "./UploadZone";

export function TranscriptionPage() {
  useDocumentTitle("Transcripción");
  const queryClient = useQueryClient();
  const prepare = useQueueStore((state) => state.prepare);
  const preparing = useQueueStore((state) => state.prepared.length > 0);
  const uploadRef = useRef<HTMLButtonElement>(null);
  // Imágenes que ya esperaban al montar la vista (se salió y se volvió): el foco no salta a ellas.
  // Se ajusta al dibujar, no en un efecto: en cuanto se vacía, lo siguiente que se prepare es nuevo.
  const [restored, setRestored] = useState(preparing);
  if (restored && !preparing) setRestored(false);
  const running = useQueueStore((state) => state.running);
  const paused = useQueueStore((state) => state.paused);
  const hasQueued = useQueueStore((state) => state.items.some((item) => item.status === "queued"));

  // La cola avanza sola mientras haya pendientes; la interfaz sigue disponible entretanto. Tras
  // cada envío se actualiza el listado, también si falló: la sesión puede haberse creado.
  useEffect(() => {
    if (!hasQueued || running || paused) return;
    void useQueueStore.getState().run(api, () => {
      refreshSessions(queryClient);
    });
  }, [hasQueued, running, paused, queryClient]);

  return (
    <main className="transcription">
      <section className="transcription__intake" aria-labelledby="transcription-title">
        <h1 id="transcription-title" className="transcription__title">
          Transcribir partituras
        </h1>
        <p className="transcription__lead">
          HOMR transcribe cada imagen y crea una sesión de trabajo con los compases que el validador
          señala. Las imágenes se envían de una en una; puedes seguir añadiendo mientras tanto.
        </p>
        <UploadZone onFiles={prepare} buttonRef={uploadRef} />
        {preparing && (
          <PreparePanel
            focusOnOpen={!restored}
            onSent={() => {
              document.getElementById("queue-title")?.focus();
            }}
            onClosed={() => {
              uploadRef.current?.focus();
            }}
          />
        )}
      </section>
      <div className="transcription__panels">
        <QueuePanel />
        <SessionsPanel />
      </div>
    </main>
  );
}
