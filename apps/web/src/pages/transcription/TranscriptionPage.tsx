import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { api } from "../../api/instance";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { useQueueStore } from "./queue";
import { QueuePanel } from "./QueuePanel";
import { refreshSessions } from "./sessions";
import { SessionsPanel } from "./SessionsPanel";
import "./transcription.css";
import { UploadZone } from "./UploadZone";

export function TranscriptionPage() {
  useDocumentTitle("Transcripción");
  const queryClient = useQueryClient();
  const add = useQueueStore((state) => state.add);
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
        <UploadZone onFiles={add} />
      </section>
      <div className="transcription__panels">
        <QueuePanel />
        <SessionsPanel />
      </div>
    </main>
  );
}
