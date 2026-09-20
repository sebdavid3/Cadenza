# ADR-0004: Persistencia con PostgreSQL + JSONB y Storage de artefactos

- **Estado:** Aceptado
- **Fecha:** 2026-09-20
- **Decisores:** Arquitecto de Software, Dirección del proyecto Cadenza
- **Relacionado:** [ADR-0002](ADR-0002-score-document-anchor-index.md), [ADR-0003](ADR-0003-separacion-planos-computo.md), [ADR-0007](ADR-0007-edit-events-inmutables.md)

---

## Contexto

Cadenza debe persistir datos de naturaleza muy distinta:

1. **Datos relacionales:** sesiones de usuario, transcripciones, relaciones entre
   imagen, partitura y correcciones.
2. **Datos semi-estructurados:** los `Finding` del validador, las anclas, los
   eventos de edición y los vectores de características del aprendizaje activo
   tienen forma variable y evolucionan con la investigación.
3. **Blobs grandes e inmutables:** imágenes originales, MusicXML crudo/corregido,
   MIDI y pesos ONNX.

Además, existe una restricción operativa derivada del ADR-0003: el **plano batch
escribe** (eventos de edición, datasets) **en paralelo** al **plano online que
lee** (UI, API). Una base puramente embebida complica esa concurrencia.

El MVP no persistía nada: los directorios temporales se eliminaban al finalizar
cada request, haciendo imposible reconstruir el corpus de correcciones que
alimenta el aprendizaje activo.

## Decisión

Se adopta una **persistencia híbrida**:

### Metadatos → PostgreSQL con columnas JSONB

- **PostgreSQL** como base de datos relacional, con **SQLAlchemy 2** como ORM y
  **Alembic** para migraciones versionadas.
- Los atributos semiestructurados y variables (`finding.payload`, `anchor`,
  `edit_event.before/after`, `sample.features`) se almacenan en columnas
  **JSONB**, lo que permite consultarlos e indexarlos sin migraciones constantes.
- La elección de PostgreSQL (sobre una base embebida) responde a: concurrencia
  escritor-lector entre planos, tipos ricos y soporte JSONB de primera clase.
- **SQLite** se mantiene como *fallback* de configuración para desarrollo de una
  sola máquina, gracias a que SQLAlchemy abstrae el motor; no es el objetivo
  de producción.

Esquema conceptual (simplificado):

```text
transcription_session
  id (pk), created_at, source_image_ref, omr_engine, model_version

score_document
  id (pk), session_id (fk), raw_ir_ref, current_ir_ref, provenance (jsonb)

validation_finding
  id (pk), score_document_id (fk), anchor (jsonb),
  rule_id, severity, message, payload (jsonb)

edit_event                       -- inmutable (ADR-0007)
  id (pk), score_document_id (fk), seq, anchor (jsonb),
  op, before (jsonb), after (jsonb), created_at

al_sample                        -- insumo del plano offline (ADR-0008)
  id (pk), score_document_id (fk), features (jsonb),
  selected_at, acquisition_strategy

model_version                    -- Model Registry (ADR-0008)
  id (pk), onnx_ref, metrics (jsonb), dataset_version, created_at
```

### Blobs → `ArtifactStore` sobre filesystem (content-addressed)

- Los artefactos **no** se guardan en la base de datos.
- Se almacenan tras el puerto `ArtifactStore`, **direccionados por el hash de su
  contenido** (`sha256`), lo que aporta idempotencia y deduplicación natural.
- La implementación inicial es `FilesystemArtifactStore`; la interfaz permite
  migrar a S3/MinIO sin tocar el dominio.
- Referencias en la base de datos como punteros (`ArtifactRef`), no como BLOBs.

## Consecuencias

### Positivas
- **Persistencia del corpus de correcciones** (requisito de M4), ausente en el MVP.
- **Esquema evolutivo:** las estructuras de investigación (features, findings)
  cambian sin migraciones rígidas gracias a JSONB.
- **Concurrencia real** entre el plano online y el batch.
- **Idempotencia y dedupe** de artefactos por hash; menos almacenamiento y
  re-procesamiento accidental.
- **Separación metadatos/blob** alineada con buenas prácticas: consultas rápidas
  sobre la DB, blobs servidos por el store.

### Riesgos / costos
- **Infraestructura adicional:** PostgreSQL en Docker, migraciones y respaldos
  que mantener; se mitiga con `docker-compose` y una política de respaldo simple.
- **Riesgo de modelar JSONB como "cajón de sastre":** hay que documentar el
  esquema lógico de cada payload y validarlo con Pydantic antes de persistir.
- La doble configuración SQLite/PostgreSQL exige disciplina para no usar
  características exclusivas de un motor.

## Alternativas consideradas

1. **Solo SQLite.** Descartado para producción: la concurrencia entre planos y la
   naturaleza del corpus de AL hacen preferible PostgreSQL; se conserva solo como
   *fallback* de desarrollo.
2. **Solo filesystem (sin base de datos).** Descartado: se pierden consultas,
   integridad referencial y trazabilidad de eventos, imprescindibles para M4 y
   para las métricas.
3. **Base de datos documental (p. ej. MongoDB).** Descartado: los datos son
   mayoritariamente relacionales y se obtiene mejor integridad con PostgreSQL +
   JSONB, sin sumar otra tecnología.
4. **Almacenar blobs en la base de datos.** Descartado: infla backups, degrada
   el rendimiento y mezcla dos ciclos de vida distintos.
