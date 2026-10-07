# Reglas Permanentes de Desarrollo — Fase 7 (Cadenza)

> Este archivo gobierna el comportamiento y las directrices operativas para la ejecución
> autónoma de la Fase 7 en el repositorio Cadenza. Toda sesión arranca bajo estas reglas.

---

## 1. Dónde está la verdad (Fuentes del Sistema)

No fiarse de la memoria conversacional; consultar siempre los documentos versionados:

- **`docs/ARCHITECTURE.md` (v1.2):** Arquitectura objetivo. Consultar principalmente:
  - §6: Casos de uso, puertos y endpoints.
  - §7: Modelo de datos y esquemas relacionales.
  - §10.2: Matriz de brechas entre el MVP/Fase 6 y el objetivo.
- **`docs/adr/ADR-0001` a `ADR-0012`:** Decisiones arquitectónicas aceptadas. En particular:
  - ADR-0009: Capa de aplicación hexagonal (`packages/application`).
  - ADR-0010: `ScoreIR` con clave y armadura; exportación en `packages/interchange`.
  - ADR-0011: Anclas relativas a un estado (`base_seq`) y traducción posicional.
  - ADR-0012: Autenticación con JWT, usuarios y sesiones privadas.
  - **Jerarquía:** Si un issue y un ADR se contradicen, **prevalece el ADR**.
- **`docs/PROJECT_STATE.md`:** Memoria viva del proyecto, inventario de deuda técnica (D1–D47) y bitácora de hitos.
- **`docs/CONVENTIONS.md`:** Convenciones de Git, calidad y Definition of Done.
- **`docs/phases/phase_7_architecture_alignment/README.md`:** Alcance y desglose de la Fase 7.
- **GitHub (`sebdavid3/Cadenza`):** Milestone *"Fase 7: Alineación con la arquitectura objetivo"*. Issue #1 (seguimiento general) e issue #39 (seguimiento de autenticación).

---

## 2. Manejo de Contexto y Persistencia

1. **Memoria en el repo y en GitHub:** La memoria vive en los archivos versionados y en los issues/PRs, no en la ventana de contexto de la sesión.
2. **Actualización permanente:** Al cerrar cada issue se actualiza la deuda técnica y la bitácora en `docs/PROJECT_STATE.md`. Nunca dejar trabajo terminado sin registrar.
3. **Protocolo de arranque:**
   - Inspeccionar árbol: `git status`.
   - Inspeccionar ramas locales y sincronización con remoto: `git branch -a`, `git fetch origin`.
   - Verificar PRs pendientes: `gh pr list`.
   - Listar issues abiertos del milestone: `gh issue list --milestone "Fase 7: Alineación con la arquitectura objetivo"`.
   - Leer cabecera de `docs/PROJECT_STATE.md`.
   - Si existe una rama o PR a medias, concluirlo antes de empezar otro trabajo.
