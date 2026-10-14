# Entrega del Contrato API v1 al Diseño del Frontend (Frontend Handoff)

> **Versión de Contrato:** `1.0.0`  
> **Especificación OpenAPI:** [`docs/api/openapi.json`](./openapi.json)  
> **Tipos TypeScript del Cliente:** [`apps/web/src/types.ts`](../../apps/web/src/types.ts)  
> **Alineación Arquitectural:** [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) v1.2, ADR-0004, ADR-0007, ADR-0010, ADR-0011, ADR-0012, ADR-0013, ADR-0014, ADR-0015, ADR-0016.

---

## 1. Guía de Arranque Rápido del Entorno Local

Esta guía describe los pasos mínimos y reproducibles para levantar el entorno de desarrollo local con el backend y el visor web.

### 1.1. Dependencias y Entorno Python

> [!WARNING]
> **Nunca ejecutar `uv sync` a secas.**  
> Los motores OMR reales (`homr`, `oemer`) y la aceleración GPU (`onnxruntime-gpu==1.26.0`) son dependencias y extras opcionales. Un comando `uv sync` normal no conserva estos paquetes y los desinstalará silenciosamente.  
> Utilizar siempre:
> ```bash
> uv sync --inexact
> uv run --no-sync <comando>
> ```

### 1.2. Variables de Entorno Mínimas

> [!IMPORTANT]
> La API de Cadenza **no** lee automáticamente archivos `.env`; requiere variables de entorno en el proceso. Con solo un archivo `.env`, el servidor no arranca por falta de clave secreta.

Definir las variables mínimas en la sesión de terminal antes del arranque:

**PowerShell (Windows):**
```powershell
$env:CADENZA_AUTH_SECRET_KEY = "clave_secreta_local_min_32_caracteres_aleatorios"
$env:CADENZA_DATABASE_URL    = "sqlite+pysqlite:///C:/ruta/fuera/del/repo/cadenza.db"
$env:CADENZA_ARTIFACTS_DIR   = "C:\ruta\fuera\del\repo\artifacts"
$env:CADENZA_OMR_ENGINE      = "fake"      # o "homr"
$env:CADENZA_OMR_USE_GPU     = "false"     # o "true" para HOMR en GPU
$env:CADENZA_DISABLE_POWER_THROTTLING = "true"
```

**Bash (Linux / macOS):**
```bash
export CADENZA_AUTH_SECRET_KEY="clave_secreta_local_min_32_caracteres_aleatorios"
export CADENZA_DATABASE_URL="sqlite+pysqlite:////ruta/fuera/del/repo/cadenza.db"
export CADENZA_ARTIFACTS_DIR="/ruta/fuera/del/repo/artifacts"
export CADENZA_OMR_ENGINE="fake"          # o "homr"
export CADENZA_OMR_USE_GPU="false"         # o "true" para HOMR en GPU
export CADENZA_DISABLE_POWER_THROTTLING="true"
```

### 1.3. Creación del Primer Usuario Investigador

Dado que la plataforma no expone registro público ni recuperación por correo ([ADR-0012](../adr/ADR-0012-autenticacion-e-identidad.md)), el usuario inicial debe crearse mediante la CLI:

```bash
uv run --no-sync python -m cadenza.api.cli create-investigator --username admin --password "clave_segura_min_8"
```

### 1.4. Ejecución del Servidor Backend

Arrancar el servidor ASGI Uvicorn:

```bash
uv run --no-sync uvicorn cadenza.api.main:create_default_app --factory --host 127.0.0.1 --port 8000 --reload
```

- **Healthcheck:** `GET http://127.0.0.1:8000/health`
- **Documentación Swagger UI:** `http://127.0.0.1:8000/docs`
- **Especificación OpenAPI:** `http://127.0.0.1:8000/openapi.json`

### 1.5. Ejecución del Visor Web (`apps/web`)

```bash
cd apps/web
npm install
npm run dev
```

El servidor Vite arrancará en el puerto **5174** (`http://localhost:5174`).

