# Entrega del Contrato API v1 al Diseño del Frontend (Frontend Handoff)

> **Versión de Contrato:** `1.0.0`  
> **Especificación OpenAPI:** [`docs/api/openapi.json`](./openapi.json)  
> **Tipos TypeScript del Cliente:** [`apps/web/src/types.ts`](../../apps/web/src/types.ts)  
> **Alineación Arquitectural:** [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) v1.2, ADR-0004, ADR-0007, ADR-0010, ADR-0011, ADR-0012, ADR-0013, ADR-0014, ADR-0015, ADR-0016.

---

## 1. Guía de Arranque Rápido del Entorno Local

Esta guía describe los pasos mínimos y reproducibles para levantar el backend en el entorno de desarrollo local. El frontend de `apps/web` (Fase 8) se arranca como indica §6.

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
$env:CADENZA_AUTH_SECRET_KEY = "<clave de openssl rand -hex 32>"   # al menos 32 bytes
$env:CADENZA_DATABASE_URL    = "sqlite+pysqlite:///C:/ruta/fuera/del/repo/cadenza.db"
$env:CADENZA_ARTIFACTS_DIR   = "C:\ruta\fuera\del\repo\artifacts"
$env:CADENZA_OMR_USE_GPU     = "false"     # o "true" para HOMR en GPU
$env:CADENZA_DISABLE_POWER_THROTTLING = "true"
```

**Bash (Linux / macOS):**
```bash
export CADENZA_AUTH_SECRET_KEY="$(openssl rand -hex 32)"
export CADENZA_DATABASE_URL="sqlite+pysqlite:////ruta/fuera/del/repo/cadenza.db"
export CADENZA_ARTIFACTS_DIR="/ruta/fuera/del/repo/artifacts"
export CADENZA_OMR_USE_GPU="false"         # o "true" para HOMR en GPU
export CADENZA_DISABLE_POWER_THROTTLING="true"
```

### 1.3. Creación del Primer Usuario Investigador

No hay recuperación por correo ([ADR-0012](../adr/ADR-0012-autenticacion-e-identidad.md)). El registro público (`POST /auth/register`, [ADR-0022](../adr/ADR-0022-registro-de-cuentas-con-activacion.md)) crea cuentas inactivas que un investigador tiene que activar, así que el primer investigador se crea con la CLI:

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
| **Autenticación y Cuentas** | `POST /auth/login`<br>`POST /auth/register`<br>`GET /auth/me`<br>`POST /auth/password`<br>`GET/POST/PATCH /users` | Autenticación OAuth2 Bearer JWT. Control de roles (ADR-0012): `transcriptor` (edita sus sesiones) e `investigador` (administra usuarios y audita métricas). Registro público abierto (ADR-0022, ADR-0025): `POST /auth/register` con `{username, password}` crea un transcriptor **activo** y autorregistrado (`self_registered: true` en `UserRead`), que puede entrar en el momento. El nombre: de 3 a 64 caracteres entre minúsculas sin tilde, cifras, `.`, `-` y `_`, empezando por letra o cifra; la contraseña, de al menos 8. Respuestas: 201, 409 nombre ocupado, 422 (esquema, con `loc` del campo), 429 con `Retry-After` y 404 si el registro está desactivado (`CADENZA_REGISTRATION_ENABLED`). Un investigador puede desactivarla con `PATCH /users/{id}` `{"active": false}`; entonces su inicio de sesión responde 401, como unas credenciales incorrectas (errores del login en §5.8). |
| **Transcripción OMR** | `POST /transcribe` | Ingesta síncrona de imágenes (PNG/JPEG), inferencia simbólica OMR con HOMR (ADR-0018), validación inicial y creación de sesión en estado `transcribed` (ADR-0005, ADR-0016). |
| **Consultas de Sesión** | `GET /sessions`<br>`GET /sessions/{id}`<br>`GET /sessions/{id}/image`<br>`GET /sessions/{id}/export` | Listado ligero paginado (sin JSONB pesado). Consulta completa con estado materializado (`current_score`, `current_seq`, `anchor_index`). Descarga de imagen de origen. Exportación a MusicXML 4.0 y MIDI 1.0. |
| **Edición Humana (HITL)** | `POST /sessions/{id}/edits`<br>`POST /sessions/{id}/undo` | Registro append-only inmutable de ediciones con verificación de concurrencia optimista (`base_seq`). Operaciones atómicas tipadas (`EditOp`). Deshacer en el servidor como evento compensatorio inverso (ADR-0007, #35). |
| **Validación y Hallazgos** | `GET /sessions/{id}/findings`<br>`POST /sessions/{id}/validate`<br>`POST /sessions/{id}/findings/{id}/dismiss`<br>`POST /sessions/{id}/findings/{id}/restore` | Evaluación determinista de reglas sobre `current_score`. Filtro de hallazgos activos vs descartados. Preservación de los falsos positivos descartados de la validación vigente si su evento no fue modificado (#36, ADR-0035). Con la capa de sugerencias, cada hallazgo lleva sus sugerencias y `POST /sessions/{id}/suggestions/{id}/reject` las rechaza (§5.9, ADR-0036). |
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

**Marcas de notación ([#213](https://github.com/sebdavid3/Cadenza/issues/213), [ADR-0031](../adr/ADR-0031-marcas-de-notacion-en-el-score-ir.md)).** Ampliación compatible del contrato v1: campos opcionales que la API devuelve siempre, con su valor por defecto si no hay marcas (también en los documentos guardados antes). Son atributos, no eventos: no cambian `event_index`.

| Campo | Dónde | Forma |
| :--- | :--- | :--- |
| `articulations` | `ScoreEventPayload` | Lista sin repetir, en este orden: `"staccato"`, `"staccatissimo"`, `"accent"`, `"marcato"`, `"tenuto"`. En un acorde, en su primera nota. Por defecto `[]`. |
| `fermata` | `ScoreEventPayload` | Calderón (también en un silencio). Por defecto `false`. |
| `slurs` | `ScoreEventPayload` | Extremos de ligadura de expresión: `[{"type": "start" \| "stop", "number": 1}]`. Por defecto `[]`. |
| `dynamics` | `MeasurePayload` | `[{"mark": "mf", "offset_beats": "3/2"}]`: ataque en negras desde el inicio del compás; rige el pentagrama. Marcas: `ppp`, `pp`, `p`, `mp`, `mf`, `f`, `ff`, `fff`, `sf`, `sfz`, `fp`, `fz`. Por defecto `[]`. |
| `wedges` | `MeasurePayload` | Extremos de regulador: `[{"type": "crescendo" \| "diminuendo" \| "stop", "number": 1, "offset_beats": "0"}]`. Por defecto `[]`. |

El inicio y el fin de una ligadura o de un regulador comparten `number`, que la identifica dentro de su parte (cruza compases, sistemas y pentagramas) y no se reutiliza. Un extremo sin pareja (p. ej. tras borrar la nota del otro extremo) se conserva y la exportación no lo dibuja; deshacer el borrado lo recompone. El MusicXML de `GET /export` lleva todas las marcas; OSMD las dibuja sin opciones adicionales. El MIDI no las lleva.

**Varias voces y silencios invisibles ([#218](https://github.com/sebdavid3/Cadenza/issues/218), [ADR-0032](../adr/ADR-0032-varias-voces-huecos-y-plicas.md)).** Los eventos de cada voz van seguidos; el hueco de una voz que entra a mitad del compás o calla entre dos notas es un silencio invisible: `ScoreEventPayload.hidden` (booleano, por defecto `false`; ampliación compatible del contrato v1, también en los documentos guardados antes). Es un evento más: `kind: "rest"`, ocupa su `duration_beats`, tiene ancla y **cuenta en `event_index`**, y el mapa de tiempos lo incluye como silencio; pero no se dibuja (el MusicXML exportado lo escribe con `print-object="no"`), no suena y la vista no lo ofrece para elegir. Lo que falta tras la última nota de una voz no es un evento. En el MusicXML exportado, las voces de cada pentagrama se numeran aparte (1-4 arriba, 5-8 abajo) y, en un compás con varias voces con notas, la más aguda lleva la plica hacia arriba y las demás hacia abajo.

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
| `InsertEvent` | `{"kind": "note" \| "rest", "duration_beats": ...}` | Inserta evento antes de la posición anclada. Si `kind="note"`, requiere `"pitch"`. Opcionales: `"tie"` (`"start"`, `"continue"`, `"stop"`), `"is_chord"` (booleano; prohibido en silencios), `"bbox"` (4 números), `"confidence"` (de 0 a 1), `"voice"` (debe coincidir con la del ancla) y las marcas de la nota (ADR-0031): `"articulations"` (lista del vocabulario de §4.1), `"fermata"` (booleano) y `"slurs"` (lista de `{"type": "start" \| "stop", "number": entero ≥ 1}`, sin otras claves); y `"hidden"` (booleano, solo con `kind="rest"`: un silencio invisible, ADR-0032). |
| `DeleteEvent` | `null` | Elimina el evento anclado. **Debe llevar `after: null`** estrictamente (cualquier objeto es rechazado). Su `before` guarda también las marcas del evento, si las tiene, y `"hidden": true` si es un silencio invisible, para que deshacer lo devuelva igual. |
| `SetClef` | `{"sign": "G", "line": 2}` | Clave musical: signo `"G"`, `"F"` o `"C"`, `"line"` de 1 a 5 y `"octave_change"` opcional de -2 a 2; o `{"clef": ...}` con objeto, nombre canónico (`"treble"`, `"bass"`, `"alto"`, etc.) o `null` para eliminar el cambio de clave. |
| `SetKey` | `{"fifths": 1, "mode": "major"}` | Armadura de clave: `"fifths"` entero de -7 a 7, `"mode"` opcional (`"major"`, `"minor"` o `null`); o `{"key_signature": ...}` / `{"key": ...}` con esa forma, entero o `null`. |
| `SetNoteMarks` | `{"articulations": ["accent"], "fermata": false}` | Marcas de la nota anclada ([ADR-0039](../adr/ADR-0039-anadir-y-quitar-marcas-de-notacion.md)): todas sus articulaciones (lista sin repetir del vocabulario de §4.1) y su calderón, las dos claves obligatorias. En un acorde, en su primera nota (una nota con `is_chord` se rechaza); un silencio solo lleva calderón; un silencio invisible, nada. |
| `SetDynamic` | `{"offset_beats": "1/2", "mark": "mf"}` | Dinámica de una posición del compás del ancla (basta que el compás exista, como `SetClef`): `"mark"` del vocabulario de §4.1 o `null` para quitarla; `"offset_beats"` ≥ 0, exacto en 10 080 divisiones por negra y sin pasar del final del compás. |
| `SetSlur` | `{"number": 2, "start": {"staff": 0, "measure": 1, "voice": 0, "event_index": 1}, "stop": {...}}` | Crea una ligadura de expresión con sus dos extremos (notas, primeras de su acorde, el fin después del inicio; `number` libre en la parte; el ancla es el evento del inicio) o, con `"start": null, "stop": null`, la quita entera (sus dos extremos o el que quede; el ancla es el inicio o, sin él, el fin). |
| `SetWedge` | `{"number": 1, "start": {"staff": 0, "measure": 1, "offset_beats": "0", "type": "crescendo"}, "stop": {"staff": 0, "measure": 2, "offset_beats": "1"}}` | Crea un regulador (`"type"` `"crescendo"` o `"diminuendo"`, el fin estrictamente después del inicio; `number` libre en la parte; ancla en el compás del inicio) o, con los dos extremos a `null`, lo quita entero. |

**Reglas de Validación Canónica (ADR-0017):**
1. **Altura canónica:** Letra mayúscula de la `A` a la `G`, alteración opcional (`#`, `##`, `b`, `bb`) y octava de 0 a 9 dentro del rango MIDI estándar (0 a 127). Valores como `"H9"`, `"C-1"` o minúsculas son rechazados con HTTP 422 (`InvalidEdit`).
2. **Duraciones admitidas:** Expresadas como entero, flotante o fracción en texto (`Fraction`), estrictamente mayores a 0 y como máximo 16 pulsos (una longa), con denominador de la forma $2^a \cdot t$ con $t \in \{1, 3, 5, 7\}$ y denominador máximo 128 (p. ej. `"1/2"`, `"1/3"`, `"3/4"`, `"1/5"`). Denominadores no representables (p. ej. `"1/17"`) o duraciones desmedidas son rechazados con 422 para garantizar exportación segura a MusicXML y MIDI.
3. **`before` fijado por el servidor:** El cliente puede enviar `before: null` o el estado previo que tenga en caché. El servidor almacena siempre una instantánea completa del estado preexistente (`snapshot_before`), de modo que deshacer (`POST /undo`) restaura el estado exacto sin depender del cliente. Si el cliente envía `before`, el servidor verifica que coincida con el estado real (de lo contrario responde 422 `InvalidEdit`).
4. **Operaciones de marcas (ADR-0039):** las cuatro son de tipo «fijar»: su `before` tiene la forma de su `after` y deshacer los intercambia. No mueven ningún evento (no desplazan anclas). No entran en el dataset ni en las métricas de los experimentos (`MARK_EDIT_OPS`, frente a las siete de contenido, `CONTENT_EDIT_OPS`).

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

