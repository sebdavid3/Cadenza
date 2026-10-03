# Cadenza: Plataforma de Digitalización Asistida de Partituras

Cadenza convierte imágenes de partituras (impresas o manuscritas modernas) en
notación editable (**MusicXML 4.0** / **MIDI 1.0**) combinando reconocimiento
óptico de música (OMR), validación musical automática y **corrección humana**
(*Human-in-the-Loop*, HITL). Cada corrección se registra como un evento inmutable
que alimenta el **aprendizaje activo** del sistema.

El núcleo sigue una **arquitectura hexagonal** (puertos y adaptadores) dentro de
un **monolito modular**: el dominio es puro (cero dependencias externas) y toda
la capacidad externa (OMR, validación, persistencia, API, aprendizaje) se
conecta a través de puertos.

---

## Estado del proyecto

| Fase | Contenido | Estado |
|---|---|---|
| **0** | Dominio puro: `ScoreDocument`, `AnchorIndex`, `EditEvent`, `TimeSignature` | ✅ |
| **1** | Adaptador OMR: puerto `OMREngine`, `HOMREngine` (in-process) y `FakeOMREngine` | ✅ |
| **2** | Motor de validación por reglas (`ValidationEngine` + `Finding` anclados) | ✅ |
| **3** | API HITL + persistencia (SQLAlchemy/JSONB, Alembic, Event Sourcing) | ✅ |
| **4** | Aprendizaje activo: `DatasetBuilder`, estrategias de adquisición, `ModelRegistry` | ✅ |
| **5** | Framework de experimentos (esfuerzo y estrategias de AL) | ✅ |
| **6** | Validación empírica sobre corpus real (PrIMuS) y OMR-NED oficial | ✅ |
| **7** | Alineación con la arquitectura objetivo (capa de aplicación, datos, API completa, plano offline) | 🔜 |

