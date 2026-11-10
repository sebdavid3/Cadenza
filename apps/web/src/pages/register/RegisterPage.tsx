import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, Navigate, useLocation } from "react-router";
import { ApiError } from "../../api/errors";
import { api } from "../../api/instance";
import { destination } from "../../auth/destination";
import { logIn } from "../../auth/session";
import { useAuthStore } from "../../auth/store";
import "../../components/button.css";
import { PixelIcon } from "../../components/PixelIcon";
import { SiteHeader } from "../../components/SiteHeader";
import { registrationEnabled } from "../../config";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import type { UserRead } from "../../types";
import "../consent/consent.css";
import { DataConsentNotice } from "../consent/DataConsentNotice";
import "../login/login.css";
import {
  CONSENT_REQUIRED,
  MIN_PASSWORD,
  passwordLength,
  registerErrorMessage,
  registerUser,
  USERNAME_PATTERN,
  USERNAME_RULE,
  type RegisterError,
  type RegisterField,
} from "./register";

/** Por qué no se pudo entrar con la cuenta recién creada; la cuenta existe en cualquier caso. */
function autoLoginNotice(error: unknown): string {
  if (error instanceof ApiError && error.kind === "rate-limited") {
    return "No se pudo entrar con ella ahora: hay demasiados intentos de acceso desde tu conexión. Entra con tu usuario y tu contraseña dentro de unos minutos.";
  }
  return "No se pudo entrar con ella automáticamente. Entra con tu usuario y tu contraseña.";
}

/**
 * Registro de una cuenta (ADR-0022, ADR-0025). Con el registro cerrado en el build
 * (`VITE_REGISTRATION_ENABLED`), la ruta sigue existiendo para quien llegue con un enlace
 * antiguo, pero no ofrece el formulario: dice que está cerrado y lleva a entrar (#248).
 */
export function RegisterPage() {
  return registrationEnabled() ? <RegisterForm /> : <RegistrationClosed />;
}

/** El registro cerrado: sin formulario ni llamadas a la API, solo el camino a entrar (#248). */
function RegistrationClosed() {
  useDocumentTitle("Registro cerrado");
  const location = useLocation();
  const status = useAuthStore((state) => state.status);
  if (status === "authenticated") return <Navigate to={destination(location.state)} replace />;
  return (
    <>
      <SiteHeader showSections={false} />
      <main className="login">
        <h1 className="login__title">
          <span>Registro cerrado</span>
        </h1>
        <div className="login__form">
          <p className="login__notice">
            Ahora no se pueden crear cuentas: las cuentas las crea un investigador del proyecto. Si
            el equipo te dio una, entra con tu usuario y tu contraseña.
          </p>
          <Link className="button login__submit" to="/entrar" state={location.state as unknown}>
            Ir a entrar
            <PixelIcon name="arrow-right" />
          </Link>
        </div>
      </main>
    </>
  );
}

/**
 * Formulario del registro: solo usuario y contraseña, sin correo. La cuenta nace activa: tras
 * crearla, la vista entra con ella y lleva a la zona privada, o a la vista de la que se venía
 * (`state.from`, como al entrar: la portada con la imagen elegida, #277). Si ese acceso falla,
 * dice que la cuenta existe y enlaza a la página de entrar.
 */
