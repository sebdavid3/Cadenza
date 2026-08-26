import React, { useEffect, useRef, useState } from 'react';
import { OpenSheetMusicDisplay } from 'opensheetmusicdisplay';
import { ZoomIn, ZoomOut, RotateCcw, Download, Eye, FileCode2, Check } from 'lucide-react';

export default function ScoreViewer({ musicxml, filename = 'partitura' }) {
  const containerRef = useRef(null);
  const osmdRef = useRef(null);
  const [zoom, setZoom] = useState(1.0);
  const [isRendered, setIsRendered] = useState(false);
  const [renderError, setRenderError] = useState(null);
  const [copied, setCopied] = useState(false);
  const [showRawXml, setShowRawXml] = useState(false);

  useEffect(() => {
    if (!containerRef.current || !musicxml) return;

    // Limpiar contenedor previo
    containerRef.current.innerHTML = '';
    setIsRendered(false);
    setRenderError(null);

    try {
      const osmd = new OpenSheetMusicDisplay(containerRef.current, {
        autoResize: true,
        drawTitle: true,
        drawSubtitle: true,
        drawComposer: true,
        drawCredits: true,
        drawingParameters: 'compact',
        backend: 'svg',
        renderSingleHorizontalPage: false,
      });

      osmdRef.current = osmd;

      osmd
        .load(musicxml)
        .then(() => {
          osmd.zoom = zoom;
          osmd.render();
          setIsRendered(true);
        })
        .catch((err) => {
          console.error('Error al renderizar MusicXML con OSMD:', err);
          setRenderError('No se pudo visualizar la partitura. El archivo XML podría tener sintaxis incompleta.');
        });
    } catch (err) {
      console.error('Error instanciando OpenSheetMusicDisplay:', err);
      setRenderError('Error inicializando el renderizador de partituras.');
    }

    return () => {
      if (containerRef.current) {
        containerRef.current.innerHTML = '';
      }
      osmdRef.current = null;
    };
  }, [musicxml]);

  // Manejador de cambio de Zoom
  const handleZoomChange = (delta) => {
    const newZoom = Math.min(Math.max(zoom + delta, 0.5), 2.5);
    setZoom(newZoom);
    if (osmdRef.current && isRendered) {
      osmdRef.current.zoom = newZoom;
      osmdRef.current.render();
    }
  };

  const handleResetZoom = () => {
    setZoom(1.0);
    if (osmdRef.current && isRendered) {
      osmdRef.current.zoom = 1.0;
      osmdRef.current.render();
    }
  };

  const handleDownloadXml = () => {
    const blob = new Blob([musicxml], { type: 'application/vnd.recordare.musicxml+xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${filename || 'transcripcion'}.musicxml`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleCopyXml = () => {
    navigator.clipboard.writeText(musicxml);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="w-full bg-slate-900 border border-slate-800 rounded-3xl overflow-hidden shadow-2xl">
      {/* Barra de herramientas superior */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 bg-slate-950/80 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-emerald-400"></div>
          <h3 className="font-bold text-slate-100 text-sm md:text-base flex items-center gap-2">
            Partitura Digitalizada (OpenSheetMusicDisplay)
          </h3>
        </div>

        <div className="flex items-center gap-2">
          {/* Controles de Zoom */}
          <div className="flex items-center bg-slate-900 rounded-xl border border-slate-800 p-1">
            <button
              onClick={() => handleZoomChange(-0.15)}
              className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
              title="Reducir Zoom"
            >
              <ZoomOut className="w-4 h-4" />
            </button>
            <span className="px-2 text-xs font-mono text-slate-300 min-w-[3.5rem] text-center">
              {Math.round(zoom * 100)}%
            </span>
            <button
              onClick={() => handleZoomChange(0.15)}
              className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
              title="Aumentar Zoom"
            >
              <ZoomIn className="w-4 h-4" />
            </button>
            <button
              onClick={handleResetZoom}
              className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors border-l border-slate-800 ml-1"
              title="Restablecer Zoom (100%)"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Toggle Raw XML */}
          <button
            onClick={() => setShowRawXml(!showRawXml)}
            className={`px-3 py-1.5 rounded-xl border text-xs font-medium flex items-center gap-1.5 transition-colors ${
              showRawXml
                ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40'
                : 'bg-slate-900 hover:bg-slate-800 text-slate-300 border-slate-800'
            }`}
          >
            <FileCode2 className="w-3.5 h-3.5" />
            {showRawXml ? 'Ver Partitura' : 'Ver Código XML'}
          </button>

          {/* Descargar MusicXML */}
          <button
            onClick={handleDownloadXml}
            className="px-3 py-1.5 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white font-medium text-xs flex items-center gap-1.5 shadow-md shadow-cyan-600/20 transition-all hover:shadow-cyan-500/40"
            title="Descargar archivo MusicXML"
          >
            <Download className="w-3.5 h-3.5" />
            Descargar .musicxml
          </button>
        </div>
      </div>

      {/* Contenedor del lienzo de la partitura o visor XML */}
      {renderError && (
        <div className="p-6 m-4 rounded-2xl bg-rose-950/40 border border-rose-800/60 text-rose-300 text-sm">
          <p className="font-semibold mb-1">Aviso al renderizar partitura:</p>
          <p>{renderError}</p>
          <button
            onClick={() => setShowRawXml(true)}
            className="mt-3 text-xs underline font-semibold text-rose-200 hover:text-white"
          >
            Ver contenido XML sin procesar
          </button>
        </div>
      )}

      {showRawXml ? (
        <div className="relative p-6 bg-slate-950 font-mono text-xs text-slate-300 max-h-[600px] overflow-auto">
          <div className="absolute top-4 right-6">
            <button
              onClick={handleCopyXml}
              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs flex items-center gap-1.5 transition-colors shadow-lg"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <FileCode2 className="w-3.5 h-3.5" />}
              {copied ? 'Copiado!' : 'Copiar XML'}
            </button>
          </div>
          <pre className="whitespace-pre-wrap">{musicxml}</pre>
        </div>
      ) : (
        <div className="p-4 md:p-8 bg-white min-h-[420px] max-h-[750px] overflow-auto flex items-center justify-center">
          <div
            ref={containerRef}
            className="w-full flex justify-center text-slate-900 overflow-x-auto"
          />
        </div>
      )}
    </div>
  );
}
