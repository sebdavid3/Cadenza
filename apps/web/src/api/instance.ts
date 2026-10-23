import { useAuthStore } from "../auth/store";
import { createApiClient } from "./client";

/**
 * Cliente de la aplicación: toma el token de la sesión y, ante un 401 de una petición
 * autenticada, la cierra como caducada (las rutas privadas llevan entonces a /entrar).
 */
export const api = createApiClient({
  getToken: () => useAuthStore.getState().token,
  onUnauthorized: () => {
    if (useAuthStore.getState().status === "authenticated") {
      useAuthStore.getState().signOut("expired");
    }
  },
});
