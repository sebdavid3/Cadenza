import { PixelIcon, type PixelIconName } from "../../components/PixelIcon";
import { selectionReady, type SelectionControls } from "./selectionControls";

function unavailableText(total?: number, unmatched?: number): string {
  const base = "No se puede elegir nota a nota en esta partitura";
  if (total === undefined || unmatched === undefined) return `${base}.`;
  if (unmatched === total) return `${base}: ninguno de sus eventos coincide con lo dibujado.`;
  const verb = unmatched === 1 ? "no coincide" : "no coinciden";
  return `${base}: ${String(unmatched)} de los ${String(total)} eventos ${verb} con lo dibujado.`;
}

/** Tecla de una leyenda: un bloque de tinta con su rótulo o su flecha de píxel. */
export function KeyCap({ icon, children }: { icon?: PixelIconName; children: string }) {
  if (!icon) return <kbd className="selection__key">{children}</kbd>;
  return (
    <kbd className="selection__key">
      <PixelIcon name={icon} />
      <span className="visually-hidden">{children}</span>
    </kbd>
  );
}

/**
 * Qué está elegido o, si no se puede elegir, por qué: la nota elegida (dónde está y qué es), la
 * indicación para elegir una o el aviso de que la selección no se ofrece.
 */
export function SelectionReadout({
  status,
  description,
}: Pick<SelectionControls, "status" | "description">) {
  if (status.kind === "unavailable") {
    return <p className="selection__note">{unavailableText(status.total, status.unmatched)}</p>;
  }
  if (status.kind === "pending") {
    return <p className="selection__note">Preparando la selección de notas…</p>;
  }
  if (status.empty) {
    return <p className="selection__note">La partitura no tiene notas ni silencios que elegir.</p>;
  }
  return (
    <div className="selection__readout" data-selected={description !== null}>
      {description ? (
        <>
          <p className="label selection__place">{description.place}</p>
          <p className="selection__what">{description.what}</p>
        </>
      ) : (
        <p className="selection__hint">Elige una nota o un silencio: tócalo o usa las flechas.</p>
      )}
    </div>
  );
}

/** «Anterior», «Siguiente» y «Quitar»: en una pantalla táctil afinan lo que el dedo no alcanza. */
export function SelectionSteps({
  description,
  onPrevious,
  onNext,
  onClear,
}: Pick<SelectionControls, "description" | "onPrevious" | "onNext" | "onClear">) {
  return (
    <div className="selection__steps" role="group" aria-label="Nota elegida">
      {/* En una partitura estrecha quedan las flechas; el nombre sigue para el lector. */}
      <button type="button" className="selection__button" onClick={onPrevious}>
        <PixelIcon name="arrow-left" />
        <span className="selection__word">Anterior</span>
      </button>
      <button type="button" className="selection__button" onClick={onNext}>
        <span className="selection__word">Siguiente</span>
        <PixelIcon name="arrow-right" />
      </button>
      <button
        type="button"
        className="selection__button"
        aria-disabled={description === null}
        onClick={() => {
          if (description) onClear();
        }}
      >
        Quitar
      </button>
    </div>
  );
}

/** Leyenda de las teclas de la selección, que también describe la partitura. */
export function SelectionKeys({ keysId, hidden }: { keysId: string; hidden: boolean }) {
  return (
    <p className="selection__keys" id={keysId} hidden={hidden}>
      <span>
        <KeyCap icon="arrow-left">flecha izquierda</KeyCap>
        <KeyCap icon="arrow-right">flecha derecha</KeyCap> nota
      </span>
      <span>
        <KeyCap icon="arrow-up">flecha arriba</KeyCap>
        <KeyCap icon="arrow-down">flecha abajo</KeyCap> voz y pentagrama
      </span>
      <span>
        <KeyCap>Ctrl</KeyCap> o <KeyCap>Cmd</KeyCap>
        <KeyCap icon="arrow-left">flecha izquierda</KeyCap>
        <KeyCap icon="arrow-right">flecha derecha</KeyCap> compás
      </span>
      <span>
        <KeyCap>Re Pág</KeyCap>
        <KeyCap>Av Pág</KeyCap> compás
      </span>
      <span>
        <KeyCap>Inicio</KeyCap>
        <KeyCap>Fin</KeyCap> dentro del compás
      </span>
      <span>
        <KeyCap>Esc</KeyCap> quitar
      </span>
    </p>
  );
}

/** La selección se anuncia cuando se detiene, no a cada paso. */
export function SelectionAnnouncement({ announcement }: { announcement: string }) {
  return (
    <p className="visually-hidden selection__live" role="status">
      {announcement}
    </p>
  );
}

/**
 * Barra de la selección de notas (ADR-0027), sin barra de corrección: qué evento está elegido,
 * cómo moverse y, en una pantalla táctil, botones de 44 px para afinar lo que el dedo no alcanza.
 * La selección se anuncia en una región `aria-live` cuando se detiene, no a cada paso.
 */
export function SelectionBar(controls: SelectionControls) {
  const { status, description } = controls;
  if (!selectionReady(status)) {
    return (
      <div className="selection" data-status={status.kind === "ready" ? "empty" : status.kind}>
        <SelectionReadout status={status} description={description} />
      </div>
    );
  }
  return (
    <div className="selection" data-status="ready">
      <SelectionReadout status={status} description={description} />
      <SelectionSteps {...controls} />
      <SelectionKeys keysId={controls.keysId} hidden={false} />
      <SelectionAnnouncement announcement={controls.announcement} />
    </div>
  );
}