4. **Carga mínima por issue:** Leer únicamente el issue a trabajar, los ADRs/secciones citados y los paquetes afectados. Evitar leer `ARCHITECTURE.md` completo en cada iteración.
5. **Subagentes para lo voluminoso:** Emplear subagentes para exploraciones amplias de código y para revisión de diffs antes de cada merge.
6. **Un issue a la vez:** 1 issue = 1 rama = 1 PR. No abrir el siguiente issue hasta fusionar el anterior (única excepción conjunta: #45 y #47).

---

## 3. Orden de Trabajo por Etapas

Seguir estrictamente el orden establecido. Tomar el primer issue abierto cuyas dependencias estén cerradas:

| Etapa | Issues | Objetivo |
|---|---|---|
| **0** | Paso 0 (sin issue) | `CLAUDE.md` y política en `docs/CONVENTIONS.md` |
| **1** | #25, #7, #2, #4 | CI, capa de aplicación, ScoreIR extendido, almacén de artefactos |
| **Inv.** | #14 y #31 juntas | Investigaciones HOMR tras concluir Etapa 1 |
| **2** | #3, #28, #32, #5, #8, #43, #44, #45 con #47, #46 | Motor real en API y autenticación completa |
| **3** | #9, #10, #48, #11, #34, #27, #12, #13, #35, #36, #6 | API completa y PostgreSQL real |
| **4** | #17, #20, #30, #18 | Reglas de validación medidas sobre errores reales |
| **5** | #19, #21, #22, #23 | Plano offline |
| **6** | #24, #29, #33, #15, #16 | Evidencia experimental |
| **Cierre** | #26, luego #39 y #1 | Contrato de API congelado |

*Nota:* Investigaciones #14, #31 y el issue #23 pueden cerrarse con resultado negativo documentado tras un esfuerzo acotado.  
*Exclusiones:* **No implementar** #37, #40, #41 ni #42 (alcance por decidir).

---

## 4. Flujo de Trabajo por Issue

1. **Sincronizar:** `git switch dev`, `git pull --ff-only`, verificar árbol limpio.
2. **Estudiar:** Leer issue completo y documentación/código referenciado.
3. **Ramificar:** Crear rama `<tipo>/<número>-<descripción-corta>`.
4. **TDD:** Escribir primero las pruebas que expresan los criterios de aceptación y luego el código. En issues de tipo corrección (bug), reproducir el fallo con un test antes de resolverlo.
5. **Verificar calidad:** Ejecutar la suite completa de puertas de calidad (DoD).
6. **Revisión independiente:** Revisar el diff con un subagente de contexto limpio. Subsanar cualquier hallazgo.
7. **Documentar:** Actualizar `docs/PROJECT_STATE.md` (deuda y bitácora), §10.2 de `docs/ARCHITECTURE.md`, README si afecta uso, y registrar ADR nuevo si se tomó una decisión arquitectónica.
8. **PR y Fusión:** Abrir PR hacia `dev`, esperar CI en verde, fusionar con *squash* y eliminar la rama.
9. **Cierre:** Verificar cierre automático del issue en GitHub y marcar casilla en issue #1 (y en #39 si corresponde a autenticación).

---

## 5. Política de Ramas, Commits, PRs y Migraciones

### Ramas
- `main` es intocable (sin push, merge directo ni PR).
- `dev` es la única rama de integración y solo recibe cambios mediante PR.
- Formato de ramas: `<tipo>/<número>-<descripción-corta>`.
  - Tipos válidos: `feature`, `fix`, `refactor`, `docs`, `chore`.
- Ramas de vida corta: si `dev` avanzó, actualizar rama antes de abrir PR. Prohibido reescribir historia publicada o forzar push (`--force`).

### Commits
- Formato **Conventional Commits** en **español**, en modo **imperativo**, minúscula inicial, sin punto final:
  `<tipo>(<scope>): <descripción>`
- Tipos: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `build`, `ci`.
- Scopes: `domain`, `application`, `interchange`, `omr`, `validation`, `persistence`, `learning`, `api`, `web`, `infra`, `docs`.
- Commits atómicos y coherentes. Cuerpo explicando la motivación técnica y terminando con `Refs #N`.
- Añadir archivos exclusivamente con rutas explícitas (prohibido `git add -A` o `git add .`).
- No comitear `.env`, secretos, `data/`, `results/` ni artefactos generados.
- Prohibido saltar hooks o usar `--no-verify`.

### Pull Requests
- Título: `<tipo>(<scope>): <descripción> (#N)`.
- Cuerpo: resumen de cambios, checklist de criterios de aceptación con evidencia de verificación, decisiones técnicas y `Closes #N`.
- Fusión mediante *squash* y borrado de la rama (un commit resultante por issue en `dev`).
- Fusión autónoma cuando linters, tests, CI y revisión estén en verde.

### Migraciones
- Alembic, numeración secuencial (`0003_…`), una por PR, implementando tanto `upgrade()` como `downgrade()`.

---

## 6. Definition of Done (Criterio de Terminado)

Un issue está terminado únicamente cuando:
1. Todos los criterios de aceptación se cumplen con evidencia demostrable.
2. Pasan sin errores ni advertencias bloqueantes:
   - `uv run pytest`
   - `uv run mypy packages apps`
   - `uv run ruff check .`
   - `uv run black --check .`
   - Si se modificó `apps/web`: `npm run test` y `npm run build` en `apps/web`.
3. Documentación actualizada y issue cerrado.
4. **Regla de integridad:** Prohibido rebajar puertas, silenciar tests, debilitar tipado estricto o insertar `# type: ignore` sin justificación explícita.

---

## 7. Autonomía y Límites Operativos

### Acciones autónomas (sin confirmación del usuario)
- Todo diseño técnico compatible con los ADRs existentes.
- Decisiones técnicas no cerradas por un issue: optar por la solución más simple coherente con los ADRs y registrarla en un nuevo ADR.
- Incorporar dependencias pequeñas y estándar requeridas por los ADRs (e.g. hashing de contraseñas, JWT, settings tipados).

### Detenerse y consultar al usuario
- Dudas o decisiones sobre issues con alcance por definir (#37, #40, #41, #42).
- Cualquier requerimiento de credenciales reales, secretos de producción o servicios de pago.
- Acciones destructivas: borrado de `data/`, `results/` o `legacy/`, alteración de historia Git, push forzado o tocar `main`.
- Contradicciones insolubles entre ADRs.

### Manejo de bloqueos
- Tras **3 intentos fallidos** en el mismo problema:
  1. Registrar comentario en el issue detallando intentos y error exacto.
  2. Continuar con el siguiente issue independiente en el orden de trabajo.
  3. No paralizar la ejecución completa por un bloqueo local.

---

## 8. Reglas Arquitectónicas Invariables

1. **Pureza de Dominio:** `packages/domain` utiliza únicamente la biblioteca estándar de Python (verificado por test de pureza).
2. **Aislamiento de Aplicación:** `packages/application` no importa FastAPI, SQLAlchemy, music21, homr ni onnxruntime.
3. **Encapsulamiento de notación:** `music21` solo se importa dentro de `packages/interchange`.
4. **Inmutabilidad del log:** El log de ediciones (`EditEvent`) es append-only; jamás se persiste una edición inválida.
5. **Anclas y concurrencia:** Toda ancla es relativa a un estado; cada edición transporta `base_seq` y nunca se reintenta automáticamente con otro número de secuencia (ADR-0011).
6. **Autoría en servidor:** El autor de un evento de edición lo fija el servidor a partir del token del usuario autenticado (ADR-0012).
7. **Desacoplamiento online/offline:** Los planos online y offline se comunican exclusivamente mediante datos persistidos.
8. **Inviolabilidad de Legacy:** La carpeta `legacy/` es inmutable y su funcionamiento no debe alterarse.
