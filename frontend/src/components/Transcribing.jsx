import React, { useState, useEffect } from 'react';
import { Rule } from './Notation';

/**
 * Estado de transcripcion en curso.
 *
 * Deliberadamente indeterminado: el backend no emite progreso parcial, asi que
 * no se finge. Lo unico que se afirma es lo unico que se sabe con certeza -que
 * sigue trabajando y cuanto lleva-, con una cabeza de nota recorriendo el
 * pentagrama como indicador de actividad.
 */
export default function Transcribing() {
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="animate-fade-in">
      <Rule />

      <div className="relative min-h-[240px] flex flex-col items-center justify-center staff-lines">
        {/* Cabeza de nota recorriendo el pentagrama */}
        <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 h-3 pointer-events-none">
          <span
            className="absolute top-0 w-[11px] h-2 rounded-[50%] bg-brass animate-staff-travel"
            style={{ transform: 'rotate(-18deg)' }}
            aria-hidden="true"
          />
        </div>

        <p className="font-display text-xl text-bone relative">Transcribiendo</p>
        <p className="label mt-3 relative" aria-live="polite">
          {seconds}s
        </p>
      </div>

      <Rule />
    </div>
  );
}
