import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { api } from "../../api/instance";
import { useAuthStore } from "../../auth/store";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { hasPendingWork, useQueueStore } from "./queue";
import { QueuePanel } from "./QueuePanel";
import { SESSIONS_QUERY_KEY } from "./sessions";
import { SessionsPanel } from "./SessionsPanel";
import "./transcription.css";
import { UploadZone } from "./UploadZone";

export function TranscriptionPage() {
  useDocumentTitle("Transcripción");
  const queryClient = useQueryClient();
  const userId = useAuthStore((state) => state.user?.id);
  const add = useQueueStore((state) => state.add);
  const claim = useQueueStore((state) => state.claim);
  const running = useQueueStore((state) => state.running);
  const hasQueued = useQueueStore((state) => state.items.some((item) => item.status === "queued"));
  const pending = useQueueStore((state) => hasPendingWork(state.items));

  useEffect(() => {
    if (userId) claim(userId);
  }, [userId, claim]);

  // Cerrar o recargar la pestaña a mitad de un lote perdería la cola: el navegador pide confirmación.
  useEffect(() => {
    if (!pending) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => {
      window.removeEventListener("beforeunload", warn);
    };
  }, [pending]);

  // La cola avanza sola mientras haya pendientes; la interfaz sigue disponible entretanto.
  useEffect(() => {
    if (!hasQueued || running) return;
    void useQueueStore.getState().run(api, () => {
      void queryClient.invalidateQueries({ queryKey: SESSIONS_QUERY_KEY });
    });
  }, [hasQueued, running, queryClient]);

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
