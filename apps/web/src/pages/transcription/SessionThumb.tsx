import { useEffect, useRef, useState } from "react";
import { api } from "../../api/instance";
import { sessionImage } from "./sessions";

type ThumbState = { kind: "waiting" } | { kind: "ready"; url: string } | { kind: "failed" };

/**
 * Miniatura de la imagen de una sesión. `GET /sessions/{id}/image` exige Bearer, así que la
 * imagen se descarga con el cliente autenticado y se muestra desde un Blob (handoff §5.6).
 * Se pide al acercarse a la pantalla y la URL del Blob se revoca al desmontar.
 */
export function SessionThumb({ sessionId }: { sessionId: string }) {
  const frameRef = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(() => !("IntersectionObserver" in window));
  const [state, setState] = useState<ThumbState>({ kind: "waiting" });

  useEffect(() => {
    if (visible) return;
    const frame = frameRef.current;
    if (!frame) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "200px" },
    );
    observer.observe(frame);
    return () => {
      observer.disconnect();
    };
  }, [visible]);

  useEffect(() => {
    if (!visible) return;
    const controller = new AbortController();
    let url: string | null = null;
    sessionImage(api, sessionId, controller.signal)
      .then((blob) => {
        // Si la vista ya se desmontó, no se crea una URL que nadie revocaría.
        if (controller.signal.aborted) return;
        url = URL.createObjectURL(blob);
        setState({ kind: "ready", url });
      })
      .catch(() => {
        if (!controller.signal.aborted) setState({ kind: "failed" });
      });
    return () => {
      controller.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [visible, sessionId]);

  return (
    <div className="thumb" ref={frameRef} data-state={state.kind}>
      {state.kind === "ready" && <img src={state.url} alt="" />}
      {state.kind === "failed" && <span className="label">Sin imagen</span>}
    </div>
  );
}
