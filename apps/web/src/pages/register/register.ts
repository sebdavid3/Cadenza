import type { ApiClient } from "../../api/client";
import { ApiError } from "../../api/errors";
import type { UserRead } from "../../types";

export type RegisterField = "username" | "password" | "confirmation";

/** Mismas reglas que la API (ADR-0022): la API sigue siendo la autoridad. */
export const USERNAME_PATTERN = /^[a-z0-9][a-z0-9._-]{2,63}$/;
export const MIN_PASSWORD = 8;

export const USERNAME_RULE =
  "De 3 a 64 caracteres: minúsculas sin tilde, cifras, punto, guion o guion bajo; empieza por letra o cifra.";

/** `POST /auth/register` (ADR-0022): público, sin token. */
export function registerUser(api: ApiClient, username: string, password: string) {
  return api.request<UserRead>("/auth/register", {
    method: "POST",
    json: { username, password },
    auth: false,
  });
}

function minutes(seconds: number) {
  const value = Math.max(1, Math.ceil(seconds / 60));
  return value === 1 ? "un minuto" : `${String(value)} minutos`;
}

/** Campo al que apunta un 422 de esquema (`detail` lista con `loc`), si se puede saber. */
function invalidField(detail: unknown): RegisterField | null {
  if (!Array.isArray(detail)) return null;
  for (const item of detail as unknown[]) {
    if (!item || typeof item !== "object" || !("loc" in item) || !Array.isArray(item.loc)) {
      continue;
    }
    const loc = item.loc as unknown[];
    if (loc.includes("username")) return "username";
    if (loc.includes("password")) return "password";
  }
  return null;
}

/** Mensaje propio y campo a corregir para cada fallo del registro; el `detail` no se muestra. */
export function registerErrorMessage(error: unknown): { message: string; field: RegisterField } {
  if (!(error instanceof ApiError)) {
    return { message: "No se pudo crear la cuenta. Inténtalo de nuevo.", field: "username" };
  }
  switch (error.kind) {
    case "conflict":
      return { message: "Ese nombre de usuario ya existe. Elige otro.", field: "username" };
    case "validation":
      // Un 422 de esquema señala el campo; si no lo señala, es la contraseña.
      return invalidField(error.detail) === "username"
        ? { message: `Usuario no válido. ${USERNAME_RULE}`, field: "username" }
        : {
            message: `La contraseña debe tener al menos ${String(MIN_PASSWORD)} caracteres.`,
            field: "password",
          };
    case "rate-limited":
      return {
        message:
          error.retryAfterSeconds !== null
            ? `Demasiados intentos desde tu conexión. Vuelve a probar en ${minutes(error.retryAfterSeconds)}.`
            : "Demasiados intentos desde tu conexión. Espera un rato antes de volver a probar.",
        field: "username",
      };
    case "not-found":
      return {
        message: "El registro de cuentas no está abierto en este servidor.",
        field: "username",
      };
    case "server":
      if (error.status === 503) {
        return {
          message:
            "El registro está cerrado por ahora: hay muchas cuentas esperando a que un investigador las revise. Vuelve a probar más tarde.",
          field: "username",
        };
      }
      return { message: error.message, field: "username" };
    default:
      return { message: error.message, field: "username" };
  }
}
