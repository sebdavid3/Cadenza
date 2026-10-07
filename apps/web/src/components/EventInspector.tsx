import { useEffect, useState } from "react";

import { appendEdit } from "../api/client";
import { anchorKey, resolvePitch, useEditorStore } from "../store/editorStore";

export function EventInspector() {
  const sessionId = useEditorStore((state) => state.sessionId);
  const selected = useEditorStore((state) => state.selected);
  const events = useEditorStore((state) => state.events);
  const history = useEditorStore((state) => state.history);
  const cursor = useEditorStore((state) => state.cursor);
  const author = useEditorStore((state) => state.author);
  const recordEdit = useEditorStore((state) => state.recordEdit);
  const [pitch, setPitch] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const info = selected ? events[anchorKey(selected)] : undefined;
  const currentPitch = selected ? resolvePitch(events, history, cursor, selected) : null;

  useEffect(() => {
    setPitch(currentPitch ?? "");
  }, [currentPitch, selected]);

  async function applyPitch() {
    if (!sessionId || !selected || pitch.length === 0) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const edit = await appendEdit(sessionId, {
        op: "SetPitch",
        anchor: selected,
        before: currentPitch ? { pitch: currentPitch } : null,
        after: { pitch },
      });
      recordEdit(edit);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  if (!selected) {
    return <p className="muted">Selecciona un evento en la partitura.</p>;
  }

  return (
    <div className="inspector">
      <dl>
        <dt>Compás</dt>
        <dd>{selected.measure}</dd>
        <dt>Voz</dt>
        <dd>{selected.voice}</dd>
        <dt>Evento</dt>
        <dd>{selected.event_index}</dd>
        <dt>Tipo</dt>
        <dd>{info?.kind ?? "—"}</dd>
        <dt>Duración</dt>
        <dd>{info?.duration ?? "—"}</dd>
        <dt>Autor</dt>
        <dd>{author}</dd>
      </dl>
      <label>
        Altura
        <input
          value={pitch}
          placeholder="p. ej. C4"
          onChange={(event) => setPitch(event.target.value)}
        />
      </label>
      <button
        type="button"
        disabled={busy || pitch.length === 0 || pitch === currentPitch}
        onClick={() => void applyPitch()}
      >
        {busy ? "Guardando…" : "Aplicar SetPitch"}
      </button>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
