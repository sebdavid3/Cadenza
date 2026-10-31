# ADR-0036: Capa de sugerencias que aprende de las correcciones

- **Estado:** Aceptado
- **Fecha:** 2026-10-30
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0001, ADR-0003, ADR-0007, ADR-0009, ADR-0011, ADR-0012, ADR-0013, ADR-0017, ADR-0018 y ADR-0035, CLAUDE.md §9 y §10). Complementa ADR-0008, que sigue rigiendo el motor OMR y su artefacto ONNX: este artefacto es un JSON con otras métricas.
- **Relacionado:** [ADR-0003](ADR-0003-separacion-planos-computo.md), [ADR-0008](ADR-0008-active-learning-model-registry.md), [ADR-0011](ADR-0011-semantica-de-anclas-ante-ediciones.md), [ADR-0012](ADR-0012-autenticacion-e-identidad.md), [ADR-0013](ADR-0013-revalidacion-y-versionado-de-hallazgos.md), [ADR-0017](ADR-0017-validacion-del-contenido-de-las-ediciones.md), [ADR-0018](ADR-0018-homr-como-unico-motor-omr.md), [ADR-0034](ADR-0034-deshacer-y-rehacer-desde-la-vista.md), [ADR-0035](ADR-0035-descartar-restaurar-y-revalidar-desde-la-vista.md), [#255](https://github.com/sebdavid3/Cadenza/issues/255), [#256](https://github.com/sebdavid3/Cadenza/issues/256), [#257](https://github.com/sebdavid3/Cadenza/issues/257), [#258](https://github.com/sebdavid3/Cadenza/issues/258), [#244](https://github.com/sebdavid3/Cadenza/issues/244), [#245](https://github.com/sebdavid3/Cadenza/issues/245), [#246](https://github.com/sebdavid3/Cadenza/issues/246), [#187](https://github.com/sebdavid3/Cadenza/issues/187), [#271](https://github.com/sebdavid3/Cadenza/issues/271)

---

## Contexto

La capa de sugerencias es el estandarte del plan de cierre ([#231](https://github.com/sebdavid3/Cadenza/issues/231)): HOMR sigue como único motor (ADR-0018) y lo propio de Cadenza es aprender de las correcciones para proponer arreglos concretos y señalar errores que las reglas no ven. Hechos comprobados en el código y en los resultados el 2026-10-30:

- **Las reglas no ven la mayoría de los errores.** En `exp_06` (91 incipits de PrIMuS, línea base provisional hasta [#246](https://github.com/sebdavid3/Cadenza/issues/246)) marcan 80 de 201 compases con errores, y 42 de 127 con errores de alteración (`results/validation_error_coverage.json`); 37 de esos 42 los ve solo `measure.balance`, anclada al primer evento de la voz.
- **Los datos para aprender están en construcción.** `exp_12` ([#255](https://github.com/sebdavid3/Cadenza/issues/255), en curso) construye un corpus por nota (`results/correction_corpus.jsonl`) a partir de una muestra prevista de 2 000 incipits de PrIMuS transcritos con HOMR en CPU, con las correcciones verificadas (`materialize(predicho, ediciones) == verdad`), una partición fija de entrenamiento y prueba **por obra** (el registro RISM, `cadenza.learning.primus_work_id`, con `cadenza.learning.assign_split`) y, por cada evento leído, su contexto **leído**: armadura, compás y clave vigentes, posición en el compás, lo que le sobra o le falta al compás, la alteración frente a la armadura y a la última de su altura en el compás, y las notas vecinas. Hay además registros `insertion` (un evento que falta, con el contexto de su hueco) y `measure` (la clave o la armadura de un compás). Las cifras se citan desde `results/correction_corpus_summary.json` (CLAUDE.md §8), no desde este ADR.
- **Las sugerencias de hoy son texto.** `Finding.suggested_fix` es una cadena libre que solo rellenan las reglas y la web no muestra.
- **El registro de modelos es del motor OMR.** `ModelVersionData` lleva SER y OMR-NED, la tabla `model_versions` los exige (`NOT NULL`) y la API resuelve de él la versión activa de HOMR (`from_active_model`). `PyTorchTrainer` estima una «magnitud de corrección» con métricas de reserva ([#271](https://github.com/sebdavid3/Cadenza/issues/271)) y no sirve de base.
- **La salida cruda de HOMR ya se conserva.** El log es append-only (ADR-0007) y el estado 0 de cada sesión es lo que leyó HOMR.
- **Validar sustituye.** `replace_findings` borra los hallazgos de la sesión con el mismo `(session_id, at_seq)` antes de guardar los nuevos; `revalidate` y `finalize_session` lo usan, y una revalidación solo hereda los descartes de la validación vigente (ADR-0035). Una sesión `unassisted` (D38) no genera hallazgos.
- **Dependencias entre paquetes.** `cadenza-validation` solo depende de `cadenza-domain`; `cadenza-application` depende de `cadenza-validation` (`revalidate`, `finalize_session` y `transcribe_score` reciben un `ValidationEngine`) y no puede importar FastAPI, SQLAlchemy, music21 ni HOMR (CLAUDE.md §10). La API depende de `cadenza.validation` y no de `cadenza.learning`, que es el plano fuera de línea (ADR-0003).

## Decisión

### 1. El modelo: frecuencias suavizadas con retroceso

La capa es una **tabla de frecuencias de correcciones por contexto, con suavizado y retroceso** de lo particular a lo general, en Python puro y sin dependencias nuevas:

- Para cada evento leído, una **clave de contexto** con los rasgos del §2, y para cada clave, cuántas veces su corrección fue cada una de las posibles (ninguna, una alteración concreta, una figura concreta, borrar, una altura a cierta distancia diatónica), contadas sobre los registros `event` **verificados** de la partición de entrenamiento.
- La probabilidad de cada corrección es la frecuencia de la clave más específica con apoyo suficiente (al menos `min_support` observaciones), suavizada hacia la distribución de su clave más general (suavizado aditivo con peso `alpha`). Los niveles de retroceso de cada familia están en la configuración: por ejemplo, para la alteración, (letra, alteración leída, armadura, alteración previa en el compás) → (alteración leída frente a la armadura, alteración previa) → (alteración leída frente a la armadura) → todo.
- **Las inserciones** se puntúan con una tabla aparte sobre los registros `insertion`, con el contexto del hueco (qué evento falta delante del evento leído o al final de la voz). Solo sirven para ordenar candidatos de las reglas (§3); no hay familia `learned.insert`. Los registros `measure` (clave y armadura) quedan **fuera** de la capa.
- **Por qué esto y no un árbol o una red.** Es explicable palabra por palabra («en 312 de 1 040 notas parecidas, la corrección fue…»), se entrena en segundos, el artefacto es un JSON que se lee sin código de entrenamiento y su coste en línea es una búsqueda en un diccionario por evento. Un árbol de decisión exige scikit-learn en la API o un intérprete propio, y no explica mejor. Si la medición de [#257](https://github.com/sebdavid3/Cadenza/issues/257) muestra que las frecuencias se quedan cortas, un árbol se añade como otra implementación del mismo puerto (§7), con otro `model_type`.
- **No reentrena HOMR** ni toca su salida: trabaja sobre el `ScoreIR` leído (ADR-0018; [#103](https://github.com/sebdavid3/Cadenza/issues/103) sigue fuera).

### 2. Los rasgos

Una sola función calcula los rasgos de un evento leído, en `packages/validation` (`cadenza.validation.learned`), y la usan el corpus ([#255](https://github.com/sebdavid3/Cadenza/issues/255)), el entrenamiento y la inferencia: el contexto que se aprende es el mismo que se ve en línea. La implementación de #256 traslada a ella el cálculo del contexto de `cadenza.learning.correction_corpus`; una prueba compara el contexto común de ambos sobre el corpus. Los rasgos, solo de lo **leído**:

- el evento: nota o silencio, figura y puntillo (derivados de `duration_beats`), letra, octava y alteración;
- la alteración frente a la armadura vigente (`in_key`/`against_key`) y la última alteración de la misma letra y octava en el compás;
- la armadura, el compás y la clave vigentes;
- la posición en el compás (`onset_beats`, y si cae en un pulso, derivado) y el índice del evento;
- lo que le sobra o le falta al compás de su voz (`measure_balance_beats`, con su signo y su cuantía);
- las notas vecinas en la voz (tipo, altura y figura de la anterior y la siguiente).

Los metadatos del corpus (`aligned`, `verified`, `split`, `incipit_id`) nunca son rasgos. La función lleva un `FEATURE_VERSION`; cambiar los rasgos (por ejemplo, el compás con su símbolo de [#236](https://github.com/sebdavid3/Cadenza/issues/236)) sube la versión.

### 3. Cómo se combina con las reglas

La capa corre **después** de las reglas, en cada validación (la de la transcripción, `revalidate` y la de `finalize_session`), sobre el mismo documento. La combinación la hacen los **casos de uso**: primero `validator.validate(doc)` y después `model.suggest(doc, findings)`.

1. **Las reglas acotan y la capa ordena.** Una regla que sabe qué arreglos cuadran (por ejemplo, `measure.balance`: al compás de 4/4 le falta media negra, y cuadra pasar una corchea a negra, poner un puntillo o añadir un silencio de corchea) los entrega como **candidatos** en su `Finding` (§7). La capa puntúa cada candidato con la probabilidad de esa corrección en el contexto de su evento (o de su hueco, si es una inserción) y los ordena. Un hallazgo de regla solo lleva sugerencias de sus candidatos: la capa no inventa arreglos para una regla, y una regla sin candidatos no cambia.
2. **Posibles errores propios.** Para cada evento, si la corrección más probable distinta de «ninguna» supera el umbral de su familia (§6), la capa emite un `Finding` con `rule_id` `learned.<operación>`: `learned.accidental`, `learned.duration`, `learned.pitch` y `learned.delete`. Cada familia se activa solo si [#257](https://github.com/sebdavid3/Cadenza/issues/257) la mide útil (la configuración del artefacto dice cuáles); se empieza por `learned.accidental`, donde las reglas fallan más. Su gravedad es `warning`, y su mensaje, en el lenguaje musical de [#245](https://github.com/sebdavid3/Cadenza/issues/245) («Puede que este Si sea Si♭: la armadura lo pide…»), nunca una cifra sin contexto.
3. **Sin duplicados.** La capa no emite un hallazgo propio sobre un evento que ya es el ancla de un hallazgo de regla, ni sobre uno que toca un candidato de esa regla. En los demás eventos del compás sí lo emite, aunque haya un hallazgo de regla en el compás: `measure.balance` señala el compás por su primer evento y no dice qué nota tiene la alteración mal.
4. **Sin capa, como hoy.** Con el interruptor apagado, sin versión promovida o con un artefacto que no se puede usar (§8), los hallazgos son exactamente los de las reglas y no llevan sugerencias (`suggestions: []`), **tampoco los candidatos de las reglas**: la condición asistida del estudio no cambia si la capa no corre. En una sesión `unassisted` no corren ni las reglas ni la capa (D38).

### 4. La sugerencia estructurada, su ciclo de vida y el contrato

Una **sugerencia** es una edición propuesta, no aplicada: `op` (un `EditOp`), `anchor` (relativa al `at_seq` de su hallazgo, ADR-0011), `before` y `after` (los mismos datos que `POST /sessions/{id}/edits`), `confidence` (0–1, o `null` si la capa no tiene datos para ordenar un candidato de regla), `confidence_level` (`high` o `medium`, §6), `explanation` (lenguaje musical, #245), `source` (`rule` si la capa no pudo puntuarla, `learned` si la ordenó o la propuso la capa) y `model_version`. Un hallazgo lleva de cero a tres sugerencias ordenadas por confianza. Antes de guardarse, cada sugerencia pasa `validate_after` y la instantánea de `before` sobre el estado `at_seq` (ADR-0017): la que no pasa se descarta, así que «Aplicar» nunca da 422 por la sugerencia en sí.

**Tipos.** La sugerencia (`SuggestedEdit`) es un tipo de `cadenza.domain`, y `Finding` gana `candidates: tuple[SuggestedEdit, ...] = ()` (las reglas los rellenan; vacío por defecto, así que los documentos y hallazgos guardados se leen igual).

**Contrato.** Ampliación compatible del contrato v1: `FindingRead` gana `suggestions: SuggestionRead[]` (vacía por defecto); `SuggestionRead` lleva además su `id` (entero, como `FindingRead.id`) y su `response` (`null`, `accepted` o `rejected`); `EditEventCreate` gana `suggestion_id: int | null`; `ProvenancePayload` gana `suggestions_version: str | null`; y hay una ruta nueva (§5). `suggested_fix` se conserva como texto. `findings_count` incluye los hallazgos `learned.*`; la cobertura de `exp_06` y [#246](https://github.com/sebdavid3/Cadenza/issues/246) los excluye (mide las reglas). Se regeneran `openapi.json` y `types.ts` en el turno de #256 de la cola del contrato (#231).

**Persistencia y ciclo de vida.** Una tabla `suggestions`, en una migración de Alembic: una fila por sugerencia, con `session_id` y `at_seq` propios, su hallazgo (`finding_id`, que puede quedar nulo), su rango, la edición propuesta, la confianza, la explicación, la versión, la respuesta, quién respondió (lo fija el servidor, ADR-0012), cuándo y el `seq` de la edición si se aplicó.

- Al sustituir los hallazgos de un estado (`replace_findings`), sus sugerencias **sin** respuesta se borran con ellos y las que **tienen** respuesta se conservan desvinculadas (`finding_id` nulo): las respuestas nunca se pierden.
- Una revalidación hereda `rejected` en la sugerencia equivalente (misma `op` y mismo `after`, con el ancla traducida y el evento sin modificar desde el rechazo) **solo desde la validación vigente**, con la misma lógica que los descartes (ADR-0035). Así lo rechazado no reaparece en cada revalidación, y una restauración de la validación vigente sigue mandando.
- `finalize_session` recibe el modelo y hereda los rechazos como `revalidate` (junto con D65, [#187](https://github.com/sebdavid3/Cadenza/issues/187)).
- Revalidar el mismo estado cambia los `id` de las sugerencias, como los de los hallazgos: responder a un `id` viejo da 404.

### 5. Propone, no aplica

- **Aplicar** es una edición de la persona: la web envía `POST /sessions/{id}/edits` con la edición de la sugerencia, su `base_seq` y `suggestion_id`. El servidor fija el autor (ADR-0012) y comprueba, en este orden:
  1. `base_seq` frente al último `seq` (409 de conflicto de secuencia, sin reintento, ADR-0011);
  2. que la sugerencia sea de la sesión, que su hallazgo sea de `base_seq` y que no tenga respuesta; si no, 409 con `detail` `stale_suggestion`, y la web no la vuelve a aplicar: la marca como antigua y ofrece revalidar ([#258](https://github.com/sebdavid3/Cadenza/issues/258));
  3. que la edición coincida con la propuesta (`op`, `anchor` y `after`, comparados tras la normalización de `validate_after`); si no, 422.

  En la misma transacción que persiste la edición, la sugerencia pasa a `accepted` con el `seq` resultante. Rehacer (ADR-0034) reenvía la edición **sin** `suggestion_id`.
- **Rechazar** es `POST /sessions/{id}/suggestions/{suggestion_id}/reject`: 200 con la sugerencia; 409 en una sesión finalizada o si ya está aceptada; 404 si no está; 403 como descartar. Rechazar una sugerencia de una validación anterior responde 200, como descartar. Rechazar no descarta el hallazgo y descartar un hallazgo no rechaza sus sugerencias.
- **La respuesta guardada no cambia después.** Para el análisis de [#257](https://github.com/sebdavid3/Cadenza/issues/257) y [#188](https://github.com/sebdavid3/Cadenza/issues/188) se derivan del log y de los hallazgos: aceptada y deshecha (hay una edición que deshace la aplicada), arreglada a mano (el estado final tiene el `after` de la sugerencia en su ancla traducida, sin `suggestion_id`), descartada (su hallazgo se descartó) e **ignorada** (toda sugerencia mostrada en cualquier validación de la sesión que no tiene respuesta al terminar la última finalización).
- Aplicar solas las de confianza alta queda **fuera**: cada cambio de la partitura es de una persona.

### 6. El umbral de confianza

La configuración del entrenamiento (`configs/learning/suggestions.yaml`) fija `min_support`, `alpha` y dos precisiones objetivo. El **umbral** de cada familia de posibles errores propios se elige en el entrenamiento por **validación cruzada de 5 pliegues agrupados por obra dentro de la partición de entrenamiento**: el menor umbral cuya precisión media entre pliegues es al menos `target_precision` (0,7 por defecto). Una familia sin umbral que la alcance queda apagada. Con el mismo método se elige el umbral de `confidence_level`: `high` si la confianza alcanza el umbral de precisión 0,9 de su familia, `medium` si no. Ambos se guardan en el artefacto. Las sugerencias que la capa ordena dentro de un hallazgo de regla se muestran con su confianza, sin umbral, porque la regla ya dijo que hay un error; solo la primera se destaca. La partición de prueba solo se usa para evaluar.

### 7. Dónde vive: tipos, puerto, implementación y planos

- **Tipos** en `cadenza.domain`: `SuggestedEdit` y `Finding.candidates` (§4).
- **Puerto** en `packages/application` (`ports/suggestion_model.py`): `SuggestionModel`, un `typing.Protocol` con `version` y `suggest(document, findings) -> SuggestionResult` (los hallazgos con sus sugerencias y los posibles errores propios). Los casos de uso de transcribir, revalidar y finalizar lo reciben inyectado, opcional.
- **Inferencia** en `packages/validation` (`cadenza.validation.learned`): los rasgos (§2), la lectura del artefacto JSON y la puntuación. Cumple el puerto por estructura, **sin importar `cadenza.application`** (no hay ciclo) ni `cadenza.learning`.
- **Entrenamiento** en `packages/learning` (`cadenza.learning.suggestions`), fuera de línea (ADR-0003): cuenta las frecuencias del corpus, elige los umbrales, mide y escribe el artefacto. Importa los rasgos de `cadenza.validation.learned`, nunca al revés; `packages/learning` declara `cadenza-validation` como dependencia.
- **La API** carga el artefacto promovido y lo inyecta; no importa código de entrenamiento.

### 8. Versionado, registro y carga

- La capa es **otro tipo de modelo** en el registro: una tabla `suggestion_model_versions` con la versión, el `sha256` del artefacto (en `artifacts`, como el de HOMR), `dataset_hash`, `config_hash`, la semilla, `model_type` (`frequency_backoff`), `feature_version`, las métricas medidas (JSON) y si está promovida; y un puerto `SuggestionModelRegistry` con `register`, `promote`, `active` y `versions`, separado del de HOMR, cuyas métricas (SER y OMR-NED) no tienen sentido para la capa. Una sola versión promovida a la vez.
- La API carga la versión promovida **al arrancar** y comprueba su `sha256` y su `feature_version` frente a la de su código: si no coinciden, valida sin capa y lo registra en el log. Una promoción entra en vigor al reiniciar la API. **Entre el congelado ([#252](https://github.com/sebdavid3/Cadenza/issues/252)) y el final del estudio no se promueve ninguna versión.**

### 9. Entrenamiento reproducible y promoción

- La CLI de `ml` gana `ml suggestions train | evaluate | promote`, con `dataset_hash` (el `sha256` del corpus), `config_hash` y semilla. Las métricas son siempre medidas sobre la partición de **prueba** fija de [#255](https://github.com/sebdavid3/Cadenza/issues/255), nunca de reserva (CLAUDE.md §8): precisión, *recall* y F1 de cada familia de posibles errores propios, cuántos de los errores que las reglas no ven señala, y la exactitud de la primera sugerencia en los hallazgos de regla cuyo arreglo verdadero está entre los candidatos; siempre frente a la línea base de no tener capa.
- **Promoción**: una versión nueva solo se promueve si mejora a la activa en la partición de prueba fija (F1 de las familias activas, sin bajar la exactitud de la primera sugerencia). La primera se promueve si mejora a no tener capa. Promover es explícito, nunca efecto de entrenar.
- La red de `PyTorchTrainer` sale del flujo de aprendizaje: la capa la sustituye. Su retirada del código se hace con [#271](https://github.com/sebdavid3/Cadenza/issues/271).

### 10. El bucle de aprendizaje

- `ml build-dataset` escribe **otro** corpus, con su propio `dataset_hash`, que une el de `exp_12` (sin modificarlo: es la evidencia de #255 y #257) y el de las sesiones **finalizadas** de Cadenza: para cada sesión, los registros de `build_correction_records(estado 0, estado final)`, con `source: cadenza`, verificados con la misma comprobación que PrIMuS, y las respuestas a sus sugerencias como rasgo de evaluación y de análisis.
- Las sesiones se asignan a entrenamiento o prueba con `assign_split` sobre su **página de origen** (`test_score_id` o, sin él, el `sha256` de la imagen), nunca sobre el id de sesión: varios participantes transcriben las mismas páginas ([#247](https://github.com/sebdavid3/Cadenza/issues/247)), y todas las sesiones de una página caen del mismo lado.
- El estado 0 es la salida cruda de HOMR, así que los **rasgos** son siempre los de los errores de HOMR. Las **etiquetas** de las sesiones sí pueden incluir sugerencias aceptadas que fueran erróneas: #257 mide aparte el reentrenamiento con y sin las sesiones de la condición con capa.
- Usar las sesiones del estudio para entrenar debe estar cubierto por el protocolo de [#244](https://github.com/sebdavid3/Cadenza/issues/244). Un reentrenamiento solo se promueve con el criterio del §9.

### 11. Trazabilidad

Cada sugerencia guarda la versión de la capa que la propuso. La sesión guarda en su procedencia la versión activa al transcribir (`Provenance.suggestions_version`, opcional: los documentos guardados antes se leen igual). Con el estado 0 del log, las sugerencias y sus respuestas, cada sugerencia se puede reconstruir y evaluar después.

### 12. Coste e interruptor

- La capa añade **como mucho 300 ms** a la validación de una página completa, medido con la página más grande del banco del estudio ([#247](https://github.com/sebdavid3/Cadenza/issues/247)) o, mientras no esté, con la página real más larga de las pruebas del motor.
- `Settings.suggestions_enabled` (`CADENZA_SUGGESTIONS_ENABLED`), **apagado por defecto** y global. Con el interruptor encendido y sin versión promovida, la API arranca y valida sin capa, y lo registra en el log. Si el estudio la usa, y en qué condición, lo decide el responsable en [#244](https://github.com/sebdavid3/Cadenza/issues/244) con la primera medición de [#257](https://github.com/sebdavid3/Cadenza/issues/257); si hiciera falta la capa por sesión, será otro valor de `condition`, decidido allí.

## Enmiendas de la implementación (#256, A6, 2026-10-30)

Lo que la implementación no pudo hacer tal cual, resuelto con lo más simple compatible:

1. **Configuración en JSON.** `configs/learning/suggestions.json`, no YAML: PyYAML no es una dependencia declarada y las demás configuraciones de `configs/learning/` son JSON. Además de `min_support`, `alpha` y las dos precisiones objetivo (`target_precision`, `high_precision`), fija la semilla de los pliegues, `folds`, `min_alarms` (alarmas mínimas entre pliegues para aceptar un umbral), `learned_families` (las familias que pueden emitir posibles errores propios; empieza con `accidental`) y los niveles de retroceso de cada familia y de las inserciones.
2. **Los rasgos no se trasladan aún desde el corpus.** `cadenza.validation.learned.features` calcula el contexto con la misma definición que `cadenza.learning.correction_corpus`, que es de #255 y no se modifica en esta rama; una prueba compara, registro a registro, el contexto de ambos y los huecos de las inserciones. Cuando #255 entre en `dev`, `build_correction_records` puede llamar a esta función sin cambiar su salida.
3. **Etiquetas relativas.** Para que el retroceso generalice, la alteración se etiqueta frente al contexto (`=key`, la que pide la armadura; `=prev`, la última de la misma nota en el compás; si no, la absoluta), la duración como razón frente a la leída (`x2`, `x1/2`) y la altura como distancia diatónica (al decodificarla, con la alteración de la armadura). Las inserciones se cuentan sobre todos los huecos de cada voz, con `none` donde no falta nada, para que su probabilidad sea comparable con la de los demás candidatos.
4. **Sin duplicados, por familia (§3.3).** «Un evento que toca un candidato de esa regla» se entiende por familia: la capa no emite `learned.<familia>` sobre un evento que ya tiene un candidato de regla de esa familia. Si no, los candidatos de `measure.balance` (cambiar la figura de cada evento del compás) ocultarían todas las alteraciones de los compases incompletos, justo donde §3.3 quiere que se emitan. Sobre el ancla de un hallazgo de regla no se emite nada, como dice §3.3.
5. **Un posible error propio sin arreglo admisible no se muestra.** Si su sugerencia no pasa `validate_after`, se descarta con ella. Si la capa falla al sugerir, la validación sigue con los hallazgos de las reglas, sin sugerencias, y se registra en el log (como §3.4).
6. **`confidence_level` de un candidato sin puntuar** es `medium`: el contrato solo admite `high` y `medium`.
7. **Herencia de rechazos.** Una edición con la misma marca de tiempo que el rechazo cuenta como posterior (el reloj puede dar el mismo microsegundo a las dos), y cada rechazo se hereda una sola vez. La sugerencia que hereda es una fila nueva, rechazada, con quién y cuándo; la original queda desvinculada.
8. **Ids que no se reutilizan.** `suggestions` usa `AUTOINCREMENT` en SQLite, para que responder a un id viejo sea siempre un 404 y nunca otra sugerencia; PostgreSQL no reutiliza ids.
9. **`ml suggestions build-dataset`, no `ml build-dataset`.** El `build-dataset` existente construye el conjunto de `PyTorchTrainer`, que se retira con #271; el del bucle de aprendizaje es un subcomando de `ml suggestions`, con la semilla de la partición de #255 (`--split-seed`) explícita. Las sesiones finalizadas van con `incipit_id` `cadenza:<sesión>` y `work_id` su página de origen, que agrupa también los pliegues; sus sugerencias van en registros `suggestion` con `response` `accepted`, `rejected` o `ignored`.
10. **Qué se compara al promover (§9).** El F1 de los posibles errores propios de las familias activas, con los aciertos sobre las alarmas de esas familias y el *recall* sobre los errores de las cuatro familias (así dos versiones con familias distintas se comparan con el mismo denominador), y la exactitud de la primera sugerencia en los hallazgos de regla cuyo arreglo verdadero está entre los candidatos, frente al primer candidato de la regla. Solo se compara con la activa si se midió con la misma partición de prueba (`evaluation_dataset_hash`); si no, no se promueve. El informe medido se guarda entero en `metrics`.
11. **Evaluación de punta a punta.** Las métricas por familia se miden sobre todos los eventos de la partición de prueba, sin la exclusión por las reglas; las de punta a punta (errores que las reglas no ven, primera sugerencia) reconstruyen el `ScoreIR` leído de cada incipit a partir de sus registros (`reconstruct_score`), con la métrica en cada compás y la clave y la armadura donde cambian, y pasan las reglas actuales y la capa. Un incipit que no se puede reconstruir se cuenta aparte, con su error.
12. **Coste.** El banco del estudio (#247) aún no existe y las pruebas del motor no tienen una página completa real en el repositorio: la prueba mide una página sintética densa (624 eventos) y `scripts/measure_suggestion_cost.py` mide cualquier página real que se le dé, sin escribir nada.
13. **Finalizar en `unassisted`.** La capa no corre. Las reglas siguen corriendo en `finalize_session` como antes de esta decisión: cambiarlo es de #187.
14. **El periodo sin promociones** (del congelado al final del estudio, §8) es una regla de operación: la CLI no la impone.
15. **Tras la revisión independiente.** La capa devuelve todos los candidatos ordenados y los casos de uso se quedan con los tres primeros admisibles; si la capa no devuelve, en su orden, todos los hallazgos de las reglas, se valida sin capa. Una respuesta guardada no cambia nunca: el repositorio solo la escribe si la sugerencia no tenía ninguna, y si dos peticiones compiten, la segunda recibe 409 (al aplicar, `stale_suggestion`, sin guardar la edición). Un rechazo heredado guarda en `inherited_from` el rechazo original, y el corpus del bucle lo lleva para no contarlo dos veces. La capa no propone cambiar la duración ni borrar una nota de un acorde. La promoción exige un informe medido sobre la partición `test`.
16. **Límites conocidos.** La promoción compara el F1 de los posibles errores propios: una versión que solo mejora el orden de los candidatos de las reglas no se promueve frente a no tener capa (#257 lo dirá si hace falta otro criterio). `same_after` normaliza la duración, la alteración y la inserción; las alturas se comparan tal cual, porque `validate_after` solo admite su forma canónica. Una sola versión promovida a la vez la garantiza el código, no un índice único.
17. **Tras la segunda revisión.** Solo se heredan los rechazos de las sugerencias que mostró la validación vigente (vinculadas a su hallazgo): una fila desvinculada es de una validación anterior del mismo estado, y una V3 no hereda el rechazo de una V1 que la V2 (por ejemplo, sin capa) no mostró. La capa propone, de las familias que superan su umbral, la más probable que pasa `validate_after` (nunca una alteración ni una altura en un silencio), y `evaluate` mide por el mismo camino que producción, con el filtro de admisibilidad de los casos de uso. El artefacto guarda los `incipit_id` con que se entrenó y `evaluate` falla si alguno está en la partición de prueba del corpus que mide. Dos rechazos a la vez responden los dos 200 con el rechazo guardado.
18. **Para #258 y #244.** Rechazar no descarta: un hallazgo `learned.*` cuya única sugerencia se rechazó reaparece activo en cada revalidación (con la sugerencia rechazada heredada) y cuenta en `findings_count`. Si la vista lo oculta, o si el rechazo de la única sugerencia debe descartar el hallazgo propio, lo deciden #258 y #244.

## Consecuencias

### Positivas

- La aportación propia de Cadenza queda separada de HOMR, medible y reemplazable: otro modelo es otra implementación del puerto y otro `model_type`.
- Las sugerencias se explican en lenguaje musical con la evidencia que las respalda, y la persona decide siempre: nada cambia la partitura sin una edición suya, y sus respuestas no se pierden al revalidar.
- El contexto que se aprende es el mismo que se ve en línea (una sola función de rasgos, versionada), y la salida cruda de HOMR sigue siendo la referencia de cada reentrenamiento.
- Sin la capa (interruptor apagado, sin modelo o en `unassisted`) el sistema se comporta exactamente como hoy.

### Negativas / riesgos

- **El corrector ideal no es una persona.** El corpus de PrIMuS viene de la alineación de coste mínimo, no de correcciones humanas; las sesiones del estudio son pocas. #257 lo dice y mide la curva de aprendizaje.
- **PrIMuS no son nuestras páginas.** Incipits de una línea, impresos limpios; la capa puede rendir peor en piano o voz con piano ([#239](https://github.com/sebdavid3/Cadenza/issues/239)).
- **Selección sobre la misma prueba.** Promover comparando una y otra vez sobre la misma partición de prueba introduce un sesgo de selección; #257 lo reconoce al reportar.
- **Cambios de contrato y de esquema.** Una migración (`suggestions`, `suggestion_model_versions`), cuatro ampliaciones de la API (`suggestions` en `FindingRead`, `suggestion_id` en la edición, `suggestions_version` en la procedencia y la ruta de rechazo) y un campo nuevo en `Finding`; todo compatible, pero entra en la cola del contrato.
- **Las reglas de [#246](https://github.com/sebdavid3/Cadenza/issues/246) cambiarán los candidatos.** La implementación empieza con las reglas actuales y se rebasa cuando lleguen.

## Alternativas consideradas

| Alternativa | Motivo del descarte |
|---|---|
| Árbol de decisión (scikit-learn) | Dependencia nueva en la API o un intérprete propio; no explica mejor que la tabla. Queda como segunda implementación del puerto si #257 la justifica. |
| Red neuronal o reentrenar HOMR | Fuera del alcance (#103, ADR-0018); no explicable; el corpus es pequeño. |
| Aplicar solas las sugerencias de confianza alta | Cambiaría la partitura sin una edición de la persona (ADR-0012) y contaminaría las métricas de esfuerzo del estudio. |
| Sugerencias como texto en `suggested_fix` | La web no puede aplicarlas con un clic ni registrar la respuesta. |
| Añadir la capa al registro del motor OMR (`model_versions`) | Sus métricas (SER, OMR-NED) son obligatorias y no tienen sentido para la capa; mezclaría la promoción de dos modelos distintos. |
| Inferencia en `packages/learning` | La API importaría el plano fuera de línea (ADR-0003). |
| Puerto como clase abstracta implementada en `packages/validation` | `validation` tendría que importar `application`, que ya depende de él: un ciclo. |
| Umbral elegido sobre la partición de prueba, o pliegues por incipit | Sobreestimarían la precisión que se reporta en #257: los incipits de una obra se parecen. |
| Partición de las sesiones por id de sesión | Varias sesiones de la misma página caerían a los dos lados. |
