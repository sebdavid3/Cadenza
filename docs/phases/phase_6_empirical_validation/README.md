# Fase 6 — Validación Empírica sobre Corpus Real

**Objetivo:** cerrar la brecha de **validez externa** de la Fase 5. Los
experimentos de simulación demostraron que la *maquinaria* funciona; esta fase
demuestra que funciona sobre **partituras reales con ground truth**, con las
métricas oficiales del estado del arte (SER / OMR-NED).

Referencias: [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md) §8 (F5),
[ADR-0005](../../adr/ADR-0005-motor-omr-homr-baseline-oemer.md),
[`../../literatura/06-datasets-corpus.md`](../../literatura/06-datasets-corpus.md),
[`../../literatura/07-formatos-evaluacion.md`](../../literatura/07-formatos-evaluacion.md).

---

## Requerimientos

1. **Puente canónico de notación** (`packages/interchange`): leer/escribir
   MusicXML y (opcionalmente) MEI/**kern como `ScoreIR`, con `music21` fuera del
   dominio.
2. **OMR-NED oficial** (`musicdiff`) integrado como métrica evaluable, con el
   proxy de Fase 4 como *fallback*.
3. **Corpus acotado y trazable**: subconjunto de PrIMuS/Camera-PrIMuS (y luego
   SMB), versionado por hash en un manifiesto; sin blobs en git.
4. **Inferencia real de HOMR** sobre GPU (con degradación a CPU documentada).
5. **Experimentos reales**: calidad OMR (SER/OMR-NED), reducción de esfuerzo
   sobre transcripciones reales y comparación de estrategias de AL sobre
   distribuciones de error reales.
6. **Reproducibilidad**: semillas fijas, manifiesto por hash y `results/`
   ignorado por git.

## Fuera de alcance (Out-of-Scope)

- Entrenamiento/*fine-tuning* real (D14): sigue pendiente.
- Corpus negociado con instituciones (descartado; se usan datasets públicos).
- Manuscritos históricos / orquesta completa (fuera del corpus objetivo).
- Autenticación, despliegue distribuido y autoescalado.

## Sub-fases

| Sub-fase | Entregable | Deuda |
|---|---|---|
| **6.0** | `packages/interchange`: puente canónico MusicXML/MEI/**kern ↔ `ScoreIR` | D9 |
| **6.1** | OMR-NED oficial con `musicdiff` (extra opcional) | D15 |
| **6.2** | Descargador + manifiesto del corpus acotado | D17 |
| **6.3** | Experimentos reales con HOMR (calidad, esfuerzo, AL) | D18, D19 |

## Criterios de aceptación (Definition of Done)

- [ ] `interchange` parsea una salida real de HOMR y un MEI de PrIMuS sin tocar el dominio.
- [ ] `music21` no aparece en `packages/domain` ni en `packages/validation` (pureza preservada).
- [ ] OMR-NED oficial calculado sobre al menos un par predicho/ground-truth.
- [ ] Corpus descargable de forma reproducible con manifiesto (ids, sha256, split).
- [ ] HOMR corre en el corpus (GPU o CPU documentado) y produce MusicXML.
- [ ] Experimentos reales exportados a `results/` con semilla y hash del corpus.
- [ ] Gates verdes: `pytest`, `mypy --strict`, `ruff`.
- [ ] `PROJECT_STATE.md` actualizado (fase, deuda, bitácora).
