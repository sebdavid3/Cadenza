import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Link } from "react-router";
import { AccountControls } from "../../components/AccountControls";
import { BrandWordmark } from "../../components/BrandWordmark";
import { PixelIcon } from "../../components/PixelIcon";

/** La vuelta a la lista de sesiones. */
export function BackLink() {
  return (
    <Link className="label session__back" to="/transcripcion">
      <PixelIcon name="arrow-left" />
      Sesiones
    </Link>
  );
}

interface SessionTopBarProps {
  /** El título de la sesión, su resumen y la ayuda, tras la vuelta a las sesiones. */
  children?: ReactNode;
  /** Las acciones de la sesión, antes de la cuenta. */
  actions?: ReactNode;
}

/**
 * Cabecera única de la vista de una sesión (#363): en una franja, la marca, la vuelta a las
 * sesiones y lo que se pase (el título y sus datos); a la derecha, las acciones de la sesión y la
 * cuenta. Sustituye a la de la aplicación para dejar el alto a la partitura.
 */
export function SessionTopBar({ children, actions }: SessionTopBarProps) {
  return (
    <header className="session__head">
      <div className="session__start">
        <Link className="session__brand" to="/" aria-label="Cadenza, página pública">
          <BrandWordmark />
        </Link>
        <BackLink />
        {children}
      </div>
      <div className="session__actions">
        {actions}
        <div className="session__account">
          <AccountControls />
        </div>
      </div>
    </header>
  );
}

interface HeaderPopoverProps {
  /** Nombre accesible del botón; sin él, su contenido. */
  label?: string;
  /** Lo que se ve en el botón. */
  toggle: ReactNode;
  className: string;
  /** Cómo se llama el panel, para el lector de pantalla. */
  panelLabel: string;
  /**
   * Si un clic fuera no lo cierra: mientras se guardan los datos, para que lo que pase al
   * terminar se vea en el panel aunque se siga trabajando en la partitura.
   */
  pinned?: boolean;
  children: ReactNode;
}

/**
 * Un botón que abre un panel bajo él, sobre la vista (#363): «?» con la entradilla y los datos, y
 * «Exportar / Datos» con los datos y las descargas. No es modal: Esc lo cierra y devuelve el foco
 * al botón, y un clic fuera también lo cierra. Lo de dentro sigue montado cerrado, para que un
 * formulario a medias o un MIDI que se prepara no se pierdan.
 */
export function HeaderPopover({
  label,
  toggle,
  className,
  panelLabel,
  pinned = false,
  children,
}: HeaderPopoverProps) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open || pinned) return;
    const onPointerDown = (event: Event) => {
      if (event.target instanceof Node && rootRef.current?.contains(event.target)) return;
      setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
    };
  }, [open, pinned]);

  // Lo de dentro que usa Esc para lo suyo (cerrar el formulario de los datos) la consume antes.
  // Fijado, Esc tampoco lo cierra: lo que pase al terminar se vería en un panel oculto.
  function onKeyDown(event: KeyboardEvent) {
    if (event.key !== "Escape" || !open || pinned || event.defaultPrevented) return;
    event.preventDefault();
    setOpen(false);
    toggleRef.current?.focus();
  }

  return (
    <div
      className={`header-popover ${className}`}
      ref={rootRef}
      onKeyDown={onKeyDown}
      onBlur={(event) => {
        // Con el teclado, el foco que pasa a otro control fuera lo cierra: así no quedan los dos
        // paneles abiertos a la vez. Sin destino (un clic en el texto del panel), no.
        const next = event.relatedTarget;
        if (!open || pinned || !(next instanceof Node)) return;
        if (!rootRef.current?.contains(next)) setOpen(false);
      }}
    >
      <button
        ref={toggleRef}
        type="button"
        className="header-popover__toggle"
        aria-label={label}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => {
          setOpen(!open);
        }}
      >
        {toggle}
      </button>
      <div
        className="header-popover__panel"
        id={panelId}
        role="group"
        aria-label={panelLabel}
        hidden={!open}
      >
        {children}
      </div>
    </div>
  );
}
