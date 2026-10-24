import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import type { FindingRead } from "../../types";
import type { FindingOutcome } from "./findingActions";
import { ruleLabel, type MeasureMark, type ValidationState } from "./findings";

/**
 * Lo que puede hacer con los posibles errores quien transcribió la sesión, mientras no esté
 * finalizada (ADR-0035). Sin esto, el panel es de solo lectura.
 */
export interface FindingsPanelActions {
  /** Hay una orden en curso: no se envía otra. */
  busy: boolean;
  /** Se está guardando una corrección: revalidar esperaría a un estado que va a cambiar. */
  editorBusy: boolean;
  /** Posible error sobre el que hay una orden en curso. */
  pendingId: number | null;
  onDismiss: (finding: FindingRead, reason: string) => Promise<FindingOutcome>;
  onRestore: (finding: FindingRead) => Promise<FindingOutcome>;
  onRevalidate: () => Promise<FindingOutcome>;
  /** Carga el estado actual de la sesión, si la lista es de uno posterior al que se ve. */
  onReload: () => Promise<boolean>;
}

interface FindingsPanelProps {
  marks: readonly MeasureMark[];
  /** Hallazgos activos cuyo compás no está en la partitura: se listan sin marca. */
  unplaced: readonly FindingRead[];
  dismissed: readonly FindingRead[];
  /** De qué estado es la última validación respecto al que se ve. */
  validation: ValidationState;
  /** Ediciones de la sesión: sin ninguna, la validación es la de la transcripción. */
  edits: number;
  /** Con varios pentagramas, cada compás dice en cuál está. */
  multiStaff: boolean;
  /** Si las marcas no se pudieron situar, los compases de la lista no se pueden resaltar. */
  selectable: boolean;
  selectedKey: string | null;
  onSelect: (key: string | null) => void;
  /** Mientras llegan o si fallan los hallazgos, el panel lo dice en su lugar. */
  status: "loading" | "error" | "ready";
  errorText?: string;
  onRetry?: () => void;
  /** Dónde está un posible error, para nombrar sus acciones: «compás 3». */
  placeOf: (finding: FindingRead) => string;
  actions?: FindingsPanelActions;
  /** Qué pasó con la última orden sobre los posibles errores (región `aria-live`). */
  message: string | null;
}

/**
 * Regla y mensaje de un posible error. Con varios en un compás que se pueden descartar, cada uno
 * lleva su número, el de su botón. El mensaje describe ese botón (`id`).
 */
function FindingText({
  finding,
  ordinal = null,
  id,
}: {
  finding: FindingRead;
  ordinal?: number | null;
  id: string;
}) {
  return (
    <>
      <span className="label findings__rule">
        {ordinal !== null && `${String(ordinal)} · `}
        {ruleLabel(finding.rule_id)}
      </span>
      <span id={id} className="findings__message">
        {finding.message}
      </span>
    </>
  );
}

function measureName(mark: MeasureMark, multiStaff: boolean) {
  const staff = multiStaff ? ` · pentagrama ${String(mark.slot.staff + 1)}` : "";
  return `Compás ${String(mark.measureNumber)}${staff}`;
}

/** Qué decir cuando no queda ningún posible error activo, sin prometer más de lo que se sabe. */
function EmptyMessage({
  dismissed,
  edits,
  validation,
}: {
  dismissed: number;
  edits: number;
  validation: ValidationState;
}) {
  if (dismissed > 0) {
    return (
      <p className="findings__empty">
        No queda ningún posible error activo: los que señaló el validador se descartaron como falso
        positivo. Descartarlos no cambió la partitura, y que no quede ninguno no garantiza que la
        transcripción esté bien.
      </p>
    );
  }
  // Revalidada después de editar: la validación es de la partitura que se ve.
  if (validation.kind === "current" && edits > 0) {
    return (
      <p className="findings__empty">
        El validador no señala ningún compás en la partitura actual.
      </p>
    );
  }
  return (
    <p className="findings__empty">
      El validador no señaló ningún compás en su última validación.
      {validation.kind === "unknown" &&
        " La partitura tiene ediciones: si se hicieron después de esa validación, puede que el resultado ya no esté al día."}
    </p>
  );
}

/** De qué partitura es una validación anterior a la que se ve. */
function validatedState(seq: number) {
  return seq === 0
    ? "la partitura tal como la transcribió HOMR"
    : `la partitura tal como estaba tras ${String(seq)} ${seq === 1 ? "edición" : "ediciones"}`;
}

