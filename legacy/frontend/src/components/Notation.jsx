import React from 'react';

/**
 * Primitivas de notacion reutilizables.
 *
 * La idea rectora: los elementos musicales aqui son estructurales, no decorativos.
 * Un pentagrama delimita una zona de trabajo, una barra final cierra una seccion,
 * una indicacion metronomica reemplaza un multiplicador abstracto. Nada de iconos
 * musicales puestos como adorno.
 */

/** Barra final: linea fina seguida de linea gruesa. Cierra una seccion. */
export function FinalBarline({ className = '' }) {
  return (
    <span
      aria-hidden="true"
      className={`inline-flex items-stretch gap-[3px] h-3 ${className}`}
    >
      <span className="w-px bg-[var(--rule-strong)]" />
      <span className="w-[3px] bg-[var(--rule-strong)]" />
    </span>
  );
}

/** Doble barra: separa secciones sin encerrarlas en una caja. */
export function DoubleRule({ className = '' }) {
  return <div aria-hidden="true" className={`rule-double w-full ${className}`} />;
}

/** Regla simple. */
export function Rule({ className = '' }) {
  return <div aria-hidden="true" className={`rule w-full ${className}`} />;
}

/**
 * Pentagrama. Envuelve contenido sobre cinco lineas reales.
 * `lines` en false lo deja como caja vacia (util para estados de arrastre).
 */
export function Staff({ children, className = '', lines = true }) {
  return (
    <div className={`relative ${lines ? 'staff-lines' : ''} ${className}`}>
      {children}
    </div>
  );
}

/**
 * Cabeza de nota. Elipse inclinada, como en la notacion real.
 * Se usa como pulsador de reproduccion y como marcador de progreso.
 */
export function NoteHead({ className = '', filled = true, size = 11 }) {
  return (
    <span
      aria-hidden="true"
      className={`inline-block rounded-[50%] ${className}`}
      style={{
        width: size,
        height: size * 0.72,
        transform: 'rotate(-18deg)',
        background: filled ? 'currentColor' : 'transparent',
        boxShadow: filled ? 'none' : 'inset 0 0 0 1.5px currentColor',
      }}
    />
  );
}

/** Marca de la aplicacion: solo tipografia. Sin glifos, iconos ni degradados. */
export function Wordmark() {
  return (
    <span className="font-display text-[19px] font-medium tracking-tight text-bone select-none">
      Cadenza
    </span>
  );
}
