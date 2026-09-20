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

### `exp_04_homr_transcribe.py` — transcripción real (GPU)

```powershell
uv sync --extra homr          # instala HOMR + onnxruntime (pesado)
uv run python ml/experiments/exp_04_homr_transcribe.py --limit 20
uv run python ml/experiments/exp_03_omr_quality.py
```

Transcribe cada imagen del corpus con `HOMREngine`, exporta la predicción a
MusicXML (`score_ir_to_musicxml`) y la deja para que `exp_03` la puntúe. Usa
`--cpu` para forzar inferencia en CPU si la GPU no está disponible.

## Reproducibilidad

Los experimentos de Fase 5 usan `SEED = 20260920` y no dependen de red, GPU ni
base de datos. Los de Fase 6 fijan el corpus por hash en `data/manifest.json`.
Las salidas en `results/` y el corpus en `data/` están ignorados por git (ver
`.gitignore`); sus valores se citan en la tesis.
