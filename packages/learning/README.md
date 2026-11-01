# cadenza-learning

Aprendizaje activo por lotes (M4, ADR-0008). Componentes:

- `DatasetBuilder` — deriva `TrainingSample` alineadas por ancla desde
  `ScoreDocument` + `EditEvent` + `Finding`.
- `AcquisitionStrategy` (puerto) — `UncertaintyAcquisition` (baseline),
  `DiversityAcquisition` y `HybridAcquisition` (apuesta principal).
- `evaluation` — `symbol_error_rate` y `normalized_edit_distance`.
- `ModelRegistry` — versiones con métricas y **promoción gobernada por umbral**.
- `Trainer` (puerto) + `FakeTrainer` — pipeline offline determinista para tests. No trae
  métricas propias: las recibe de quien lo llama y marca su resultado como simulado
  (`TrainedArtifact.simulated`), porque no evalúa el modelo
  ([#271](https://github.com/sebdavid3/Cadenza/issues/271)).
- `suggestions` — entrenamiento y medición de la capa de sugerencias
  ([ADR-0036](../../docs/adr/ADR-0036-capa-de-sugerencias-aprendida.md)), que sustituye a la red
  de `PyTorchTrainer`, retirada en #271.

El ajuste fino real del modelo de reconocimiento es trabajo futuro
([#103](https://github.com/sebdavid3/Cadenza/issues/103)).
