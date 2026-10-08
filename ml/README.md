# `ml/` — Framework de Experimentos (Fase 5)

Scripts que simulan el sistema Cadenza para recolectar la **data cuantitativa de
la tesis**. No forman parte del producto (no son paquetes del workspace uv); se
ejecutan con `uv run` y consumen los paquetes `cadenza-*` del workspace.

## Estructura

```text
ml/
└── experiments/
    ├── exp_01_effort.py           # Fase 5: reducción de esfuerzo (sintético)
    ├── exp_02_active_learning.py  # Fase 5: comparación de estrategias de AL
    ├── corpus.py                  # Fase 6: registro, descarga y manifiesto de corpus
    ├── exp_03_omr_quality.py      # Fase 6: calidad OMR (OMR-NED oficial)
    └── exp_04_homr_transcribe.py  # Fase 6: transcripción real con HOMR (GPU)
results/                           # Salidas generadas (ignoradas por git)
data/                              # Corpus descargado (ignorado por git)
```

## Ejecución

```powershell
uv run python ml/experiments/exp_01_effort.py
uv run python ml/experiments/exp_02_active_learning.py
```

## Experimentos

### `exp_01_effort.py` — Reducción de esfuerzo

Genera un `ScoreDocument` sintético (40 compases, ~25% desbalanceados), lo pasa
por `ValidationEngine` + `MeasureBalanceRule` y compara:

- **Línea base:** inspeccionar los N compases a mano → `N` inspecciones.
- **Línea asistida:** inspeccionar solo los compases con `Finding` → `X`.

Salida (→ `results/effort_comparison.json`): `total_measures`, `total_findings`,
`baseline_inspections`, `assisted_inspections` y `effort_reduction_percent`.

### `exp_02_active_learning.py` — Estrategias de adquisición

Construye un pool de 80 muestras con `DatasetBuilder`, les asigna señales
simuladas de `error_density` y `correction_magnitude`, y muestrea un lote de 5 con
`UncertaintyAcquisition`, `DiversityAcquisition` y `HybridAcquisition`.

Salida (→ `results/al_strategies_comparison.csv`): por cada estrategia, las
muestras elegidas (compás, densidad de error, magnitud de corrección). El resumen
impreso en consola reporta la media de error, magnitud y **diversidad media por
par**, evidencia de que la híbrida balancea criticidad y cobertura.

## Fase 6 — Validación empírica sobre corpus real

Requiere el extra de métricas (`musicdiff`), ya incluido en el entorno de
desarrollo:

```powershell
uv sync        # instala cadenza-learning[metrics] vía el grupo dev
```

### `corpus.py` — registro, descarga y manifiesto

```powershell
uv run python ml/experiments/corpus.py info
# PrIMuS (impresas monofónicas, MEI)
uv run python ml/experiments/corpus.py fetch --corpus primus `
  --url https://grfia.dlsi.ua.es/primus/packages/primusCalvoRizoAppliedSciences2018.tgz
