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
- **`docs/adr/ADR-0001` a `ADR-0035`:** Decisiones arquitectónicas aceptadas. **Si un issue y un ADR se contradicen, prevalece el ADR.**
- **`docs/api/frontend-handoff.md` y `docs/api/openapi.json`:** Contrato congelado de la API v1 y guía de integración para el frontend.
- **`docs/infra/operacion_backend.md`:** Procedimientos de despliegue, monitoreo (`/health`), logs estructurados, copias de seguridad y ejecución en GPU.
- **`docs/CONVENTIONS.md`:** Convenciones de Git, calidad y Definition of Done.
- **`docs/phases/plan_de_cierre/README.md`:** Plan de cierre del proyecto (26 de octubre – 15 de noviembre de 2026): resultado final, límites, calendario, carriles y orden de los issues.
- **`docs/investigaciones/`:** Investigaciones técnicas (INV-0001: coordenadas y confianza de HOMR; INV-0002: Audiveris frente a HOMR).
- **GitHub (`sebdavid3/Cadenza`):** Issues y milestones. Los PR van contra `dev`, que no es la rama por defecto: **«Closes #N» no cierra el issue; hay que cerrarlo a mano** tras fusionar.

---

## 2. Estado y trabajo siguiente

- **Fase 7 (backend):** cerrada. El backend está completo y el contrato de la API v1, congelado.
- **Verificación de evidencia (milestone 2):** corrigió los resultados experimentales que figuraban como medidos sin serlo (#106 cerrado con transcripción síncrona ratificada; #99 cerrado con PostgreSQL en CI). #100 (línea base de oemer) se cerró como «no se hará»: HOMR es el único motor OMR (ADR-0018, #130).
- **Fase 8 (frontend), hecho:** `apps/web` sobre la API v1, publicada en `https://r2d2.tailcacb19.ts.net`. Incluye la landing, el registro y el acceso, la transcripción por lotes, la vista de una sesión (partitura con OSMD, posibles errores, descarga del MusicXML, reproducción con Tone.js, selección de una nota con su ancla, #182 y ADR-0027, corrección de su altura, su duración y su alteración, #183 y ADR-0030, las marcas de notación de la partitura: articulaciones, calderones, ligaduras de expresión, dinámicas y reguladores, #213 y ADR-0031, las varias voces de un pentagrama con su ritmo y las plicas separadas, #218 y ADR-0032, insertar y borrar eventos y cambiar la clave y la armadura, #184 y ADR-0033, deshacer y rehacer con la historia de ediciones, #185 y ADR-0034, y descartar, restaurar y revalidar los posibles errores, #186 y ADR-0035, desplegados en #229 sin comprobar con sesión) y la moderación de cuentas. Detalle en `docs/phases/phase_8_web_interface/README.md`. Punto de partida para integrar: `docs/api/frontend-handoff.md`.
  - Lo hecho que condiciona lo siguiente: #184 deja elegido tras guardar el evento nuevo o el que ocupa el sitio del borrado; #213 y #218 cambiaron la instantánea de `DeleteEvent` y lo que admite `InsertEvent`, y #218 hace del hueco de una voz un silencio invisible con ancla, `hidden`, que la vista no ofrece para elegir; #185 rehace reenviando la edición deshecha y lee las pilas del log (`pages/session/history.ts`); #186 descarta cada posible error, no el compás, numera los de un compás con varios y revalida solo bajo demanda, leyendo el `current_seq` que devuelve `POST /validate`, con el editor en espera mientras tanto; una revalidación solo hereda los descartes de la validación vigente (ADR-0035).
- **Plan de cierre (26 de octubre – 15 de noviembre de 2026), acordado el 2026-10-25:** `docs/phases/plan_de_cierre/README.md` y el seguimiento #231 fijan el resultado final, los límites, el calendario, tres carriles y el orden de los issues. **Congelado del sistema el 2026-11-08** (#252) y estudio con participantes del 9 al 15 de noviembre (#253): lo que no esté desplegado el 8 no entra en el estudio, y entre el 9 y el 15 no se despliega nada sin decisión del responsable. Milestones:
  - **Fase 8, interfaz web** (8 nov): #187 (finalizar y reabrir; finalizar debe conservar los descartes, D65), #214 (añadir y quitar marcas; su ADR fija la política de `EditOp` para el dataset y las métricas), #235 (título, compositor e instrumentos), #240 (formulario antes de transcribir), #241 (compás y tresillos en la barra), #242 (sonido por instrumento), #243 (figura de un acorde, D61), #188 (métricas de esfuerzo, tras #187 y #244), #189 (MIDI) y #190 (contraseña).
  - **Fase 9, reconocimiento y reglas** (8 nov): #234 (conjunto de referencia), #236 (compás con su símbolo y tresillos en el dominio), #237 (reconocer el compás por tramos, C y ¢, y los tresillos implícitos, en una etapa fuera de `HOMREngine`), #238 (cambios de armadura), #239 (voz superior y piano), #245 (ADR de reglas y mensajes en lenguaje musical) y #246 (implementarlas y volver a medir `exp_06`).
  - **Fase 10, estudio de esfuerzo** (15 nov): #244 (definiciones del protocolo, las decide el responsable), #247 (banco TS-01 a TS-04), #248 (registro cerrado durante el estudio), #249 (cuentas y sesiones de cada participante), #250 (fidelidad residual y NASA-TLX en `exp_10`), #251 (piloto), #252 (congelado), #253 (sesiones), #254 (análisis) y #226.
  - **Fase 11, aprendizaje de las correcciones** (15 nov): #255 (corpus de correcciones), #256 (capa de post-corrección que propone, sin reentrenar HOMR), #257 (validación cruzada y curva de aprendizaje) y #258 (opcional).
  - **Cierre del proyecto** (15 nov): #232 (este plan en el repositorio), #233 (INV-0002), #259 (licencia), #260 (documentación final) y #261 (despliegue final y `dev` → `main`, que hace el responsable).
- **Coordinación:** los PR que regeneran `openapi.json` y `types.ts` se fusionan de uno en uno, en este orden: #214 → #235 → #236 → #243 (si cambia el contrato) → #258, rebasando y regenerando antes de fusionar.
- **Fuera de la entrega (milestone «Trabajo futuro», etiqueta `fuera de alcance`; no implementar sin consultar):** #262 (matices con Audiveris, INV-0002), #263 (título y letra leídos de la imagen), #264 (D62 y D64), #102 (SMB y MUSCIMA++), #103 (reentrenar HOMR, D14 y D53), #194 (políticas completas del registro, D59) y #215 (volumen según los matices).

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
   - Si se modificó `apps/web`, incluido `apps/web/src/types.ts` al regenerar el contrato: `npm run test` y `npm run build` en `apps/web` (la CI pasa además `npm run lint` y `npm run format:check`). La sincronía de `types.ts` con el contrato la comprueba también `pytest`.
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
- Issues del milestone «Trabajo futuro (fuera del alcance)» (#102, #103, #194, #215, #262, #263 y #264) y cualquier cambio del contrato de la API v1 que rompa compatibilidad.
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
