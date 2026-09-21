import os
import sys
import json
import uuid
import base64
import shutil
import asyncio
import logging
import tempfile
import subprocess
from pathlib import Path
from collections import deque
from typing import Dict, Any, Optional, Deque, Set

from fastapi import FastAPI, UploadFile, File, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Configuración de Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("cadenza-backend")

# Difusión de registro en vivo
# ---------------------------------------------------------------------------
# El motor OMR escribe su progreso real por stderr mientras trabaja. En lugar de
# capturarlo entero al final, se retransmite línea a línea a los clientes
# conectados, de modo que la interfaz muestre lo que de verdad está ocurriendo.

MAX_LINE_CHARS = 500      # el motor emite líneas de varios KB al volcar el XML
BACKLOG_SIZE = 200        # historial que recibe quien se conecta a mitad de proceso
QUEUE_SIZE = 1000


class LogBroker:
    """Reparte líneas de registro a los clientes suscritos.

    `publish` es seguro desde cualquier hilo: el trabajo pesado del motor corre
    fuera del bucle de eventos, así que las líneas llegan desde otro hilo y hay
    que reinyectarlas en el bucle para tocar las colas de asyncio.
    """

    def __init__(self) -> None:
        self._subscribers: Set[asyncio.Queue] = set()
        self._backlog: Deque[str] = deque(maxlen=BACKLOG_SIZE)
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def backlog(self) -> list:
        return list(self._backlog)

    def publish(self, line: str) -> None:
        line = line.rstrip()
        if not line:
            return
        if len(line) > MAX_LINE_CHARS:
            line = line[:MAX_LINE_CHARS] + f" … (+{len(line) - MAX_LINE_CHARS} caracteres)"
        if self._loop is None:
            self._backlog.append(line)
            return
        try:
            self._loop.call_soon_threadsafe(self._fanout, line)
        except RuntimeError:
            # El bucle se cerró mientras el motor seguía escribiendo
            pass

    def _fanout(self, line: str) -> None:
        self._backlog.append(line)
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(line)
            except asyncio.QueueFull:
                # Un cliente lento no debe frenar la transcripción
                pass


log_broker = LogBroker()


