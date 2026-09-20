# PROJECT STATE — Cadenza

> **Documento vivo.** Es la memoria compartida del proyecto y el único mapa
> maestro de navegación. **Toda tarea futura termina actualizando este archivo.**
> No se crea un índice paralelo; este documento es la fuente de verdad del estado.

| Campo | Valor |
|---|---|
| **Fase actual** | Fase 0 — Refactorización del Dominio Core |
| **Último hito completado** | Arquitectura y ADRs definidos (`docs/ARCHITECTURE.md` + `docs/adr/0001–0008`) |
| **Próximo paso inmediato** | Aislar los modelos de dominio sin romper el prototipo actual |
| **Deuda técnica / Blockers activos** | *(vacío)* |
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
| **Dominio** | `packages/domain` (ScoreDocument, Anchor, EditEvent) | Fase 0 | En curso |
| **M1** | `OMREngine` (HOMR/ONNX + oemer baseline) | Fase 1 | Pendiente |
| **M2** | Motor de validación por reglas | Fase 2 | Pendiente |
| **M3** | Interfaz HITL (editor + eventos) | Fase 3 | Pendiente |
| **M4** | Active Learning + Model Registry | Fase 4 | Pendiente |

---

## Deuda técnica / Blockers

| ID | Descripción | Impacto | Estado |
|---|---|---|---|
| — | Sin blockers activos | — | — |

*(Se agregan filas aquí a medida que surgen; se eliminan al resolverse.)*

---

## Bitácora de hitos

| Fecha | Hito | Fase | Evidencia |
|---|---|---|---|
| 2026-09-20 | Diagnóstico del MVP y definición de arquitectura desde cero | — | `docs/ARCHITECTURE.md`, `docs/adr/` |
| 2026-09-20 | Estructura de memoria de estado y fases creada | Fase 0 | `docs/PROJECT_STATE.md`, `docs/phases/` |
| — | Aislar modelos de dominio | Fase 0 | `docs/phases/phase_0_core_domain/prompts/01_refactor_domain.md` |

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
