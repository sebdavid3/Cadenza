import { useEffect } from "react";
import { api } from "../api/instance";
import { restoreSession } from "./session";
import { useAuthStore } from "./store";
import { msUntilExpiry } from "./token";

/**
 * Ciclo de vida de la sesión en el navegador: la recupera de la pestaña al arrancar y la
 * cierra como caducada cuando vence el `exp` del token (30 min, sin refresco, ADR-0012).
 */
export function useSessionLifecycle() {
  const token = useAuthStore((state) => state.token);

  useEffect(() => {
    if (useAuthStore.getState().status === "restoring") void restoreSession(api);
  }, []);

  useEffect(() => {
    if (!token) return;
    const timer = setTimeout(() => {
      if (useAuthStore.getState().token === token) useAuthStore.getState().signOut("expired");
    }, msUntilExpiry(token));
    return () => {
      clearTimeout(timer);
    };
  }, [token]);
}
