# ADR-0059: El compás por tramos, C y ¢ y los tresillos implícitos, en una etapa tras HOMR

- **Estado:** Aceptado
- **Fecha:** 2026-11-02
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0001, ADR-0018, ADR-0040, ADR-0044 y ADR-0056, CLAUDE.md §8 y §9)
- **Actualiza:** [ADR-0018](ADR-0018-homr-como-unico-motor-omr.md) (lo que da el motor: la transcripción de HOMR pasa por una etapa de Cadenza antes de validarse)
- **Relacionado:** [ADR-0040](ADR-0040-catalogo-de-reglas-y-mensajes-en-lenguaje-musical.md), [ADR-0044](ADR-0044-compas-con-su-simbolo-y-tresillos-como-edicion.md), [ADR-0056](ADR-0056-conjunto-de-referencia-del-compas-tresillos-armaduras-y-voz-con-piano.md), [INV-0002](../investigaciones/INV-0002-audiveris-frente-a-homr.md), [#234](https://github.com/sebdavid3/Cadenza/issues/234), [#236](https://github.com/sebdavid3/Cadenza/issues/236), [#237](https://github.com/sebdavid3/Cadenza/issues/237), [#239](https://github.com/sebdavid3/Cadenza/issues/239)

---

## Contexto

Leído en el código de HOMR 0.7.0 y en sus lecturas del conjunto de referencia (#234):

- **El compás.** Su vocabulario solo tiene `timeSignature/{denominador}`. `find_division_and_time_signature_nominator` pone a todos los compases de cada pentagrama (en HOMR, una «voz»: el mismo pentagrama en todos los sistemas) el mismo numerador, la mediana de lo que suman sus compases. Además, `_remove_redudant_clefs_keys_and_time_signatures` quita, en toda la página, una indicación igual a la anterior: el MusicXML de HOMR solo lleva `<time>` donde cambia el denominador o donde aparece el primero. Así que en el `ScoreIR` importado, donde cada compás lleva su métrica efectiva (ADR-0044), **los tramos que leyó HOMR son las rachas de compases con la misma indicación**, y los compases sin ninguna son de un tramo que empezó en otra página.
- **El símbolo.** HOMR no lo escribe nunca (ADR-0044): C y 4/4 son para él `timeSignature/4`, y ¢ y 2/2, `timeSignature/2`.
- **Los tresillos.** `_fix_over_eager_tuplets` quita los tresillos de los compases que suman menos que la mediana de la página. En la Sonata *Claro de luna* desaparecen los del compás 1, los únicos marcados, y la página sale en 3/2 con doce corcheas en la mano derecha; la izquierda dura una redonda por compás.
- **No hay barras de corchea** en la salida de HOMR (ni en su vocabulario): la agrupación de las figuras no se puede leer de ella.
- **La línea base medida** (`exp_15`, ADR-0056, ejecución del responsable en `results/exp_15/`): HOMR no lee el símbolo en ningún compás (0 de 120 en las páginas, 0 de 4 192 en PrIMuS); el numerador está bien en el 62,8 % de PrIMuS (1 236 de 1 968), y el error de métrica más frecuente es leer C como 3/4 (250 incipits), a menudo porque la anacrusa y el último compás cortado bajan la mediana; a mitad de página, 3 de 6 cambios con la métrica buena; tresillos implícitos, 0 de 2.
- `exp_04`, `exp_07`, `exp_11` y `exp_12` construyen `HOMREngine` y deben seguir midiendo HOMR solo. Sustituir en caliente `_fix_over_eager_tuplets`, como se hizo con `detect_title` (#106), ataría Cadenza a HOMR 0.7.0.

## Decisión

### 1. Una etapa propia, después del motor y fuera de `HOMREngine`

`cadenza.omr.meter_stage` (su propio módulo, que solo depende del dominio): `recognize_meter(score, rasgos)` recibe el `ScoreIR` que dio el motor y devuelve otro, con lo que decidió; `MeterStage(rasgos).apply(documento)` lo aplica a un `ScoreDocument`, deriva de nuevo las anclas (la etapa no añade ni quita eventos, así que cada ancla sigue señalando el mismo evento) y se anota en la procedencia (§5).

- **Corre en el caso de uso `transcribe_score`** (que la recibe por el puerto `RecognitionStage`, un `Protocol` que `MeterStage` cumple por estructura), tras `OMREngine.transcribe` y antes de las reglas, **en las dos condiciones** (`assisted` y `unassisted`): las dos condiciones del estudio parten de la misma lectura.
- **`HOMREngine` no cambia**, ni los experimentos que lo construyen: siguen midiendo HOMR solo. Tampoco se sustituye nada de HOMR en caliente.
- **En la API**, `create_app` construye la etapa con los rasgos de `CADENZA_OMR_METER_FEATURES` cuando construye HOMR (sin motor inyectado). Con un motor inyectado, solo corre la etapa que se inyecte (`create_app(meter_stage=…)`): el doble de pruebas da su partitura tal cual y las pruebas que dependen de ella no cambian.
- Trabaja sobre el `ScoreIR`, no sobre el MusicXML de HOMR: es lo que se guarda en la sesión, se prueba con lecturas sintéticas sin HOMR ni imágenes, y #239, que cambia la importación de las partes, no la toca.

### 2. Las señales

- **El denominador leído**, que no se cambia (HOMR acierta el denominador en el 99,2 % de PrIMuS).
- **Lo que suma cada compás de cada pentagrama**: la voz más larga, sin las notas de un acorde.
- **La anacrusa y el último compás**: el primero no vota si suma menos que la mediana de los demás; el último tampoco (el que completa la anacrusa, o un incipit cortado). Solo con tres compases o más. Con la mediana, y no con el más largo, un compás leído de más no le quita el voto a un primer o un último compás completos.
- **Los tresillos marcados**: las figuras con un 3 en el denominador (ADR-0044 §3) que HOMR dejó.
- **La parte**: la duración del compás es la de la parte (ADR-0044 §2), así que lo que dura un pentagrama confirma la del otro.
- **La agrupación no se usa**: no está en la salida de HOMR. Sin ella, 3/2 con doce corcheas y ¢ con doce tresillos de corchea solo se distinguen por la parte o por los tresillos marcados (§3.3).

### 3. Tres rasgos que se activan por separado

1. **`numerator`, el numerador por tramo.** Cada tramo de cada parte (los compases seguidos con la misma indicación de HOMR; sin indicación no hay tramo) recibe la duración que más votos tiene: cada compás de cada pentagrama vota por lo que suma, sin la anacrusa ni el último si suman menos (§2), y a igualdad gana la mayor. Solo votan las sumas que dan, con el denominador leído, un numerador entero de 1 a 32 (con denominador 4, nueve corcheas no son ningún compás: son una lectura de más o de menos). El numerador es la duración ganadora por el denominador; si no vota ninguna suma (o el tramo está vacío, como una cortesía leída como un compás aparte), se queda el de HOMR. Se usa la moda y no el máximo: en una página, un compás leído de más pesaría tanto como todos los buenos.
2. **`symbol`, C y ¢.** Un tramo en 4/4 se escribe C, y uno en 2/2, ¢: es lo que se imprime casi siempre. En PrIMuS, 775 incipits llevan C frente a 5 con 4/4, y 284 llevan ¢ frente a 19 con 2/2; en las páginas del conjunto, todos los 4/4 y 2/2 impresos son C y ¢. No es leer el símbolo, que HOMR no da, sino la grafía más probable de la métrica; su acierto se mide aparte con `time_symbol_agreement` (ADR-0044 §1).
3. **`implicit_tuplets`, los tresillos sin marcar.** Un compás cuya voz dura más que el compás del tramo se lee con tresillos si pasar a tresillo de 3:2 **todas** sus figuras de un mismo valor sin puntillo (notas y silencios, en múltiplo de tres, con las notas de sus acordes) lo deja durando justo lo que el compás; si cuadra con dos figuras distintas, es ambiguo y no se toca, y las figuras que ya son de tresillo no cambian. Hace falta una señal de que hay tresillos sin marcar: que el pentagrama ya tenga tresillos marcados de esa figura en el tramo, en ese compás o antes (al estilo de `implicitTuplets` de Audiveris), o que **otro pentagrama de la parte** tenga compases que duren justo eso (sin contar su anacrusa ni su último compás) y que **al menos dos** compases del pentagrama cuadren así: un solo compás leído de más que cuadra por casualidad no basta. Con `numerator`, el compás del tramo y los tresillos se deciden a la vez: un compás que cuadra con tresillos a una duración vota también por ella. En la Sonata, la mano izquierda (una redonda) y la derecha con tresillos votan ¢ frente a la derecha sin ellos, que vota 3/2; sin `implicit_tuplets`, las dos manos empatan y gana la mayor, 3/2. Doce corcheas en un solo pentagrama, sin tresillos marcados, no tienen señal y se quedan en 3/2.

### 4. Activación

`CADENZA_OMR_METER_FEATURES` (por defecto, `numerator,symbol,implicit_tuplets`; `all` o `none`) dice qué rasgos corren en la API; un nombre desconocido impide arrancar, para que una errata no apague un rasgo en silencio. La decisión de cada rasgo sale de la medición (§6).

### 5. Procedencia

`Provenance` gana `omr_stages`: un objeto por etapa que corrió tras el motor, aquí `{"meter": {"version", "features", "segments", "tuplets", "skipped_parts"}}`, con cada tramo (parte, compases, lo que leyó HOMR, lo reconocido y si cambió) y cada compás que pasó a tresillos (parte, pentagrama, compás y la figura de cada voz). Sin etapa no se serializa: los documentos guardados antes se leen y se guardan igual. `Provenance.omr_engine` sigue siendo `homr`, y `METER_STAGE_VERSION` (1) sube si cambia lo que la etapa decide con la misma entrada.

- **El contrato de la API v1 no cambia**: `ProvenancePayload` no tiene el campo y lo ignora al responder, como antes cualquier clave que no declara. Se guarda en el documento de la sesión, no en otra tabla: no hay migración.
- Las anclas, el log y las ediciones no cambian: la etapa produce el estado 0, como antes lo producía HOMR.

### 6. Medición

`exp_15` gana `--meter-features`: la lectura de HOMR de cada página y de cada incipit pasa por la etapa antes de compararla, y en PrIMuS da además la SER antes y después de la etapa y, en los incipits que la etapa cambia (la igualdad del `ScoreIR` no ve el símbolo), el OMR-NED antes y después, con MusicXML exportados del `ScoreIR` sin el símbolo, como `exp_14` (ADR-0044 §1). El OMR-NED y la SER de PrIMuS se miden en `exp_15` y no en `exp_03`, porque `exp_03` compara con musicdiff el MusicXML de HOMR tal cual, sin pasar por el `ScoreIR`, donde corre la etapa.

**Resultado** (2026-11-02, ejecución del autor en su scratchpad, no en `results/`, con `--reuse-predictions` sobre las predicciones de HOMR de la línea base; sin rasgos reproduce exactamente su `headline`). Las doce páginas cuentan pentagramas de la verdad (ADR-0056); PrIMuS, los 1 968 incipits medidos de las dos fuentes. El resto del resumen (armaduras, tresillos marcados, partes y pentagramas, compases heredados) no cambia con ningún rasgo.

| Medida | HOMR solo | `numerator` | `symbol` | `implicit_tuplets` | los tres |
|---|---|---|---|---|---|
| Páginas: inicio de tramo con la grafía buena | 9/15 | 9/15 | 15/15 | 9/15 | 15/15 |
| Páginas: cambio a mitad de página con la métrica buena | 3/6 | 6/6 | 3/6 | 3/6 | 6/6 |
| Páginas: cambio a mitad de página con la grafía buena | 0/6 | 3/6 | 3/6 | 0/6 | 6/6 |
| Páginas: compases impresos con la métrica buena | 360/375 | 375/375 | 360/375 | 360/375 | 375/375 |
| Páginas: compases impresos con la grafía buena | 240/375 | 255/375 | 360/375 | 240/375 | 375/375 |
| Páginas: símbolo C/¢ por compás (`time_symbol_agreement`) | 0/120 | 0/120 | 120/135 | 0/120 | 120/120 |
| Páginas: tresillos implícitos leídos | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| Páginas: compases leídos con tresillos que están en la verdad | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| PrIMuS: numerador (y métrica) | 1 236 (62,8 %) | 1 717 (87,2 %) | 1 236 | 1 236 | 1 717 (87,2 %) |
| PrIMuS: métrica y grafía | 660 (33,5 %) | 828 | 1 224 | 660 | 1 695 (86,1 %) |
| PrIMuS: símbolo C/¢ por compás | 0/4 192 | 0/4 192 | 2 287/4 304 | 0/4 192 | 3 602/4 336 (83,1 %) |

`symbol` solo, sin `numerator`, escribe C donde HOMR lee 4/4 un 3/4 (*Ellens Gesang*, p. 7): de ahí los 15 compases con el símbolo mal de esa columna, que desaparecen con los dos rasgos.

**La SER y el OMR-NED de PrIMuS** solo cambian con `numerator` (con `symbol` o `implicit_tuplets` solos, la etapa no cambia ninguna lectura que midan; los tres juntos dan lo mismo que `numerator`):

| Fuente | Incipits | Cambiados por la etapa | SER media antes → después | Mejoran / empeoran (SER) | OMR-NED medio de los cambiados antes → después | Mejoran / empeoran (OMR-NED) |
|---|---|---|---|---|---|---|
| `primus-exp-03` | 91 | 18 | 0,1124 → 0,0873 | 16 / 0 | 0,3574 → 0,2866 | 18 / 0 |
| `primus-exp-12` | 1 877 | 531 | 0,1339 → 0,0966 | 480 / 13 | 0,3295 → 0,2619 | 494 / 15 |

El OMR-NED medio sobre todos los incipits medidos baja 0,0140 y 0,0191 (musicdiff comparó todos los pares). **Esto no es una prueba aparte de que el resto no empeora**: con `numerator` solo no cambia ninguna figura, solo la indicación, que la SER cuenta en cada compás (`time:b/t`) y el OMR-NED en cada `<time>`; la SER y el OMR-NED repiten, pesado por compases, el acierto del numerador. Lo que asegura que el resto no empeora es que, sin `implicit_tuplets`, la etapa no toca ningún evento; y con él, que en `exp_15` no cambia ninguno. Los incipits que empeoran (13 por la SER) son lecturas en las que la mediana de HOMR acertaba y la suma más repetida no: compases leídos de más que ganan (un C que HOMR leía 4/4 y la etapa pasa a 5/4, 6/4 u 8/4; un 3/4 que pasa a 4/4).

**Los tresillos implícitos no cambian nada en `exp_15`**: en las páginas, los dos compases implícitos (*Der stürmische Morgen*, p. 65) no tienen tresillos marcados en su página y HOMR lee sus figuras con otro valor; en PrIMuS no hay incipit que cumpla la regla. Fuera del conjunto:

- **La Sonata *Claro de luna*** (página del responsable, no versionada), por el camino de producción (`HOMREngine` en CPU, la etapa con los rasgos por defecto y `transcribe_score`): HOMR lee 3/2 con doce corcheas; la etapa da ¢ y doce tresillos de corchea en la mano derecha de los compases 1 a 4, y el MusicXML exportado lleva `<time symbol="cut">` y los `<time-modification>`. Con `numerator` y `symbol` sin `implicit_tuplets`, la página se queda en 3/2.
- **El banco del estudio** (#247, solo para comprobar): el calentamiento y la página de TS-04 pasan de 4/4 a C, como su verdad; TS-01, un incipit en C que HOMR lee como 2/4 porque lee las negras como corcheas en tres de sus cuatro compases, sigue en 2/4; TS-02, TS-03 y el recorte de TS-04 no traen compás impreso y la etapa no los toca.

**Decisión por rasgo**: `numerator` y `symbol` se activan: juntos dejan bien todos los compases con indicación impresa de las páginas y suben la métrica y la grafía de PrIMuS, sin tocar ningún evento. `implicit_tuplets` se activa también: no cambia ninguna cifra de `exp_15` ni de PrIMuS (no empeora nada) y es lo que da los tresillos y el ¢ de la Sonata que pide #237. Su única evidencia es esa página, que no está en el conjunto; si el responsable prefiere no activarlo sin una medida del conjunto, basta con quitarlo de `CADENZA_OMR_METER_FEATURES`, sin cambiar código.

## Consecuencias

### Positivas
- En las páginas del conjunto, todos los compases con indicación impresa salen con la métrica y la grafía buenas (375 de 375), también los dos cambios a mitad de página; en PrIMuS, la métrica pasa del 62,8 % al 87,2 % y la grafía del 33,5 % al 86,1 %.
- La Sonata sale en ¢ con los tresillos de la mano derecha en los compases 1 a 4.
- Lo que la etapa decidió queda en la sesión, y se puede apagar rasgo a rasgo sin tocar código.
- Los experimentos de HOMR no cambian, y la etapa se mide con el mismo conjunto, rasgo a rasgo.

### Negativas / Riesgos
- **El símbolo es una apuesta, no una lectura**: un 4/4 o un 2/2 impresos con números salen C o ¢. En PrIMuS es lo raro; en música de otra época u otra editorial puede no serlo.
- **El numerador depende de que HOMR lea bien las figuras**: si las lee a la mitad en casi todos los compases (TS-01 del banco del estudio, un incipit en C que HOMR lee como 2/4 con negras leídas como corcheas), la moda sigue la lectura y el compás se queda mal.
- **Un cambio de compás con el mismo denominador a mitad de página se pierde**: HOMR quita la segunda indicación (`_remove_redudant_…`) y el tramo une las dos métricas; la moda se queda con la de más compases.
- **Los compases sin indicación** (un tramo que empezó en otra página, 409 de 414 en el conjunto) siguen sin ella: sin denominador leído, la etapa no los adivina.
- **Tresillos implícitos**: solo los de 3:2 y solo si todas las figuras de un valor de la voz pasan a tresillo; un compás que mezcla tresillos y figuras normales del mismo valor no cuadra y no se toca. En `exp_15` no se ve ninguno (los dos compases implícitos de *Der stürmische Morgen* no tienen tresillos marcados en su página y HOMR lee sus figuras de otro valor); la única evidencia de que mejora es la Sonata, que no es del conjunto.
- **Tresillos por la parte**: en un piano, la mano izquierda suele durar el compás, así que basta que dos compases de la derecha estén leídos de más justo en un tercio de sus figuras de un valor para que pasen a tresillos. En las doce páginas no ocurre (los compases leídos con tresillos siguen estando todos en la verdad), pero son pocas páginas.
- **La etapa se diseñó y se midió con el mismo conjunto** (el de #234, sin el banco del estudio): sus cifras no son de una muestra independiente. Además son del scratchpad del autor; antes de citarlas, el responsable las regenera en `results/` (CLAUDE.md §8.4).

## Alternativas consideradas

1. **Sustituir en caliente `_fix_over_eager_tuplets`** (como `detect_title`, #106). Descartada: ata Cadenza a HOMR 0.7.0 y cambia lo que miden los experimentos de HOMR.
2. **La etapa dentro de `HOMREngine`, o un motor que lo envuelva.** Descartada: `exp_04`, `exp_07`, `exp_11` y `exp_12` dejarían de medir HOMR solo; envolverlo, además, choca con `from_active_model`, que construye el motor por su tipo.
3. **Trabajar sobre el MusicXML de HOMR.** Descartada: habría que reescribir divisiones y `<time-modification>`; el `ScoreIR` es lo que se guarda, y los tramos de HOMR se ven igual en él (§Contexto).
4. **El numerador por el máximo de las sumas.** En PrIMuS acierta algo más que la moda (incipits cortos), pero en una página un compás leído de más decide el tramo. Se mide la moda.
5. **Adivinar el compás de los compases sin indicación** (el tramo de otra página). Descartada aquí: sin denominador, 3/8 y 3/4 o 6/8 suman lo mismo (*Mondnacht*).
6. **Audiveris** para el símbolo y los tresillos (INV-0002). Fuera de la entrega (#262): lento y no siempre acierta.
