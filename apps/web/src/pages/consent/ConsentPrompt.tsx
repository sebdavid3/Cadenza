import { useEffect, useRef, useState } from "react";
import { api } from "../../api/instance";
import { useAuthStore } from "../../auth/store";
import "../../components/button.css";
import "../login/login.css";
import {
  consentErrorMessage,
  consentVersionLabel,
  DATA_CONSENT_VERSION,
  setDataConsent,
} from "./consent";
import "./consent.css";
import { DataConsentNotice } from "./DataConsentNotice";

/** Dónde se recuerda «Ahora no» durante una entrada, también al recargar la página. */
const LATER_KEY = "cadenza.consent-later";

/**
 * Lo que identifica una entrada: la cuenta, el texto y cuándo vence la sesión, que cambia en cada
 * inicio de sesión y se conserva al recargar. «Ahora no» vale para esa entrada; en la siguiente
 * se vuelve a pedir.
 */
function entryKey(username: string, expiresAt: number | null): string {
  return `${username}|${DATA_CONSENT_VERSION}|${String(expiresAt ?? "")}`;
}

function readLater(): string | null {
  try {
    return sessionStorage.getItem(LATER_KEY);
  } catch {
    return null;
  }
}

function writeLater(value: string) {
  try {
    sessionStorage.setItem(LATER_KEY, value);
  } catch {
    // Sin almacén de la sesión, «Ahora no» dura hasta recargar: se vuelve a pedir entonces.
  }
}

/** Tras quitar la banda, el foco vuelve al título de la página (lo tiene `tabIndex={-1}`). */
function focusPageTitle() {
  requestAnimationFrame(() => {
    document.querySelector<HTMLElement>("h1")?.focus();
  });
}

/**
 * Pide al entrar (#430, ADR-0065) que vuelva a dar el permiso de uso de los datos una cuenta del
 * registro que lo dio para un texto anterior: #427 subió la versión y, como promete el texto, el
 * permiso dejó de estar vigente. A quien lo retiró no se le insiste: retirarlo borra la versión,
 * así que no queda «anterior» que pedir renovar, y puede volver a darlo en «Tu cuenta».
 *
 * Lo da con un gesto o lo deja para otra entrada; sin él, Cadenza se usa igual. El marco de la
 * zona privada lo coloca bajo su cabecera, fuera de la vista de una sesión y de «Tu cuenta», que
 * tiene su propio interruptor.
 */
export function ConsentPrompt() {
  const user = useAuthStore((state) => state.user);
  const expiresAt = useAuthStore((state) => state.expiresAt);
  const [later, setLater] = useState(readLater);
  const [thanks, setThanks] = useState(false);
  const [closed, setClosed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const closeRef = useRef<HTMLButtonElement>(null);

  // Al dar el permiso desaparece el botón que tenía el foco: pasa a «Cerrar».
  useEffect(() => {
    if (thanks) closeRef.current?.focus();
  }, [thanks]);

  // Es el permiso de las cuentas del registro; las del equipo no dependen de él (ADR-0065 §5).
  if (!user?.self_registered || closed) return null;
  const outdated = !user.data_consent && Boolean(user.data_consent_version);
  if (!thanks && !outdated) return null;
  const key = entryKey(user.username, expiresAt);
  if (!thanks && later === key) return null;

  const grant = async () => {
    // Mientras guarda, el botón no se deshabilita (perdería el foco): se ignora otro toque.
    if (savingRef.current) return;
    savingRef.current = true;
    setSaving(true);
    setError(null);
    try {
      const updated = await setDataConsent(api, true);
      useAuthStore.setState({ user: updated });
      setThanks(true);
    } catch (caught) {
      setError(consentErrorMessage(caught));
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };

  return (
    <section className="consent-prompt" aria-labelledby="consent-prompt-title">
      {/* Rótulo, no encabezado: la banda va antes del `h1` de la página. */}
      <p id="consent-prompt-title" className="consent-prompt__title">
        Tu permiso de uso de los datos
      </p>
      {!thanks && (
        <>
          <p className="consent-prompt__lead">
            El texto del permiso ha cambiado: el de ahora es del {consentVersionLabel()}. Léelo y,
            si estás de acuerdo, vuelve a darlo. Sin él puedes seguir usando Cadenza igual.
          </p>
          <DataConsentNotice id="consent-prompt-notice" />
          <div className="consent-prompt__actions">
            <button
              type="button"
              className="button button--primary"
              aria-disabled={saving}
              aria-describedby="consent-prompt-notice"
              onClick={() => {
                void grant();
              }}
            >
              Doy mi permiso
            </button>
            <button
              type="button"
              className="button"
              aria-disabled={saving}
              onClick={() => {
                // Mientras se guarda, la respuesta decide: no se oculta a medias.
                if (savingRef.current) return;
                writeLater(key);
                setLater(key);
                focusPageTitle();
              }}
            >
              Ahora no
            </button>
          </div>
        </>
      )}
      {/* Región viva presente desde el principio, como en «Tu cuenta»: el agradecimiento se
          anuncia al llegar. */}
      <p className="consent-prompt__status" aria-live="polite">
        {thanks
          ? "Gracias: has dado tu permiso. Puedes retirarlo cuando quieras desde «Tu cuenta»."
          : ""}
      </p>
      {thanks && (
        <button
          ref={closeRef}
          type="button"
          className="button button--compact"
          onClick={() => {
            setClosed(true);
            focusPageTitle();
          }}
        >
          Cerrar
        </button>
      )}
      {error && (
        <p className="login__error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
