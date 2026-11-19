# Pares imagen–partitura para entrenar un lector (`ml export-pairs`)

> El responsable pidió (2026-11-09, #400) que los datos de la plataforma sirvan para entrenar un
> modelo de transcripción mejor. `ml export-pairs` ([#420](https://github.com/sebdavid3/Cadenza/issues/420),
> [ADR-0071](../adr/ADR-0071-pares-imagen-partitura-para-entrenar-un-lector.md)) deja listos
> los pares: la tira de la foto de cada pentagrama y su partitura en MusicXML, la que leyó HOMR
> y la corregida, con la partición fija por obra y la ficha del dataset. **No entrena nada**:
> reentrenar HOMR es trabajo futuro (D14, [#103](https://github.com/sebdavid3/Cadenza/issues/103)).
> Las tablas de los errores de HOMR están en [`diccionario_tablas.md`](diccionario_tablas.md).

## Uso

```powershell
# Sobre una copia de la base y de sus artefactos, nunca la de producción. La salida ha de estar
# vacía (o no existir) y no puede caer en results/ ni en data/ del repositorio.
uv run --no-sync python -m ml export-pairs --output-dir <carpeta> `
  --db-url <url de la copia> --artifacts-dir <artefactos de la copia> `
  --split-seed <semilla de correction_corpus_split.json> [--test-fraction 0.2] `
  [--exclude-self-registered]
```

- En producción, el procedimiento entero (la copia, la imagen con que se ejecuta, la orden y cómo
  se saca la salida) está en [`operacion_backend.md` §2.5](../infra/operacion_backend.md#25-exportar-los-pares-para-entrenar-un-lector-420-adr-0071).
- `--split-seed` es obligatoria: es la semilla de la partición de #255 (la de
  `correction_corpus_split.json`), la misma de `ml export-tables` y de la capa de sugerencias.
  Pero la obra no es la misma: aquí las sesiones que comparten partitura de prueba o foto son
  una sola obra, y allí cada sesión va por su página. Una página del banco subida sin su
  partitura de prueba puede caer en lados distintos en las dos exportaciones.
- Una obra puede cambiar de lado entre dos exportaciones si cambia la sesión que la unía a otra
  (una nueva, o una que se va porque su cuenta retiró el permiso o por
  `--exclude-self-registered`): un modelo se evalúa con la `test` de la misma exportación con
  la que se entrenó.
- Por defecto entran las cuentas del registro público con el permiso de uso de los datos
  vigente (ADR-0065; decisión del responsable del 2026-11-19, #422); `--exclude-self-registered`
  las deja fuera. Las que no tienen el permiso vigente quedan fuera siempre.

## Qué sesiones entran

| Regla | Motivo en `run_info.json` |
|---|---|
| Solo las finalizadas | (las demás no se leen: su corrección no la dio nadie por buena) |
| Cuenta del registro sin el permiso del texto vigente (nunca dado, retirado o de otro texto), siempre | solo se cuentan, en `consent.sessions_without_current_consent`: ni su identificador sale |
| Cuenta del registro con `--exclude-self-registered` | solo se cuentan, en `consent.sessions_excluded_by_option` |
| Sesión cuya cuenta no está en la base | `sin la cuenta de su dueño` (en `left_out`, como las siguientes) |
| Sin partitura de prueba ni imagen | `sin página de origen (test_score_id ni imagen)` |
| Sin la captura de HOMR (transcrita antes de #403) | `sin la captura de HOMR (transcrita antes de #403)` |
| Corrección que no se verifica (`correction_verified`) | `la corrección no se verifica: …` |
| Sin la foto en los artefactos | `sin la imagen (…)` |
| Imagen preprocesada, captura con errores, otra proporción o cajas que no casan | el de `plan_strips` (ADR-0067) |
| Cualquier otro fallo de una sesión | `no se pudo exportar (…)`, sin parar la exportación |

## La salida

```text
<carpeta>/
  README.md        la ficha del dataset: origen, licencias, permiso, partición y limitaciones
  run_info.json    commit, fecha, filtros, sesiones fuera con su motivo, recuentos y sha256
  pares.csv        una fila por par
  train/<sesión>/s<sistema>_<parte>-<pentagrama>.png             la tira de la foto
  train/<sesión>/s<sistema>_<parte>-<pentagrama>.homr.musicxml   lo que leyó HOMR
  train/<sesión>/s<sistema>_<parte>-<pentagrama>.musicxml        lo corregido (la etiqueta)
  test/…           igual, para las obras de la partición de prueba
```

Un gran pentagrama de piano es un solo par (`_1-0+1-1`): su MusicXML tiene la parte con sus dos
pentagramas. Cada MusicXML tiene solo los compases de la tira, con sus números de la página, y
su primer compás lleva la clave, la armadura y el compás que rigen allí.

## `pares.csv`

| Columna | Qué es |
|---|---|
| `par` | Identificador del par: `<sesión>/s<sistema>_<pentagramas>` |
| `split` | `train` o `test`: la partición fija por obra de #255 |
| `work_id` | La obra sobre la que se parte: `test_score:<id>` o `image:<sha256 de la foto>`. Las sesiones que comparten partitura de prueba o foto son la misma obra (`shared_works`): una página del banco subida sin su partitura de prueba va con ella |
| `session_id` | La sesión de Cadenza |
| `test_score_id` | La partitura de prueba del banco del estudio, si la tiene |
| `source_image_hash` | El sha256 de la foto de la sesión (como en `pentagramas.csv`) |
| `sistema` | Número del sistema en la página, desde 1 |
| `pentagramas` | `parte-pentagrama` del `ScoreIR`, desde 0; dos unidos por `+` en un gran pentagrama |
| `compases`, `primer_compas`, `ultimo_compas` | Cuántos compases tiene la tira, el primero y el último |
| `lectura_homr` | De qué lectura de HOMR salen las cajas (`alone` o `paired`, ADR-0067) |
| `homr_version` | La versión de HOMR que leyó la foto |
| `imagen`, `ancho`, `alto`, `imagen_sha256` | La tira en PNG (ruta relativa), su tamaño en píxeles y su sha256 |
| `homr`, `homr_sha256` | El MusicXML de lo que leyó HOMR y su sha256 |
| `corregida`, `corregida_sha256` | El MusicXML corregido y su sha256 |
| `corregido` | `true` si los dos MusicXML difieren: cualquier corrección de la tira, también de la clave, la armadura, el compás o las marcas (más que el `corregido` de `pentagramas.csv`, que solo mira las notas) |

Las filas van por partición y sesión, y dentro de cada sesión en el orden de la página. La misma
base da el mismo `pares.csv` byte a byte: los MusicXML se escriben sin fecha y con las partes
numeradas (`score_ir_to_musicxml(…, stable=True)`).

## `run_info.json`

`format_version` (1), `simulated: false`, `commit`, `generated_at`, `origin` (solo el dialecto y
el nombre de la base, y el nombre de la carpeta de artefactos), `format` (PNG y MusicXML, con el
ADR), `filters` (`status`, `verified_only`, `exclude_self_registered`, `split_seed`,
`test_fraction`), `consent` (`version` del texto, `sessions_without_current_consent`: las
sesiones de cuentas del registro sin el permiso vigente, y `sessions_excluded_by_option`: las
que deja fuera `--exclude-self-registered`; de esas sesiones no sale el identificador),
`sessions` (las exportadas), `left_out` (las que quedan fuera por otros motivos, con el suyo),
`counts` (pares, pares corregidos, sesiones y obras, en total y por partición),
`homr_versions` (sesiones por versión) y `sha256` de `pares.csv` y de `README.md`.

## Para entrenar HOMR

HOMR entrena con un índice de líneas `imagen,archivo.tokens`, en su formato propio, que genera
desde MusicXML con su conversor (`training/omr_datasets/music_xml_parser.py`), como hace con
OpenScore Lieder y PDMX. Para cada fila de `pares.csv`, `imagen` es la imagen y `corregida` el
MusicXML que se pasa a `.tokens`. Antes conviene decidir si se quita el compás de las tiras que no
empiezan la obra, que la imagen no dibuja (ADR-0071). Esa conversión y el entrenamiento son de
#103.

## Cuidado con los datos

La carpeta tiene fotos de personas y partituras con derechos de terceros: se usa solo dentro del
proyecto, no se publica ni se comparte, y no tiene licencia para redistribuirse (ADR-0065). Una
exportación es una foto fija: si alguien retira su permiso, se borra y se vuelve a exportar.
