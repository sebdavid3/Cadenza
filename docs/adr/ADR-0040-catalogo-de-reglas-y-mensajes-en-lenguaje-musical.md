# ADR-0040: Catálogo de reglas del validador y mensajes en lenguaje musical

- **Estado:** Propuesto. Pasa a Aceptado cuando el responsable revise los ejemplos del §12 (criterio de aceptación de [#245](https://github.com/sebdavid3/Cadenza/issues/245)) y decida lo del §14 (qué parte de las alteraciones se atribuye a la capa de sugerencias). El resto es técnico y compatible con los ADR vigentes.
- **Fecha:** 2026-10-31
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0003, ADR-0011, ADR-0013, ADR-0017, ADR-0021, ADR-0028, ADR-0032, ADR-0033, ADR-0035 y ADR-0036, CLAUDE.md §9 y §10). Los ejemplos de los mensajes y el §14, el responsable.
- **Relacionado:** [ADR-0013](ADR-0013-revalidacion-y-versionado-de-hallazgos.md), [ADR-0017](ADR-0017-validacion-del-contenido-de-las-ediciones.md), [ADR-0021](ADR-0021-visualizacion-de-la-transcripcion-y-marcado-de-hallazgos.md), [ADR-0028](ADR-0028-notas-sin-duracion-como-notas-de-adorno.md), [ADR-0032](ADR-0032-varias-voces-huecos-y-plicas.md), [ADR-0033](ADR-0033-insertar-borrar-clave-y-armadura.md), [ADR-0035](ADR-0035-descartar-restaurar-y-revalidar-desde-la-vista.md), [ADR-0036](ADR-0036-capa-de-sugerencias-aprendida.md), [#245](https://github.com/sebdavid3/Cadenza/issues/245), [#246](https://github.com/sebdavid3/Cadenza/issues/246), [#236](https://github.com/sebdavid3/Cadenza/issues/236), [#237](https://github.com/sebdavid3/Cadenza/issues/237), [#238](https://github.com/sebdavid3/Cadenza/issues/238), [#239](https://github.com/sebdavid3/Cadenza/issues/239), [#244](https://github.com/sebdavid3/Cadenza/issues/244), [#187](https://github.com/sebdavid3/Cadenza/issues/187), [#257](https://github.com/sebdavid3/Cadenza/issues/257), [#258](https://github.com/sebdavid3/Cadenza/issues/258), [#270](https://github.com/sebdavid3/Cadenza/issues/270)

---

## Contexto

Las reglas son la ayuda que mide el estudio en la condición asistida ([#244](https://github.com/sebdavid3/Cadenza/issues/244), protocolo §2.2), así que su catálogo y lo que dicen entran en el congelado del 8 de noviembre ([#252](https://github.com/sebdavid3/Cadenza/issues/252)). Estos hechos se comprobaron en el código y en `results/` el 2026-10-31. Cada cifra se cita desde su archivo de `results/`, y **hay que regenerarla antes de citarla en la tesis** (CLAUDE.md §8).

**Lo que hay.** Cinco reglas en `packages/validation/src/cadenza/validation/rules/`:

| Regla | Qué comprueba hoy | Medido en `exp_06` (91 incipits de PrIMuS, 359 compases; `results/validation_metrics_summary.json`) |
|---|---|---|
| `measure.balance` | Que cada voz de cada compás sume su métrica. Una voz corta no es error si otra que se ve completa el compás (ADR-0032 §4). Da los candidatos de ADR-0036 §3. | 73 aciertos y 35 falsos positivos por compás |
| `key.consistency` | (a) Pentagramas de una misma parte con armaduras distintas. (b) Un bemol con armadura de sostenidos, o un sostenido con armadura de bemoles. (c) Sostenido y bemol sobre la misma letra en un compás. | 6 y 1 |
| `pitch.range` | Una nota fuera del registro de su clave. | 0 y 0 |
| `tie.resolution` | Ligaduras de prolongación abiertas, sin cerrar o en un silencio, por voz y altura. | 0 y 0 |
| `voice.collision` | Acordes mal formados y duraciones no positivas. | 3 y 8 |

- **En conjunto**, la precisión es del 64,52 % y el *recall* del 39,80 % por compás: se marcan 80 de los 201 compases con errores.
- **Lo que se escapa son sobre todo alteraciones.** En los compases que no se marcan, 85 de 138 correcciones por categoría son de alteración (comentario de #245).
- **De los 127 compases con errores de alteración** se marcan 42, y 37 de ellos solo por `measure.balance` (`results/validation_error_coverage.json`).

**Lo que dice el corpus de correcciones** (`exp_12`, [#255](https://github.com/sebdavid3/Cadenza/issues/255); 1 818 incipits verificados):

- **El 62 % de las correcciones son de duración** (3 112 de 4 994, `results/correction_corpus_summary.json`). Las confusiones más frecuentes son de una figura leída como la mitad de la verdadera:
  - corchea leída donde va negra: 1 606;
  - fusa donde va semicorchea: 568;
  - semicorchea donde va corchea: 368.
- **191 de las 201 alteraciones corregidas** están en notas cuya alteración leída va contra la armadura, y casi todas quitan una alteración que sobra (`'#' → ''`: 130; `'b' → ''`: 65). La armadura mal leída no las explica: solo hay 2 incipits con la armadura mal leída.
- **El compás está mal leído en el 37,6 % de los incipits** (705 de 1 877). La confusión más frecuente es 3/4 leído donde va 4/4, en 237 incipits (`results/correction_corpus_incipits.csv`, columnas `time_read` y `time_true`). HOMR deduce el numerador con la mediana de lo que suman los compases ([#237](https://github.com/sebdavid3/Cadenza/issues/237)).
- **Hay 524 notas leídas con duración 0**, que son las notas de adorno de ADR-0028, y ninguna se corrigió.

**Lo que dice la capa de sugerencias** (`exp_14`, [#257](https://github.com/sebdavid3/Cadenza/issues/257), `results/suggestion_layer_summary.json`, 352 incipits de prueba):

- **Los candidatos de las reglas rara vez aciertan.** De 724 hallazgos de regla, 528 traen candidatos y solo 46 contienen el arreglo verdadero; los de `measure.balance` casi nunca lo contienen.
- **`learned.accidental` sí acierta.** Acierta en 33 de 38 y encuentra 33 de los 35 errores de alteración que las reglas no ven.
- **Lo que se muestra en el estudio.** El responsable decidió en #244 que, en la condición asistida, la capa solo muestre sugerencias de alteración de confianza alta. ADR-0036 lo recoge en su enmienda 19 (PR #288, `SuggestionPolicy`): una sugerencia se muestra solo si es de una familia permitida (por defecto, `accidental`) y de nivel alto, y un candidato de regla que la capa no puntúa cuenta como `medium` (enmienda 6).

**Recuento exploratorio** sobre `results/correction_corpus.jsonl`. Se hizo para este ADR, de solo lectura y sin script versionado, así que **no es citable**: #246 mide las reglas con `exp_06` y `exp_14`.

Con los registros `event` de los incipits verificados:

- **El caso de `accidental.repeated` (§7).** Es una nota con sostenido o bemol contra la armadura cuya **última nota anterior en el compás con la misma letra y octava** lleva esa misma alteración (en el corpus, `context.previous_accidental_same_step`).
  - Se corrigió en 181 de 193 casos, y siempre a la alteración de la armadura. Son 181 de las 201 alteraciones corregidas.
  - En la imagen se ve que HOMR no lee el becuadro de la segunda nota: en `000101245-1_1_1` hay un Fa♯ y después un Fa con becuadro, y los dos se leen Fa♯.
  - Una nota contra la armadura sin alteración anterior de su letra y octava en el compás se corrigió en 8 de 691: casi todas son alteraciones escritas.
- **`key.consistency` (b) y (c).** La (b) marca 157 notas. De ellas, 36 entran en el caso anterior (33 corregidas y 3 no) y las otras 121 son correctas: en Sol menor, por ejemplo, el Fa♯ de la sensible es un sostenido con armadura de bemoles. La (c) no aparece.
- **Compases cuyas figuras no llegan a la métrica leída.** Los que tienen alguna corrección, según su posición en el pentagrama:
  - el primero, 75 de 528;
  - el último, 78 de 472;
  - los de en medio, 254 de 270.

Con todos los incipits derivados:

- **El criterio de `time.signature` en todo el tramo** (§5, caso 1, sobre el primer pentagrama y su voz principal) dispararía en 196 incipits: 194 con el compás mal leído (de 699) y 2 con el compás bien leído (de 1 172).
  - En 149 de esos 194, la suma que da es la métrica verdadera.
  - Los demás incipits con el compás mal leído tienen pocos compases para decidir.

**Los mensajes de hoy** no hablan como un músico:

- `measure.balance` escribe la suma con un `Fraction` («suma 2/3 negras … exige 8/12»).
- La voz sale con su índice desde 0 («voz 0»).
- Las claves se nombran como «Sol en 2ª línea».
- Las sugerencias son genéricas («Ajustar las duraciones … para sumar 4 negras»).

La vista muestra el nombre de la regla (`findings.ts`, `RULE_LABELS`) y `message`. `suggested_fix` viaja en `FindingRead`, pero la vista no lo enseña. Los mensajes de la capa (`cadenza.validation.learned.messages`) ya hablan en lenguaje musical («Puede que este Si sea Si♭: la armadura lo pide»).

**Lo que viene:**

- [#236](https://github.com/sebdavid3/Cadenza/issues/236) añade `TimeSignature.symbol` (C y ¢), una operación para cambiar el compás y los tresillos como edición.
- [#237](https://github.com/sebdavid3/Cadenza/issues/237) reconoce el compás por tramos y los tresillos implícitos, fuera de `HOMREngine`.
- [#238](https://github.com/sebdavid3/Cadenza/issues/238) mide los cambios de armadura.
- [#239](https://github.com/sebdavid3/Cadenza/issues/239) trae voz y piano en tres pentagramas.

El `ScoreIR` ya admite:

- duraciones con denominador 3, 5 o 7 (ADR-0017);
- voces que entran a mitad del compás con un silencio invisible (`Event.hidden`, ADR-0032);
- una armadura y una clave por compás (ADR-0033).

**La condición no asistida.** Según el protocolo (§2.2), el validador no se ejecuta. `transcribe_score` y `revalidate` guardan `findings = ()` en una sesión `unassisted` (D38), pero `finalize_session` sigue ejecutando las reglas (ADR-0036, enmienda 13). Además, la vista no mira `condition`: sin hallazgos diría que «el validador no señala ningún compás» (ADR-0035, riesgos).

## Decisión

### 1. Cómo habla el validador

Todo lo que dice el validador sale de un módulo puro nuevo, `cadenza.validation.language`, que solo usa la biblioteca estándar y `cadenza.domain`. Lo usan las reglas y la capa: `learned/messages.py` deja de definir `note_name` y `figure_name` y los importa de ahí.

- **Notas**, por su nombre en solfeo y su alteración, sin octava: «Fa♯», «Si♭», «Mi» (signos ♯, ♭, 𝄪 y 𝄫).
  - El becuadro (♮) solo se escribe cuando contradice la armadura.
  - La octava, en notación científica (Do4 es el Do central), solo se dice donde importa: en `pitch.range`.
- **Figuras**, por su nombre: cuadrada, redonda, blanca, negra, corchea, semicorchea, fusa, semifusa y garrapatea, más «con puntillo» y «con doble puntillo».
  - Una figura de tresillo se nombra por la figura que resulta de multiplicar su duración por 3/2: «corchea de tresillo».
  - En plural, con el número en letra hasta doce: «seis corcheas».
- **Cuánto falta o sobra** (`amount`). Se elige la primera forma que sirva:
  1. una figura: «una corchea», «una negra con puntillo»;
  2. una figura de tresillo: «una corchea de tresillo»;
  3. dos figuras sin puntillo: «una negra y una semicorchea»;
  4. si no hay ninguna, no se dice cuánto: «le falta duración».

  **Una cantidad nunca se dice con una fracción ni contando negras.** Para decir lo que suma un compás entero (§5), se cuentan figuras del denominador: «cuatro negras», «seis corcheas».
- **Dónde** (`position`). Es un sintagma con artículo: «el tiempo 3» o «la segunda corchea del tiempo 3». Las plantillas lo combinan con su preposición y su contracción: «del tiempo 3», «de la segunda corchea del tiempo 3», «antes del tiempo 4».
  - **Desde dónde se cuenta**: desde el principio del compás, en la voz y con los silencios invisibles.
  - **El tiempo** es la figura del denominador. En un compás compuesto (numerador múltiplo de 3 mayor que 3: 6/8, 9/8, 12/8 o 6/4) son tres figuras del denominador. En un compás sin métrica (`time_signature` vacío), es la negra.
  - **En un tiempo justo** se dice «el tiempo 3».
  - **Dentro de un tiempo** se usa la subdivisión más gruesa que cae justo, con su ordinal: «la segunda corchea del tiempo 3». Valen las mitades, cuartos y octavos del tiempo; en un compás compuesto, los tercios y sextos; y en uno simple, los tercios y sextos «de tresillo».
  - **Si no cabe**, o si el ordinal pasa de «octava», se dice solo el tiempo.
- **Compases**, por su número (`Measure.number`), que es el que muestra la vista. Un compás 0 de MusicXML es «la anacrusa».
  - Dos compases: «los compases 2 y 3».
  - Tres o más seguidos: «los compases 2 a 7».
  - Si no son seguidos: «cinco de los seis compases del 2 al 7».
- **Voces**: solo se nombran si el pentagrama tiene en ese compás más de una voz con algo que se vea. Nunca se usa el índice interno, y el pentagrama no se repite porque la lista ya lo dice (ADR-0021 §2).
  - Con dos voces, «la voz de arriba» y «la voz de abajo», por altura media, como las plicas (ADR-0032 §2).
  - Con más, «la voz 1», «la voz 2»…, de arriba abajo.
  - Una voz que solo tiene silencios no tiene altura media y va al final.
- **Métrica**, como se escribe: «3/4», y «C» o «¢» cuando #236 guarde el símbolo.
- **Armadura**: «dos sostenidos», «un bemol», «sin alteraciones».
- **Clave**: «clave de sol», «clave de fa», «clave de do en {primera … quinta}», «clave de {sol | fa} en {línea}» si no está en su línea habitual, y «… octavada alta» u «… octavada baja».
- **Tono honesto** (ADR-0021 §4):
  - El mensaje dice lo que se observa, que es cierto: «las figuras no llenan el compás».
  - Lo que quizá sea se dice en «Qué revisar», con «puede que» o «mira si».
  - No se usan identificadores de regla, números MIDI ni la palabra «error».

### 2. Qué ve la persona

Cada hallazgo de regla tiene:

- **Título**: el nombre de su regla en la vista (`RULE_LABELS`, tabla del §3).
- **Mensaje** (`Finding.message`): una frase que empieza por el sitio («En el compás 3…», «El Fa♯ del tiempo 2…») y dice qué se observa.
- **Qué revisar** (`Finding.suggested_fix`): una frase en imperativo que dice qué mirar en la partitura impresa y qué puede ser.
  - La vista la muestra bajo el mensaje, precedida de «Qué revisar:».
  - El campo ya está en `FindingRead`, así que **el contrato no cambia**.
  - Es texto y no se aplica. Las ediciones propuestas son las sugerencias estructuradas de ADR-0036, que la vista muestra aparte (#258).
- **Severidad**: `error` cuando lo escrito es imposible tal cual (el compás no cuadra, el tresillo está incompleto, el acorde está mal formado); `warning` cuando es posible pero sospechoso. La vista no la presenta como certeza (ADR-0021 §4).
- **Ancla**: el evento que nombra el mensaje. Si el problema es del compás o del tramo, el primer evento **que se ve** de su voz o de su compás: un silencio invisible no se puede elegir (ADR-0032). La marca de la vista sigue siendo el compás (ADR-0021).
- **Candidatos** (`Finding.candidates`, ADR-0036 §3): solo los arreglos que la regla sabe que cuadran. Se muestran según la capa y su política: sin capa no se muestra ninguno (ADR-0036 §3.4), y con la política del estudio solo las alteraciones de nivel alto (enmienda 19).

### 3. El catálogo

| Regla | Título en la vista | Severidad | Ancla | Candidatos | Estado |
|---|---|---|---|---|---|
| `measure.balance` | Duración del compás | `error` | primer evento que se ve de la voz | cambiar una figura, añadir un silencio al final o borrar un evento (ADR-0036) | ajustada (§4) |
| `time.signature` | Indicación de compás | `warning` | primer evento que se ve del compás donde empieza el tramo o la racha | cambiar el compás, cuando exista la operación de #236 | **nueva** (§5) |
| `tuplet.incomplete` | Tresillo incompleto | `error` | primer evento del grupo | ninguno | **nueva** (§6) |
| `accidental.repeated` | Alteración repetida | `warning` | la nota | la alteración de la armadura | **nueva** (§7) |
| `key.consistency` | Armaduras distintas | `warning` | primer evento que se ve del compás, en el pentagrama que discrepa | la armadura del pentagrama de arriba | reducida (§8) |
| `pitch.range` | Altura fuera de registro | `warning` | la nota | la misma nota en la octava más cercana dentro del registro | ajustada (§9) |
| `tie.resolution` | Ligadura sin cerrar | `warning` | la nota o el silencio | ninguno: no hay operación para las ligaduras | ajustada (§10) |
| `voice.collision` | Acorde mal formado | `error` | el evento | ninguno | ajustada (§11) |

Los posibles errores de la capa también tienen título en `RULE_LABELS`, porque hoy la vista mostraría su identificador:

| Identificador | Título |
|---|---|
| `learned.accidental` | Alteración dudosa |
| `learned.duration` | Figura dudosa |
| `learned.pitch` | Altura dudosa |
| `learned.delete` | Nota de más |

**Identificadores y versión.**

- **Se mantienen los identificadores de las reglas que ya existen.** Los guardan los hallazgos de las sesiones, `exp_06` cuenta por ellos y la capa los distingue de los suyos.
- **`rules_version` sigue siendo la lista de identificadores ordenada**, porque `exp_06` la separa por comas para saber qué reglas medir. Solo cambia porque entran reglas nuevas.
- **Versión del catálogo.** Como cambiar lo que hace una regla no cambia su identificador, `cadenza.validation` gana una constante, `RULES_CATALOG_VERSION = 2`, para este catálogo. `exp_06` y `exp_14` la guardan junto a `rules_version` en sus resúmenes.
- **`Provenance` no cambia**: las sesiones del estudio son todas posteriores al congelado y, por tanto, de esta versión.

### 4. `measure.balance`: duración del compás

**Detecta** una voz de un compás cuyas figuras no llenan su **capacidad**. La capacidad es la métrica del compás o, en los compases de un hallazgo de `time.signature`, la suma que da ese hallazgo (§5). El **pentagrama** es el `Staff` del `ScoreIR` en toda la página, no una línea del sistema.

**Dispara** en dos casos. Si ninguna voz llena el compás, cada voz corta se señala aparte (ADR-0032 §4).

- Cuando una voz se pasa de la capacidad.
- Cuando se queda corta y ninguna otra voz que se ve la llena.

**No dispara** en estos casos, que son falsos positivos conocidos:

1. **Anacrusa:** el primer compás de un pentagrama con más de un compás, si se queda corto (en el recuento, 75 de 528 tenían alguna corrección). Si se pasa, sí dispara.
2. **Último compás que completa la anacrusa:** el último compás de un pentagrama, si se queda corto, el primero también, y entre los dos suman la capacidad.
   - Un último compás corto sin anacrusa **sí** se señala: en una página del estudio el último compás suele estar completo.
   - En los incipits de PrIMuS, que se cortan donde sea, esto da falsos positivos (en el recuento, solo 78 de 472 últimos compases cortos tenían alguna corrección). Lo mide #246.
3. **Silencio de compás:** una voz hecha de un solo silencio que se ve, de redonda o de la duración del compás, en cualquier métrica.
4. **Voces que salen antes** (ADR-0032 §4): una voz corta no se señala si otra que se ve completa el compás.
   - **Una voz hecha solo de silencios invisibles no se señala nunca**, porque no se ve. Antes se señalaba si ninguna voz completaba el compás.
5. **Tresillo incompleto:** si lo que falta o sobra en la voz es exactamente lo que explican sus grupos de `tuplet.incomplete` (§6), solo se señala el tresillo.
6. **Compás sin métrica** (`time_signature` vacío): no hay capacidad, como hoy.

**Qué suma** (como hoy, salvo lo nuevo de las notas de duración nula):

- Las notas de adorno (duración 0 o nula, ADR-0028) suman 0.
- De un acorde solo suma la primera nota.
- Un silencio de duración 0 o nula suma una negra, que es como se exporta (ADR-0028 §2). Ya no deja la voz sin comprobar.

**Mensaje**, según el caso. Con varias voces, «En el compás {n}, a {la voz} le falta…» y «En el compás {n}, a {la voz} le sobra…».

- **Le falta**: «Al compás {n} le falta {cuánto} para completar el {métrica}: las figuras se acaban antes {de dónde acaban}.»
- **Le sobra**: se mira el primer evento que acaba después de la capacidad.
  - Si empieza dentro del compás: «En el compás {n} sobra {cuánto} para el {métrica}: el {nota o «silencio»} {del dónde}, {una figura}, se sale del compás.»
  - Si empieza en la barra o después: «En el compás {n} sobra {cuánto} para el {métrica}: el compás ya está lleno cuando llega el {nota o «silencio»}.»
- **Tresillos sin marcar**, el caso que #237 corrige en la lectura. Solo en un compás simple (en 6/8 las corcheas van de tres en tres por definición), cuando la voz tiene justo la mitad de la capacidad de más y todas sus figuras van en grupos seguidos de tres iguales: «En el compás {n} sobra {cuánto} para el {métrica}: sus {número} {figuras} van en grupos de tres, como los tresillos.»
- **En los compases de un hallazgo de `time.signature`** la métrica se nombra como lo que suman: «… para completar las cuatro negras que suman los demás compases».

**Qué revisar.** En todos los casos dice «del compás» con una sola voz y «de {la voz}» con varias.

- Le falta: «Revisa las figuras del compás: puede que alguna sea más larga de lo que se leyó, o que falte una nota o un silencio de {cuánto}.»
- Le sobra: «Revisa las figuras del compás: puede que alguna sea más corta de lo que se leyó, o que sobre una nota de {cuánto}.» La segunda parte solo aparece si algún evento dura eso.
- Tresillos sin marcar: «Si en la partitura son tresillos, márcalos como tresillos; si no, revisa las figuras.»

**Candidatos**: los de ADR-0036 §3, calculados contra la capacidad. No hay ninguno en los casos que no disparan.

### 5. `time.signature`: indicación de compás (nueva)

**Detecta** una métrica leída que no casa con lo que suman los compases. Es el error más visible de HOMR (#237), y hoy produce un `measure.balance` por compás, casi todos falsos.

**Cómo se mide.**

- **Tramos**: los compases seguidos de un pentagrama con la misma métrica leída. Un tramo termina donde cambia la métrica (#236 y #237).
- **Suma de un compás**: la de su voz más larga que se ve.
- **Medibles** de un tramo: sus compases, menos el primero y el último del pentagrama (la anacrusa y el final).

**Dispara** en dos casos:

1. **En todo el tramo.** El tramo tiene al menos dos medibles, y una misma suma S distinta de la métrica aparece en al menos dos de ellos y en más de la mitad. El hallazgo se ancla al primer compás del tramo, y S es la capacidad de **todo el tramo**.
2. **Desde un compás**, si no se da el caso 1. Tres o más medibles seguidos suman la misma S, distinta de la métrica. Esos compases forman una **racha**.
   - El hallazgo se ancla al primer compás de la racha: «puede que el compás cambie ahí».
   - S es la capacidad **solo de esa racha**. Fuera de ella, la capacidad vuelve a ser la métrica leída.
   - Varias rachas del mismo tramo dan un hallazgo cada una, cada una con su S.

**Condiciones comunes:**

- **S tiene que poder escribirse como métrica.** Se prueba con el denominador leído y, si no sale entero, con el doble; si tampoco, no dispara. Una métrica de 4/8 se dice 2/4.
- **No dispara si son tresillos sin marcar.** Pasa cuando, en un compás simple, S es la métrica más su mitad y los compases que suman S van en grupos de tres figuras iguales. Esos compases los señala `measure.balance` con su mensaje de tresillos sin marcar (§4), contra la métrica leída.
- **La capacidad vale para toda la parte.** Se aplica a todos los pentagramas de la parte, con los mismos números de compás, porque la métrica es la misma para todos. Se calcula sobre el pentagrama de arriba y el hallazgo se emite una vez, en él.

**No dispara** en estos casos:

- Tramos con menos de dos medibles, como un incipit de tres compases.
- Sumas dispersas: son errores de figuras, y ya los señala `measure.balance`.
- Compases sin métrica.
- Cuando la métrica leída y las sumas están mal a la vez y cuadran entre sí, por ejemplo 3/2 con doce corcheas donde va ¢ con tresillos. Eso solo lo ve la etapa de #237, con la imagen.

**Severidad**: `warning`.

**Candidatos**: cambiar el compás a S desde el compás del ancla, con la operación de #236 si es una sola `EditOp`; sin ella, ninguno. Con la política del estudio (enmienda 19 de ADR-0036: familias `accidental`) no se mostraría. Si se quiere mostrar, lo decide #244.

**Mensaje**:

- En todo el tramo: «{Los compases 2 y 3 | Los compases 2 a 7 | Cinco de los seis compases del 2 al 7} suman {S en figuras del denominador: «cuatro negras», «seis corcheas»} y la indicación de compás es {métrica}.»
- Desde un compás: «Desde el compás {n}, los compases suman {S} y la indicación sigue siendo {métrica}.»

**Qué revisar**:

- En todo el tramo: «Revisa la indicación de compás del compás {n}: puede que sea {S como métrica} ({C o ¢ si es 4/4 o 2/2}). Mientras no cambie, la duración de cada compás se comprueba con {S}.»
- Desde un compás: «Revisa si en el compás {n} cambia el compás: puede que sea {S como métrica}.»

### 6. `tuplet.incomplete`: tresillo incompleto (nueva)

**Detecta** un tresillo al que le falta o le sobra una parte. En el `ScoreIR` un tresillo es una duración con 3 en el denominador (ADR-0017), sin un grupo explícito.

**Cómo se mide.**

- **Grupo**: en cada voz, una serie de eventos seguidos cuya duración tiene el factor 3 en el denominador. De un acorde solo cuenta la primera nota, y las notas de adorno no cuentan.
- **Unidad**: la menor duración del grupo.
- **Completo**: el grupo está completo si su suma es una figura sin tresillo, es decir, si su denominador es una potencia de dos.

Los grupos de cinco o siete (cinquillos y septillos) quedan **fuera** de esta regla: los señala `measure.balance` si no cuadran, como hoy.

**Dispara** con un grupo incompleto.

**No dispara**:

- con grupos completos, aunque mezclen figuras (negra y corchea de tresillo);
- con dos tresillos completos seguidos, que suman una figura.

**Severidad**: `error`. **Ancla**: el primer evento del grupo. **Candidatos**: ninguno, porque no se sabe la altura de la nota que falta (los tresillos como edición son de #236).

**Mensaje**. Se cuenta cuántas unidades le faltan a la suma para llegar al siguiente múltiplo de tres:

- Si le falta una: «En el compás {n}, al tresillo de {figuras} {del dónde} le falta una {figura}.»
- Si le faltan dos: «En el compás {n}, al tresillo de {figuras} {del dónde} le faltan dos {figuras}.»

**Qué revisar**:

- Si le falta una: «Revisa el tresillo: puede que falte una nota o que una de sus {figuras} sea más larga.»
- Si le faltan dos: «Revisa el tresillo: puede que falten dos notas o que sobre una.»

### 7. `accidental.repeated`: alteración repetida (nueva)

**Detecta** el error de alteración más frecuente de HOMR. Cuando una nota repite en el mismo compás la letra y la octava de otra con alteración, HOMR no ve su becuadro y le pone la alteración de la anterior. En el recuento del contexto son 181 de las 201 alteraciones corregidas. Es la regla que ataca los errores de alteración que se escapan (#245).

**Dispara** en una nota que se ve, con sostenido o bemol (también doble) **contra la armadura vigente** del compás (la de #238 si cambia), cuando **la última nota anterior de la misma voz y compás con su misma letra y octava lleva esa misma alteración**.

- Cuentan como anteriores las notas de adorno y las de un acorde, en el orden de la voz, como en el contexto del corpus (`learned/features.py`, `previous_accidental_same_step`).
- En Fa♯ · Fa♮ · Fa♯, el tercero **no** dispara, porque la última nota anterior lleva becuadro.
- Se señala cada repetición, no la primera nota, cuya alteración está escrita.

**No dispara**:

- en la primera nota con la alteración;
- en una nota con la alteración de la armadura;
- en un becuadro contra la armadura: en el recuento, ninguno de los 4 casos era un error;
- en la misma letra en otra octava;
- en una nota de otra voz, como en el contexto del corpus (ADR-0036 §2);
- entre compases: la barra anula la alteración, y en el recuento las notas así no tienen ninguna corrección.

**Falso positivo conocido**: la alteración repetida que sí está escrita así (en el recuento, 12 de 193). En una página real con cromatismos (TS-02) habrá más. Por eso la severidad es `warning` y el mensaje pregunta.

**Ancla**: la nota.

**Candidato**: cambiar la alteración por la de la armadura (`SetAccidental`: «Cambiar Fa♯ por Fa»). Es el arreglo verdadero en los 181 casos del recuento.

**Cómo llega a la persona.**

- **El hallazgo y su «Qué revisar» se ven siempre** en la condición asistida.
- **El candidato se ve solo si lo muestra la capa.** Con la capa encendida, la capa lo puntúa y, si su nivel es alto, se muestra como una sugerencia de alteración (política de #244). Sin capa, o con un nivel `medium`, no se muestra (ADR-0036 §3.4, enmiendas 6 y 19).
- **La capa deja de emitir `learned.accidental` sobre estas notas**, porque no duplica la familia de un candidato de regla (enmienda 4). Lo que hoy es un posible error propio de la capa pasa a ser un posible error de regla que ordena la capa (§14).

**Mensaje**: «El {Fa♯} {del dónde} repite el {sostenido} del {Fa} {del dónde de la anterior}, y la armadura no lo lleva.»

**Qué revisar**: «Mira si en la partitura este {Fa} lleva {becuadro | bemol | sostenido}: entonces es {Fa}, no {Fa♯}.» La alteración que se nombra es la que la armadura pone a esa letra.

### 8. `key.consistency`: armaduras distintas (reducida)

**Se queda** solo con la comprobación (a): pentagramas de una misma parte (un piano) con armaduras distintas en un compás.

- **Dispara** desde el compás en que empiezan a discrepar, una vez por tramo de discrepancia y no en cada compás.
- **No dispara** entre partes distintas: un instrumento transpositor lleva otra armadura (voz y piano, #239).
- **Ancla**: el primer evento que se ve del compás, en el pentagrama que discrepa.
- **Candidato**: cambiar su armadura por la del pentagrama de arriba (`SetKey`, ADR-0033).

**Se retiran** las comprobaciones (b) y (c):

- (b) señala alteraciones escritas y correctas, como la sensible de las tonalidades menores. En el recuento, 121 de sus 157 notas son correctas, y las otras 36 las cubre `accidental.repeated`.
- (c) no aparece en el corpus.

**Mensaje**: «En el compás {n}, la armadura del pentagrama de abajo ({un sostenido}) no coincide con la de arriba ({dos sostenidos}).»

**Qué revisar**: «Revisa las dos armaduras: en los pentagramas de un mismo piano suelen ser iguales.»

### 9. `pitch.range`: altura fuera de registro (ajustada)

**Detecta** una nota fuera del registro de su clave vigente, con las tablas actuales. Una clave sin tabla usa el registro del piano, de La0 a Do8. En PrIMuS no dispara: queda para las octavas y las claves mal leídas de las páginas reales.

**Ajuste**: deja de disparar en las notas de adorno. En los silencios no disparaba ya.

**Candidato**: la misma nota, desplazada por octavas hasta la más cercana dentro del registro (`SetPitch`).

**Mensaje**: «El {Do8} {del dónde} está muy por {encima | debajo} de lo que se escribe en {clave de sol} (de {Sol2} a {Do7}).»

**Qué revisar**: «Revisa la octava de la nota o la clave del pentagrama: puede que sea {Do7}.»

### 10. `tie.resolution`: ligadura sin cerrar (ajustada)

**Detecta** una ligadura de prolongación que no une dos notas iguales seguidas. Las notas de adorno no cuentan.

**Con qué se empareja una ligadura.** La nota ligada busca la **nota siguiente**:

- **Dentro del compás**: el evento de la misma voz que empieza donde acaba la nota ligada, ya sea una nota, un acorde o un silencio. Con un acorde, la ligadura empareja con la nota del acorde que tiene su misma altura.
- **Al cruzar la barra**: los eventos que empiezan con el compás siguiente (en el tiempo 1), en el mismo pentagrama y en cualquier voz, prefiriendo la misma. Las voces se numeran desde 0 en cada compás (ADR-0032 §3), así que la ligadura puede llegar a otra voz con otro número. Una nota más adelante en el compás no cuenta.
- **Si alguna de esas notas tiene su misma altura**, la ligadura está resuelta, aunque esa nota no lleve la marca de final.

**Cuándo hay un posible error.** Se señala **uno solo** por ligadura, en la nota donde empieza. Si la nota siguiente lleva la marca de final de ligadura, esa marca no se señala aparte.

- **No llega**: la nota siguiente es de otra altura o es un silencio.
- **Final sin principio**: una nota con la marca de final sin una nota ligada antes, según las reglas anteriores.
- **Ligadura en un silencio**.

**No dispara** en los bordes de la página:

- una ligadura que termina en el primer compás del pentagrama sin empezar en él, porque viene de la página anterior;
- una ligadura que empieza en el último compás y no termina, porque sigue en la siguiente.

**Mensajes** (`warning`, sin candidatos). Cuando la otra nota está en otro compás, el mensaje lo dice («…, en el compás 4»).

- **No llega**: «La ligadura del {Sol} {del dónde} no llega a otro {Sol}: lo siguiente es {un La | un silencio}.»
  - Qué revisar: «Si en la partitura une notas distintas, es una ligadura de expresión y este aviso se puede descartar; si no, revisa la altura del {La}.»
- **Final sin principio**: «El {Re} {del dónde} termina una ligadura que no empieza en ninguna nota anterior.»
  - Qué revisar: «Revisa si la nota anterior es también un {Re} ligado; si no, la ligadura sobra.»
- **Ligadura en un silencio**: «El silencio de {figura} {del dónde} tiene una ligadura, y los silencios no se ligan.»
  - Qué revisar: «Revisa si en la partitura ese silencio es una nota.»

Las ligaduras no se pueden editar (no hay `EditOp` para ellas), así que «Qué revisar» dice qué mirar, no cómo arreglarlo.

### 11. `voice.collision`: acorde mal formado (ajustada)

**Detecta** acordes que no se pueden escribir, y un silencio sin duración:

- notas del acorde con figuras distintas;
- un silencio dentro de un acorde;
- una nota de acorde sin una nota antes con la que sonar;
- la misma altura dos veces en un acorde;
- un silencio sin duración.

**Se retira** la «duración no positiva» de una **nota** de duración 0 o nula: es una nota de adorno (ADR-0028) y no un error. En el corpus hay 524 y ninguna se corrigió. Un silencio de duración 0 sigue siendo un posible error.

**Mensajes** (`error`, sin candidatos):

- **Figuras distintas**, en cada nota del acorde cuya figura no es la de la primera: «En el acorde {del dónde}, el {Mi} es una {corchea} y el {Do} es una {negra}.» El {Do} es la primera nota del acorde.
  - Qué revisar: «Si en la partitura suenan juntas, iguala la figura; si el {Mi} va aparte, es de otra voz.»
- **Silencio en un acorde**: «El silencio {del dónde} está dentro de un acorde.»
  - Qué revisar: «Revisa si es una nota del acorde o un silencio de otra voz.»
- **Nota de acorde sin base**: «El {Sol} {del dónde} está marcado como nota de un acorde, pero no tiene antes otra nota con la que sonar.»
  - Qué revisar: «Revisa si es una nota suelta.»
- **Altura repetida**: «El acorde {del dónde} tiene dos veces el mismo {Sol}.»
  - Qué revisar: «Borra uno de los dos.»
- **Silencio sin duración**: «El silencio {del dónde} no dura nada.»
  - Qué revisar: «Revisa su figura en la partitura.»

### 12. Ejemplos

Cada fila da lo leído en un compás de partida, con el mensaje y el «Qué revisar» que debe dar. Salvo que se diga otra cosa, el compás no es el primero ni el último de su pentagrama y tiene una sola voz. Son los casos que #246 convierte en pruebas por regla. **Están pendientes de la revisión del responsable** (criterio de #245).

| Regla | Compás de partida (lo leído) | Mensaje | Qué revisar |
|---|---|---|---|
| `measure.balance`, le falta | 4/4, compás 3: Do4 negra · Re4 negra · Mi4 corchea · Fa4 negra | Al compás 3 le falta una corchea para completar el 4/4: las figuras se acaban antes de la segunda corchea del tiempo 4. | Revisa las figuras del compás: puede que alguna sea más larga de lo que se leyó, o que falte una nota o un silencio de corchea. |
| `measure.balance`, le sobra (una nota cruza la barra) | 4/4, compás 2: Mi4 blanca · Re4 negra · Do4 blanca | En el compás 2 sobra una negra para el 4/4: el Do del tiempo 4, una blanca, se sale del compás. | Revisa las figuras del compás: puede que alguna sea más corta de lo que se leyó, o que sobre una nota de negra. |
| `measure.balance`, le sobra (el compás ya está lleno) | 3/4, compás 5: Sol4 blanca · La4 negra · Si4 negra | En el compás 5 sobra una negra para el 3/4: el compás ya está lleno cuando llega el Si. | Revisa las figuras del compás: puede que alguna sea más corta de lo que se leyó, o que sobre una nota de negra. |
| `measure.balance`, dos voces cortas | 4/4, compás 7: arriba, Mi5 blanca · Re5 negra; abajo, Do4 blanca · Si3 corchea | (1) En el compás 7, a la voz de arriba le falta una negra para completar el 4/4: sus figuras se acaban antes del tiempo 4. (2) En el compás 7, a la voz de abajo le falta una negra con puntillo para completar el 4/4: sus figuras se acaban antes de la segunda corchea del tiempo 3. | (1) Revisa las figuras de la voz de arriba: puede que alguna sea más larga de lo que se leyó, o que falte una nota o un silencio de negra. (2) Igual, con «la voz de abajo» y «negra con puntillo». |
| `measure.balance`, tresillos sin marcar | 2/4, compás 2 (y los compases de alrededor de dos negras): Do5 · Re5 · Mi5 · Fa5 · Sol5 · La5, corcheas | En el compás 2 sobra una negra para el 2/4: sus seis corcheas van en grupos de tres, como los tresillos. | Si en la partitura son tresillos, márcalos como tresillos; si no, revisa las figuras. |
| `measure.balance`, no dispara (anacrusa) | 3/4, compás 1 de 4: Re4 negra | (ningún `measure.balance`) | — |
| `measure.balance`, no dispara (el último compás completa la anacrusa) | 3/4, compás 1 de 4: Re4 negra; compás 4: Do5 blanca | (ningún `measure.balance` en los compases 1 y 4) | — |
| `measure.balance`, no dispara (silencio de compás) | 3/4: un silencio de redonda solo | (ningún `measure.balance`) | — |
| `time.signature`, en todo el tramo | 3/4 leído. Compás 1: Re4 negra. Compases 2 y 3: cuatro negras cada uno. Compás 4: Do5 blanca con puntillo (con la anacrusa, suma las cuatro negras) | Los compases 2 y 3 suman cuatro negras y la indicación de compás es 3/4. (Y ningún `measure.balance` en los compases 1 a 4.) | Revisa la indicación de compás del compás 1: puede que sea 4/4 (C). Mientras no cambie, la duración de cada compás se comprueba con cuatro negras. |
| `time.signature`, desde un compás | 3/4 leído. Compás 1: Re4 negra. Compases 2 a 8: tres negras cada uno. Compases 9 a 11: dos negras cada uno. Compás 12: Sol4 blanca con puntillo | Desde el compás 9, los compases suman dos negras y la indicación sigue siendo 3/4. (Y ningún `measure.balance` en los compases 1 a 12.) | Revisa si en el compás 9 cambia el compás: puede que sea 2/4. |
| `tuplet.incomplete` | 2/4, compás 6: Do5 corchea de tresillo · Re5 corchea de tresillo · Mi5 negra | En el compás 6, al tresillo de corcheas del tiempo 1 le falta una corchea. (Y ningún `measure.balance`.) | Revisa el tresillo: puede que falte una nota o que una de sus corcheas sea más larga. |
| `accidental.repeated`, becuadro | Do mayor, 4/4, compás 1: Fa♯4 negra · Fa♯4 negra · Sol4 blanca. Se señala el segundo Fa♯ | El Fa♯ del tiempo 2 repite el sostenido del Fa del tiempo 1, y la armadura no lo lleva. | Mira si en la partitura este Fa lleva becuadro: entonces es Fa, no Fa♯. |
| `accidental.repeated`, bemol | Fa mayor, 2/4, compás 4: Mi♭4 corchea · Re4 corchea · Mi♭4 negra. Se señala el segundo Mi♭ | El Mi♭ del tiempo 2 repite el bemol del Mi del tiempo 1, y la armadura no lo lleva. | Mira si en la partitura este Mi lleva becuadro: entonces es Mi, no Mi♭. |
| `accidental.repeated`, no dispara (sensible escrita) | Sol menor (dos bemoles), compás 3: Fa♯4 negra · Sol4 negra | (ningún `accidental.repeated`, que solo señala repeticiones, ni `key.consistency`, que hoy sí lo señala) | — |
| `accidental.repeated`, no dispara (becuadro intermedio) | Do mayor, 4/4: Fa♯4 negra · Fa4 negra · Fa♯4 blanca | (ningún `accidental.repeated`: la última nota anterior del tercer Fa lleva becuadro) | — |
| `key.consistency` | Piano, compás 9: arriba, dos sostenidos; abajo, un sostenido | En el compás 9, la armadura del pentagrama de abajo (un sostenido) no coincide con la de arriba (dos sostenidos). | Revisa las dos armaduras: en los pentagramas de un mismo piano suelen ser iguales. |
| `pitch.range` | Clave de sol, compás 4: La5 negra · Do8 negra | El Do8 del tiempo 2 está muy por encima de lo que se escribe en clave de sol (de Sol2 a Do7). | Revisa la octava de la nota o la clave del pentagrama: puede que sea Do7. |
| `tie.resolution`, otra altura | 4/4. Compás 3: … Sol4 negra ligada en el tiempo 4. Compás 4: La4 blanca en el tiempo 1 | La ligadura del Sol del tiempo 4 no llega a otro Sol: lo siguiente es un La, en el compás 4. | Si en la partitura une notas distintas, es una ligadura de expresión y este aviso se puede descartar; si no, revisa la altura del La. |
| `tie.resolution`, silencio | 3/4, compás 2: Do5 negra · silencio de negra ligado · Re5 negra | El silencio de negra del tiempo 2 tiene una ligadura, y los silencios no se ligan. | Revisa si en la partitura ese silencio es una nota. |
| `voice.collision` | 4/4, compás 2: acorde en el tiempo 1 con Do4 negra (primera nota), Mi4 corchea y Sol4 negra | En el acorde del tiempo 1, el Mi es una corchea y el Do es una negra. | Si en la partitura suenan juntas, iguala la figura; si el Mi va aparte, es de otra voz. |
| `voice.collision`, no dispara (nota de adorno) | 4/4: Sol♯4 de duración 0 antes de La4 negra | (ningún `voice.collision`; hoy da «Duración no positiva») | — |

### 13. La condición no asistida

En una sesión `unassisted` el validador **no se ejecuta** (protocolo §2.2), y quien corrige no ve nada que venga de él.

1. **No corren ni las reglas ni la capa, en ningún momento.**
   - Al transcribir y al revalidar ya es así (D38).
   - **`finalize_session` también tiene que guardar `findings = ()`** en `unassisted`. Hoy ejecuta las reglas (ADR-0036, enmienda 13), y la lista final que lee el estudio contaría como posibles errores unos que nadie vio.
   - Lo hace [#187](https://github.com/sebdavid3/Cadenza/issues/187), que es el issue de finalizar, junto con D65. Ese criterio no está aún en #187, así que **hay que añadírselo**.
   - Si el análisis necesita los hallazgos del estado final de una sesión no asistida, los calcula el plano fuera de línea sobre el estado materializado del log (ADR-0003), sin guardarlos en la sesión.
2. **La vista no habla del validador.**
   - Con `condition == "unassisted"` (que ya está en `SessionDetailRead` y `SessionViewRead`) no se muestra el panel de posibles errores, ni las marcas, ni «Revalidar», ni las sugerencias.
   - Tampoco se muestra ningún aviso sobre la validación: ni «el validador no señala ningún compás» ni «puede que no esté al día». Darían a entender que la partitura se revisó.
   - Quedan la partitura, la imagen y el editor.
   - Lo hace #246. Es un criterio que **hay que añadirle**.
3. **Las reglas nuevas no cambian la condición no asistida**, porque no hay mensajes que mostrar. Sí cambian la asistida, así que la versión de las reglas que se congela el 8 de noviembre vale para todo el estudio.

### 14. La capa de sugerencias y las alteraciones (decide el responsable)

**Lo que no cambia de la capa** (ADR-0036):

- Ordena los candidatos de las reglas y añade los `learned.*` donde las reglas no llegan.
- Sus mensajes usan el vocabulario del §1.
- `exp_06` y la cobertura por categoría siguen excluyendo los hallazgos `learned.*` (ADR-0036 §4).

**Qué pasa con las alteraciones.** `accidental.repeated` cubre el caso del que salen casi todos los aciertos de `learned.accidental`. En `exp_14` eran 33 de 38 posibles errores propios correctos y 33 de los 35 errores de alteración que las reglas no veían. Con esta regla:

- **Ese caso pasa a ser un posible error de regla** que la capa solo ordena. El arreglo que se muestra es el mismo, porque la capa puntúa el candidato con la misma tabla.
- **Bajan las métricas propias de la capa.** «Errores que las reglas no ven» y el F1 de los posibles errores propios de `learned.accidental` caerán mucho, porque las reglas ya no los dejan pasar.
- **Puede no promoverse una versión reentrenada.** La promoción de ADR-0036 (§9, enmiendas 10 y 16) compara justo ese F1, así que una versión reentrenada medida con las reglas nuevas podría no promoverse frente a la activa, aunque ordene igual de bien.
- **Cambia lo que la tesis atribuye a la capa (#270).** La capa sigue aportando el orden y el nivel de confianza de la sugerencia, pero el hallazgo pasa a ser de una regla.

**Las opciones**, que decide el responsable (CLAUDE.md §9):

- **A. Propuesta: incluir `accidental.repeated`.**
  - El posible error se ve aunque la capa no corra o no tenga versión promovida, y la condición asistida no depende de la promoción antes del congelado.
  - Lo propio de la capa se mide en dos planos: frente a las reglas de la versión 1 (lo que ya midió #257) y frente a las de la versión 2, con el orden y el nivel de las sugerencias de alteración.
  - El criterio de promoción frente a la versión activa se compara siempre con la misma versión de las reglas.
- **B. Dejar ese caso a la capa.** Se queda fuera del catálogo. El estudio solo lo ve si la capa está promovida y encendida en la condición asistida, y las reglas no atacan los errores de alteración que pide #245.

#246 implementa la regla detrás de su sitio en `DEFAULT_RULES_CATALOG`, así que pasar de A a B es quitarla del catálogo.

### 15. Qué construye #246

1. **El vocabulario.** `cadenza.validation.language` (§1), con sus pruebas, y `learned/messages.py` importando de él.
2. **Un apoyo común** para la capacidad de cada compás (tramos, rachas y S de `time.signature`, por parte) y para los grupos de tresillo. Lo usan `measure.balance`, `time.signature` y `tuplet.incomplete`, para que las tres reglas digan lo mismo.
3. **Las reglas** del §4 al §11, en `DEFAULT_RULES_CATALOG`, y `RULES_CATALOG_VERSION = 2`.
   - Pruebas por regla que incluyen **los ejemplos del §12**, con el mensaje y el «Qué revisar» exactos, los casos que no disparan y sus anclas y candidatos.
   - Las pruebas que expresaban lo que se retira se sustituyen diciendo por qué, como en ADR-0032 §4: las comprobaciones (b) y (c) de `key.consistency` y la nota de duración 0 de `voice.collision`.
4. **El compás de #236.** Si #236 ya está en `dev`, el símbolo del compás en los mensajes y el candidato de `time.signature`. Si no, se añaden cuando llegue.
5. **La vista**, sin cambios del contrato:
   - los títulos del §3 en `RULE_LABELS`;
   - «Qué revisar:» bajo el mensaje;
   - la condición no asistida del §13.2.
6. **Medir de nuevo** `exp_06` (precisión, *recall* y cobertura por categoría y por regla) y `exp_14`, con la versión nueva de las reglas.
   - Son mediciones nuevas, documentadas junto a las anteriores, y cada cifra lleva su `rules_version` y su `RULES_CATALOG_VERSION`.
   - Los recuentos exploratorios de este ADR no se citan. Si hacen falta, se regeneran con un script versionado.
7. **Verificar y desplegar.** Verificación contra la API real a 1440 y 390 px, y despliegue antes del congelado del 8 de noviembre.

## Consecuencias

### Positivas

- **El validador habla como un músico**: figuras, tiempos y nombres de notas, sin fracciones ni índices. Y dice qué mirar en la partitura impresa.
- **Hay una regla para los errores de alteración que más se escapan** (§7). Su posible error se ve sin la capa, y su arreglo llega como sugerencia cuando la capa lo puntúa alto.
- **Un compás mal leído da un hallazgo**, en lugar de uno por compás, y los compases bien leídos dejan de ser falsos positivos (§5).
- **Desaparecen falsos positivos conocidos**: la anacrusa, el último compás que la completa, el silencio de compás, las notas de adorno y la sensible de las tonalidades menores.
- **Los tresillos y los cambios de compás y de armadura tienen su sitio en el catálogo.** Las voces que entran o salen a mitad del compás (ADR-0032) no producen mensajes sobre lo que no se ve.
- **Ni el contrato ni el esquema cambian**: `message` y `suggested_fix` ya existen.

### Negativas / riesgos

- **Se gana precisión a costa de *recall*.** #246 lo mide. Ya no se señalan:
  - un primer compás corto con un error de figura;
  - una voz que se queda corta cuando otra completa el compás (ADR-0032);
  - una alteración repetida en otra voz.
- **El último compás corto sigue señalándose en los incipits de PrIMuS**, que se cortan donde sea: `exp_06` tendrá falsos positivos ahí. Se elige así por las páginas del estudio.
- **`time.signature` puede equivocarse de capacidad.**
  - Si la métrica leída es la buena y varios compases tienen el mismo error de figura, S esconde ese error en ellos y señala los buenos. En el recuento pasa en 2 de 1 172 incipits con el compás bien leído.
  - La métrica que propone no siempre es la verdadera (149 de 194): por eso dice «puede que sea».
  - El caso «desde un compás» (§5, caso 2) no está medido.
  - Con la etapa de #237 debería ser raro.
- **`accidental.repeated` se aprendió de PrIMuS con HOMR.** En páginas con cromatismos (TS-02) la repetición escrita es más frecuente, así que tendrá más falsos positivos. Por eso es `warning` y pregunta.
- **La capa pierde métricas propias** (§14), pendiente de la decisión del responsable.
- **Las cifras de este ADR son exploratorias** y de otro conjunto que `exp_06`. Las que valen son las de #246.
- **Hay más trabajo antes del congelado**: ocho reglas (tres nuevas) y la vista en la semana 2, con #236 por delante para el compás.
- **Los hallazgos ya guardados no se recalculan** (ADR-0013): son de la versión anterior del catálogo.

## Alternativas consideradas

| Alternativa | Motivo del descarte |
|---|---|
| Señalar toda alteración contra la armadura | En el recuento, solo 191 de 957 notas así se corrigieron (20 %): señala cada alteración escrita. |
| Dejar las alteraciones solo a la capa (`learned.accidental`) | Es la opción B del §14, que decide el responsable. Sin capa encendida y promovida, no se vería ningún posible error de alteración. |
| Corregir el compás en el validador | Las reglas no cambian la partitura (ADR-0036 §5). Leer bien el compás es de la etapa de #237, y cambiarlo es una edición de la persona (#236). |
| Un `measure.balance` por compás también con el compás mal leído | Es lo de hoy: un posible error falso en cada compás, con candidatos que acortan figuras buenas. |
| No señalar nunca el último compás corto | Es lo mejor para los incipits de PrIMuS, pero quitaría la mitad de «le falta» en una página de cuatro compases (TS-01). |
| Mensajes con la suma en negras («suma 7/2 negras») | Es lo que el issue pide quitar: una fracción no dice qué figura falta ni dónde. |
| Nombrar las voces por su número | El número es interno y cambia de un compás a otro (ADR-0032 §3). Arriba y abajo es lo que se ve. |
| Renombrar `key.consistency` y `voice.collision` | Los identificadores están en los hallazgos guardados y en `exp_06` por regla. Cambia el título en la vista, no el identificador. |
| Poner la versión del catálogo dentro de `rules_version` | `exp_06` separa `rules_version` por comas para saber qué reglas medir. La versión va en una constante aparte. |
| Mostrar «Qué revisar» como una sugerencia aplicable | Es texto. Lo aplicable son las sugerencias estructuradas de ADR-0036, que la vista muestra aparte (#258). |
