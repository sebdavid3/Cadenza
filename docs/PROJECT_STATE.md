# PROJECT STATE — Cadenza

> **Documento vivo.** Es la memoria compartida del proyecto y el único mapa
> maestro de navegación. **Toda tarea futura termina actualizando este archivo.**
> No se crea un índice paralelo; este documento es la fuente de verdad del estado.

| Campo | Valor |
|---|---|
| **Fase actual** | Fase 2 — Validación por reglas — **cerrada** (alcance acordado: motor + regla de balance) |
| **Último hito completado** | Motor de validación (`packages/validation`): `ValidationRule` + `ValidationEngine` + `MeasureBalanceRule` sobre `music21`; `TimeSignature` añadido al dominio; 54 tests verdes (pytest/ruff/black/mypy strict) |
| **Próximo paso inmediato** | Iniciar Fase 3 (Interfaz HITL): editor sobre anclas, `EditEvent` y playback |
| **Rama activa** | `feature/validation-engine` (integrada a `dev`) |
| **Deuda técnica / Blockers activos** | D1–D9 (ver sección *Deuda técnica / Blockers*) |
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
| **M2** | Motor de validación por reglas | Fase 2 | Completado (núcleo: motor + balance); pendiente catálogo/DB/métricas (D6–D9) |
| **M3** | Interfaz HITL (editor + eventos) | Fase 3 | Pendiente |
| **M4** | Active Learning + Model Registry | Fase 4 | Pendiente |

---

## Deuda técnica / Blockers

| ID | Descripción | Impacto | Estado |
|---|---|---|---|
| D1 | `OemerEngine` (línea base OMR para comparación experimental) no implementado | Fase 1 / M1 | Pendiente (sub-tarea) |
| D2 | Preprocesado configurable (deskew, binarización, control de DPI) no implementado | Fase 1 / M1 | Pendiente (sub-tarea) |
| D3 | Reporte del dispositivo efectivo desde `onnxruntime.get_available_providers()` no expuesto | Fase 1 / M1 | Pendiente (sub-tarea) |
| D4 | Anclas sin `bbox`: el puente MusicXML→`ScoreIR` mapea sin coordenadas por evento | Fase 1 / M3 | Pendiente (sub-tarea de enriquecimiento) |
| D5 | `HOMREngine` no verificado E2E (requiere extra `homr` + GPU/pesos); validado por gating de import y mapper | Fase 1 | Pendiente (entorno) |
| D6 | Catálogo de reglas incompleto: faltan armadura/alteraciones, colisiones de voz, rango y cierres | Fase 2 / M2 | Pendiente (sub-tarea) |
| D7 | Persistencia de `Finding` en PostgreSQL/JSONB no implementada | Fase 2 / M2 | Pendiente (sub-tarea) |
| D8 | Métricas de precisión/recall del validador sobre casos conocidos no reportadas | Fase 2 / M2 | Pendiente (sub-tarea) |
| D9 | Frontera canónica MusicXML↔`ScoreIR` con `music21` no implementada (sigue el puente `xml.etree` de Fase 1) | Fase 2 | Pendiente (sub-tarea) |

*(Se agregan filas aquí a medida que surgen; se eliminan al resolverse.)*

---

## Bitácora de hitos

| Fecha | Hito | Fase | Evidencia |
|---|---|---|---|
| 2026-09-20 | Diagnóstico del MVP y definición de arquitectura desde cero | — | `docs/ARCHITECTURE.md`, `docs/adr/` |
| 2026-09-20 | Estructura de memoria de estado y fases creada | Fase 0 | `docs/PROJECT_STATE.md`, `docs/phases/` |
| 2026-09-20 | Dominio core aislado: workspace `uv`, modelos puros y 21 tests verdes (pytest/ruff/black/mypy strict) | Fase 0 | `packages/domain/`, `pyproject.toml`, `uv.lock` |
| 2026-09-20 | Adaptador OMR: puerto `OMREngine`, `FakeOMREngine` determinista y `HOMREngine` in-process (API Python, sin subprocess), namespace `cadenza` PEP 420 y 35 tests verdes | Fase 1 | `packages/omr/`, `pyproject.toml`, `uv.lock` |
| 2026-09-20 | Motor de validación: `TimeSignature` en dominio, `ValidationRule`/`ValidationEngine` y `MeasureBalanceRule` sobre `music21` con anclaje al primer evento; 54 tests verdes | Fase 2 | `packages/validation/`, `packages/domain/`, `pyproject.toml`, `uv.lock` |

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
