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
