/** Prefijo que el proxy de Vite reenvía a la API (vite.config.ts). */
export const DEFAULT_API_BASE_URL = "/api";

/** Timeout general de las peticiones. */
export const DEFAULT_TIMEOUT_MS = 15_000;

/** `POST /transcribe` es síncrono: hasta unos 12 s por página en CPU (frontend-handoff §5.7). */
export const TRANSCRIBE_TIMEOUT_MS = 30_000;

export function resolveBaseUrl(configured: string | undefined = import.meta.env.VITE_API_BASE_URL) {
  const value = configured?.trim();
  if (!value) return DEFAULT_API_BASE_URL;
  return value;
}
