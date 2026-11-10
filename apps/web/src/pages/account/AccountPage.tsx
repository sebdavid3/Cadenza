import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError } from "../../api/errors";
import { api } from "../../api/instance";
import { useAuthStore } from "../../auth/store";
import "../../components/button.css";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { consentErrorMessage, setDataConsent } from "../consent/consent";
import "../consent/consent.css";
import { DataConsentNotice } from "../consent/DataConsentNotice";
import { parseUtc } from "../transcription/sessions";
import "../login/login.css";
import { MIN_PASSWORD, passwordLength } from "../register/register";
import {
  afterChangeNotice,
  changePassword,
  passwordErrorMessage,
  sessionStillValid,
  SHORT_PASSWORD_MESSAGE,
  type PasswordError,
  type PasswordField,
} from "./account";
import "./account.css";

/**
 * Tu cuenta (#190): quien tiene sesión cambia su contraseña. No hay recuperación por correo
 * (PRODUCT.md) y la web no la restablece (#155). Aquí se da o se retira también el permiso de
 * uso de los datos, con el mismo texto que en el registro (#378, ADR-0064).
 */
export function AccountPage() {
  useDocumentTitle("Tu cuenta");
  const user = useAuthStore((state) => state.user);

  return (
    <main className="account">
      <header className="account__head">
        <h1 className="account__title">Tu cuenta</h1>
        {user && (
          <p className="account__lead">
            Has entrado como <strong>{user.username}</strong>. No hay recuperación de la contraseña
            por correo ni desde la web: guárdala bien y, si la olvidas, habla con el equipo del
            proyecto.
          </p>
        )}
      </header>
      <DataConsentSection />
      <section className="account__panel" aria-labelledby="password-title">
        <h2 id="password-title" className="account__subtitle">
          Cambiar la contraseña
        </h2>
        <PasswordForm username={user?.username ?? ""} />
      </section>
    </main>
  );
}

/**
 * Contraseña actual, nueva y su repetición, con las mismas comprobaciones previas que el registro.
 * Un 401 dice que la actual no es correcta sin cerrar la sesión, salvo que la sesión ya no valga.
 * Tras el cambio, la sesión abierta sigue hasta que vence y la vista lo dice.
 */
function PasswordForm({ username }: { username: string }) {
  const expiresAt = useAuthStore((state) => state.expiresAt);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<PasswordError | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [changed, setChanged] = useState(false);
  const currentRef = useRef<HTMLInputElement>(null);
  const nextRef = useRef<HTMLInputElement>(null);
  const confirmationRef = useRef<HTMLInputElement>(null);
  const errorRef = useRef<HTMLParagraphElement>(null);
  const doneRef = useRef<HTMLParagraphElement>(null);

  // Tras un error, el foco va al campo que hay que corregir o, si no es de un campo, al aviso.
  useEffect(() => {
    if (!error) return;
    const fields = { current: currentRef, next: nextRef, confirmation: confirmationRef };
    const target = (error.field ? fields[error.field] : errorRef).current;
    target?.focus();
    // La contraseña equivocada queda elegida: lo que se escriba la sustituye.
    if (target instanceof HTMLInputElement) target.select();
  }, [error]);

  useEffect(() => {
    if (changed) doneRef.current?.focus();
  }, [changed]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitting) return;
    setChanged(false);
    if (current === "") {
      setError({ message: "Escribe tu contraseña actual.", field: "current" });
      return;
    }
    if (passwordLength(next) < MIN_PASSWORD) {
      setError({ message: SHORT_PASSWORD_MESSAGE, field: "next" });
      return;
    }
    // Igual que la actual, el aviso de después («la anterior ya no vale») sería falso.
    if (next === current) {
      setError({ message: "La contraseña nueva es igual a la actual.", field: "next" });
      return;
    }
    if (next !== confirmation) {
      setError({ message: "Las dos contraseñas nuevas no coinciden.", field: "confirmation" });
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await changePassword(api, current, next);
    } catch (caught) {
      const failure = passwordErrorMessage(caught);
      // Un 401 es la actual equivocada solo si la sesión sigue valiendo; si no, la comprobación
      // la cierra y la ruta privada lleva a entrar.
      if (
        caught instanceof ApiError &&
        caught.kind === "unauthorized" &&
        !(await sessionStillValid(api))
      ) {
        setSubmitting(false);
        return;
      }
      setError(failure);
      setSubmitting(false);
      return;
    }
    setCurrent("");
    setNext("");
    setConfirmation("");
    setSubmitting(false);
    setChanged(true);
  };

  const describedBy = (field: PasswordField, help?: string) =>
    [error?.field === field ? "password-error" : null, help].filter(Boolean).join(" ") || undefined;

  return (
    <form
      className="account__form"
      aria-labelledby="password-title"
      onSubmit={(event) => void submit(event)}
      noValidate
    >
      {/* Para que el gestor de contraseñas sepa de qué cuenta es la nueva. */}
      <input type="text" name="username" autoComplete="username" value={username} readOnly hidden />
      {error && (
        <p className="login__error" role="alert" id="password-error" ref={errorRef} tabIndex={-1}>
          {error.message}
        </p>
      )}
      {changed && (
        <p className="login__notice account__done" role="status" ref={doneRef} tabIndex={-1}>
          <strong>Contraseña cambiada.</strong> {afterChangeNotice(expiresAt)}
        </p>
      )}
      <div className="field">
        <label className="label" htmlFor="password-current">
          Contraseña actual
        </label>
        <input
          ref={currentRef}
          id="password-current"
          name="current-password"
          type="password"
          autoComplete="current-password"
          value={current}
          onChange={(event) => {
            setCurrent(event.target.value);
          }}
          readOnly={submitting}
          aria-invalid={error?.field === "current"}
          aria-describedby={describedBy("current")}
          required
        />
      </div>
      <div className="field">
        <label className="label" htmlFor="password-next">
          Contraseña nueva
        </label>
        <input
          ref={nextRef}
          id="password-next"
          name="new-password"
          type="password"
          autoComplete="new-password"
          value={next}
          onChange={(event) => {
            setNext(event.target.value);
          }}
          readOnly={submitting}
          aria-invalid={error?.field === "next"}
          aria-describedby={describedBy("next", "password-next-help")}
          required
        />
        <p className="login__hint" id="password-next-help">
          Al menos {MIN_PASSWORD} caracteres. No hay recuperación por correo: guárdala bien.
        </p>
      </div>
      <div className="field">
        <label className="label" htmlFor="password-confirmation">
          Repite la contraseña nueva
        </label>
        <input
          ref={confirmationRef}
          id="password-confirmation"
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
      <button className="button button--primary login__submit" type="submit" disabled={submitting}>
        {submitting ? "Cambiando la contraseña…" : "Cambiar la contraseña"}
      </button>
    </form>
  );
}

