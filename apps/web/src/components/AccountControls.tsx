import { NavLink, useNavigate } from "react-router";
import { useAuthStore } from "../auth/store";
import { pendingWorkWarning } from "../pendingWork";
import "./button.css";

const ROLE_LABELS: Record<string, string> = {
  investigador: "Investigador",
  transcriptor: "Transcriptor",
};

/**
 * La persona en sesión, que lleva a su cuenta (#190), y «Salir»: en la cabecera de la aplicación
 * y, en la vista de una sesión, en su cabecera única (#363).
 */
export function AccountControls() {
  const user = useAuthStore((state) => state.user);
  const signOut = useAuthStore((state) => state.signOut);
  const navigate = useNavigate();

  return (
    <>
      {user && (
        <NavLink className="app-header__user" to="/cuenta">
          <span className="visually-hidden">Tu cuenta: </span>
          <span className="app-header__name">{user.username}</span>
          <span className="label app-header__role">{ROLE_LABELS[user.role] ?? user.role}</span>
        </NavLink>
      )}
      <button
        type="button"
        className="button app-header__exit"
        onClick={() => {
          const warning = pendingWorkWarning();
          if (warning && !window.confirm(warning)) return;
          signOut("signed-out");
          void navigate("/entrar", { replace: true });
        }}
      >
        Salir
      </button>
    </>
  );
}
