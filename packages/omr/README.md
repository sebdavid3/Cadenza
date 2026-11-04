# cadenza-omr

Adaptador OMR de Cadenza. Expone el puerto `OMREngine` y su único adaptador
([ADR-0018](../../docs/adr/ADR-0018-homr-como-unico-motor-omr.md)):

- `HOMREngine` — HOMR **in-process** sobre su API de Python, mapeado al
  `ScoreDocument` del dominio.

El módulo importa sin tener instalado HOMR; el stack pesado vive en el extra
opcional `homr` y se importa de forma perezosa dentro de `transcribe`:

```bash
uv pip install -e "packages/omr[homr]"
```

`cadenza.omr.testing.FakeOMREngine` es un doble de pruebas: devuelve una
partitura determinista sin I/O ni modelos para que las pruebas y la CI, que no
instalan HOMR, puedan inyectarlo en `create_app`. No se exporta desde
`cadenza.omr` ni se puede seleccionar por configuración.
