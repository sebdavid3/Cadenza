import type { ApiClient } from "../api/client";
import { ApiError } from "../api/errors";
import type { TokenResponse, UserRead } from "../types";
import { readStoredToken, useAuthStore } from "./store";
import { msUntilExpiry } from "./token";

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
  const user = await api.request<UserRead>("/auth/me", { token });
  useAuthStore.getState().signIn(token, user);
  return user;
}

/** Recupera la sesión guardada en la pestaña si el token sigue vigente. */
export async function restoreSession(api: ApiClient) {
  const store = useAuthStore.getState();
  const token = readStoredToken();
  if (!token || msUntilExpiry(token) <= 0) {
    if (token) store.signOut("expired");
    else store.finishRestoring();
    return;
  }
  try {
    const user = await api.request<UserRead>("/auth/me", { token });
    store.signIn(token, user);
  } catch (error) {
    store.signOut(
      error instanceof ApiError && error.kind === "unauthorized" ? "expired" : undefined,
    );
  }
}
