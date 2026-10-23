import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { api } from "../../api/instance";
import "../../components/button.css";
import { PixelIcon } from "../../components/PixelIcon";
import { SiteHeader } from "../../components/SiteHeader";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { loginErrorMessage, logIn } from "../../auth/session";
import { useAuthStore } from "../../auth/store";
import { PRIVATE_HOME } from "../../config";
import "./login.css";

function destination(state: unknown): string {
  if (state && typeof state === "object" && "from" in state && typeof state.from === "string") {
    if (state.from.startsWith("/") && !state.from.startsWith("//")) return state.from;
  }
  return PRIVATE_HOME;
}

export function LoginPage() {
  useDocumentTitle("Entrar");
  const location = useLocation();
  const navigate = useNavigate();
  const status = useAuthStore((state) => state.status);
  const endReason = useAuthStore((state) => state.endReason);
  const clearEndReason = useAuthStore((state) => state.clearEndReason);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (status === "authenticated" && !submitting) {
    return <Navigate to={destination(location.state)} replace />;
  }

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitting) return;
    if (!username.trim() || !password) {
      setError("Escribe tu usuario y tu contraseña.");
      return;
    }
    setSubmitting(true);
    setError(null);
    clearEndReason();
    try {
      await logIn(api, username.trim(), password);
      void navigate(destination(location.state), { replace: true });
    } catch (caught) {
      setError(loginErrorMessage(caught));
      setPassword("");
      setSubmitting(false);
    }
  };

  return (
    <>
      <SiteHeader showSections={false} showEnter={false} />
      <main className="login">
        <h1 className="login__title">
          <span>Entrar</span>
        </h1>
        <form className="login__form" onSubmit={(event) => void submit(event)} noValidate>
          {endReason === "expired" && !error && (
            <p className="login__notice" role="status">
              Tu sesión caducó. Vuelve a entrar para seguir trabajando.
            </p>
          )}
          {error && (
            <p className="login__error" role="alert">
              {error}
            </p>
          )}
          <div className="field">
            <label className="label" htmlFor="login-username">
              Usuario
            </label>
            <input
              id="login-username"
              name="username"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              value={username}
              onChange={(event) => {
                setUsername(event.target.value);
              }}
              disabled={submitting}
              required
            />
          </div>
          <div className="field">
            <label className="label" htmlFor="login-password">
              Contraseña
            </label>
            <input
              id="login-password"
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => {
                setPassword(event.target.value);
              }}
              disabled={submitting}
              required
            />
          </div>
          <button
            className="button button--primary login__submit"
            type="submit"
            disabled={submitting}
          >
            {submitting ? "Entrando…" : "Entrar"}
            {!submitting && <PixelIcon name="arrow-right" />}
          </button>
          <p className="login__help">
            No hay registro abierto ni recuperación de contraseña por correo. Las cuentas las crea
            un investigador del proyecto: pídele la tuya o una contraseña nueva.
          </p>
        </form>
      </main>
    </>
  );
}