> [!NOTE]
> **Entorno verificado:** Configuración probada y validada en Windows 11 (Intel Core i5-13450HX, 10 núcleos, 16 hilos, 32 GB RAM, NVIDIA GeForce RTX 5050 Laptop GPU 8 GB), Python 3.12, Node.js v24.18.0, el 2026-10-13.

---

## 2. Propósito y Alcance

Este documento formaliza la entrega del contrato de API v1 de Cadenza como base estable y congelada para el desarrollo y diseño integral de la interfaz de usuario frontend (`apps/web`).

El contrato está completamente especificado mediante OpenAPI 3.1, verificado en CI contra deriva de código y sincronizado automáticamente con tipos TypeScript fuertemente tipados (`apps/web/src/types.ts`).

---

## 3. Capacidades Funcionales del Backend

La API de Cadenza proporciona el ciclo de vida completo de digitalización y corrección musical asistida:

| Módulo / Capacidad | Endpoints Principales | Descripción |
| :--- | :--- | :--- |
| **Autenticación y Cuentas** | `POST /auth/login`<br>`GET /auth/me`<br>`POST /auth/password`<br>`GET/POST/PATCH /users` | Autenticación OAuth2 Bearer JWT. Control de roles (ADR-0012): `transcriptor` (edita sus sesiones) e `investigador` (administra usuarios y audita métricas). |
| **Transcripción OMR** | `POST /transcribe` | Ingesta síncrona de imágenes (PNG/JPEG), inferencia simbólica OMR (`HOMR` o `Fake`), validación inicial y creación de sesión en estado `transcribed` (ADR-0005, ADR-0016). |
| **Consultas de Sesión** | `GET /sessions`<br>`GET /sessions/{id}`<br>`GET /sessions/{id}/image`<br>`GET /sessions/{id}/export` | Listado ligero paginado (sin JSONB pesado). Consulta completa con estado materializado (`current_score`, `current_seq`, `anchor_index`). Descarga de imagen de origen. Exportación a MusicXML 4.0 y MIDI 1.0. |
| **Edición Humana (HITL)** | `POST /sessions/{id}/edits`<br>`POST /sessions/{id}/undo` | Registro append-only inmutable de ediciones con verificación de concurrencia optimista (`base_seq`). Operaciones atómicas tipadas (`EditOp`). Deshacer en el servidor como evento compensatorio inverso (ADR-0007, #35). |
| **Validación y Hallazgos** | `GET /sessions/{id}/findings`<br>`POST /sessions/{id}/validate`<br>`POST /sessions/{id}/findings/{id}/dismiss`<br>`POST /sessions/{id}/findings/{id}/restore` | Evaluación determinista de reglas sobre `current_score`. Filtro de hallazgos activos vs descartados. Preservación de falsos positivos descartados si su evento no fue modificado (#36). |
| **Mapa de Tiempo** | `GET /sessions/{id}/timing` | Cálculo determinista de mapa temporal para reproducción sincronizada (tiempo de inicio/fin en segundos por evento, compás, voz y acorde) (ARCHITECTURE.md §6.1, #42). |
| **Ciclo de Vida** | `POST /sessions/{id}/finalize`<br>`POST /sessions/{id}/reopen` | Cierre formal de sesión tras corrección (rechaza ediciones con `409 SessionClosed`). Reapertura permitida bajo auditoría (ADR-0014, #34). |
| **Métricas de Esfuerzo** | `POST /sessions/{id}/effort`<br>`GET /sessions/{id}/effort` | Persistencia de telemetría editorial: duración total, latencia hasta la primera corrección e intervenciones distribuidas por compás (ADR-0004, ADR-0009, #13). |
| **Sistema y Metadatos** | `GET /version`<br>`GET /health` | Metadatos del contrato (`1.0.0`) y estado del sistema. Todas las respuestas inyectan la cabecera HTTP `X-API-Version: 1.0.0`. |

---

## 4. Modelo de Datos y Representación Simbólica

### 4.1. `ScoreDocument` vs `ScoreIR` Materializado

1. **`ScoreDocument` (Crudo OMR, Inmutable):**
   - Contiene el árbol `ScoreIR` reconocido originalmente por el motor OMR.
   - Contiene `anchors` (`AnchorIndex`): asignación de cada evento musical a su ancla lógica y espacial en la imagen de origen.
   - Contiene `provenance`: motor OMR, hashes SHA-256 de imagen, marcas temporales y versiones de catálogo de reglas.
2. **`current_score` (`ScoreIR` Materializado en `current_seq`):**
   - Producido al aplicar en orden el registro append-only de ediciones (`edits`) sobre el árbol crudo.
   - Representa el estado presente de la música editada por el transcriptor.
3. **`anchor_index` (Índice de Anclas Actual):**
   - Mantiene la correspondencia posicional de eventos en el estado `current_seq`.

### 4.2. Estructura de un Ancla (`Anchor`) y Límites de Coordenadas (INV-0001)

El ancla es la clave lógica del modelo HITL (ADR-0011):

```typescript
export interface Anchor {
  part: number;          // Índice de parte instrumental (0-indexed)
  staff: number;         // Índice de pentagrama (0-indexed)
  measure: number;       // Número de compás (1-indexed)
  voice: number;         // Voz musical dentro del pentagrama (0-indexed)
  event_index: number;   // Posición secuencial del evento en su voz/compás
  staff_id: string;      // Identificador del pentagrama (ej. 'part-0-staff-0')
  bbox: [number, number, number, number] | null; // [x0, y0, x1, y1] en píxeles de la imagen original o null
  confidence: number | null; // Puntuación de certeza OMR [0.0 - 1.0] o null
}
```

> [!IMPORTANT]
> **Comportamiento de Coordenadas `bbox` y Confianza (`confidence`):**
> - **Formato de coordenadas `bbox`:** Cuando está presente, `bbox` especifica `[x0, y0, x1, y1]` en píxeles absolutos de la imagen original (esquina superior izquierda `[x0, y0]` y esquina inferior derecha `[x1, y1]`), **no** valores normalizados `[x, y, ancho, alto]`. Así lo consume directamente `apps/web/src/components/ImageOverlay.tsx`, calculando el ancho como `(x1 - x0)` y el alto como `(y1 - y0)`.
> - **Motor de prueba `FakeOMREngine`:** Genera cajas sintéticas `bbox` delimitadoras individuales por evento musical (`100 + event_index * 50, ...`).
> - **Motor real `HOMREngine`:** Los campos `bbox` y `confidence` son siempre **`null`** (investigación técnica INV-0001, ADR-0004 / D4). HOMR procesa la partitura mediante atención secuencial y no produce cajas delimitadoras confiables a nivel de símbolo individual ni emite probabilidades calibradas en su salida ONNX.
> - **Implicación para el Frontend:** La interfaz de usuario **NO** debe prometer ni depender de recuadros o resaltados sobre la imagen original de la partitura a nivel de nota o compás individual cuando se opera con el motor real. El diseño de la interfaz HITL debe fundamentarse en la **notación musical renderizada** (mediante OSMD o Verovio), manteniendo la imagen de origen cargada desde `GET /sessions/{id}/image` como una referencia visual estática y global de consulta para el transcriptor.

### 4.3. Operaciones de Edición (`EditOp`)

Las operaciones admitidas en `POST /sessions/{id}/edits` son estrictamente atómicas:

- `SetPitch`: Modifica altura absoluta (`after: { pitch: "C4" }`).
- `SetDuration`: Modifica valor rítmico en beats (`after: { duration_beats: "1/4" }`).
- `SetAccidental`: Altera alteración conservando la nota (`after: { accidental: "#" }`).
- `InsertEvent`: Inserta nota/silencio antes de la posición anclada.
- `DeleteEvent`: Elimina el evento anclado.
- `SetClef`: Cambia la clave musical del compás (`after: { sign: "G", line: 2 }`).
- `SetKey`: Cambia la armadura de clave (`after: { fifths: 1 }`).

---

## 5. Guía de Integración para el Frontend

### 5.1. Concurrencia Optimista con `base_seq`

Al enviar una edición (`POST /sessions/{id}/edits`):
1. El cliente envía `base_seq = current_seq` que tiene en su store local.
2. Si otro cliente editó mientras tanto, el servidor responde con `409 Conflict` (`SequenceConflict`):
   ```json
   {
     "detail": "Conflicto de secuencia: base_seq=0 no coincide con el estado actual de la sesión (seq=1)"
   }
   ```
3. El frontend debe recargar la sesión (`GET /sessions/{id}`) y notificar al usuario para resolver el conflicto sin pérdida silenciosa de datos.

### 5.2. Autoría de la Edición Fijada por el Servidor y Esquema Estricto

De acuerdo con ADR-0012 y el esquema `EditEventCreate`:
- El cuerpo de una edición (`POST /sessions/{id}/edits`) está estrictamente compuesto por `{base_seq, op, anchor, before, after}`:
  ```json
  {
    "base_seq": 0,
    "op": "SetPitch",
    "anchor": {
      "part": 0,
      "staff": 0,
      "measure": 1,
      "voice": 0,
      "event_index": 0
    },
    "before": null,
    "after": {
      "pitch": "D4"
    }
  }
  ```
- El autor de toda edición es fijado **exclusivamente por el servidor** a partir del token JWT del usuario autenticado (`current_user.username`).
- El modelo Pydantic prohíbe entradas adicionales (`extra="forbid"`). Cualquier otro campo en el cuerpo de la petición (por ejemplo `author` o `user_id`) es rechazado de inmediato con error **HTTP 422 Unprocessable Entity** (`extra_forbidden: Extra inputs are not permitted`).

### 5.3. Deshacer en el Servidor (`POST /sessions/{id}/undo`)

El frontend no debe implementar deshacer destructivo localmente para persistir en backend.
El backend gestiona undo append-only:
- `POST /sessions/{id}/undo` calcula automáticamente la edición inversa compensatoria, avanza `current_seq = current_seq + 1` y devuelve el `current_score` y `anchor_index` listos para ser repintados.

### 5.4. Formato de Errores de Validación de Pydantic (`422 Unprocessable Entity`)

Cuando una petición no cumple con la validación de esquemas (por ejemplo datos incompletos o tipos inválidos), FastAPI/Pydantic devuelve un objeto JSON con la clave `detail` (una lista de errores con `loc`, `msg` y `type`), **no** un atributo `errors`:

```json
{
  "detail": [
    {
      "loc": ["body", "op", "after", "pitch"],
      "msg": "Field required",
      "type": "missing"
    }
  ]
}
```

El cliente web debe consultar `error.response.data.detail` para extraer los mensajes de validación.

### 5.5. Proxy de Desarrollo de Vite (`apps/web/vite.config.ts`)

En desarrollo (`npm run dev`), el servidor Vite escucha en el puerto **5174** y redirige mediante proxy las peticiones hacia el backend (`http://localhost:8000`).

Rutas cubiertas por el proxy de Vite:
- `/transcribe` → `http://localhost:8000/transcribe`
- `/sessions` → `http://localhost:8000/sessions`
- `/auth` → `http://localhost:8000/auth`
- `/health` → `http://localhost:8000/health`

> [!WARNING]
> El proxy de Vite **NO** cubre `/users` ni `/version`. Si el frontend necesita consumir `/users` (administración de cuentas) o `/version`, debe añadirlas a `vite.config.ts` o utilizar una URL base explícita.

### 5.6. Renderizado de Notación y Navegación

1. **Lienzo de Partitura:** Se recomienda renderizar la partitura materializada usando OSMD (OpenSheetMusicDisplay) o Verovio alimentado desde `GET /sessions/{id}/export?format=musicxml` o procesando el `ScoreIR` tipado.
2. **Imagen de Referencia:** La imagen se obtiene en `GET /sessions/{id}/image` y se expone como un panel lateral o pestaña de referencia comparativa global.
3. **Panel de Hallazgos:** La lista de hallazgos devuelta por `GET /sessions/{id}/findings` señala anclas específicas (compás, pentagrama, evento). Al seleccionar un hallazgo, el frontend debe enfocar y resaltar el evento correspondiente en la partitura renderizada (OSMD/SVG).

### 5.7. Tiempos de Transcripción y Timeout Recomendado (#106)

El endpoint `POST /transcribe` es **síncrono**: procesa la imagen y devuelve directamente la sesión inicializada con su partitura y hallazgos. Con la eliminación de la detección de título por RapidOCR y la desactivación explícita de la limitación de energía de Windows 11 (EcoQoS / Power Throttling, issue #106), los tiempos medidos son:

- **Incipits / fragmentos de 1 pentagrama (caso interactivo estándar, motor directo):**
  - **GPU:** mediana de 0,7 s (media 0,7 s, máx 0,9 s; 0 peticiones ≥ 30 s).
  - **CPU:** mediana de 1,2 s (media 1,2 s, máx 1,5 s; 0 peticiones ≥ 30 s).
- **Páginas densas apiladas (hasta 12 pentagramas, motor directo):**
  - **GPU:** mediana de 6,4 s (máx 7,6 s).
  - **CPU:** mediana de 11,6 s (máx 12,0 s).
- **Arranque en frío (primera llamada tras iniciar el proceso):**
  - **Motor directo:** en GPU hasta 4,2 s (mediana 3,6 s); en CPU hasta 2,0 s (mediana 2,0 s).
  - **A través de HTTP (`POST /transcribe`):** la primera petición incorpora la carga de modelos, el grafo ONNX/CUDA, la conversión a `ScoreIR`, la persistencia en base de datos y el guardado en `ArtifactStore`. En ejecuciones reales contra el servidor en vivo con HOMR en GPU, este primer arranque en frío por HTTP se ha medido entre **3,8 s y 7,4 s**.
- **Latencia de extremo a extremo por HTTP en régimen caliente (HOMR en GPU):**
  - **Incipits:** entre 0,69 s y 0,76 s (mediana ~0,72 s; sobrecoste HTTP/BD típicamente menor a 40 ms frente al motor).
  - **Página de 8 pentagramas:** entre 4,16 s y 4,48 s (frente a 4,42 s de inferencia directa del motor).

**Recomendaciones para el Frontend:**
1. **Timeout HTTP del cliente:** Configurar el *timeout* de la petición `fetch`/`axios` en **30 s**. Este valor ofrece más de un 100 % de margen frente al peor caso medido en CPU (12,0 s para páginas de 12 pentagramas) y casi un 300 % frente a GPU (7,6 s en régimen normal; 7,4 s en el peor arranque en frío por HTTP). Si el backend opera en un entorno Windows 11 sin la renuncia a EcoQoS (`CADENZA_DISABLE_POWER_THROTTLING=false`), el proceso podría ser confinado a E-cores requiriendo hasta 120 s en páginas densas, pero con la configuración estándar (`true`) 30 s es plenamente suficiente (ADR-0016).
2. **Indicador de progreso:** El frontend debe mostrar un estado visual de carga explícito y no bloqueante (barra de progreso o indicador de actividad) mientras `POST /transcribe` resuelve la inferencia.

---

## 6. Estado Actual de `apps/web` (Punto de Partida para Fase 8)

El directorio `apps/web` contiene la base inicial del cliente web, estructurada con:
- **Tecnologías:** React 18, Vite 5, TypeScript 5, Zustand 4 (`editorStore`), TanStack React Query 5 y Vitest.
- **Cliente HTTP y Tipos:** `src/api/client.ts` tipado con las interfaces generadas automáticamente desde OpenAPI en `src/types.ts`.
- **Componentes Construidos:**
  - `LoginPanel`: Formulario de login Bearer JWT con roles `transcriptor`/`investigador`.
  - `UploadPanel`: Selector y carga de imagen para `POST /transcribe`.
  - `HitlWorkspace`: Espacio de trabajo integrado que orquesta la sesión activa.
  - `FindingsPanel`: Visualización de anomalías reportadas por el validador con botones para descartar (`POST /dismiss`) o restaurar (`POST /restore`).
  - `HistoryPanel`: Listado cronológico de eventos de edición y disparador de deshacer en servidor (`POST /undo`).
  - `EventInspector`: Visualización y formulario atómico para emitir operaciones `EditOp` (`SetPitch`, `SetDuration`, etc.).
  - `EffortMetrics`: Contador de tiempo de edición e intervenciones editoriales para `POST /effort`.
  - `ImageOverlay`: Dibuja las cajas delimitadoras `bbox` (`[x0, y0, x1, y1]` en píxeles) sobre la imagen de origen como botones interactivos. Es la forma principal de seleccionar un evento musical en el visor actual, junto con hacer clic sobre un hallazgo en `FindingsPanel`. **Consecuencia crítica con el motor real:** dado que `HOMREngine` no genera coordenadas espaciales y devuelve `bbox: null` (INV-0001), en sesiones procesadas con HOMR no se dibuja ninguna caja sobre la imagen; en consecuencia, una nota que no presente hallazgos activos no puede ser seleccionada interactivamente desde `ImageOverlay`.
- **Próximo Paso (Fase 8):** Incorporar el renderizador de notación musical OpenSheetMusicDisplay (OSMD) para permitir la selección interactiva de cualquier símbolo directamente sobre la partitura vectorial renderizada (independientemente del motor OMR), conectar la reproducción sonora interactiva con Tone.js consumiendo `GET /sessions/{id}/timing`, y pulir la experiencia de usuario interactiva sobre la partitura renderizada.

---

## 7. Verificado y No Verificado

### 7.1. Flujo Completo Verificado contra Backend Real (2026-10-13)

La secuencia completa de digitalización, edición, concurrencia, validación, deshacer y exportación fue ejecutada de punta a punta contra el servidor ASGI Uvicorn real (`uv run --no-sync python -m uvicorn cadenza.api.main:create_default_app --factory`), con base de datos SQLite y almacén de artefactos independientes ubicados fuera del repositorio, evaluando sucesivamente tanto el motor sintético (`CADENZA_OMR_ENGINE=fake`) como el motor de inferencia neuronal real (`CADENZA_OMR_ENGINE=homr` con `CADENZA_OMR_USE_GPU=true`):

#### 1. Verificación con motor de prueba (`CADENZA_OMR_ENGINE=fake`, CPU)
1. **Creación de Investigador:** `python -m cadenza.api.cli create-investigator --username admin --password <secreta>` ejecutado con código de salida 0.
2. **Sonda de Salud (`GET /health`):** HTTP 200 respondiendo exactamente:
   ```json
   {
     "status": "healthy",
     "version": "1.0.0",
     "database": "connected",
     "artifact_store": "accessible",
     "omr_engine": "fake",
     "device": "cpu"
   }
   ```
3. **Autenticación (`POST /auth/login`):** HTTP 200 devuelve token Bearer JWT (`token_type: "bearer"`).
4. **Transcripción Síncrona (`POST /transcribe`):** Carga multipart de imagen PNG; responde HTTP 201 con `session_id`, árbol `ScoreDocument`, cajas sintéticas `bbox` por evento y estado inicial `transcribed` en 16,8 ms.
5. **Consulta de Sesión (`GET /sessions/{id}`):** HTTP 200 con `current_seq=0` y partitura materializada.
6. **Edición Atómica (`POST /sessions/{id}/edits`):** Con `base_seq=0`, `op: "SetPitch"` (`C4` → `D4`), `before: null` y `after: {"pitch": "D4"}` persiste la corrección respondiendo HTTP 201 y avanzando a `seq=1`.
7. **Detección de Conflicto de Concurrencia Optimista:** Repetición de edición con `base_seq=0` sobre el estado actual (`seq=1`) rechazada con HTTP 409 Conflict:
   ```json
   {
     "detail": "Conflicto de secuencia. base_seq=0, actual=1"
   }
   ```
8. **Rechazo de Campos No Autorizados:** Petición de edición incluyendo el campo `author` rechazada con HTTP 422:
   ```json
   {
     "detail": [
       {
         "type": "extra_forbidden",
         "loc": ["body", "author"],
         "msg": "Extra inputs are not permitted"
       }
     ]
   }
   ```
9. **Revalidación (`POST /sessions/{id}/validate`):** HTTP 200 revalida deterministamente el estado actual.
10. **Deshacer en Servidor (`POST /sessions/{id}/undo`):** Con `base_seq=1` revierte la edición anterior, avanza a `current_seq=2` y devuelve la partitura restaurada HTTP 200.
11. **Exportación MusicXML y MIDI:** `GET /sessions/{id}/export?format=musicxml` devuelve HTTP 200 (`Content-Type: application/vnd.recordare.musicxml+xml`) y `GET /sessions/{id}/export?format=midi` devuelve HTTP 200 (`Content-Type: audio/midi`).

#### 2. Verificación con motor neuronal real (`CADENZA_OMR_ENGINE=homr`, GPU NVIDIA CUDA)
1. **Sonda de Salud (`GET /health`):** HTTP 200 confirmando inicialización y proveedor CUDA:
   ```json
   {
     "status": "healthy",
     "version": "1.0.0",
     "database": "connected",
     "artifact_store": "accessible",
     "omr_engine": "homr",
     "device": "cuda"
   }
   ```
2. **Transcripción Síncrona (`POST /transcribe`):**
   - **Arranque en frío a través de HTTP:** 3,82 s (frente a 3,10 s del motor directo), inicializando grafos ONNX en GPU, persistencia en BD y almacenamiento del artefacto.
   - **Estructura de anclas:** Genera todas las anclas simbólicas con `bbox: null` y `confidence: null` (INV-0001).
   - Responde HTTP 201 con sesión `transcribed`.
3. **Flujo HITL Completo:** `GET /sessions/{id}` (HTTP 200), edición `SetPitch` (HTTP 201, `seq=1`), conflicto por `base_seq=0` (HTTP 409), rechazo de `author` (HTTP 422), revalidación (HTTP 200), deshacer compensatorio en servidor (HTTP 200, `seq=2`), y exportación MusicXML y MIDI (HTTP 200) validados idénticamente.
4. **Medición de Latencias de Extremo a Extremo por HTTP:**
   - **Incipits en caliente:** 0,736 s, 0,715 s y 0,685 s (mediana 0,715 s; motor directo 0,70 s).
   - **Página de 8 pentagramas en caliente:** 4,480 s y 4,155 s (motor directo 4,423 s).

### 7.2. No Verificado (Alcance de la Fase 8)

- **Renderizado OSMD en Navegador:** Render dinámico de las partituras exportadas dentro de componentes Canvas/SVG en el navegador.
- **Reproducción Tone.js:** Síntesis de audio y seguimiento visual del cursor a partir de los tiempos de `GET /sessions/{id}/timing`.
- **Panel Administrativo `/users`:** Vistas de gestión de cuentas en el frontend web.

---

## 8. Mantenimiento y Regeneración del Contrato

Si se realizan cambios en los modelos Pydantic o endpoints del backend:

```powershell
# Regenerar openapi.json y apps/web/src/types.ts
uv run --no-sync python scripts/generate_openapi_and_types.py

# Verificar que los tests del contrato y frontend pasen al 100%
uv run --no-sync pytest apps/api/tests/test_openapi_contract.py
npm --prefix apps/web test
npm --prefix apps/web run build
```
