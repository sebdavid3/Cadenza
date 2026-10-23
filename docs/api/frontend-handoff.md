# Entrega del Contrato API v1 al Diseño del Frontend (Frontend Handoff)

> **Versión de Contrato:** `1.0.0`  
> **Especificación OpenAPI:** [`docs/api/openapi.json`](./openapi.json)  
> **Tipos TypeScript del Cliente:** [`apps/web/src/types.ts`](../../apps/web/src/types.ts)  
> **Alineación Arquitectural:** [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) v1.2, ADR-0004, ADR-0007, ADR-0010, ADR-0011, ADR-0012, ADR-0013, ADR-0014, ADR-0015, ADR-0016.

---

## 1. Guía de Arranque Rápido del Entorno Local

Esta guía describe los pasos mínimos y reproducibles para levantar el backend en el entorno de desarrollo local. El frontend de `apps/web` se construye desde cero en la Fase 8 y se arranca como indica §6.

### 1.1. Dependencias y Entorno Python

> [!WARNING]
> **Nunca ejecutar `uv sync` a secas.**  
> El motor OMR (`homr`, único motor según ADR-0018) y la aceleración GPU (`onnxruntime-gpu==1.26.0`) son dependencias y extras opcionales. Un comando `uv sync` normal no conserva estos paquetes y los desinstalará silenciosamente.  
> Utilizar siempre:
> ```bash
> uv sync --inexact
> uv run --no-sync <comando>
> ```

> [!IMPORTANT]
> **HOMR es imprescindible para transcribir.** Es el único motor OMR (ADR-0018). Se instala como extra:
> ```bash
> uv pip install -e "packages/omr[homr]"
> ```
> Sin él la API arranca y `GET /health` responde, pero `POST /transcribe` devuelve **500**. La primera transcripción descarga los pesos del modelo.

### 1.2. Variables de Entorno Mínimas

> [!IMPORTANT]
> La API de Cadenza **no** lee automáticamente archivos `.env`; requiere variables de entorno en el proceso. Con solo un archivo `.env`, el servidor no arranca por falta de clave secreta.

Definir las variables mínimas en la sesión de terminal antes del arranque:

**PowerShell (Windows):**
```powershell
$env:CADENZA_AUTH_SECRET_KEY = "clave_secreta_local_min_32_caracteres_aleatorios"
$env:CADENZA_DATABASE_URL    = "sqlite+pysqlite:///C:/ruta/fuera/del/repo/cadenza.db"
$env:CADENZA_ARTIFACTS_DIR   = "C:\ruta\fuera\del\repo\artifacts"
$env:CADENZA_OMR_USE_GPU     = "false"     # o "true" para HOMR en GPU
$env:CADENZA_DISABLE_POWER_THROTTLING = "true"
```

**Bash (Linux / macOS):**
```bash
export CADENZA_AUTH_SECRET_KEY="clave_secreta_local_min_32_caracteres_aleatorios"
export CADENZA_DATABASE_URL="sqlite+pysqlite:////ruta/fuera/del/repo/cadenza.db"
export CADENZA_ARTIFACTS_DIR="/ruta/fuera/del/repo/artifacts"
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
| **Transcripción OMR** | `POST /transcribe` | Ingesta síncrona de imágenes (PNG/JPEG), inferencia simbólica OMR con HOMR (ADR-0018), validación inicial y creación de sesión en estado `transcribed` (ADR-0005, ADR-0016). |
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
> - **Motor `HOMREngine` (único motor, ADR-0018):** Los campos `bbox` y `confidence` son siempre **`null`** (investigación técnica [INV-0001](../investigaciones/INV-0001-salidas-internas-homr-bbox-y-confianza.md), deuda D4). HOMR procesa la partitura mediante atención secuencial y no produce cajas delimitadoras confiables a nivel de símbolo individual ni emite probabilidades calibradas en su salida ONNX.
> - **Implicación para el Frontend:** La interfaz de usuario **NO** debe prometer ni depender de recuadros o resaltados sobre la imagen original de la partitura a nivel de nota o compás individual. El diseño de la interfaz HITL debe fundamentarse en la **notación musical renderizada** (mediante OSMD o Verovio), manteniendo la imagen de origen cargada desde `GET /sessions/{id}/image` como una referencia visual estática y global de consulta para el transcriptor.

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
      "bbox": null,
      "confidence": null
    },
    "before": null,
    "after": {
      "pitch": "D4"
    }
  }
  ```
