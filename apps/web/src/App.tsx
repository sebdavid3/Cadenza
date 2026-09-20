import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

import { HitlWorkspace } from "./components/HitlWorkspace";
import { UploadPanel } from "./components/UploadPanel";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});

interface ActiveSession {
  id: string;
  imageUrl: string;
}

export function App() {
  const [session, setSession] = useState<ActiveSession | null>(null);

  return (
    <QueryClientProvider client={queryClient}>
      {session ? (
        <HitlWorkspace
          sessionId={session.id}
          imageUrl={session.imageUrl}
          onReset={() => setSession(null)}
        />
      ) : (
        <UploadPanel onTranscribed={(id, imageUrl) => setSession({ id, imageUrl })} />
      )}
    </QueryClientProvider>
  );
}
