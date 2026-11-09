/**
 * Preferencias de la mesa de corrección que el navegador recuerda (#341): el ancho de la imagen y
 * si el panel lateral está plegado. Son comodidades de quien mira: si el almacenamiento no está
 * (ventana privada, datos bloqueados), la vista funciona igual con sus valores por defecto.
 */

const PREFIX = "cadenza.mesa.";

export function readStored(key: string): string | null {
  try {
    return window.localStorage.getItem(PREFIX + key);
  } catch {
    return null;
  }
}

export function writeStored(key: string, value: string): void {
  try {
    window.localStorage.setItem(PREFIX + key, value);
  } catch {
    // Sin almacenamiento, la preferencia dura lo que dura la página.
  }
}
