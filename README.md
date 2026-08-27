# Cadenza: Plataforma de Digitalización Asistida de Partituras

Cadenza es una plataforma fullstack diseñada para el reconocimiento óptico de música (OMR), validación inteligente basada en teoría musical y transcripción interactiva con retroalimentación humana (*Human-in-the-Loop*). Permite procesar partituras impresas y manuscritas modernas a partir de imágenes o escaneos, convirtiéndolas en formatos editables y reproducibles (**MusicXML 4.0** y **MIDI 1.0**), integrando visualización gráfica interactiva con **OpenSheetMusicDisplay** y síntesis de audio en tiempo real con **Tone.js**.

---

## Estructura del Repositorio

```
Cadenza/
├── backend/                  # Servidor API FastAPI, inferencia OMR y utilidades
│   ├── main.py               # Endpoints REST (/transcribe, /health, /gpu-info)
│   ├── check_gpu.py          # Script de diagnóstico de CUDA y memoria VRAM
│   ├── requirements.txt      # Dependencias estándar para ejecución en CPU
│   ├── requirements-gpu.txt  # Dependencias optimizadas con PyTorch CUDA 12.1
│   ├── Dockerfile            # Imagen base para entorno CPU
│   └── Dockerfile.gpu        # Imagen optimizada con aceleración NVIDIA CUDA
├── frontend/                 # Interfaz de usuario interactiva (SPA)
│   ├── src/
│   │   ├── App.jsx           # Componente principal y monitoreo de estado
│   │   ├── components/
│   │   │   ├── DropZone.jsx  # Carga de imágenes y previsualización
│   │   │   ├── ScoreViewer.jsx # Renderizado interactivo SVG (OSMD)
│   │   │   ├── AudioPlayer.jsx # Reproducción de partitura sintetizada (Tone.js)
│   │   │   └── LoadingSpinner.jsx # Indicador visual de progreso
│   │   └── main.jsx
│   ├── package.json          # Dependencias y scripts de Node.js
│   ├── vite.config.js        # Configuración de compilación con Vite
│   └── Dockerfile            # Imagen de despliegue para frontend
├── docs/                     # Documentación técnica, estado del arte y diseño DBB
│   ├── README.md             # Índice y guía general de documentación
│   ├── arquitectura-dbb.md   # Especificación de bloques de construcción (DBB)
│   ├── revision-literatura-prisma.md # Metodología sistemática PRISMA
│   └── literatura/           # Fichas bibliográficas organizadas por categoría
├── latex/                    # Documento maestro de tesis en formato IEEEtran
│   ├── main.tex              # Documento orquestador modular
│   ├── IEEEtran.cls          # Clase de documento IEEE de conferencia
│   ├── secciones/            # Capítulos individuales (Introducción, Problema, etc.)
│   ├── figuras/              # Diagramas vectoriales TikZ (Árbol del problema)
│   └── plantilla/            # Archivos de referencia y guía oficial de IEEE
├── scripts/                  # Scripts automatizados de instalación y ejecución
│   ├── setup_local.bat       # Instalador de entorno local para Windows
│   ├── setup_local.sh        # Instalador de entorno local para Linux/macOS/WSL
│   ├── run-local.bat         # Lanzador concurrent para Windows
│   ├── run-local.sh          # Lanzador concurrent para Linux/macOS/WSL
│   ├── run-docker-gpu.sh     # Lanzador Docker con aceleración GPU
│   └── run-docker-cpu.sh     # Lanzador Docker en modo CPU Fallback
├── docker-compose.yml        # Orquestación de contenedores con GPU NVIDIA
└── docker-compose.cpu.yml    # Orquestación de contenedores en modo CPU
```

---

## 1. Instalación y Ejecución Local

### Requisitos del Sistema
- **Python:** Versión 3.11.
- **Node.js:** Versión 18 o superior.
- **Gestor de Entornos:** Miniconda o Anaconda (recomendado).
- **Aceleración por Hardware (Opcional):** GPU NVIDIA con controladores compatibles con CUDA 12.1.