**Una edición, un viaje ([#275](https://github.com/sebdavid3/Cadenza/issues/275), [ADR-0037](../adr/ADR-0037-una-edicion-en-un-solo-viaje.md)).** El 201 de `POST /sessions/{id}/edits` (`EditAppliedRead`) trae, además de la edición guardada con sus campos de siempre, el estado que crea: `current_seq`, `current_score`, `status`, `musicxml` (el mismo texto que daría `GET /export?format=musicxml`; `null` si no se pudo exportar, y entonces `/export` da el error) y `timing` (el mapa de `GET /timing`; `null` si no cambia respecto del estado `base_seq`, porque la edición no tocó duraciones ni eventos). `POST /undo` añade a su respuesta `status`, `musicxml` y `timing` con el mismo sentido. Los posibles errores no cambian sin revalidar (ADR-0035): no hay que volver a pedirlos. Con esto la vista no pide nada más tras editar, deshacer o rehacer; el 409 se trata igual que antes, recargando.

**Detalle sin lo que la vista no usa.** `GET /sessions/{id}?fields=view` devuelve `SessionViewRead`: los campos del detalle sin `document` ni `anchor_index`, que el servidor no calcula (cuesta eventos por ediciones). Sin `fields`, la respuesta no cambia.

**Medir.** Cada respuesta lleva `Server-Timing` con lo que tardó cada etapa en el servidor, en milisegundos: `db`, `materialize` (reconstruir el estado o aplicar y validar la edición), `export` (music21), `timing`, `serialize` y `total`. La API devuelve el `X-Request-ID` que envía el cliente si tiene la forma `[A-Za-z0-9._-]{1,64}` (si no, pone uno suyo) y lo registra; la web envía uno por petición (`web-` y 20 cifras hexadecimales).

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
- Respuesta HTTP 200: Devuelve `{anchor_index, compensatory_edit, compensatory_edit_id, current_score, current_seq, session_id, undone_edit_id}` y, desde [#275](https://github.com/sebdavid3/Cadenza/issues/275), `{status, musicxml, timing}` del estado nuevo (§5.1).
- La operación calcula automáticamente la edición inversa compensatoria, avanza la secuencia a `current_seq = current_seq + 1` (ej. `seq=2`) y restaura el estado previo en `current_score` y `anchor_index` (coincidente con el estado anterior a la edición deshecha).
- **Protección contra ediciones antiguas sin estado previo:** Si se solicita deshacer una edición histórica previa a ADR-0017 que carecía de un `before` suficiente, el servidor rechaza la petición con **HTTP 422** (`InvalidEdit`) indicando que no cuenta con estado previo suficiente, en lugar de corromper la partitura. Sin ninguna edición vigente que deshacer también responde **422** (`NoEditsToUndo`): el `status` no distingue las dos causas.
- **Qué se deshace:** la última edición vigente, leyendo el log como una pila en la que cada compensatoria (`reverts_edit_id`) retira la que revierte; deshacer varias veces va hacia atrás.
- **No hay endpoint de rehacer:** la vista de una sesión rehace volviendo a enviar la edición deshecha (misma `op`, `anchor` y `after`, con `before: null`) como edición nueva con el `base_seq` actual; tras deshacerla, su ancla vuelve a ser válida (ADR-0011). Ver [ADR-0034](../adr/ADR-0034-deshacer-y-rehacer-desde-la-vista.md).

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

1. **Lienzo de Partitura:** Se recomienda renderizar la partitura materializada usando OSMD (OpenSheetMusicDisplay) o Verovio alimentado desde `GET /sessions/{id}/export?format=musicxml` o procesando el `ScoreIR` tipado. Desde [#152](https://github.com/sebdavid3/Cadenza/issues/152) el MusicXML reproduce el `ScoreIR` compás a compás: cada compás lleva sus eventos en orden y con sus duraciones, también si está incompleto o sobrellenado (sin silencios ocultos de relleno ni notas repartidas entre compases); la métrica se escribe solo en el primer compás y donde cambia, y no hay título ni compositor de relleno. Una duración que no cabe en una sola figura se escribe como notas ligadas dentro del mismo compás. Una nota o un acorde de duración cero o nula se escribe como nota de adorno, que no ocupa tiempo ([#199](https://github.com/sebdavid3/Cadenza/issues/199), [ADR-0028](../adr/ADR-0028-notas-sin-duracion-como-notas-de-adorno.md)); un silencio de duración cero, como silencio de negra. El MIDI deja fuera las notas de adorno. Un compás sobrellenado no lleva barras de agrupación (music21 no lo agrupa) y un compás del que se borraron todos los eventos sale sin notas.
2. **Imagen de Referencia:** La imagen se obtiene en `GET /sessions/{id}/image` y se expone como un panel lateral o pestaña de referencia comparativa global. El endpoint exige `Authorization: Bearer` y un `<img src>` no envía esa cabecera: la imagen debe descargarse con el cliente HTTP autenticado y mostrarse a partir de un `Blob` (`URL.createObjectURL`).
3. **Panel de Hallazgos:** La lista de hallazgos devuelta por `GET /sessions/{id}/findings` señala anclas específicas (compás, pentagrama, evento). Al seleccionar un hallazgo, el frontend debe enfocar y resaltar el evento correspondiente en la partitura renderizada (OSMD/SVG).

### 5.7. Tiempos de Transcripción y Timeout Recomendado (#106, #118)

El endpoint `POST /transcribe` es **síncrono**: procesa la imagen e inicializa la sesión en base de datos. Devuelve únicamente los identificadores principales de la sesión y el conteo inicial de hallazgos (`{session_id, document_id, omr_engine, findings_count, condition, test_score_id}`). Con demasiadas transcripciones en curso responde **503** con `Retry-After` y un `detail` en español: HOMR calcula de una en una y la API admite `CADENZA_TRANSCRIBE_MAX_CONCURRENCY` a la vez ([ADR-0024](../adr/ADR-0024-transcripciones-simultaneas.md)); la vista de transcripción ya trata el 503 como servidor no disponible y pausa la cola. No devuelve la partitura (`current_score`), ni el índice de anclas (`anchor_index`), ni el estado: estos se obtienen a continuación mediante `GET /sessions/{id}`.

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

### 5.8. Errores del Inicio de Sesión (`POST /auth/login`, #143)

`POST /auth/login` recibe `username` y `password` como formulario `application/x-www-form-urlencoded` (OAuth2), que es el `requestBody` que declara el contrato. Sus respuestas, comprobadas el 2026-10-24 contra la API en local; los cuatro códigos están declarados en `openapi.json`, las cabeceras no:

| Código | Cuándo | Cuerpo y cabeceras |
| :--- | :--- | :--- |
| 200 | Credenciales válidas de una cuenta activa | `TokenResponse`: `{"access_token": "<JWT>", "token_type": "bearer"}`, con validez de `CADENZA_AUTH_TOKEN_EXPIRE_MINUTES` (30 por defecto) |
| 401 | Usuario inexistente, contraseña incorrecta o cuenta desactivada, sin distinguirlos | `{"detail": "Credenciales inválidas"}` y `WWW-Authenticate: Bearer` |
| 422 | Falta `username` o `password` como campo del formulario (un cuerpo JSON, una petición sin cuerpo o un campo vacío), o se envía un `grant_type` distinto de `password` | `detail` es una lista (§5.4), p. ej. `{"type": "missing", "loc": ["body", "password"], "msg": "Field required", "input": null}` |
| 429 | Tras 5 intentos fallidos en 300 s con el mismo nombre desde la misma IP (o red /64 en IPv6) | P. ej. `{"detail": "Demasiados intentos fallidos. Reintente en 299 segundos."}` y `Retry-After: 299`: los segundos que faltan, que bajan con el tiempo |

- **El 401 del login no es una sesión caducada.** Son unas credenciales inválidas o una cuenta desactivada, y el cliente no debe cerrar ninguna sesión por él. En `apps/web`, `logIn` envía la petición sin token (`auth: false`), y el cliente solo trata como caducada la sesión ante un 401 de una petición que llevaba token; la vista `/entrar` lo muestra como «Usuario o contraseña incorrectos, o la cuenta está desactivada.».
- **Tampoco el tiempo los distingue** ([#226](https://github.com/sebdavid3/Cadenza/issues/226), [ADR-0042](../adr/ADR-0042-login-con-el-mismo-trabajo-de-hash.md)): en los tres casos del 401 la API verifica la contraseña una vez, contra el hash de la cuenta o contra uno de relleno, y tarda lo mismo dentro del ruido (medido en local; el despliegue público no está medido).
- **El límite** (`CADENZA_LOGIN_RATE_LIMIT_MAX_ATTEMPTS` y `CADENZA_LOGIN_RATE_LIMIT_WINDOW_SECONDS`): el intento siguiente al quinto fallo ya responde 429, también con la contraseña correcta, hasta que el fallo más antiguo sale de la ventana. Un inicio de sesión correcto borra los fallos de ese nombre desde esa IP (los de otras IP siguen contando), y un 422 no cuenta. Con la API en otro origen, el navegador no deja leer `Retry-After` (§6, registro y cuentas).
- **En el despliegue,** Nginx limita además `/api/auth/login` a 10 peticiones por minuto por visitante, con ráfagas de 10 y cuerpos de hasta 16 KB ([`operacion_backend.md`](../infra/operacion_backend.md)), con cualquier nombre y salgan bien o mal. Ese 429 (o el 413 de un cuerpo mayor) es la página de error de Nginx, sin `detail` en JSON ni `Retry-After`: `deploy/nginx/cadenza.conf` no define `error_page`. El cliente de `apps/web` lo trata como cualquier 429.
- **Otro tipo de cuerpo:** FastAPI también acepta los dos campos en `multipart/form-data` (responde 200), pero el contrato solo declara `application/x-www-form-urlencoded`, que es lo que debe enviar el cliente (`URLSearchParams`).

---

### 5.9. Sugerencias de la capa que aprende (#256, ADR-0036)

Ampliación compatible del contrato: ningún campo existente cambia.

- `FindingRead.suggestions` (`SuggestionRead[]`, vacía por defecto) lleva de cero a tres ediciones propuestas, ordenadas por confianza: `id`, `op`, `anchor` (relativa al `at_seq` del hallazgo), `before`, `after`, `confidence` (0–1 o `null` si la capa no pudo puntuar el candidato de la regla), `confidence_level` (`high` o `medium`), `explanation` en lenguaje musical, `source` (`rule` o `learned`), `model_version` y `response` (`null`, `accepted` o `rejected`). Los posibles errores propios de la capa llegan como hallazgos con `rule_id` `learned.<familia>` (`learned.accidental` primero) y cuentan en `findings_count`.
- **Aplicar** es una edición normal: `POST /sessions/{id}/edits` con la `op`, el `anchor` y el `after` de la sugerencia, su `base_seq` y `suggestion_id`. Errores, en este orden: 409 de `base_seq` (sin reintento), 409 con `{"detail": "stale_suggestion"}` si la sugerencia no es de la validación de `base_seq` o ya tiene respuesta (marcarla como antigua y ofrecer revalidar), y 422 si la edición no es la propuesta. Rehacer reenvía la edición **sin** `suggestion_id`.
- **Rechazar**: `POST /sessions/{id}/suggestions/{suggestion_id}/reject` devuelve la `SuggestionRead`; 404 si no está (revalidar el mismo estado cambia los id), 403 a un investigador ajeno, 409 en una sesión finalizada o si ya se aplicó. Rechazar no descarta el hallazgo, y una revalidación hereda el rechazo de la validación vigente si el evento no cambió.
- `ProvenancePayload.suggestions_version` dice qué versión de la capa corrió al transcribir (`null` si no corrió).
- La capa solo corre con `CADENZA_SUGGESTIONS_ENABLED=true` y una versión promovida (`ml suggestions promote`); sin ella, o en `unassisted`, `suggestions` es siempre `[]`. La interfaz es de [#258](https://github.com/sebdavid3/Cadenza/issues/258).
- **Qué llega en el estudio (ADR-0036, enmienda 19).** La API solo envía las sugerencias que pasan su política (`CADENZA_SUGGESTIONS_MIN_LEVEL` y `CADENZA_SUGGESTIONS_FAMILIES`), que por defecto, la decisión del responsable en [#244](https://github.com/sebdavid3/Cadenza/issues/244), es solo las de alteración de confianza alta: `op` `SetAccidental` y `confidence_level` `high`. Los hallazgos de las reglas llegan igual, pero sin sugerencias de otra familia ni de confianza media: `measure.balance` llega con `suggestions: []` y no hay que ofrecer «Aplicar» en él, mientras que `key.consistency`, cuyos candidatos son alteraciones, sí puede traer sugerencias `SetAccidental` de confianza alta, que se aplican igual. Los posibles errores propios son solo `learned.accidental`, cada uno con su sugerencia. La web no debe dar nada de esto por supuesto (otra configuración puede enviar `medium` u otras familias), pero con la de por defecto no verá otra cosa. Sin cambios del contrato.

## 6. Estado Actual de `apps/web` (Fase 8)

`apps/web` se construyó desde cero en la Fase 8 ([#129](https://github.com/sebdavid3/Cadenza/issues/129) retiró la base anterior); el plan de la fase y su criterio de cierre están en [`docs/phases/phase_8_web_interface/README.md`](../phases/phase_8_web_interface/README.md). La base ([#144](https://github.com/sebdavid3/Cadenza/issues/144), [ADR-0019](../adr/ADR-0019-base-del-cliente-web.md)) aporta:

- **Stack:** React 18 + TypeScript estricto + Vite, con React Router, ESLint, Prettier y Vitest.
- **Cliente HTTP** (`apps/web/src/api/client.ts`), tipado con `apps/web/src/types.ts`: URL base configurable (`VITE_API_BASE_URL`, `/api` por defecto), `Authorization: Bearer` cuando hay sesión, timeout por petición (15 s por defecto; la constante `TRANSCRIBE_TIMEOUT_MS`, 30 s, es la que usa `POST /transcribe`, §5.7) y errores tipados por código de estado con mensajes propios en español. El `detail` del backend nunca se muestra.
- **Proxy de desarrollo:** Vite reenvía `/api` y lo que va bajo `/api/` a `http://127.0.0.1:8000` quitando el prefijo (§5.5); `/apidocs`, por ejemplo, no se reenvía, configurable con `CADENZA_API_PROXY_TARGET`. Ninguna ruta de la interfaz empieza por `/api`.
- **Sesión** ([#146](https://github.com/sebdavid3/Cadenza/issues/146), [ADR-0020](../adr/ADR-0020-sesion-del-cliente-web.md)): vista `/entrar`, token en `sessionStorage`, recuperación al recargar, cierre al vencer o ante un 401 y rutas privadas.
- **Página pública** en `/` ([#145](https://github.com/sebdavid3/Cadenza/issues/145)).
- **Transcripción** en `/transcripcion` ([#147](https://github.com/sebdavid3/Cadenza/issues/147)): cola que envía las imágenes de una en una a `POST /transcribe` con el timeout de §5.7 y estado por archivo, y listado de `GET /sessions` con la miniatura de `GET /sessions/{id}/image` cargada como Blob (§5.6).
- **Registro y cuentas** ([#155](https://github.com/sebdavid3/Cadenza/issues/155), [#169](https://github.com/sebdavid3/Cadenza/issues/169), [ADR-0022](../adr/ADR-0022-registro-de-cuentas-con-activacion.md), [ADR-0025](../adr/ADR-0025-registro-abierto-sin-aprobacion.md)): vista pública `/registro` (usuario y contraseña con su repetición, comprobación previa del patrón del nombre y de la longitud, mensajes propios para 409, 422 por campo, 429 con el tiempo de `Retry-After` y 404) que crea la cuenta, entra con ella y lleva a `/transcripcion` (si ese acceso falla, dice que la cuenta existe y enlaza a entrar); vista privada `/cuentas`, solo para investigadores, por fecha de alta, el origen de cada cuenta (registro o investigador) y activar o desactivar con `PATCH /users/{id}`. `ApiError.retryAfterSeconds` guarda el `Retry-After` de un 429; con la API en otro origen (`VITE_API_BASE_URL`) el navegador no deja leer esa cabecera, porque la API solo expone `X-Request-ID` y `X-API-Version`, y la vista cae en un «espera un rato». La landing y `/entrar` solo enlazan al registro si el build declara `VITE_REGISTRATION_ENABLED=true`, que debe coincidir con `CADENZA_REGISTRATION_ENABLED` de la API.
- **Vista de una sesión** en `/sesiones/:id` ([#153](https://github.com/sebdavid3/Cadenza/issues/153), [ADR-0021](../adr/ADR-0021-visualizacion-de-la-transcripcion-y-marcado-de-hallazgos.md)), enlazada desde el listado. La imagen original (Blob) sobre la partitura dibujada por OSMD 2.2.1 a partir del MusicXML exportado, cargado bajo demanda, y la lista de posibles errores de `GET /sessions/{id}/findings?latest_only=true&include_dismissed=true`. Cada hallazgo activo marca su compás (trama y contorno violetas); los descartados se listan aparte sin marca. Si OSMD dibuja otro número de compases que el `ScoreIR` no se marca nada y se avisa; una sesión ajena o inexistente responde 404 y la vista no distingue entre las dos. «Descargar MusicXML» ([#176](https://github.com/sebdavid3/Cadenza/issues/176)) guarda ese mismo MusicXML, sin otra petición (solo si la exportación había fallado, pulsarlo la vuelve a pedir), como `cadenza-<8 primeros caracteres del id>.musicxml` (`application/vnd.recordare.musicxml+xml`): el nombre no sale de `Content-Disposition`, que con la API en otro origen no se puede leer. La vista reproduce la partitura ([#177](https://github.com/sebdavid3/Cadenza/issues/177), [ADR-0026](../adr/ADR-0026-reproduccion-de-la-partitura-en-el-navegador.md)) con las notas de `GET /sessions/{id}/timing` y las alturas de `current_score` del mismo estado (unidas por ancla; el `event_index` cuenta los eventos de su voz en el compás), a 120 negras por minuto por defecto y sintetizada con Tone.js 15.1.22. El compás que suena se resalta con la geometría de las marcas. Tone.js se importa por sus módulos y con el reloj por `setTimeout`: el Worker desde `blob:` de su reloj por defecto lo bloquea la CSP de producción sin lanzar ninguna excepción.
- **Selección de una nota** ([#182](https://github.com/sebdavid3/Cadenza/issues/182), [ADR-0027](../adr/ADR-0027-seleccion-de-notas-sobre-la-partitura.md)): en la vista de una sesión se elige una nota o un silencio sobre la partitura dibujada y se obtiene su ancla (`AnchorPayload`), que es lo que llevarán las ediciones. El mapa ancla→caja por evento empareja cada evento de `current_score` con la figura que OSMD dibuja para él: por voz, clase, duración y altura, imitando cómo escribe el exportador los acordes (una figura), las duraciones que no caben en una figura (notas ligadas) y las nulas o cero (una negra, por music21). La caja sale del SVG (la cabeza de la nota o el glifo del silencio) y se recalcula al volver a maquetar. Si algo no cuadra no se ofrece la selección y la vista lo dice. El ancla se construye como en `GET /timing`: `event_index` cuenta los eventos de su voz en el compás. Se elige con el ratón o el dedo (la nota más cercana del compás tocado), con el teclado sobre la partitura (`role="application"`: flechas, Ctrl o ⌘ más flechas, Re Pág y Av Pág, Inicio, Fin y Esc) o con los pasos «Anterior» y «Siguiente» de 44 px, que son la alternativa táctil. Lo elegido se anuncia en una región `aria-live` cuando la selección se detiene. Se guarda en Zustand (`useSelectionStore` en `pages/session/selection.ts`) como `{ sessionId, seq, anchor }`: vale para ese estado y se olvida al salir de la sesión. Cuando la vista pasa a un estado posterior, sigue elegida con su ancla llevada a ese estado por la regla de desplazamiento de ADR-0011 §2 (`carryAnchor` en `pages/session/edits.ts`).
- **Corrección de la altura, la duración y la alteración** ([#183](https://github.com/sebdavid3/Cadenza/issues/183), [ADR-0030](../adr/ADR-0030-correccion-de-altura-duracion-y-alteracion.md)): para quien transcribió la sesión y mientras no esté finalizada, una barra «Corregir» bajo la de la selección con la altura (un paso diatónico dentro de la armadura del compás, o una octava), la alteración (de doble bemol a doble sostenido; el becuadro se envía como `"natural"`) y la figura de semifusa a redonda con puntillo; la figura de un acorde no se ofrece (D61). Con el teclado sobre la partitura: Mayús+↑/↓, Mayús+Re Pág/Av Pág, + − =, del 1 al 7 y el punto. Cada orden es un `POST /sessions/{id}/edits` con el valor final, `before: null` y el `base_seq` del estado que se ve; no hay envío optimista ni se envía otra mientras se guarda (`pages/session/editor.ts`). Tras el 201 se pide el detalle y, antes de mostrarlo, el MusicXML, los posibles errores y los tiempos de ese estado; la vista pasa a él de una vez y la partitura se redibuja sin vaciarse ni perder el foco. Un 409 recarga la sesión y distingue por el `status` recargado una sesión finalizada de una edición hecha en otra parte, conserva lo que se quería hacer y solo lo vuelve a aplicar si la persona lo pide. El 422, el 403, el 404, la red y un 201 sin estado nuevo tienen mensajes propios. Un investigador ante una sesión ajena y una sesión finalizada se ven en solo lectura.
- **Marcas de notación** ([#213](https://github.com/sebdavid3/Cadenza/issues/213), [ADR-0031](../adr/ADR-0031-marcas-de-notacion-en-el-score-ir.md)): la partitura dibuja las articulaciones, los calderones, las ligaduras de expresión (también entre pentagramas), las dinámicas y los reguladores que lleva el MusicXML exportado; la web no cambia (OSMD los dibuja con sus reglas por defecto y no añaden figuras al mapa de selección). Las correcciones de #183 los conservan. Añadirlos y quitarlos desde la vista es [#214](https://github.com/sebdavid3/Cadenza/issues/214) (abajo); que la reproducción siga las dinámicas ([#215](https://github.com/sebdavid3/Cadenza/issues/215)) queda fuera de la entrega de noviembre de 2026.
- **Varias voces** ([#218](https://github.com/sebdavid3/Cadenza/issues/218), [ADR-0032](../adr/ADR-0032-varias-voces-huecos-y-plicas.md)): cada voz de un pentagrama se dibuja con su ritmo (una voz que entra, calla o sale a mitad del compás) y con las plicas separadas; el mapa de selección (`noteMap.ts`) salta los silencios invisibles (`hidden`), que no tienen figura, y `osmd.ts` no cuenta como figura lo que OSMD no dibuja (`print-object="no"`).
- **Insertar y borrar eventos, y la clave y la armadura** ([#184](https://github.com/sebdavid3/Cadenza/issues/184), [ADR-0033](../adr/ADR-0033-insertar-borrar-clave-y-armadura.md)): la barra «Corregir» inserta una nota o un silencio antes del evento elegido (`InsertEvent` en su ancla, con su figura y, una nota, su altura o, ante un silencio, la de la línea central de la clave; ante una nota de un acorde, antes del acorde) y lo borra (`DeleteEvent`, `after: null`), también con N, S, Supr y Retroceso; la primera nota de un acorde con más notas no se borra. Cambia la clave (`SetClef`, de sol, fa, do en tercera o do en cuarta) y la armadura (`SetKey`, con un desplegable y «Cambiar») del compás del evento elegido, en su pentagrama, ancladas al primer evento del compás (ADR-0010); si es la que trae del compás anterior, envía `{"clef": null}` o `{"key_signature": null}` para quitar el cambio. Las notas conservan su altura. Tras el 201 queda elegido el evento nuevo o el que ocupa el sitio del borrado, con su ancla en el estado de la edición (`placedBy` en `useSelectionStore`); el 409 ofrece volver a aplicar la misma edición sobre el ancla llevada al estado recargado. Borrar una nota con un extremo de ligadura de expresión avisa de que la ligadura deja de dibujarse. Antes de dibujar, `osmd.ts` escribe la armadura (sin alteraciones) y la clave (de sol) de partida en el primer compás si no las tiene y otro compás sí: OSMD 2.2.1 dibujaría desde el compás 1 el primer cambio. La descarga es el MusicXML exportado tal cual.
- **Añadir y quitar marcas** ([#214](https://github.com/sebdavid3/Cadenza/issues/214), [ADR-0039](../adr/ADR-0039-anadir-y-quitar-marcas-de-notacion.md)): la barra «Corregir» pone y quita las articulaciones y el calderón del evento elegido (`SetNoteMarks` con el conjunto final; en un acorde, en su primera nota), la dinámica de su posición (`SetDynamic`, con un desplegable y «Poner» o «Quitar») y crea ligaduras de expresión y reguladores desde un inicio marcado con «Inicio» hasta el evento elegido (`SetSlur`, `SetWedge`, con el siguiente `number` libre de la parte); cada ligadura o regulador que pasa por el evento elegido tiene su botón «Quitar …», que lo quita entero. Teclas sobre la partitura: P, A, M y T (picado, acento, marcato, tenuto), C (calderón), I (inicio), L, < y > (ligadura, crescendo y diminuendo hasta el evento elegido). El 409 ofrece volver a aplicar la misma marca sobre el estado recargado (una ligadura o un regulador, entre los mismos eventos llevados a él y con otro número), y el 422 y los demás errores se dicen como en #183.
- **Deshacer y rehacer** ([#185](https://github.com/sebdavid3/Cadenza/issues/185), [ADR-0034](../adr/ADR-0034-deshacer-y-rehacer-desde-la-vista.md)): un grupo «Deshacer y rehacer» al principio de la barra «Corregir», con lo que haría cada botón o «Nada que deshacer ni rehacer.», y Ctrl+Z, Ctrl+Mayús+Z y Ctrl+Y (también con ⌘) en toda la vista, salvo en un campo de texto. Deshacer es `POST /sessions/{id}/undo` con el `base_seq` del estado que se ve (§5.3); rehacer vuelve a enviar la última edición deshecha con `POST /edits` y el `base_seq` actual, sin cambio del contrato. Qué se puede deshacer y rehacer se lee del log (`edits` de `GET /sessions/{id}`, `readLog` en `pages/session/history.ts`), con la misma pila que el servidor; una edición nueva vacía la de rehacer, también si llega de otra pestaña. El 409 recarga sin reintentar y el 422 de una edición sin estado previo tiene su mensaje. Tras deshacer o rehacer queda elegido el evento que cambia (nunca un silencio invisible). La historia de ediciones de la sesión va en la columna de los posibles errores, con lo deshecho tachado y etiquetado; `created_at` se lee en UTC aunque llegue sin zona (la API sobre SQLite no la da).
- **Posibles errores** ([#186](https://github.com/sebdavid3/Cadenza/issues/186), [ADR-0035](../adr/ADR-0035-descartar-restaurar-y-revalidar-desde-la-vista.md)): para quien transcribió la sesión y mientras no esté finalizada, cada posible error de la lista tiene «Descartar», que abre debajo un formulario con un motivo opcional y dice que descartar no corrige la partitura (`POST /sessions/{id}/findings/{finding_id}/dismiss` con `{"reason": …}`, recortado; en blanco, `null`), y los descartados tienen «Restaurar» (`.../restore`). Con varios en un compás (uno por voz, ADR-0032) se numeran, y cada botón describe el suyo con su mensaje. Nada se da por hecho sin el 200: el hallazgo devuelto sustituye al de la lista. «Revalidar» (`POST /sessions/{id}/validate`) aparece cuando la validación es de un estado anterior al que se ve o cuando no se sabe; la respuesta solo trae los activos, así que la vista vuelve a pedir la lista con los descartados, y su `current_seq` dice si el servidor validó el estado que se ve, uno posterior (se carga) o uno anterior (hay que volver a revalidar). Revalidar el mismo estado sustituye sus hallazgos con otros id: un descarte sobre un id viejo responde 404 y la vista vuelve a pedir la lista. Revalidar otro estado deja los anteriores como historia, y descartar uno de ellos responde 200: tras cada descarte o restauración la vista vuelve a pedir la lista y, si el hallazgo ya no está en ella, lo dice; si la lista es de un estado posterior al que se ve, ofrece «Recargar la sesión». Mientras se revalida, las correcciones esperan. Una revalidación solo hereda los descartes de la validación vigente. El 409 de estas rutas es la sesión finalizada. Sin posibles errores, la vista recuerda en la pestaña el `current_seq` de la última revalidación, porque `SessionDetailRead` no expone `validated_at_seq` (D64). Un investigador ante una sesión ajena las ve en solo lectura.
- **Sistema de diseño:** `PRODUCT.md`, `DESIGN.md` y los *briefs* de `.impeccable/surfaces/`; tokens en `apps/web/src/styles/tokens.css` y tipografías servidas desde el proyecto.

Arranque, con la API ya en marcha (§1.4):

```bash
cd apps/web
npm ci
npm run dev        # http://localhost:5173 ; la API queda en http://localhost:5173/api
```

Puertas del frontend: `npm run lint`, `npm run format:check`, `npm run test` y `npm run build` (también en la CI).

Queda por construir sobre la API v1, planificado en issues del milestone de la Fase 8:
- **Acceso:** el inicio de sesión ya existe ([#146](https://github.com/sebdavid3/Cadenza/issues/146), [ADR-0020](../adr/ADR-0020-sesion-del-cliente-web.md)): vista `/entrar`, token en `sessionStorage`, recuperación al recargar, cierre al vencer el `exp` o ante un 401 y rutas privadas. Queda el cambio de contraseña ([#190](https://github.com/sebdavid3/Cadenza/issues/190)); la gestión de cuentas se limita a activar y desactivar ([#155](https://github.com/sebdavid3/Cadenza/issues/155)), sin roles ni restablecer contraseñas.
- **Corrección:** sobre la nota elegida en la partitura dibujada con OSMD (la selección no depende de las coordenadas del motor OMR, porque HOMR devuelve `bbox: null`, INV-0001): las once operaciones de `EditOp` con `base_seq` y manejo del 409 (§5.1); deshacer en el servidor (`POST /undo`, §5.3); descarte, restauración y revalidación de hallazgos. La selección de una nota ([#182](https://github.com/sebdavid3/Cadenza/issues/182)) la corrección de su altura, su duración y su alteración ([#183](https://github.com/sebdavid3/Cadenza/issues/183)), insertar y borrar eventos y cambiar la clave y la armadura ([#184](https://github.com/sebdavid3/Cadenza/issues/184)) deshacer y rehacer ([#185](https://github.com/sebdavid3/Cadenza/issues/185)), añadir y quitar marcas ([#214](https://github.com/sebdavid3/Cadenza/issues/214)) y descartar, restaurar y revalidar los posibles errores ([#186](https://github.com/sebdavid3/Cadenza/issues/186)) ya existen.
- **Cierre:** finalización y reapertura ([#187](https://github.com/sebdavid3/Cadenza/issues/187)), métricas de esfuerzo (`POST /sessions/{id}/effort`, [#188](https://github.com/sebdavid3/Cadenza/issues/188)) y descarga del MIDI ([#189](https://github.com/sebdavid3/Cadenza/issues/189); la del MusicXML ya existe, [#176](https://github.com/sebdavid3/Cadenza/issues/176)).

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

- **Selección de símbolos sobre OSMD:** verificada ([#182](https://github.com/sebdavid3/Cadenza/issues/182), 2026-10-23, contra la API real con HOMR, a 1440 y 390 px). El emparejamiento está medido sobre 99 sesiones de incipits monofónicos; acordes, ligaduras, voces y varios pentagramas solo se han comprobado con partituras construidas con el exportador y con pruebas, no sobre transcripciones de HOMR ([ADR-0027](../adr/ADR-0027-seleccion-de-notas-sobre-la-partitura.md)).
- **Reproducción Tone.js:** el transporte y el compás que suena están verificados en el navegador ([#177](https://github.com/sebdavid3/Cadenza/issues/177), 2026-10-23, contra la API real con HOMR y con la CSP de producción); el sonido no lo ha escuchado nadie (un navegador sin interfaz no oye) y queda por comprobar a mano, también en móvil.

---

## 8. Mantenimiento y Regeneración del Contrato

Si se realizan cambios en los modelos Pydantic o endpoints del backend:

```powershell
# Regenerar openapi.json y apps/web/src/types.ts
uv run --no-sync python scripts/generate_openapi_and_types.py

# Verificar que los tests del contrato pasen al 100%
uv run --no-sync pytest apps/api/tests/test_openapi_contract.py
```
