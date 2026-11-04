import { useAuthStore } from "../auth/store";
import { createApiClient } from "./client";

/**
 * Cliente de la aplicación: toma el token de la sesión y, ante un 401 de una petición
 * autenticada, la cierra como caducada (las rutas privadas llevan entonces a /entrar). Solo
 * si el token rechazado es el vigente: un 401 tardío de una sesión anterior no cierra la nueva.
 */
export const api = createApiClient({
  getToken: () => useAuthStore.getState().token,
  onUnauthorized: (rejectedToken) => {
    const { status, token, signOut } = useAuthStore.getState();
    if (status === "authenticated" && token === rejectedToken) signOut("expired");
  },
});
