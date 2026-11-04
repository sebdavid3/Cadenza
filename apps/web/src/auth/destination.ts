import { PRIVATE_HOME } from "../config";

/**
 * Ruta a la que volver tras entrar o crear la cuenta: la que se recordó en `state.from`, solo si
 * es una ruta interna de la propia aplicación; si no, la zona privada.
 */
export function destination(state: unknown): string {
  if (state && typeof state === "object" && "from" in state && typeof state.from === "string") {
    const from = state.from;
    if (from.startsWith("/") && !from.startsWith("//") && !from.includes("\\")) return from;
  }
  return PRIVATE_HOME;
}
