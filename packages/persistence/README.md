# cadenza-persistence

Capa de persistencia relacional y almacenamiento de Cadenza ([ADR-0004](https://github.com/sebdavid3/Cadenza/blob/dev/docs/adr/ADR-0004-persistencia-postgresql-jsonb.md), [ADR-0007](https://github.com/sebdavid3/Cadenza/blob/dev/docs/adr/ADR-0007-diseno-del-log-de-ediciones.md)).

## Entidades y Agregados Persistidos

- `Session` (`sessions`): documento procesado, propietario (`owner_id` FK a `users` con `ondelete="RESTRICT"`), artefacto de imagen (`image_artifact` FK a `artifacts`), estado de ciclo de vida (`status`), versión del modelo OMR y secuencia de última validación (`validated_at_seq`). El árbol `ScoreDocument` se persiste serializado en formato JSON.
- `EditEventRecord` (`edit_events`): corrección humana **inmutable** (*append-only*). Contiene `seq`, `op`, `author`, `anchor`, `before`, `after`, `reverts_edit_id` (para eventos compensatorios de deshacer) y marca de tiempo. Garantiza unicidad e integridad estricta mediante la restricción `UNIQUE(session_id, seq)` y clave foránea `session_id` con `ondelete="RESTRICT"`.
- `FindingRecord` (`findings`): hallazgos de reglas de validación musical vinculados al `at_seq` de evaluación. Incluye resolución y descarte como falso positivo (`status`, `dismissed_at`, `dismissed_by`, `dismissal_reason`).
- `UserRecord` (`users`): cuentas de investigadores y transcriptores con hash de contraseña Argon2id y rol tipado ([ADR-0012](https://github.com/sebdavid3/Cadenza/blob/dev/docs/adr/ADR-0012-autenticacion-e-identidad.md)).
- `ArtifactRecord` (`artifacts`): metadatos de archivos direccionados por contenido (`sha256`, tipo MIME, tamaño y ruta física en disco).
- `EffortMetricsRecord` (`effort_metrics`): métricas de esfuerzo cognitivo y temporal de corrección humana asociadas a cada sesión.

## Dialectos de Base de Datos y JSONB

- **PostgreSQL (producción):** las columnas de tipo `JsonDocument` se resuelven nativamente al tipo de datos `JSONB`, habilitando consultas indexables y compresión binaria. En producción, la API opera con `CADENZA_AUTO_CREATE_SCHEMA=false`, dependiendo exclusivamente de las migraciones de Alembic.
- **SQLite (desarrollo y tests unitarios):** las columnas de tipo `JsonDocument` se compilan transparentemente como `JSON` estructurado en texto.

## Migraciones con Alembic

Las migraciones viven en `packages/persistence/migrations/` y son versionadas secuencialmente:

```bash
# Aplicar todas las migraciones hasta HEAD
uv run alembic -c packages/persistence/alembic.ini upgrade head

# Revertir la última revisión
uv run alembic -c packages/persistence/alembic.ini downgrade -1

# Inspeccionar el SQL estático (modo offline) para PostgreSQL
uv run alembic -c packages/persistence/alembic.ini upgrade head --sql
```

## Pruebas de Compatibilidad con PostgreSQL

El archivo `tests/test_postgres_compatibility.py` valida:
1. Compilación del DDL hacia dialecto PostgreSQL y resolución a `JSONB`.
2. Presencia de restricciones `UNIQUE(session_id, seq)` y `ondelete="RESTRICT"`.
3. Generación offline limpia de sentencias SQL para todas las migraciones (0001..0009).
4. Pruebas de integración sobre servidor PostgreSQL en vivo (se omiten automáticamente mediante `pytest.skip` si no hay un servidor configurado en `CADENZA_TEST_POSTGRES_URL`).
