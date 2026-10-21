# Entrega del Contrato API v1 al Diseño del Frontend (Frontend Handoff)

> **Versión de Contrato:** `1.0.0`  
> **Especificación OpenAPI:** [`docs/api/openapi.json`](./openapi.json)  
> **Tipos TypeScript del Cliente:** [`apps/web/src/types.ts`](../../apps/web/src/types.ts)  
> **Alineación Arquitectural:** [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) v1.2, ADR-0004, ADR-0007, ADR-0010, ADR-0011, ADR-0012, ADR-0013, ADR-0014, ADR-0015, ADR-0016.

---

## 1. Guía de Arranque Rápido del Entorno Local

Esta guía describe los pasos mínimos y reproducibles para levantar el backend en el entorno de desarrollo local. El frontend de `apps/web` se rehace desde cero en la Fase 8 (§6).

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

> [!NOTE]
> **Entorno verificado:** Configuración del backend probada y validada en Windows 11 (Intel Core i5-13450HX, 10 núcleos, 16 hilos, 32 GB RAM, NVIDIA GeForce RTX 5050 Laptop GPU 8 GB) y Python 3.12, el 2026-10-13.

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
| **Mapa de Tiempo** | `GET /sessions/{id}/timing` | Cálculo determinista de mapa métrico para reproducción sincronizada: pulsos expresados como cadenas de fracciones exactas (`offset_beats`, `duration_beats`, `measure_offset_beats`, `total_beats`, `measure_offsets`) por evento, compás y voz. No incluye tempo ni segundos absolutos; la conversión a tiempo real la calcula el cliente a partir del tempo (BPM) seleccionado (ARCHITECTURE.md §6.1, #42). |
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
> - **Formato de coordenadas `bbox`:** Cuando está presente, `bbox` especifica `[x0, y0, x1, y1]` en píxeles absolutos de la imagen original (esquina superior izquierda `[x0, y0]` y esquina inferior derecha `[x1, y1]`), **no** valores normalizados `[x, y, ancho, alto]`: el ancho es `(x1 - x0)` y el alto `(y1 - y0)`.
> - **Motor de prueba `FakeOMREngine`:** Genera cajas sintéticas `bbox` rectangulares deterministas individuales por evento musical con `[x0, y0, x1, y1]`: abscisas `x0 = 20.0 + 30.0 * i`, `x1 = 36.0 + 30.0 * i` (donde `i` es el índice secuencial del evento en toda la partitura de prueba, orden `[0, 1, 2, 3]`), con `y0 = 40.0` e `y1 = 60.0` fijas (ancho de 16 px y alto de 20 px). En la partitura de prueba de 4 eventos devuelve `[20.0, 40.0, 36.0, 60.0]`, `[50.0, 40.0, 66.0, 60.0]`, `[80.0, 40.0, 96.0, 60.0]` y `[110.0, 40.0, 126.0, 60.0]` (ver `packages/omr/src/cadenza/omr/adapters/fake.py`).
> - **Motor real `HOMREngine`:** Los campos `bbox` y `confidence` son siempre **`null`** (investigación técnica [INV-0001](../investigaciones/INV-0001-salidas-internas-homr-bbox-y-confianza.md), deuda D4). HOMR procesa la partitura mediante atención secuencial y no produce cajas delimitadoras confiables a nivel de símbolo individual ni emite probabilidades calibradas en su salida ONNX.
> - **Implicación para el Frontend:** La interfaz de usuario **NO** debe prometer ni depender de recuadros o resaltados sobre la imagen original de la partitura a nivel de nota o compás individual cuando se opera con el motor real. El diseño de la interfaz HITL debe fundamentarse en la **notación musical renderizada** (mediante OSMD o Verovio), manteniendo la imagen de origen cargada desde `GET /sessions/{id}/image` como una referencia visual estática y global de consulta para el transcriptor.

### 4.3. Operaciones de Edición (`EditOp`) y Validación de Carga Útil (ADR-0017)

Las operaciones admitidas en `POST /sessions/{id}/edits` son estrictamente atómicas. De acuerdo con [ADR-0017](../adr/ADR-0017-validacion-del-contenido-de-las-ediciones.md), el servidor valida la coherencia de `after` en el vocabulario canónico del dominio y fija `before` con una instantánea del estado modificado (`snapshot_before`) antes de persistir la edición:

| Operación (`op`) | `after` admitido | Descripción y restricciones |
| :--- | :--- | :--- |
| `SetPitch` | `{"pitch": "C4"}` | Altura canónica (ej. `"C#4"`, `"Bb3"`). Solo se aplica sobre notas (rechaza silencios). |
| `SetDuration` | `{"duration_beats": "1/4"}` | Duración válida como número o cadena fraccionaria (`"1"`, `"0.5"`, `"3/4"`, `"1/3"`). |
| `SetAccidental` | `{"accidental": "#"}` | Alteración canónica: `null`, `""`, `"natural"`, `"#"`, `"##"`, `"x"`, `"b"`, `"-"`, `"bb"` o `"--"`. Solo sobre notas y la altura resultante debe ser canónica. |
| `InsertEvent` | `{"kind": "note" \| "rest", "duration_beats": ...}` | Inserta evento antes de la posición anclada. Si `kind="note"`, requiere `"pitch"`. Opcionales: `"tie"` (`"start"`, `"continue"`, `"stop"`), `"is_chord"` (booleano; prohibido en silencios), `"bbox"` (4 números), `"confidence"` (de 0 a 1) y `"voice"` (debe coincidir con la del ancla). |
| `DeleteEvent` | `null` | Elimina el evento anclado. **Debe llevar `after: null`** estrictamente (cualquier objeto es rechazado). |
| `SetClef` | `{"sign": "G", "line": 2}` | Clave musical: signo `"G"`, `"F"` o `"C"`, `"line"` de 1 a 5 y `"octave_change"` opcional de -2 a 2; o `{"clef": ...}` con objeto, nombre canónico (`"treble"`, `"bass"`, `"alto"`, etc.) o `null` para eliminar el cambio de clave. |
| `SetKey` | `{"fifths": 1, "mode": "major"}` | Armadura de clave: `"fifths"` entero de -7 a 7, `"mode"` opcional (`"major"`, `"minor"` o `null`); o `{"key_signature": ...}` / `{"key": ...}` con esa forma, entero o `null`. |

**Reglas de Validación Canónica (ADR-0017):**
1. **Altura canónica:** Letra mayúscula de la `A` a la `G`, alteración opcional (`#`, `##`, `b`, `bb`) y octava de 0 a 9 dentro del rango MIDI estándar (0 a 127). Valores como `"H9"`, `"C-1"` o minúsculas son rechazados con HTTP 422 (`InvalidEdit`).
2. **Duraciones admitidas:** Expresadas como entero, flotante o fracción en texto (`Fraction`), estrictamente mayores a 0 y como máximo 16 pulsos (una longa), con denominador de la forma $2^a \cdot t$ con $t \in \{1, 3, 5, 7\}$ y denominador máximo 128 (p. ej. `"1/2"`, `"1/3"`, `"3/4"`, `"1/5"`). Denominadores no representables (p. ej. `"1/17"`) o duraciones desmedidas son rechazados con 422 para garantizar exportación segura a MusicXML y MIDI.
3. **`before` fijado por el servidor:** El cliente puede enviar `before: null` o el estado previo que tenga en caché. El servidor almacena siempre una instantánea completa del estado preexistente (`snapshot_before`), de modo que deshacer (`POST /undo`) restaura el estado exacto sin depender del cliente. Si el cliente envía `before`, el servidor verifica que coincida con el estado real (de lo contrario responde 422 `InvalidEdit`).

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

De acuerdo con ADR-0012, ADR-0017 y el esquema `EditEventCreate`:
- El cuerpo de una edición (`POST /sessions/{id}/edits`) está estrictamente compuesto por `{base_seq, op, anchor, before, after}`. El objeto `anchor` debe incluir obligatoriamente todos sus campos identificadores, en particular `staff_id`:
  ```json
  {
    "base_seq": 0,
    "op": "SetPitch",
    "anchor": {
      "part": 0,
      "staff": 0,
      "measure": 1,
      "voice": 0,
      "event_index": 0,
      "staff_id": "part-0-staff-0",
      "bbox": [20.0, 40.0, 36.0, 60.0],
      "confidence": null
    },
    "before": null,
    "after": {
      "pitch": "D4"
    }
  }
  ```
- Si se omite `staff_id` en el ancla, la API rechaza la petición con error de validación de esquema **HTTP 422** (`type: "missing"`, `loc: ["body", "anchor", "staff_id"]`).
- Una edición enviada con `before: null` es aceptada con **HTTP 201 Created**, el servidor fija en `before` la instantánea del estado previo (`snapshot_before`) y devuelve el evento de edición persistido:
  ```json
  {
    "id": "97ee35f2-807f-474e-aa6a-23f3a4dfdb57",
    "session_id": "8fa662dc-6c60-4ff7-b516-d07fb666a387",
    "seq": 1,
    "op": "SetPitch",
    "author": "admin",
    "anchor": {
      "part": 0,
      "staff": 0,
      "measure": 1,
      "voice": 0,
      "event_index": 0,
      "staff_id": "part-0-staff-0",
      "bbox": [20.0, 40.0, 36.0, 60.0],
      "confidence": null
    },
    "before": {
      "pitch": "C4"
    },
    "after": {
      "pitch": "D4"
    },
    "reverts_edit_id": null,
    "created_at": "2026-10-14T12:30:33.897236Z"
  }
  ```
- El autor de toda edición es fijado **exclusivamente por el servidor** a partir del token JWT del usuario autenticado (`current_user.username`).
- El modelo Pydantic prohíbe entradas adicionales (`extra="forbid"`). Cualquier otro campo en el cuerpo de la petición (por ejemplo `author` o `user_id`) es rechazado de inmediato con error **HTTP 422 Unprocessable Entity** (`extra_forbidden: Extra inputs are not permitted`).

### 5.3. Deshacer en el Servidor (`POST /sessions/{id}/undo`)

El frontend no debe implementar deshacer destructivo localmente para persistir en backend.
El backend gestiona undo *append-only* (ADR-0007, ADR-0017):
- Petición: `POST /sessions/{id}/undo` enviando `{"base_seq": 1}`.
- Respuesta HTTP 200: Devuelve `{anchor_index, compensatory_edit, compensatory_edit_id, current_score, current_seq, session_id, undone_edit_id}`.
- La operación calcula automáticamente la edición inversa compensatoria, avanza la secuencia a `current_seq = current_seq + 1` (ej. `seq=2`) y restaura el estado previo en `current_score` y `anchor_index` (coincidente con el estado anterior a la edición deshecha).
- **Protección contra ediciones antiguas sin estado previo:** Si se solicita deshacer una edición histórica previa a ADR-0017 que carecía de un `before` suficiente, el servidor rechaza la petición con **HTTP 422** (`InvalidEdit`) indicando que no cuenta con estado previo suficiente, en lugar de corromper la partitura.

### 5.4. Formato de Errores de Validación (`422 Unprocessable Entity`)

La API emite errores HTTP 422 en dos formatos según el origen de la validación:

#### 1. Errores de validación de esquema Pydantic (`detail` es una lista)
Ocurren cuando el cuerpo JSON incumple la estructura sintáctica o de tipos. La clave `detail` es un array de objetos con `type`, `loc`, `msg` e `input`:

Ejemplo por ancla incompleta (falta `staff_id`):
```json
{
  "detail": [
    {
      "type": "missing",
      "loc": [
        "body",
        "anchor",
        "staff_id"
      ],
      "msg": "Field required",
      "input": {
        "part": 0,
        "staff": 0,
        "measure": 1,
        "voice": 0,
        "event_index": 0
      }
    }
  ]
}
```

Ejemplo por campo extra prohibido (`extra_forbidden` al enviar `author`):
```json
{
  "detail": [
    {
      "type": "extra_forbidden",
      "loc": [
        "body",
        "author"
      ],
      "msg": "Extra inputs are not permitted",
      "input": "admin"
    }
  ]
}
```

#### 2. Errores de regla de negocio o edición no válida (`detail` es una cadena de texto)
Ocurren cuando la petición cumple con el esquema básico pero viola las reglas semánticas de dominio (ADR-0017) o el estado previo no concuerda. La clave `detail` es directamente un `string`:

Ejemplo por altura no válida para `SetPitch` (`InvalidEdit`):
```json
{
  "detail": "Contenido de 'after' no válido para SetPitch: altura no válida: 'H9' (forma esperada: letra mayúscula de la A a la G, alteración opcional #, ##, b o bb y octava de 0 a 9 dentro del rango MIDI, p. ej. 'C#4' o 'Bb3')"
}
```

Ejemplo por discrepancia en el `before` suministrado por el cliente:
```json
{
  "detail": "Estado previo 'before' de pitch no coincide: esperado 'C4', recibido 'A0'"
}
```

> [!TIP]
> **Integración en el Cliente Web:** El cliente HTTP del frontend debe comprobar si `Array.isArray(error.response.data.detail)`. Si es un array, puede mapear los errores por campo (`loc.join('.')`); si es una cadena de texto (`typeof detail === "string"`), debe presentarlo directamente como mensaje de error al usuario.

### 5.5. Acceso a la API en Desarrollo (CORS o Proxy)

La API escucha en `http://localhost:8000` y sus rutas no llevan prefijo (`/auth`, `/users`, `/transcribe`, `/sessions`, `/health`, `/version`). El frontend puede llamarla de dos formas:

- **URL base explícita y CORS:** declarar el origen del servidor de desarrollo del frontend en `CADENZA_CORS_ORIGINS` (ADR-0015) y usar una URL base configurable en el cliente.
- **Proxy del servidor de desarrollo:** reenviar al backend las rutas de la API.

> [!WARNING]
> Con un proxy, ninguna ruta de la propia aplicación web puede coincidir con un prefijo reenviado. La base anterior de `apps/web` reenviaba `/sessions` y `/transcribe` y además los usaba como rutas de la interfaz: al recargar la página o abrir un enlace directo, la petición del documento llegaba al backend en lugar de devolver la aplicación (comprobado el 2026-10-20 con el servidor de desarrollo de Vite). Conviene agrupar la API bajo un prefijo del proxy (por ejemplo `/api`, reescrito al reenviar) o usar rutas de interfaz distintas.

> [!WARNING]
> `GET /sessions/{id}/image` exige `Authorization: Bearer`, y un `<img src>` no envía esa cabecera: la imagen debe descargarse con el cliente HTTP autenticado y mostrarse a partir de un `Blob` (`URL.createObjectURL`).

### 5.6. Renderizado de Notación y Navegación

1. **Lienzo de Partitura:** Se recomienda renderizar la partitura materializada usando OSMD (OpenSheetMusicDisplay) o Verovio alimentado desde `GET /sessions/{id}/export?format=musicxml` o procesando el `ScoreIR` tipado.
2. **Imagen de Referencia:** La imagen se obtiene en `GET /sessions/{id}/image` y se expone como un panel lateral o pestaña de referencia comparativa global.
3. **Panel de Hallazgos:** La lista de hallazgos devuelta por `GET /sessions/{id}/findings` señala anclas específicas (compás, pentagrama, evento). Al seleccionar un hallazgo, el frontend debe enfocar y resaltar el evento correspondiente en la partitura renderizada (OSMD/SVG).

### 5.7. Tiempos de Transcripción y Timeout Recomendado (#106, #118)

El endpoint `POST /transcribe` es **síncrono**: procesa la imagen e inicializa la sesión en base de datos. Devuelve únicamente los identificadores principales de la sesión y el conteo inicial de hallazgos (`{session_id, document_id, omr_engine, findings_count, condition, test_score_id}`). No devuelve la partitura (`current_score`), ni el índice de anclas (`anchor_index`), ni el estado: estos se obtienen a continuación mediante `GET /sessions/{id}`.

Con la eliminación de la detección de título por RapidOCR y la desactivación explícita de la limitación de energía de Windows 11 (EcoQoS / Power Throttling, issue #106), las mediciones del benchmark del motor (`results/latency_benchmark_summary.json`) son:
- **Incipits / fragmentos de 1 pentagrama (motor directo):**
  - **GPU:** mediana de 0,7 s (media 0,7 s, máx 0,9 s; 0 peticiones ≥ 30 s).
  - **CPU:** mediana de 1,2 s (media 1,2 s, máx 1,5 s; 0 peticiones ≥ 30 s).
- **Páginas compuestas (hasta 12 pentagramas, motor directo):**
  - **Página de 8 pentagramas (GPU):** mediana de 4,3 s (máx 5,2 s).
  - **Página de 12 pentagramas (GPU):** mediana de 6,4 s (máx 7,6 s).
  - **Página de 12 pentagramas (CPU):** mediana de 11,6 s (máx 12,0 s).
- **Arranque en frío (primera llamada del motor directo en el proceso):**
  - En GPU entre 3,5 s y 4,2 s (mediana 3,6 s); en CPU 2,0 s.

**Mediciones reales de latencia de extremo a extremo por HTTP (`POST /transcribe` con HOMR en GPU):**
Al invocar `POST /transcribe` a través de HTTP sobre la API en ejecución, la petición incluye la transferencia de la imagen, la inferencia OMR, la conversión a `ScoreIR`, la persistencia relacional en base de datos y el almacenamiento del artefacto en disco. En cuatro sesiones de verificación empírica contra el servidor Uvicorn en vivo con HOMR en GPU (Intel Core i5-13450HX, NVIDIA RTX 5050 Laptop GPU), las mediciones arrojaron:
- **Arranque en frío por HTTP (primera petición tras iniciar el proceso):**
  - Sesiones de verificación: 7,43 s / 3,82 s / 3,30 s / 11,29 s.
  - Rango observado: **3,30 s a 11,29 s**.
- **Incipits de 1 pentagrama en caliente por HTTP:**
  - Sesiones de verificación: 0,69–0,76 s / 0,69–0,74 s / 0,88–0,91 s / 0,78–0,85 s (mediana 0,85 s).
  - Rango global observado: **0,69 s a 0,91 s**.
- **Página de 8 pentagramas en caliente por HTTP:**
  - Sesiones de verificación: 4,39–4,40 s / 4,16–4,48 s / 5,25 s / 4,91–4,99 s.
  - Rango global observado: **4,16 s a 5,25 s** (coherente con la mediana de 4,3 s del benchmark del motor).

**Recomendaciones para el Frontend:**
1. **Timeout HTTP del cliente:** Configurar el *timeout* de la petición `fetch`/`axios` en **30 s**. Este valor ofrece amplio margen frente al peor caso medido en CPU (12,0 s para páginas de 12 pentagramas) y frente a GPU (máximo en caliente de 7,6 s y peor arranque en frío por HTTP de 11,29 s). Con la renuncia a EcoQoS activa (`CADENZA_DISABLE_POWER_THROTTLING=true`), 30 s es plenamente suficiente (ADR-0016).
2. **Indicador de progreso:** El frontend debe mostrar un estado visual de carga explícito y no bloqueante (barra de progreso o indicador de actividad) mientras `POST /transcribe` resuelve la inferencia.

---

## 6. Estado Actual de `apps/web` (Punto de Partida para Fase 8)

`apps/web` está vacío a propósito ([#129](https://github.com/sebdavid3/Cadenza/issues/129)): la base inicial del cliente web y el sistema de diseño anterior se retiraron para rehacer el frontend desde cero. Solo contiene `apps/web/src/types.ts`, las interfaces TypeScript generadas desde `docs/api/openapi.json` (§8), que no se editan a mano.

La Fase 8 debe cubrir sobre la API v1:
- **Acceso:** inicio de sesión con token Bearer JWT, perfil (`GET /auth/me`), cambio de contraseña y gestión de cuentas para el rol investigador (`/users`).
- **Ingesta:** envío de la imagen a `POST /transcribe` con el indicador de progreso de §5.7 y listado de sesiones (`GET /sessions`).
- **Corrección:** render de la partitura con OpenSheetMusicDisplay (OSMD) para seleccionar cualquier símbolo sobre la notación, independientemente del motor OMR (HOMR devuelve `bbox: null`, INV-0001); las siete operaciones de `EditOp` con `base_seq` y manejo del 409 (§5.1); deshacer en el servidor (`POST /undo`, §5.3); descarte, restauración y revalidación de hallazgos.
- **Reproducción:** Tone.js con el cursor sincronizado a partir de `GET /sessions/{id}/timing`.
- **Cierre:** métricas de esfuerzo (`POST /sessions/{id}/effort`), finalización, reapertura y exportación MusicXML y MIDI.

---

## 7. Verificado y No Verificado

### 7.1. Flujo Completo Verificado contra Backend Real (2026-10-13 / 2026-10-14)

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
3. **Autenticación (`POST /auth/login`):** HTTP 200 devuelve token Bearer JWT (`token_type: "bearer"`, `access_token`).
4. **Transcripción Síncrona (`POST /transcribe`):** Carga multipart de imagen PNG; responde HTTP 201 en 39 ms devolviendo los identificadores principales y el conteo de hallazgos (sin partitura ni cajas):
   ```json
   {
     "session_id": "8fa662dc-6c60-4ff7-b516-d07fb666a387",
     "document_id": "fake-doc-0001",
     "omr_engine": "fake",
     "findings_count": 0,
     "condition": "assisted",
     "test_score_id": null
   }
   ```
5. **Consulta de Sesión (`GET /sessions/{id}`):** HTTP 200 con `status: "transcribed"`, `current_seq=0`, partitura materializada (`current_score`) y 4 anclas con cajas sintéticas deterministas `bbox`: `[20.0, 40.0, 36.0, 60.0]`, `[50.0, 40.0, 66.0, 60.0]`, `[80.0, 40.0, 96.0, 60.0]` y `[110.0, 40.0, 126.0, 60.0]`.
6. **Rechazo de Ancla sin `staff_id`:** Petición de edición omitiendo `staff_id` rechazada con HTTP 422:
   ```json
   {
     "detail": [
       {
         "type": "missing",
         "loc": ["body", "anchor", "staff_id"],
         "msg": "Field required",
         "input": {
           "part": 0,
           "staff": 0,
           "measure": 1,
           "voice": 0,
           "event_index": 0
         }
       }
     ]
   }
   ```
7. **Rechazo de Carga Útil No Válida (`InvalidEdit`):** Petición `SetPitch` con `after: {"pitch": "H9"}` rechazada con HTTP 422:
   ```json
   {
     "detail": "Contenido de 'after' no válido para SetPitch: altura no válida: 'H9' (forma esperada: letra mayúscula de la A a la G, alteración opcional #, ##, b o bb y octava de 0 a 9 dentro del rango MIDI, p. ej. 'C#4' o 'Bb3')"
   }
   ```
8. **Rechazo de `before` No Coincidente:** Petición `SetPitch` con `before: {"pitch": "A0"}` sobre la nota `C4` rechazada con HTTP 422:
   ```json
   {
     "detail": "Estado previo 'before' de pitch no coincide: esperado 'C4', recibido 'A0'"
   }
   ```
9. **Edición Atómica Aceptada (`POST /sessions/{id}/edits`):** Con `base_seq=0`, `op: "SetPitch"` (`C4` → `D4`), `before: null` y `after: {"pitch": "D4"}` persiste la corrección respondiendo HTTP 201, avanzando a `seq=1`, autor `"admin"` y `before: {"pitch": "C4"}` fijado por el servidor:
   ```json
   {
     "id": "97ee35f2-807f-474e-aa6a-23f3a4dfdb57",
     "session_id": "8fa662dc-6c60-4ff7-b516-d07fb666a387",
     "seq": 1,
     "op": "SetPitch",
     "author": "admin",
     "anchor": {
       "part": 0,
       "staff": 0,
       "measure": 1,
       "voice": 0,
       "event_index": 0,
       "staff_id": "part-0-staff-0",
       "bbox": [20.0, 40.0, 36.0, 60.0],
       "confidence": null
     },
     "before": {
       "pitch": "C4"
     },
     "after": {
       "pitch": "D4"
     },
     "reverts_edit_id": null,
     "created_at": "2026-10-14T12:30:33.897236Z"
   }
   ```
10. **Detección de Conflicto de Concurrencia Optimista:** Repetición de edición con `base_seq=0` sobre el estado actual (`seq=1`) rechazada con HTTP 409 Conflict:
    ```json
    {
      "detail": "Conflicto de secuencia: base_seq=0 no coincide con el estado actual de la sesión (seq=1)"
    }
    ```
11. **Rechazo de Campos No Autorizados:** Petición de edición incluyendo el campo `author` rechazada con HTTP 422:
    ```json
    {
      "detail": [
        {
          "type": "extra_forbidden",
          "loc": ["body", "author"],
          "msg": "Extra inputs are not permitted",
          "input": "admin"
        }
      ]
    }
    ```
12. **Revalidación (`POST /sessions/{id}/validate`):** HTTP 200 devuelve `{current_seq: 1, findings: [], session_id: "8fa662dc-6c60-4ff7-b516-d07fb666a387"}`.
13. **Deshacer en Servidor (`POST /sessions/{id}/undo`):** Con `base_seq=1` revierte la edición anterior, avanza a `current_seq=2`, responde HTTP 200 con `{anchor_index, compensatory_edit, compensatory_edit_id, current_score, current_seq, session_id, undone_edit_id}` y restaura exactamente el `current_score` previo (`restored: true`).
14. **Exportación MusicXML y MIDI:** `GET /sessions/{id}/export?format=musicxml` devuelve HTTP 200 (`Content-Type: application/vnd.recordare.musicxml+xml`, 2177 bytes) y `GET /sessions/{id}/export?format=midi` devuelve HTTP 200 (`Content-Type: audio/midi`, 103 bytes).
15. **Mapa de Tiempo (`GET /sessions/{id}/timing`):** HTTP 200 devuelve `total_beats: "8"`, `measure_offsets: {"1": "0", "2": "4"}` y eventos con pulsos como fracciones en texto (`offset_beats: "0"`, `duration_beats: "1"`, `measure_offset_beats: "0"`).
16. **Imagen de Origen (`GET /sessions/{id}/image`):** HTTP 200 (`Content-Type: image/png`).

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
   - **Arranque en frío a través de HTTP:** 11,29 s (inicializando grafos ONNX en CUDA, inferencia neuronal, persistencia en BD y guardado de artefacto en disco). Rango medido en 4 sesiones de verificación: 3,30 s a 11,29 s.
   - **Estructura de anclas:** Genera 15 anclas simbólicas con `bbox: null` y `confidence: null` (INV-0001).
   - Responde HTTP 201 con sesión `{session_id: "4a5bc05c-1519-4a78-adae-3d24328666c9", document_id: "homr-c7598751d6ee", omr_engine: "homr", findings_count: 0, condition: "assisted", test_score_id: null}`.
3. **Flujo HITL Completo:** `GET /sessions/{id}` (HTTP 200, 15 anclas con `bbox: null`), edición `SetPitch` (`before: null` → HTTP 201 con `seq=1` y `before: {"pitch": "Bb5"}` fijado por servidor), conflicto de secuencia `base_seq=0` (HTTP 409), rechazo de `author` (HTTP 422), rechazo de `H9` (HTTP 422), revalidación (HTTP 200), deshacer compensatorio en servidor (HTTP 200, `seq=2`, `restored: true`), exportación MusicXML (HTTP 200, 5638 bytes) y MIDI (HTTP 200, 206 bytes), y timing (HTTP 200, `total_beats: "6"`) validados exhaustivamente.
4. **Medición de Latencias de Extremo a Extremo por HTTP en GPU:**
   - **Incipits en caliente:** 0,848 s, 0,846 s y 0,779 s (mediana 0,846 s; rango entre sesiones: 0,69 s a 0,91 s).
   - **Página de 8 pentagramas en caliente:** 4,986 s y 4,906 s (rango entre sesiones: 4,16 s a 5,25 s).

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

# Verificar que los tests del contrato pasen al 100%
uv run --no-sync pytest apps/api/tests/test_openapi_contract.py
```