uv run python ml/experiments/corpus.py manifest --corpus primus --limit 100
```

El manifiesto (`data/manifest.json`) empareja **por nombre base** imagen↔ground
truth escaneando recursivamente `data/<corpus>/` (los corpus reales anidan sus
carpetas de forma diversa), y guarda el sha256 de cada par para reproducibilidad.
Si el emparejamiento fallara, se pueden fijar las carpetas con `--images-dir` y
`--ground-truth-dir`. Corpus registrados: PrIMuS y Camera-PrIMuS (MEI) y SMB
(**kern). La descarga directa se pasa con `--url`; las URLs de aterrizaje
oficiales están en el registro (`info`).

### `exp_03_omr_quality.py` — OMR-NED oficial

```powershell
uv run python ml/experiments/exp_03_omr_quality.py
```

Sin corpus corre en modo *smoke* con un fixture; con `data/manifest.json` y
predicciones en `data/<corpus>/predictions/<id>.musicxml`, mide OMR-NED por par
y escribe `results/omr_baseline.csv` + `results/omr_baseline_summary.json`.

### `exp_04_homr_transcribe.py` — transcripción real (CPU/GPU)

```powershell
uv pip install -e "packages/omr[homr]"   # HOMR + onnxruntime (base)
uv run python ml/experiments/exp_04_homr_transcribe.py --limit 20 --cpu
uv run python ml/experiments/exp_03_omr_quality.py
```

Transcribe cada imagen con `HOMREngine.transcribe_musicxml` y guarda el
**MusicXML nativo de HOMR** (no el `ScoreIR`, que es lossy) en
`data/<corpus>/predictions/<id>.musicxml`, para que `exp_03` lo puntúe contra el
ground truth. Es tolerante a fallos: registra las imágenes no procesables en
`predictions/failures.json` y continúa, y limpia predicciones previas al empezar.

**GPU (Windows, RTX 50xx/Blackwell):** ORT 1.30+ es CUDA 13 y sus wheels
`nvidia-*-cu13` son *placeholders*. Usa la build CUDA 12.8 (`onnxruntime-gpu`
1.24–1.26) con los wheels `cu12`:

```powershell
uv pip uninstall onnxruntime onnxruntime-gpu
uv pip install "onnxruntime-gpu[cuda,cudnn]==1.26.0"   # CUDA 12.8 + cuDNN 9 (cu12)
uv run python ml/experiments/exp_04_homr_transcribe.py
```

`HOMREngine` añade automáticamente los `bin` de los wheels NVIDIA al `PATH`
(`ensure_cuda_dll_dirs`), necesario porque cuDNN carga sus sub-librerías
(`cudnn_engines_*`) en inferencia; sin esto la primera `Conv` falla con
`CUDNN_STATUS_SUBLIBRARY_LOADING_FAILED`. El `run_info.json` de cada run registra
versión de ORT, providers y si la sesión CUDA se creó de verdad.

## CLI de Jobs Offline (Fase 7, #22)

Orquesta el ciclo por lotes de aprendizaje activo de forma explícita y reproducible
([ADR-0008](docs/adr/ADR-0008-active-learning-model-registry.md), `ARCHITECTURE.md` §3.2 y §6.5).
Los comandos se encadenan mediante artefactos serializados en disco, sin estado en memoria entre ellos.

### Comandos disponibles

```powershell
# 1. Construir dataset desde la base de datos (sesiones finalizadas y sus ediciones)
uv run python -m ml build-dataset --config configs/learning/default.json --output data/datasets/dataset.json

# 2. Seleccionar lote de muestras con una estrategia de adquisición y presupuesto
uv run python -m ml select --input data/datasets/dataset.json --output data/datasets/selected.json `
  --strategy hybrid --budget 10 --seed 42

# 3. Entrenar modelo (FakeTrainer / Trainer) y almacenar pesos en el ArtifactStore
uv run python -m ml train --input data/datasets/selected.json --output results/trained_artifact.json `
  --artifacts-dir data/artifacts

# 4. Evaluar el artefacto entrenado contra los umbrales de promoción
uv run python -m ml evaluate --input results/trained_artifact.json --output results/evaluation_report.json

# 5. Promover y activar la versión en el ModelRegistry si cumple el umbral
uv run python -m ml promote --input results/trained_artifact.json --version v1.1.0 `
  --output results/promotion_result.json

# 6. Pipeline encadenado completo (de punta a punta)
uv run python -m ml run --config configs/learning/default.json --work-dir results/pipeline_run `
  --strategy hybrid --budget 10 --version v1.1.0
```

### Encadenamiento y trazabilidad de artefactos

| Comando | Entrada | Salida | Metadatos persistidos |
|---|---|---|---|
| `build-dataset` | Base de datos (`SessionRepository`, `EditEventRepository`) | `dataset.json` | `dataset_hash`, `count`, `config_hash`, `seed`, muestras |
| `select` | `dataset.json` | `selected.json` | `dataset_hash`, `source_dataset_hash`, `strategy`, `budget`, `seed` |
| `train` | `selected.json` | `trained_artifact.json` + `data/artifacts/sha256/...` | `artifact_hash` (pesos), `dataset_hash`, `config_hash`, métricas |
| `evaluate` | `trained_artifact.json` | `evaluation_report.json` | `metrics` (SER, OMR-NED), `threshold`, `meets_threshold` |
| `promote` | `trained_artifact.json` | `promotion_result.json` + `model_versions` (BD) | `version`, `promoted`, `active_model_version`, umbral |

## Reproducibilidad

Los experimentos de Fase 5 usan `SEED = 20260920` y no dependen de red, GPU ni
base de datos. Los de Fase 6 fijan el corpus por hash en `data/manifest.json`.
Los jobs offline fijan `dataset_hash`, `config_hash` y semilla en cada artefacto.
Las salidas en `results/` y el corpus en `data/` están ignorados por git (ver
`.gitignore`); sus valores se citan en la tesis.

