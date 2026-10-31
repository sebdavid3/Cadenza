import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import "./lifecycle.css";
import type { LifecycleOutcome } from "./lifecycle";

interface LifecyclePanelProps {
  /** Si la sesión está finalizada: entonces se ofrece reabrirla; si no, finalizarla. */
  finalized: boolean;
  /** Si es asistida: en una no asistida no se habla del validador (ADR-0040 §13). */
  assisted: boolean;
  /** Hay una orden del ciclo de vida en curso. */
  busy: boolean;
  /**
   * Otra cosa en curso (se guarda una corrección, se revalida, se descarta): finalizar validaría
   * un estado que va a cambiar, y espera.
   */
  waiting: boolean;
  /** Qué pasó con la última orden (región `aria-live`). */
  message: string | null;
  onFinalize: () => Promise<LifecycleOutcome>;
  onReopen: () => Promise<LifecycleOutcome>;
}

/** Tras una orden, a dónde va el foco: el botón que lo tenía puede haber desaparecido. */
type FocusTarget = "finalize" | "reopen";

/**
 * Finalizar la corrección, con confirmación, y reabrirla (#187, ADR-0043). Finalizar valida la
 * partitura tal como está y deja la sesión en solo lectura; reabrir la vuelve a hacer editable.
 * Solo para quien transcribió la sesión.
 */
export function LifecyclePanel({
  finalized,
  assisted,
  busy,
  waiting,
  message,
  onFinalize,
  onReopen,
}: LifecyclePanelProps) {
  const [confirming, setConfirming] = useState(false);
  const confirmId = useId();
  const noteId = useId();
  const finalizeRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const reopenRef = useRef<HTMLButtonElement>(null);
  // Tras una orden, el foco va a donde se pidió en cuanto ese botón está dibujado.
  const [focusRequest, setFocusRequest] = useState<{ target: FocusTarget; nonce: number } | null>(
    null,
  );
  const handledFocus = useRef(0);
  useEffect(() => {
    if (!focusRequest || handledFocus.current === focusRequest.nonce) return;
    // Si el botón pedido no está (la vista no llegó a cargar el estado nuevo), al que haya.
    const element =
      (focusRequest.target === "reopen" ? reopenRef.current : finalizeRef.current) ??
      reopenRef.current ??
      finalizeRef.current;
    if (!element) return;
    handledFocus.current = focusRequest.nonce;
    element.focus();
  });
  const focusAfter = (target: FocusTarget) => {
    setFocusRequest((previous) => ({ target, nonce: (previous?.nonce ?? 0) + 1 }));
  };
  useEffect(() => {
    if (confirming) confirmRef.current?.focus();
  }, [confirming]);

  // Finalizada (aquí o en otra pestaña), no queda nada que confirmar.
  const open = confirming && !finalized;
  const blocked = busy || waiting;

  async function finalize() {
    if (blocked) return;
    const outcome = await onFinalize();
    if (outcome === "ignored") return;
    setConfirming(false);
    focusAfter(outcome === "failed" ? "finalize" : "reopen");
  }

  async function reopen() {
    if (blocked) return;
    const outcome = await onReopen();
    if (outcome === "done") focusAfter("finalize");
  }

  function onKeyDown(event: KeyboardEvent) {
    if (event.key !== "Escape" || busy) return;
    event.preventDefault();
    setConfirming(false);
    finalizeRef.current?.focus();
  }

  return (
    <div className="lifecycle">
      {finalized ? (
        <button
          ref={reopenRef}
          type="button"
          className="button button--compact"
          aria-disabled={blocked || undefined}
          onClick={() => void reopen()}
        >
          Reabrir la sesión
        </button>
      ) : (
        <button
          ref={finalizeRef}
          type="button"
          className="button button--compact"
          aria-expanded={open}
          aria-controls={open ? confirmId : undefined}
          aria-disabled={(busy && !open) || undefined}
          onClick={() => {
            if (busy) return;
            setConfirming(!open);
          }}
        >
          Finalizar la corrección
        </button>
      )}
      {open && (
        <div
          id={confirmId}
          className="lifecycle__confirm"
          role="group"
          aria-label="Confirmar la finalización"
          aria-describedby={noteId}
          onKeyDown={onKeyDown}
        >
          <p id={noteId} className="lifecycle__note">
            {assisted
              ? "¿Das por terminada la corrección? Se validará la partitura tal como está y la sesión quedará en solo lectura, con el resultado de esa validación."
              : "¿Das por terminada la corrección? La sesión quedará en solo lectura."}{" "}
            Si se te pasó algo, podrás reabrirla.
          </p>
          <div className="lifecycle__actions">
            <button
              ref={confirmRef}
              type="button"
              className="button button--compact button--primary"
              aria-disabled={blocked || undefined}
              onClick={() => void finalize()}
            >
              Sí, finalizar
            </button>
            <button
              type="button"
              className="link-button"
              aria-disabled={busy || undefined}
              onClick={() => {
                if (busy) return;
                setConfirming(false);
                finalizeRef.current?.focus();
              }}
            >
              Cancelar
            </button>
          </div>
          {waiting && !busy && (
            <p className="lifecycle__wait">Espera a que termine lo que está en curso.</p>
          )}
        </div>
      )}
      <p className="lifecycle__status" role="status" aria-live="polite">
        {message}
      </p>
    </div>
  );
}
