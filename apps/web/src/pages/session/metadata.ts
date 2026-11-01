import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import type { ApiClient } from "../../api/client";
import { ApiError, errorMessage } from "../../api/errors";
import type { SessionMetadataRead, SessionMetadataUpdate, SessionViewRead } from "../../types";
import { metadataUpdate, type ScoreDataDraft } from "../transcription/scoreData";
import { SESSIONS_QUERY_KEY } from "../transcription/sessions";
import { sessionDetailQuery, sessionMusicXmlQuery } from "./session";

/**
 * `PATCH /sessions/{id}`: cambia el título, el compositor o los instrumentos (#235, ADR-0041). No
 * es una edición del log: no lleva `base_seq` ni cambia `current_seq`, el estado ni las métricas.
 * Solo el dueño, también con la sesión finalizada.
 */
export function patchSessionMetadata(
  api: ApiClient,
  sessionId: string,
  body: SessionMetadataUpdate,
  signal?: AbortSignal,
): Promise<SessionMetadataRead> {
  return api.request<SessionMetadataRead>(`/sessions/${encodeURIComponent(sessionId)}`, {
    method: "PATCH",
    json: body,
    signal,
  });
}

/** Por qué no se guardaron los datos, en palabras de la vista. */
export function metadataErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.kind) {
      case "validation":
        return "No se guardaron los datos: el servidor no los aceptó. Revisa el nombre, el compositor y los instrumentos.";
      case "not-found":
        return "No se guardaron los datos: la sesión ya no existe o no tienes acceso a ella.";
      case "forbidden":
        return "No se guardaron los datos: solo quien transcribió la sesión puede cambiarlos.";
      default:
        break;
    }
  }
  return `No se guardaron los datos. ${errorMessage(error)}`;
}

export type MetadataMessage = { kind: "saved" | "failed"; text: string } | null;

/**
 * Guardar los datos de la partitura desde la vista (#240, ADR-0045). Nada se da por guardado sin
 * el 200, y lo que se muestra es lo que devuelve (el servidor normaliza el texto). Con él, el
 * detalle en caché toma los datos nuevos, el MusicXML se vuelve a pedir (lo que se descarga lleva
 * el título y los instrumentos nuevos) y el listado queda por actualizar.
 */
export function useSessionMetadata(api: ApiClient, sessionId: string) {
  const queryClient = useQueryClient();
  // Lo último guardado desde esta vista: manda sobre el detalle en caché, que una corrección que
  // estuviera guardándose a la vez podría componer con los datos de antes.
  const [saved, setSaved] = useState<SessionMetadataRead | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<MetadataMessage>(null);
  const inFlight = useRef(false);
  const controllerRef = useRef<AbortController | null>(null);
  useEffect(
    () => () => {
      controllerRef.current?.abort();
    },
    [],
  );

  async function save(draft: ScoreDataDraft): Promise<boolean> {
    if (inFlight.current) return false;
    inFlight.current = true;
    const controller = new AbortController();
    controllerRef.current = controller;
    setSaving(true);
    setMessage(null);
    try {
      const result = await patchSessionMetadata(
        api,
        sessionId,
        metadataUpdate(draft),
        controller.signal,
      );
      setSaved(result);
      queryClient.setQueryData<SessionViewRead>(
        sessionDetailQuery(api, sessionId).queryKey,
        (current) =>
          current && {
            ...current,
            title: result.title ?? null,
            composer: result.composer ?? null,
            instruments: result.instruments ?? [],
            source_filename: result.source_filename ?? null,
          },
      );
      // Solo el MusicXML del estado que se ve: mientras se guardaba, las correcciones esperaban,
      // así que el servidor sigue en ese estado y lo que exporte ahora es de él.
      const seq =
        queryClient.getQueryData<SessionViewRead>(sessionDetailQuery(api, sessionId).queryKey)
          ?.current_seq ?? 0;
      void queryClient.invalidateQueries({
        queryKey: sessionMusicXmlQuery(api, sessionId, seq).queryKey,
        exact: true,
      });
      void queryClient.invalidateQueries({ queryKey: SESSIONS_QUERY_KEY });
      setMessage({ kind: "saved", text: "Datos guardados." });
      return true;
    } catch (error) {
      if (controller.signal.aborted) return false;
      setMessage({ kind: "failed", text: metadataErrorMessage(error) });
      return false;
    } finally {
      inFlight.current = false;
      if (controllerRef.current === controller) controllerRef.current = null;
      if (!controller.signal.aborted) setSaving(false);
    }
  }

  return {
    saved,
    saving,
    message,
    save,
    clearMessage: () => {
      setMessage(null);
    },
  };
}