class BrokerLogHandler(logging.Handler):
    """Envía al difusor lo que el propio backend registra."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            log_broker.publish(self.format(record))
        except Exception:
            pass


_broker_handler = BrokerLogHandler()
_broker_handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S"))
logger.addHandler(_broker_handler)

# Detección de GPU PyTorch
def get_gpu_status() -> Dict[str, Any]:
    try:
        import torch
        cuda_available = torch.cuda.is_available()
        if cuda_available:
            device_id = torch.cuda.current_device()
            device_name = torch.cuda.get_device_name(device_id)
            props = torch.cuda.get_device_properties(device_id)
            total_mem = props.total_memory / (1024 ** 3)
            alloc_mem = torch.cuda.memory_allocated(device_id) / (1024 ** 3)
            res_mem = torch.cuda.memory_reserved(device_id) / (1024 ** 3)
            return {
                "cuda_available": True,
                "mode": "GPU",
                "device_count": torch.cuda.device_count(),
                "current_device": device_id,
                "device_name": device_name,
                "cuda_version": torch.version.cuda,
                "torch_version": torch.__version__,
                "memory_total_gb": round(total_mem, 2),
                "memory_allocated_gb": round(alloc_mem, 2),
                "memory_reserved_gb": round(res_mem, 2)
            }
        else:
            return {
                "cuda_available": False,
                "mode": "CPU",
                "device_count": 0,
                "current_device": None,
                "device_name": "CPU Fallback",
                "cuda_version": None,
                "torch_version": torch.__version__,
                "memory_total_gb": 0.0,
                "memory_allocated_gb": 0.0,
                "memory_reserved_gb": 0.0
            }
    except Exception as e:
        logger.warning(f"No se pudo consultar estado de GPU: {e}")
        return {
            "cuda_available": False,
            "mode": "CPU",
            "device_count": 0,
            "current_device": None,
            "device_name": "Unknown / CPU",
            "cuda_version": None,
            "torch_version": "N/A",
            "memory_total_gb": 0.0,
            "memory_allocated_gb": 0.0,
            "memory_reserved_gb": 0.0
        }

app = FastAPI(
    title="Cadenza HOMR OMR Backend",
    description="Servicio de transcripción de partituras ópticas a MusicXML y MIDI con aceleración GPU local y HOMR",
    version="1.0.0"
)

# CORS para permitir peticiones desde Vite / React
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Carpeta base para temporales
BASE_TEMP_DIR = Path("/tmp/homr-proto") if os.name != "nt" else Path(tempfile.gettempdir()) / "homr-proto"
BASE_TEMP_DIR.mkdir(parents=True, exist_ok=True)

class TranscribeResponse(BaseModel):
    musicxml: str
    midi_base64: str
    used_gpu: bool
    device_name: str
    processing_time_sec: Optional[float] = None
    message: str

@app.on_event("startup")
async def startup_event():
    # El difusor necesita el bucle de eventos para poder recibir líneas desde el
    # hilo en el que corre el motor
    log_broker.bind_loop(asyncio.get_running_loop())
    logger.info("Servicio iniciado.")


@app.get("/logs")
async def stream_logs():
    """Registro en vivo por Server-Sent Events.

    Quien se conecta recibe primero el historial reciente y después cada línea
    nueva a medida que se produce. El comentario periódico mantiene viva la
    conexión frente a proxies que cierran conexiones ociosas.
    """

    async def event_source():
        queue = log_broker.subscribe()
        try:
            for line in log_broker.backlog():
                yield f"data: {json.dumps(line)}\n\n"
            while True:
                try:
                    line = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(line)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            log_broker.unsubscribe(queue)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Evita que un proxy intermedio acumule la respuesta antes de enviarla
            "X-Accel-Buffering": "no",
        },
    )

@app.get("/health")
def health_check():
    gpu_info = get_gpu_status()
    return {
        "status": "healthy",
        "service": "cadenza-homr-backend",
        "gpu_available": gpu_info["cuda_available"],
        "device_name": gpu_info["device_name"],
        "torch_version": gpu_info["torch_version"],
        "cuda_version": gpu_info["cuda_version"]
    }

@app.get("/gpu-info")
def gpu_info():
    return get_gpu_status()

def run_homr_process(image_path: Path, output_dir: Path) -> Path:
    """
    Ejecuta el CLI de HOMR sobre image_path y retorna la ruta al MusicXML generado.
    """
    cmd_candidates = [
        ["homr", str(image_path)],
        [sys.executable, "-m", "homr", str(image_path)],
        [sys.executable, "-m", "homr.cli", str(image_path)],
        [sys.executable, "-m", "homr.main", str(image_path)]
    ]

    last_error = ""
    stderr_output = ""

    # Buscar comando ejecutable
    executed = False
    for cmd in cmd_candidates:
        try:
            logger.info(f"Ejecutando motor: {' '.join(cmd)}")
            # Popen en lugar de run: el motor tarda decenas de segundos y escribe
            # su progreso mientras trabaja. Leyendo línea a línea se puede
            # retransmitir en vivo en vez de esperar al volcado final.
            proc = subprocess.Popen(
                cmd,
                cwd=str(output_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # una sola corriente, en orden cronológico
                text=True,
                bufsize=1,                 # por líneas
                errors="replace"
            )

            collected = []
            try:
                assert proc.stdout is not None
                for raw_line in proc.stdout:
                    line = raw_line.rstrip()
                    if not line:
                        continue
                    collected.append(line)
                    log_broker.publish(line)
                returncode = proc.wait(timeout=180)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail="Tiempo de espera agotado al procesar la imagen (>180s)."
                )

            stderr_output = "\n".join(collected[-40:])

            if returncode == 0:
                executed = True
                break
            last_error = f"Código de salida {returncode}. Salida: {stderr_output}"
        except FileNotFoundError:
            continue
        except HTTPException:
            raise
        except Exception as ex:
            last_error = str(ex)

    if not executed:
        # Si falló la invocación por CLI, intentar importación directa de Python
        try:
            logger.info("Intentando ejecutar HOMR mediante importación en Python...")
            import homr
            # Algunos paquetes homr exponen funciones principales
            if hasattr(homr, "transcribe_image"):
                homr.transcribe_image(str(image_path), str(output_dir))
                executed = True
            elif hasattr(homr, "main") and hasattr(homr.main, "main"):
                # Simular sys.argv
                old_argv = sys.argv
                sys.argv = ["homr", str(image_path)]
                try:
                    homr.main.main()
                    executed = True
                finally:
                    sys.argv = old_argv
        except Exception as py_err:
            logger.warning(f"Intento de ejecución de HOMR por API Python falló: {py_err}")

    # Buscar archivos MusicXML generados en el directorio temporal
    xml_files = list(output_dir.glob("*.musicxml")) + list(output_dir.glob("*.xml"))
    if not xml_files:
        err_msg = f"HOMR no generó ningún archivo MusicXML. Detalle: {last_error or stderr_output or 'Proceso finalizó sin emitir XML'}"
        logger.error(err_msg)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=err_msg
        )

    # Retornar el archivo generado más reciente o con nombre coincidente
    return xml_files[0]

@app.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(file: UploadFile = File(...)):
    import time
    start_time = time.time()

    if not file.filename:
        raise HTTPException(status_code=400, detail="Nombre de archivo inválido.")

    # Validar extensión
    ext = Path(file.filename).suffix.lower()
    if ext not in [".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"]:
        raise HTTPException(
            status_code=400,
            detail=f"Formato no soportado '{ext}'. Por favor sube una imagen PNG, JPG, JPEG, BMP o TIFF."
        )

    # Crear directorio temporal único por solicitud
    request_id = str(uuid.uuid4())
    req_dir = BASE_TEMP_DIR / request_id
    req_dir.mkdir(parents=True, exist_ok=True)
    
    input_image_path = req_dir / f"input{ext}"
    midi_output_path = req_dir / "transcription.mid"

    try:
        # Guardar imagen recibida
        content = await file.read()
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="El archivo subido está vacío.")

        with open(input_image_path, "wb") as f_out:
            f_out.write(content)

        gpu_status = get_gpu_status()
        used_gpu = gpu_status["cuda_available"]
        device_name = gpu_status["device_name"]

        logger.info(f"[{request_id}] Iniciando transcripción OMR de {file.filename} (Tamaño: {len(content)} bytes). Modo: {gpu_status['mode']}")

        # 1. Ejecutar HOMR
        # A un hilo aparte: el motor bloquea decenas de segundos y, ejecutado
        # directamente aquí, congelaría el bucle de eventos —dejando sin responder
        # al resto de peticiones y, en particular, al registro en vivo—.
        musicxml_path = await asyncio.to_thread(run_homr_process, input_image_path, req_dir)

        # 2. Leer contenido de MusicXML
        with open(musicxml_path, "r", encoding="utf-8", errors="replace") as f_xml:
            musicxml_str = f_xml.read()

        # 3. Convertir MusicXML a MIDI usando music21
        logger.info(f"[{request_id}] Convirtiendo MusicXML a MIDI con music21...")
        try:
            from music21 import converter
            score = converter.parse(str(musicxml_path))
            score.write('midi', fp=str(midi_output_path))
            
            with open(midi_output_path, "rb") as f_midi:
                midi_bytes = f_midi.read()
                midi_base64 = base64.b64encode(midi_bytes).decode("utf-8")
        except Exception as midi_err:
            logger.error(f"[{request_id}] Error al convertir MusicXML a MIDI con music21: {midi_err}")
            # Si falla la conversión MIDI, se genera una respuesta con midi vacío para no bloquear la visualización
            midi_base64 = ""

        elapsed_sec = round(time.time() - start_time, 2)
        logger.info(f"[{request_id}] Transcripción completada exitosamente en {elapsed_sec}s.")

        return TranscribeResponse(
            musicxml=musicxml_str,
            midi_base64=midi_base64,
            used_gpu=used_gpu,
            device_name=device_name,
            processing_time_sec=elapsed_sec,
            message=f"Transcripción exitosa en {elapsed_sec}s usando {device_name}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[{request_id}] Error inesperado durante la transcripción: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno durante la transcripción: {str(e)}"
        )
    finally:
        # Limpieza de archivos temporales
        try:
            shutil.rmtree(req_dir, ignore_errors=True)
            logger.info(f"[{request_id}] Directorio temporal limpio.")
        except Exception as clean_err:
            logger.warning(f"[{request_id}] No se pudo limpiar {req_dir}: {clean_err}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
