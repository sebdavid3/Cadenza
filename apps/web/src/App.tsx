import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { clearToken, fetchMe, getToken, logout, onUnauthorized } from "./api/client";
import { HitlWorkspace } from "./components/HitlWorkspace";
import { LoginPanel } from "./components/LoginPanel";
import { UploadPanel } from "./components/UploadPanel";
import { useEditorStore } from "./store/editorStore";
import type { UserProfile } from "./types";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});

interface ActiveSession {
  id: string;
  imageUrl: string;
}

export function App() {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [session, setSession] = useState<ActiveSession | null>(null);
  const [loadingUser, setLoadingUser] = useState<boolean>(true);
  const setAuthor = useEditorStore((state) => state.setAuthor);

  useEffect(() => {
    const token = getToken();
    if (token) {
      fetchMe()
        .then((profile) => {
          setUser(profile);
          setAuthor(profile.username);
        })
        .catch(() => {
          clearToken();
          setUser(null);
        })
        .finally(() => {
          setLoadingUser(false);
        });
    } else {
      setLoadingUser(false);
    }

    return onUnauthorized(() => {
      setUser(null);
      setSession(null);
    });
  }, [setAuthor]);

  function handleLogout() {
    logout();
    setUser(null);
    setSession(null);
  }

  function handleLoggedIn(loggedInUser: UserProfile) {
    setUser(loggedInUser);
    setAuthor(loggedInUser.username);
  }

  if (loadingUser) {
    return (
      <div className="upload">
        <p className="muted">Cargando…</p>
      </div>
    );
  }

  if (!user) {
    return <LoginPanel onLoggedIn={handleLoggedIn} />;
  }

  return (
    <QueryClientProvider client={queryClient}>
      {!session && (
        <header className="workspace-header" style={{ justifyContent: "space-between" }}>
          <h1>Cadenza · HITL</h1>
          <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
            <span className="muted">
              {user.username} ({user.role})
            </span>
            <button type="button" onClick={handleLogout}>
              Cerrar sesión
            </button>
          </div>
        </header>
      )}
      {session ? (
        <HitlWorkspace
          sessionId={session.id}
          imageUrl={session.imageUrl}
          user={user}
          onLogout={handleLogout}
          onReset={() => setSession(null)}
        />
      ) : (
        <UploadPanel onTranscribed={(id, imageUrl) => setSession({ id, imageUrl })} />
      )}
    </QueryClientProvider>
  );
}
