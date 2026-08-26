import React, { useState, useRef } from 'react';
import { UploadCloud, Image as ImageIcon, X, Sparkles, FileImage, Zap, Cpu } from 'lucide-react';

// Generador de imágenes de muestra para pruebas rápidas sin necesidad de buscar archivos
function createSampleScoreImage(sampleType) {
  const canvas = document.createElement('canvas');
  canvas.width = 900;
  canvas.height = 450;
  const ctx = canvas.getContext('2d');

  // Fondo blanco papel
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  ctx.fillStyle = '#111827';
  ctx.font = 'bold 24px serif';
  ctx.textAlign = 'center';

  if (sampleType === 'c_major') {
    ctx.fillText('Escala Do Mayor — HOMR Test', 450, 50);
  } else if (sampleType === 'twinkle') {
    ctx.fillText('Twinkle Twinkle Little Star — HOMR Test', 450, 50);
  } else {
    ctx.fillText('Melodía Simple — HOMR Test', 450, 50);
  }

  // Dibujar pentagrama (5 líneas)
  const startY = 180;
  const lineSpacing = 16;
  ctx.strokeStyle = '#000000';
  ctx.lineWidth = 2;

  for (let i = 0; i < 5; i++) {
    const y = startY + i * lineSpacing;
    ctx.beginPath();
    ctx.moveTo(80, y);
    ctx.lineTo(820, y);
    ctx.stroke();
  }

  // Clave de Sol simplificada / texto
  ctx.font = 'bold 64px serif';
  ctx.fillText('𝄞', 110, startY + 54);

  // Compás 4/4
  ctx.font = 'bold 30px serif';
  ctx.fillText('4', 160, startY + 24);
  ctx.fillText('4', 160, startY + 54);

  // Notas musicales en el pentagrama
  const notes = sampleType === 'c_major' 
    ? [
        { x: 230, y: startY + 68, label: 'C4', ledger: true },
        { x: 300, y: startY + 60, label: 'D4' },
        { x: 370, y: startY + 52, label: 'E4' },
        { x: 440, y: startY + 44, label: 'F4' },
        { x: 510, y: startY + 36, label: 'G4' },
        { x: 580, y: startY + 28, label: 'A4' },
        { x: 650, y: startY + 20, label: 'B4' },
        { x: 720, y: startY + 12, label: 'C5' },
      ]
    : [
        { x: 230, y: startY + 68, label: 'C4', ledger: true },
        { x: 300, y: startY + 68, label: 'C4', ledger: true },
        { x: 370, y: startY + 36, label: 'G4' },
        { x: 440, y: startY + 36, label: 'G4' },
        { x: 510, y: startY + 28, label: 'A4' },
        { x: 580, y: startY + 28, label: 'A4' },
        { x: 670, y: startY + 36, label: 'G4', half: true },
      ];

  notes.forEach((note) => {
    // Línea adicional para Do central
    if (note.ledger) {
      ctx.beginPath();
      ctx.moveTo(note.x - 16, note.y);
      ctx.lineTo(note.x + 16, note.y);
      ctx.stroke();
    }

    // Cabeza de la nota
    ctx.beginPath();
    ctx.ellipse(note.x, note.y, 11, 8, -0.3, 0, Math.PI * 2);
    if (note.half) {
      ctx.strokeStyle = '#000000';
      ctx.lineWidth = 2.5;
      ctx.stroke();
    } else {
      ctx.fillStyle = '#000000';
      ctx.fill();
    }

    // Plica
    ctx.beginPath();
    ctx.moveTo(note.x + 9, note.y);
    ctx.lineTo(note.x + 9, note.y - 48);
    ctx.lineWidth = 2;
    ctx.stroke();
  });

  // Barra de compás final
  ctx.beginPath();
  ctx.moveTo(780, startY);
  ctx.lineTo(780, startY + 64);
  ctx.lineWidth = 2;
  ctx.stroke();

  ctx.beginPath();
  ctx.moveTo(790, startY);
  ctx.lineTo(790, startY + 64);
  ctx.lineWidth = 4;
  ctx.stroke();

  return new Promise((resolve) => {
    canvas.toBlob((blob) => {
      const file = new File([blob], `${sampleType}_sample_score.png`, { type: 'image/png' });
      resolve({ file, previewUrl: canvas.toDataURL('image/png') });
    }, 'image/png');
  });
}

