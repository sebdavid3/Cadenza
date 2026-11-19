# INV-0003: SMB y MUSCIMA++ — qué traen, su licencia y cuánto falla HOMR con ellos

- **Fecha:** 2026-11-19
- **Issue:** [#102](https://github.com/sebdavid3/Cadenza/issues/102) (Fase 12, milestone 10); cifras para el informe ([#418](https://github.com/sebdavid3/Cadenza/issues/418)) y la portada ([#423](https://github.com/sebdavid3/Cadenza/issues/423), [#424](https://github.com/sebdavid3/Cadenza/issues/424))
- **Relacionado:** [ADR-0072](../adr/ADR-0072-smb-y-muscima-en-el-corpus-de-correcciones.md), [ADR-0036](../adr/ADR-0036-capa-de-sugerencias-aprendida.md), [ADR-0066](../adr/ADR-0066-homr-en-la-gpu-de-produccion.md), [#255](https://github.com/sebdavid3/Cadenza/issues/255)
- **Estado:** MUSCIMA++ medido (`exp_16`). SMB sin datos: el responsable decidió el 2026-11-19 no esperar su acceso restringido; `exp_17` queda listo y sin ejecutar.

> Las cifras de la §4 son de la ejecución del 2026-11-19 con el commit a1b2b57 (`results/muscima_homr_summary.json`, sin versionar). Antes de citarlas hay que regenerarlas con la §6 (`CLAUDE.md` §8.4).

---

## 1. Por qué

Los datos de los errores de HOMR salían solo de PrIMuS (`exp_12`): *incipits* impresos, dibujados con Verovio, de una voz. El objetivo 1 de la tesis prometía además SMB y MUSCIMA++ (D34); `exp_09`, que los simulaba, se retiró en #271. El 2026-11-19 el responsable los metió en la Fase 12.

## 2. Qué trae cada corpus

| | PrIMuS (`exp_12`) | SMB (`exp_17`) | MUSCIMA++ v2.0 (`exp_16`) |
|---|---|---|---|
| **Música** | *Incipits* de RISM, impresos y sintéticos | Páginas reales escaneadas, de KernScores (del Barroco al *ragtime*) | Música manuscrita: 20 páginas copiadas a mano por copistas distintos |
| **Textura** | Una voz | Monodia, piano, cuarteto y otras | Solistas, piano, coro y orquesta |
| **Tamaño** | 87 678 *incipits* (se usan 2 000) | 685 páginas, 4 039 regiones (artículo) | 140 imágenes: 20 páginas × 7 copistas |
| **Verdad** | MEI y `.semantic` | **kern por región (pentagrama o sistema) | Grafo de símbolos MuNG: cabezas, plicas, barras, alteraciones, claves…, con sus cajas y enlaces |
| **Cómo la lee Cadenza** | `read_score` y la altura que suena del `.semantic` | `read_score` (**kern) | `cadenza.learning.muscima`: inferencia propia, solo un pentagrama por sistema y una voz |
| **Licencia** | Investigación | CC BY-NC 4.0 según su ficha; el artículo no la dice | CC BY-NC-SA 4.0 (anotaciones); CVC-MUSCIMA, investigación |
| **Acceso** | Libre | Restringido, con aprobación manual de los autores | Libre |
| **¿Lo vio HOMR al entrenarse?** | Hasta la 0.7.x, sí (Camera-PrIMuS) | No las imágenes; sí música de KernScores renderizada (GrandStaff). Sus autores lo usan como banco al elegir modelos | No: nada manuscrito |

### 2.1. SMB

*Sheet Music Benchmark* (Martinez-Sevilla et al., ISMIR 2025, arXiv 2506.10488), en Hugging Face como `PRAIG/SMB`, revisión `1b75cc8` (2026-09-29).

- **Archivos:** `data/test-00000-of-00001.parquet` (366 854 135 bytes) con todo, o `metadata.jsonl` (19 791 539 bytes) y 685 PNG bajo `test/` (361 716 881 bytes en total). Columnas: `image`, `id`, `original_width`, `original_height`, `regions` (cada una con `bbox` en porcentajes de la imagen, `raw`, `kern` y `ekern`), `page_texture`, `page` y `original_score`.
- **Composición según el artículo** (páginas / regiones): monodia 115 / 972, piano 469 / 2 686, cuarteto 79 / 304, otras 22 / 77. No se ha comprobado con los datos.
- **Licencia:** la ficha de Hugging Face declara CC BY-NC 4.0; el artículo no declara ninguna. Las imágenes son escaneos de dominio público cuando existen. Uso no comercial y de investigación, compatible con la tesis; nada se redistribuye.
- **Acceso:** restringido con aprobación manual (`gated: manual`): el responsable tiene que pedirlo con su cuenta y los autores lo aprueban a mano. El 2026-11-19 el responsable decidió no esperarlo.
- **Relación con HOMR:** su transformador se entrenó con GrandStaff, que es música de KernScores renderizada con Verovio (`LICENSE_FAQ.md` de HOMR): puede conocer la música de algunas regiones, no sus imágenes. Sus autores publican además una cifra de SMB en cada entrenamiento (`Training.md`, «SMB scores»), con su propio cálculo: no es comparable con el OMR-NED de Cadenza y no se cita como resultado.

### 2.2. MUSCIMA++ v2.0

Hajič jr. y Pecina (ICDAR 2017), versión 2.0 en `github.com/OMR-Research/muscima-pp` (commit `9a1aa68`, carpeta `v2.0`: 140 anotaciones MuNG y sus especificaciones, 89 836 042 bytes). La versión 2.1 no está publicada (su carpeta solo trae los metadatos) y LINDAT solo sirve la 1.0.

- **Imágenes:** no vienen con las anotaciones. Son de CVC-MUSCIMA (Fornés et al., 2012), cuya web oficial devuelve 404 desde el CVC; se bajaron de la réplica `github.com/apacha/OMR-Datasets` (`CVC_MUSCIMA_PP_Annotated-Images.zip`, 8 038 367 bytes, sha256 `54c739621e480a1111ca85b21b010156942fd518e596cb2800b086402dbd5e3b`): las 140 imágenes anotadas, binarias, con pentagramas, en blanco sobre negro.
- **Licencia:** CC BY-NC-SA 4.0 para las anotaciones; CVC-MUSCIMA se publicó para investigación y la réplica lo etiqueta también CC BY-NC-SA 4.0. Nada se redistribuye.
- **Relación con HOMR:** su segmentación se entrenó con DeepScoresV2 y su transformador con Lieder, StringQuartets, GrandStaff y PDMX (`LICENSE_FAQ.md`): todo impreso o renderizado. MUSCIMA++ queda fuera de lo que conoce.

## 3. ¿Se puede convertir MuNG a `ScoreIR`?

**En parte.** MuNG anota los símbolos y sus relaciones, no la partitura: cada cabeza enlaza con su línea o espacio del pentagrama (o con sus líneas adicionales), su plica, sus barras o corchetes, sus puntillos, su alteración y su ligadura; las claves, armaduras, compases y barras de compás enlazan con su pentagrama. De ahí salen la altura y la duración con reglas fijas (`cadenza.learning.muscima`; la de la posición en el pentagrama es la de la inferencia de referencia de `mung`, MIT). Lo que no sale:

- **Las voces.** MuNG no las anota, y la inferencia de referencia se niega a ordenar los ataques de música polifónica (`Cannot deal with onsets in polyphonic music yet`). Inventarlas con la dirección de las plicas sería una verdad de Cadenza, no del corpus.
- **Los sistemas de varios pentagramas** (piano, coro, orquesta), por lo mismo y porque habría que repartir los pentagramas en partes.
- **Los compases abreviados** (`multiMeasureRest`, `repeat1Bar`): su contenido no está escrito y su número no está enlazado.
- **Una clave de do entre dos líneas** sin otra clave de do antes en la página: el centro de su caja no dice qué línea marca (con otra antes, se toma su línea).

La polifonía se detecta sin voces: una cabeza con dos plicas, o dos grupos de cabezas de plicas distintas que se solapan en horizontal (en una voz, cada cabeza empieza a la derecha de la anterior). Un silencio solo cuenta si comparte más de la mitad de su anchura: los silencios escritos a mano invaden a menudo la cabeza vecina. Las barras de repetición cierran el compás aunque no enlacen con su pentagrama.

Por eso se convierten solo las páginas de **un pentagrama por sistema y una voz**; las demás se rechazan con su motivo y se miden solo con la tasa de fallos y los recuentos. Las notas de adorno quedan fuera de la verdad (el dominio no las tiene) y se cuentan aparte. Es un **resultado negativo para la mayor parte del corpus** y positivo para el subconjunto de una voz.

La verdad inferida se comprueba sin HOMR de dos formas (§4.3): los compases con compás conocido deben sumar lo que pide el compás, y las versiones de una misma página de copistas distintos deben parecerse. Las diferencias que quedan mezclan errores de copia, de anotación y de la conversión.

## 4. Resultados de MUSCIMA++ (`exp_16`, 2026-11-19)

HOMR 0.7.0 en la GPU de la máquina de desarrollo, sin preprocesado; las imágenes se invierten a negro sobre blanco.

### 4.1. Tasa de fallos

HOMR no falló en ninguna de las 140 imágenes (0 / 140): siempre encontró pentagramas y devolvió un MusicXML. Pero **Cadenza no puede leer 7 de esos MusicXML** (5,0 %): music21 se detiene con `float division by zero` al calcular la proporción de un compás (`barDurationProportion`) en lecturas sin indicación de compás. Son W-02, W-09, W-30 y W-44 de la página 17, W-18 de la 12, W-29 de la 15 y W-44 de la 06. Para el usuario, una lectura que la plataforma no abre es un fallo: `transcription.unusable` del resumen los cuenta juntos.

### 4.2. Cuánto lee

En las 133 imágenes que se leen, HOMR devuelve **0,87 notas por cabeza anotada** en las páginas de sistemas de varios pentagramas (10 333 notas frente a 11 923 cabezas, 69 imágenes) y **0,89** en las de un pentagrama por sistema (8 769 frente a 9 888, 71 imágenes). Es un recuento, no un acierto: dice que lee casi tantas notas como hay, no que las lea bien (§4.4).

### 4.3. Conversión y calidad de la verdad

Se convierten **24 de las 140 imágenes** (17,1 %), de 5 páginas de música: 01 (4 copias), 02 (1), 06 (6), 13 (6) y 15 (7). Las demás quedan fuera por sistemas de varios pentagramas (69), polifonía (32), compases abreviados (14) o una armadura con sostenidos y bemoles a la vez (1, W-45 de la página 01). Las páginas 07, 09, 11 y 19, de un pentagrama por sistema, se rechazan por polifonía en sus 7 copias.

La verdad convertida es coherente:

- de los 175 compases con indicación de compás anotada, **161 suman exactamente lo que pide (92,0 %)**; en los compases sin compás anotado, 647 de 701 (92,3 %) suman lo que suman más a menudo los de su página, una comprobación más débil que no ve un error repetido en todas las copias;
- entre las versiones de una misma página de copistas distintos (57 pares), la **SER media es 0,038** (mediana 0,039): por página, 0,044 en la 01, 0,041 en la 06, 0,032 en la 13 y 0,039 en la 15. Esa diferencia mezcla errores de copia, de anotación y de la conversión, y es más de diez veces menor que la de HOMR (§4.4).

Un error que comparten todas las copias no lo ve ninguna de las dos comprobaciones: en la página 15, por ejemplo, los tresillos que solo marcan el primer grupo dejan sin anotar los siguientes (como en la partitura impresa, el resto se sobreentiende), y sus compases suman de más en todas las copias.

### 4.4. Métricas en el subconjunto convertido

De las 24 imágenes convertidas, 23 se pueden comparar (la de W-44 en la página 06 es una de las ilegibles).

| Métrica | Media | Mediana | Con la ilegible como distancia máxima (media) |
|---|---|---|---|
| SER | 0,668 | 0,667 | 0,682 |
| OMR-NED | 0,707 | 0,726 | 0,719 |

- **Compases:** HOMR lee el mismo número de compases que la verdad en **3 de 23 imágenes**; en 19 lee de más y en 1 de menos.
- **Verificación:** ninguna de las 23 queda verificada (`materialize(predicho, correcciones) == verdad`). La derivación empareja los compases por su posición y no corrige cuántos hay, así que en las 20 imágenes con otro número de compases sus correcciones son, sobre todo, de alineación. El corpus (`results/muscima_correction_corpus.jsonl`, 5 031 registros) **no tiene etiquetas de confianza**: sirve para describir los errores, no para entrenar la capa de sugerencias.
- **Correcciones del corrector ideal**, solo en las 3 imágenes con los compases alineados (W-31 de la página 01, W-36 y W-50 de la 15; 425 notas): 446 correcciones, **1,05 por nota**. Cambios de altura 57,2 %, de duración 21,7 %, inserciones 11,7 %, borrados 5,6 %, alteraciones 3,1 %, 2 claves y 1 armadura. Son tres imágenes de dos páginas: un indicio, no una distribución.
- **Partición:** las 5 páginas convertidas caen en `train` con la semilla por defecto; el corpus no tiene `test`.

En resumen: HOMR casi nunca se niega a leer música manuscrita, pero lo que lee se parece poco a la partitura: en el subconjunto que se puede medir, la distancia de edición equivale a dos tercios de los símbolos de la partitura (SER 0,67), y casi siempre lee otro número de compases.

## 5. SMB: plan pendiente de acceso

`exp_17_smb_homr.py` está escrito y probado con páginas de ejemplo, no con SMB:

1. El responsable pide el acceso a `PRAIG/SMB` con su cuenta y, aprobado, baja el parquet a `data/smb/`. Se añade `pyarrow` al grupo `dev` (`uv add --group dev pyarrow --no-sync` y `uv sync --inexact`).
2. `prepare` recorta cada región con **kern (la unidad es la región, como el incipit de `exp_12`) y escribe su imagen y su verdad.
3. Piloto: `transcribe --limit 30` y revisar a ojo los recortes y las lecturas; si HOMR necesita margen alrededor del sistema, `prepare --force --margin 0.1`.
4. `transcribe` completo y `build`: tasa de fallos, SER y OMR-NED por textura y el corpus `results/smb_correction_corpus.jsonl` (`source = smb`, obra `smb:<original_score>`).

## 6. Cómo regenerar

Con las anotaciones y las imágenes en `data/muscima/` (§2.2):

```powershell
uv run --no-sync python ml/experiments/exp_16_muscima_homr.py prepare
uv run --no-sync python ml/experiments/exp_16_muscima_homr.py transcribe
uv run --no-sync python ml/experiments/exp_16_muscima_homr.py build
```

Salidas: `results/muscima_homr_summary.json`, `results/muscima_homr_images.csv`, `results/muscima_correction_corpus.jsonl` y `results/exp_16_run_info.json`.

## 7. Límites

- Las 140 imágenes son 20 páginas de música: la variedad es la de 20 piezas. La partición del corpus agrupa las 7 copias de cada página.
- La verdad de MUSCIMA++ es inferida y solo del subconjunto de una voz; su calidad está medida, no garantizada.
- Los recuentos de notas dicen cuánto lee HOMR, no si lo lee bien.
- HOMR se ejecutó en la GPU (como producción desde ADR-0066); `exp_12` se midió en CPU.
