import React, { useState, useRef, useEffect } from 'react';
import { Rule } from './Notation';

const ACCEPTED = 'image/png,image/jpeg,image/jpg,image/bmp,image/tiff,image/webp';
const EXT_PATTERN = /\.(png|jpe?g|bmp|tiff?|webp)$/i;
const MAX_BYTES = 20 * 1024 * 1024;

/**
 * Genera una partitura de muestra en un lienzo, para poder probar sin buscar un
 * archivo. Dibuja pentagrama, clave, compas y notas: es contenido de partitura
 * real, que es justamente lo que el motor necesita leer.
 */
function createSampleScoreImage(sampleType) {
  const canvas = document.createElement('canvas');
  canvas.width = 900;
  canvas.height = 450;
  const ctx = canvas.getContext('2d');

  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  ctx.fillStyle = '#111111';
  ctx.font = 'bold 24px serif';
  ctx.textAlign = 'center';
  ctx.fillText(sampleType === 'c_major' ? 'Escala de Do mayor' : 'Estrellita', 450, 50);

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

  // Clave de sol y compas de cuatro por cuatro
  ctx.font = 'bold 64px serif';
  ctx.fillText('𝄞', 110, startY + 54);

  ctx.font = 'bold 30px serif';
  ctx.fillText('4', 160, startY + 24);
  ctx.fillText('4', 160, startY + 54);

  const notes = sampleType === 'c_major'
    ? [
        { x: 230, y: startY + 68, ledger: true },
        { x: 300, y: startY + 60 },
        { x: 370, y: startY + 52 },
        { x: 440, y: startY + 44 },
        { x: 510, y: startY + 36 },
        { x: 580, y: startY + 28 },
        { x: 650, y: startY + 20 },
        { x: 720, y: startY + 12 },
      ]
    : [
        { x: 230, y: startY + 68, ledger: true },
        { x: 300, y: startY + 68, ledger: true },
        { x: 370, y: startY + 36 },
        { x: 440, y: startY + 36 },
        { x: 510, y: startY + 28 },
        { x: 580, y: startY + 28 },
        { x: 670, y: startY + 36, half: true },
      ];

  notes.forEach((note) => {
    if (note.ledger) {
      ctx.beginPath();
      ctx.moveTo(note.x - 16, note.y);
      ctx.lineTo(note.x + 16, note.y);
      ctx.stroke();
    }

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

    ctx.beginPath();
    ctx.moveTo(note.x + 9, note.y);
    ctx.lineTo(note.x + 9, note.y - 48);
    ctx.lineWidth = 2;
    ctx.stroke();
  });

  // Barra final: fina y luego gruesa
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
      resolve({
        file: new File([blob], `${sampleType}.png`, { type: 'image/png' }),
        previewUrl: canvas.toDataURL('image/png'),
      });
    }, 'image/png');
  });
}

export default function DropZone({ onFileSelect, onTranscribe, selectedFile, disabled = false }) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [localError, setLocalError] = useState(null);
  const fileInputRef = useRef(null);
  const objectUrlRef = useRef(null);

  // Libera la URL anterior antes de crear otra, y tambien al desmontar
  const setPreview = (url, isObjectUrl) => {
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
    if (isObjectUrl) objectUrlRef.current = url;
    setPreviewUrl(url);
  };

  useEffect(() => () => {
    if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
  }, []);

  const processSelectedFile = (file) => {
    if (!file) return;

    const looksLikeImage = file.type.startsWith('image/') || EXT_PATTERN.test(file.name);
    if (!looksLikeImage) {
      setLocalError('Ese archivo no es una imagen. Usa PNG, JPG, BMP, TIFF o WebP.');
      return;
    }
    if (file.size > MAX_BYTES) {
      setLocalError('La imagen supera los 20 MB. Prueba con una version mas ligera.');
      return;
    }

    setLocalError(null);
    setPreview(URL.createObjectURL(file), true);
    onFileSelect(file);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files?.length) processSelectedFile(e.dataTransfer.files[0]);
  };

  const handleClear = () => {
    setPreview(null, false);
    setLocalError(null);
    onFileSelect(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleLoadSample = async (key) => {
    const { file, previewUrl: url } = await createSampleScoreImage(key);
    setLocalError(null);
    setPreview(url, false);
    onFileSelect(file);
  };

  // ---- Estado con archivo elegido ----
  if (selectedFile) {
    return (
      <div className="animate-fade-in">
        <Rule />
        <div className="py-8 flex flex-col sm:flex-row gap-8 items-start">
          {previewUrl && (
            <img
              src={previewUrl}
              alt="Vista previa de la partitura"
              className="w-full sm:w-56 h-40 object-contain bg-paper p-2 shrink-0"
            />
          )}

          <div className="flex-1 min-w-0">
            <p className="font-display text-lg text-bone truncate" title={selectedFile.name}>
              {selectedFile.name}
            </p>
            <p className="label mt-1.5">{(selectedFile.size / 1024).toFixed(0)} KB</p>

            <div className="flex flex-wrap items-center gap-6 mt-8">
              <button
                onClick={onTranscribe}
                disabled={disabled}
                className="px-5 py-2.5 rounded-sm bg-brass text-ink text-sm font-medium hover:bg-bone transition-colors disabled:opacity-40 disabled:hover:bg-brass"
              >
                Transcribir
              </button>
              <button
                onClick={handleClear}
                className="text-sm text-bone-dim hover:text-bone transition-colors"
              >
                Elegir otra
              </button>
            </div>
          </div>
        </div>
        <Rule />
      </div>
    );
  }

  // ---- Estado vacio: el pentagrama es la zona de carga ----
  return (
    <div>
      <Rule />

      <div
        onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={handleDrop}
        className="relative min-h-[240px] flex flex-col items-center justify-center text-center px-6 staff-lines transition-colors"
        style={isDragOver ? { '--rule': 'rgba(201, 162, 39, 0.55)' } : undefined}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED}
          onChange={(e) => e.target.files?.length && processSelectedFile(e.target.files[0])}
          className="hidden"
          id="sheet-music-input"
        />

        {isDragOver ? (
          <p className="font-display text-xl text-brass">Suelta para empezar</p>
        ) : (
          <>
            <p className="font-display text-xl text-bone mb-6">
              Arrastra una partitura aqui
            </p>
            <label
              htmlFor="sheet-music-input"
              className="px-5 py-2.5 rounded-sm bg-brass text-ink text-sm font-medium hover:bg-bone transition-colors cursor-pointer"
            >
              Seleccionar imagen
            </label>
          </>
        )}
      </div>

      <Rule />

      <div className="flex flex-wrap items-center justify-between gap-4 pt-4">
        <span className="label">PNG · JPG · BMP · TIFF · WebP</span>
        <span className="flex items-center gap-4 text-xs text-bone-dim">
          <span className="label">Ejemplos</span>
          <button
            onClick={() => handleLoadSample('c_major')}
            className="hover:text-bone transition-colors"
          >
            Escala de Do mayor
          </button>
          <button
            onClick={() => handleLoadSample('twinkle')}
            className="hover:text-bone transition-colors"
          >
            Estrellita
          </button>
        </span>
      </div>

      {localError && (
        <p className="mt-4 text-sm text-brick animate-fade-in">{localError}</p>
      )}
    </div>
  );
}
