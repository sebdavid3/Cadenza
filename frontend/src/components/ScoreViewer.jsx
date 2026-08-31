import React, { useEffect, useRef, useState, useCallback } from 'react';
import { OpenSheetMusicDisplay } from 'opensheetmusicdisplay';
import { Rule } from './Notation';

const ZOOM_MIN = 0.5;
const ZOOM_MAX = 2.5;
const ZOOM_STEP = 0.15;

export default function ScoreViewer({ musicxml, filename = 'partitura' }) {
  const containerRef = useRef(null);
  const osmdRef = useRef(null);
  const zoomRef = useRef(1.0);
  const [zoom, setZoom] = useState(1.0);
  const [renderError, setRenderError] = useState(null);

  useEffect(() => {
    const host = containerRef.current;
    if (!host || !musicxml) return;

    host.innerHTML = '';
    setRenderError(null);
    let cancelled = false;

    const osmd = new OpenSheetMusicDisplay(host, {
      autoResize: true,
      drawTitle: true,
      drawSubtitle: true,
      drawComposer: true,
      drawCredits: false,
      backend: 'svg',
      renderSingleHorizontalPage: false,
    });
    osmdRef.current = osmd;

    osmd
      .load(musicxml)
      .then(() => {
        if (cancelled) return;
        // Se lee del ref para no capturar un zoom obsoleto en el cierre
        osmd.zoom = zoomRef.current;
        osmd.render();
      })
      .catch((err) => {
        if (cancelled) return;
        console.error('Error al renderizar la partitura:', err);
        setRenderError('No se pudo dibujar esta partitura completa.');
      });

    return () => {
      cancelled = true;
      osmdRef.current = null;
      if (host) host.innerHTML = '';
    };
  }, [musicxml]);

  const applyZoom = useCallback((next) => {
    const clamped = Math.min(Math.max(next, ZOOM_MIN), ZOOM_MAX);
    zoomRef.current = clamped;
    setZoom(clamped);
    if (osmdRef.current) {
      osmdRef.current.zoom = clamped;
      osmdRef.current.render();
    }
  }, []);

  const handleDownload = () => {
    const blob = new Blob([musicxml], { type: 'application/vnd.recordare.musicxml+xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${filename}.musicxml`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <section className="mt-14">
      <div className="flex flex-wrap items-baseline justify-between gap-4 mb-3">
        <h2 className="font-display text-lg text-bone">Partitura</h2>

        <div className="flex items-center gap-6">
          <div className="flex items-center gap-3 text-bone-dim">
            <button
              onClick={() => applyZoom(zoom - ZOOM_STEP)}
              disabled={zoom <= ZOOM_MIN}
              className="hover:text-bone transition-colors disabled:opacity-30 disabled:hover:text-bone-dim leading-none"
              aria-label="Reducir"
            >
              &minus;
            </button>
            <button
              onClick={() => applyZoom(1.0)}
              className="label hover:text-bone transition-colors tabular-nums"
              title="Restablecer tamaño"
            >
              {Math.round(zoom * 100)}%
            </button>
            <button
              onClick={() => applyZoom(zoom + ZOOM_STEP)}
              disabled={zoom >= ZOOM_MAX}
              className="hover:text-bone transition-colors disabled:opacity-30 disabled:hover:text-bone-dim leading-none"
              aria-label="Ampliar"
            >
              +
            </button>
          </div>

          <button
            onClick={handleDownload}
            className="text-sm text-bone hover:text-bone-dim transition-colors"
          >
            Descargar MusicXML
          </button>
        </div>
      </div>

      <Rule />

      {renderError && (
        <p className="pt-4 text-sm font-display italic text-bone">{renderError}</p>
      )}

      {/* La hoja: papel sobre la mesa, sin marco ni recuadro */}
      <div className="mt-5 bg-paper px-6 py-10 md:px-10 max-h-[760px] overflow-auto">
        <div ref={containerRef} className="w-full text-black" />
      </div>
    </section>
  );
}
