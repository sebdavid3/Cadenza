# Convenciones de Desarrollo — Cadenza

> **Contrato de calidad y control de versiones del proyecto.** De aplicación
> obligatoria para todo el equipo. Toda excepción debe justificarse en el PR.

| Campo | Valor |
|---|---|
| **Documento** | Convenciones de Desarrollo (CONVENTIONS.md) |
| **Versión** | 1.0 |
| **Estado** | Vigente |
| **Fecha** | 2026-09-20 |

---

## 1. Flujo de trabajo Git

### 1.1 Ramas

| Rama | Rol |
|---|---|
| `main` | **Sagrada.** Solo código de producción funcional. Intocable: no se hace push, merge directo ni PR hacia ella. |
| `dev` | Rama de **integración**. Punto de convergencia del desarrollo. Solo recibe cambios mediante Pull Request. |
| `<tipo>/<número>-<descripción-corta>` | Ramas de trabajo asociadas a issues específicos (p. ej. `refactor/7-capa-de-aplicacion`, `chore/25-integracion-continua`). |

**Tipos válidos de rama:** `feature`, `fix`, `refactor`, `docs`, `chore`.

### 1.2 Flujo de integración

1. Se parte **siempre** de `dev` actualizado (`git switch dev`, `git pull --ff-only`).
2. Se crea una rama dedicada para cada issue: `<tipo>/<número>-<descripción-corta>`.
3. Ramas de vida corta: si `dev` avanzó durante el desarrollo, se actualiza la rama antes de abrir el PR.
4. La integración a `dev` se realiza exclusivamente mediante **Pull Request** fusionado con *squash* y eliminación de la rama.
5. `main` se actualiza únicamente por promoción manual desde `dev` en hitos verificados.

```text
main  ←── (release / hito) ────────┐
  ▲                                │
dev   ←── (squash PR) ─────────────┘
  ▲
  └── <tipo>/<número>-<descripción-corta>
```

### 1.3 Higiene y control de versiones

- Commits pequeños y coherentes. Un commit = un cambio lógico completo.
- Se añaden archivos con **rutas explícitas**; prohibido el uso de `git add -A` o `git add .`.
- No se comitean secretos, credenciales, `.env`, datos crudos (`data/`), resultados experimentales (`results/`) ni artefactos generados (`node_modules/`, `.venv/`, `dist/`, cachés).
- No se reescribe historia publicada (`main`/`dev`) ni se utiliza `git push --force`.
- Prohibido saltar hooks o utilizar `--no-verify`.

---

## 2. Conventional Commits (OBLIGATORIO)

Todo mensaje de commit sigue el estándar Conventional Commits en **español**, en modo **imperativo**, con **minúscula inicial** y **sin punto final**:

```text
<tipo>(<scope>): <descripción en imperativo>
```

### 2.1 Tipos permitidos

| Tipo | Uso |
|---|---|
| `feat` | Nueva funcionalidad |
| `fix` | Corrección de defecto |
| `refactor` | Reestructuración sin cambio de comportamiento |
| `docs` | Documentación y gobernanza |
| `test` | Añadir o ajustar pruebas |
| `chore` | Mantenimiento, dependencias, configuración, tareas mecánicas |
| `perf` | Mejora de rendimiento |
| `build` | Sistema de construcción o empaquetado |
| `ci` | Integración continua y flujos de automatización |

### 2.2 Scopes oficiales

`domain`, `application`, `interchange`, `omr`, `validation`, `persistence`, `learning`, `api`, `web`, `infra`, `docs`.

### 2.3 Reglas

- Descripción en **imperativo**, minúscula inicial, sin punto final (p. ej. `añadir clave y armadura al ScoreIR`).
- El cuerpo del commit explica la motivación técnica cuando no es evidente y termina referenciando el issue: `Refs #N`.
- Breaking changes se indican con `!` tras el scope (p. ej. `feat(api)!: ...`) o con el pie `BREAKING CHANGE:`.

### 2.4 Ejemplos

```text
feat(domain): añadir clave y armadura al ScoreIR
fix(api): validar ediciones antes de persistir en el log
refactor(application): extraer casos de uso a packages/application
docs(conventions): incorporar politica de ramas y calidad para la fase 7
chore(ci): configurar pipeline de github actions
```

---

## 3. Pull Requests y Migraciones

### 3.1 Política de Pull Requests
- **Un issue = una rama = un PR.** No se inicia el siguiente issue hasta fusionar el anterior (salvo excepciones acopladas explícitas).
- **Título:** Formato Conventional Commit con el número de issue:
  `<tipo>(<scope>): <descripción> (#N)`
- **Cuerpo estructurado:**
  - Resumen conciso de cambios.
  - Verificación detallada de cada criterio de aceptación con evidencia de tests.
  - Decisiones técnicas o arquitectónicas adoptadas.
  - Cláusula de cierre: `Closes #N`.
- **Fusión:** Siempre mediante *squash and merge* y borrado de rama, de modo que `dev` conserve exactamente un commit por issue.

### 3.2 Migraciones de Base de Datos
- Gestionadas exclusivamente con **Alembic**.
- Numeración secuencial estricta (`0003_…`, `0004_…`).
- Máximo una migración por PR cuando se modifique el esquema relacional.
- Toda migración debe implementar coherentemente tanto `upgrade()` como `downgrade()`.

---

## 4. Estilo de código y calidad

### 4.1 Python

- **Intérprete:** Python **3.12** (`requires-python = ">=3.12,<3.13"`), gestionado con `uv`.
- **Tipado estricto obligatorio:** `mypy` en modo `strict`. Prohibido introducir `Any` o `# type: ignore` sin justificación explícita.
- **Formateo y linting:** `ruff` y `black` configurados en `pyproject.toml` raíz.
- **Pruebas:** Todo módulo core debe contar con tests en `pytest`. Se aplica TDD (escribir pruebas que expresen criterios antes de implementar; reproducir fallos antes de corregirlos).
- **Pureza del dominio:** `packages/domain` utiliza **solo la librería estándar** (`dataclasses`). Cero dependencias externas, verificado por test automatizado.
- **Aislamiento hexagonal:** `packages/application` no importa FastAPI, SQLAlchemy, music21, homr ni onnxruntime. `music21` reside exclusivamente en `packages/interchange`.

### 4.2 Frontend

- **TypeScript** con tipado estricto.
- Formateo con **Prettier** y lint con **ESLint**.
- Pruebas con **Vitest** (unidad) y **Playwright** (E2E).

---

## 5. Definition of Done (DoD)

Un issue o tarea se considera **terminada** únicamente cuando:

1. Cumple **todos los criterios de aceptación** del issue, demostrados con evidencia.
2. Pasan sin errores ni omisiones:
   - `uv run pytest`
   - `uv run mypy packages apps`
   - `uv run ruff check .`
   - `uv run black --check .`
   - Si se modificó `apps/web`: `npm run test` y `npm run build` en `apps/web`.
3. Sigue estrictamente la política de ramas, commits y PRs.
4. Actualiza la documentación correspondiente:
   - **`docs/PROJECT_STATE.md`** (deuda técnica y bitácora de hitos).
   - Matriz §10.2 de **`docs/ARCHITECTURE.md`**.
   - `README.md` si se modifica la forma de uso o configuración.
   - Nuevo documento en `docs/adr/` si se adoptó una decisión estructural.
5. El PR es fusionado hacia `dev` y el issue correspondiente en GitHub queda cerrado.

