# Entrega del Contrato API v1 al Diseño del Frontend (Frontend Handoff)

> **Versión de Contrato:** `1.0.0`  
> **Especificación OpenAPI:** [`docs/api/openapi.json`](./openapi.json)  
> **Tipos TypeScript del Cliente:** [`apps/web/src/types.ts`](../../apps/web/src/types.ts)  
> **Alineación Arquitectural:** [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) v1.2, ADR-0004, ADR-0007, ADR-0010, ADR-0011, ADR-0012, ADR-0013, ADR-0014.

---

## 1. Propósito y Alcance

Este documento formaliza la entrega del contrato de API v1 de Cadenza como base estable y congelada para el desarrollo y diseño integral de la interfaz de usuario frontend (`apps/web`).

El contrato está completamente especificado mediante OpenAPI 3.1, verificado en CI contra deriva de código y sincronizado automáticamente con tipos TypeScript fuertemente tipados.

---

## 2. Capacidades Funcionales del Backend

La API de Cadenza proporciona el ciclo de vida completo de digitalización y corrección musical asistida:

| Módulo / Capacidad | Endpoints Principales | Descripción |
| :--- | :--- | :--- |
| **Autenticación y Cuentas** | `POST /auth/login`<br>`GET /auth/me`<br>`POST /auth/password`<br>`GET/POST/PATCH /users` | Autenticación OAuth2 Bearer JWT. Control de roles (ADR-0012): `transcriptor` (edita sus sesiones) e `investigador` (administra usuarios y audita métricas). |
| **Transcripción OMR** | `POST /transcribe` | Ingesta asíncrona de imágenes (PNG/JPEG), inferencia simbólica OMR (`HOMR` o `Fake`), validación inicial y creación de sesión en estado `transcribed`. |
| **Consultas de Sesión** | `GET /sessions`<br>`GET /sessions/{id}`<br>`GET /sessions/{id}/image`<br>`GET /sessions/{id}/export` | Listado ligero paginado (sin JSONB pesado). Consulta completa con estado materializado (`current_score`, `current_seq`, `anchor_index`). Descarga de imagen de origen. Exportación a MusicXML 4.0 y MIDI 1.0. |
| **Edición Humana (HITL)** | `POST /sessions/{id}/edits`<br>`POST /sessions/{id}/undo` | Registro append-only inmutable de ediciones con verificación de concurrencia optimista (`base_seq`). Operaciones atómicas tipadas (`EditOp`). Deshacer en el servidor como evento compensatorio inverso (ADR-0007, #35). |
| **Validación y Hallazgos** | `GET /sessions/{id}/findings`<br>`POST /sessions/{id}/validate`<br>`POST /sessions/{id}/findings/{id}/dismiss`<br>`POST /sessions/{id}/findings/{id}/restore` | Evaluación determinista de reglas sobre `current_score`. Filtro de hallazgos activos vs descartados. Preservación de falsos positivos descartados si su evento no fue modificado (#36). |
| **Ciclo de Vida** | `POST /sessions/{id}/finalize`<br>`POST /sessions/{id}/reopen` | Cierre formal de sesión tras corrección (rechaza ediciones con `409 SessionClosed`). Reapertura permitida bajo auditoría (ADR-0014, #34). |
| **Métricas de Esfuerzo** | `POST /sessions/{id}/effort`<br>`GET /sessions/{id}/effort` | Persistencia de telemetría editorial: duración total, latencia hasta la primera corrección e intervenciones distribuidas por compás (ADR-0012, #13). |
| **Sistema y Metadatos** | `GET /version` | Metadatos del contrato (`1.0.0`). Todas las respuestas inyectan la cabecera HTTP `X-API-Version: 1.0.0`. |

---

## 3. Modelo de Datos y Representación Simbólica

### 3.1. `ScoreDocument` vs `ScoreIR` Materializado

1. **`ScoreDocument` (Crudo OMR, Inmutable):**
   - Contiene el árbol `ScoreIR` reconocido originalmente por el motor OMR.
   - Contiene `anchors` (`AnchorIndex`): asignación de cada evento musical a su ancla lógica y espacial en la imagen de origen.
   - Contiene `provenance`: motor OMR, hashes SHA-256 de imagen, marcas temporales y versiones de catálogo de reglas.
2. **`current_score` (`ScoreIR` Materializado en `current_seq`):**
   - Producido al aplicar en orden el registro append-only de ediciones (`edits`) sobre el árbol crudo.
   - Representa el estado presente de la música editada por el transcriptor.
3. **`anchor_index` (Índice de Anclas Actual):**
   - Mantiene la correspondencia posicional de eventos en el estado `current_seq`, heredando las cajas delimitadoras (`bbox`) y confianzas originales.

### 3.2. Estructura de un Ancla (`Anchor`)

El ancla es la clave lógica del modelo HITL (ADR-0011):

```typescript
export interface Anchor {
  part: number;          // Índice de parte instrumental (0-indexed)
  staff: number;         // Índice de pentagrama (0-indexed)
  measure: number;       // Número de compás (1-indexed)
  voice: number;         // Voz musical dentro del pentagrama (0-indexed)
  event_index: number;   // Posición secuencial del evento en su voz/compás
  staff_id: string;      // Identificador del pentagrama (ej. 'part-0-staff-0')
  bbox: [number, number, number, number] | null; // [x, y, ancho, alto] normalizado
  confidence: number | null; // Puntuación de certeza OMR [0.0 - 1.0]
}
```

### 3.3. Operaciones de Edición (`EditOp`)

Las operaciones admitidas en `POST /sessions/{id}/edits` son estrictamente atómicas:

- `SetPitch`: Modifica altura absoluta (`after: { pitch: "C4" }`).
- `SetDuration`: Modifica valor rítmico en beats (`after: { duration_beats: "1/4" }`).
- `SetAccidental`: Altera alteración conservando la nota (`after: { accidental: "#" }`).
- `InsertEvent`: Inserta nota/silencio antes de la posición anclada.
- `DeleteEvent`: Elimina el evento anclado.
- `SetClef`: Cambia la clave musical del compás (`after: { sign: "G", line: 2 }`).
- `SetKey`: Cambia la armadura de clave (`after: { fifths: 1 }`).

---

## 4. Guía de Integración para el Frontend

### 4.1. Concurrencia Optimista con `base_seq`

Al enviar una edición (`POST /sessions/{id}/edits`):
1. El cliente envía `base_seq = current_seq` que tiene en su store local.
2. Si otro cliente editó mientras tanto, el servidor responde con `409 Conflict` (`SequenceConflict`).
3. El frontend debe recargar la sesión (`GET /sessions/{id}`) y notificar al usuario para resolver el conflicto sin pérdida silenciosa de datos.

### 4.2. Deshacer en el Servidor (`POST /sessions/{id}/undo`)

El frontend no debe implementar deshacer destructivo localmente para persistir en backend.
El backend gestiona undo append-only:
- `POST /sessions/{id}/undo` calcula automáticamente la edición inversa compensatoria, avanza `current_seq = current_seq + 1` y devuelve el `current_score` y `anchor_index` listos para ser repintados.

### 4.3. Renderizado y Navegación

1. **Lienzo de Partitura:** Se recomienda renderizar la partitura materializada usando OSMD (OpenSheetMusicDisplay) o Verovio alimentado desde `GET /sessions/{id}/export?format=musicxml` o procesando el `ScoreIR` tipado.
2. **Superposición de Imagen:** La imagen se obtiene en `GET /sessions/{id}/image`. Las coordenadas `bbox` de las anclas permiten dibujar overlays de resaltado sincronizados cuando el usuario selecciona un compás o nota.
3. **Panel de Hallazgos:** La lista de hallazgos devuelta por `GET /sessions/{id}/findings` señala anclas específicas. Al hacer clic en un hallazgo, el frontend puede enfocar la nota tanto en la partitura renderizada como en el recuadro de la imagen de origen.

---

## 5. Mantenimiento y Regeneración del Contrato

Si se realizan cambios en los modelos Pydantic o endpoints del backend:

```powershell
# Regenerar openapi.json y apps/web/src/types.ts
uv run python scripts/generate_openapi_and_types.py

# Verificar que los tests del contrato y frontend pasen al 100%
uv run pytest apps/api/tests/test_openapi_contract.py
npm --prefix apps/web test
npm --prefix apps/web run build
```
