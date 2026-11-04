/** Repositorio público del proyecto: la prueba que la página pública puede enlazar. */
export const REPOSITORY_URL = "https://github.com/sebdavid3/Cadenza";

/** Primera vista de la zona privada, adonde lleva el acceso por defecto. */
export const PRIVATE_HOME = "/transcripcion";

/**
 * Si este despliegue ofrece el registro público (ADR-0022). La API lo trae apagado por defecto
 * (`CADENZA_REGISTRATION_ENABLED`): la interfaz solo lo enlaza si el build lo declara con
 * `VITE_REGISTRATION_ENABLED=true`. Se lee al llamar, para que las pruebas puedan cambiarlo.
 */
export function registrationEnabled(): boolean {
  return import.meta.env.VITE_REGISTRATION_ENABLED === "true";
}

/**
 * Umbral de las pausas en la medición del esfuerzo (#188, protocolo §3.4, ADR-0050): de cada
 * pausa sin teclado, ratón ni toque más larga que esto solo cuenta esto. Dos minutos,
 * confirmado por el responsable el 2026-11-01 (#244). Este es el único sitio donde se fija, y
 * cada tramo enviado lo lleva consigo.
 */
export const EFFORT_IDLE_THRESHOLD_MS = 2 * 60_000;

/**
 * Si este despliegue transcribe sin cuenta desde la portada (#278, ADR-0054). La API lo trae
 * apagado (`CADENZA_ANONYMOUS_PREVIEW_ENABLED`): la portada solo lo ofrece si el build lo declara
 * con `VITE_ANONYMOUS_PREVIEW_ENABLED=true`, y si la API responde 404 vuelve a pedir que se entre.
 */
export function anonymousPreviewEnabled(): boolean {
  return import.meta.env.VITE_ANONYMOUS_PREVIEW_ENABLED === "true";
}
