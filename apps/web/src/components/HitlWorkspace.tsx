import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";

import { fetchSession } from "../api/client";
import { useEditorStore } from "../store/editorStore";
import type { UserProfile } from "../types";
import { EffortMetrics } from "./EffortMetrics";
import { EventInspector } from "./EventInspector";
import { FindingsPanel } from "./FindingsPanel";
import { HistoryPanel } from "./HistoryPanel";
import { ImageOverlay } from "./ImageOverlay";

interface HitlWorkspaceProps {
  sessionId: string;
  imageUrl: string;
  user?: UserProfile | null;
  onLogout?: () => void;
  onReset: () => void;
}

export function HitlWorkspace({
  sessionId,
  imageUrl,
  user,
  onLogout,
  onReset,
}: HitlWorkspaceProps) {
  const loadSession = useEditorStore((state) => state.loadSession);
  const reset = useEditorStore((state) => state.reset);
  const query = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => fetchSession(sessionId),
  });

  useEffect(() => {
    if (query.data) {
      loadSession(query.data, imageUrl);
    }
  }, [query.data, imageUrl, loadSession]);

  if (query.isLoading) {
    return <p className="muted">Cargando sesión…</p>;
  }
  if (query.isError) {
    return <p className="error">Error: {String(query.error)}</p>;
  }

  return (
    <div className="workspace">
      <header className="workspace-header">
        <h1>Cadenza · HITL</h1>
        <span className="muted">sesión {sessionId.slice(0, 8)}</span>
        {user && (
          <span className="muted" style={{ marginLeft: "auto" }}>
            {user.username} ({user.role})
          </span>
        )}
        <button
          type="button"
          style={!user ? { marginLeft: "auto" } : undefined}
          onClick={() => {
            reset();
            onReset();
          }}
        >
          Nueva sesión
        </button>
        {onLogout && (
          <button type="button" onClick={onLogout}>
            Cerrar sesión
          </button>
        )}
      </header>
      <main className="workspace-grid">
        <section className="pane pane--image">
          <ImageOverlay />
        </section>
        <section className="pane">
          <h2>Hallazgos</h2>
          <FindingsPanel />
        </section>
        <section className="pane">
          <h2>Inspector</h2>
          <EventInspector />
        </section>
        <section className="pane">
          <h2>Historial</h2>
          <HistoryPanel />
          <h2>Esfuerzo cognitivo</h2>
          <EffortMetrics />
        </section>
      </main>
    </div>
  );
}
