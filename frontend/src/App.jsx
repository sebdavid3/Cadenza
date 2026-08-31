import React, { useState, useEffect, useCallback } from 'react';
import DropZone from './components/DropZone';
import ScoreViewer from './components/ScoreViewer';
import AudioPlayer from './components/AudioPlayer';
import Transcribing from './components/Transcribing';
import LogConsole from './components/LogConsole';
import { Wordmark, Rule, DoubleRule, FinalBarline } from './components/Notation';

const API_BASE = import.meta.env.VITE_API_URL || '';

export default function App() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  // null mientras no se ha comprobado; true/false una vez conocido
  const [online, setOnline] = useState(null);

  const checkConnection = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/health`);
      setOnline(res.ok);
    } catch {
      setOnline(false);
    }
  }, []);

  useEffect(() => {
    checkConnection();
    // Sondeo espaciado y suspendido con la pestaña oculta: la conexion solo
    // interesa mientras alguien esta mirando.
    const interval = setInterval(() => {
      if (!document.hidden) checkConnection();
    }, 30000);
    const onVisible = () => { if (!document.hidden) checkConnection(); };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [checkConnection]);

  const handleTranscribe = async () => {
    if (!selectedFile) return;

    setIsProcessing(true);
    setError(null);

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      const res = await fetch(`${API_BASE}/transcribe`, { method: 'POST', body: formData });

      if (!res.ok) {
        // El detalle del backend es diagnostico, no informacion para quien usa
        // la aplicacion: queda en consola y en pantalla se explica que hacer.
        let detail = `HTTP ${res.status}`;
        try {
          const data = await res.json();
          if (data?.detail) detail = data.detail;
        } catch { /* respuesta sin cuerpo JSON */ }
        console.error('Fallo de transcripción:', detail);
        throw new Error('transcription-failed');
      }

      setResult(await res.json());
      setOnline(true);
    } catch (err) {
      if (err.message === 'transcription-failed') {
        setError('No se pudo leer esta partitura. Prueba con una imagen más nítida, bien encuadrada y sin sombras.');
      } else {
        console.error('Fallo de red:', err);
        setError('No hay conexión con el servidor.');
        setOnline(false);
      }
    } finally {
      setIsProcessing(false);
    }
  };

  const handleReset = () => {
    setSelectedFile(null);
    setResult(null);
    setError(null);
  };

  const baseName = selectedFile?.name?.replace(/\.[^/.]+$/, '') || 'partitura';
  const showIntake = !result && !isProcessing;

  return (
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-30 bg-ink/95 backdrop-blur-sm">
        <div className="max-w-4xl mx-auto px-6 h-16 flex items-center">
          <Wordmark />
        </div>
        <Rule />
      </header>

      {online === false && (
        <div className="bg-ink-900">
          <p className="max-w-4xl mx-auto px-6 py-2.5 text-xs font-display italic text-bone-dim">
            Sin conexión con el servidor. Las transcripciones no estarán disponibles hasta que se restablezca.
          </p>
          <Rule />
        </div>
      )}

      <main className="flex-1 w-full max-w-4xl mx-auto px-6 py-14 md:py-20">
        {showIntake && (
          <div className="animate-fade-in">
            <h1 className="font-display text-[26px] md:text-[32px] leading-snug text-bone mb-2">
              Convierte una partitura en sonido
            </h1>
            <p className="text-sm text-bone-dim max-w-md mb-10">
              Sube la foto o el escaneo de una partitura y obtén la versión digital,
              lista para verse y escucharse.
            </p>

            <DropZone
              onFileSelect={setSelectedFile}
              onTranscribe={handleTranscribe}
              selectedFile={selectedFile}
              disabled={online === false}
            />
          </div>
        )}

        {isProcessing && <Transcribing />}

        {error && !isProcessing && (
          <div className="mt-10 animate-fade-in">
            <Rule />
            <div className="py-5">
              <p className="text-sm font-display italic text-bone mb-4">{error}</p>
              <div className="flex flex-wrap gap-6">
                <button
                  onClick={handleTranscribe}
                  disabled={!selectedFile}
                  className="text-sm text-bone hover:text-bone-dim transition-colors disabled:opacity-40 disabled:hover:text-bone"
                >
                  Reintentar
                </button>
                <button
                  onClick={handleReset}
                  className="text-sm text-bone-dim hover:text-bone transition-colors"
                >
                  Elegir otra imagen
                </button>
              </div>
            </div>
            <Rule />
          </div>
        )}

        {result && (
          <div className="animate-fade-in">
            <div className="flex flex-wrap items-baseline justify-between gap-4 mb-1">
              <h1 className="font-display text-[26px] md:text-[32px] leading-snug text-bone">
                {baseName}
              </h1>
              <button
                onClick={handleReset}
                className="text-sm text-bone hover:text-bone-dim transition-colors"
              >
                Nueva partitura
              </button>
            </div>
            <p className="text-sm text-bone-dim mb-10">Transcripción lista.</p>

            {result.midi_base64 && (
              <AudioPlayer midiBase64={result.midi_base64} filename={baseName} />
            )}

            {result.musicxml && (
              <ScoreViewer musicxml={result.musicxml} filename={baseName} />
            )}
          </div>
        )}
        <LogConsole />
      </main>

      <footer className="mt-auto">
        <DoubleRule />
        <div className="max-w-4xl mx-auto px-6 py-6 flex items-center justify-between">
          <span className="text-xs text-bone-faint">
            Cadenza — Digitalización asistida de partituras
          </span>
          <FinalBarline />
        </div>
      </footer>
    </div>
  );
}
