# cadenza-learning

Aprendizaje activo por lotes (M4, ADR-0008). Componentes:

- `DatasetBuilder` — deriva `TrainingSample` alineadas por ancla desde
  `ScoreDocument` + `EditEvent` + `Finding`.
- `AcquisitionStrategy` (puerto) — `UncertaintyAcquisition` (baseline),
  `DiversityAcquisition` y `HybridAcquisition` (apuesta principal).
- `evaluation` — `symbol_error_rate` y `normalized_edit_distance`.
- `ModelRegistry` — versiones con métricas y **promoción gobernada por umbral**.
- `Trainer` (puerto) + `FakeTrainer` — pipeline offline determinista para tests.

El entrenamiento real (PyTorch + pipeline de HOMR + export ONNX) y la métrica
OMR-NED con `musicdiff` quedan como deuda técnica: esta fase entrega el
esqueleto verificable y comparable.
