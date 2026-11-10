# cadenza-api

API Gateway de Cadenza (FastAPI). Expone el flujo hexagonal completo sobre
`HOMREngine`, el único motor OMR (ADR-0018), y `ValidationEngine`:

- `POST /transcribe` — transcripción síncrona con HOMR, validación y persistencia
  de la sesión + findings iniciales.
- `POST /transcription-jobs` — la misma transcripción en segundo plano: responde
  202 enseguida y `GET /transcription-jobs/{id}` dice en qué está (en cola,
  detectando, leyendo el pentagrama X de N, revisando, lista o fallida). La cola
  vive en la memoria del proceso: supone un solo proceso de la API y se pierde
  al reiniciarla (ADR-0064). Topes: `CADENZA_TRANSCRIBE_JOBS_PER_USER` (10, 429)
  y `CADENZA_TRANSCRIBE_JOBS_MAX` (30, 503).
- `GET /sessions/{id}/findings` — hallazgos anclados de la sesión.
- `POST /sessions/{id}/edits` — append inmutable de un `EditEvent` (ADR-0007).

Arranque local:

```bash
uv run uvicorn cadenza.api.main:create_default_app --factory
```
