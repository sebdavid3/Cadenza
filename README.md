# Cadenza — OMR con HOMR, GPU Passthrough y Reproducción en Navegador

Prototipo Fullstack para la digitalización y transcripción de partituras musicales a **MusicXML** y **MIDI** utilizando **HOMR** (Optical Music Recognition con Deep Learning), con aceleración por GPU (**NVIDIA CUDA 12.1**), renderizado interactivo en el navegador con **OpenSheetMusicDisplay** y reproducción sintetizada en tiempo real con **Tone.js**.

---

## 🏗️ Arquitectura del Sistema

```
homr-music-proto / Cadenza
├── backend/
│   ├── main.py                  # API FastAPI (POST /transcribe, GET /health, GET /gpu-info)
│   ├── requirements.txt         # Dependencias para modo CPU Fallback
│   ├── requirements-gpu.txt     # Dependencias con PyTorch CUDA 12.1
│   ├── check_gpu.py             # Diagnóstico y verificación de GPU/VRAM
│   ├── Dockerfile               # Imagen Docker CPU
│   └── Dockerfile.gpu           # Imagen Docker con soporte NVIDIA CUDA 12.1
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # Interfaz principal y monitor de estado hardware en tiempo real
│   │   ├── components/
│   │   │   ├── DropZone.jsx     # Carga de fotos/escaneos y generador de partituras de prueba
│   │   │   ├── ScoreViewer.jsx  # Renderizador interactivo SVG con OpenSheetMusicDisplay
│   │   │   ├── AudioPlayer.jsx  # Reproductor MIDI con sintetizador polifónico Tone.js
│   │   │   └── LoadingSpinner.jsx # Monitor de progreso de etapas en tiempo real
│   │   └── main.jsx
│   ├── package.json
│   ├── vite.config.js
│   └── Dockerfile
├── docker-compose.yml           # Despliegue con GPU NVIDIA (nvidia container runtime)
├── docker-compose.cpu.yml       # Despliegue en CPU (sin requisitos NVIDIA)
├── setup_local.sh               # Instalador automatizado Conda + CUDA 12.1 (Linux/macOS/WSL)
├── setup_local.bat              # Instalador automatizado para Windows nativo
├── run-local.sh                 # Lanzador local concurrent (Linux/macOS/WSL)
├── run-local.bat                # Lanzador local para Windows nativo
├── run-docker-gpu.sh            # Lanzador Docker con GPU
└── run-docker-cpu.sh            # Lanzador Docker CPU Fallback
```

---

## ⚡ 1. Desarrollo Local con GPU (Nativo)

### Requisitos Previos
- Tarjeta Gráfica NVIDIA con drivers actualizados.
- Miniconda o Anaconda instalado.
- Node.js (v18+ o v20+).

### Instalación Automatizada

En Linux / WSL / macOS:
```bash
chmod +x setup_local.sh run-local.sh run-docker-gpu.sh run-docker-cpu.sh
./setup_local.sh
```

En Windows (CMD / PowerShell):
```cmd
setup_local.bat
```

### Pasos Manuales (si prefieres paso a paso)

```bash
# 1. Crear entorno Conda con Python 3.11
conda create -n homr-proto python=3.11 -y
conda activate homr-proto

# 2. Instalar PyTorch con aceleración CUDA 12.1
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# 3. Instalar dependencias del Backend
pip install -r backend/requirements-gpu.txt

# 4. Verificar disponibilidad de GPU
python backend/check_gpu.py

# 5. Instalar dependencias del Frontend
cd frontend
npm install
cd ..
```

### Ejecutar Localmente

```bash
# En Linux/WSL:
./run-local.sh

# En Windows:
run-local.bat
```

* **Frontend:** [http://localhost:5173](http://localhost:5173)
* **Backend API & Swagger Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🐳 2. Docker con GPU (NVIDIA Passthrough)

### Requisitos Previos
1. Drivers de NVIDIA instalados en el sistema anfitrión.
2. **NVIDIA Container Toolkit** instalado y configurado en Docker:
   - Guía oficial: [NVIDIA Container Toolkit Installation](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
3. Verificar que Docker tiene acceso a la GPU:
   ```bash
   docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
   ```

### Levantar Contenedores con GPU

```bash
./run-docker-gpu.sh
# O manualmente:
docker compose -f docker-compose.yml up --build
```

---

## 💻 3. Docker sin GPU (Modo CPU Fallback)

Si no cuentas con GPU NVIDIA o estás en un entorno de integración continua:

```bash
./run-docker-cpu.sh
# O manualmente:
docker compose -f docker-compose.cpu.yml up --build
```

---

## 🔍 Endpoints de la API Backend

| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/health` | Estado del servicio y detección básica de GPU. |
| `GET` | `/gpu-info` | Diagnóstico de hardware (nombre de GPU, VRAM total, en uso y reservada, CUDA version). |
| `POST` | `/transcribe` | Recibe imagen (`multipart/form-data`), ejecuta HOMR, convierte MusicXML a MIDI con music21 y retorna JSON `{ musicxml, midi_base64, used_gpu, device_name, processing_time_sec }`. |

---

## 🎼 Notas Técnicas y Optimizaciones

1. **Caché de Modelos HOMR:**
   HOMR descarga automáticamente sus pesos neuronales en la primera ejecución (~cientos de MB). En los archivos `docker-compose.yml` se configuraron volúmenes persistentes (`homr_torch_cache` y `homr_models_cache`) mapeados a `/root/.cache/torch` y `/root/.cache/homr` para evitar descargas repetidas en cada inicio de contenedor.

2. **Detección Dinámica de Hardware:**
   El backend consulta `torch.cuda.is_available()`. Si la GPU está presente, HOMR y PyTorch ejecutan sus tensores en el dispositivo CUDA indexado; si no, cae transparentemente a CPU sin provocar errores 500.

3. **Conversión MusicXML → MIDI con `music21`:**
   Se utiliza el parser interno de `music21`:
   ```python
   from music21 import converter
   score = converter.parse(xml_path)
   score.write('midi', fp=midi_path)
   ```
   Esto no requiere la instalación pesada de MuseScore en el servidor y es 100% autónomo.

4. **Políticas de Audio del Navegador & Tone.js:**
   Los navegadores modernos bloquean la reproducción de audio hasta que el usuario interactúe con el DOM. El componente [`AudioPlayer.jsx`](file:///frontend/src/components/AudioPlayer.jsx) invoca de forma segura `await Tone.start()` en el evento de clic de inicio, utilizando un sintetizador polifónico optimizado `Tone.PolySynth(Tone.Synth)`.

5. **Limpia de Archivos Temporales:**
   Cada petición genera un identificador UUID y almacena sus imágenes en `/tmp/homr-proto/<uuid>`. La limpieza de archivos se garantiza en un bloque `finally` para evitar fugas de espacio en disco.
