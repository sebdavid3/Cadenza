# PROJECT STATE — Cadenza

> **Documento vivo.** Es la memoria compartida del proyecto y el único mapa
> maestro de navegación. **Toda tarea futura termina actualizando este archivo.**
> No se crea un índice paralelo; este documento es la fuente de verdad del estado.

| Campo | Valor |
|---|---|
| **Fase actual** | Fase 7 — Alineación con la Arquitectura Objetivo — **en ejecución** (Etapa 1 finalizada, investigaciones #14 y #31 a continuación) |
| **Último hito completado** | `ArtifactStore` direccionado por sha256 ([#4](https://github.com/sebdavid3/Cadenza/issues/4)): puerto `ArtifactStore` e `InMemoryArtifactStore` en `packages/application`, adaptador `FilesystemArtifactStore` (`sha256/ab/cd/<hash>`) y tabla `artifacts` con migración `0003` en `packages/persistence`; 128 tests verdes |
| **Próximo paso inmediato** | Investigaciones conjuntas #14 y #31 (salidas internas de HOMR: bbox y confianza) antes de iniciar la Etapa 2 |
| **Rama activa** | `dev` |
| **Deuda técnica / Blockers activos** | D1–D6, D8, D10–D14, D16–D19, D21, D25–D30, D32–D42, D44–D47 (D4 mitigada; D23 y D31 parciales; D7, D9, D15, D20, D22 y D24 resueltas; D43 cerrada como fuera de alcance) |
| **Guía de estilo / calidad** | [`docs/CONVENTIONS.md`](CONVENTIONS.md) y [`CLAUDE.md`](../CLAUDE.md) — **contrato oficial** de Git, commits y calidad de código |
| **Fecha de actualización** | 2026-10-07 |

---

## Principio rector (no destructivo)

El repositorio contiene un **prototipo funcional E2E** (FastAPI + HOMR + Docker
CUDA + visor OSMD + Tone.js). El objetivo de las fases siguientes es
**refactorizarlo progresivamente** hacia la arquitectura hexagonal de
[`docs/ARCHITECTURE.md`](ARCHITECTURE.md), **no reescribirlo desde cero**.

Reglas:

1. El prototipo en `legacy/` (`legacy/backend`, `legacy/frontend`,
   `legacy/docker-compose*`, `legacy/scripts`) permanece **operativo** en todo momento.
2. Cada fase construye el nuevo componente **en paralelo** y solo se integra al
   prototipo cuando su *Definition of Done* está verificado.
3. Ninguna tarea rompe el flujo E2E existente sin una tarea de migración explícita.

---

## Estado por módulo

| Módulo | Componente | Fase objetivo | Estado actual |
|---|---|---|---|
| — | Arquitectura + ADRs | Fase 0 | Completado |
| **Dominio** | `packages/domain` (ScoreDocument, Anchor, EditEvent, TimeSignature) | Fase 0 | Completado |
| **M1** | `OMREngine` (HOMR/ONNX + oemer baseline) | Fase 1 | Completado (núcleo: Fake + HOMR); pendiente Oemer/preproc/device/bbox (D1–D4) |
| **M2** | Motor de validación por reglas | Fase 2 | Completado (núcleo: motor + balance); pendiente catálogo/métricas (D6, D8) |
| **M3-A** | API Gateway + persistencia (`apps/api`, `packages/persistence`) | Fase 3A | Completado (núcleo: 4 endpoints, SQLAlchemy/JSONB, E2E SQLite); pendiente Postgres real/auth (D10) |
| **M3** | Interfaz HITL (editor + eventos) | Fase 3B | Completado (núcleo: imagen + overlays `bbox`, `SetPitch` inmutable, undo/redo, métricas); pendiente OSMD/Tone.js (D11, D12) |
| **M4** | Active Learning + Model Registry | Fase 4 | Completado (núcleo: `DatasetBuilder`, 3 estrategias, `ModelRegistry`, `FakeTrainer`); pendiente trainer real/ONNX/musicdiff (D14–D16) |
| **M5** | Framework de Experimentos (`ml/experiments/`, `results/`) | Fase 5 | Completado (núcleo: `exp_01_effort` y `exp_02_active_learning` deterministas); pendiente corpus real + integración con persistencia (D17, D18) |
| **M6** | Validación empírica (`packages/interchange`, OMR-NED, corpus) | Fase 6 | Completado (núcleo: puente canónico, OMR-NED oficial, línea base HOMR sobre PrIMuS en CPU y GPU); pendiente AL sobre errores reales (D21) |
| — | Alineación con la arquitectura objetivo (aplicación, datos, API, plano offline) | Fase 7 | Planificado: 42 issues en el milestone, 4 con alcance por decidir y 1 de adaptación del visor web de la fase ([`phases/phase_7_architecture_alignment/`](phases/phase_7_architecture_alignment/README.md)) |

---

## Deuda técnica / Blockers

| ID | Descripción | Impacto | Estado |
|---|---|---|---|
| D1 | `OemerEngine` (línea base OMR para comparación experimental) no implementado | Fase 1 / M1 | Pendiente (sub-tarea) |
| D2 | Preprocesado configurable (deskew, binarización, control de DPI) no implementado | Fase 1 / M1 | Pendiente (sub-tarea) |
| D3 | Reporte del dispositivo efectivo desde `onnxruntime.get_available_providers()` no expuesto | Fase 1 / M1 | Pendiente (sub-tarea) |
| D4 | Anclas sin `bbox` real: mitigado con rectángulos sintéticos en `FakeOMREngine`; el OMR real sigue sin coordenadas | Fase 1 / M3 | **Mitigada (parcial)** — desbloquea overlays de 3B; bbox real pendiente |
| D5 | `HOMREngine` no verificado E2E (requiere extra `homr` + GPU/pesos); validado por gating de import y mapper | Fase 1 | Pendiente (entorno) |
| D6 | Catálogo de reglas incompleto: faltan armadura/alteraciones, colisiones de voz, rango y cierres | Fase 2 / M2 | Pendiente (sub-tarea) |
| D7 | Persistencia de `Finding`/`EditEvent` en PostgreSQL/JSONB no implementada | Fase 2 / M2 | **Resuelta** — `packages/persistence` (modelos + Alembic) y persistencia en `POST /transcribe` y `POST /sessions/{id}/edits` |
| D8 | Métricas de precisión/recall del validador sobre casos conocidos no reportadas | Fase 2 / M2 | Pendiente (sub-tarea) |
| D9 | Frontera canónica MusicXML↔`ScoreIR` con `music21` no implementada (sigue el puente `xml.etree` de Fase 1) | Fase 2 | **Resuelta** — `packages/interchange` (`musicxml_to_score_ir`/`read_score`/`score_ir_to_musicxml`); el parser `xml.etree` se retiró |
| D10 | Persistencia verificada solo en SQLite en memoria: sin migración aplicada ni tests contra PostgreSQL real; API sin autenticación | Fase 3A | Pendiente — PostgreSQL en la Fase 7; autenticación decidida (ADR-0012) y planificada en la Fase 7 |
| D11 | Renderizado de notación con OSMD no implementado: bloqueado por el exportador `ScoreIR`→MusicXML (paquete `export`) y por la instrumentación `Anchor→SVG` (ADR-0006) | Fase 3B / M3 | Pendiente (sub-tarea) |
| D12 | Reproducción con Tone.js y cursor sincronizado (mapa tiempo→ancla) no implementada | Fase 3B / M3 | Pendiente (sub-tarea) |
| D13 | Métricas de esfuerzo calculadas solo en el cliente; no se persisten en la base de datos | Fase 3B / M4 | Pendiente (sub-tarea) |
| D14 | `Trainer` real no implementado: solo `FakeTrainer` determinista; falta PyTorch + pipeline de HOMR + export ONNX (requiere GPU y pesos) | Fase 4 / M4 | Pendiente (entorno) |
| D15 | OMR-NED con `musicdiff` no integrada: `normalized_edit_distance` es un proxy propio sobre secuencias de símbolos | Fase 4 / M4 | **Resuelta** — `cadenza.learning.omr_ned_pair`/`omr_ned_batch` (extra `metrics`, musicdiff 5.2); el proxy se conserva como fallback |
| D16 | Sin orquestación CLI del job de *fine-tuning* ni `DatasetBuilder` acoplado a persistencia (`EditEvents`/imágenes); `configs/` solo tiene la config base | Fase 4 / M4 | Pendiente (sub-tarea) |
| D17 | Experimento 1 usa un documento sintético; falta correrlo sobre un corpus/partituras reales con OMR para reclamar validez externa | Fase 5 / M5 | Pendiente (sub-tarea) |
| D18 | Experimento 2 depende del `DatasetBuilder`, no de la persistencia: el pool histórico aún no se extrae de sesiones reales (`EditEvents` en BD) | Fase 5 / M5 | Pendiente (sub-tarea) |
| D19 | Reducción de esfuerzo medida en `ml/experiments` no usa los eventos HITL reales ni `musicdiff` para OMR-NED | Fase 5 / M5 | **Parcial** — OMR-NED oficial integrado (`exp_03`); falta correrlo sobre corpus real (D20) |
| D20 | HOMR real no ejecutado en GPU | Fase 6 / M6 | **Resuelta** — GPU operativa con `onnxruntime-gpu==1.26.0` (CUDA 12.8 + cuDNN 9 cu12) y `ensure_cuda_dll_dirs` (PATH de sub-librerías cuDNN). Baseline PrIMuS 91/100, **OMR-NED medio 0.2285** idéntico CPU↔GPU, 9 fallos `No staffs found` |
| D21 | Experimento de AL sobre distribuciones de error reales (derivar `EditEvent`s del diff HOMR↔GT) sin diseñar | Fase 6 / M6 | Pendiente (sub-tarea) |
| D23 | `ScoreIR` sin clave, armadura ni ligaduras; `SetClef`/`SetKey` no proyectables y `SetAccidental` equivale a `SetPitch` (ADR-0010) | Fase 7 / Dominio | **Parcial** — `ScoreIR` con clave, armadura y ligaduras (`Clef`, `KeySignature`, `Tie`) y round-trip en `packages/interchange` implementados ([#2](https://github.com/sebdavid3/Cadenza/issues/2)); proyección de operaciones pendiente ([#3](https://github.com/sebdavid3/Cadenza/issues/3)) |
| D24 | `ArtifactStore` no implementado: la imagen subida se descarta al terminar `/transcribe` | Fase 7 / M3 | **Resuelta** — puerto `ArtifactStore` e `InMemoryArtifactStore` en `packages/application`, `FilesystemArtifactStore` (`data/artifacts/sha256/ab/cd/<hash>`) y tabla `artifacts` con migración `0003` en `packages/persistence` ([#4](https://github.com/sebdavid3/Cadenza/issues/4)) |
| D25 | Esquema relacional incompleto frente a `ARCHITECTURE.md` §7.2 (`sessions` sin imagen ni versión de modelo, `findings` sin `at_seq`, sin `artifacts`/`effort_metrics`/`model_versions`) | Fase 7 | Pendiente |
| D26 | La API usa siempre `FakeOMREngine`: el motor real no está conectado al plano online | Fase 7 / M1 | Pendiente |
| D27 | `POST /sessions/{id}/edits` no valida la edición: una edición no proyectable anula `current_score` de forma permanente | Fase 7 / M3 | Pendiente |
| D28 | Los hallazgos se calculan solo al transcribir; no hay revalidación tras las correcciones | Fase 7 / M2 | Pendiente |
| D29 | Sin exportación MIDI ni endpoint de exportación (solo `score_ir_to_musicxml`) | Fase 7 | Pendiente |
| D30 | `ModelRegistry` solo en memoria; el plano online no consulta la versión activa | Fase 7 / M4 | Pendiente |
| D31 | Sin integración continua ni contrato OpenAPI congelado (tipos del frontend escritos a mano) | Fase 7 | **Parcial** — CI operativa en GitHub Actions (`.github/workflows/ci.yml`, [#25](https://github.com/sebdavid3/Cadenza/issues/25)); contrato OpenAPI pendiente ([#26](https://github.com/sebdavid3/Cadenza/issues/26)) |
| D32 | Sin listado de sesiones: `GET /sessions` no existe y una sesión solo se recupera conociendo su `id` | Fase 7 / M3 | Pendiente |
| D33 | Semántica de las anclas frente a `InsertEvent`/`DeleteEvent` (riesgo señalado en ADR-0007) | Fase 7 / Dominio | **Decidida** (ADR-0011: ancla posicional relativa a un estado + `origin_anchor`); implementación pendiente |
| D34 | Evaluación solo sobre PrIMuS: SMB y MUSCIMA++, prometidos en la documentación y en el objetivo 1, sin evaluar | Fase 7 / M6 | Pendiente |
| D35 | SER no calculada sobre datos reales: falta la serialización de `ScoreIR` a secuencia de símbolos (objetivo 5) | Fase 7 / M4 | Pendiente |
| D36 | `HOMREngine` no extrae confianza del modelo: la estrategia de incertidumbre usa la densidad de errores del validador | Fase 7 / M1, M4 | Pendiente |
| D37 | Piano simple (dos pentagramas) sin verificar: pruebas, *fixtures* y corpus son monofónicos | Fase 7 / Dominio | Pendiente |
| D38 | Sin protocolo de estudio de esfuerzo: las sesiones no registran participante ni condición (asistida / no asistida) | Fase 7 / M3 | Pendiente |
| D39 | Ciclo de vida de la sesión sin definir: no se puede marcar una corrección como finalizada | Fase 7 / M3 | Pendiente |
| D40 | Deshacer solo en el navegador: no se registra el evento inverso que exige ADR-0007 y el log diverge del editor | Fase 7 / M3 | Pendiente |
| D41 | Los hallazgos no se pueden descartar como falsos positivos | Fase 7 / M2 | Pendiente |
| D42 | `POST /transcribe` es síncrono; sin consulta de estado para transcripciones largas | Alcance por decidir | Pendiente (decisión) |
| D43 | Entrada PDF y multipágina mencionada en `ARCHITECTURE.md` pero sin modelo de página en anclas ni `bbox` | — | **Cerrada** — fuera de alcance: una imagen por sesión; PDF retirado de `ARCHITECTURE.md` |
| D44 | Operación del backend sin resolver: salud, registro estructurado, CORS, imagen CUDA del plano offline y copias | Alcance por decidir | Pendiente (decisión) |
| D45 | Sin tarea de migración para retirar `legacy/`, que el principio rector exige antes de eliminarlo | Alcance por decidir | Pendiente (decisión) |
| D46 | La API no expone el estado actual de la sesión (`seq` e índice de anclas) y las ediciones no declaran el estado sobre el que se construyeron (`base_seq`, ADR-0011) | Fase 7 / M3 | Pendiente |
| D47 | El visor web no tiene inicio de sesión ni envía token: dejará de funcionar cuando la API exija autenticación (ADR-0012) | Frontend | Pendiente |

*(Se agregan filas aquí a medida que surgen. Las resueltas se conservan marcadas para trazabilidad.)*

### Deuda ↔ issues de la Fase 7

| Deuda | Issue | Deuda | Issue |
|---|---|---|---|
| D1 | [#16](https://github.com/sebdavid3/Cadenza/issues/16) | D19 | [#24](https://github.com/sebdavid3/Cadenza/issues/24) |
| D2 | [#15](https://github.com/sebdavid3/Cadenza/issues/15) | D21 | [#20](https://github.com/sebdavid3/Cadenza/issues/20) |
| D3, D5 | [#8](https://github.com/sebdavid3/Cadenza/issues/8) | D22 | [#7](https://github.com/sebdavid3/Cadenza/issues/7) |
| D4 | [#14](https://github.com/sebdavid3/Cadenza/issues/14) | D23 | [#2](https://github.com/sebdavid3/Cadenza/issues/2), [#3](https://github.com/sebdavid3/Cadenza/issues/3) |
| D6 | [#17](https://github.com/sebdavid3/Cadenza/issues/17) | D24 | [#4](https://github.com/sebdavid3/Cadenza/issues/4), [#9](https://github.com/sebdavid3/Cadenza/issues/9) |
| D8 | [#18](https://github.com/sebdavid3/Cadenza/issues/18) | D25 | [#5](https://github.com/sebdavid3/Cadenza/issues/5), [#13](https://github.com/sebdavid3/Cadenza/issues/13), [#21](https://github.com/sebdavid3/Cadenza/issues/21) |
| D10 | [#6](https://github.com/sebdavid3/Cadenza/issues/6) | D26 | [#8](https://github.com/sebdavid3/Cadenza/issues/8) |
| D11 (backend) | [#12](https://github.com/sebdavid3/Cadenza/issues/12) | D27 | [#10](https://github.com/sebdavid3/Cadenza/issues/10) |
| D13 | [#13](https://github.com/sebdavid3/Cadenza/issues/13) | D28 | [#11](https://github.com/sebdavid3/Cadenza/issues/11) |
| D14 | [#23](https://github.com/sebdavid3/Cadenza/issues/23) | D29 | [#12](https://github.com/sebdavid3/Cadenza/issues/12) |
| D16 | [#19](https://github.com/sebdavid3/Cadenza/issues/19), [#22](https://github.com/sebdavid3/Cadenza/issues/22) | D30 | [#21](https://github.com/sebdavid3/Cadenza/issues/21) |
| D17 | [#24](https://github.com/sebdavid3/Cadenza/issues/24) | D31 | [#25](https://github.com/sebdavid3/Cadenza/issues/25), [#26](https://github.com/sebdavid3/Cadenza/issues/26) |
| D18 | [#19](https://github.com/sebdavid3/Cadenza/issues/19) | D32 | [#27](https://github.com/sebdavid3/Cadenza/issues/27) |
| D34 | [#29](https://github.com/sebdavid3/Cadenza/issues/29) | D33 | [#28](https://github.com/sebdavid3/Cadenza/issues/28) |
| D35 | [#30](https://github.com/sebdavid3/Cadenza/issues/30) | D36 | [#31](https://github.com/sebdavid3/Cadenza/issues/31) |
| D37 | [#32](https://github.com/sebdavid3/Cadenza/issues/32) | D38 | [#33](https://github.com/sebdavid3/Cadenza/issues/33) |
| D39 | [#34](https://github.com/sebdavid3/Cadenza/issues/34) | D40 | [#35](https://github.com/sebdavid3/Cadenza/issues/35) |
| D41 | [#36](https://github.com/sebdavid3/Cadenza/issues/36) | D10 (autenticación) | [#39](https://github.com/sebdavid3/Cadenza/issues/39), [#43](https://github.com/sebdavid3/Cadenza/issues/43), [#44](https://github.com/sebdavid3/Cadenza/issues/44), [#45](https://github.com/sebdavid3/Cadenza/issues/45), [#46](https://github.com/sebdavid3/Cadenza/issues/46) |
| D46 | [#48](https://github.com/sebdavid3/Cadenza/issues/48) | D47 (frontend, fuera del milestone) | [#47](https://github.com/sebdavid3/Cadenza/issues/47) |

Con alcance por decidir (fuera del milestone):

| Deuda | Issue | Deuda | Issue |
|---|---|---|---|
| D42 | [#37](https://github.com/sebdavid3/Cadenza/issues/37) | D12 (mapa tiempo→ancla) | [#42](https://github.com/sebdavid3/Cadenza/issues/42) |
| D44 | [#40](https://github.com/sebdavid3/Cadenza/issues/40) | D45 | [#41](https://github.com/sebdavid3/Cadenza/issues/41) |

D43 ([#38](https://github.com/sebdavid3/Cadenza/issues/38)) se cerró como fuera de alcance.

D11 (parte de interfaz) y la reproducción de D12 pertenecen al diseño del
frontend y quedan fuera de la Fase 7.

---

## Bitácora de hitos

| Fecha | Hito | Fase | Evidencia |
|---|---|---|---|
| 2026-09-20 | Diagnóstico del MVP y definición de arquitectura desde cero | — | `docs/ARCHITECTURE.md`, `docs/adr/` |
| 2026-09-20 | Estructura de memoria de estado y fases creada | Fase 0 | `docs/PROJECT_STATE.md`, `docs/phases/` |
| 2026-09-20 | Dominio core aislado: workspace `uv`, modelos puros y 21 tests verdes (pytest/ruff/black/mypy strict) | Fase 0 | `packages/domain/`, `pyproject.toml`, `uv.lock` |
| 2026-09-20 | Adaptador OMR: puerto `OMREngine`, `FakeOMREngine` determinista y `HOMREngine` in-process (API Python, sin subprocess), namespace `cadenza` PEP 420 y 35 tests verdes | Fase 1 | `packages/omr/`, `pyproject.toml`, `uv.lock` |
| 2026-09-20 | Motor de validación: `TimeSignature` en dominio, `ValidationRule`/`ValidationEngine` y `MeasureBalanceRule` sobre `music21` con anclaje al primer evento; 54 tests verdes | Fase 2 | `packages/validation/`, `packages/domain/`, `pyproject.toml`, `uv.lock` |
| 2026-09-20 | Backend API + persistencia: 3 endpoints FastAPI, modelos SQLAlchemy con JSONB (SQLite/PostgreSQL) y Alembic, `bbox` sintético en `FakeOMREngine`, flujo E2E Fake→Validation→SQLite; 61 tests verdes | Fase 3A | `apps/api/`, `packages/persistence/`, `packages/omr/`, `pyproject.toml`, `uv.lock` |
| 2026-09-20 | Frontend HITL: `apps/web` (React 18 + TS + Zustand + TanStack Query), `GET /sessions/{id}`, overlays `bbox` sobre imagen, `SetPitch` inmutable, undo/redo y métricas de esfuerzo; E2E en navegador (64 pytest + 8 vitest + build) | Fase 3B | `apps/web/`, `apps/api/`, `pyproject.toml` |
| 2026-09-20 | Aprendizaje activo: `packages/learning` con `DatasetBuilder`, `Uncertainty`/`Diversity`/`Hybrid` acquisition, evaluación SER/NED, `ModelRegistry` con promoción por umbral, `Trainer`/`FakeTrainer` y `configs/learning/`; 93 tests verdes | Fase 4 | `packages/learning/`, `configs/learning/`, `pyproject.toml`, `uv.lock` |
| 2026-09-20 | Auditoría hexagonal y saneamiento: append-only real en BD (`EditEventRepository` + listeners + migración `0002`), proyección del log (`materialize`/`apply_edit`), `music21` fuera del validador, upload a disco; 104 tests verdes | Fase 3/4 (deuda) | `packages/domain/projection.py`, `packages/persistence/repository.py`, `migrations/versions/0002_*`, `apps/api/main.py` |
| 2026-09-20 | Framework de experimentos: `ml/experiments/exp_01_effort.py` (reducción de esfuerzo 75%) y `exp_02_active_learning.py` (comparación uncertainty/diversity/hybrid), salidas en `results/` | Fase 5 | `ml/experiments/`, `results/`, `.gitignore`, `docs/PROJECT_STATE.md` |
| 2026-09-20 | Puente canónico de notación: `packages/interchange` (MusicXML/MEI/**kern ↔ `ScoreIR` con music21, import perezoso en OMR); 6 tests; parser `xml.etree` retirado | Fase 6 (6.0) | `packages/interchange/`, `packages/omr/`, `pyproject.toml`, `uv.lock` |
| 2026-09-20 | OMR-NED oficial: `cadenza.learning.omr_ned_pair`/`omr_ned_batch` con musicdiff 5.2 (extra `metrics`); tooling de corpus (`corpus.py`) y experimentos `exp_03`/`exp_04`; 108 tests verdes | Fase 6 (6.1–6.2) | `packages/learning/`, `ml/experiments/`, `docs/phases/phase_6_empirical_validation/` |
| 2026-09-20 | Primer baseline OMR real: PrIMuS descargado, HOMR 0.7 adaptado (`transcribe_musicxml`, config sin `title_detection`), manifiesto con filtrado AppleDouble y `exp_04` tolerante a fallos; OMR-NED medio **0.0868** sobre 4 incipits (CPU) | Fase 6 (6.3, parcial) | `packages/omr/adapters/homr.py`, `ml/experiments/`, `results/omr_baseline_summary.json` |
| 2026-09-20 | Baseline OMR completo (100 incipits PrIMuS, CPU): 91 transcritos, 9 fallos `No staffs found`, **OMR-NED medio 0.2285** (mediana 0.1727); `exp_04` registra `run_info.json` con el entorno de inferencia | Fase 6 (6.3) | `results/omr_baseline.csv`, `data/primus/predictions/` |
| 2026-09-20 | GPU operativa: `onnxruntime-gpu==1.26.0` (CUDA 12.8, cu12) + `ensure_cuda_dll_dirs` en el adaptador (expone los `bin` de cuDNN que `preload_dlls` no cubre); baseline re-ejecutado en GPU con OMR-NED idéntico al de CPU (0.2285) | Fase 6 (6.3) | `packages/omr/adapters/homr.py`, `ml/experiments/exp_04_homr_transcribe.py`, `docs/PROJECT_STATE.md` |
| 2026-09-20 | Reorganización del repositorio: el prototipo MVP (`backend/`, `frontend/`, `scripts/`, `docker-compose*`) se movió a `legacy/`; `.gitignore`, `pyproject.toml` y documentación actualizados; compose validado desde la nueva ruta | — | `legacy/`, `pyproject.toml`, `.gitignore`, `README.md` |
| 2026-10-03 | Arquitectura objetivo v1.1: capa de aplicación (ADR-0009), `ScoreIR` extendido y exportación en `interchange` (ADR-0010), organización de datos y catálogo de funciones; DBB alineado con `ARCHITECTURE.md`; brechas registradas como D22–D31 y como issues [#1](https://github.com/sebdavid3/Cadenza/issues/1)–[#26](https://github.com/sebdavid3/Cadenza/issues/26) | Fase 7 | `docs/ARCHITECTURE.md`, `docs/arquitectura-dbb.md`, `docs/adr/ADR-0009-*`, `docs/adr/ADR-0010-*`, `docs/phases/phase_7_architecture_alignment/` |
| 2026-10-03 | Dos brechas adicionales registradas tras revisar la cobertura de la fase: listado de sesiones (D32, [#27](https://github.com/sebdavid3/Cadenza/issues/27)) y estabilidad de anclas ante ediciones estructurales (D33, [#28](https://github.com/sebdavid3/Cadenza/issues/28)) | Fase 7 | `docs/ARCHITECTURE.md` §6 y §10.2, `docs/phases/phase_7_architecture_alignment/` |
| 2026-10-03 | Planificación del backend final completada: ocho brechas más frente a los objetivos de la tesis y la coherencia del backend (D34–D41, [#29](https://github.com/sebdavid3/Cadenza/issues/29)–[#36](https://github.com/sebdavid3/Cadenza/issues/36)) y seis piezas con alcance por decidir (D42–D45, D10, D12; [#37](https://github.com/sebdavid3/Cadenza/issues/37)–[#42](https://github.com/sebdavid3/Cadenza/issues/42)) | Fase 7 | `docs/ARCHITECTURE.md` §6, §7.2 y §10.2, `docs/phases/phase_7_architecture_alignment/` |
| 2026-10-03 | Decisiones previas al desarrollo: una imagen por sesión (PDF y multipágina fuera de alcance, [#38](https://github.com/sebdavid3/Cadenza/issues/38) cerrado), autenticación completa con sesiones privadas (ADR-0012, [#39](https://github.com/sebdavid3/Cadenza/issues/39) pasa al milestone) y anclas posicionales relativas a un estado con función de traducción (ADR-0011, [#28](https://github.com/sebdavid3/Cadenza/issues/28)); `ARCHITECTURE.md` v1.2 | Fase 7 | `docs/adr/ADR-0011-*`, `docs/adr/ADR-0012-*`, `docs/ARCHITECTURE.md`, `docs/phases/phase_7_architecture_alignment/` |
| 2026-10-03 | Trabajo derivado de las decisiones convertido en issues: autenticación desglosada en [#43](https://github.com/sebdavid3/Cadenza/issues/43)–[#46](https://github.com/sebdavid3/Cadenza/issues/46) (con [#39](https://github.com/sebdavid3/Cadenza/issues/39) como seguimiento), estado actual de la sesión y `base_seq` ([#48](https://github.com/sebdavid3/Cadenza/issues/48), D46) e inicio de sesión en el visor ([#47](https://github.com/sebdavid3/Cadenza/issues/47), D47); ADR-0011 precisa el control por `base_seq` y ADR-0012, la gestión de cuentas | Fase 7 | `docs/adr/ADR-0011-*`, `docs/adr/ADR-0012-*`, `docs/ARCHITECTURE.md` §6 y §10.2 |
| 2026-10-07 | Paso 0 de la Fase 7 completado: reglas permanentes en `CLAUDE.md`, política de ramas, commits, PRs y Definition of Done en `docs/CONVENTIONS.md`; árbol formateado con `black` y suites de calidad 100% limpias | Fase 7 (Paso 0) | `CLAUDE.md`, `docs/CONVENTIONS.md`, `pyproject.toml`, rama `docs/0-reglas-de-trabajo` |
| 2026-10-07 | Integración continua completada ([#25](https://github.com/sebdavid3/Cadenza/issues/25)): workflow GitHub Actions `ci.yml` para Python 3.12 (`pytest`, `mypy`, `ruff`, `black`) y frontend (`vitest`, `build`) con caché e insignia en `README.md` | Fase 7 / Infra | `.github/workflows/ci.yml`, `README.md`, `docs/ARCHITECTURE.md` |
| 2026-10-07 | Capa de aplicación hexagonal extraída ([#7](https://github.com/sebdavid3/Cadenza/issues/7)): paquete `packages/application` (casos de uso `transcribe_score`, `get_session`, `append_edit`, `list_findings`; puertos `SessionRepository` y `EditEventRepository` con adaptadores SQLAlchemy; apps/api como raíz de composición); 114 tests verdes y test de pureza de aplicación | Fase 7 / App | `packages/application/`, `packages/persistence/`, `apps/api/`, `docs/ARCHITECTURE.md` |
| 2026-10-07 | `ScoreIR` completo con clave, armadura y ligaduras ([#2](https://github.com/sebdavid3/Cadenza/issues/2)): tipos de valor puros `Clef`, `KeySignature` y `Tie` en `packages/domain` (ADR-0010), lectura/escritura y round-trip en `packages/interchange`, compatibilidad hacia atrás, estabilidad de anclas y 122 tests verdes | Fase 7 / Dominio | `packages/domain/`, `packages/interchange/`, `docs/ARCHITECTURE.md` |
| 2026-10-07 | `ArtifactStore` direccionado por `sha256` completado ([#4](https://github.com/sebdavid3/Cadenza/issues/4)): puerto `ArtifactStore` e `InMemoryArtifactStore` en `packages/application`, adaptador `FilesystemArtifactStore` (`data/artifacts/sha256/ab/cd/<hash>`) y tabla `artifacts` con migración `0003_artifacts_table` en `packages/persistence`; 128 tests verdes | Fase 7 / Datos | `packages/application/`, `packages/persistence/`, `docs/ARCHITECTURE.md` |

---

## Convención de actualización

Al **concluir cualquier tarea**, actualizar en este orden:

1. **Fase actual** y **Próximo paso inmediato**.
2. **Último hito completado** (una línea, verificable).
3. Filas de **Deuda técnica / Blockers** (agregar o resolver).
4. Nueva fila en la **Bitácora de hitos** con fecha y evidencia.
5. **Fecha de actualización**.

Los prompts de cada fase viven en `docs/phases/<fase>/prompts/` y terminan con
la instrucción: `Al finalizar, actualiza PROJECT_STATE.md`.
