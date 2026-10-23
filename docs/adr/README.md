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
| [ADR-0005](ADR-0005-motor-omr-homr-baseline-oemer.md) | HOMR/ONNX como motor OMR base, oemer como línea base | Aceptado; punto 3 reemplazado y punto 4 precisado por ADR-0018 | M1 |
| [ADR-0006](ADR-0006-render-editor-osmd-verovio-zustand.md) | Renderizado reactivo (OSMD/Verovio) y estado editorial (Zustand) | Aceptado | M3 |
| [ADR-0007](ADR-0007-edit-events-inmutables.md) | Correcciones HITL como eventos inmutables sobre anclas | Aceptado | M3, M4 |
| [ADR-0008](ADR-0008-active-learning-model-registry.md) | Estrategia de Active Learning y Model Registry | Aceptado | M4 |
| [ADR-0009](ADR-0009-capa-de-aplicacion.md) | Capa de aplicación con casos de uso | Aceptado | Transversal |
| [ADR-0010](ADR-0010-score-ir-atributos-y-exportacion.md) | Atributos de compás en el `ScoreIR` y exportación en `interchange` | Aceptado | Dominio, M2, M3 |
| [ADR-0011](ADR-0011-semantica-de-anclas-ante-ediciones.md) | Semántica de las anclas ante ediciones estructurales | Aceptado | Dominio, M2, M3, M4 |
| [ADR-0012](ADR-0012-autenticacion-e-identidad.md) | Autenticación e identidad de usuario | Aceptado | Transversal |
| [ADR-0013](ADR-0013-revalidacion-y-versionado-de-hallazgos.md) | Revalidación bajo demanda y versionado de hallazgos | Aceptado | M2, M3, M4 |
| [ADR-0014](ADR-0014-ciclo-de-vida-de-la-sesion.md) | Ciclo de vida de la sesión (estados, finalización y reapertura) | Aceptado | M2, M3, M4 |
| [ADR-0015](ADR-0015-operacion-y-despliegue-del-backend.md) | Operación y despliegue del backend | Aceptado | API, Infra |
| [ADR-0016](ADR-0016-transcripcion-sincrona-vs-asincrona.md) | Transcripción síncrona de página única frente a colas asíncronas | Aceptado | API, Plano Online |
| [ADR-0017](ADR-0017-validacion-del-contenido-de-las-ediciones.md) | Validación del contenido de las ediciones y estado previo fijado por el servidor | Aceptado | Dominio, API, M3, M4 |
| [ADR-0018](ADR-0018-homr-como-unico-motor-omr.md) | HOMR como único motor OMR | Aceptado | M1, API |
| [ADR-0019](ADR-0019-base-del-cliente-web.md) | Base del cliente web (Fase 8) | Aceptado | Web |
| [ADR-0020](ADR-0020-sesion-del-cliente-web.md) | Sesión del cliente web: token, recuperación y caducidad | Aceptado | Web |
| [ADR-0021](ADR-0021-visualizacion-de-la-transcripcion-y-marcado-de-hallazgos.md) | Visualización de la transcripción y marcado de hallazgos por compás | Aceptado | Web, M2 |