/**
 * El día en que se dio el permiso, en la hora local y en español: «9 de noviembre de 2026». Con
 * SQLite la fecha llega sin zona, pero es UTC, como `created_at` (`parseUtc`).
 */
function consentDate(value: string): string {
  return parseUtc(value).toLocaleDateString("es", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

/**
 * El permiso de uso de los datos (#378, ADR-0064): el mismo aviso que en el registro y un
 * interruptor que lo da o lo retira con un solo gesto. Lo que se guarda vuelve en el perfil, que
 * pasa a ser el de la sesión.
 */
function DataConsentSection() {
  const user = useAuthStore((state) => state.user);
  const [saving, setSaving] = useState(false);
  const [changed, setChanged] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!user) return null;
  const granted = user.data_consent ?? false;
  // Dado para una versión anterior del texto: no está vigente hasta que se vuelva a dar.
  const outdated = !granted && Boolean(user.data_consent_version);

  const toggle = async (next: boolean) => {
    setSaving(true);
    setError(null);
    setChanged(null);
    try {
      const updated = await setDataConsent(api, next);
      useAuthStore.setState({ user: updated });
      setChanged(next ? "Has dado tu permiso." : "Has retirado tu permiso.");
    } catch (caught) {
      setError(consentErrorMessage(caught));
    } finally {
      setSaving(false);
    }
  };

  const state = granted
    ? `Diste tu permiso el ${consentDate(user.data_consent_at ?? "")}.`
    : outdated
      ? "Diste tu permiso para una versión anterior de este texto: léelo y, si estás de acuerdo, vuelve a darlo."
      : "No has dado tu permiso.";

  return (
    <section className="account__panel" aria-labelledby="consent-title">
      <h2 id="consent-title" className="account__subtitle">
        Uso de tus datos
      </h2>
      <DataConsentNotice id="account-consent-notice" />
      <div className="consent-switch">
        <input
          id="account-consent"
          type="checkbox"
          role="switch"
          checked={granted}
          disabled={saving}
          aria-describedby="account-consent-notice account-consent-state"
          onChange={(event) => {
            void toggle(event.target.checked);
          }}
        />
        <label htmlFor="account-consent">Permitir que se usen mis datos así</label>
      </div>
      {/* Región viva sin rol «status»: el aviso de la contraseña ya lo es. */}
      <p id="account-consent-state" className="consent-status" aria-live="polite">
        {changed ?? state}
      </p>
      {error && (
        <p className="login__error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
