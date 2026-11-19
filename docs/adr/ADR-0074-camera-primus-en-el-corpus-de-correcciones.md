# ADR-0074: Camera-PrIMuS en los datos de los errores de HOMR

- **Estado:** Aceptado
- **Fecha:** 2026-11-19
- **Decisores:** Responsable del proyecto (autorizó la descarga y decidió el 2026-11-19 que el corpus ampliado lleve solo una muestra de Camera-PrIMuS, en [#421](https://github.com/sebdavid3/Cadenza/issues/421)) y Equipo de Desarrollo
- **Relacionado:** [ADR-0036](ADR-0036-capa-de-sugerencias-aprendida.md), [ADR-0066](ADR-0066-homr-en-la-gpu-de-produccion.md), [ADR-0068](ADR-0068-tablas-y-recortes-en-una-sola-exportacion.md), [ADR-0069](ADR-0069-informe-visual-de-los-errores-de-homr.md), [#255](https://github.com/sebdavid3/Cadenza/issues/255), [#418](https://github.com/sebdavid3/Cadenza/issues/418)

---

## Contexto

El corpus de los errores de HOMR (`exp_12`, #255) son 2 000 incipits de PrIMuS con su imagen limpia, impresa por ordenador. Lo que se sube a Cadenza son fotos. Camera-PrIMuS (Calvo-Zaragoza y Rizo, 2018) trae los mismos 87 678 incipits con la imagen distorsionada para que parezca una foto (ondulada, desenfocada, cortada, con otro contraste) y la misma verdad (MEI y `.semantic`). El responsable decidió el 2026-11-19 ampliar los datos con una muestra de Camera-PrIMuS y no con todo PrIMuS: los demás corpus quedan fuera.

Tres cosas había que resolver: cómo elegir la muestra sin cerrar la puerta a ampliarla, cómo hacer que la partición sea la de #255 y cómo juntar en las tablas y en el informe dos corpus con los mismos identificadores de incipit.

## Decisión

1. **Un experimento nuevo, `exp_18_camera_primus.py`, sin tocar `exp_12` ni `exp_14`.** Reutiliza la transcripción reanudable y la medición de `ml/experiments/external_corpus.py`, que nació en el trabajo de #102 y entra con este cambio, y el análisis de la armadura, el compás y la clave de `exp_12`. La verdad es la de `exp_12`: el MEI con la altura que suena del `.semantic`. HOMR corre en la GPU por defecto (`--cpu` para la CPU), como en producción (ADR-0066), sin preprocesado; el dispositivo queda en `run_info` y la transcripción no mezcla predicciones de dos dispositivos: con `--force` aparta las anteriores y lo repite todo. Escribe archivos nuevos en `results/` (`camera_primus_correction_corpus*` y `exp_18_run_info.json`), con `"simulated": false`.
2. **La muestra es el principio de una ordenación al azar.** Los incipits completos que no están en `exp_03` se ordenan con `random.Random(semilla).shuffle` y se toman los primeros, con la semilla de `exp_12`: **3 000**. Se propusieron 10 000 (unas 1,7 h de HOMR en la GPU) y el responsable decidió el 2026-11-19 cortar en 3 000 por tiempo; HOMR se paró al pasar de 3 000 y la muestra se regeneró con ese tamaño, así que las 3 000 son las primeras de la misma ordenación. Una muestra mayor con la misma semilla empieza por la menor: se puede ampliar sin repetir lo leído. Al sustituirla con `--force`, las predicciones se conservan si una muestra empieza por la otra y, si no, se apartan a `predictions.previas-<fecha>` sin borrarlas. La línea de órdenes no deja cambiar la semilla.
3. **Los identificadores llevan la fuente.** En el corpus, cada incipit es `camera-primus:<id de PrIMuS>`, con `source: camera-primus`, como las sesiones de Cadenza son `cadenza:<sesión>`. La obra (`work_id`) es el registro RISM, la de PrIMuS. Así, el mismo incipit de `exp_12` y de `exp_18` son dos filas distintas en las tablas, el informe y la capa de sugerencias, que agrupan por `incipit_id`.
4. **La partición es la de #255 y se comprueba.** `assign_split` sobre la obra, con la semilla y la fracción de prueba de `exp_12`. `build` lee `results/correction_corpus_split.json` (u otra ruta con `--exp-12-split`) y se niega a escribir si la semilla o la fracción no coinciden o si alguna obra que comparte con `exp_12` cae del otro lado; el resumen dice cuántas obras e incipits comparte.
5. **`ml export-tables` lee varios corpus a la vez.** `--corpus` se repite; un mismo incipit de la misma fuente en dos corpus es un error, porque saldría dos veces. Con un solo corpus, `run_info.origins.corpus` sigue siendo un objeto, con los registros por `source` del archivo añadidos (`sources`); con varios, es una lista, uno por corpus. `--camera-primus-dir` copia la imagen distorsionada de cada incipit a `recortes/camera-primus/`, como `--primus-dir` la de PrIMuS.
6. **El informe nombra Camera-PrIMuS y no separa las fuentes.** `ml/tables_report.py` da a cada fuente su nombre (PrIMuS, Camera-PrIMuS, Cadenza; las que no conoce, por su `source`) en el «Origen» del historial, y explica qué es Camera-PrIMuS como ya explicaba PrIMuS, también que las imágenes que HOMR no lee no están y dónde se cuentan. El filtro sigue siendo el único de ADR-0069 tal como lo dejó #418: el de las pruebas reales.
7. **La capa de sugerencias no se reentrena con este corpus:** mezclarlo con el de `exp_12` es una decisión aparte, con su medición.

## Alternativas consideradas

- **Todo PrIMuS (87 678 incipits limpios).** El issue lo pedía al principio; el responsable lo dejó fuera el 2026-11-19. La imagen limpia ya está medida en `exp_12` y se parece menos a una foto.
- **`random.sample` como en `exp_12`.** Una muestra de 10 000 con la misma semilla no contendría a la de 3 000: ampliar obligaría a leerlo todo de nuevo.
- **Mantener el identificador de PrIMuS y distinguir por `source` en todas partes.** El informe, `corpus_tables` y la capa de sugerencias agrupan por `incipit_id`: habría que cambiar todos y sus pruebas. Con la fuente en el identificador no cambia ninguno, y es la convención de Cadenza.
- **Copiar `exp_12` con otro nombre de salida.** Duplicaría su lectura de la verdad, su derivación y su análisis. Se reutilizan sus funciones de análisis y la medición común de `external_corpus`; solo el resumen se ensambla aparte, con los campos propios (SER, compatibilidad con #255, muestra parcial).

## Consecuencias

- Los datos de los errores de HOMR incluyen una lectura parecida a una foto, con la misma verdad que `exp_12`: se pueden comparar los mismos incipits con imagen limpia y distorsionada.
- Las distorsiones son sintéticas: no son fotos reales de móvil, y así se dice en el resumen y en el informe.
- `exp_18` depende de que `results/correction_corpus_split.json` de `exp_12` exista: sin él falla con un mensaje claro.
