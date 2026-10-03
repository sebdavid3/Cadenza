# Architecture Decision Records (ADR) — Cadenza

Este directorio registra, de forma **inmutable y fechada**, las decisiones
arquitectónicas significativas del sistema Cadenza. Cada ADR documenta el
contexto, la decisión, sus consecuencias y las alternativas descartadas, de modo
que el capítulo de Diseño e Implementación de la tesis pueda justificar cada
elección técnica frente al jurado.

El documento maestro que integra y da coherencia a todas estas decisiones es
[`../ARCHITECTURE.md`](../ARCHITECTURE.md).

---

## Convención

- **Formato de archivo:** `ADR-NNNN-titulo-en-kebab-case.md` (numeración de
  cuatro dígitos, sin reutilizar números).
- **Plantilla mínima:** Estado, Fecha, Contexto, Decisión, Consecuencias
  (positivas / riesgos) y Alternativas consideradas.
- **Estados:** `Propuesto`, `Aceptado`, `Rechazado`, `Reemplazado por ADR-NNNN`.
- **Inmutabilidad:** una decisión aceptada no se edita; si cambia, se crea un
  nuevo ADR que la reemplaza y se marca el anterior como `Reemplazado`.

---

## Índice de decisiones

| ID | Título | Estado | Módulo(s) afectado(s) |
|---|---|---|---|
| [ADR-0001](ADR-0001-monolito-modular-hexagonal.md) | Monolito modular hexagonal (Puertos y Adaptadores) | Aceptado | Transversal |
| [ADR-0002](ADR-0002-score-document-anchor-index.md) | `ScoreDocument` con `AnchorIndex` como fuente de verdad | Aceptado | Transversal |
| [ADR-0003](ADR-0003-separacion-planos-computo.md) | Separación estricta de planos de cómputo Online / Offline | Aceptado | M1, M4 |
| [ADR-0004](ADR-0004-persistencia-postgresql-jsonb.md) | Persistencia con PostgreSQL + JSONB y Storage de artefactos | Aceptado | M2, M3, M4 |
| [ADR-0005](ADR-0005-motor-omr-homr-baseline-oemer.md) | HOMR/ONNX como motor OMR base, oemer como línea base | Aceptado | M1 |
| [ADR-0006](ADR-0006-render-editor-osmd-verovio-zustand.md) | Renderizado reactivo (OSMD/Verovio) y estado editorial (Zustand) | Aceptado | M3 |
| [ADR-0007](ADR-0007-edit-events-inmutables.md) | Correcciones HITL como eventos inmutables sobre anclas | Aceptado | M3, M4 |
| [ADR-0008](ADR-0008-active-learning-model-registry.md) | Estrategia de Active Learning y Model Registry | Aceptado | M4 |
| [ADR-0009](ADR-0009-capa-de-aplicacion.md) | Capa de aplicación con casos de uso | Aceptado | Transversal |
| [ADR-0010](ADR-0010-score-ir-atributos-y-exportacion.md) | Atributos de compás en el `ScoreIR` y exportación en `interchange` | Aceptado | Dominio, M2, M3 |
| [ADR-0011](ADR-0011-semantica-de-anclas-ante-ediciones.md) | Semántica de las anclas ante ediciones estructurales | Aceptado | Dominio, M2, M3, M4 |
| [ADR-0012](ADR-0012-autenticacion-e-identidad.md) | Autenticación e identidad de usuario | Aceptado | Transversal |
