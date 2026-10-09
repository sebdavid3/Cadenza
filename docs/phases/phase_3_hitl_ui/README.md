# Fase 3 — Interfaz HITL (editor y eventos)

**Objetivo:** construir la interfaz *Human-in-the-Loop* que permita revisar,
escuchar y **corregir** la transcripción, registrando cada corrección como
`EditEvent` inmutable anclado.

Referencias: [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md) §5 (M3),
[ADR-0002](../../adr/ADR-0002-score-document-anchor-index.md),
[ADR-0006](../../adr/ADR-0006-render-editor-osmd-verovio-zustand.md),
[ADR-0007](../../adr/ADR-0007-edit-events-inmutables.md).

---

## Requerimientos

1. Correcciones modeladas como **`EditEvent` inmutables** sobre anclas; el estado
   actual se materializa aplicando la secuencia de eventos sobre el `ScoreIR` crudo.
2. Operaciones: `SetPitch`, `SetDuration`, `SetAccidental`, `InsertEvent`,
   `DeleteEvent`, `SetClef`, `SetKey`.
3. Renderizado con **OSMD instrumentado** para exponer el mapa `Anchor → elemento
   SVG`; **Verovio** como alternativa de evolución.
4. Estado del editor con **Zustand** (incluye undo/redo) y estado remoto con
   **TanStack Query**; frontend migrado a **TypeScript**.
5. **Overlays** de findings sobre la partitura y selección cruzada imagen↔nota.
6. Reproducción con **Tone.js** y **cursor sincronizado** (mapa tiempo→ancla).
7. Captura de métricas de esfuerzo: tiempo de edición e intervenciones por compás.
8. Imagen original en paralelo, con recorte por ancla cuando exista `bbox`.

## Fuera de alcance (Out-of-Scope)

- Reentrenamiento o ajuste del modelo (Fase 4).
- Autenticación multiusuario y control de acceso.
- Símbolos de expresión no incluidos en el alcance (matices avanzados,
  articulaciones complejas).

## Criterios de aceptación (Definition of Done)

- [ ] Corrección de nota (altura/duración/alteración) persistida como `EditEvent`.
- [ ] Undo/redo operativo y coherente con el log de eventos.
- [ ] Overlays de findings visibles y anclados correctamente.
- [ ] Reproducción con cursor sincronizado funcionando.
- [ ] Métricas de esfuerzo capturadas y almacenadas.
- [ ] `PROJECT_STATE.md` actualizado.
