# Reglas Permanentes de Desarrollo — Cadenza

> Este archivo gobierna el comportamiento y las directrices operativas de cualquier
> sesión de trabajo en el repositorio Cadenza. Toda sesión arranca bajo estas reglas.

---

## 1. Dónde está la verdad (Fuentes del Sistema)

No fiarse de la memoria conversacional; consultar siempre los documentos versionados:

- **`docs/PROJECT_STATE.md`:** Memoria viva del proyecto: fase actual, deuda técnica y bitácora. Es lo primero que se lee.
- **`docs/ARCHITECTURE.md` (v1.2):** Arquitectura objetivo. Consultar principalmente:
  - §6: Casos de uso, puertos y endpoints.
  - §7: Modelo de datos y esquemas relacionales.
  - §10: Estado real frente al objetivo.
- **`docs/adr/ADR-0001` a `ADR-0018`:** Decisiones arquitectónicas aceptadas. **Si un issue y un ADR se contradicen, prevalece el ADR.**
- **`docs/api/frontend-handoff.md` y `docs/api/openapi.json`:** Contrato congelado de la API v1 y guía de integración para el frontend.
- **`docs/infra/operacion_backend.md`:** Procedimientos de despliegue, monitoreo (`/health`), logs estructurados, copias de seguridad y ejecución en GPU.
- **`docs/CONVENTIONS.md`:** Convenciones de Git, calidad y Definition of Done.
- **GitHub (`sebdavid3/Cadenza`):** Issues y milestones. Los PR van contra `dev`, que no es la rama por defecto: **«Closes #N» no cierra el issue; hay que cerrarlo a mano** tras fusionar.

---

## 2. Estado y trabajo siguiente