export default function DropZone({ onFileSelect, onTranscribe, selectedFile, isProcessing, gpuInfo }) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [previewUrl, setPreviewUrl] = useState(null);
  const fileInputRef = useRef(null);

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  const processSelectedFile = (file) => {
    if (!file) return;
    const validTypes = ['image/png', 'image/jpeg', 'image/jpg', 'image/bmp', 'image/tiff', 'image/webp'];
    if (!validTypes.includes(file.type) && !file.name.match(/\.(png|jpe?g|bmp|tiff?|webp)$/i)) {
      alert('Por favor selecciona una imagen válida (PNG, JPG, BMP, TIFF, WebP)');
      return;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    onFileSelect(file);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      processSelectedFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileInputChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      processSelectedFile(e.target.files[0]);
    }
  };

  const handleClear = () => {
    setPreviewUrl(null);
    onFileSelect(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleLoadSample = async (sampleKey) => {
    const { file, previewUrl } = await createSampleScoreImage(sampleKey);
    setPreviewUrl(previewUrl);
    onFileSelect(file);
  };

  return (
    <div className="w-full max-w-4xl mx-auto">
      {/* Selector / Drag and drop */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`relative border-2 border-dashed rounded-3xl p-8 transition-all duration-200 text-center ${
          isDragOver
            ? 'border-cyan-400 bg-cyan-950/20 scale-[1.01]'
            : 'border-slate-800 hover:border-slate-700 bg-slate-900/60'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept="image/png,image/jpeg,image/jpg,image/bmp,image/tiff,image/webp"
          onChange={handleFileInputChange}
          className="hidden"
          id="sheet-music-input"
        />

        {!selectedFile ? (
          <div className="flex flex-col items-center justify-center py-6">
            <div className="w-20 h-20 rounded-2xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center mb-4 text-cyan-400">
              <UploadCloud className="w-10 h-10" />
            </div>
            <h3 className="text-xl font-bold text-slate-100 mb-2">
              Arrastra una foto o escaneo de partitura aquí
            </h3>
            <p className="text-sm text-slate-400 max-w-md mb-6">
              Soporta imágenes monocromáticas, fotos de celular o partituras impresas en formato PNG, JPG, BMP o TIFF.
            </p>
            <label
              htmlFor="sheet-music-input"
              className="px-6 py-3 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white font-semibold text-sm shadow-lg shadow-cyan-600/30 cursor-pointer transition-all hover:shadow-cyan-500/50 flex items-center gap-2"
            >
              <FileImage className="w-4 h-4" /> Seleccionar desde el dispositivo
            </label>
          </div>
        ) : (
          <div className="flex flex-col md:flex-row items-center gap-6 p-2">
            {previewUrl && (
              <div className="relative group max-w-xs w-full bg-slate-950 rounded-2xl overflow-hidden border border-slate-800 shadow-md">
                <img
                  src={previewUrl}
                  alt="Vista previa de partitura"
                  className="w-full h-48 object-contain bg-white/95 p-2"
                />
                <button
                  onClick={handleClear}
                  disabled={isProcessing}
                  className="absolute top-2 right-2 p-1.5 rounded-full bg-rose-600/90 text-white hover:bg-rose-500 shadow-md transition-colors"
                  title="Quitar imagen"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            )}

            <div className="flex-1 text-left w-full">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-mono uppercase tracking-wider text-cyan-400 bg-cyan-950/80 px-2.5 py-1 rounded border border-cyan-800/60">
                  Archivo Preparado
                </span>
                <span className="text-xs text-slate-400 font-mono">
                  {(selectedFile.size / 1024).toFixed(1)} KB
                </span>
              </div>
              <h4 className="text-lg font-bold text-slate-100 truncate mb-1" title={selectedFile.name}>
                {selectedFile.name}
              </h4>
              <p className="text-xs text-slate-400 mb-6">
                Listo para procesar con HOMR OMR y síntesis MIDI.
              </p>

              <div className="flex flex-wrap items-center gap-3">
                <button
                  onClick={onTranscribe}
                  disabled={isProcessing}
                  className={`flex-1 min-w-[200px] px-6 py-3.5 rounded-xl font-bold text-sm shadow-xl flex items-center justify-center gap-2 transition-all ${
                    isProcessing
                      ? 'bg-slate-800 text-slate-500 cursor-not-allowed'
                      : 'bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white shadow-cyan-500/25 hover:shadow-cyan-400/40 hover:-translate-y-0.5'
                  }`}
                >
                  {gpuInfo?.cuda_available ? (
                    <Zap className="w-4 h-4 text-amber-300" />
                  ) : (
                    <Cpu className="w-4 h-4 text-cyan-300" />
                  )}
                  {isProcessing ? 'Procesando Partitura...' : 'Transcribir a MusicXML & MIDI'}
                </button>

                <button
                  onClick={handleClear}
                  disabled={isProcessing}
                  className="px-4 py-3.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium text-sm border border-slate-700 transition-colors"
                >
                  Cambiar
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Botones de Partituras de Ejemplo Rápidas */}
      <div className="mt-4 flex flex-wrap items-center justify-center gap-2 text-xs text-slate-400">
        <span className="flex items-center gap-1 text-slate-400 font-semibold mr-1">
          <Sparkles className="w-3.5 h-3.5 text-amber-400" /> Probar con ejemplos rápidos:
        </span>
        <button
          onClick={() => handleLoadSample('c_major')}
          disabled={isProcessing}
          className="px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-cyan-300 transition-colors cursor-pointer"
        >
          🎵 Escala Do Mayor
        </button>
        <button
          onClick={() => handleLoadSample('twinkle')}
          disabled={isProcessing}
          className="px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-cyan-300 transition-colors cursor-pointer"
        >
          ✨ Twinkle Twinkle
        </button>
      </div>
    </div>
  );
}