### Instalación Automatizada

**En Linux / macOS / WSL:**
```bash
chmod +x scripts/*.sh
./scripts/setup_local.sh
```

**En Windows (CMD o PowerShell):**
```cmd
scripts\setup_local.bat
```

### Instalación Manual (Paso a Paso)

1. Crear y activar el entorno de trabajo:
   ```bash
   conda create -n homr-proto python=3.11 -y
   conda activate homr-proto
   ```

2. Instalar PyTorch con aceleración CUDA (o CPU):
   ```bash
   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
   ```

3. Instalar las dependencias del backend:
   ```bash
   pip install -r backend/requirements-gpu.txt
   ```

4. Instalar las dependencias del frontend:
   ```bash
   cd frontend
   npm install
   cd ..
   ```

### Inicio de los Servicios

**En Linux / macOS / WSL:**
```bash
./scripts/run-local.sh
```

**En Windows:**
```cmd
scripts\run-local.bat
```

* **Interfaz de Usuario (Frontend):** [http://localhost:5173](http://localhost:5173)
* **API y Documentación Interactiva (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 2. Despliegue con Docker

### Modo con Aceleración por GPU (NVIDIA Container Toolkit)

Requiere tener configurado el soporte de GPU en Docker ([NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)).

```bash
./scripts/run-docker-gpu.sh
# O mediante docker compose directamente:
docker compose -f docker-compose.yml up --build
```

### Modo Estándar en CPU (Fallback)

Para servidores o estaciones de trabajo sin tarjeta gráfica dedicada:

```bash
./scripts/run-docker-cpu.sh
# O mediante docker compose directamente:
docker compose -f docker-compose.cpu.yml up --build
```

---

## 3. Especificación de la API REST

| Método | Endpoint | Parámetros / Body | Descripción |
|---|---|---|---|
| `GET` | `/health` | Ninguno | Verifica la disponibilidad del servicio y el estado de la GPU. |
| `GET` | `/gpu-info` | Ninguno | Reporta el modelo de GPU, memoria VRAM disponible, en uso y versión de CUDA. |
| `POST` | `/transcribe` | `file: UploadFile` (multipart/form-data) | Transcribe la imagen de partitura enviada, genera MusicXML, sintetiza el archivo MIDI en base64 y retorna el resultado estructurado junto con métricas de tiempo de inferencia. |

---

## 4. Consideraciones Técnicas y de Diseño

1. **Gestión de Caché de Modelos Neuronales:**  
   Los pesos de los modelos OMR se descargan automáticamente en la primera ejecución. En los despliegues con Docker, se emplean volúmenes nombrados persistentes (`homr_torch_cache` y `homr_models_cache`) mapeados a `/root/.cache/torch` y `/root/.cache/homr` para evitar transferencias redundantes en cada recreación del contenedor.

2. **Detección Dinámica de Hardware:**  
   El backend evalúa la disponibilidad de hardware mediante `torch.cuda.is_available()`. Si una GPU compatible está presente, los tensores se transfieren al dispositivo CUDA correspondiente; en caso contrario, la inferencia se degrada de manera controlada a la CPU sin generar interrupciones en el servicio.

3. **Conversión Simbólica y Validación con `music21`:**  
   La transformación de estructuras MusicXML a secuencias de eventos MIDI se realiza de manera determinista utilizando el toolkit de musicología computacional `music21`, eliminando dependencias externas de software como MuseScore en el entorno de backend.

4. **Sincronización de Audio en el Navegador:**  
   El frontend gestiona las restricciones de reproducción de audio (*autoplay policy*) inicializando el contexto Web Audio mediante `Tone.start()` tras la primera interacción del usuario, empleando un sintetizador polifónico para la reproducción auditiva inmediata de la transcripción generada.
