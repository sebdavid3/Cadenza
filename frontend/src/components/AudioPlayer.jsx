import React, { useState, useEffect, useRef } from 'react';
import * as Tone from 'tone';
import { Midi } from '@tonejs/midi';
import { Play, Pause, Square, RotateCcw, Volume2, VolumeX, Download, Music2, Gauge, Repeat } from 'lucide-react';

export default function AudioPlayer({ midiBase64, filename = 'partitura' }) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [tempoMultiplier, setTempoMultiplier] = useState(1.0);
  const [volume, setVolume] = useState(80);
  const [isMuted, setIsMuted] = useState(false);
  const [isLooping, setIsLooping] = useState(false);
  const [midiData, setMidiData] = useState(null);
  const [audioReady, setAudioReady] = useState(false);
  const [activeNotesCount, setActiveNotesCount] = useState(0);

  const synthRef = useRef(null);
  const partRef = useRef(null);
  const animFrameRef = useRef(null);
  const isLoopingRef = useRef(isLooping);

  useEffect(() => {
    isLoopingRef.current = isLooping;
  }, [isLooping]);

  // Inicializar sintetizador y decodificar MIDI cuando cambie `midiBase64`
  useEffect(() => {
    if (!midiBase64) return;

    // Reset de estado previo
    Tone.Transport.stop();
    Tone.Transport.cancel();
    if (partRef.current) {
      partRef.current.dispose();
      partRef.current = null;
    }
    setIsPlaying(false);
    setCurrentTime(0);

    try {
      // 1. Decodificar Base64 a ArrayBuffer
      const binaryString = window.atob(midiBase64);
      const len = binaryString.length;
      const bytes = new Uint8Array(len);
      for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      // 2. Parsear MIDI
      const parsedMidi = new Midi(bytes.buffer);
      setMidiData(parsedMidi);
      const totalDuration = parsedMidi.duration || 1;
      setDuration(totalDuration);
      setAudioReady(true);
    } catch (err) {
      console.error('Error parseando o programando MIDI:', err);
    }

    return () => {
      Tone.Transport.stop();
      Tone.Transport.cancel();
      if (partRef.current) {
        partRef.current.dispose();
      }
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
      }
    };
  }, [midiBase64]);

  // Loop de actualización del tiempo de reproducción
  useEffect(() => {
    const updateTime = () => {
      if (Tone.Transport.state === 'started') {
        const current = Tone.Transport.seconds;
        setCurrentTime(current);

        if (duration > 0 && current >= duration) {
          if (isLoopingRef.current) {
            Tone.Transport.seconds = 0;
            Tone.Transport.start();
          } else {
            Tone.Transport.stop();
            Tone.Transport.seconds = 0;
            setIsPlaying(false);
            setCurrentTime(0);
          }
        }
      }
      animFrameRef.current = requestAnimationFrame(updateTime);
    };

    animFrameRef.current = requestAnimationFrame(updateTime);
    return () => {
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
      }
    };
  }, [duration]);

  // Manejo de reproducción / pausa
  const togglePlay = async () => {
    // Requisito Tone.js: Iniciar AudioContext tras interacción del usuario
    if (Tone.context.state !== 'running') {
      await Tone.start();
    }

    // Inicializar sintetizador si aún no existe
    if (!synthRef.current) {
      const polySynth = new Tone.PolySynth(Tone.Synth, {
        oscillator: { type: 'triangle8' },
        envelope: {
          attack: 0.01,
          decay: 0.2,
          sustain: 0.4,
          release: 0.8,
        },
      }).toDestination();

      const limiter = new Tone.Limiter(-2).toDestination();
      polySynth.connect(limiter);
      synthRef.current = polySynth;
    }

    // Programar notas si no se han programado
    if (!partRef.current && midiData) {
      const events = [];
      midiData.tracks.forEach((track) => {
        track.notes.forEach((note) => {
          events.push({
            time: note.time,
            note: note.name,
            duration: note.duration,
            velocity: note.velocity || 0.8,
          });
        });
      });
      events.sort((a, b) => a.time - b.time);

      const part = new Tone.Part((time, value) => {
        if (synthRef.current) {
          synthRef.current.triggerAttackRelease(
            value.note,
            value.duration,
            time,
            value.velocity
          );
        }
      }, events);

      part.start(0);
      partRef.current = part;
    }

    if (isPlaying) {
      Tone.Transport.pause();
      setIsPlaying(false);
    } else {
      Tone.Transport.bpm.value = 120 * tempoMultiplier;
      Tone.Transport.start();
      setIsPlaying(true);
    }
  };

  const handleStop = () => {
    Tone.Transport.stop();
    Tone.Transport.seconds = 0;
    setIsPlaying(false);
    setCurrentTime(0);
  };

  const handleSeek = (e) => {
    const newTime = parseFloat(e.target.value);
    setCurrentTime(newTime);
    Tone.Transport.seconds = newTime;
  };

  const handleTempoChange = (multiplier) => {
    setTempoMultiplier(multiplier);
    Tone.Transport.bpm.value = 120 * multiplier;
  };

  const handleVolumeChange = (e) => {
    const newVol = parseInt(e.target.value, 10);
    setVolume(newVol);
    if (!isMuted) {
      // Mapear 0-100 a dB (-40dB a 0dB)
      const db = newVol === 0 ? -Infinity : Tone.gainToDb(newVol / 100);
      Tone.getDestination().volume.value = db;
    }
  };

  const toggleMute = () => {
    if (isMuted) {
      setIsMuted(false);
      const db = volume === 0 ? -Infinity : Tone.gainToDb(volume / 100);
      Tone.getDestination().volume.value = db;
    } else {
      setIsMuted(true);
      Tone.getDestination().volume.value = -Infinity;
    }
  };

  const handleDownloadMidi = () => {
    if (!midiBase64) return;
    const binaryString = window.atob(midiBase64);
    const len = binaryString.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    const blob = new Blob([bytes.buffer], { type: 'audio/midi' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${filename || 'transcripcion'}.mid`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const formatTime = (secs) => {
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  };

  if (!midiBase64) {
    return (
      <div className="p-6 bg-slate-900 border border-slate-800 rounded-3xl text-center text-slate-400 text-sm">
        No hay datos MIDI disponibles para reproducir.
      </div>
    );
  }

  const progressPercent = duration > 0 ? (currentTime / duration) * 100 : 0;

  return (
    <div className="w-full bg-slate-900/90 backdrop-blur border border-slate-800 rounded-3xl p-6 shadow-2xl">
      {/* Cabecera del reproductor */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400 shadow-inner">
            <Music2 className="w-5 h-5" />
          </div>
          <div>
            <h4 className="font-bold text-slate-100 text-sm md:text-base">
              Reproductor de Audio (Tone.js + @tonejs/midi)
            </h4>
            <p className="text-xs text-slate-400">
              Síntesis polifónica sintetizada en tiempo real directamente en el navegador
            </p>
          </div>
        </div>

        <button
          onClick={handleDownloadMidi}
          className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-semibold flex items-center gap-2 transition-all hover:text-white"
          title="Descargar archivo MIDI"
        >
          <Download className="w-3.5 h-3.5 text-cyan-400" />
          Descargar .mid
        </button>
      </div>

      {/* Barra de progreso / Scrubber */}
      <div className="mb-4">
        <div className="flex justify-between text-xs font-mono text-slate-400 mb-1.5">
          <span>{formatTime(currentTime)}</span>
          <span>{formatTime(duration)}</span>
        </div>
        <div className="relative group">
          <input
            type="range"
            min="0"
            max={duration || 1}
            step="0.05"
            value={currentTime}
            onChange={handleSeek}
            className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-cyan-400 hover:h-2.5 transition-all"
          />
          <div
            className="absolute left-0 top-0 h-2 bg-gradient-to-r from-cyan-500 to-blue-500 rounded-lg pointer-events-none transition-all"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </div>

      {/* Controles principales */}
      <div className="flex flex-wrap items-center justify-between gap-4 pt-2 border-t border-slate-800/80">
        {/* Play, Stop, Loop */}
        <div className="flex items-center gap-2">
          <button
            onClick={togglePlay}
            className={`w-12 h-12 rounded-2xl flex items-center justify-center font-bold shadow-lg transition-all ${
              isPlaying
                ? 'bg-amber-500 hover:bg-amber-400 text-slate-950 shadow-amber-500/30'
                : 'bg-cyan-500 hover:bg-cyan-400 text-slate-950 shadow-cyan-500/30 hover:scale-105'
            }`}
            title={isPlaying ? 'Pausar' : 'Reproducir'}
          >
            {isPlaying ? <Pause className="w-6 h-6 fill-current" /> : <Play className="w-6 h-6 fill-current ml-0.5" />}
          </button>

          <button
            onClick={handleStop}
            className="w-10 h-10 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white flex items-center justify-center transition-colors border border-slate-700"
            title="Detener"
          >
            <Square className="w-4 h-4 fill-current" />
          </button>

          <button
            onClick={() => setIsLooping(!isLooping)}
            className={`w-10 h-10 rounded-xl flex items-center justify-center transition-colors border ${
              isLooping
                ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40'
                : 'bg-slate-800 hover:bg-slate-700 text-slate-400 border-slate-700'
            }`}
            title="Bucle continuo (Loop)"
          >
            <Repeat className="w-4 h-4" />
          </button>
        </div>

        {/* Multiplicador de Velocidad / Tempo */}
        <div className="flex items-center gap-1.5 bg-slate-950/80 px-2.5 py-1.5 rounded-xl border border-slate-800">
          <Gauge className="w-3.5 h-3.5 text-slate-400 mr-1" />
          {[0.5, 0.75, 1.0, 1.25, 1.5].map((mult) => (
            <button
              key={mult}
              onClick={() => handleTempoChange(mult)}
              className={`px-2 py-1 rounded-lg text-xs font-mono font-medium transition-colors ${
                tempoMultiplier === mult
                  ? 'bg-cyan-500 text-slate-950 font-bold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {mult}x
            </button>
          ))}
        </div>

        {/* Control de Volumen */}
        <div className="flex items-center gap-2">
          <button
            onClick={toggleMute}
            className="p-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 transition-colors"
            title={isMuted ? 'Activar sonido' : 'Silenciar'}
          >
            {isMuted || volume === 0 ? (
              <VolumeX className="w-4 h-4 text-rose-400" />
            ) : (
              <Volume2 className="w-4 h-4 text-cyan-400" />
            )}
          </button>
          <input
            type="range"
            min="0"
            max="100"
            value={isMuted ? 0 : volume}
            onChange={handleVolumeChange}
            className="w-20 md:w-24 h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-cyan-400"
          />
        </div>
      </div>
    </div>
  );
}
