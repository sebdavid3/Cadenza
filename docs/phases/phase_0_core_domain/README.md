# Fase 0 — Refactorización del Dominio Core

**Objetivo:** crear el núcleo hexagonal de Cadenza (`packages/domain`) como código
**puro** —sin dependencias externas—, junto con el *tooling* raíz del repositorio,
**sin romper el prototipo E2E existente**.

Referencia arquitectónica: [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md),
[ADR-0001](../../adr/ADR-0001-monolito-modular-hexagonal.md),
[ADR-0002](../../adr/ADR-0002-score-document-anchor-index.md),
[ADR-0007](../../adr/ADR-0007-edit-events-inmutables.md).

---

## Requerimientos

1. **Estructura `packages/domain/`** con el modelo `ScoreDocument` compuesto por
   `ScoreIR`, `AnchorIndex` y `Provenance` (ADR-0002).
2. **`Anchor`** como ruta lógica estable (`part`, `staff`, `measure`, `voice`,
   `event_index`, `staff_id`) con metadatos opcionales (`bbox`, `confidence`).
3. **`AnchorIndex`** como mapa determinista `Anchor → EventRef`.
4. **`EditEvent`** inmutable (`op`, `anchor`, `before`, `after`, `author`,
   `created_at`) y el conjunto de operaciones (`SetPitch`, `SetDuration`,
   `SetAccidental`, `InsertEvent`, `DeleteEvent`, `SetClef`, `SetKey`).
5. **`Finding`** con `anchor`, `rule_id`, `severity`, `message`, `suggested_fix?`.
6. **Modelos con `dataclasses` de la librería estándar: cero dependencias externas.**
   Pydantic v2 se reserva para los adaptadores de entrada en `apps/api/`.
7. **Tooling raíz:** `pyproject.toml` con **uv workspace**, configuración única de
   `ruff`, `black`, `mypy` y `pytest` (un solo punto de verdad).
8. **Tests base** del dominio (invariantes de anclas, inmutabilidad de eventos,
   determinismo del índice).

---

## Fuera de alcance (Out-of-Scope)

- **No modificar** `legacy/` (`legacy/backend`, `legacy/frontend`,
  `legacy/docker-compose*`, `legacy/scripts`).
- **No integrar** HOMR ni invocar el motor OMR.
- **No importar** `music21`, `torch`, `onnxruntime` ni frameworks web en el dominio.
- Sin persistencia (base de datos), sin API, sin UI.
- Sin `DatasetBuilder`, validación ni aprendizaje activo (fases posteriores).

---

## Criterios de aceptación (Definition of Done)

- [ ] `packages/domain/` existe con los modelos listados y **cero imports de
      terceros** (verificado de forma automatizada).
- [ ] `Anchor` es determinista: dos construcciones equivalentes producen el mismo
      ancla; existe prueba que lo demuestra.
- [ ] `EditEvent` es inmutable y serializable a/desde `dataclass`.
- [ ] Suite de `pytest` del dominio **verde**.
- [ ] `ruff`, `black --check` y `mypy` pasan sin errores.
- [ ] `pyproject.toml` raíz con uv workspace operativo.
- [ ] El prototipo E2E sigue funcionando sin cambios.
- [ ] `docs/PROJECT_STATE.md` actualizado (fase, hito, bitácora).

---

## Prompt ejecutable

[`prompts/01_refactor_domain.md`](prompts/01_refactor_domain.md)