/** Tras una orden, a dónde va el foco: lo que lo tenía puede haber desaparecido. */
type FocusTarget = { kind: "dismiss"; id: number } | { kind: "revalidate" } | { kind: "heading" };

/** El formulario del descarte: dice antes de enviarlo que descartar no corrige nada (ADR-0021 §4). */
function DismissForm({
  id,
  label,
  saving,
  busy,
  onCancel,
  onSubmit,
}: {
  id: string;
  label: string;
  saving: boolean;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (reason: string) => void;
}) {
  const [reason, setReason] = useState("");
  const fieldRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    fieldRef.current?.focus();
  }, []);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!busy) onSubmit(reason);
  }

  function onKeyDown(event: KeyboardEvent) {
    if (event.key !== "Escape" || saving) return;
    event.preventDefault();
    onCancel();
  }

  return (
    <form
      id={id}
      className="findings__dismiss"
      aria-label={`Descartar como falso positivo · ${label}`}
      onSubmit={submit}
      onKeyDown={onKeyDown}
    >
      <p className="findings__dismiss-note">
        Descartar no corrige la partitura: el compás deja de señalarse, pero sus notas siguen igual.
        Si el error es real, corrígelo en la partitura.
      </p>
      <label className="findings__field">
        <span className="label">Motivo (opcional)</span>
        <input
          ref={fieldRef}
          type="text"
          className="findings__input"
          value={reason}
          maxLength={500}
          autoComplete="off"
          onChange={(event) => {
            setReason(event.target.value);
          }}
        />
      </label>
      <div className="findings__dismiss-actions">
        <button type="submit" className="button button--compact" aria-disabled={busy || undefined}>
          Descartar como falso positivo
        </button>
        <button
          type="button"
          className="link-button"
          aria-disabled={saving || undefined}
          onClick={() => {
            if (!saving) onCancel();
          }}
        >
          Cancelar
        </button>
      </div>
    </form>
  );
}

/**
 * Descartar un posible error: un botón que abre debajo el formulario con el motivo, opcional. Su
 * nombre dice qué y dónde, y su descripción es el mensaje del posible error. Con varios en el
 * compás (por ejemplo, uno por voz, ADR-0032), lleva el número del suyo.
 */
function DismissControl({
  finding,
  place,
  ordinal,
  describedBy,
  open,
  saving,
  busy,
  onOpen,
  onClose,
  onSubmit,
}: {
  finding: FindingRead;
  /** Dónde está: «compás 3». */
  place: string;
  /** Su número entre los posibles errores del compás, o null si es el único. */
  ordinal: number | null;
  /** El elemento con su mensaje. */
  describedBy: string;
  open: boolean;
  saving: boolean;
  busy: boolean;
  onOpen: () => void;
  onClose: () => void;
  onSubmit: (reason: string) => void;
}) {
  const formId = useId();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const rule = ruleLabel(finding.rule_id);

  return (
    <div className="findings__control">
      <button
        ref={triggerRef}
        type="button"
        className="link-button findings__action"
        aria-expanded={open}
        aria-controls={open ? formId : undefined}
        aria-disabled={busy || undefined}
        aria-describedby={describedBy}
        data-dismiss={finding.id}
        onClick={() => {
          if (busy) return;
          if (open) onClose();
          else onOpen();
        }}
      >
        {/* Los espacios, fuera de lo oculto: el nombre accesible recorta los de cada hijo. */}
        Descartar{ordinal !== null && ` ${String(ordinal)}`}{" "}
        <span className="visually-hidden">como falso positivo</span>{" "}
        <span className="visually-hidden">
          · {rule}, {place}
        </span>
      </button>
      {open && (
        <DismissForm
          id={formId}
          label={`${rule}, ${place}`}
          saving={saving}
          busy={busy}
          onCancel={() => {
            onClose();
            triggerRef.current?.focus();
          }}
          onSubmit={onSubmit}
        />
      )}
    </div>
  );
}

/**
 * Posibles errores del validador agrupados por compás. Nunca se presentan como errores seguros:
 * el validador no lo detecta todo y lo que señala hay que comprobarlo (ADR-0021). Quien transcribió
 * la sesión puede descartar cada uno como falso positivo, restaurarlo y revalidar tras corregir
 * (ADR-0035); descartar no corrige nada, y se dice.
 */
