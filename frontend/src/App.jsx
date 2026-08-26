import React, { useState, useEffect } from 'react';
import { 
  Zap, 
  Cpu, 
  Music, 
  RefreshCw, 
  AlertCircle, 
  CheckCircle, 
  Sparkles, 
  Radio, 
  Layers, 
  Info,
  ExternalLink
} from 'lucide-react';
import DropZone from './components/DropZone';
import ScoreViewer from './components/ScoreViewer';
import AudioPlayer from './components/AudioPlayer';
import LoadingSpinner from './components/LoadingSpinner';

const API_BASE = import.meta.env.VITE_API_URL || '';

export default function App() {
  const [gpuInfo, setGpuInfo] = useState(null);
  const [backendHealthy, setBackendHealthy] = useState(null);
  const [selectedFile, setSelectedFile] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [transcriptionResult, setTranscriptionResult] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);
  const [statusMessage, setStatusMessage] = useState('');
  const [loadingGpuInfo, setLoadingGpuInfo] = useState(false);

  // Consultar estado de GPU y salud del backend
  const fetchGpuInfo = async () => {
    setLoadingGpuInfo(true);
    try {
      const res = await fetch(`${API_BASE}/gpu-info`);
      if (res.ok) {
        const data = await res.json();
        setGpuInfo(data);
        setBackendHealthy(true);
      } else {
        setBackendHealthy(false);
      }
    } catch (err) {
      console.warn('No se pudo conectar con el backend:', err);
      setBackendHealthy(false);
    } finally {
      setLoadingGpuInfo(false);
    }
  };

  useEffect(() => {
    fetchGpuInfo();
    const interval = setInterval(fetchGpuInfo, 15000); // Polling cada 15s
    return () => clearInterval(interval);
  }, []);

  const handleTranscribe = async () => {
    if (!selectedFile) return;

    setIsProcessing(true);
    setErrorMessage(null);
    setStatusMessage('Enviando imagen al motor HOMR...');

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      const res = await fetch(`${API_BASE}/transcribe`, {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        let errDetail = 'Error en el servidor al transcribir';
        try {
          const errData = await res.json();
          errDetail = errData.detail || errDetail;
        } catch {
          errDetail = `HTTP ${res.status}: ${res.statusText}`;
        }
        throw new Error(errDetail);
      }

      const data = await res.json();
      setTranscriptionResult(data);
      setStatusMessage('Transcripción completada.');
    } catch (err) {
      console.error('Error en transcripción:', err);
      setErrorMessage(err.message || 'Error de conexión o fallo de ejecución en HOMR.');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleReset = () => {
    setSelectedFile(null);
    setTranscriptionResult(null);
    setErrorMessage(null);
    setStatusMessage('');
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Barra de Navegación / Header */}
      <header className="sticky top-0 z-30 bg-slate-900/80 backdrop-blur border-b border-slate-800 px-6 py-4">
        <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center shadow-lg shadow-cyan-500/20">
              <Music className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="font-extrabold text-lg text-white tracking-tight">Cadenza OMR</h1>
                <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">
                  HOMR Local
                </span>
              </div>
              <p className="text-xs text-slate-400">Digitalización de partituras con aceleración GPU</p>
            </div>
          </div>

          {/* Indicador de Estado del Backend y GPU en Tiempo Real */}
          <div className="flex items-center gap-3">
            {backendHealthy === false ? (
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-rose-950/60 border border-rose-800/80 text-rose-300 text-xs">
                <AlertCircle className="w-4 h-4 text-rose-400 animate-pulse" />
                <span>Backend Desconectado ({API_BASE})</span>
              </div>
            ) : gpuInfo ? (
              <div className="flex items-center gap-2 bg-slate-950/80 p-1.5 rounded-2xl border border-slate-800">
                {gpuInfo.cuda_available ? (
                  <div 
                    className="flex items-center gap-2 px-3 py-1 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs font-semibold"
                    title={`GPU: ${gpuInfo.device_name} | CUDA ${gpuInfo.cuda_version} | VRAM: ${gpuInfo.memory_total_gb} GB`}
                  >
                    <Zap className="w-3.5 h-3.5 text-emerald-400" />
                    <span>GPU: {gpuInfo.device_name}</span>
                    <span className="text-[10px] font-mono opacity-80">({gpuInfo.memory_total_gb}GB VRAM)</span>
                  </div>
                ) : (
                  <div 
                    className="flex items-center gap-2 px-3 py-1 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs font-semibold"
                    title="Ejecutando en procesador CPU fallback sin acelerador NVIDIA CUDA"
                  >
                    <Cpu className="w-3.5 h-3.5 text-amber-400" />
                    <span>Modo CPU Fallback</span>
                  </div>
                )}

                <button
                  onClick={fetchGpuInfo}
                  disabled={loadingGpuInfo}
                  className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
                  title="Actualizar estado del servidor"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${loadingGpuInfo ? 'animate-spin text-cyan-400' : ''}`} />
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-800 text-slate-400 text-xs">
                <RefreshCw className="w-3.5 h-3.5 animate-spin text-cyan-400" />
                <span>Detectando hardware...</span>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Contenido Principal */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 md:px-6 py-8 flex flex-col gap-8">
        {/* Banner informativo de arquitectura si no hay archivo procesado */}
        {!transcriptionResult && !isProcessing && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-4 flex items-start gap-3.5">
              <div className="p-2.5 rounded-xl bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                <Zap className="w-5 h-5" />
              </div>
              <div>
                <h4 className="font-bold text-sm text-slate-200">100% Local & GPU Passthrough</h4>
                <p className="text-xs text-slate-400 mt-0.5">
                  Procesamiento local con PyTorch CUDA 12.1 para máxima velocidad y privacidad sin enviar datos a la nube.
                </p>
              </div>
            </div>

            <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-4 flex items-start gap-3.5">
              <div className="p-2.5 rounded-xl bg-blue-500/10 text-blue-400 border border-blue-500/20">
                <Layers className="w-5 h-5" />
              </div>
              <div>
                <h4 className="font-bold text-sm text-slate-200">OMR con Deep Learning</h4>
                <p className="text-xs text-slate-400 mt-0.5">
                  Motor HOMR con redes neuronales convolucionales para reconocimiento de pentagramas, notas y figuras.
                </p>
              </div>
            </div>

            <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-4 flex items-start gap-3.5">
              <div className="p-2.5 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/20">
                <Music className="w-5 h-5" />
              </div>
              <div>
                <h4 className="font-bold text-sm text-slate-200">MusicXML & Síntesis MIDI</h4>
                <p className="text-xs text-slate-400 mt-0.5">
                  Conversión con music21 y renderizado interactivo en tiempo real con OpenSheetMusicDisplay y Tone.js.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Zona de Carga de Imagen */}
        {!transcriptionResult && !isProcessing && (
          <DropZone
            onFileSelect={setSelectedFile}
            onTranscribe={handleTranscribe}
            selectedFile={selectedFile}
            isProcessing={isProcessing}
            gpuInfo={gpuInfo}
          />
        )}

        {/* Spinner animado durante el procesamiento */}
        {isProcessing && (
          <LoadingSpinner
            usedGpu={gpuInfo?.cuda_available}
            deviceName={gpuInfo?.device_name}
            statusMessage={statusMessage}
          />
        )}

        {/* Mensaje de Error si ocurre */}
        {errorMessage && (
          <div className="max-w-2xl mx-auto w-full bg-rose-950/50 border border-rose-800 rounded-2xl p-6 shadow-xl animate-fade-in">
            <div className="flex items-start gap-4">
              <div className="p-2 rounded-xl bg-rose-900/60 text-rose-400 border border-rose-700">
                <AlertCircle className="w-6 h-6" />
              </div>
              <div className="flex-1">
                <h4 className="font-bold text-rose-200 mb-1">Error al procesar la partitura</h4>
                <p className="text-xs text-rose-300 font-mono bg-rose-950/80 p-3 rounded-lg border border-rose-900 mb-4 whitespace-pre-wrap">
                  {errorMessage}
                </p>
                <div className="flex gap-3">
                  <button
                    onClick={handleTranscribe}
                    className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold transition-colors"
                  >
                    Reintentar
                  </button>
                  <button
                    onClick={handleReset}
                    className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition-colors"
                  >
                    Elegir otra imagen
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Resultados de Transcripción */}
        {transcriptionResult && (
          <div className="flex flex-col gap-6 animate-fade-in">
            {/* Banner de éxito */}
            <div className="flex flex-wrap items-center justify-between gap-4 p-4 bg-slate-900 border border-slate-800 rounded-2xl shadow-lg">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-xl bg-emerald-500/20 text-emerald-400 flex items-center justify-center border border-emerald-500/30">
                  <CheckCircle className="w-4 h-4" />
                </div>
                <div>
                  <h4 className="font-bold text-sm text-slate-100">
                    Transcripción completada con éxito
                  </h4>
                  <p className="text-xs text-slate-400">
                    Procesado en <span className="font-mono text-cyan-400 font-semibold">{transcriptionResult.processing_time_sec}s</span> usando{' '}
                    <span className="text-slate-200 font-medium">{transcriptionResult.device_name}</span> ({transcriptionResult.used_gpu ? 'GPU' : 'CPU'})
                  </p>
                </div>
              </div>

              <button
                onClick={handleReset}
                className="px-4 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-bold transition-all shadow-md shadow-cyan-600/20"
              >
                Transcribir otra partitura
              </button>
            </div>

            {/* Reproductor de Audio Tone.js */}
            {transcriptionResult.midi_base64 && (
              <AudioPlayer
                midiBase64={transcriptionResult.midi_base64}
                filename={selectedFile?.name?.replace(/\.[^/.]+$/, '') || 'transcripcion'}
              />
            )}

            {/* Visor de Partituras OSMD */}
            {transcriptionResult.musicxml && (
              <ScoreViewer
                musicxml={transcriptionResult.musicxml}
                filename={selectedFile?.name?.replace(/\.[^/.]+$/, '') || 'transcripcion'}
              />
            )}
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800/80 bg-slate-950 py-4 px-6 text-center text-xs text-slate-400">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-2">
          <span>Cadenza — Digitalización Asistida de Partituras</span>
          <span className="font-mono text-[11px]">HOMR • PyTorch CUDA 12.1 • music21 • OSMD • Tone.js</span>
        </div>
      </footer>
    </div>
  );
}
