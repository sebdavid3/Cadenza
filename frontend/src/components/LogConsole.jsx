import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Rule } from './Notation';

const API_BASE = import.meta.env.VITE_API_URL || '';
const MAX_LINES = 400;

/**
 * Registro en vivo del servidor.
 *
 * El motor de reconocimiento escribe su progreso real mientras trabaja; el
 * backend lo retransmite por Server-Sent Events y aqui se muestra tal cual.
 * La conexion solo se abre cuando el panel esta desplegado: mantener abierta
 * una corriente de eventos que nadie mira no tiene sentido.
 */
export default function LogConsole() {
  const [open, setOpen] = useState(false);
  const [lines, setLines] = useState([]);
  const [connected, setConnected] = useState(false);
  const [follow, setFollow] = useState(true);

  const viewportRef = useRef(null);
  const sourceRef = useRef(null);
  const followRef = useRef(follow);

  useEffect(() => { followRef.current = follow; }, [follow]);

  useEffect(() => {
    if (!open) {
      sourceRef.current?.close();
      sourceRef.current = null;
      setConnected(false);
      return undefined;
    }

    const source = new EventSource(`${API_BASE}/logs`);
    sourceRef.current = source;

    source.onopen = () => setConnected(true);

    source.onmessage = (event) => {
      let text;
      try {
        text = JSON.parse(event.data);
      } catch {
        text = event.data;
      }
      // Se descartan las lineas mas antiguas: una transcripcion larga emite
      // miles y conservarlas todas degrada el renderizado
      setLines((prev) => {
        const next = prev.length >= MAX_LINES
          ? [...prev.slice(prev.length - MAX_LINES + 1), text]
          : [...prev, text];
        return next;
      });
    };

    // EventSource reconecta solo; aqui unicamente se refleja el estado
    source.onerror = () => setConnected(false);

    return () => {
      source.close();
      sourceRef.current = null;
    };
  }, [open]);

  // Desplazamiento automatico, salvo que se haya subido a leer algo
  useEffect(() => {
    if (!followRef.current) return;
    const el = viewportRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines]);

  const handleScroll = useCallback(() => {
    const el = viewportRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
    setFollow(atBottom);
  }, []);

  return (
    <section className="mt-16">
      <Rule />

      <div className="flex flex-wrap items-center justify-between gap-4 py-4">
        <button
          onClick={() => setOpen(!open)}
          className="text-sm text-bone hover:text-bone-dim transition-colors"
          aria-expanded={open}
        >
          {open ? 'Ocultar registro' : 'Ver registro del servidor'}
        </button>

        {open && (
          <div className="flex items-center gap-5">
            <span className="label">
              {connected ? 'En vivo' : 'Sin conexión'}
            </span>
            {lines.length > 0 && (
              <button
                onClick={() => setLines([])}
                className="text-xs text-bone-dim hover:text-bone transition-colors"
              >
                Limpiar
              </button>
            )}
          </div>
        )}
      </div>

      {open && (
        <div className="animate-fade-in">
          <div
            ref={viewportRef}
            onScroll={handleScroll}
            className="h-72 overflow-auto bg-ink-900 px-4 py-3 font-mono text-[11.5px] leading-relaxed"
          >
            {lines.length === 0 ? (
              <p className="text-bone-faint">
                Sin actividad todavía. Las líneas aparecerán aquí mientras se transcribe.
              </p>
            ) : (
              lines.map((line, i) => (
                <div key={i} className="text-bone-dim whitespace-pre-wrap break-words">
                  {line}
                </div>
              ))
            )}
          </div>

          {!follow && (
            <button
              onClick={() => {
                setFollow(true);
                const el = viewportRef.current;
                if (el) el.scrollTop = el.scrollHeight;
              }}
              className="mt-3 text-xs text-bone hover:text-bone-dim transition-colors"
            >
              Volver al final
            </button>
          )}
        </div>
      )}
    </section>
  );
}
