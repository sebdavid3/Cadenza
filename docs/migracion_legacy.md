# Plan de migración y paridad para el retiro del prototipo legacy

- **Estado:** Aprobado / En vigencia
- **Fecha:** 2026-10-08
- **Relacionado:** [ADR-0001](adr/ADR-0001-monolito-modular-hexagonal.md), [ADR-0006](adr/ADR-0006-render-editor-osmd-verovio-zustand.md), [ADR-0015](adr/ADR-0015-operacion-y-despliegue-del-backend.md), [PROJECT_STATE.md](PROJECT_STATE.md) (principio rector)
- **Issue asociado:** [#41](https://github.com/sebdavid3/Cadenza/issues/41) (Deuda técnica D45)
- **Etiqueta Git de preservación:** `archive/legacy-mvp`

---

## 1. Contexto y principio rector

El proyecto Cadenza inició con un prototipo funcional de prueba de concepto (*MVP*) almacenado en el directorio `legacy/`:
- `legacy/backend/`: API monolítica en FastAPI que invocaba el script de inferencia de HOMR directamente mediante subprocesos o ejecución local de PyTorch.
- `legacy/frontend/`: Interfaz web interactiva en React, Vite, Tailwind CSS, OpenSheetMusicDisplay (OSMD) para renderizado de partituras MusicXML y Tone.js para síntesis y reproducción de audio.
- `legacy/docker-compose*.yml` y `legacy/scripts/`: Entornos de ejecución en contenedores Docker con y sin soporte GPU NVIDIA.

El **principio rector no destructivo** consagrado en `docs/PROJECT_STATE.md` (§2) estipuló que:
> 1. El prototipo en `legacy/` permanece operativo en todo momento.
> 2. Cada fase construye el nuevo componente en paralelo y solo se integra al prototipo cuando su *Definition of Done* está verificado.
> 3. Ninguna tarea rompe el flujo E2E existente sin una tarea de migración explícita.

Habiéndose completado al 100% la **Fase 7 (Alineación con la Arquitectura Objetivo)**, el backend, el dominio simbólico, la persistencia relacional, la validación musical por reglas, el plano offline de Active Learning y la infraestructura operativa se han construido y verificado en la nueva arquitectura hexagonal.

Este documento establece la **matriz de paridad de capacidades**, formaliza el **criterio de paridad acordado** y traza la **hoja de ruta de retiro definitivo** de `legacy/`.

---

## 2. Matriz exhaustiva de paridad de capacidades

| Área / Capacidad | Implementación en `legacy/` | Equivalente en la nueva arquitectura | Estado de paridad |
|---|---|---|---|
| **Arquitectura de software** | Monolito plano no estructurado (`legacy/backend/main.py`), lógica de negocio acoplada a HTTP. | Monolito modular hexagonal: `packages/domain`, `packages/application`, `packages/persistence`, `packages/omr`, `packages/validation`, `packages/interchange`, `packages/learning`, `apps/api`, `apps/web`. | **Superada ampliamente** |
| **Representación musical** | Manejo efímero de MusicXML crudo como cadenas XML en memoria o disco. | `ScoreDocument` inmutable con `ScoreIR`, `AnchorIndex` determinista, soporte de polifonía/piano (`is_chord`, voces), metadatos de compás y conversión bidireccional sin pérdida con `music21` (`packages/interchange`). | **Superada ampliamente** |
| **Motor OMR online** | Invocación monolítica acoplada a HOMR con decodificación voraz sin abstracción de interfaz. | Puerto desacoplado `OMREngine` con adaptadores in-process `HOMREngine` (ONNX Runtime CPU/GPU), línea base `OemerEngine` y `FakeOMREngine` para pruebas, preprocesado configurable (`exp_07`) e inferencia no bloqueante con `asyncio.to_thread` (ADR-0016). | **Superada ampliamente** |
| **Persistencia y datos** | Almacenamiento volátil en disco local sin base de datos ni control de transacciones. | PostgreSQL 16 con tipos nativos JSONB y fallback SQLite, 11 migraciones versionadas con Alembic, tablas `sessions`, `edit_events`, `findings`, `effort_metrics`, `users`, y `ArtifactStore` direccionado por SHA-256. | **Superada ampliamente** |
| **Validación musical** | Inexistente (el usuario debía identificar errores manualmente a simple vista). | Motor de reglas formal `ValidationEngine` con 5 familias de reglas musicales (ritmo, tesitura, alteraciones, ligaduras, polifonía), precisión 64.52% y recall 39.80% evaluados sobre PrIMuS (`exp_06`), revalidación bajo demanda (ADR-0013) y descarte de falsos positivos (#36). | **Capacidad nueva inexistente en legacy** |
| **Auditoría HITL y Edición** | Ediciones directas sobre el XML sin trazabilidad histórica. | Log inmutable de correcciones humanas `EditEvent` con anclas estables (ADR-0007, ADR-0011), operaciones inversas de deshacer en servidor (`POST /sessions/{id}/undo`), control de concurrencia optimista (`base_seq`) y estados de sesión (`transcribed`, `correcting`, `finalized`, `failed`). | **Capacidad nueva inexistente en legacy** |
| **Métricas de esfuerzo** | Sin telemetría de esfuerzo ni evaluación científica. | Registro continuo de tiempo por compás, conteo de correcciones, protocolo metodológico formalizado (`docs/experimentos/protocolo_medicion_esfuerzo.md`), diseño intrasujeto con Cuadrado Latino 2x2, NASA-TLX y exportación tabular reproducible (`exp_10_effort_study.py`). | **Capacidad nueva inexistente en legacy** |
| **Plano Offline / ML** | Scripts aislados sin integración ni reproducibilidad. | Plano offline desacoplado (ADR-0003, ADR-0008): `DatasetBuilder` conectado a BD, selector de muestras por densidad de error e incertidumbre, `PyTorchTrainer` con exportación ONNX, `ModelRegistry` persistente, CLI `cadenza-ml` (`python -m ml`) y suite de experimentos `exp_01` a `exp_11`. | **Capacidad nueva inexistente en legacy** |
| **Seguridad y Operación** | Sin autenticación, CORS abierto, sin sondas de salud. | Autenticación JWT con hashing Argon2id (ADR-0012), propiedad estricta de sesiones, sondeo de salud `GET /health` (base de datos y `ArtifactStore`), trazabilidad con `X-Request-ID`, CORS configurable, límite de intentos de login (HTTP 429) y scripts de backup atómico (ADR-0015). | **Superada ampliamente** |
| **Entorno Docker / CUDA** | `legacy/docker-compose.yml` y `legacy/docker-compose.cpu.yml`. | `Dockerfile` multistage de producción, `Dockerfile.ml-cuda` optimizado para GPU NVIDIA (CUDA 12.8), orquestación formal con `docker-compose.yml` (`api`, `postgres`, perfil `batch` para `ml-batch`). | **Superada ampliamente** |
| **Frontend - Autenticación y Flujo** | Sin soporte de usuarios. | `apps/web`: `LoginPanel.tsx` (JWT en `sessionStorage`), gestión de sesión con React Query y Zustand, manejo de expiración de token y deslogueo reactivo. | **Superada ampliamente** |
| **Frontend - Carga e Inspección** | Subida básica de imagen (`DropZone.jsx`). | `apps/web`: `UploadPanel.tsx` integrado con la API tipada v1, `ImageOverlay.tsx` con cajas delimitadoras de pentagramas y notas, `FindingsPanel.tsx`, `EventInspector.tsx`, `HistoryPanel.tsx`, `EffortMetrics.tsx`. | **Superada ampliamente** |
| **Frontend - Renderizado OSMD** | `ScoreViewer.jsx` (renderizado interactivo SVG de MusicXML mediante OpenSheetMusicDisplay 1.8.8). | Pendiente de migración a `apps/web/src/components/ScoreViewer.tsx` (Fase 8, Deuda D11). | **Pendiente en nueva arquitectura** |
| **Frontend - Reproducción de Audio** | `AudioPlayer.jsx` (síntesis y reproducción interactiva mediante Tone.js y `@tonejs/midi`). | Endpoint backend implementado (`GET /sessions/{id}/timing`, ADR-0012, Issue #42). Pendiente de integración con sintetizador en `apps/web/src/components/AudioPlayer.tsx` (Fase 8, Deuda D11/D12). | **Pendiente en nueva arquitectura** |

---

## 3. Criterio formal de paridad para el retiro

Se acuerda el siguiente criterio técnico para autorizar la eliminación física del directorio `legacy/`:

### Criterio de Paridad (Definition of Parity)
1. **Backend, Infraestructura y ML:** Paridad superada al 100% (verificada y consolidada en las Fases 0 a 7).
2. **Frontend Interactivo:** La eliminación física de `legacy/` procederá en el marco de la **Fase 8 (Frontend / UI Avanzada)** una vez que se verifiquen los siguientes dos requisitos en `apps/web`:
   - **Renderizado de partitura:** Integración de OpenSheetMusicDisplay (OSMD) o Verovio en `apps/web` (según [ADR-0006](adr/ADR-0006-render-editor-osmd-verovio-zustand.md)) para proyectar interactivamente el MusicXML materializado de la sesión.
   - **Reproducción sincronizada:** Integración de sintetizador Web Audio / Tone.js en `apps/web` consumiendo el mapa temporal provisto por `GET /sessions/{id}/timing`.

---

## 4. Política de preservación y archivo histórico

Para garantizar que el código original del prototipo MVP nunca se extravíe y permanezca accesible de manera inmutable frente al jurado de tesis o para fines de auditoría histórica:

1. **Etiqueta Git permanente:** Se ha creado y fijado la etiqueta git:
   ```bash
   git tag archive/legacy-mvp
   ```
   Cualquier evaluador o desarrollador puede consultar o ejecutar el prototipo MVP en su estado histórico original mediante:
   ```bash
   git checkout archive/legacy-mvp
   ```
2. **Estado de `legacy/` en el árbol de trabajo actual:**
   - Se marca como **DEPRECADO (CONGELADO)**.
   - Se incluye un archivo `legacy/README.md` que alerta sobre su obsolescencia y remite a la documentación oficial.
   - Ningún nuevo desarrollo debe realizarse dentro de `legacy/`.

---

## 5. Procedimiento paso a paso para la eliminación física (Fase 8)

Cuando los criterios de paridad de la Fase 8 se cumplan satisfactoriamente, el procedimiento de retiro definitivo constará de los siguientes pasos atómicos:

1. **Eliminar el directorio legacy:**
   ```bash
   git rm -rf legacy
   ```
2. **Actualizar configuración de herramientas (`pyproject.toml`):**
   - Remover `legacy` de `tool.ruff.lint.extend-exclude`.
   - Remover `legacy` de `tool.black.extend-exclude` y `tool.black.exclude`.
3. **Actualizar `.gitignore`:**
   - Remover las líneas `legacy/frontend/node_modules/`, `legacy/frontend/dist/`, `legacy/frontend/dist-ssr/`.
4. **Actualizar `README.md`:**
   - Sustituir la sección *Prototipo legacy (referencia)* por una mención histórica breve enlazando a la etiqueta `archive/legacy-mvp`.
5. **Verificar Quality Gates:**
   - Ejecutar la suite completa de pruebas y linters (`pytest`, `mypy`, `ruff`, `black`, `vitest`).
6. **Commit y cierre:**
   - Registrar el commit convencional `chore(repo): eliminar directorio legacy tras paridad total en Fase 8`.
