# Diccionario de las tablas de correcciones (`ml export-tables`)

> Las estadísticas principales del proyecto son las que permiten reconocer los errores de HOMR,
> para demostrar que los datos de la plataforma servirían para entrenar un modelo de
> transcripción o de sugerencias mejor (decisión del responsable, 2026-11-09). El análisis no
> se hace en la plataforma: `ml export-tables` escribe CSV planos que se leen con pandas, R o
> una hoja de cálculo. Reentrenar HOMR queda fuera de esta versión (#103).

## Uso

```powershell
# Sobre una copia de la base (nunca la de producción): sesiones finalizadas, sin cuentas del
# registro público.
uv run --no-sync python -m ml export-tables --output-dir <carpeta> `
  --db-url <url de la copia> --split-seed <semilla de correction_corpus_split.json>

# El corpus de PrIMuS de exp_12 (o el de `ml suggestions build-dataset`), con las mismas columnas.
uv run --no-sync python -m ml export-tables --output-dir <carpeta> --corpus <corpus.jsonl>

# Las dos fuentes juntas, en las mismas tablas: la columna `source` las distingue. Con la base,
# los registros `source: cadenza` del corpus (los que añade build-dataset) se descartan y sus
# sesiones salen de la base, para no repetirlas.
uv run --no-sync python -m ml export-tables --output-dir <carpeta> --corpus <corpus.jsonl> `
  --db-url <url> --split-seed <semilla>
```

| Opción | Significado |
|---|---|
| `--output-dir` | Obligatoria. Carpeta de los CSV y de `run_info.json`. No hay salida por defecto. |
| `--db-url` | URL de la base. Si no se da `--corpus`, por defecto `CADENZA_DATABASE_URL`; con `--corpus`, la base solo se lee si se da `--db-url`. |
| `--corpus` | Corpus JSONL de correcciones (formato de `build_correction_records`, versión 1). |
| `--split-seed` | Obligatoria con la base: la semilla de la partición de #255. |
| `--test-fraction` | Fracción de prueba de la partición (0,2, como #255). |
| `--include-self-registered` | Incluye las sesiones de cuentas del registro público **con el permiso de uso de los datos de la versión vigente del texto** (ADR-0065; la misma regla que `ml export-staves`, ADR-0067). Las demás cuentas del registro quedan fuera también con la opción. Sin ella, todas fuera. |
| `--include-unfinished` | Incluye las sesiones sin finalizar; su estado final es el último del log, no uno que la persona dio por bueno. |

## Formato

- Un CSV por tabla, en UTF-8 sin BOM, separado por comas, con fin de línea `\n` y una cabecera
  con nombres estables en `snake_case`. Las columnas van siempre en el orden de este documento.
- Vacío es «no aplica» o «no se sabe» (`NA`). Los booleanos son `true` y `false`. Los decimales
  llevan punto.
- Toda columna `*_beats` es una duración en negras como fracción exacta en texto (`1/2`,
  `1/3`), la misma que guarda el corpus; la columna `*_beats_dec` de su lado es su decimal
  redondeado a seis cifras.
- Los nombres de las columnas que vienen del corpus de correcciones conservan los suyos (en
  inglés: `read_pitch`, `ctx_key_fifths`), para que cada columna se reconozca en el JSONL con el
  que se entrena; las que calcula la exportación van en español (`resultado`, `es_inicial`).
- Los valores se escriben tal cual. Los de texto libre (`dismissal_reason`, los nombres de
  usuario) pueden empezar por `=`, `+`, `-` o `@`: una hoja de cálculo los tomaría por fórmulas.
  Importar el CSV como texto o leerlo con pandas o R evita el problema.
- Las tablas se escriben siempre, también vacías, para que las dos fuentes tengan los mismos
  archivos y las mismas columnas.

### `run_info.json`

| Campo | Significado |
|---|---|
| `format_version` | Versión del formato de las tablas (1). |
| `simulated` | Siempre `false`: las tablas son los datos guardados, no una simulación (CLAUDE.md §8). |
| `commit` | Commit del código que exportó (`git rev-parse HEAD`), o `null` fuera de un repositorio. |
| `generated_at` | Fecha y hora de la exportación (UTC, ISO 8601). |
| `origins.database` | `url`: solo el dialecto y el nombre de la base (`postgresql:cadenza`), sin usuario, host ni contraseña; y el número de sesiones exportadas. |
| `origins.corpus` | Nombre del archivo (sin la ruta), sha256 y número de registros del corpus; con la base, `cadenza_records_dropped`: los registros de sesiones de Cadenza que se descartaron porque salen de la base. |
| `filters` | `include_self_registered`, `include_unfinished`, `split_seed`, `test_fraction`. |
| `left_out` | Las sesiones que quedan fuera, con su motivo: `cuenta del registro público`, `cuenta del registro sin el permiso de uso de los datos vigente`, `sin terminar (status …)` o `sin página de origen (test_score_id ni imagen)`. |
| `tables` | Por tabla: filas, filas por `source` y sha256 del CSV. |

## Claves comunes

Todas las tablas empiezan por estas columnas:

| Columna | Significado | Valores |
|---|---|---|
| `source` | De dónde sale la fila. | `cadenza` (una sesión de la plataforma) o `primus` (un incipit del corpus de `exp_12`). Un registro del corpus sin `source` es de PrIMuS. |
| `incipit_id` | Identificador de la partitura en el corpus. Une todas las tablas. | `cadenza:<session_id>` o el identificador de PrIMuS. |
| `session_id` | Sesión de Cadenza. | Vacío en PrIMuS. |
| `work_id` | Página u obra de origen, la unidad de la partición. | `test_score:<id>` o `image:<sha256>` en Cadenza; el registro RISM en PrIMuS. |
| `split` | Partición fija de #255 (ADR-0036 §10): todas las sesiones de una página caen del mismo lado. | `train` o `test`. |

El **ancla** (`part`, `staff`, `measure`, `voice`, `event_index`) es la de ADR-0002: índices de
parte y pentagrama desde 0, número del compás (`measure`, no su posición) y posición del evento
en su voz dentro del compás. En `notas`, `faltantes` y `clave_armadura` es relativa a la lectura
de HOMR (`seq` 0, ADR-0011); en `sugerencias` y `avisos`, al estado en que se generó (`at_seq`).

## Tablas

### `partituras.csv`: una fila por sesión (o por incipit de PrIMuS)

| Columna | Significado | Origen |
|---|---|---|
| `participante` | Nombre de usuario de la cuenta dueña. En las cuentas del estudio es un seudónimo; en las del registro público (`--include-self-registered`) es el que eligió la persona y puede identificarla. | `users.username` |
| `rol` | Rol de la cuenta. | `transcriptor` o `investigador` |
| `origen` | `estudio` si la sesión tiene `test_score_id`; si no, `registro` si la cuenta es del registro público; si no, `equipo`. | calculado |
| `condition` | Condición del estudio. | `assisted` o `unassisted` |
| `test_score_id` | Partitura del banco del estudio (TS-01 a TS-04), si la hay. | `sessions` |
| `status` | Estado de la sesión. | `transcribed`, `finalized`… |
| `omr_engine`, `model_version` | Motor OMR y versión del modelo que leyeron la página. | procedencia del documento |
| `rules_version` | Versión de las reglas de validación al transcribir. | procedencia |
| `source_image_hash` | sha256 de la imagen subida. | procedencia |
| `suggestions_version` | Versión de la capa de sugerencias activa al transcribir. | procedencia |
| `partes`, `pentagramas`, `compases` | Tamaño de la lectura de HOMR. | lectura |
| `eventos_leidos`, `eventos_finales` | Eventos (notas, silencios y huecos de voz) de la lectura y del estado final. | lectura y `materialize` |
| `ediciones_log` | Filas del log de ediciones, deshacer y rehacer incluidos. | `edit_events` |
| `correcciones_netas` | Ediciones que derivan de la lectura al estado final (`derive_edit_events`): la suma de los `ops` de `notas`, `faltantes` y `clave_armadura`. Un evento con la altura y la figura corregidas cuenta dos. No incluye la indicación de compás. | calculado |
| `compases_con_indicacion_corregida` | Compases cuya indicación de compás cambió (ver `compases`). | calculado |
| `verified` | Si `materialize(lectura, derive_edit_events(lectura, final))` reproduce el estado final: solo entonces las correcciones de la sesión son etiquetas de confianza. | `session_records` |
| `versiones_capa` | Versiones de la capa aprendida de las sugerencias guardadas en la sesión, unidas con `+`. | `suggestions.model_version` |
| `permiso_datos` | Si la cuenta tiene el permiso de uso de los datos de la versión vigente del texto (#378, ADR-0065). Una cuenta del registro sin él no llega a las tablas. | `users.data_consent_at`, `users.data_consent_version` |
| `created_at` | Fecha de la sesión (ISO 8601). | `sessions` |

No hay `source_filename`: un nombre de archivo puede llevar datos personales. En PrIMuS solo
se rellenan las claves, `eventos_leidos`, `correcciones_netas` y `verified`.

### `notas.csv`: una fila por evento leído (registro `event`)

| Columna | Significado |
|---|---|
| `verified` | El de su partitura. |
| `aligned` | `false` si el evento está en un compás que la lectura tiene de más: no hay estado final con que compararlo. |
| ancla | Ver arriba. |
| `read_kind` | `note` o `rest`. |
| `read_pitch` | Altura leída en notación científica (`C4`, `Bb3`, `F#5`); vacío en un silencio. |
| `read_duration_beats` (`_dec`) | Figura leída, en negras. |
| `read_tie` | Ligadura de prolongación leída: `start`, `continue`, `stop` o vacío. |
| `read_is_chord` | Si suena con la nota anterior (nota de acorde). |
| `read_hidden` | Si es un hueco de voz (silencio invisible, ADR-0032). |
| `resultado` | `bien` (sin corrección), `corregida`, `borrada` o `sin_alinear` (`aligned` falso). |
| `ops` | Operaciones de la corrección unidas con `+`, en el orden de `derive_edit_events`: `SetPitch`, `SetAccidental`, `SetDuration`, `DeleteEvent`. |
| `fix_pitch` | Altura final, si cambió. |
| `fix_accidental_before`, `fix_accidental_after` | Alteración leída y final con `SetAccidental`: `#`, `b`, `##`, `bb` o vacío (natural, sin signo). |
| `fix_duration_beats` (`_dec`) | Figura final, si cambió. |
| `ctx_clef` | Clave vigente: signo y línea (`G2`, `F4`, `C3`), con el cambio de octava (`G2-1`). |
| `ctx_key_fifths` | Armadura vigente en quintas (−7 a 7). |
| `ctx_time_signature` | Indicación de compás vigente (`3/4`); vacío si la partitura no tiene. |
| `ctx_measure_index` | Posición del compás en el pentagrama, desde 0. |
| `ctx_measures_in_staff` | Compases del pentagrama. |
| `ctx_events_in_voice` | Eventos leídos de la voz en el compás. |
| `ctx_measure_beats_read` (`_dec`) | Lo que suman las figuras leídas de la voz en el compás. |
| `ctx_measure_capacity_beats` (`_dec`) | Lo que debería durar el compás según su indicación. |
| `ctx_measure_balance_beats` (`_dec`) | Lo que le sobra (positivo) o le falta (negativo) a la voz en el compás. |
| `ctx_onset_beats` (`_dec`) | Dónde empieza el evento dentro del compás. |
| `ctx_accidental` | Alteración escrita de la nota leída. |
| `ctx_key_accidental` | Alteración que la armadura impone a su letra. |
| `ctx_accidental_vs_key` | `in_key` si coinciden, `against_key` si no. |
| `ctx_previous_accidental_same_step` | Alteración de la última nota de la misma letra y octava antes en el compás. |
| `prev_kind`, `prev_pitch`, `prev_duration_beats` (`_dec`) | El evento anterior de la misma voz en el pentagrama (vacío al principio). |
| `next_kind`, `next_pitch`, `next_duration_beats` (`_dec`) | El siguiente. |

El contexto solo usa lo leído, porque es lo que vería un modelo; la verdad solo está en las
columnas `fix_*` y en `resultado`.

### `faltantes.csv`: una fila por evento que faltaba (registro `insertion`)

Un evento del estado final que la lectura no tiene, delante del evento leído de su ancla
(`event_index` puede ser el número de eventos de la voz: falta al final).

| Columna | Significado |
|---|---|
| `ins_kind`, `ins_pitch`, `ins_duration_beats` (`_dec`), `ins_tie`, `ins_is_chord`, `ins_hidden` | El evento que faltaba, como en `read_*`. |
| `ctx_*`, `prev_*`, `next_*` | El contexto del hueco, como en `notas`; las columnas de la alteración van vacías. |

### `clave_armadura.csv`: una fila por compás con la clave o la armadura corregidas (registro `measure`)

| Columna | Significado |
|---|---|
| `read_clef`, `read_key_fifths` | La clave y la armadura escritas en el compás leído (vacías si hereda las anteriores). |
| `ops` | `SetClef`, `SetKey` o `SetClef+SetKey`. |
| `fix_clef`, `fix_key_fifths` | Las finales. |

### `compases.csv`: una fila por sesión, parte, pentagrama y compás (solo Cadenza)

Compara la lectura y el estado final compás a compás, sin pasar por `derive_edit_events`: así
se ve también lo que esa alineación no recoge, como la indicación de compás. Desde la vista no
se insertan ni se borran compases (no hay ninguna `EditOp` para eso, y `SetTime` cambia la
indicación sin mover compases), así que el compás N leído es el compás N final.

| Columna | Significado |
|---|---|
| `part`, `staff`, `measure` | Parte, pentagrama y número del compás. |
| `measure_index` | Posición del compás en el pentagrama, desde 0. |
| `time_read`, `time_final` | Indicación de compás vigente leída y final. |
| `clef_read`, `clef_final` | Clave vigente leída y final. |
| `key_fifths_read`, `key_fifths_final` | Armadura vigente leída y final. |
| `eventos_leidos`, `eventos_finales` | Eventos del compás, todas las voces. |
| `notas_corregidas`, `notas_borradas`, `faltantes` | Filas de `notas` (corregidas y borradas) y de `faltantes` en el compás. |
| `clave_corregida`, `armadura_corregida` | Si `clave_armadura` corrige la clave o la armadura del compás. |
| `indicacion_corregida` | Si la indicación vigente cambió. |
| `correcciones_netas` | Ediciones derivadas en el compás (los `ops` de sus filas de `notas`, `faltantes` y `clave_armadura`); no incluye la indicación. |
| `avisos_iniciales` | Posibles errores de la validación de la lectura (`at_seq` 0) anclados en el compás. |
| `avisos_vigentes` | Los de la validación vigente (`validated_at_seq`). |
| `avisos_descartados` | Los de la validación vigente descartados por la persona (una revalidación hereda los descartes, ADR-0035, así que la vigente es la última palabra). |

### `sugerencias.csv`: una fila por sugerencia

| Columna | Significado |
|---|---|
| `condition` | La de la sesión. |
| `suggestion_id` | Identificador en la base (vacío si la fila viene de un corpus JSONL). |
| `response` | `accepted`, `rejected` o `ignored` (sin respuesta). |
| `es_heredada` | `true` si es un rechazo heredado de la validación anterior (ADR-0036 §4): repite el de `inherited_from` y **no es otra respuesta**; para contar respuestas, filtrar `es_heredada = false`. |
| `inherited_from` | La sugerencia cuyo rechazo hereda. |
| `responded_by`, `responded_at` | Quién (su nombre de usuario, como `participante`) y cuándo respondió. |
| `at_seq` | Estado sobre el que se propuso. |
| `rank` | Orden entre las sugerencias de su posible error (0 la primera). |
| `op`, ancla, `after_json` | La edición propuesta, con su `after` en JSON. |
| `confidence` | Probabilidad que dio la capa (0 a 1), o vacío. |
| `confidence_level` | `high` o `medium` (solo de la base). |
| `suggestion_source` | `learned` (de la capa) o `rule` (candidato de una regla). |
| `model_version` | Versión de la capa. |
| `linked_to_finding` | Si sigue unida a un posible error (una revalidación del mismo estado desvincula las que tenían respuesta). |
| `finding_rule_id` | Regla de ese posible error, si sigue unida (solo de la base). |
| `applied_seq` | `seq` de la edición que la aplicó, si se aceptó. |

### `avisos.csv`: una fila por posible error (solo Cadenza)

| Columna | Significado |
|---|---|
| `finding_id` | Identificador en la base. |
| `at_seq` | Estado validado: 0 es la lectura original; revalidar añade otros sin borrar los anteriores. |
| `es_inicial` | `at_seq` 0. |
| `es_vigente` | Es de la validación vigente (`sessions.validated_at_seq`). |
| `rule_id`, `severity` | Regla (catálogo de ADR-0040) y gravedad: `info`, `warning` o `error`. |
| ancla | La del posible error, relativa a su `at_seq`. |
| `status` | `active` o `dismissed`. |
| `dismissal_reason` | Motivo del descarte, si se dio. **Es texto libre**: revisarlo antes de compartir las tablas. |
| `compas_con_correccion` | Si su compás tiene alguna corrección neta o la indicación corregida en `compases`. Se une por compás, no por evento, porque el `event_index` cambia entre estados. |

## La «respuesta correcta» y sus límites

- **La verdad es la de una persona, no una partitura de referencia.** En Cadenza, el estado
  final es lo que dejó quien corrigió. Un error de HOMR que se le escapó cuenta como `bien`, y
  una corrección equivocada cuenta como corrección. Las tasas de error que salgan de estas
  tablas son, por eso, una cota inferior de los errores de HOMR, sesgada hacia lo que una
  persona ve. En PrIMuS la verdad es la del corpus.
- Con `--include-unfinished`, el estado final de una sesión sin finalizar es el último del log,
  que la persona aún no dio por bueno.
- `verified` falso marca las sesiones cuyas correcciones derivadas no reproducen el estado final:
  sus etiquetas no son de confianza.

### Limitaciones conocidas (no se arreglan aquí)

- `derive_edit_events` no alinea las indicaciones de compás: no hay filas de `notas` ni de
  `clave_armadura` para ellas, y `verified` no lo nota, porque la comparación estructural de
  `session_records` no mira la indicación (una sesión con solo el compás corregido sale con
  `verified` verdadero y ninguna corrección neta). Se ven en `compases.indicacion_corregida` y
  en `partituras.compases_con_indicacion_corregida`.
- Un tresillo o la figura de un acorde, que en la vista son una sola edición (`SetTuplet`,
  `SetChordDuration`), salen como un `SetDuration` por nota.
- Una ligadura de prolongación corregida (`SetTie`) sale como borrar e insertar.
- Las marcas (articulaciones, dinámicas, ligaduras de expresión, reguladores) no entran en el
  dataset (ADR-0031 §6, ADR-0039): sus ediciones no dejan filas.
- Las uniones por compás (`compases`, `avisos.compas_con_correccion`) usan el número del
  compás: si una lectura repitiera un número en un pentagrama, esos compases compartirían sus
  recuentos.
- Una sesión sin ningún registro del corpus (una partitura vacía) sale con `verified` vacío.
- `notas` y `faltantes` alinean por voz dentro del compás: un evento cambiado de voz sale como
  borrado y faltante.
