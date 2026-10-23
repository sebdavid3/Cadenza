import type { ApiClient } from "../api/client";
import { ApiError } from "../api/errors";
import type { TokenResponse, UserRead } from "../types";
import { readStoredSession, useAuthStore } from "./store";
import { localExpiry, msUntil } from "./token";

/** Mensajes del inicio de sesión: aquí un 401 significa credenciales inválidas, no sesión caducada. */
export function loginErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "No se pudo entrar. Inténtalo de nuevo.";
  switch (error.kind) {
    case "unauthorized":
      return "Usuario o contraseña incorrectos. Si el problema sigue, pide al equipo que revise tu cuenta.";
    case "rate-limited":
      return "Demasiados intentos fallidos. Espera unos minutos antes de volver a probar.";
    case "validation":
      return "Escribe tu usuario y tu contraseña.";
    default:
      return error.message;
  }
}

/** `POST /auth/login` (formulario urlencoded) y `GET /auth/me` con el token recién emitido. */
export async function logIn(api: ApiClient, username: string, password: string) {
  const { access_token: token } = await api.request<TokenResponse>("/auth/login", {
    method: "POST",
    body: new URLSearchParams({ username, password }),
    auth: false,
  });
  const expiresAt = localExpiry(token);
  const user = await api.request<UserRead>("/auth/me", { token });
  useAuthStore.getState().signIn(token, user, expiresAt);
  return user;
}

let restoring: Promise<void> | null = null;

/**
 * Recupera la sesión guardada en la pestaña si el token sigue vigente. Las llamadas
 * simultáneas (p. ej. el doble montaje de StrictMode en desarrollo) comparten la misma.
 */
export function restoreSession(api: ApiClient): Promise<void> {
  restoring ??= doRestore(api).finally(() => {
    restoring = null;
  });
  return restoring;
}

/** Vuelve a comprobar una sesión guardada que no se pudo comprobar por falta de conexión. */
export function retryRestore(api: ApiClient): Promise<void> {
  useAuthStore.getState().startRestoring();
  return restoreSession(api);
}

async function doRestore(api: ApiClient) {
  const store = useAuthStore.getState();
  const stored = readStoredSession();
  if (!stored) {
    store.finishRestoring();
    return;
  }
  const expiresAt = stored.expiresAt ?? localExpiry(stored.token);
  if (msUntil(expiresAt) <= 0) {
    store.signOut("expired");
    return;
  }
  // Mientras tanto la persona puede haber entrado o salido: el resultado solo se aplica
  // si la sesión sigue en comprobación.
  const stillRestoring = () => useAuthStore.getState().status === "restoring";
  try {
    const user = await api.request<UserRead>("/auth/me", { token: stored.token });
    if (stillRestoring()) useAuthStore.getState().signIn(stored.token, user, expiresAt);
  } catch (error) {
    if (!stillRestoring()) return;
    if (error instanceof ApiError && error.kind === "unauthorized") {
      useAuthStore.getState().signOut("expired");
    } else {
      // Sin conexión o error del servidor: no se descarta un token que puede seguir valiendo.
      useAuthStore.getState().markUnreachable();
    }
  }
}
