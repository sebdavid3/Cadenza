import { useEffect } from "react";
import { api } from "../api/instance";
import { restoreSession } from "./session";
import { useAuthStore } from "./store";
import { msUntil } from "./token";

/** Mayor retardo que admite `setTimeout` (unos 24,8 días); más allá se reprograma. */
const MAX_TIMEOUT_MS = 2 ** 31 - 1;

/**
 * Ciclo de vida de la sesión en el navegador: la recupera de la pestaña al arrancar y la
 * cierra como caducada cuando vence el token (30 min, sin refresco, ADR-0012).
 */
export function useSessionLifecycle() {
  const token = useAuthStore((state) => state.token);
  const expiresAt = useAuthStore((state) => state.expiresAt);

  useEffect(() => {
    if (useAuthStore.getState().status === "restoring") void restoreSession(api);
  }, []);

  useEffect(() => {
    if (!token || expiresAt === null) return;
    let timer: ReturnType<typeof setTimeout>;
    const schedule = () => {
      const remaining = msUntil(expiresAt);
      if (remaining <= 0) {
        if (useAuthStore.getState().token === token) useAuthStore.getState().signOut("expired");
        return;
      }
      timer = setTimeout(schedule, Math.min(remaining, MAX_TIMEOUT_MS));
    };
    schedule();
    return () => {
      clearTimeout(timer);
    };
  }, [token, expiresAt]);
}
