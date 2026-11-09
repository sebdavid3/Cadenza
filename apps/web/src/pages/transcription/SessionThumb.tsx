import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useLayoutEffect, useRef, useState, type Ref } from "react";
import { api } from "../../api/instance";
import type { QueueItem } from "./queue";
import { queueImageQuery, sessionImageQuery } from "./sessions";

/** Una imagen más de 2,2 veces ancha que alta (un incipit) se ve entera; las demás, por arriba. */
const WIDE_RATIO = 2.2;

interface ThumbProps {
  blob: Blob | undefined;
  failed: boolean;
  frameRef?: Ref<HTMLDivElement>;
}

/**
 * Dibuja una imagen en miniatura desde un Blob. La URL se asigna al <img> antes de pintar: cada
 * montaje crea la suya y la revoca al irse, también con el doble montaje de StrictMode.
 */
function Thumb({ blob, failed, frameRef }: ThumbProps) {
  const imageRef = useRef<HTMLImageElement>(null);
  const [wide, setWide] = useState(false);
  // El navegador no pudo dibujar este Blob (no era una imagen): se dice, sin icono roto.
  const [broken, setBroken] = useState<Blob | null>(null);
  const shown = blob && broken !== blob ? blob : undefined;

  useLayoutEffect(() => {
    const element = imageRef.current;
    if (!shown || !element) return;
    const url = URL.createObjectURL(shown);
    element.src = url;
    return () => {
      element.removeAttribute("src");
      URL.revokeObjectURL(url);
    };
  }, [shown]);

  const state = shown ? "ready" : failed || blob ? "failed" : "waiting";
  return (
    <div className="thumb" ref={frameRef} data-state={state} data-shape={wide ? "wide" : "page"}>
      {shown && (
        <img
          ref={imageRef}
          alt=""
          decoding="async"
          onLoad={(event) => {
            const { naturalWidth, naturalHeight } = event.currentTarget;
            setWide(naturalHeight > 0 && naturalWidth / naturalHeight > WIDE_RATIO);
          }}
          onError={() => {
            setBroken(shown);
          }}
        />
      )}
      {state === "failed" && <span className="label">Sin imagen</span>}
    </div>
  );
}

/**
 * Miniatura de la imagen de una sesión. `GET /sessions/{id}/image` exige Bearer, así que la
 * imagen se descarga con el cliente autenticado y se muestra desde un Blob (handoff §5.6).
 * Se pide al acercarse a la pantalla.
 */
export function SessionThumb({ sessionId }: { sessionId: string }) {
  const frameRef = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(() => !("IntersectionObserver" in window));
  const image = useQuery({ ...sessionImageQuery(api, sessionId), enabled: visible });

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

  return <Thumb blob={image.data} failed={image.isError} frameRef={frameRef} />;
}

/** Miniatura de una imagen de la cola (#370): el archivo elegido, reducido en el navegador. */
export function QueueThumb({ item }: { item: QueueItem }) {
  // Un archivo rechazado antes de enviarlo (no es PNG ni JPEG) no se intenta dibujar.
  const image = useQuery({ ...queueImageQuery(item.id, item.file), enabled: !item.rejected });
  // La imagen de la sesión es la que se subió: la lámina que ocupa el sitio de esta no la vuelve
  // a descargar ni aparece en blanco mientras llega.
  const queryClient = useQueryClient();
  const sessionId = item.status === "done" ? item.result?.session_id : undefined;
  const blob = image.data;
  useEffect(() => {
    if (sessionId === undefined || !blob) return;
    const { queryKey } = sessionImageQuery(api, sessionId);
    if (queryClient.getQueryData(queryKey) === undefined) queryClient.setQueryData(queryKey, blob);
  }, [sessionId, blob, queryClient]);
  return <Thumb blob={image.data} failed={image.isError || item.rejected === true} />;
}
