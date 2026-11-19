import { Link, NavLink, Outlet, useMatch } from "react-router";
import { ConsentPrompt } from "../pages/consent/ConsentPrompt";
import { AccountControls } from "./AccountControls";
import "./app-layout.css";
import { BrandWordmark } from "./BrandWordmark";
import "./button.css";

/**
 * Marco de la zona privada: marca, secciones, persona en sesión y salida. La vista de una sesión
 * lleva su propia cabecera, que reúne la marca, la vuelta a las sesiones y la cuenta con los datos
 * y las acciones de la sesión, para dejar el alto a la partitura (#363).
 *
 * Bajo la cabecera se pide el permiso de uso de los datos a quien no lo tiene vigente (#430),
 * salvo en la vista de una sesión, que necesita todo su alto, y en «Tu cuenta», que tiene su
 * propio interruptor.
 */
export function AppLayout() {
  const ownHeader = useMatch("/sesiones/:sessionId") !== null;
  const onAccount = useMatch("/cuenta") !== null;

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
          </nav>
          <AccountControls />
        </header>
      )}
      {!ownHeader && !onAccount && <ConsentPrompt />}
      <Outlet />
    </div>
  );
}