- Si se omite `staff_id` en el ancla, la API rechaza la petición con error de validación de esquema **HTTP 422** (`type: "missing"`, `loc: ["body", "anchor", "staff_id"]`).
- Una edición enviada con `before: null` es aceptada con **HTTP 201 Created**, el servidor fija en `before` la instantánea del estado previo (`snapshot_before`) y devuelve el evento de edición persistido (respuesta real con HOMR sobre el primer incipit del manifiesto de PrIMuS, 2026-10-20):
  ```json
  {
    "id": "dd39d405-2383-4908-909a-77f212a51540",
    "session_id": "90ee3d01-ae10-4ed5-b580-b39e90f3d92d",
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
      "bbox": null,
      "confidence": null
    },
    "before": {
      "pitch": "Bb5"
    },
    "after": {
      "pitch": "D4"
    },
    "reverts_edit_id": null,
    "created_at": "2026-10-21T02:51:31.681403Z"
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
  "detail": "Estado previo 'before' de pitch no coincide: esperado 'Bb5', recibido 'A0'"
}
```

> [!TIP]
> **Integración en el Cliente Web:** El cliente de `apps/web` convierte toda respuesta de error en un `ApiError` con su tipo (`kind`, según el código de estado) y un mensaje propio en español ([ADR-0019](../adr/ADR-0019-base-del-cliente-web.md)). El `detail` se conserva en `ApiError.detail` solo para depurar y **no se muestra al usuario**, porque mezcla español e inglés. Una vista que necesite señalar campos en un 422 de esquema puede recorrer `detail` cuando es una lista y traducir cada `loc` a un mensaje propio; un `detail` de texto nunca se presenta tal cual.

### 5.5. Acceso a la API en Desarrollo (CORS o Proxy)

La API escucha en `http://127.0.0.1:8000` (§1.4) y sus rutas no llevan prefijo (`/auth`, `/users`, `/transcribe`, `/sessions`, `/health`, `/version`). El frontend puede llamarla de dos formas:

- **URL base explícita y CORS:** usar una URL base configurable en el cliente. Con el valor por defecto `CADENZA_CORS_ORIGINS=*` no hace falta declarar nada; si se restringe la lista de orígenes (ADR-0015), hay que incluir el del servidor de desarrollo del frontend.
- **Proxy del servidor de desarrollo:** reenviar al backend las rutas de la API.

> [!WARNING]
> Con un proxy, ninguna ruta de la propia aplicación web puede coincidir con un prefijo reenviado: si el proxy reenvía `/sessions` y la interfaz usa una ruta `/sessions/:id`, al recargar la página o abrir un enlace directo la petición del documento llega al backend en lugar de devolver la aplicación (comprobado el 2026-10-20 con el servidor de desarrollo de Vite en una rama de prueba sin fusionar). Conviene agrupar la API bajo un prefijo del proxy (por ejemplo `/api`, reescrito al reenviar) o usar rutas de interfaz distintas.

### 5.6. Renderizado de Notación y Navegación

1. **Lienzo de Partitura:** Se recomienda renderizar la partitura materializada usando OSMD (OpenSheetMusicDisplay) o Verovio alimentado desde `GET /sessions/{id}/export?format=musicxml` o procesando el `ScoreIR` tipado.
2. **Imagen de Referencia:** La imagen se obtiene en `GET /sessions/{id}/image` y se expone como un panel lateral o pestaña de referencia comparativa global. El endpoint exige `Authorization: Bearer` y un `<img src>` no envía esa cabecera: la imagen debe descargarse con el cliente HTTP autenticado y mostrarse a partir de un `Blob` (`URL.createObjectURL`).
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

## 6. Estado Actual de `apps/web` (Fase 8)

