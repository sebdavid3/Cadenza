import { useState } from "react";

import { transcribe } from "../api/client";

interface UploadPanelProps {
  onTranscribed: (sessionId: string, imageUrl: string) => void;
}

export function UploadPanel({ onTranscribed }: UploadPanelProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File) {
    setBusy(true);
    setError(null);
    try {
      const result = await transcribe(file);
      onTranscribed(result.session_id, URL.createObjectURL(file));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="upload">
      <h1>Cadenza · Editor HITL</h1>
      <p className="muted">Sube una imagen de partitura para transcribir y revisar.</p>
      <label className="upload-button">
        {busy ? "Transcribiendo…" : "Seleccionar imagen"}
        <input
          type="file"
          accept="image/*"
          disabled={busy}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) {
              void handleFile(file);
            }
          }}
        />
      </label>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
