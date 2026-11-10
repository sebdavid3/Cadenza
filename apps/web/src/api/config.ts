/** Prefijo que el proxy de Vite reenvía a la API (vite.config.ts). */
export const DEFAULT_API_BASE_URL = "/api";

/** Timeout general de las peticiones. */
export const DEFAULT_TIMEOUT_MS = 15_000;

/**
 * Subir una imagen de hasta 20 MB a la cola de transcripción (`POST /transcription-jobs`): la
 * respuesta llega en cuanto la imagen está en el servidor, y la transcripción sigue sin plazo
 * (#375, frontend-handoff §5.7).
 */
export const UPLOAD_TIMEOUT_MS = 120_000;

/**
 * `POST /previews`, la transcripción sin cuenta de la portada, sigue siendo síncrona y está
 * apagada (#278, ADR-0054): se espera como mucho 30 s.
 */
export const PREVIEW_TIMEOUT_MS = 30_000;

export function resolveBaseUrl(configured: string | undefined = import.meta.env.VITE_API_BASE_URL) {
  const value = configured?.trim();
  if (!value) return DEFAULT_API_BASE_URL;
  return value;
}
