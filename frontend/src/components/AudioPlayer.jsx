import React, { useState, useEffect, useRef, useCallback } from 'react';
import * as Tone from 'tone';
import { Midi } from '@tonejs/midi';
import { Play, Pause, Square, Repeat } from 'lucide-react';
import { Rule } from './Notation';

const BASE_BPM = 120;
// Indicaciones metronomicas reales en lugar de multiplicadores abstractos
const TEMPI = [60, 90, 120, 150, 180];

export default function AudioPlayer({ midiBase64, filename = 'partitura' }) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [bpm, setBpm] = useState(BASE_BPM);
  const [volume, setVolume] = useState(80);
  const [isMuted, setIsMuted] = useState(false);
  const [isLooping, setIsLooping] = useState(false);
  const [midiData, setMidiData] = useState(null);

  const synthRef = useRef(null);
  const volumeRef = useRef(null);
  const partRef = useRef(null);
  const animFrameRef = useRef(null);
  const isLoopingRef = useRef(isLooping);

  useEffect(() => { isLoopingRef.current = isLooping; }, [isLooping]);

  const decodeBase64 = useCallback((b64) => {
    const binary = window.atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return bytes;
  }, []);

  // Decodificar el MIDI recibido
  useEffect(() => {
    if (!midiBase64) return;

    Tone.Transport.stop();
    Tone.Transport.cancel();
    if (partRef.current) {
      partRef.current.dispose();
      partRef.current = null;
    }
    setIsPlaying(false);
    setCurrentTime(0);

    try {
      const parsed = new Midi(decodeBase64(midiBase64).buffer);
      setMidiData(parsed);
      setDuration(parsed.duration || 0);
    } catch (err) {
      console.error('No se pudo leer el MIDI:', err);
      setMidiData(null);
      setDuration(0);
    }
  }, [midiBase64, decodeBase64]);

  // Liberar la cadena de audio al desmontar
  useEffect(() => () => {
    Tone.Transport.stop();
    Tone.Transport.cancel();
    partRef.current?.dispose();
    synthRef.current?.dispose();
    volumeRef.current?.dispose();
    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
  }, []);

  // El bucle de refresco solo corre mientras suena algo
  useEffect(() => {
    if (!isPlaying) return undefined;

    const tick = () => {
      const current = Tone.Transport.seconds;
      setCurrentTime(current);

      if (duration > 0 && current >= duration) {
        if (isLoopingRef.current) {
          Tone.Transport.seconds = 0;
        } else {
          Tone.Transport.stop();
          Tone.Transport.seconds = 0;
          setIsPlaying(false);
          setCurrentTime(0);
          return;
        }
      }
      animFrameRef.current = requestAnimationFrame(tick);
    };

    animFrameRef.current = requestAnimationFrame(tick);
    return () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    };
  }, [isPlaying, duration]);

  const gainFor = (vol) => (vol === 0 ? -Infinity : Tone.gainToDb(vol / 100));

  const togglePlay = async () => {
    if (Tone.context.state !== 'running') await Tone.start();

    // Cadena de audio: sintetizador -> volumen -> limitador -> salida.
    // Una sola ruta hasta la salida; conectar tambien en directo duplicaria
    // la señal y dejaria parte del audio fuera del limitador.
    if (!synthRef.current) {
      const limiter = new Tone.Limiter(-2).toDestination();
      const vol = new Tone.Volume(gainFor(isMuted ? 0 : volume)).connect(limiter);
      const synth = new Tone.PolySynth(Tone.Synth, {
        oscillator: { type: 'triangle8' },
        envelope: { attack: 0.01, decay: 0.2, sustain: 0.4, release: 0.8 },
      }).connect(vol);

      synthRef.current = synth;
      volumeRef.current = vol;
    }

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
        synthRef.current?.triggerAttackRelease(value.note, value.duration, time, value.velocity);
      }, events);
      part.start(0);
      partRef.current = part;
    }

    if (isPlaying) {
      Tone.Transport.pause();
      setIsPlaying(false);
    } else {
      Tone.Transport.bpm.value = bpm;
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
    const next = parseFloat(e.target.value);
    setCurrentTime(next);
    Tone.Transport.seconds = next;
  };

  const handleTempo = (next) => {
    setBpm(next);
    Tone.Transport.bpm.value = next;
  };

  const handleVolume = (e) => {
    const next = parseInt(e.target.value, 10);
    setVolume(next);
    setIsMuted(false);
    if (volumeRef.current) volumeRef.current.volume.value = gainFor(next);
  };

  const toggleMute = () => {
    const next = !isMuted;
    setIsMuted(next);
    if (volumeRef.current) volumeRef.current.volume.value = gainFor(next ? 0 : volume);
  };

  const handleDownload = () => {
    const blob = new Blob([decodeBase64(midiBase64).buffer], { type: 'audio/midi' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${filename}.mid`;
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

  if (!midiBase64) return null;

  return (
    <section>
      <div className="flex flex-wrap items-baseline justify-between gap-4 mb-3">
        <h2 className="font-display text-lg text-bone">Audio</h2>
        <button
          onClick={handleDownload}
          className="text-sm text-brass hover:text-bone transition-colors"
        >
          Descargar MIDI
        </button>
      </div>

      <Rule />

      <div className="pt-6">
        {/* Recorrido de la pieza */}
        <div className="flex items-center gap-4">
          <span className="label tabular-nums shrink-0">{formatTime(currentTime)}</span>
          <input
            type="range"
            min="0"
            max={duration || 1}
            step="0.05"
            value={currentTime}
            onChange={handleSeek}
            aria-label="Posición de reproducción"
          />
          <span className="label tabular-nums shrink-0">{formatTime(duration)}</span>
        </div>

        <div className="mt-8 flex flex-wrap items-center gap-x-10 gap-y-6">
          {/* Transporte */}
          <div className="flex items-center gap-5">
            <button
              onClick={togglePlay}
              className="w-10 h-10 rounded-full bg-brass text-ink flex items-center justify-center hover:bg-bone transition-colors"
              aria-label={isPlaying ? 'Pausar' : 'Reproducir'}
            >
              {isPlaying
                ? <Pause className="w-4 h-4 fill-current" />
                : <Play className="w-4 h-4 fill-current ml-0.5" />}
            </button>
            <button
              onClick={handleStop}
              className="text-bone-dim hover:text-bone transition-colors"
              aria-label="Detener"
            >
              <Square className="w-4 h-4 fill-current" />
            </button>
            <button
              onClick={() => setIsLooping(!isLooping)}
              className={`transition-colors ${isLooping ? 'text-brass' : 'text-bone-dim hover:text-bone'}`}
              aria-label="Repetir"
              aria-pressed={isLooping}
            >
              <Repeat className="w-4 h-4" />
            </button>
          </div>

          {/* Tempo, en pulsaciones por minuto */}
          <div className="flex items-center gap-4">
            <span className="label">Tempo</span>
            <div className="flex items-center gap-3">
              {TEMPI.map((value) => (
                <button
                  key={value}
                  onClick={() => handleTempo(value)}
                  className={`font-mono text-xs tabular-nums transition-colors ${
                    bpm === value ? 'text-brass' : 'text-bone-faint hover:text-bone'
                  }`}
                >
                  {value}
                </button>
              ))}
            </div>
          </div>

          {/* Volumen, rotulado con matices musicales */}
          <div className="flex items-center gap-3 min-w-[160px]">
            <button
              onClick={toggleMute}
              className={`font-display italic text-sm transition-colors ${
                isMuted ? 'text-brass' : 'text-bone-faint hover:text-bone'
              }`}
              aria-label={isMuted ? 'Restablecer volumen' : 'Silenciar'}
              aria-pressed={isMuted}
            >
              pp
            </button>
            <input
              type="range"
              min="0"
              max="100"
              value={isMuted ? 0 : volume}
              onChange={handleVolume}
              aria-label="Volumen"
            />
            <span className="font-display italic text-sm text-bone-faint" aria-hidden="true">ff</span>
          </div>
        </div>
      </div>
    </section>
  );
}
