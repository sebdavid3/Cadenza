import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router";
import { api } from "../../api/instance";
import { loginErrorMessage, logIn } from "../../auth/session";
import { useAuthStore } from "../../auth/store";
import "../../components/button.css";
import { PixelIcon } from "../../components/PixelIcon";
import { SiteHeader } from "../../components/SiteHeader";
import { PRIVATE_HOME } from "../../config";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import "./login.css";

/** Ruta a la que volver tras entrar: solo rutas internas de la propia aplicación. */
function destination(state: unknown): string {
  if (state && typeof state === "object" && "from" in state && typeof state.from === "string") {
    const from = state.from;
    if (from.startsWith("/") && !from.startsWith("//") && !from.includes("\\")) return from;
  }
  return PRIVATE_HOME;
}

type Field = "username" | "password";

export function LoginPage() {
  useDocumentTitle("Entrar");
  const location = useLocation();
  const navigate = useNavigate();
  const status = useAuthStore((state) => state.status);
  const clearEndReason = useAuthStore((state) => state.clearEndReason);
  // El aviso de caducidad se muestra una vez, en la llegada desde una sesión que caducó.
  const [expiredNotice] = useState(() => useAuthStore.getState().endReason === "expired");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<{ message: string; field: Field } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const usernameRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const noticeRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    clearEndReason();
    if (expiredNotice) noticeRef.current?.focus();
  }, [clearEndReason, expiredNotice]);

  // Tras un error, el foco vuelve al campo que hay que corregir.
  useEffect(() => {
    if (!error) return;
    (error.field === "username" ? usernameRef : passwordRef).current?.focus();
  }, [error]);

  if (status === "authenticated" && !submitting) {
    return <Navigate to={destination(location.state)} replace />;
  }

  const checking = status === "restoring";

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitting || checking) return;
    if (!username.trim() || !password) {
      setError({
        message: "Escribe tu usuario y tu contraseña.",
        field: username.trim() ? "password" : "username",
      });
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await logIn(api, username.trim(), password);
      void navigate(destination(location.state), { replace: true });
    } catch (caught) {
      setError({ message: loginErrorMessage(caught), field: "password" });
      setPassword("");
    } finally {
      setSubmitting(false);
    }
  };

  const invalid = error !== null;

  return (
    <>
      <SiteHeader showSections={false} showEnter={false} />
      <main className="login">
        <h1 className="login__title">
          <span>Entrar</span>
        </h1>
        <form className="login__form" onSubmit={(event) => void submit(event)} noValidate>
          {expiredNotice && !error && (
            <p className="login__notice" role="status" ref={noticeRef} tabIndex={-1}>
              Tu sesión caducó. Vuelve a entrar para seguir trabajando.
            </p>
          )}
          {error && (
            <p className="login__error" role="alert" id="login-error">
              {error.message}
            </p>
          )}
          <div className="field">
            <label className="label" htmlFor="login-username">
              Usuario
            </label>
            <input
              ref={usernameRef}
              id="login-username"
              name="username"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              value={username}
              onChange={(event) => {
                setUsername(event.target.value);
              }}
              readOnly={submitting}
              aria-invalid={invalid}
              aria-describedby={invalid ? "login-error" : undefined}
              required
            />
          </div>
          <div className="field">
            <label className="label" htmlFor="login-password">
              Contraseña
            </label>
            <input
              ref={passwordRef}
              id="login-password"
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => {
                setPassword(event.target.value);
              }}
              readOnly={submitting}
              aria-invalid={invalid}
              aria-describedby={invalid ? "login-error" : undefined}
              required
            />
          </div>
          <button
            className="button button--primary login__submit"
            type="submit"
            disabled={submitting || checking}
          >
            {checking ? "Comprobando la sesión…" : submitting ? "Entrando…" : "Entrar"}
            {!submitting && !checking && <PixelIcon name="arrow-right" />}
          </button>
          <p className="login__help">
            ¿No tienes cuenta? <Link to="/registro">Créala</Link>: queda pendiente hasta que un
            investigador del proyecto la active. No hay recuperación de contraseña por correo: si la
            olvidas, pide una nueva a un investigador.
          </p>
        </form>
      </main>
    </>
  );
}
