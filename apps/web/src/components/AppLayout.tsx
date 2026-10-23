import { Link, NavLink, Outlet, useNavigate } from "react-router";
import { useAuthStore } from "../auth/store";
import "./app-layout.css";
import "./button.css";

const ROLE_LABELS: Record<string, string> = {
  investigador: "Investigador",
  transcriptor: "Transcriptor",
};

/** Marco de la zona privada: marca, secciones, persona en sesión y salida. */
export function AppLayout() {
  const user = useAuthStore((state) => state.user);
  const signOut = useAuthStore((state) => state.signOut);
  const navigate = useNavigate();

  return (
    <div className="app-layout">
      <header className="app-header">
        <Link className="app-header__brand" to="/" aria-label="Cadenza, página pública">
          Cadenza
        </Link>
        <nav className="app-header__nav" aria-label="Zona de trabajo">
          <NavLink className="label" to="/transcripcion">
            Transcripción
          </NavLink>
        </nav>
        {user && (
          <div className="app-header__user">
            <span className="app-header__name">{user.username}</span>
            <span className="label app-header__role">{ROLE_LABELS[user.role] ?? user.role}</span>
          </div>
        )}
        <button
          type="button"
          className="button app-header__exit"
          onClick={() => {
            signOut();
            void navigate("/entrar", { replace: true });
          }}
        >
          Salir
        </button>
      </header>
      <Outlet />
    </div>
  );
}
