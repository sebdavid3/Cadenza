# Prototipo Legacy (MVP Original) — DEPRECADO

> [!WARNING]
> Este directorio contiene el prototipo MVP original de prueba de concepto (desarrollado antes de la arquitectura hexagonal de Cadenza).
> **Está formalmente deprecado y congelado.** No se debe añadir código nuevo aquí.

## Estado actual
- La arquitectura oficial de producción del sistema reside en `packages/` (núcleo de dominio, OMR, validación, persistencia, aprendizaje), `apps/api/` (API FastAPI) y `apps/web/` (interfaz React/TypeScript).
- La preservación histórica completa del prototipo MVP original se encuentra congelada en la etiqueta de Git:
  ```bash
  git checkout archive/legacy-mvp
  ```
- Para conocer la matriz de paridad de capacidades, el estado de cada componente y el procedimiento de retiro definitivo, consulta [`../docs/migracion_legacy.md`](../docs/migracion_legacy.md).
