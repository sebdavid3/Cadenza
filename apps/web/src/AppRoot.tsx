import { Outlet } from "react-router";
import { useSessionLifecycle } from "./auth/useSessionLifecycle";

/** Raíz de todas las rutas: mantiene la sesión del navegador. */
export function AppRoot() {
  useSessionLifecycle();
  return <Outlet />;
}
