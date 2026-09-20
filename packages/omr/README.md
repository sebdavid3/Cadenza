# cadenza-omr

Adaptador OMR de Cadenza. Expone el puerto `OMREngine` y sus adaptadores:

- `FakeOMREngine` — transcripción determinista y hardcodeada, sin I/O ni modelos
  (tests, CI y Fases 2–3).
- `HOMREngine` — HOMR **in-process** sobre su API de Python, mapeado al
  `ScoreDocument` del dominio.

El módulo importa sin tener instalado HOMR; el stack pesado vive en el extra
opcional `homr` y se importa de forma perezosa dentro de `HOMREngine.transcribe`.
