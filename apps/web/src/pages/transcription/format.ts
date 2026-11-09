/** Tamaño de un archivo en KB o MB, en español. */
export function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${String(Math.max(1, Math.round(bytes / 1024)))} KB`;
  return `${(bytes / (1024 * 1024)).toLocaleString("es", { maximumFractionDigits: 1 })} MB`;
}

/** Lo que el validador señaló, en las palabras de la mesa de corrección (#370). */
export function findingsLabel(count: number): string {
  if (count === 0) return "Sin posibles errores";
  return count === 1 ? "1 posible error" : `${String(count)} posibles errores`;
}

export function editsLabel(count: number): string {
  return count === 1 ? "1 edición" : `${String(count)} ediciones`;
}
