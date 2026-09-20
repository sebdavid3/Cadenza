# cadenza-persistence

Persistencia de Cadenza (ADR-0004). Modela tres agregados:

- `Session` — un documento procesado (guarda el `ScoreDocument` serializado).
- `FindingRecord` — hallazgo de validación con `anchor` en JSONB.
- `EditEventRecord` — corrección humana **inmutable** (append-only) con payload y
  `anchor` en JSONB (ADR-0007).

El tipo JSON es `JSONB` en PostgreSQL y `JSON` en SQLite (tests). El esquema se
crea con `create_schema` en desarrollo/tests; para PostgreSQL se usa Alembic
(`migrations/`).
