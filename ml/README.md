# `ml/` — Framework de Experimentos (Fase 5)

Scripts que simulan el sistema Cadenza para recolectar la **data cuantitativa de
la tesis**. No forman parte del producto (no son paquetes del workspace uv); se
ejecutan con `uv run` y consumen los paquetes `cadenza-*` del workspace.

## Estructura

```text
ml/
└── experiments/
    ├── exp_01_effort.py           # Fase 5: reducción de esfuerzo sobre PrIMuS
    ├── exp_02_active_learning.py  # Fase 5: comparación de estrategias de AL
    ├── corpus.py                  # Fase 6: registro, descarga y manifiesto de corpus
    ├── exp_03_omr_quality.py      # Fase 6: calidad OMR (OMR-NED oficial)
    └── exp_04_homr_transcribe.py  # Fase 6: transcripción real con HOMR (GPU)
results/                           # Salidas generadas (ignoradas por git)
data/                              # Corpus descargado (ignorado por git)
```

## Ejecución

```powershell
uv run --no-sync python ml/experiments/exp_01_effort.py
uv run --no-sync python ml/experiments/exp_02_active_learning.py
```

## Experimentos

### `exp_01_effort.py` — Reducción de esfuerzo

Compara las transcripciones de HOMR de PrIMuS con su verdad de referencia, compás a
compás, pasando cada predicción por `ValidationEngine`:

- **Línea base:** inspeccionar los N compases a mano → `N` inspecciones.
- **Línea asistida:** inspeccionar solo los compases con `Finding` → `X`.