export function FindingsPanel({
  marks,
  unplaced,
  dismissed,
  validation,
  edits,
  multiStaff,
  selectable,
  selectedKey,
  onSelect,
  status,
  errorText,
  onRetry,
  placeOf,
  actions,
  message,
}: FindingsPanelProps) {
  const total = marks.reduce((count, mark) => count + mark.findings.length, 0) + unplaced.length;
  const panelRef = useRef<HTMLElement>(null);
  const idBase = useId();
  const messageId = (finding: FindingRead) => `${idBase}-mensaje-${String(finding.id)}`;
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  // Tras una orden, el foco va a donde se pidió en cuanto la lista nueva está dibujada; si eso ya
  // no está, al título del panel. Cada petición se atiende una vez.
  const [focusRequest, setFocusRequest] = useState<{ target: FocusTarget; nonce: number } | null>(
    null,
  );
  const handledFocus = useRef(0);
  useEffect(() => {
    if (!focusRequest || handledFocus.current === focusRequest.nonce) return;
    handledFocus.current = focusRequest.nonce;
    const { target } = focusRequest;
    const panel = panelRef.current;
    const element =
      target.kind === "dismiss"
        ? panel?.querySelector<HTMLElement>(`[data-dismiss="${String(target.id)}"]`)
        : target.kind === "revalidate"
          ? panel?.querySelector<HTMLElement>(".findings__revalidate")
          : null;
    (element ?? headingRef.current)?.focus();
  }, [focusRequest]);
  const focusAfter = (target: FocusTarget) => {
    setFocusRequest((previous) => ({ target, nonce: (previous?.nonce ?? 0) + 1 }));
  };

  // Sin acciones (la sesión pasó a solo lectura), ningún formulario sigue abierto.
  const open = actions ? openId : null;
  const busy = actions?.busy ?? false;
  // Orden de la lista: el foco pasa al posible error siguiente al descartado, o al anterior.
  const order = [...marks.flatMap((mark) => mark.findings), ...unplaced].map((f) => f.id);

  async function dismiss(finding: FindingRead, reason: string) {
    if (!actions) return;
    const position = order.indexOf(finding.id);
    const neighbour = order[position + 1] ?? order[position - 1];
    const outcome = await actions.onDismiss(finding, reason);
    if (outcome === "done") {
      setOpenId(null);
      focusAfter(
        neighbour === undefined ? { kind: "heading" } : { kind: "dismiss", id: neighbour },
      );
    } else if (outcome === "gone" || outcome === "closed") {
      setOpenId(null);
      focusAfter({ kind: "heading" });
    }
  }

  async function restore(finding: FindingRead) {
    if (!actions || busy) return;
    const outcome = await actions.onRestore(finding);
    if (outcome === "done") focusAfter({ kind: "dismiss", id: finding.id });
    else if (outcome === "gone" || outcome === "closed") focusAfter({ kind: "heading" });
  }

  async function revalidate() {
    if (!actions || busy || actions.editorBusy) return;
    setOpenId(null);
    const outcome = await actions.onRevalidate();
    if (outcome === "done") focusAfter({ kind: "revalidate" });
  }

  async function reload() {
    if (!actions || busy || actions.editorBusy) return;
    if (await actions.onReload()) focusAfter({ kind: "heading" });
  }

  function dismissControls(findings: readonly FindingRead[]) {
    if (!actions) return null;
    return (
      <div className="findings__actions">
        {findings.map((finding, index) => (
          <DismissControl
            key={finding.id}
            finding={finding}
            place={placeOf(finding)}
            ordinal={findings.length > 1 ? index + 1 : null}
            describedBy={messageId(finding)}
            open={open === finding.id}
            saving={actions.pendingId === finding.id}
            busy={busy}
            onOpen={() => {
              setOpenId(finding.id);
            }}
            onClose={() => {
              setOpenId(null);
            }}
            onSubmit={(reason) => void dismiss(finding, reason)}
          />
        ))}
      </div>
    );
  }

  const revalidateButton = actions && (
    <button
      type="button"
      className="button button--compact findings__revalidate"
      aria-disabled={busy || actions.editorBusy || undefined}
      onClick={() => void revalidate()}
    >
      Revalidar
    </button>
  );

  return (
    <section ref={panelRef} className="findings" aria-labelledby="findings-title">
      <div className="findings__head">
        <h2 id="findings-title" ref={headingRef} className="findings__title" tabIndex={-1}>
          Posibles errores
        </h2>
        {status === "ready" && <span className="label findings__count">{total}</span>}
      </div>

      <p className="findings__status" role="status">
        {message}
      </p>

      {status === "loading" && (
        <p className="findings__empty" role="status">
          Cargando los posibles errores…
        </p>
      )}

      {status === "error" && (
        <div className="findings__error" role="alert">
          <p>No se pudieron cargar los posibles errores. {errorText}</p>
          {onRetry && (
            <button type="button" className="link-button" onClick={onRetry}>
              Reintentar
            </button>
          )}
        </div>
      )}

      {status === "ready" && validation.kind === "stale" && (
        <div className="findings__stale">
          <p>
            {total + dismissed.length > 0
              ? `Corresponden a ${validatedState(validation.seq)}`
              : `La última validación fue sobre ${validatedState(validation.seq)}`}
            ; después se editó y todavía no se ha vuelto a validar.
          </p>
          {revalidateButton}
        </div>
      )}

      {status === "ready" && validation.kind === "ahead" && (
        <div className="findings__stale">
          <p>
            Corresponden a un estado de la partitura posterior al que ves: se editó en otra pestaña
            o dispositivo.{" "}
            {actions ? "Recarga la sesión para verlo." : "Recarga la página para verlo."}
          </p>
          {actions && (
            <button
              type="button"
              className="button button--compact"
              aria-disabled={busy || actions.editorBusy || undefined}
              onClick={() => void reload()}
            >
              Recargar la sesión
            </button>
          )}
        </div>
      )}

      {status === "ready" && total === 0 && (
        <EmptyMessage dismissed={dismissed.length} edits={edits} validation={validation} />
      )}
      {status === "ready" && total === 0 && validation.kind === "unknown" && revalidateButton}

      {status === "ready" && total > 0 && (
        <ul className="findings__list" role="list">
          {marks.map((mark) => {
            const selected = mark.key === selectedKey;
            const content = (
              <>
                <span className="findings__measure">{measureName(mark, multiStaff)}</span>
                {mark.findings.map((finding, index) => (
                  <span key={finding.id} className="findings__finding">
                    <FindingText
                      finding={finding}
                      id={messageId(finding)}
                      ordinal={actions && mark.findings.length > 1 ? index + 1 : null}
                    />
                  </span>
                ))}
              </>
            );
            return (
              <li key={mark.key} className="findings__entry">
                {selectable ? (
                  <button
                    type="button"
                    className="findings__item"
                    aria-pressed={selected}
                    onClick={() => {
                      onSelect(selected ? null : mark.key);
                    }}
                  >
                    {content}
                  </button>
                ) : (
                  <div className="findings__item findings__item--static">{content}</div>
                )}
                {dismissControls(mark.findings)}
              </li>
            );
          })}
          {unplaced.map((finding) => (
            <li key={finding.id} className="findings__entry">
              <div className="findings__item findings__item--static">
                <span className="findings__measure">Compás {finding.anchor.measure}</span>
                <span className="findings__finding">
                  <FindingText finding={finding} id={messageId(finding)} />
                </span>
                <span className="findings__reason">
                  Ese compás ya no está en la partitura: no se puede marcar.
                </span>
              </div>
              {dismissControls([finding])}
            </li>
          ))}
        </ul>
      )}

      <p className="findings__notice">
        El validador señala compases que conviene revisar con la imagen. No lo detecta todo: que no
        señale un compás no garantiza que esté bien transcrito.
        {actions && " Descartar un posible error no corrige la partitura: solo deja de señalarlo."}
      </p>

      {status === "ready" && dismissed.length > 0 && (
        <details className="findings__dismissed">
          <summary className="label">Descartados como falso positivo · {dismissed.length}</summary>
          <ul role="list">
            {dismissed.map((finding) => (
              <li key={finding.id} className="findings__dismissed-item">
                <span className="findings__measure">Compás {finding.anchor.measure}</span>
                <FindingText finding={finding} id={messageId(finding)} />
                {finding.dismissal_reason && (
                  <span className="findings__reason">Motivo: {finding.dismissal_reason}</span>
                )}
                {actions && (
                  <button
                    type="button"
                    className="link-button findings__action"
                    aria-disabled={busy || undefined}
                    aria-describedby={messageId(finding)}
                    onClick={() => void restore(finding)}
                  >
                    Restaurar{" "}
                    <span className="visually-hidden">
                      · {ruleLabel(finding.rule_id)}, {placeOf(finding)}
                    </span>
                  </button>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
