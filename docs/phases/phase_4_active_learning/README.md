# Fase 4 — Aprendizaje Activo y Model Registry

**Objetivo:** cerrar el ciclo de mejora continua usando las correcciones humanas
para seleccionar muestras de valor y hacer *fine-tuning* **batch** del modelo de
reconocimiento, con promoción gobernada al plano online.

Referencias: [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md) §5 (M4),
[ADR-0003](../../adr/ADR-0003-separacion-planos-computo.md),
[ADR-0004](../../adr/ADR-0004-persistencia-postgresql-jsonb.md),
[ADR-0008](../../adr/ADR-0008-active-learning-model-registry.md).

---

## Requerimientos

1. **`DatasetBuilder`:** traduce `(imagen, ScoreIR crudo, ScoreIR corregido,
   EditEvents)` a tuplas de entrenamiento compatibles con el pipeline de HOMR,
   alineando por anclas.
2. **`AcquisitionStrategy` (puerto)** con implementaciones comparables:
   - `UncertaintyAcquisition` — línea base (reproduce el hallazgo de AL-003);
   - `DiversityAcquisition` — cobertura del espacio de características;
   - `HybridAcquisition` — **apuesta principal**: densidad de errores del
     validador + magnitud de corrección + diversidad.
3. **`Trainer`** en PyTorch con configuración versionada y semillas fijas.
4. Exportación a **ONNX** e introducción en el **`Model Registry`**.
5. **Promoción gobernada por umbral** de evaluación; nunca automática.
6. Evaluación con métricas **SER** y **OMR-NED** (`musicdiff`).
7. Reproducibilidad: dataset y artefactos direccionados por hash; config en `configs/`.

## Fuera de alcance (Out-of-Scope)

- **TFLite / Edge Learning / entrenamiento en el dispositivo.**
- **LLM / VLM** y cualquier post-proceso basado en modelos de lenguaje.
- Aprendizaje continuo/online dentro del request.
- Despliegue distribuido o autoescalado.

## Criterios de aceptación (Definition of Done)

- [ ] `DatasetBuilder` genera tuplas alineadas por anclas y verificables.
- [ ] Las tres estrategias de adquisición son intercambiables y comparables.
- [ ] Job de *fine-tuning* reproducible (semillas + config versionada).
- [ ] Modelo exportado a ONNX y registrado con métricas (SER/OMR-NED).
- [ ] Promoción condicionada a umbral; versión trazada en `Provenance`.
- [ ] Informe de evaluación del experimento generado.
- [ ] `PROJECT_STATE.md` actualizado.
