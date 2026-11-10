import { Link, NavLink, Outlet, useMatch } from "react-router";
import { useAuthStore } from "../auth/store";
import { AccountControls } from "./AccountControls";
import "./app-layout.css";
import { BrandWordmark } from "./BrandWordmark";
import "./button.css";

/**
 * Marco de la zona privada: marca, secciones, persona en sesión y salida. La vista de una sesión
 * lleva su propia cabecera, que reúne la marca, la vuelta a las sesiones y la cuenta con los datos
 * y las acciones de la sesión, para dejar el alto a la partitura (#363).
 */
export function AppLayout() {
  const user = useAuthStore((state) => state.user);
  const ownHeader = useMatch("/sesiones/:sessionId") !== null;

  return (
    <div className="app-layout">
      {!ownHeader && (
        <header className="app-header">
          <Link className="app-header__brand" to="/" aria-label="Cadenza, página pública">
            <BrandWordmark />
          </Link>
          <nav className="app-header__nav" aria-label="Zona de trabajo">
            <NavLink className="label" to="/transcripcion">
              Transcripción
            </NavLink>
            {user?.role === "investigador" && (
              <NavLink className="label" to="/cuentas">
                Cuentas
              </NavLink>
            )}
          </nav>
          <AccountControls />
        </header>
      )}
      <Outlet />
    </div>
  );
}
