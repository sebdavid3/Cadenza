import type { TranscribeResponse, TranscriptionJobRead } from "../types";
import { jsonResponse, mockApi, type Route } from "./auth-helpers";

/** Una transcripción del servidor (#375), en cola si no se dice otra cosa. */
export function job(
  overrides: Partial<TranscriptionJobRead> & { id: string },
): TranscriptionJobRead {
  return {
    stage: "queued",
    ahead: 0,
    reading: null,
    staff: null,
    staffs: null,
    result: null,
    failure: null,
    source_filename: "pagina.png",
    title: null,
    created_at: "2026-11-09T10:00:00Z",
    started_at: null,
    finished_at: null,
    ...overrides,
  };
}

/** Una transcripción terminada con su sesión. */
export function doneJob(result: TranscribeResponse, overrides: Partial<TranscriptionJobRead> = {}) {
  return job({
    id: result.session_id,
    stage: "done",
    ahead: null,
    result,
    started_at: "2026-11-09T10:00:01Z",
    finished_at: "2026-11-09T10:00:05Z",
    ...overrides,
  });
}

/**
 * Las rutas de la cola de transcripción con un servidor que transcribe al instante: la subida
 * (`POST /transcription-jobs`) responde lo que diga `respond`, como respondía `POST /transcribe`
 * antes de #375: un error tal cual, o la sesión creada, como una transcripción ya terminada.
 */
export function instantJobRoutes(respond: Route): Record<string, Route> {
  const jobs = new Map<string, TranscriptionJobRead>();
  return {
    "POST /transcription-jobs": async (init, url) => {
      const response = await respond(init, url);
      if (!response.ok) return response;
      const result = (await response.json()) as TranscribeResponse;
      const done = doneJob(result);
      jobs.set(done.id, done);
      return jsonResponse(done, 202);
    },
    "GET /transcription-jobs": () => jsonResponse([...jobs.values()]),
  };
}

/**
 * `mockApi` con la cola de transcripción al instante: la ruta `POST /transcribe` de las pruebas se
 * convierte en la subida a la cola (`instantJobRoutes`). Las demás rutas, tal cual.
 */
export function mockApiWithInstantJobs(routes: Record<string, Route>) {
  const { "POST /transcribe": transcribe, ...rest } = routes;
  return mockApi(transcribe ? { ...instantJobRoutes(transcribe), ...rest } : rest);
}
