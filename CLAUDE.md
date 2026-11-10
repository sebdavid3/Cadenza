# Reglas Permanentes de Desarrollo — Cadenza

> Este archivo gobierna el comportamiento y las directrices operativas de cualquier
> sesión de trabajo en el repositorio Cadenza. Toda sesión arranca bajo estas reglas.
> El estado del proyecto no vive aquí, sino en `docs/PROJECT_STATE.md`.

---

## 1. Dónde está la verdad (Fuentes del Sistema)

No fiarse de la memoria conversacional; consultar siempre los documentos versionados:

- **`docs/PROJECT_STATE.md`:** Memoria viva del proyecto: fase actual, próximo paso, deuda técnica y bitácora. Es lo primero que se lee.
- **`docs/ARCHITECTURE.md` (v1.2):** Arquitectura objetivo. Principalmente §6 (casos de uso, puertos y endpoints), §7 (modelo de datos) y §10 (estado real frente al objetivo).
- **`docs/adr/`:** Decisiones arquitectónicas aceptadas, con su índice en `docs/adr/README.md`. **Si un issue y un ADR se contradicen, prevalece el ADR.**
- **`docs/api/frontend-handoff.md` y `docs/api/openapi.json`:** Contrato de la API v1 (solo admite cambios compatibles) y guía de integración para el frontend. La vista de una sesión (elegir, corregir, insertar y borrar, deshacer, descartar y revalidar) la fijan ADR-0027 a ADR-0035 y ADR-0058; su historia, `docs/phases/phase_8_web_interface/README.md`.
- **`docs/infra/operacion_backend.md`:** Despliegue, monitoreo (`/health`), logs estructurados, copias de seguridad, GPU y los interruptores de producción.
- **`docs/CONVENTIONS.md`:** Convenciones de Git, calidad, niveles de cambio y Definition of Done.
- **`docs/phases/plan_de_cierre/README.md`:** Plan de cierre del proyecto (seguimiento en #231): resultado final, límites, carriles y orden de los issues.
- **`docs/investigaciones/`:** Investigaciones técnicas (índice en su `README.md`).
- **GitHub (`sebdavid3/Cadenza`):** Issues y milestones. Los PR van contra `dev`, que no es la rama por defecto: **«Closes #N» no cierra el issue; hay que cerrarlo a mano** tras fusionar.

---

## 2. Lo que hay que saber antes de empezar

El detalle y las fechas, en `docs/PROJECT_STATE.md`. Lo que no cambia de una sesión a otra:

- **Fase:** plan de cierre en curso; el estudio con participantes está aplazado (2026-11-08), con fechas nuevas por decidir y un piloto antes. Cuando se fijen, del congelado al final del estudio no se despliega nada, salvo un arreglo que lo bloquee y con decisión del responsable. El estandarte del proyecto es la capa de sugerencias que aprende de las correcciones (Fase 11, etiqueta `estandarte`).
- **Producción** sigue la rama `dev`: un clon en `/opt/docker/cadenza` del servidor `r2d2` (`ssh r2d2`, o `ssh r2d2-cf` si Tailscale no responde), publicado en `https://r2d2.tailcacb19.ts.net` y `https://cadenza.sebdavid.dev`. Se despliega con `deploy/desplegar.sh` (nivel 1, §4). HOMR corre en CPU.
- **`main`** es la versión publicada: se promueve desde `dev` cuando lo pide el responsable (§5). El despliegue continuo desde `main` (ADR-0062) está listo pero sin activar.
- **La CI de GitHub no arranca** (D69, un cobro pendiente de la cuenta): las puertas locales de `scripts/puertas.py` la sustituyen, con su línea en el PR.
- **Interruptores de producción** (`.env` del servidor): cada uno se enciende o se apaga solo cuando lo pide el responsable, con el procedimiento de `operacion_backend.md` §2.2.
- **Contrato:** los PR que regeneran `openapi.json` y `types.ts` se fusionan de uno en uno, rebasando y regenerando antes de fusionar.
- **Fuera de la entrega:** los issues del milestone «Trabajo futuro (fuera del alcance)» (etiqueta `fuera de alcance`) no se implementan sin consultar.

Al empezar una fase nueva, lo primero es planificarla: milestone e issues con contexto, objetivo, criterios de aceptación y dependencias.

---

## 3. Manejo de Contexto y Persistencia

1. **Memoria en el repo y en GitHub:** vive en los archivos versionados y en los issues/PR, no en la conversación.
2. **Actualización permanente:** al cerrar cada issue, una fila en la bitácora de `docs/PROJECT_STATE.md` y la deuda si cambia. La cabecera se toca solo si cambian la fase o el próximo paso, en una o dos frases: el detalle va en la fila. Lo que se opera sin código (nivel 1, §4) se anota en el siguiente PR.
3. **Protocolo de arranque:** para empezar un issue de código, `git status`, `git fetch origin`, `gh pr list` y la cabecera de `docs/PROJECT_STATE.md`; si hay una rama o un PR propios a medias, se concluyen antes. Para una consulta o una operación basta con `git status` y `git fetch origin`.
4. **Carga mínima por issue:** leer solo el issue, los ADR y secciones que cita y los paquetes afectados.
5. **Subagentes para lo voluminoso:** exploraciones amplias de código y la revisión independiente que pide el nivel del cambio.
6. **Una rama y un PR por issue.** Varias sesiones pueden trabajar a la vez, cada una en su issue y en su propio worktree (§7), sin tocar los mismos archivos.

---

## 4. Flujo de Trabajo por Issue

**Tres niveles, según lo que toque el cambio** (decisión del responsable del 2026-11-10, #382): los cambios sencillos han de ser rápidos. Ante la duda, o si un cambio mezcla niveles, manda el más alto. Detalle en `docs/CONVENTIONS.md` §5.1.

- **Nivel 1, operar sin código** (~1 min): desplegar `dev` (`deploy/desplegar.sh`), promover a `main`, cambiar una variable del `.env` de producción o hacer una copia. Se sigue `docs/infra/operacion_backend.md` y se comprueba en producción. Sin rama, PR ni puertas: la línea de la bitácora va en el siguiente PR, o en uno de nivel 2 si no hay otro.
- **Nivel 2, solo documentación** (~1 min): solo archivos `.md` fuera de `apps/web`. Rama, PR y *squash*, sin puertas ni revisión con subagente: ninguna prueba lee esos archivos, salvo `docs/experimentos/protocolo_medicion_esfuerzo.md` (con él, `pytest apps/api/tests/test_prepare_study_participant.py`).
- **Nivel 3, código** (5–10 min con el despliegue): cualquier otro archivo. El flujo de abajo entero, con las puertas solo de lo que se tocó (§6) y la revisión con subagente solo si toca la API, la persistencia o las migraciones, el dominio o la aplicación, el contrato, la autenticación o las cuentas, o pasa de unas 200 líneas sin contar las pruebas; si no, basta releer uno mismo el diff.

1. **Sincronizar:** `git switch dev`, `git pull --ff-only`, árbol limpio.
2. **Estudiar:** leer el issue completo y la documentación y el código que cita.
3. **Ramificar:** rama `<tipo>/<número>-<descripción-corta>`.
4. **TDD (nivel 3):** primero las pruebas que expresan los criterios de aceptación, después el código. En los fallos, reproducir el fallo con un test antes de corregirlo.
5. **Verificar calidad:** las puertas que pide su nivel (§6). Si falla una, se repite solo esa (`--solo`). No se comitea a mitad de una pasada.
6. **Revisión:** la que pide su nivel; la independiente, con un subagente de contexto limpio, y subsanando los hallazgos.
7. **Documentar:** `docs/PROJECT_STATE.md` (§3.2), `docs/ARCHITECTURE.md` §10 si cambia el estado, README si cambia el uso y un ADR nuevo si hubo una decisión arquitectónica.
8. **PR y fusión:** PR hacia `dev` con la línea de las puertas (sustituye a la CI mientras esté bloqueada, D69), fusión con *squash* y borrado de la rama. Si hay que desplegar, `deploy/desplegar.sh` (nivel 1).
9. **Cierre:** cerrar el issue a mano con `gh issue close <N> --comment "..."` y actualizar el issue de seguimiento si lo hay.

---

## 5. Política de Ramas, Commits, PRs y Migraciones

### Ramas
- `main` solo se actualiza promoviendo `dev`, cuando lo pide el responsable: un PR de `dev` a `main` fusionado con commit de fusión (`gh pr merge --merge`, título `release: promover dev a main (#261)`), nunca con push directo ni *squash*.
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
- Fusión mediante *squash* y borrado de la rama, de forma autónoma cuando estén en verde las puertas y la revisión que pide su nivel (§4).

### Migraciones
- Alembic, numeración secuencial, una por PR, con `upgrade()` y `downgrade()`.

---

## 6. Definition of Done

Un issue está terminado únicamente cuando:
1. Todos los criterios de aceptación se cumplen con evidencia demostrable.
2. En un cambio de código (nivel 3, §4), pasan sin errores las puertas de lo que se tocó, con `uv run --no-sync python scripts/puertas.py`; los niveles 1 y 2 no pasan puertas:
   - Python (`packages`, `apps/api`, `ml`, `scripts`, `deploy`, las migraciones, `pyproject.toml`, `uv.lock`): `--solo ruff,black,mypy,pytest` (~4 min).
   - Solo `apps/web`, sin tocar `types.ts`: `--solo lint,format:check,test,build` (~3 min).
   - Las dos, el contrato (`openapi.json`, `types.ts`, que comprueba `pytest`) o las dependencias de la web: todas, sin `--solo` (~6 min). Con `Dockerfile*`, el compose o `deploy/`, conviene además `--docker`.
3. Documentación actualizada e issue cerrado a mano en GitHub.
4. **Regla de integridad:** prohibido rebajar puertas, silenciar tests, debilitar el tipado estricto o insertar `# type: ignore` sin justificación explícita.

---

## 7. Entorno

- **Nunca ejecutar `uv sync` a secas.** HOMR y `onnxruntime-gpu==1.26.0` se instalan como extras a mano (ver README) y un `uv sync` normal los desinstala sin avisar; los tests del motor real pasan entonces a omitirse y nadie lo nota. Usar `uv sync --inexact` y `uv run --no-sync`. Si un test del motor real aparece como omitido, comprobar primero que HOMR sigue instalado (`uv pip list`).
- **`results/` y `data/` no se tocan desde las pruebas.** Una guarda de sesión falla si un test escribe en `results/`. Nadie, tampoco un subagente revisor, ejecuta `ml/experiments` fuera de pytest: escribe en `results/`. Las pruebas de la API que no inyectan su almacén escriben en `./data/artifacts`: se les da uno o se usa `monkeypatch.chdir(tmp_path)`.
- **Contraseñas de prueba:** se generan con una llamada, nunca con un literal en el código (GitGuardian avisa de cada una).
- **Prettier solo sobre `apps/web`:** fuera de ella reformatea archivos enteros.
- **Sesiones en paralelo:** si otra sesión trabaja en la carpeta principal, se trabaja en un worktree aparte (`git worktree add -b <rama> <ruta> origin/dev`), sin cambiar la rama de la carpeta principal.
- **Shell en Windows:** los `.sh` se sacan con LF (`.gitattributes`); una copia sacada antes de eso puede tener CRLF y se rehace con `git checkout`.

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
- Las decisiones del responsable: el protocolo del estudio y sus fechas, la licencia, los objetivos de la tesis frente a lo entregado, qué se recorta, borrar o archivar salidas de `results/` y descargar corpus o páginas.
- Encender o apagar un interruptor de producción, desplegar o promover a `main` sin que lo haya pedido.
- Issues del milestone «Trabajo futuro (fuera del alcance)» y cualquier cambio del contrato de la API v1 que rompa compatibilidad.
- Credenciales reales, secretos de producción o servicios de pago.
- Acciones destructivas: borrado de `data/`, `results/` o `legacy/`, alteración de historia Git o push forzado.
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
