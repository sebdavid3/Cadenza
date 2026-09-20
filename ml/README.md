# `ml/` — Framework de Experimentos (Fase 5)

Scripts que simulan el sistema Cadenza para recolectar la **data cuantitativa de
la tesis**. No forman parte del producto (no son paquetes del workspace uv); se
ejecutan con `uv run` y consumen los paquetes `cadenza-*` del workspace.

## Estructura

```text
ml/
└── experiments/
    ├── exp_01_effort.py          # Reducción de esfuerzo: manual vs. asistido
    └── exp_02_active_learning.py # Comparación de estrategias de AL
results/                          # Salidas generadas (ignoradas por git)
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

## Reproducibilidad

Ambos usan `SEED = 20260920` y no dependen de red, GPU ni base de datos, por lo
que son deterministas y aptos para CI. Las salidas en `results/` están ignoradas
por git (ver `.gitignore`); sus valores se citan en la tesis.
