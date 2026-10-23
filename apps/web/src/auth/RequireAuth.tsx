import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";
import { useAuthStore } from "./store";

/** Ruta privada: sin sesión, al acceso, recordando adónde se quería ir. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const status = useAuthStore((state) => state.status);
  const location = useLocation();

  if (status === "restoring") {
    return (
      <p className="label auth-pending" role="status">
        Comprobando la sesión…
      </p>
    );
  }
  if (status !== "authenticated") {
    return <Navigate to="/entrar" replace state={{ from: location.pathname + location.search }} />;
  }
  return children;
}