- **Fase 7 (backend):** cerrada. El backend está completo y el contrato de la API v1, congelado.
- **Verificación de evidencia (milestone 2):** corrigió los resultados experimentales que figuraban como medidos sin serlo (#106 cerrado con transcripción síncrona ratificada; #99 cerrado con PostgreSQL en CI). #100 (línea base de oemer) se cerró como «no se hará»: HOMR es el único motor OMR (ADR-0018, #130).
- **Fase 8 (frontend), trabajo siguiente:** interfaz de corrección en `apps/web` sobre la API v1, construida desde cero (`apps/web` solo conserva los tipos generados, #129). Punto de partida: `docs/api/frontend-handoff.md`. Deuda asociada: D11 (render de notación con OSMD y reproducción con Tone.js).
- **Alcance por decidir (no implementar sin consultar):** #102 (evaluación real sobre SMB y MUSCIMA++) y #103 (ajuste fino real del modelo OMR), que no forman parte de la Fase 8.

Al empezar una fase nueva, lo primero es planificarla: milestone e issues con contexto, objetivo, criterios de aceptación y dependencias. Después se trabaja issue por issue con el flujo de la sección 4.

---

## 3. Manejo de Contexto y Persistencia

1. **Memoria en el repo y en GitHub:** vive en los archivos versionados y en los issues/PR, no en la conversación.
2. **Actualización permanente:** al cerrar cada issue se actualizan la deuda y la bitácora en `docs/PROJECT_STATE.md`.
3. **Protocolo de arranque:** `git status`, `git fetch origin` y `git branch -a`, `gh pr list`, issues abiertos del milestone en curso y cabecera de `docs/PROJECT_STATE.md`. Si hay una rama o un PR a medias, se concluye antes de empezar otra cosa.
4. **Carga mínima por issue:** leer solo el issue, los ADR y secciones que cita y los paquetes afectados.
5. **Subagentes para lo voluminoso:** exploraciones amplias de código y revisión de diffs antes de cada fusión.
6. **Un issue a la vez:** 1 issue = 1 rama = 1 PR.

---

## 4. Flujo de Trabajo por Issue

1. **Sincronizar:** `git switch dev`, `git pull --ff-only`, árbol limpio.
2. **Estudiar:** leer el issue completo y la documentación y el código que cita.
3. **Ramificar:** rama `<tipo>/<número>-<descripción-corta>`.
4. **TDD:** primero las pruebas que expresan los criterios de aceptación, después el código. En los fallos, reproducir el fallo con un test antes de corregirlo.
5. **Verificar calidad:** todas las puertas de la sección 6.
6. **Revisión independiente:** revisar el diff con un subagente de contexto limpio y subsanar los hallazgos.
7. **Documentar:** `docs/PROJECT_STATE.md` (deuda y bitácora), `docs/ARCHITECTURE.md` §10 si cambia el estado, README si cambia el uso y un ADR nuevo si hubo una decisión arquitectónica.
8. **PR y fusión:** PR hacia `dev`, CI en verde, fusión con *squash* y borrado de la rama.
9. **Cierre:** cerrar el issue a mano con `gh issue close <N> --comment "..."` y actualizar el issue de seguimiento si lo hay.

---

## 5. Política de Ramas, Commits, PRs y Migraciones

### Ramas
- `main` es intocable (sin push, merge directo ni PR). La promoción de `dev` a `main` la hace el responsable del proyecto.
- `dev` es la única rama de integración y solo recibe cambios mediante PR.
- Formato: `<tipo>/<número>-<descripción-corta>`, con tipos `feature`, `fix`, `refactor`, `docs`, `chore`.
- Ramas de vida corta. Prohibido reescribir historia publicada o forzar push.

### Commits
- **Conventional Commits** en **español**, en imperativo, minúscula inicial, sin punto final: `<tipo>(<scope>): <descripción>`.
- Tipos: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `build`, `ci`.
- Scopes: `domain`, `application`, `interchange`, `omr`, `validation`, `persistence`, `learning`, `api`, `web`, `infra`, `docs`.
- Commits atómicos. El cuerpo explica la motivación y termina con `Refs #N`.
- Añadir archivos solo con rutas explícitas (prohibido `git add -A` o `git add .`).
- No comitear `.env`, secretos, `data/`, `results/` ni artefactos generados.
- Prohibido saltar hooks o usar `--no-verify`.

### Pull Requests
- Título: `<tipo>(<scope>): <descripción> (#N)`.
- Cuerpo: resumen, criterios de aceptación con su evidencia, decisiones técnicas y `Closes #N`.
- Fusión mediante *squash* y borrado de la rama, de forma autónoma cuando linters, tests, CI y revisión estén en verde.

### Migraciones
- Alembic, numeración secuencial, una por PR, con `upgrade()` y `downgrade()`.

---

## 6. Definition of Done

Un issue está terminado únicamente cuando:
1. Todos los criterios de aceptación se cumplen con evidencia demostrable.
2. Pasan sin errores:
   - `uv run --no-sync pytest`
   - `uv run --no-sync mypy packages apps`
   - `uv run --no-sync ruff check .`
   - `uv run --no-sync black --check .`
   - Si se modificó la aplicación de `apps/web` (existe `apps/web/package.json`): `npm run test` y `npm run build` en `apps/web`. Regenerar `apps/web/src/types.ts` con `scripts/generate_openapi_and_types.py` no lo exige: su sincronía con el contrato la comprueba `pytest`.
3. Documentación actualizada e issue cerrado a mano en GitHub.
4. **Regla de integridad:** prohibido rebajar puertas, silenciar tests, debilitar el tipado estricto o insertar `# type: ignore` sin justificación explícita.

---

## 7. Entorno

- **Nunca ejecutar `uv sync` a secas.** HOMR y `onnxruntime-gpu==1.26.0` se instalan como extras a mano (ver README) y un `uv sync` normal los desinstala sin avisar; los tests del motor real pasan entonces a omitirse y nadie lo nota. Usar `uv sync --inexact` y `uv run --no-sync`.
- Si un test del motor real aparece como omitido, comprobar primero que HOMR sigue instalado (`uv pip list`).
- Los tests no escriben en `results/`: una guarda de sesión falla si lo hacen.

---

## 8. Integridad de los resultados experimentales

`results/` contiene la evidencia de la tesis. Reglas sin excepción:

1. **Un resultado es una medición.** Prohibido escribir cifras a mano, listas de casos «conocidos» o valores de reserva en un script de experimento. Si falta el motor, el corpus o una dependencia, el script falla con un mensaje claro.
2. **Lo simulado se marca.** Toda salida que no provenga de una ejecución real lleva `"simulated": true` y una advertencia, y no se cita en la documentación como resultado.
3. **La documentación distingue medido, simulado y pendiente.** Ninguna deuda se marca como resuelta apoyándose en datos simulados.
4. **Antes de citar una cifra, se regenera** ejecutando el script correspondiente y se comprueba que coincide.

---

## 9. Autonomía y Límites Operativos

### Acciones autónomas (sin confirmación del usuario)
- Todo diseño técnico compatible con los ADR existentes.
- Decisiones técnicas no cerradas por un issue: la solución más simple coherente con los ADR, registrada en un ADR nuevo.
- Incorporar dependencias pequeñas y estándar que el trabajo requiera.

### Detenerse y consultar al usuario
- Issues con alcance por decidir (#102, #103) y cualquier cambio del contrato de la API v1 que rompa compatibilidad.
- Credenciales reales, secretos de producción o servicios de pago.
- Acciones destructivas: borrado de `data/`, `results/` o `legacy/`, alteración de historia Git, push forzado o tocar `main`.
- Contradicciones insolubles entre ADR.

### Manejo de bloqueos
- Tras **3 intentos fallidos** en el mismo problema: comentar en el issue los intentos y el error exacto, y continuar con el siguiente issue independiente.

---

## 10. Reglas Arquitectónicas Invariables

1. **Pureza de dominio:** `packages/domain` usa solo la biblioteca estándar (verificado por test de pureza).
2. **Aislamiento de aplicación:** `packages/application` no importa FastAPI, SQLAlchemy, music21, homr ni onnxruntime.
3. **Encapsulamiento de notación:** `music21` solo se importa dentro de `packages/interchange`.
4. **Inmutabilidad del log:** el log de ediciones es append-only; jamás se persiste una edición inválida.
5. **Anclas y concurrencia:** toda ancla es relativa a un estado; cada edición lleva `base_seq` y nunca se reintenta con otro número de secuencia (ADR-0011).
6. **Autoría en servidor:** el autor de una edición lo fija el servidor a partir del usuario autenticado (ADR-0012).
7. **Desacoplamiento online/offline:** los planos se comunican exclusivamente mediante datos persistidos.
8. **`legacy/` congelado:** no se añade código ni se altera su funcionamiento.
9. **Contrato de la API v1:** `docs/api/openapi.json` se genera con `scripts/generate_openapi_and_types.py`; los tipos de `apps/web/src/types.ts` no se editan a mano.