Las fases 0–6 implementan el **núcleo** de cada módulo. Las brechas frente a la
arquitectura objetivo se cierran en la Fase 7, cuyo trabajo está en los
[issues del repositorio](https://github.com/sebdavid3/Cadenza/milestone/1).

Estado detallado, deuda técnica y bitácora: [`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md).

---

## Arquitectura

```
                     ┌──────────────────────── Dominio puro ────────────────────────┐
                     │  packages/domain  (ScoreDocument · Anchor · EditEvent)        │
                     └──────────────────────────────────────────────────────────────┘
                                    ▲                ▲                 ▲
             ┌──────────────────────┘                │                 └──────────────────────┐
             │                                       │                                        │
   packages/interchange                  packages/validation                        packages/learning
   (MusicXML/MEI/**kern ↔ ScoreIR)       (reglas puras)                            (AL, OMR-NED, registry)
             ▲
             │
   packages/omr  ─── puerto OMREngine ─── HOMREngine / FakeOMREngine
             │
   packages/persistence ─── EditEventRepository (append-only) + SQLAlchemy/JSONB
             │
   apps/api ─── FastAPI (transcripción, findings, eventos de edición)
```

**Regla de dependencias:** los adaptadores dependen del dominio (y de sus
puertos), nunca al contrario. El dominio no importa Pydantic, SQLAlchemy, FastAPI
ni music21 (verificado por un test de pureza). Decisiones en
[`docs/adr/`](docs/adr/) (ADR-0001 … ADR-0010).

El diagrama muestra lo implementado. La arquitectura objetivo añade una capa de
aplicación (`packages/application`), un `ArtifactStore` y la exportación
MusicXML/MIDI; ver [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) §10.

---

## Estructura del repositorio

```
Cadenza/
├── packages/                  # Monolito modular (paquetes del workspace uv)
│   ├── domain/                # Núcleo puro: modelos, anclas, proyección del log
│   ├── interchange/           # Puente canónico MusicXML/MEI/**kern ↔ ScoreIR (music21)
│   ├── omr/                   # Puerto OMREngine + HOMREngine / FakeOMREngine
│   ├── validation/            # Motor de reglas y hallazgos anclados
│   ├── persistence/           # Modelos SQLAlchemy/JSONB, repositorio append-only, Alembic
│   └── learning/              # DatasetBuilder, estrategias AL, OMR-NED, Model Registry
├── apps/
│   ├── api/                   # API Gateway FastAPI (nueva arquitectura)
│   └── web/                   # Visor HITL (React + TS + Zustand + TanStack Query)
├── ml/experiments/            # Experimentos de la tesis (esfuerzo, AL, OMR-NED)
├── configs/learning/          # Configuraciones de entrenamiento versionadas
├── docs/                      # Arquitectura, ADRs, estado del proyecto, literatura
├── latex/                     # Documento maestro de tesis (IEEEtran)
├── results/                   # Salidas de experimentos (ignoradas por git)
├── data/                      # Corpus descargado (ignorado por git)
└── legacy/                    # Prototipo MVP original (backend, frontend, scripts, docker-compose)
```

---

## Requisitos

- **Python 3.12**
- **[uv](https://docs.astral.sh/uv/)** (gestor de workspace y entorno)
- **Node.js 18+** (solo para `apps/web`)
- **GPU NVIDIA (opcional):** para acelerar la inferencia OMR real

---

## Instalación y calidad

El repositorio es un workspace de `uv`; un solo comando instala todos los paquetes
y el grupo de desarrollo (pytest, mypy, ruff, black):

```bash
uv sync
```

Ejecutar la batería de calidad:

```bash
uv run pytest                      # suite completa
uv run mypy packages apps          # tipado estricto
uv run ruff check .                # linting
uv run black --check .             # formato
```

---

## Ejecución

### API (nueva arquitectura)

```bash
uv run uvicorn cadenza.api.main:create_default_app --factory --reload
```

- Documentación interactiva: <http://127.0.0.1:8000/docs>
- La base de datos se toma de `CADENZA_DATABASE_URL` (por defecto SQLite
  `./cadenza.db`; en producción PostgreSQL vía JSONB).

### Interfaz web HITL

```bash
cd apps/web
npm install
npm run dev
```

### Experimentos (tesis)

```bash
uv run python ml/experiments/exp_01_effort.py            # reducción de esfuerzo
uv run python ml/experiments/exp_02_active_learning.py   # estrategias de AL
```

Validación empírica sobre corpus real (PrIMuS) con la métrica oficial OMR-NED:

```bash
uv run python ml/experiments/corpus.py info
uv run python ml/experiments/corpus.py fetch --corpus primus \
  --url https://grfia.dlsi.ua.es/primus/packages/primusCalvoRizoAppliedSciences2018.tgz
uv run python ml/experiments/corpus.py manifest --corpus primus --limit 100
uv run python ml/experiments/exp_04_homr_transcribe.py   # transcripción real
uv run python ml/experiments/exp_03_omr_quality.py       # OMR-NED vs. ground truth
```

Detalles en [`ml/README.md`](ml/README.md).

### Aceleración por GPU

El extra `homr` instala HOMR; para GPU se recomienda la build **CUDA 12.8** de
`onnxruntime` (compatible con Blackwell/sm_120):

```bash
uv pip install -e "packages/omr[homr]"
uv pip uninstall onnxruntime onnxruntime-gpu
uv pip install "onnxruntime-gpu[cuda,cudnn]==1.26.0"
```

`HOMREngine` expone automáticamente los `bin` de los wheels NVIDIA al `PATH`
(`ensure_cuda_dll_dirs`), necesario porque cuDNN carga sus sub-librerías durante
la inferencia. Sin GPU, los scripts funcionan en CPU con `--cpu`.

---

## API REST

| Método | Endpoint | Descripción |
|---|---|---|
| `POST` | `/transcribe` | Sube una imagen, ejecuta OMR + validación y crea una sesión. |
| `GET` | `/sessions/{id}` | Documento, hallazgos, eventos de edición y `current_score` materializado. |
| `GET` | `/sessions/{id}/findings` | Hallazgos de validación de la sesión. |
| `POST` | `/sessions/{id}/edits` | Añade una corrección humana inmutable (append-only). |

---

## Prototipo legacy (referencia)

El prototipo MVP original (FastAPI + HOMR + Docker CUDA + visor OSMD + Tone.js)
se conserva en `legacy/` —`legacy/backend`, `legacy/frontend`, `legacy/scripts` y
`legacy/docker-compose*.yml`—. Sigue operativo durante la migración a la
arquitectura hexagonal y **no** es el código de producción.

```bash
./legacy/scripts/run-docker-gpu.sh     # Docker con GPU NVIDIA
./legacy/scripts/run-docker-cpu.sh     # Docker en CPU (fallback)
./legacy/scripts/run-local.sh          # Entorno local (Linux/macOS/WSL)
```

---

## Documentación

- [`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md) — estado vivo, deuda técnica y bitácora.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — arquitectura objetivo, funciones, datos y brechas.
- [`docs/arquitectura-dbb.md`](docs/arquitectura-dbb.md) — diagramas de bloques (DBB).
- [`docs/adr/`](docs/adr/) — registros de decisiones (ADR-0001 … ADR-0010).
- [`docs/CONVENTIONS.md`](docs/CONVENTIONS.md) — convenciones de Git y calidad.
- [`docs/literatura/`](docs/literatura/) — estado del arte y corpus de evaluación.
- [`latex/`](latex/) — documento maestro de la tesis.
