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
| `main` | **Sagrada.** Solo código de producción funcional. Nada entra aquí sin pasar por `dev` y verificación. |
| `dev` | Rama de **integración**. Es el punto de convergencia del trabajo diario. |
| `feature/*` | Nueva funcionalidad. |
| `fix/*` | Corrección de un defecto. |
| `refactor/*` | Reestructuración sin cambio de comportamiento. |
| `docs/*` | Documentación, ADRs, gobernanza. |

### 1.2 Flujo

1. Se parte **siempre** de `dev` actualizado.
2. Se trabaja en una rama con el prefijo correspondiente
   (p. ej. `refactor/domain-core`).
3. La rama se integra a `dev` vía PR (o merge directo si es un cambio menor),
   con verificación verde.
4. `dev` se promueve a `main` únicamente en releases o hitos verificados.

```text
main  ←── (release / hito) ────────┐
  ▲                                │
dev   ←── (integración) ───────────┘
  ▲
  └── feature/* · fix/* · refactor/* · docs/*
```

### 1.3 Higiene

- Un commit = un cambio coherente.
- No se comitean secretos, credenciales ni artefactos generados
  (`node_modules/`, `.venv/`, `dist/`, cachés).
- No se reescribe historia publicada (`main`/`dev`) salvo acuerdo explícito.

---

## 2. Conventional Commits (OBLIGATORIO)

Todo mensaje de commit sigue el estándar:

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
| `chore` | Mantenimiento, dependencias, build |
| `perf` | Mejora de rendimiento |
| `build` | Sistema de construcción o empaquetado |
| `ci` | Integración continua |

### 2.2 Scopes sugeridos

`domain`, `omr`, `validation`, `hitl`, `learning`, `api`, `web`, `infra`,
`docs`.

### 2.3 Reglas

- Descripción en **imperativo**, minúscula inicial, sin punto final.
- El *scope* es obligatorio cuando el cambio afecta a un módulo concreto.
- Breaking changes se indican con `!` tras el scope (p. ej. `feat(api)!: ...`)
  o con un pie `BREAKING CHANGE:`.

### 2.4 Ejemplos

```text
feat(domain): modelar AnchorIndex determinista
fix(api): corregir reporte de proveedor de onnxruntime
refactor(validation): extraer catálogo de reglas
docs(architecture): establecer bases de gobernanza, ADRs y convenciones
chore: fijar Python 3.12 en el workspace
```

---

## 3. Estilo de código y calidad

### 3.1 Python

- **Intérprete:** Python **3.12** (`requires-python = ">=3.12,<3.13"`),
  gestionado con `uv`.
- **Tipado estricto obligatorio:** `mypy` en modo `strict`. No se introduce
  `Any` sin justificación.
- **Formateo y linting:** delegados a **`ruff`** (`ruff format` + `ruff check`),
  con configuración central en el `pyproject.toml` raíz.
- **Pruebas:** todo **módulo core** debe tener tests en `pytest`.
- **Pureza del dominio:** `packages/domain` usa **solo la librería estándar**
  (`dataclasses`). Cero dependencias externas; se verifica con un test
  automatizado. Pydantic v2 se reserva para los adaptadores de entrada en
  `apps/api/`.
- **Configuración única:** `ruff`, `mypy` y `pytest` se configuran **una sola
  vez** en el `pyproject.toml` raíz (uv workspace).

### 3.2 Frontend

- **TypeScript** con tipado estricto.
- Formateo con **Prettier** y lint con **ESLint**.
- Pruebas con **Vitest** (unidad) y **Playwright** (E2E).

### 3.3 Contratos y arquitectura

- Las dependencias apuntan **hacia el dominio**; los adaptadores dependen de él,
  nunca al revés.
- Los puertos se definen como interfaces y se verifican con *tests* de contrato.

---

## 4. Definition of Done (general)

Una tarea se considera terminada cuando:

1. Cumple sus **criterios de aceptación** de fase.
2. Pasa `pytest`, `ruff`, `black --check` y `mypy` sin errores.
3. Sigue las convenciones de commits y ramas.
4. Actualiza **`docs/PROJECT_STATE.md`** (fase, hito, bitácora, blockers).
5. No rompe el flujo E2E del prototipo sin una tarea de migración explícita.