Necesita `data/manifest.json` (ver `corpus.py`) y las predicciones de HOMR en
`data/<corpus>/predictions/` (`exp_04`), o `--predictions`. **Sin manifiesto, o sin
ninguna predicción utilizable, el experimento falla**: no tiene modo sintético ni escribe
resultados con ceros (CLAUDE.md §8.1, #130, #139).

Salida (→ `results/effort_comparison.json`, `results/effort_comparison_by_score.csv`
y `results/exp_01_run_info.json`): esfuerzo de inspección con y sin validador,
errores reales que quedan sin revisar y su desglose por tipo de operación. La
interpretación y la justificación del tamaño de muestra (N y errores estándar) se
calculan con los recuentos de la ejecución: ningún experimento escribe cifras a mano en
sus resultados (#139).

### `exp_02_active_learning.py` — Estrategias de adquisición

Construye el pool de muestras a partir de los errores reales de HOMR frente a la
verdad de referencia de PrIMuS (`build_real_training_pool`) y compara
`UncertaintyAcquisition`, `DiversityAcquisition`, `HybridAcquisition` y
`RandomAcquisition` con los cinco criterios definidos a priori, para presupuestos de
10, 20 y 50 muestras.

Necesita `data/manifest.json` (ver `corpus.py`) y las predicciones de HOMR en
`data/<corpus>/predictions/` (`exp_04`), o `--predictions`; admite `--limit` y `--seed`.
**Sin manifiesto o sin ninguna muestra real, el experimento falla**: no tiene modo sintético y la
interpretación del resumen se calcula a partir de los valores medidos (CLAUDE.md §8.1,
#134).

Salida (→ `results/al_strategies_comparison.csv`, `results/al_strategies_summary.json` y
`results/exp_02_run_info.json`): por cada estrategia, las muestras elegidas y las
métricas de los criterios, más la matriz de similitud de Jaccard entre estrategias.

## Fase 6 — Validación empírica sobre corpus real

Requiere el extra de métricas (`musicdiff`), ya incluido en el entorno de
desarrollo:

```powershell
uv sync --inexact   # instala cadenza-learning[metrics] vía el grupo dev sin quitar HOMR
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

### `exp_03_omr_quality.py` — Calidad OMR oficial (OMR-NED y SER)

```powershell
uv run python ml/experiments/exp_03_omr_quality.py
```

Necesita `data/manifest.json` y las predicciones de `exp_04` en
`data/<corpus>/predictions/<id>.musicxml` (con `failures.json` para las imágenes que HOMR
no pudo transcribir). **Sin manifiesto, o con alguna entrada sin predicción ni fallo registrado, el
experimento falla**: no tiene modo de prueba (CLAUDE.md §8.1, #139). Mide:
1. **OMR-NED** (normalizada a nivel gráfico con `musicdiff`).
2. **SER** (tasa de error simbólico a nivel de secuencia canónica de símbolos con `score_ser_pair`).
Reporta métricas sobre éxitos y métricas penalizadas que imputan 1.0 a cada fallo de
segmentación, con la tasa de fallos y su error estándar. Escribe `results/omr_baseline.csv` +
`results/omr_baseline_summary.json`. Reutiliza como caché los valores de OMR-NED y SER del
CSV anterior solo si el sha256 de la predicción y el de la verdad de referencia coinciden con
los guardados; `--force` los recalcula todos.

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

### `exp_07_preprocessing_impact.py` — impacto del preprocesado

Transcribe el corpus con HOMR bajo cada configuración de preprocesado y la compara
con la línea base de `exp_04`, partitura a partitura. Necesita el extra `homr`.

```powershell
uv run --no-sync python ml/experiments/exp_07_preprocessing_impact.py                 # transcribe y mide
uv run --no-sync python ml/experiments/exp_07_preprocessing_impact.py --no-transcribe # solo mide
uv run --no-sync python ml/experiments/exp_07_preprocessing_impact.py --retry-failures # reintenta los fallos
```

La configuración `control` transcribe sin preprocesado en la misma ejecución: su diferencia
con la línea base mide cuánto varía el resultado entre dos ejecuciones. Solo el error de
transcripción del motor cuenta como fallo de una partitura; cualquier otro detiene el script.

### `exp_11_latency_benchmark.py` — latencia de transcripción

Cronometra `HOMREngine` sobre incipits y páginas compuestas. Un dispositivo por
ejecución; las ejecuciones sucesivas acumulan muestras (`--reset` las descarta).

```powershell
uv run --no-sync python ml/experiments/exp_11_latency_benchmark.py --device gpu --reset
uv run --no-sync python ml/experiments/exp_11_latency_benchmark.py --device cpu --reset
```

Ninguno de los dos tiene valores de reserva: sin motor o sin corpus terminan con error.

### `exp_12_correction_corpus.py` — corpus de correcciones a escala (#255)

El corpus con que aprende la capa de sugerencias (#256). Elige 2 000 incipits de PrIMuS al
azar con semilla, sin los 100 de `exp_03`; los transcribe con HOMR en CPU y sin preprocesado,
como en producción; deriva las correcciones del corrector ideal y las verifica con
`materialize(predicho, ediciones) == verdad`. Necesita el extra `homr` y el corpus en
`data/primus/package_*` con imagen, MEI y `.semantic`.

```powershell
uv run --no-sync python ml/experiments/exp_12_correction_corpus.py sample      # data/primus/exp_12/manifest.json
uv run --no-sync python ml/experiments/exp_12_correction_corpus.py transcribe  # se reanuda; --retry-failures repite los fallos
uv run --no-sync python ml/experiments/exp_12_correction_corpus.py build       # corpus, partición y análisis en results/
```

La verdad es la altura que suena: el MEI de PrIMuS no codifica la alteración de la armadura
(con tres bemoles, la nota de la línea de Si se lee `B4` y suena `Bb4`), así que las alturas
salen del `.semantic` del mismo incipit, comprobando que coinciden la letra y la octava.
El corpus (`results/correction_corpus.jsonl`) tiene un registro por evento leído, evento que
falta y compás con la clave o la armadura mal leídas: lo que leyó HOMR, su corrección o
ninguna, y el contexto leído (armadura, compás, clave, posición, lo que le sobra o le falta
al compás y las notas vecinas). La partición fija (`correction_corpus_split.json`) depende
solo de la obra del incipit (su registro RISM, `cadenza.learning.primus_work_id`) y de la
semilla de la muestra (`cadenza.learning.assign_split`): los incipits de una misma obra caen
del mismo lado. Lo que no se puede leer (un MEI o una predicción que el dominio no admite,
o un `.semantic` que no describe las mismas notas) se registra por incipit y no entra en
el corpus.

### `exp_14_suggestion_layer.py` — medición de la capa de sugerencias (#257)

La primera medición de la capa de sugerencias (#256, ADR-0036), con la que el responsable
decide si entra en el estudio (#244). Entrena la capa con la partición `train` del corpus de
`exp_12` y la mide en `test` por el camino de producción: las reglas y después la capa, con el
filtro de admisibilidad de los casos de uso (`validate_after`, sin duplicados, tres por
hallazgo), sobre el `ScoreIR` que leyó HOMR. La verdad es la del corpus (el corrector ideal
frente a la altura que suena). Necesita el corpus, su partición, la muestra de `exp_12` con sus
predicciones y la verdad (MEI y `.semantic`); sin alguno de ellos, o si la predicción y la
verdad no dan los registros del corpus, falla.

```powershell
uv run --no-sync python ml/experiments/exp_14_suggestion_layer.py            # results/
uv run --no-sync python ml/experiments/exp_14_suggestion_layer.py --output-dir <dir> --seed 20260920
# Lo que verá la condición asistida (la política por defecto de la API, ADR-0036 enmienda 19):
uv run --no-sync python ml/experiments/exp_14_suggestion_layer.py --output-dir <dir> `
  --min-level high --families accidental
```

Con `--min-level` o `--families`, la prueba, los pliegues y la curva se miden con la capa
envuelta en la misma política de qué se muestra que la API (`SuggestionPolicy`,
`PolicySuggestionModel`); lo que no se da no filtra, y sin ninguna de las dos se mide todo lo
admisible, como en #287. La línea base del orden de la regla y `promotion_metrics` no pasan
por la política. El resumen y `run_info` dicen qué política se midió (`display_policy`).

Mide, en `results/suggestion_layer_summary.json` (con `run_info`):

- **Validación cruzada** de 5 pliegues agrupados por obra dentro de `train` (media y desviación
  de las métricas principales; cada pliegue elige sus umbrales con su propia validación
  cruzada interna, como `ml suggestions train`).
- **Sugerencias a los posibles errores de las reglas:** acierto de la primera y de las tres
  primeras, sobre los hallazgos con sugerencias y sobre los que tienen el arreglo verdadero
  entre sus candidatos, frente al orden de la propia regla.
- **Errores que las reglas no ven:** precisión y *recall* por compás con la definición de
  `exp_06` (`cadenza.learning.evaluate_measures`), con las reglas solas y con las reglas más los
  posibles errores propios de la capa, y su cobertura por categoría; también por evento.
- **Antes y después:** SER y OMR-NED frente a la verdad con HOMR solo, con las sugerencias de
  confianza alta aplicadas y con todas las primeras sugerencias aplicadas (una tras otra, con
  el ancla traducida y `validate_after`).
- **Daño**, de las sugerencias elegidas y de las aplicadas: por evento (eventos correctos
  estropeados, eventos con error arreglados mal, inserciones donde no falta nada o de otro
  evento) y por atributo (alteración, altura o duración sin error que se cambiarían, o un
  evento que la verdad borra). Una sugerencia acierta si su familia y su valor son los de la
  verdad.
- **Curva de aprendizaje** con el 10, el 25, el 50 y el 100 % de las obras de `train`
  (submuestreo anidado con la semilla), medida en `test`, con las correcciones de cada punto.
- **Sesiones del estudio:** todavía no hay; el resultado lo dice (`study_sessions`).
- Las métricas de `ml suggestions evaluate` (`promotion_metrics`).

Decisiones de la medición: la SER se calcula sin aplicar la armadura, porque las alturas del
`ScoreIR` son las que suenan (aplicándola, un Si natural leído donde suena Si bemol no contaría);
el OMR-NED compara MusicXML exportados del `ScoreIR` (verdad y cada variante), para que el antes
y el después pasen por el mismo camino, así que no es el de `exp_12`; las correcciones por
compás salen de los registros del corpus, que son las de `derive_edit_events` frente a la altura
que suena, no frente al MEI tal cual como en `exp_06`; los pliegues y la curva usan la semilla
del experimento (`--seed`), y los umbrales, la de la configuración. El artefacto entrenado se
guarda en la salida (`suggestion_layer_artifact.json`) y no se registra ni se promueve. Salen
también `suggestion_layer_incipits.csv` (una fila por incipit de prueba) y
`exp_14_run_info.json` (commit, semilla, sha256 del corpus, de la partición y del artefacto,
versión de rasgos y configuración). `--no-omr-ned` omite el OMR-NED (solo para depurar).
Si la capa falla o pierde hallazgos de las reglas, el experimento falla (producción validaría
sin capa); las proporciones sin denominador son `null`, y las medias de SER y OMR-NED son
sobre los incipits que tienen las tres variantes.

El OMR-NED de `musicdiff` tarda segundos por par (el `build` de `exp_12` tardó horas por él):
`--workers` (por defecto, los núcleos menos uno) reparte la lectura de las partituras y el
OMR-NED entre procesos, y una variante idéntica a otra del mismo incipit (sin sugerencias
aplicadas) reutiliza su valor. El resultado no depende del número de procesos.

## CLI de Jobs Offline (Fase 7, #22)

Orquesta el ciclo por lotes de aprendizaje activo de forma explícita y reproducible
([ADR-0008](../docs/adr/ADR-0008-active-learning-model-registry.md), `ARCHITECTURE.md` §3.2 y §6.5).
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
| `build-dataset` | Base de datos (`SessionRepository`, `EditEventRepository`, `UserRepository`) | `dataset.json` | `dataset_hash`, `count`, `config_hash`, `seed`, `self_registered_included`, muestras |
| `select` | `dataset.json` | `selected.json` | `dataset_hash`, `source_dataset_hash`, `strategy`, `budget`, `seed`, `self_registered_included` |
| `train` | `selected.json` | `trained_artifact.json` + `data/artifacts/sha256/...` | `artifact_hash` (pesos), `dataset_hash`, `config_hash`, métricas |
| `evaluate` | `trained_artifact.json` | `evaluation_report.json` | `metrics` (SER, OMR-NED), `threshold`, `meets_threshold` |
| `promote` | `trained_artifact.json` | `promotion_result.json` + `model_versions` (BD) | `version`, `promoted`, `active_model_version`, umbral |

`evaluate` toma la SER y el OMR-NED, por este orden, de `--ser`/`--omr-ned`, de `--manifest`
(medidas con `exp_03`) o del artefacto, y guarda la fuente de cada una en `metrics_source`.
Sin ninguna de esas fuentes falla, igual que `promote` con un artefacto sin métricas: ninguno
usa métricas de reserva (#139). Las métricas que escribe `train` **no son mediciones**: sin
`--ser` y `--omr-ned`, `FakeTrainer` y `PyTorchTrainer` devuelven valores fijos, porque el
ajuste fino real del modelo no existe (D14, [#103](https://github.com/sebdavid3/Cadenza/issues/103)).
`train` marca **siempre** sus métricas con `"simulated": true`, también con `--ser` y
`--omr-ned` (que se indican juntos o ninguno), porque ningún entrenador evalúa el modelo que
produce; `evaluate` y `promote` propagan la marca a sus informes, y la tabla `model_versions` no
la guarda. `promote` registra siempre las métricas del artefacto que recibe, no las de
`evaluate`. `evaluate --manifest` mide las predicciones de `--predictions-dir` (sin comprobar que
procedan del artefacto) y, como `exp_03`, exige que cada entrada sin predicción figure en
`failures.json`.

### Capa de sugerencias (`ml suggestions`, #256, ADR-0036)

La capa que aprende de las correcciones sustituye en el flujo de aprendizaje a la red de
`PyTorchTrainer`, que se retira del código con
[#271](https://github.com/sebdavid3/Cadenza/issues/271). Ningún comando escribe por defecto en
`results/` ni en `data/`: las rutas se dan siempre.

```powershell
# 1. Entrenar: frecuencias por contexto de la partición `train` y umbrales por validación
#    cruzada de 5 pliegues agrupados por obra. Mismo corpus y configuración, mismos bytes.
uv run --no-sync python -m ml suggestions train --corpus <corpus.jsonl> `
  --config configs/learning/suggestions.json --output <modelo.json>

# 2. Evaluar sobre la partición de prueba fija de #255, frente a no tener capa.
uv run --no-sync python -m ml suggestions evaluate --model <modelo.json> `
  --corpus <corpus.jsonl> --output <informe.json>

# 3. Promover solo si mejora a la activa (o, la primera, a no tener capa) en la misma
#    partición de prueba. Entra en vigor al reiniciar la API con CADENZA_SUGGESTIONS_ENABLED,
#    que solo muestra lo que deja su política (CADENZA_SUGGESTIONS_MIN_LEVEL y
#    CADENZA_SUGGESTIONS_FAMILIES; por defecto, las alteraciones de confianza alta).
uv run --no-sync python -m ml suggestions promote --model <modelo.json> --report <informe.json> `
  --db-url <url> --artifacts-dir <dir de artefactos de la API> --version <versión>

# 4. Bucle de aprendizaje: el corpus de exp_12, sin modificarlo, más las sesiones finalizadas
#    de Cadenza (partidas por página de origen) y las respuestas a sus sugerencias.
uv run --no-sync python -m ml suggestions build-dataset --corpus <corpus de exp_12> `
  --output <corpus ampliado.jsonl> --db-url <url> --split-seed <semilla de la partición>
```

| Comando | Entrada | Salida | Trazabilidad |
|---|---|---|---|
| `suggestions train` | corpus JSONL | artefacto JSON | `training.dataset_hash` (sha256 del corpus), `config_hash`, `seed`, curva de la validación cruzada |
| `suggestions evaluate` | artefacto y corpus | informe JSON | `model_sha256`, `evaluation_dataset_hash`, métricas medidas (`simulated: false`) |
| `suggestions promote` | artefacto e informe | `suggestion_model_versions` (BD) y el artefacto en el ArtifactStore | versión, `sha256`, hashes, semilla, `feature_version`, métricas |
| `suggestions build-dataset` | corpus de exp_12 y BD | corpus JSONL | `dataset_hash` propio; registros `source: cadenza` y `suggestion` |

El informe de `evaluate` mide, por familia, la precisión, el *recall* y el F1 de los posibles
errores propios; cuántos de los errores que las reglas no ven señala la capa; y la exactitud de
la primera sugerencia en los hallazgos de regla cuyo arreglo verdadero está entre los
candidatos, frente al primer candidato de la regla. Si no hay con qué medir, falla o deja la
métrica en `null`, y la promoción se rechaza: nunca hay cifras de reserva (CLAUDE.md §8).
Entre el congelado (#252) y el final del estudio no se promueve ninguna versión.

El coste en línea se mide con `scripts/measure_suggestion_cost.py` sobre una página real (no
escribe nada) y con la prueba `packages/learning/tests/test_suggestion_cost.py`.

## Reproducibilidad

Los experimentos de Fase 5 usan `SEED = 20260920` y no dependen de red, GPU ni
base de datos. Los de Fase 6 fijan el corpus por hash en `data/manifest.json`.
Los jobs offline fijan `dataset_hash`, `config_hash` y semilla en cada artefacto.
Las salidas en `results/` y el corpus en `data/` están ignorados por git (ver
`.gitignore`). Solo se citan en la tesis las salidas medidas: las que llevan
`"simulated": true` son simuladas y no son resultados.