function RegisterForm() {
  useDocumentTitle("Crear una cuenta");
  const location = useLocation();
  const status = useAuthStore((state) => state.status);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<RegisterError | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [created, setCreated] = useState<{ user: UserRead; notice: string } | null>(null);
  const usernameRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const confirmationRef = useRef<HTMLInputElement>(null);
  const consentRef = useRef<HTMLInputElement>(null);
  const errorRef = useRef<HTMLParagraphElement>(null);
  const doneRef = useRef<HTMLHeadingElement>(null);

  // Tras un error, el foco va al campo que hay que corregir o, si no es de un campo, al aviso.
  useEffect(() => {
    if (!error) return;
    const fields = {
      username: usernameRef,
      password: passwordRef,
      confirmation: confirmationRef,
      consent: consentRef,
    };
    (error.field ? fields[error.field] : errorRef).current?.focus();
  }, [error]);

  useEffect(() => {
    if (created) doneRef.current?.focus();
  }, [created]);

  if (status === "authenticated") return <Navigate to={destination(location.state)} replace />;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitting) return;
    const name = username.trim();
    if (!USERNAME_PATTERN.test(name)) {
      setError({ message: `Usuario no válido. ${USERNAME_RULE}`, field: "username" });
      return;
    }
    if (passwordLength(password) < MIN_PASSWORD) {
      setError({
        message: `La contraseña debe tener al menos ${String(MIN_PASSWORD)} caracteres.`,
        field: "password",
      });
      return;
    }
    if (password !== confirmation) {
      setError({ message: "Las dos contraseñas no coinciden.", field: "confirmation" });
      return;
    }
    // La casilla del permiso es obligatoria para crear la cuenta (#378, ADR-0065).
    if (!consent) {
      setError({ message: CONSENT_REQUIRED, field: "consent" });
      return;
    }
    setSubmitting(true);
    setError(null);
    let user: UserRead;
    try {
      user = await registerUser(api, name, password, consent);
    } catch (caught) {
      // Los fallos pasajeros (límite, red, servidor) no obligan a escribirla de nuevo.
      setError(registerErrorMessage(caught));
      setSubmitting(false);
      return;
    }
    try {
      // Al entrar, el estado pasa a autenticado y el <Navigate> de arriba lleva a la zona privada
      // o a la vista de la que se venía.
      await logIn(api, name, password);
    } catch (caught) {
      // La cuenta existe aunque no se haya podido entrar con ella: se dice por qué y se enlaza a
      // entrar. Si falla `/auth/me`, `logIn` no deja una sesión a medias.
      setPassword("");
      setConfirmation("");
      setCreated({ user, notice: autoLoginNotice(caught) });
      setSubmitting(false);
    }
  };

  const describedBy = (field: RegisterField, help?: string) =>
    [error?.field === field ? "register-error" : null, help].filter(Boolean).join(" ") || undefined;

  return (
    <>
      <SiteHeader showSections={false} />
      <main className="login">
        <h1 className="login__title">
          <span>Crear cuenta</span>
        </h1>
        {created ? (
          <section
            className="login__form"
            aria-labelledby="register-done"
            aria-describedby="register-done-notice"
          >
            <h2
              className="login__done-title"
              id="register-done"
              ref={doneRef}
              tabIndex={-1}
              aria-describedby="register-done-notice"
            >
              Cuenta creada
            </h2>
            <p className="login__done-user">
              Tu usuario es <strong>{created.user.username}</strong>.
            </p>
            <p className="login__notice" id="register-done-notice">
              {created.notice}
            </p>
            <Link className="button login__submit" to="/entrar" state={location.state as unknown}>
              Ir a entrar
              <PixelIcon name="arrow-right" />
            </Link>
          </section>
        ) : (
          <form className="login__form" onSubmit={(event) => void submit(event)} noValidate>
            {error && (
              <p
                className="login__error"
                role="alert"
                id="register-error"
                ref={errorRef}
                tabIndex={-1}
              >
                {error.message}
              </p>
            )}
            <div className="field">
              <label className="label" htmlFor="register-username">
                Usuario
              </label>
              <input
                ref={usernameRef}
                id="register-username"
                name="username"
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                maxLength={64}
                value={username}
                onChange={(event) => {
                  setUsername(event.target.value);
                }}
                readOnly={submitting}
                aria-invalid={error?.field === "username"}
                aria-describedby={describedBy("username", "register-username-help")}
                required
              />
              <p className="login__hint" id="register-username-help">
                {USERNAME_RULE} Puede ser un seudónimo: no pedimos tu nombre ni tu correo.
              </p>
            </div>
            <div className="field">
              <label className="label" htmlFor="register-password">
                Contraseña
              </label>
              <input
                ref={passwordRef}
                id="register-password"
                name="password"
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(event) => {
                  setPassword(event.target.value);
                }}
                readOnly={submitting}
                aria-invalid={error?.field === "password"}
                aria-describedby={describedBy("password", "register-password-help")}
                required
              />
              <p className="login__hint" id="register-password-help">
                Al menos {MIN_PASSWORD} caracteres. No hay recuperación por correo: guárdala bien.
              </p>
            </div>
            <div className="field">
              <label className="label" htmlFor="register-confirmation">
                Repite la contraseña
              </label>
              <input
                ref={confirmationRef}
                id="register-confirmation"
                name="confirmation"
                type="password"
                autoComplete="new-password"
                value={confirmation}
                onChange={(event) => {
                  setConfirmation(event.target.value);
                }}
                readOnly={submitting}
                aria-invalid={error?.field === "confirmation"}
                aria-describedby={describedBy("confirmation")}
                required
              />
            </div>
            <fieldset className="field register__consent">
              <legend className="label">Uso de tus datos</legend>
              <DataConsentNotice id="register-consent-notice" expandable />
              <div className="consent-check">
                <input
                  ref={consentRef}
                  id="register-consent"
                  name="data_consent"
                  type="checkbox"
                  checked={consent}
                  onChange={(event) => {
                    setConsent(event.target.checked);
                  }}
                  disabled={submitting}
                  aria-invalid={error?.field === "consent"}
                  aria-describedby={describedBy("consent", "register-consent-notice")}
                  required
                />
                <label htmlFor="register-consent">
                  Doy mi permiso para que se usen mis datos así.
                </label>
              </div>
            </fieldset>
            <button
              className="button button--primary login__submit"
              type="submit"
              disabled={submitting}
            >
              {submitting ? "Creando la cuenta…" : "Crear cuenta y entrar"}
              {!submitting && <PixelIcon name="arrow-right" />}
            </button>
            <p className="login__help">
              Entras en el momento, sin esperar a nadie.{" "}
              <Link to="/entrar" state={location.state as unknown}>
                ¿Ya tienes cuenta? Entra
              </Link>
              .
            </p>
          </form>
        )}
      </main>
    </>
  );
}
