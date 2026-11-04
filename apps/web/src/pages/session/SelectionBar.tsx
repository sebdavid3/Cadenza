import { PixelIcon, type PixelIconName } from "../../components/PixelIcon";

/** Qué se puede hacer con la selección de notas en la partitura dibujada. */
export type SelectionStatus =
  | { kind: "pending" }
  | { kind: "ready"; empty: boolean }
  /** No se ofrece: OSMD dibujó otros compases (sin recuento) o no todos los eventos cuadran. */
  | { kind: "unavailable"; total?: number; unmatched?: number };

interface SelectionBarProps {
  status: SelectionStatus;
  /** Evento elegido: dónde está y qué es. */
  description: { place: string; what: string } | null;
  announcement: string;
  /** Identificador de la leyenda de teclas, que describe la partitura. */
  keysId: string;
  onPrevious: () => void;
  onNext: () => void;
  onClear: () => void;
}

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
 * Barra de la selección de notas (ADR-0027): qué evento está elegido, cómo moverse y, en una
 * pantalla táctil, botones de 44 px para afinar lo que el dedo no alcanza. La selección se
 * anuncia en una región `aria-live` cuando se detiene, no a cada paso.
 */
export function SelectionBar({
  status,
  description,
  announcement,
  keysId,
  onPrevious,
  onNext,
  onClear,
}: SelectionBarProps) {
  if (status.kind === "unavailable") {
    return (
      <div className="selection" data-status="unavailable">
        <p className="selection__note">{unavailableText(status.total, status.unmatched)}</p>
      </div>
    );
  }
  if (status.kind === "pending") {
    return (
      <div className="selection" data-status="pending">
        <p className="selection__note">Preparando la selección de notas…</p>
      </div>
    );
  }
  if (status.empty) {
    return (
      <div className="selection" data-status="empty">
        <p className="selection__note">La partitura no tiene notas ni silencios que elegir.</p>
      </div>
    );
  }

  return (
    <div className="selection" data-status="ready" data-selected={description !== null}>
      <div className="selection__readout">
        {description ? (
          <>
            <p className="label selection__place">{description.place}</p>
            <p className="selection__what">{description.what}</p>
          </>
        ) : (
          <p className="selection__hint">Elige una nota o un silencio: tócalo o usa las flechas.</p>
        )}
      </div>
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
      <p className="selection__keys" id={keysId}>
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
      <p className="visually-hidden" role="status">
        {announcement}
      </p>
    </div>
  );
}
