# Prompt 01 — Refactorización del Dominio Core

**Fase:** 0 — `phase_0_core_domain`
**Tipo:** construcción de dominio (paralelo, no destructivo)
**Referencias:** [`../../ARCHITECTURE.md`](../../../ARCHITECTURE.md) §2,
[ADR-0001](../../../adr/ADR-0001-monolito-modular-hexagonal.md),
[ADR-0002](../../../adr/ADR-0002-score-document-anchor-index.md),
[ADR-0007](../../../adr/ADR-0007-edit-events-inmutables.md)

---

## Rol

Actúa como **Tech Lead** del proyecto Cadenza. Vas a crear el núcleo del dominio
hexagonal, que será el contrato compartido por los cuatro módulos de
investigación.

## Contexto crítico (NO DESTRUCTIVO)

El repositorio **ya contiene un prototipo funcional E2E** (FastAPI en
`legacy/backend/main.py`, HOMR, Docker con CUDA, visor OSMD y Tone.js). **No debes
romperlo ni sobrescribirlo.** El nuevo dominio se construye **en paralelo** en
`packages/domain/` y **no se integra** al prototipo durante esta tarea.

Prohibido:

- editar `legacy/` (`legacy/backend`, `legacy/frontend`, `legacy/docker-compose*.yml`, `legacy/scripts`);
- invocar o importar HOMR, `music21`, `torch` u `onnxruntime`;
- usar frameworks web o de validación en el dominio.

## Objetivo

Implementar los **modelos puros del dominio** con `dataclasses` de la librería
estándar (**cero dependencias externas**) y el *tooling* raíz, preparando el
terreno para las fases 1–4 sin tocar el prototipo.

## Entregables

1. `pyproject.toml` raíz con **uv workspace**, configurando de forma única
   `ruff`, `black`, `mypy` y `pytest`.
2. Paquete `packages/domain/` con:
   - `Anchor` — ruta lógica estable (`part`, `staff`, `measure`, `voice`,
     `event_index`, `staff_id`) + metadatos opcionales inmutables (`bbox`,
     `confidence`).
   - `AnchorIndex` — mapa determinista `Anchor → EventRef`.
   - `ScoreIR` — contenedor de la representación simbólica normalizada (en esta
     fase, estructura neutral; **no** parsea MusicXML ni usa `music21`).
   - `Provenance` — trazabilidad (`omr_engine`, `model_version`, `rules_version`,
     `source_image_hash`).
   - `ScoreDocument` — agregado `(ScoreIR, AnchorIndex, Provenance)`.
   - `Finding` — `anchor`, `rule_id`, `severity` (enum), `message`,
     `suggested_fix?`.
   - `EditEvent` — inmutable: `op`, `anchor`, `before`, `after`, `author`,
     `created_at`; enum `EditOp` con `SetPitch`, `SetDuration`, `SetAccidental`,
     `InsertEvent`, `DeleteEvent`, `SetClef`, `SetKey`.
   - Invariantes documentadas (p. ej. `Anchor` congelado, `AnchorIndex`
     determinista, `EditEvent` inmutable).
3. Tests base en `packages/domain/tests/`:
   - determinismo del `AnchorIndex`;
   - inmutabilidad de `EditEvent` (no mutación in-place);
   - serialización/deserialización round-trip de los modelos;
   - ausencia de imports de terceros en el dominio (test automatizado).

## Restricciones de diseño

- `dataclasses` de la stdlib; sin Pydantic, sin attrs, sin ORM.
- Sin acoplamiento a I/O: el dominio no lee archivos, ni red, ni base de datos.
- Pydantic v2 queda **estrictamente** para adaptadores de entrada en `apps/api/`.
- Inmutabilidad donde corresponda (`frozen=True`) y tipos anotados (`mypy` estricto).

## Verificación (obligatoria)

Ejecuta y deja evidencia en el resumen final:

```bash
uv sync
uv run pytest packages/domain
uv run ruff check .
uv run black --check .
uv run mypy packages/domain
```

Además, confirma que el prototipo no se tocó: `git status` no debe mostrar
cambios en `legacy/`.

## Criterios de aceptación

- Dominio con **cero dependencias externas** y sin acoplamiento a I/O.
- Suite de dominio verde; `ruff`/`black`/`mypy` limpios.
- Prototipo E2E intacto (sin diffs en sus rutas).
- Sin cambios fuera de `packages/` y `pyproject.toml` (+ `docs/` para el estado).

---

**Al finalizar, actualiza PROJECT_STATE.md**
