import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";
import { api } from "../api/instance";
import "../components/button.css";
import { retryRestore } from "./session";
import { useAuthStore } from "./store";

/** Ruta privada: sin sesión, al acceso, recordando adónde se quería ir. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const status = useAuthStore((state) => state.status);
  const endReason = useAuthStore((state) => state.endReason);
  const location = useLocation();

  if (status === "restoring") {
    return (
      <p className="label auth-pending" role="status">
        Comprobando la sesión…
      </p>
    );
  }
  if (status === "unreachable") {
    return (
      <div className="auth-pending" role="alert">
        <p>No se pudo conectar con el servidor para comprobar tu sesión.</p>
        <button type="button" className="button" onClick={() => void retryRestore(api)}>
          Reintentar
        </button>
      </div>
    );
  }
  if (status !== "authenticated") {
    // Tras «Salir» no se recuerda la ruta: la siguiente persona empieza desde el principio.
    const state =
      endReason === "signed-out"
        ? undefined
        : { from: location.pathname + location.search + location.hash };
    return <Navigate to="/entrar" replace state={state} />;
  }
  return children;
}
