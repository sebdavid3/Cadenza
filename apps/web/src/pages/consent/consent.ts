import type { ApiClient } from "../../api/client";
import { ApiError } from "../../api/errors";
import type { UserRead } from "../../types";

/**
 * Versión del texto del permiso de uso de los datos (#378, ADR-0064): la fecha en que se redactó.
 * Es la misma que `DATA_CONSENT_VERSION` de la API, y una prueba lo comprueba. Si el texto cambia,
 * cambian las dos, y los permisos dados para el texto anterior dejan de estar vigentes.
 */
export const DATA_CONSENT_VERSION = "2026-11-09";

/** La página con el texto completo, pública: se lee antes de crear la cuenta. */
export const DATA_USE_PATH = "/uso-de-los-datos";

/** Lo que se guarda de cada persona, en el aviso breve y en el texto completo. */
export const STORED_DATA = [
  "las imágenes de partituras que subes",
  "lo que HOMR leyó en ellas",
  "tus correcciones",
  "el tiempo que trabajas en cada partitura",
  "lo que respondes a las sugerencias",
] as const;

/** `PUT /auth/data-consent`: da el permiso para el texto vigente o lo retira. */
export function setDataConsent(api: ApiClient, granted: boolean) {
  return api.request<UserRead>("/auth/data-consent", {
    method: "PUT",
    json: granted ? { granted, version: DATA_CONSENT_VERSION } : { granted },
  });
}

/** Mensaje propio de un fallo al dar o retirar el permiso; el `detail` del backend no se muestra. */
export function consentErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.kind === "conflict") {
    return "El texto del permiso ha cambiado. Recarga la página, léelo y vuelve a darlo.";
  }
  if (error instanceof ApiError && error.kind === "network") {
    return "No se pudo conectar con el servidor. Inténtalo de nuevo.";
  }
  return "No se pudo guardar tu elección. Inténtalo de nuevo.";
}