`apps/web` se construye desde cero en la Fase 8 ([#129](https://github.com/sebdavid3/Cadenza/issues/129) retiró la base anterior). La base ([#144](https://github.com/sebdavid3/Cadenza/issues/144), [ADR-0019](../adr/ADR-0019-base-del-cliente-web.md)) aporta:

- **Stack:** React 18 + TypeScript estricto + Vite, con React Router, ESLint, Prettier y Vitest.
- **Cliente HTTP** (`apps/web/src/api/client.ts`), tipado con `apps/web/src/types.ts`: URL base configurable (`VITE_API_BASE_URL`, `/api` por defecto), `Authorization: Bearer` cuando hay sesión, timeout por petición (15 s por defecto; la constante `TRANSCRIBE_TIMEOUT_MS`, 30 s, es la que usará `POST /transcribe`, §5.7) y errores tipados por código de estado con mensajes propios en español. El `detail` del backend nunca se muestra.
- **Proxy de desarrollo:** Vite reenvía `/api` y lo que va bajo `/api/` a `http://127.0.0.1:8000` quitando el prefijo (§5.5); `/apidocs`, por ejemplo, no se reenvía, configurable con `CADENZA_API_PROXY_TARGET`. Ninguna ruta de la interfaz empieza por `/api`.
- **Sesión** ([#146](https://github.com/sebdavid3/Cadenza/issues/146), [ADR-0020](../adr/ADR-0020-sesion-del-cliente-web.md)): vista `/entrar`, token en `sessionStorage`, recuperación al recargar, cierre al vencer o ante un 401 y rutas privadas.
- **Página pública** en `/` ([#145](https://github.com/sebdavid3/Cadenza/issues/145)).
- **Transcripción** en `/transcripcion` ([#147](https://github.com/sebdavid3/Cadenza/issues/147)): cola que envía las imágenes de una en una a `POST /transcribe` con el timeout de §5.7 y estado por archivo, y listado de `GET /sessions` con la miniatura de `GET /sessions/{id}/image` cargada como Blob (§5.6).
- **Sistema de diseño:** `PRODUCT.md`, `DESIGN.md` y los *briefs* de `.impeccable/surfaces/`; tokens en `apps/web/src/styles/tokens.css` y tipografías servidas desde el proyecto.

Arranque, con la API ya en marcha (§1.4):

```bash
cd apps/web
npm ci
npm run dev        # http://localhost:5173 ; la API queda en http://localhost:5173/api
```

Puertas del frontend: `npm run lint`, `npm run format:check`, `npm run test` y `npm run build` (también en la CI).

Queda por construir sobre la API v1:
- **Acceso:** el inicio de sesión ya existe ([#146](https://github.com/sebdavid3/Cadenza/issues/146), [ADR-0020](../adr/ADR-0020-sesion-del-cliente-web.md)): vista `/entrar`, token en `sessionStorage`, recuperación al recargar, cierre al vencer el `exp` o ante un 401 y rutas privadas. Quedan el cambio de contraseña y la gestión de cuentas del investigador (`/users`).
- **Corrección:** render de la partitura con OpenSheetMusicDisplay (OSMD) para seleccionar cualquier símbolo sobre la notación, independientemente del motor OMR (HOMR devuelve `bbox: null`, INV-0001); las siete operaciones de `EditOp` con `base_seq` y manejo del 409 (§5.1); deshacer en el servidor (`POST /undo`, §5.3); descarte, restauración y revalidación de hallazgos.
- **Reproducción:** Tone.js con el cursor sincronizado a partir de `GET /sessions/{id}/timing`.
- **Cierre:** métricas de esfuerzo (`POST /sessions/{id}/effort`), finalización, reapertura y exportación MusicXML y MIDI.

---

## 7. Verificado y No Verificado

### 7.1. Flujo Completo Verificado contra Backend Real (2026-10-13 / 2026-10-14)

La secuencia completa de digitalización, edición, concurrencia, validación, deshacer y exportación fue ejecutada de punta a punta contra el servidor ASGI Uvicorn real (`uv run --no-sync python -m uvicorn cadenza.api.main:create_default_app --factory`), con base de datos SQLite y almacén de artefactos independientes ubicados fuera del repositorio, con HOMR en GPU (`CADENZA_OMR_USE_GPU=true`).

> [!NOTE]
> El mismo flujo se verificó también, el 2026-10-13, con el antiguo motor de prueba `fake`, retirado en [#130](https://github.com/sebdavid3/Cadenza/issues/130) ([ADR-0018](../adr/ADR-0018-homr-como-unico-motor-omr.md)). Ese registro queda en el historial de git de este archivo.

#### Verificación con HOMR (GPU NVIDIA CUDA)
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
