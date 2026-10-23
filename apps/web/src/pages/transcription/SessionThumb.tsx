import { useQuery } from "@tanstack/react-query";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { api } from "../../api/instance";
import { sessionImageQuery } from "./sessions";

/**
 * Miniatura de la imagen de una sesión. `GET /sessions/{id}/image` exige Bearer, así que la
 * imagen se descarga con el cliente autenticado y se muestra desde un Blob (handoff §5.6).
 * Se pide al acercarse a la pantalla; la URL del Blob se crea al montar y se revoca al desmontar.
 */
export function SessionThumb({ sessionId }: { sessionId: string }) {
  const frameRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const [visible, setVisible] = useState(() => !("IntersectionObserver" in window));
  const image = useQuery({ ...sessionImageQuery(api, sessionId), enabled: visible });
  const blob = image.data;

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

  // La URL se asigna al <img> antes de pintar: cada montaje crea la suya y la revoca al irse,
  // también con el doble montaje de StrictMode, sin pasar por el estado.
  useLayoutEffect(() => {
    const element = imageRef.current;
    if (!blob || !element) return;
    const url = URL.createObjectURL(blob);
    element.src = url;
    return () => {
      element.removeAttribute("src");
      URL.revokeObjectURL(url);
    };
  }, [blob]);

  const state = blob ? "ready" : image.isError ? "failed" : "waiting";
  return (
    <div className="thumb" ref={frameRef} data-state={state}>
      {blob && <img ref={imageRef} alt="" decoding="async" />}
      {state === "failed" && <span className="label">Sin imagen</span>}
    </div>
  );
}
