# cadenza-api

API Gateway de Cadenza (FastAPI). Expone el flujo hexagonal completo sobre
`HOMREngine`, el único motor OMR (ADR-0018), y `ValidationEngine`:

- `POST /transcribe` — transcripción con HOMR, validación y persistencia de la
  sesión + findings iniciales.
- `GET /sessions/{id}/findings` — hallazgos anclados de la sesión.
- `POST /sessions/{id}/edits` — append inmutable de un `EditEvent` (ADR-0007).

Arranque local:

```bash
uv run uvicorn cadenza.api.main:create_default_app --factory
```
