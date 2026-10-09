# cadenza-omr

Adaptador OMR de Cadenza. Expone el puerto `OMREngine` y sus adaptadores:

- `FakeOMREngine` — transcripción determinista y hardcodeada, sin I/O ni modelos
  (tests, CI y Fases 2–3).
- `HOMREngine` — HOMR **in-process** sobre su API de Python, mapeado al
  `ScoreDocument` del dominio.
- `OemerEngine` — línea base OMR alternativa **in-process** sobre la API de `oemer`
  (ADR-0005, deuda D1), mapeada al `ScoreDocument` del dominio.

El módulo importa sin tener instalado HOMR ni oemer; los stacks pesados viven en
los extras opcionales `homr` y `oemer` y se importan de forma perezosa dentro de sus
respectivos métodos `transcribe`:

```bash
uv pip install -e "packages/omr[homr]"
uv pip install -e "packages/omr[oemer]"
```

El motor se selecciona en el plano online mediante la variable de entorno `CADENZA_OMR_ENGINE`
(`fake`, `homr` o `oemer`).

