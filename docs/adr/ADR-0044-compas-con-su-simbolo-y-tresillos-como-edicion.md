# ADR-0044: El compás con su símbolo, cambiar el compás y poner o quitar tresillos

- **Estado:** Aceptado
- **Fecha:** 2026-11-01
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0007, ADR-0010, ADR-0011, ADR-0017, ADR-0033, ADR-0034, ADR-0036, ADR-0037, ADR-0039 y ADR-0040, CLAUDE.md §9)
- **Completa:** [ADR-0039](ADR-0039-anadir-y-quitar-marcas-de-notacion.md) §3.7 (operaciones futuras de `EditOp`) y [ADR-0040](ADR-0040-catalogo-de-reglas-y-mensajes-en-lenguaje-musical.md) §1, §5 y su enmienda 1 (el símbolo leído y el candidato de `time.signature`)
- **Relacionado:** [ADR-0007](ADR-0007-edit-events-inmutables.md), [ADR-0010](ADR-0010-score-ir-atributos-y-exportacion.md), [ADR-0011](ADR-0011-semantica-de-anclas-ante-ediciones.md), [ADR-0017](ADR-0017-validacion-del-contenido-de-las-ediciones.md), [ADR-0031](ADR-0031-marcas-de-notacion-en-el-score-ir.md), [ADR-0033](ADR-0033-insertar-borrar-clave-y-armadura.md), [ADR-0034](ADR-0034-deshacer-y-rehacer-desde-la-vista.md), [ADR-0036](ADR-0036-capa-de-sugerencias-aprendida.md), [ADR-0037](ADR-0037-una-edicion-en-un-solo-viaje.md), [#236](https://github.com/sebdavid3/Cadenza/issues/236), [#237](https://github.com/sebdavid3/Cadenza/issues/237), [#241](https://github.com/sebdavid3/Cadenza/issues/241), [#244](https://github.com/sebdavid3/Cadenza/issues/244)

---

## Contexto

Hechos comprobados en el código el 2026-10-31:

- `TimeSignature` era `(beats, beat_type)`: no distinguía C de 4/4 ni ¢ de 2/2, y la exportación escribía con números lo que se había importado con símbolo.
- **La importación da a cada compás su métrica efectiva** (`_measure_signature` toma la del contexto si el compás no tiene la suya), y la exportación solo la escribe donde cambia (#152). Así que en un `ScoreIR` importado todos los compases llevan indicación, y «cambiar el compás desde el compás 5» no es cambiar un atributo del compás 5.
- El mapa de tiempos (`compute_timing_map`) toma la métrica de un número de compás de cualquier pentagrama que la declare, y el exportador une los pentagramas de una parte (un piano). La validación (ADR-0040 §5) calcula la capacidad de cada compás para toda la parte.
- Ninguna de las once `EditOp` cambiaba el compás. ADR-0017 ya admite duraciones con denominador 3 y el exportador escribe los `<time-modification>` de esas figuras, pero convertir doce corcheas en cuatro tresillos eran doce `SetDuration` y doce pasos de deshacer.
- `derive_edit_events` (`cadenza.learning.alignment`) no compara las indicaciones de compás, y un tresillo mal leído sale como un `SetDuration` por figura. La cobertura de `exp_02` es `len(op_counts) / len(CONTENT_EDIT_OPS)` (ADR-0039 §3).
- HOMR 0.7.0 nunca escribe `symbol` en sus `<time>` (0 de 91 predicciones de `data/primus/predictions`). Las verdades MEI de PrIMuS sí lo traen a menudo (`meter.sym`).

## Decisión

### 1. `TimeSignature.symbol`

`TimeSignature` gana `symbol`: `"common"` (C), `"cut"` (¢) o `None` (con números). C solo vale con 4/4 y ¢ con 2/2.

- **Es grafía, no métrica**: la igualdad y el hash de `TimeSignature` siguen siendo los de `beats` y `beat_type`, y `str()` sigue dando «4/4». C y 4/4 son la misma métrica, como las marcas de notación no son contenido (ADR-0031 §6). Lo que sí distingue la grafía (exportar, el tramo de `SetTime`, el `before` del cliente) usa `same_notation` / `same_time_notation`.
- **Primitivo**: sin símbolo no se serializa, así que las sesiones guardadas se leen y se exportan igual.
- **Importación**: se guarda si music21 lo trae y escribe su métrica (otro `symbol`, como `single-number`, o un C sobre 3/4, se queda en los números). **Exportación**: se escribe donde cambia la métrica o su grafía, también de C a 4/4 con números.
- **Huella de `data/`** (antes y después, en solo lectura, sobre 4 436 archivos: las verdades MEI de los dos manifiestos, las predicciones de HOMR de `data/primus/predictions*` y las tres verdades de referencia): cambian 1 155, todas verdades (72 de las 100 del manifiesto principal, 1 081 del de `exp_12` y dos `.mxl` de referencia), por 3 397 compases con C y 1 346 con ¢; ninguna predicción. Quitando el símbolo, las 1 155 dan exactamente la huella de antes.
- **Las cifras de `results/` no cambian**: los experimentos comparan métricas con `==` (`time_misread` de `exp_12`, `is_structurally_equal`), que no ve el símbolo; la SER y el corpus usan `str()` o `beats`/`beat_type`; los rasgos de la capa de sugerencias usan `str(time)`, así que `FEATURE_VERSION` no cambia.
- **Contrato**: `TimeSignaturePayload.symbol`, opcional y `null` por defecto.

### 2. `SetTime`: cambiar el compás desde un compás

Anclada al primer evento del compás, como `SetKey` (ADR-0010, ADR-0033 §6). `after`: `{"time_signature": {"beats", "beat_type", "symbol"?}, "measures"?: k}`.

- **Desde el compás del ancla hasta el siguiente cambio**, como la clave y la armadura. Como cada compás importado lleva su métrica, el ámbito es el **tramo**: el compás del ancla y los siguientes que llevan su misma indicación (métrica y grafía) o ninguna, hasta el primero que lleva otra. El compás del ancla pasa a llevar la nueva y los demás del tramo que llevaban una, también; los que no llevaban ninguna siguen sin ella (heredan la nueva). `measures` dice cuántos compases cambia, sin pasar del siguiente cambio; sin él, el tramo entero.
- **En todos los pentagramas de la parte**, a diferencia de la clave y la armadura: la duración de un compás es la de la parte (el mapa de tiempos, la validación y el exportador la comparten), y cambiarla en un solo pentagrama de un piano dejaría la partitura incoherente. Si los pentagramas no llevan la misma indicación en ese compás o sus tramos no miden lo mismo, 422 (un solo `before` no podría devolverlos; no ocurre con HOMR).
- **`time_signature: null` se rechaza** (422): la importación da a cada compás su métrica, y un compás sin ella dejaría de comprobarse (`measure.balance`) y de rellenarse al exportar (#152). Para quitar un cambio se pone la del compás anterior. Solo la compensatoria escribe `null`, para devolver un compás que no la llevaba.
- **Tipo «fijar»** (ADR-0039 §1): el `before` es `{"time_signature": la del compás del ancla o null, "measures": los compases que cambió}` y la compensatoria intercambia `before` y `after`. Deshacer es exacto: devuelve la indicación del compás del ancla y la vigente a los demás de esos compases que la llevaban, y deja sin ella los que no la llevaban. Rehacer reenvía el `after` original, que vuelve a calcular el tramo sobre el mismo estado.
- Validación: claves exactas, `beats` de 1 a 32, `beat_type` 1, 2, 4, 8, 16 o 32, el símbolo con su métrica; las notas no cambian (como la clave: el validador señala después los compases que no cuadran).

### 3. Tresillos: una operación nueva, `SetTuplet`

El criterio del issue es que convertir en tresillos un compás de doce corcheas cueste como mucho dos acciones y se deshaga de un paso. **Una operación nueva**, no un grupo de ediciones:

- `SetTuplet`, anclada al primer evento del tramo: `{"durations": [d1, ..., dn]}`, las figuras finales de los n eventos seguidos de la voz del ancla en su compás. **Tipo «fijar»**: el `before` son sus figuras de antes y deshacer las intercambia, en un paso. Doce corcheas a cuatro tresillos: **una edición**; en la barra de #241, elegir y pulsar.
- **Solo tresillos de 3:2**: poner multiplica cada figura por 2/3 y la figura nueva tiene que llevar el tresillo (una figura con puntillo por 2/3 es otra figura sin tresillo, y se rechaza); quitar multiplica por 3/2 las que lo llevan. Todo el tramo hace lo mismo. Las figuras resultantes pasan la validación de duraciones de ADR-0017 (un tresillo dentro de otro, 2/9, no es representable). Quintillos y septillos siguen siendo `SetDuration` por figura.
- Las notas de adorno del tramo (ADR-0028) llevan `null` y no cambian. El tramo no empieza ni acaba a mitad de un acorde, y las notas de un acorde cambian con él.
- El exportador ya escribe el tresillo (`<time-modification>` y su corchete) a partir de las figuras.

### 4. Política de `EditOp`: una clase nueva, `METER_EDIT_OPS`

ADR-0039 §3.7 pide clasificar cada operación nueva. `SetTime` y `SetTuplet` forman **`METER_EDIT_OPS`** («compás y tresillos»), aparte de `CONTENT_EDIT_OPS` (que pasa a ser una lista explícita de siete) y de `MARK_EDIT_OPS`:

1. **`derive_edit_events` no las produce**: no alinea las indicaciones de compás, y un tresillo mal leído sale como un `SetDuration` por figura, que es lo que miden la SER y la cobertura. Contarlas en el denominador de la cobertura de `exp_02` bajaría la cifra sin que cambie nada medido, así que **`len(CONTENT_EDIT_OPS)` sigue siendo 7 y la cobertura de `exp_02` no cambia**.
2. **`DatasetBuilder`** no hace muestras de ellas (una muestra es de un evento y su altura). El corpus de correcciones (#255) y la capa de sugerencias (#256) siguen viendo los tresillos corregidos, porque comparan el estado 0 con el final: salen como `SetDuration`.
3. **`categorize_edit_op`** las llama `"meter"`.
4. **Las métricas de esfuerzo del estudio** (#188) las cuentan como intervenciones, como las de marcas (ADR-0039 §3.6).
5. **Las mediciones de las sugerencias** (`exp_14` y la de #257) cuentan solo los candidatos de contenido (`with_content_candidates`): su verdad es `derive_edit_events`, que no puede juzgar un candidato de cambiar el compás. Así, el candidato nuevo de `time.signature` (§5) no cambia sus cifras (`with_candidates`, `top1`…).

### 5. Validador (completa ADR-0040)

- **El símbolo leído en los mensajes**: la métrica se nombra como se escribe, «C» o «¢» si lleva su símbolo (ADR-0040 §1). Las predicciones de HOMR no lo traen, así que los mensajes medidos en `exp_06` y `exp_14` no cambian.
- **El candidato de `time.signature`**: un `SetTime` a S desde el compás del ancla, como fija ADR-0040 §5. En el caso «en todo el tramo», hasta el siguiente cambio; en el caso «desde un compás», solo los compases de la racha (`measures`), porque fuera de ella la capacidad vuelve a ser la métrica leída. El candidato es admisible (`validate_after`) y `describe_edit` lo dice («Cambiar la indicación de compás a 4/4 desde este compás.»).
- **No se muestra en el estudio**: `SetTime` no es de ninguna familia de sugerencias (`SUGGESTION_FAMILIES`), como el `SetKey` de `key.consistency`, así que ninguna política lo muestra. Mostrarlo lo decidiría #244.
- **`RULES_CATALOG_VERSION` sigue en 2**: lo que miden `exp_06` y `exp_14` (hallazgos, anclas y candidatos de contenido) no cambia. Un catálogo 3 obligaría a medir de nuevo para comparar modelos (`promotion_decision`) sin que cambie ninguna cifra.

### 6. Web

La barra para cambiar el compás y los tresillos es #241. Aquí solo la historia de ediciones dice las operaciones nuevas («compás 3/4», «compás C», «tresillo en 12 figuras», «quitar el tresillo de 3 figuras»), el compás de `SetTime` sin voz, que no mueve la selección, y qué `before` basta para deshacer.

### 7. Contrato y migración

Ampliación compatible del contrato v1: `EditOp` gana `SetTime` y `SetTuplet`, y `TimeSignaturePayload`, `symbol` opcional; `openapi.json` y `types.ts` regenerados. No hay migración: el log guarda `op` como texto y `before`/`after` como JSON, y el `ScoreIR` como JSON.

## Consecuencias

### Positivas
- Se corrige el compás (números, C o ¢) desde un compás y para toda la parte con una edición, y doce corcheas pasan a cuatro tresillos con una edición; las dos se deshacen de un paso y exactamente.
- Las verdades con C y ¢ se exportan con su símbolo.
- Las cifras de `results/` no cambian (§1 y §4), y la caché del estado (ADR-0037) no necesita nada: las dos operaciones pasan por `apply_edit` y un cambio de solo grafía no cambia el mapa de tiempos.
- `time.signature` trae ya su candidato aplicable, por si #244 decide mostrarlo.

### Negativas / Riesgos
- La igualdad de `TimeSignature` no ve el símbolo: código nuevo que quiera distinguir C de 4/4 debe usar `same_notation`. Las pruebas lo cubren en el exportador, `SetTime` y el `before` del cliente.
- `SetTime` no admite `null` de un cliente, a diferencia de `SetClef` y `SetKey`: para quitar un cambio hay que poner el compás anterior.
- Una partitura cuyos pentagramas lleven compases distintos en un mismo compás (no ocurre con HOMR) no se puede cambiar con `SetTime` (422).
- `SetTime` no toca las notas: cambiar 3/4 por 4/4 deja los compases con las mismas figuras, y el validador los señala si no cuadran.
- Solo hay tresillos de 3:2 como una edición; un quintillo o un septillo son `SetDuration` por figura. Una figura con puntillo no se convierte en tresillo con `SetTuplet`.
- El tramo del candidato de `time.signature` «en todo el tramo» se calcula con la métrica (sin grafía) y el de `SetTime`, con la grafía: en un tramo que mezclara C y 4/4 con números (no ocurre con HOMR), el candidato cambiaría solo hasta el cambio de grafía.

## Alternativas consideradas

1. **Tresillos como un grupo de ediciones** (doce `SetDuration` con un identificador de grupo). Descartada: deshacer y rehacer de un paso necesitarían un concepto nuevo en el log (ADR-0034 deshace de una en una) y la historia vería doce ediciones.
2. **`SetTuplet` con un factor** (`{"count": 12, "factor": "2/3"}`) en vez de las figuras. Descartada: el `before` no sería una instantánea (ADR-0017), deshacer dependería de recalcular y una figura con puntillo no volvería exacta.
3. **Una operación genérica de figuras** (`SetDurations`, cualquier figura nueva). Descartada: sería otra forma de `SetDuration` que la historia y las métricas no podrían nombrar; `SetTuplet` dice lo que hace y valida que lo hace.
4. **`SetTime` en el pentagrama del ancla, como `SetKey`.** Descartada: la duración del compás es de la parte, y un piano quedaría con dos métricas a la vez.
5. **`SetTime` solo en el compás del ancla.** Descartada: como la importación da a cada compás su métrica, el compás siguiente volvería a la anterior; cambiar el compás de una pieza serían tantas ediciones como compases.
6. **Normalizar la importación para que solo los compases con cambio lleven indicación.** Descartada: cambiaría el `ScoreIR` de todas las verdades y predicciones de `data/` y las sesiones guardadas.
7. **El símbolo dentro de la igualdad de `TimeSignature`.** Descartada: `time_misread` de `exp_12` compara la métrica leída por HOMR (sin símbolo) con la de la verdad MEI (con él) y su cifra cambiaría sin que cambie la métrica leída; también partiría los tramos de `time.signature` entre C y 4/4.
8. **`SetTime` y `SetTuplet` en `CONTENT_EDIT_OPS`.** Descartada: la cobertura de `exp_02` pasaría de «de 7» a «de 9» con dos operaciones que `derive_edit_events` nunca produce.
9. **Subir `RULES_CATALOG_VERSION`.** Descartada (§5).
