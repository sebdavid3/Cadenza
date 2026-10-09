# Fase 1 — Adaptador OMR (`OMREngine`)

**Objetivo:** encapsular la transcripción OMR detrás del puerto `OMREngine` e
integrar HOMR **in-process** sobre `onnxruntime`, sustituyendo la invocación por
`subprocess` del prototipo, sin romper el flujo E2E.

Referencias: [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md) §5 (M1),
[ADR-0001](../../adr/ADR-0001-monolito-modular-hexagonal.md),
[ADR-0003](../../adr/ADR-0003-separacion-planos-computo.md),
[ADR-0005](../../adr/ADR-0005-motor-omr-homr-baseline-oemer.md).

---

## Requerimientos

1. Puerto `OMREngine.transcribe(image) → ScoreDocument` (contrato en `packages/omr`).
2. Adaptadores: `HomrEngine` (principal), `OemerEngine` (línea base),
   `FakeEngine` (tests/CI sin modelos ni GPU).
3. Integración **in-process**; se elimina el `subprocess` y el *scraping* de salida.
4. Preprocesado configurable (deskew, binarización, DPI) como etapa medible.
5. Reporte del dispositivo efectivo desde `onnxruntime.get_available_providers()`
   (`CUDAExecutionProvider` / `CPUExecutionProvider`), **nunca** desde `torch.cuda`.
6. Mapeo de la salida del motor al `ScoreDocument` (ScoreIR + AnchorIndex +
   Provenance), ocupando el contrato definido en Fase 0.

## Fuera de alcance (Out-of-Scope)

- Motor de validación (Fase 2), editor HITL (Fase 3), aprendizaje activo (Fase 4).
- *Fine-tuning* del modelo y export ONNX.
- Modelos de *deep learning* propios o nuevas arquitecturas.
- LLM/VLM y Edge/TFLite.

## Criterios de aceptación (Definition of Done)

- [ ] Transcripción E2E ejecutada **a través del puerto** `OMREngine`.
- [ ] `FakeEngine` permite probar sin dependencias pesadas (suite verde en CI).
- [ ] El hardware reportado proviene de `onnxruntime` y es verificable.
- [ ] `HomrEngine` y `OemerEngine` intercambiables sin tocar el dominio.
- [ ] El flujo E2E del prototipo sigue operativo tras la migración.
- [ ] `PROJECT_STATE.md` actualizado.
