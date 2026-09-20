# PROJECT STATE — Cadenza

> **Documento vivo.** Es la memoria compartida del proyecto y el único mapa
> maestro de navegación. **Toda tarea futura termina actualizando este archivo.**
> No se crea un índice paralelo; este documento es la fuente de verdad del estado.

| Campo | Valor |
|---|---|
| **Fase actual** | Fase 6 — Validación Empírica sobre Corpus Real — **en curso** (6.0 y 6.1 cerradas; 6.2/6.3 pendientes de entorno) |
| **Último hito completado** | Puente canónico de notación (`packages/interchange`, music21) + OMR-NED oficial (`musicdiff`) como extra de `cadenza-learning`; `ml/experiments/corpus.py`, `exp_03_omr_quality.py` y `exp_04_homr_transcribe.py`; 108 tests verdes (pytest/ruff/mypy strict) |
| **Próximo paso inmediato** | Descargar un split acotado de PrIMuS/Camera-PrIMuS (`corpus.py fetch`), instalar el extra `homr` y correr `exp_04` (GPU) + `exp_03` sobre el corpus real |
| **Rama activa** | `feature/interchange` |
| **Deuda técnica / Blockers activos** | D1–D6, D8–D16 (D4 mitigada, D7 resuelta) |
| **Guía de estilo / calidad** | [`docs/CONVENTIONS.md`](CONVENTIONS.md) — **contrato oficial** de Git, commits y calidad de código |
| **Fecha de actualización** | 2026-09-20 |

---

## Principio rector (no destructivo)

El repositorio contiene un **prototipo funcional E2E** (FastAPI + HOMR + Docker
CUDA + visor OSMD + Tone.js). El objetivo de las fases siguientes es
**refactorizarlo progresivamente** hacia la arquitectura hexagonal de
[`docs/ARCHITECTURE.md`](ARCHITECTURE.md), **no reescribirlo desde cero**.

Reglas:

1. El prototipo en `backend/`, `frontend/`, `docker-compose*` y `scripts/`
   permanece **operativo** en todo momento.
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
| **M6** | Validación empírica (`packages/interchange`, OMR-NED, corpus) | Fase 6 | En curso: 6.0 puente canónico y 6.1 OMR-NED **completos**; 6.2 tooling de corpus listo; 6.3 pendiente de descarga + GPU (D20) |

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
| D10 | Persistencia verificada solo en SQLite en memoria: sin migración aplicada ni tests contra PostgreSQL real; API sin autenticación | Fase 3A | Pendiente (sub-tarea) |
| D11 | Renderizado de notación con OSMD no implementado: bloqueado por el exportador `ScoreIR`→MusicXML (paquete `export`) y por la instrumentación `Anchor→SVG` (ADR-0006) | Fase 3B / M3 | Pendiente (sub-tarea) |
| D12 | Reproducción con Tone.js y cursor sincronizado (mapa tiempo→ancla) no implementada | Fase 3B / M3 | Pendiente (sub-tarea) |
| D13 | Métricas de esfuerzo calculadas solo en el cliente; no se persisten en la base de datos | Fase 3B / M4 | Pendiente (sub-tarea) |
| D14 | `Trainer` real no implementado: solo `FakeTrainer` determinista; falta PyTorch + pipeline de HOMR + export ONNX (requiere GPU y pesos) | Fase 4 / M4 | Pendiente (entorno) |
| D15 | OMR-NED con `musicdiff` no integrada: `normalized_edit_distance` es un proxy propio sobre secuencias de símbolos | Fase 4 / M4 | **Resuelta** — `cadenza.learning.omr_ned_pair`/`omr_ned_batch` (extra `metrics`, musicdiff 5.2); el proxy se conserva como fallback |
| D16 | Sin orquestación CLI del job de *fine-tuning* ni `DatasetBuilder` acoplado a persistencia (`EditEvents`/imágenes); `configs/` solo tiene la config base | Fase 4 / M4 | Pendiente (sub-tarea) |
| D17 | Experimento 1 usa un documento sintético; falta correrlo sobre un corpus/partituras reales con OMR para reclamar validez externa | Fase 5 / M5 | Pendiente (sub-tarea) |
| D18 | Experimento 2 depende del `DatasetBuilder`, no de la persistencia: el pool histórico aún no se extrae de sesiones reales (`EditEvents` en BD) | Fase 5 / M5 | Pendiente (sub-tarea) |
| D19 | Reducción de esfuerzo medida en `ml/experiments` no usa los eventos HITL reales ni `musicdiff` para OMR-NED | Fase 5 / M5 | **Parcial** — OMR-NED oficial integrado (`exp_03`); falta correrlo sobre corpus real (D20) |
| D20 | HOMR real no ejecutado en GPU: falta descargar corpus (PrIMuS/SMB), instalar el extra `homr` y verificar `onnxruntime-gpu` en la RTX 5050 (Blackwell/sm_120) | Fase 6 / M6 | Pendiente (entorno) |
| D21 | Experimento de AL sobre distribuciones de error reales (derivar `EditEvent`s del diff HOMR↔GT) sin diseñar | Fase 6 / M6 | Pendiente (sub-tarea) |

*(Se agregan filas aquí a medida que surgen. Las resueltas se conservan marcadas para trazabilidad.)*

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
