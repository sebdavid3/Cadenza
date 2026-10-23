/** Tipo con el que la API sirve el MusicXML sin comprimir (`/sessions/{id}/export`). */
export const MUSICXML_TYPE = "application/vnd.recordare.musicxml+xml";

/**
 * Margen antes de revocar la URL del Blob: Safari empieza la descarga después del clic y la
 * pierde si la URL ya no existe (el mismo que usa FileSaver.js).
 */
export const REVOKE_DELAY_MS = 40_000;

export interface DownloadFile {
  name: string;
  blob: Blob;
}

/**
 * MusicXML de una sesión listo para guardar. El nombre sale del id y no del
 * `Content-Disposition` de la API: con la API en otro origen, CORS no deja leer esa cabecera.
 */
export function musicXmlFile(sessionId: string, xml: string): DownloadFile {
  return {
    name: `cadenza-${sessionId.slice(0, 8)}.musicxml`,
    blob: new Blob([xml], { type: MUSICXML_TYPE }),
  };
}

/** Descarga un archivo con un enlace temporal y libera su URL pasado el margen. */
export function saveFile({ name, blob }: DownloadFile) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  // Firefox solo descarga desde un enlace que está en el documento.
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => {
    URL.revokeObjectURL(url);
  }, REVOKE_DELAY_MS);
}
