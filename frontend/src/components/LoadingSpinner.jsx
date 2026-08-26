import React, { useState, useEffect } from 'react';
import { Cpu, Zap, Music, FileText, Loader2, CheckCircle2 } from 'lucide-react';

export default function LoadingSpinner({ usedGpu, deviceName, statusMessage }) {
  const [seconds, setSeconds] = useState(0);
  const [currentStep, setCurrentStep] = useState(1);

  useEffect(() => {
    const timer = setInterval(() => {
      setSeconds(prev => prev + 1);
    }, 1000);

    // Simular avance de pasos visuales mientras se procesa
    const stepTimer1 = setTimeout(() => setCurrentStep(2), 2000);
    const stepTimer2 = setTimeout(() => setCurrentStep(3), 8000);

    return () => {
      clearInterval(timer);
      clearTimeout(stepTimer1);
      clearTimeout(stepTimer2);
    };
  }, []);

  const steps = [
    { id: 1, label: 'Cargando y preprocesando imagen', icon: FileText },
    { 
      id: 2, 
      label: `Procesando con HOMR Deep Learning (${usedGpu ? `GPU: ${deviceName || 'NVIDIA'}` : 'CPU Fallback'})`, 
      icon: usedGpu ? Zap : Cpu 
    },
    { id: 3, label: 'Generando MusicXML y convirtiendo a MIDI con music21', icon: Music },
  ];

  return (
    <div className="flex flex-col items-center justify-center p-8 bg-slate-900/90 backdrop-blur border border-slate-800 rounded-2xl shadow-2xl max-w-xl mx-auto my-6 animate-fade-in">
      {/* Spinner central */}
      <div className="relative mb-6">
        <div className="w-20 h-20 rounded-full border-4 border-cyan-500/20 border-t-cyan-400 animate-spin flex items-center justify-center"></div>
        <div className="absolute inset-0 flex items-center justify-center">
          {usedGpu ? (
            <Zap className="w-8 h-8 text-emerald-400 animate-pulse" />
          ) : (
            <Cpu className="w-8 h-8 text-cyan-400 animate-pulse" />
          )}
        </div>
      </div>

      <h3 className="text-xl font-bold text-slate-100 mb-1">Transcribiendo Partitura con HOMR</h3>
      <p className="text-sm text-slate-400 mb-4 text-center">
        Tiempo transcurrido: <span className="font-mono text-cyan-400 font-bold">{seconds}s</span>
      </p>

      {/* Badge de hardware */}
      <div className="mb-6">
        {usedGpu ? (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
            <Zap className="w-3.5 h-3.5" /> Aceleración GPU Activa ({deviceName || 'CUDA 12.1'})
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/40">
            <Cpu className="w-3.5 h-3.5" /> Modo CPU ({deviceName || 'Procesador Local'})
          </span>
        )}
      </div>

      {/* Lista de pasos en tiempo real */}
      <div className="w-full space-y-3 bg-slate-950/60 p-4 rounded-xl border border-slate-800/80">
        {steps.map((step) => {
          const StepIcon = step.icon;
          const isDone = currentStep > step.id;
          const isCurrent = currentStep === step.id;

          return (
            <div 
              key={step.id} 
              className={`flex items-center gap-3 text-sm transition-all duration-300 ${
                isCurrent 
                  ? 'text-cyan-300 font-medium translate-x-1' 
                  : isDone 
                    ? 'text-emerald-400' 
                    : 'text-slate-500 opacity-60'
              }`}
            >
              <div className="flex-shrink-0">
                {isDone ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                ) : isCurrent ? (
                  <Loader2 className="w-4 h-4 text-cyan-400 animate-spin" />
                ) : (
                  <StepIcon className="w-4 h-4 text-slate-500" />
                )}
              </div>
              <span className="truncate">{step.label}</span>
            </div>
          );
        })}
      </div>

      {statusMessage && (
        <p className="mt-4 text-xs font-mono text-slate-400 text-center max-w-md bg-slate-950 px-3 py-1.5 rounded border border-slate-800">
          {statusMessage}
        </p>
      )}
    </div>
  );
}
