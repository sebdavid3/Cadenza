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

### `exp_06_validation_metrics.py` — precisión y *recall* del validador

Ejecuta el catálogo de reglas (`ValidationEngine`) sobre las predicciones de HOMR y lo compara
compás a compás con las correcciones reales que salen del diff con la verdad de referencia
(`derive_edit_events`): precisión, *recall* y F1 globales y por regla, y cobertura por
categoría de error. Cada salida lleva la versión de las reglas con que se midió:
`rules_version` (la lista de identificadores, que el experimento usa para saber qué reglas
medir) y `rules_catalog_version` (`RULES_CATALOG_VERSION`, que cambia aunque los
identificadores no cambien; ADR-0040 §3), en el resumen, en la cobertura y en cada fila de
los CSV.

```powershell
uv run --no-sync python ml/experiments/exp_06_validation_metrics.py --output-dir <dir>
```

La medición de una versión del catálogo no reemplaza a la de otra: si la salida ya tiene un
resumen de otra versión (sin `rules_catalog_version`, la 1, anterior a #246), el experimento
falla antes de medir y pide otro `--output-dir`. La de `results/` es la del catálogo 1.

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
uv run --no-sync python ml/experiments/exp_14_suggestion_layer.py --output-dir <dir> --seed 20260920
# Lo que verá la condición asistida (la política por defecto de la API, ADR-0036 enmienda 19):
uv run --no-sync python ml/experiments/exp_14_suggestion_layer.py --output-dir <dir> `
  --min-level high --families accidental
```

Con `--min-level` o `--families`, la prueba, los pliegues y la curva se miden con la capa
envuelta en la misma política de qué se muestra que la API (`SuggestionPolicy`,
`PolicySuggestionModel`); lo que no se da no filtra, y sin ninguna de las dos se mide todo lo
admisible, como en #287. La línea base del orden de la regla y `promotion_metrics` no pasan
por la política, así que con ella la comparación de la primera y las tres primeras sugerencias
con la línea base mide el filtro y no el orden (`display_policy.baseline_comparison_valid:
false`). El resumen y `run_info` dicen qué política se midió (`display_policy`). Con política,
`--output-dir` es obligatorio: `results/` guarda la medición de #287.

Lo propio de la capa depende de las reglas con que se mide: con el catálogo de ADR-0040
(versión 2), `accidental.repeated` señala el caso del que salían casi todos los aciertos de
`learned.accidental`, que pasa a ser un posible error de regla que la capa ordena (§14). Por
eso el resumen, `run_info` y cada fila del CSV llevan `rules_version` y
`rules_catalog_version`, y, como `exp_06`, el experimento no sobrescribe una medición de otra
versión del catálogo: la de `results/` (#287) es del catálogo 1, y la del 2 va a otro
`--output-dir`.

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

### `exp_15_reference_set.py` — conjunto de referencia del compás, los tresillos, las armaduras y la voz con piano (#234)

La línea base de #237, #238 y #239 ([ADR-0056](../docs/adr/ADR-0056-conjunto-de-referencia-del-compas-tresillos-armaduras-y-voz-con-piano.md)).
El conjunto lo fija `ml/experiments/reference_set_manifest.json`: doce páginas impresas de IMSLP
(dominio público) de *Ellens Gesang I*, *Mondnacht* y *Der stürmische Morgen* con su verdad de
OpenScore Lieder (CC0), y las predicciones de HOMR sobre PrIMuS de `exp_04` y `exp_12` (renders de
Verovio, no escaneos) para el numerador del compás y C y ¢. Los PDF, las verdades y las predicciones
están en `data/` sin versionar; el manifiesto guarda su sha256. Las páginas del banco del estudio
(#247) no entran.

```powershell
# Rasteriza las páginas con pdftoppm a 300 ppp en data/reference/pages/ (run lo hace si faltan)
uv run --no-sync python ml/experiments/exp_15_reference_set.py pages
# Transcribe las doce páginas con HOMR en CPU, compara y lee PrIMuS (por defecto, en results/)
uv run --no-sync python ml/experiments/exp_15_reference_set.py run
```

Si falta un archivo del manifiesto, o su sha256 (o la huella de las predicciones de PrIMuS) no es el
del manifiesto, falla antes de transcribir con la lista de lo que falta. Las imágenes tienen que dar
el sha256 del manifiesto, que se hizo con `pdftoppm` 24.04.0 (poppler): con otra versión, falla. Los
rasgos que el manifiesto dice de cada página se cotejan con su verdad.

Mide pentagrama a pentagrama (los de la verdad: uno que HOMR no lee cuenta como no leído), con
alineación proporcional de los compases de la página, una tolerancia de `--tolerance` compases (1 por
defecto) y cada cambio o compás con tresillos leído emparejado como mucho con uno de la verdad (de
los cambios dentro de la tolerancia, el que lee el valor bueno y, si no, el más cercano):

- **el compás por tramo**: cada indicación impresa (al principio de página o a mitad), si HOMR la lee,
  con la métrica y con la grafía; la métrica y la grafía de cada compás; el símbolo C y ¢ con
  `time_symbol_agreement`; los compases de un tramo que empezó antes, sin indicación impresa, aparte;
  la indicación de cortesía del final y los cambios de más;
- **la armadura**: al principio de la página, en cada cambio, en la cortesía y en cada compás;
- **los tresillos**: los compases de la verdad con tresillos, marcados o implícitos (sin número en el
  MusicXML de la verdad), que HOMR lee, y los que lee HOMR que están en la verdad;
- **las partes y los pentagramas** de cada página;
- **PrIMuS**: el compás inicial (numerador, denominador y grafía, con las confusiones) y el símbolo en
  todos los compases, sobre los incipits medidos y con los fallos de HOMR como mal leídos.

Salida (`--output-dir`, por defecto `results/`): `reference_set_summary.json` (con `run_info`),
`reference_set_pages.csv`, `reference_set_primus.csv`, `exp_15_run_info.json` y
`reference_set_predictions/` con el MusicXML de HOMR de cada página (`--reuse-predictions` lo
reutiliza si es de la misma imagen y del mismo motor). `--gpu` transcribe en GPU; `--workers` (hasta 8
por defecto) lee PrIMuS en paralelo.

**La etapa del compás (#237, [ADR-0059](../docs/adr/ADR-0059-compas-por-tramos-c-y-cortado-y-tresillos-implicitos-tras-homr.md)).**
`--meter-features` (por defecto `none`: HOMR solo) pasa cada lectura de HOMR por la etapa que corre
tras HOMR en producción, con esos rasgos (`numerator`, `symbol`, `implicit_tuplets`, `all`), antes de
compararla. Con rasgos, cada fuente de PrIMuS da además `omr_quality`: la SER antes y después de la
etapa en todos los incipits medidos y, en los que la etapa cambia, el OMR-NED antes y después
(MusicXML exportados del `ScoreIR` sin el símbolo del compás, como `exp_14`), con cuántos mejoran y
cuántos empeoran. El resumen dice los rasgos y la versión de la etapa (`meter_stage`).

```powershell
uv run --no-sync python ml/experiments/exp_15_reference_set.py run --reuse-predictions --meter-features all --output-dir <carpeta>
```

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

# 3. Guardar los pesos de FakeTrainer en el ArtifactStore, con unas métricas dadas
#    (obligatorias y marcadas siempre como simuladas: ningún entrenador evalúa el modelo)
uv run python -m ml train --input data/datasets/selected.json --output results/trained_artifact.json `
  --artifacts-dir data/artifacts --ser <SER> --omr-ned <OMR-NED>

# 4. Evaluar el artefacto entrenado contra los umbrales de promoción
uv run python -m ml evaluate --input results/trained_artifact.json --output results/evaluation_report.json

# 5. Promover y activar la versión en el ModelRegistry si cumple el umbral
uv run python -m ml promote --input results/trained_artifact.json --version v1.1.0 `
  --output results/promotion_result.json

# 6. Pipeline encadenado completo (de punta a punta)
uv run python -m ml run --config configs/learning/default.json --work-dir results/pipeline_run `
  --strategy hybrid --budget 10 --version v1.1.0 --ser <SER> --omr-ned <OMR-NED>
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
usa métricas de reserva (#139). Las métricas que escribe `train` **no son mediciones**: el
ajuste fino real del modelo no existe (D14, [#103](https://github.com/sebdavid3/Cadenza/issues/103))
y el único entrenador, `FakeTrainer`, no evalúa el modelo que produce. Por eso `train` exige
`--ser` y `--omr-ned` (juntos) y, sin ellas, falla con un mensaje que lo explica; no hay
valores fijos de reserva ([#271](https://github.com/sebdavid3/Cadenza/issues/271)). Las
métricas que recibe van **siempre** marcadas con `"simulated": true`; `evaluate` y `promote`
propagan la marca a sus informes, y la tabla `model_versions` no la guarda. `run` exige
también `--ser` y `--omr-ned`, y lo comprueba antes de escribir nada en `--work-dir`.
`--trainer` ya no existe: elegía `PyTorchTrainer`, una red auxiliar, retirada en #271, que
devolvía métricas de reserva. `promote` registra siempre las métricas del artefacto que
recibe, no las de `evaluate`. `evaluate --manifest` mide las predicciones de `--predictions-dir` (sin comprobar que
procedan del artefacto) y, como `exp_03`, exige que cada entrada sin predicción figure en
`failures.json`.

### Capa de sugerencias (`ml suggestions`, #256, ADR-0036)

La capa que aprende de las correcciones sustituye en el flujo de aprendizaje a la red de
`PyTorchTrainer`, retirada del código en
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

## Experimentos retirados y datos simulados (#271)

- **`exp_09` (SMB y MUSCIMA++) se retiró en [#271](https://github.com/sebdavid3/Cadenza/issues/271).**
  No evaluaba ningún corpus real: SMB eran tres filas sintéticas sobre una partitura de
  prueba y MUSCIMA++ un texto fijo; los dos corpus son trabajo futuro
  ([#102](https://github.com/sebdavid3/Cadenza/issues/102)). Lo que dejó en `results/`
  (`multicorpus_evaluation_summary.json`, `smb_baseline.csv` y `exp_09_run_info.json`, del
  2026-10-08) es sintético aunque no lleve `"simulated"`, y no se cita.
- **`exp_08` (línea base de oemer) se retiró en [#130](https://github.com/sebdavid3/Cadenza/issues/130)**
  sin haber ejecutado oemer: `oemer_baseline.csv`, `oemer_baseline_summary.json` y
  `exp_08_run_info.json` registran 100 fallos por falta de predicciones y no se citan.
- **`exp_10` solo exporta sesiones reales** (`--db-url`). Sin base de datos, o con una sin
  sesiones del estudio, falla en vez de rellenar con datos sintéticos. `--smoke` genera
  datos sintéticos para probar la exportación, marcados con `"simulated": true` también en
  su `exp_10_run_info.json`, y se niega a escribir en `results/`: exige un `--output-dir`
  fuera de él. Los `effort_study_*` y `exp_10_run_info.json` que hay en `results/` (del
  2026-10-12) son de una ejecución sintética anterior y no se citan; el estudio real llega
  con [#250](https://github.com/sebdavid3/Cadenza/issues/250) y
  [#253](https://github.com/sebdavid3/Cadenza/issues/253).

Archivar o borrar esas salidas de `results/` lo decide el responsable (`CLAUDE.md` §9).

## Reproducibilidad

Los experimentos de Fase 5 usan `SEED = 20260920` y no dependen de red, GPU ni
base de datos. Los de Fase 6 fijan el corpus por hash en `data/manifest.json`.
Los jobs offline fijan `dataset_hash`, `config_hash` y semilla en cada artefacto.
Las salidas en `results/` y el corpus en `data/` están ignorados por git (ver
`.gitignore`). Solo se citan en la tesis las salidas medidas: las que llevan
`"simulated": true` son simuladas y no son resultados.

