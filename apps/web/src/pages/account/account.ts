import type { ApiClient } from "../../api/client";
import { ApiError } from "../../api/errors";
import type { StatusResponse, UserRead } from "../../types";
import { MIN_PASSWORD, minutes } from "../register/register";

export type PasswordField = "current" | "next" | "confirmation";

/**
 * `POST /auth/password`. Su 401 es la contraseña actual equivocada, no una sesión caducada: no
 * debe cerrar la sesión (`notifyUnauthorized: false`).
 */
export function changePassword(api: ApiClient, current: string, next: string) {
  return api.request<StatusResponse>("/auth/password", {
    method: "POST",
    json: { current_password: current, new_password: next },
    notifyUnauthorized: false,
  });
}

/**
 * La API responde 401 tanto a la contraseña actual equivocada como a un token que ya no vale (una
 * cuenta desactivada, una sesión vencida). Para no decir lo primero cuando es lo segundo, se
 * pregunta por la sesión con `GET /auth/me`: si ya no vale, ese 401 la cierra como cualquier otro.
 * Devuelve si la sesión sigue valiendo; ante otro fallo, se supone que sí.
 */
export async function sessionStillValid(api: ApiClient): Promise<boolean> {
  try {
    await api.request<UserRead>("/auth/me");
    return true;
  } catch (error) {
    return !(error instanceof ApiError && error.kind === "unauthorized");
  }
}

/**
 * Un error del cambio: su mensaje y el campo que hay que corregir, o null si no es culpa de ningún
 * campo (límite, servidor, red), en cuyo caso el aviso se lleva el foco.
 */
export interface PasswordError {
  message: string;
  field: PasswordField | null;
}

export const SHORT_PASSWORD_MESSAGE = `La contraseña nueva debe tener al menos ${String(MIN_PASSWORD)} caracteres.`;

/** Campo al que apunta un 422 de esquema (`detail` lista con `loc`), si se puede saber. */
function invalidField(detail: unknown): PasswordField | null {
  if (!Array.isArray(detail)) return null;
  for (const item of detail as unknown[]) {
    if (!item || typeof item !== "object" || !("loc" in item) || !Array.isArray(item.loc)) {
      continue;
    }
    const loc = item.loc as unknown[];
    if (loc.includes("current_password")) return "current";
    if (loc.includes("new_password")) return "next";
  }
  return null;
}

/** Mensaje propio para cada fallo del cambio; el `detail` del backend no se muestra. */
export function passwordErrorMessage(error: unknown): PasswordError {
  if (!(error instanceof ApiError)) {
    return { message: "No se pudo cambiar la contraseña. Inténtalo de nuevo.", field: null };
  }
  switch (error.kind) {
    case "unauthorized":
      return { message: "La contraseña actual no es correcta.", field: "current" };
    case "validation":
      // Un 422 de esquema señala el campo; si no lo señala, es la nueva (la API mide su longitud).
      return invalidField(error.detail) === "current"
        ? { message: "Escribe tu contraseña actual.", field: "current" }
        : { message: SHORT_PASSWORD_MESSAGE, field: "next" };
    case "rate-limited":
      return {
        message:
          error.retryAfterSeconds !== null
            ? `Demasiados intentos. Vuelve a probar en ${minutes(error.retryAfterSeconds)}.`
            : "Demasiados intentos. Espera un rato antes de volver a probar.",
        field: null,
      };
    case "network":
    case "timeout":
      return {
        message: `${error.message} Puede que la contraseña llegara a cambiarse: si la actual deja de valer, prueba con la nueva.`,
        field: null,
      };
    default:
      return { message: error.message, field: null };
  }
}

const TIME_FORMAT = new Intl.DateTimeFormat("es", { hour: "2-digit", minute: "2-digit" });

/**
 * Qué pasa con la sesión abierta tras el cambio, comprobado contra la API: el token emitido antes
 * sigue valiendo hasta que vence (la API no lo invalida) y la contraseña anterior ya no entra.
 */
export function afterChangeNotice(expiresAt: number | null): string {
  const until =
    expiresAt === null ? "hasta que caduque" : `hasta las ${TIME_FORMAT.format(expiresAt)}`;
  return `Sigues dentro: esta sesión dura ${until}, y las que tengas abiertas en otras pestañas o navegadores, hasta que caduquen. La próxima vez que entres, usa la contraseña nueva; la anterior ya no vale.`;
}
