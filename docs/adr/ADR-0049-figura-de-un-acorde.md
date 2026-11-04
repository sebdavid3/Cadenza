# ADR-0049: Cambiar la figura de un acorde entero con una operación nueva, `SetChordDuration`

- **Estado:** Aceptado
- **Fecha:** 2026-11-01
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0007, ADR-0011, ADR-0017, ADR-0030, ADR-0032, ADR-0033, ADR-0034, ADR-0036, ADR-0037, ADR-0039 y ADR-0044, CLAUDE.md §9)
- **Completa:** [ADR-0030](ADR-0030-correccion-de-altura-duracion-y-alteracion.md) §2 («En un acorde no se cambia la figura… queda para cuando se pueda cambiar el acorde entero») y [ADR-0039](ADR-0039-anadir-y-quitar-marcas-de-notacion.md) §3.7 (clasificar cada operación nueva de `EditOp`)
- **Relacionado:** [ADR-0007](ADR-0007-edit-events-inmutables.md), [ADR-0011](ADR-0011-semantica-de-anclas-ante-ediciones.md), [ADR-0017](ADR-0017-validacion-del-contenido-de-las-ediciones.md), [ADR-0032](ADR-0032-varias-voces-huecos-y-plicas.md), [ADR-0033](ADR-0033-insertar-borrar-clave-y-armadura.md), [ADR-0034](ADR-0034-deshacer-y-rehacer-desde-la-vista.md), [ADR-0036](ADR-0036-capa-de-sugerencias-aprendida.md), [ADR-0037](ADR-0037-una-edicion-en-un-solo-viaje.md), [ADR-0044](ADR-0044-compas-con-su-simbolo-y-tresillos-como-edicion.md), [#243](https://github.com/sebdavid3/Cadenza/issues/243), [#183](https://github.com/sebdavid3/Cadenza/issues/183), [#188](https://github.com/sebdavid3/Cadenza/issues/188), [#241](https://github.com/sebdavid3/Cadenza/issues/241)

---

## Contexto

D61: la vista no cambia la figura de un acorde (ADR-0030 §2). Hechos comprobados en el código el 2026-11-01, sobre `dev` con #236 fusionado (`fca134f`):

- **Un acorde son varios eventos.** Una nota y las que la siguen en su voz con `is_chord`. El exportador los agrupa así y dibuja el acorde con la figura de su primera nota (`_build_voice_elements`); el mapa de tiempos, en cambio, da a cada nota su propia duración (todas atacan con la primera), y la reproducción de la web suena cada nota con la del mapa (`playback.ts`). El validador (`measure.balance`, `support`), el corpus de correcciones y los rasgos de la capa de sugerencias no cuentan la duración de las notas con `is_chord`.
- **`SetDuration` cambia un evento.** En la primera nota de un acorde cambia lo que se dibuja, pero las demás notas siguen sonando con la figura vieja; en otra nota no cambia nada de lo que se ve. Por eso ADR-0030 no lo ofrece en un acorde.
- **La importación da a todas las notas de un acorde la figura del acorde** (music21 guarda una duración por `Chord`). Un acorde con figuras distintas solo sale de ediciones hechas con la API (`InsertEvent` con `is_chord` y otra duración, o `SetDuration` en una de sus notas).
- **HOMR sí da acordes en un piano**: en la página 9 de *Mondnacht* de la verificación de ADR-0033, 123 y 75 notas con `is_chord` en los dos pentagramas. TS-04 del protocolo los tendrá.
- **`SetTuplet` (ADR-0044) ya fija las figuras de varios eventos seguidos** de una voz con `{"durations": [...]}`, de tipo «fijar», incluidas las notas de un acorde; no admite otra cosa que poner o quitar un tresillo de 3:2.
- **Lo que depende de `EditOp`** (ADR-0039 §3): `derive_edit_events` deriva del diff con la verdad las siete de contenido; la cobertura de `exp_02` es `len(op_counts) / len(CONTENT_EDIT_OPS)`; el corpus de correcciones de las sesiones compara el estado 0 con el final (`materialize`) y comprueba que `materialize(estado 0, derive_edit_events(...))` lo reproduce (`verified`).

## Decisión

### 1. Una operación nueva, no varias ediciones seguidas ni otro `SetDuration`

El criterio del issue es cambiar la figura de un acorde entero en una decisión y deshacerla de un paso. **Una operación nueva, `SetChordDuration`**:

- **Varias `SetDuration` seguidas** (una por nota) se descartan: deshacer de un paso necesitaría grupos en el log (ADR-0034 deshace de una en una, y ADR-0044 ya lo descartó para los tresillos), entre una y otra el `ScoreIR` tendría un acorde con dos figuras, y la orden podría quedarse a medias (un 409 o un 422 en la segunda).
- **Cambiar `SetDuration` para que en un acorde cambie todas sus notas** se descarta: cambiaría lo que significan las ediciones ya guardadas (la proyección del log es determinista y una `SetDuration` de un cliente de la API sobre una nota de un acorde se proyectaría distinto), deshacer no sería exacto con un acorde de figuras distintas (la instantánea de `SetDuration` tiene una sola duración) y `derive_edit_events`, que da una `SetDuration` por nota, dejaría de reproducir la verdad al materializarse en un acorde de figuras distintas. El corpus y los rasgos de la capa (`correction_corpus`, `learned.features`) dependen de esa reproducción; con una operación nueva no cambian (§3).

### 2. `SetChordDuration`

- **Ancla:** la primera nota del acorde (la que no lleva `is_chord`, o la primera nota tras un evento que no es nota: la agrupación del exportador). Una nota del acorde que no es la primera se rechaza («ánclalo en su primera nota»), como en `SetTuplet`.
- **`after`:** `{"durations": [d, ..., d]}`, una figura por nota del acorde, exactamente tantas como notas tiene, **todas iguales** (un acorde tiene una figura) y con las duraciones de ADR-0017 (`check_duration`); `null` se rechaza: solo lo escribe la compensatoria. Se rechazan también una nota sola y un silencio: su figura es `SetDuration`, y no hay dos formas de decir lo mismo en el log.
- **Tipo «fijar»** (ADR-0039 §1): el servidor guarda en `before` la figura de cada nota, con la misma forma, y la compensatoria intercambia los dos. Deshacer es exacto, también en un acorde de figuras distintas o de notas de adorno (vuelven a `null`); rehacer reenvía el `after`. No mueve ningún evento: no desplaza anclas (`translate_anchor`, `carryAnchor`).
- **Lo que no cambia:** las alturas, las ligaduras de prolongación, las marcas (las del acorde siguen en su primera nota) y los demás eventos de la voz. El compás puede quedar corto o largo: el validador lo señala al revalidar, como con `SetDuration`.
- Se implementa junto a `SetTuplet` (`meter_edits`): comparten la forma, la instantánea y la proyección (`_apply_durations`).

### 3. Política de `EditOp`: en `METER_EDIT_OPS`

ADR-0039 §3.7 pide clasificarla al crearla. **`SetChordDuration` entra en `METER_EDIT_OPS`**, que pasa a ser «el compás y las figuras de varios eventos a la vez» (tresillos y acordes), por las mismas razones que `SetTuplet` (ADR-0044 §4):

1. **`derive_edit_events` no la produce**: una figura de acorde mal leída sale del diff como una `SetDuration` por nota, que es lo que miden la SER y la cobertura. **`len(CONTENT_EDIT_OPS)` sigue siendo 7 y la cobertura de `exp_02` no cambia.**
2. **`DatasetBuilder`** no hace muestras de ella, y **`categorize_edit_op`** la llama `"meter"`, como a los tresillos.
3. **El corpus de correcciones y los rasgos de la capa no cambian.** `SetDuration` no cambia; ninguna sesión guardada ni ningún archivo de `data/` tiene la operación nueva; y una `SetChordDuration` deja exactamente el estado que dejarían las `SetDuration` de cada nota, así que el corpus de una sesión (estado 0 frente al final), su comprobación (`verified`, con una `SetDuration` por nota derivada) y los rasgos calculados sobre el estado son los mismos que si se hubiera corregido nota a nota (`test_a_chord_figure_edit_gives_the_corpus_and_features_of_one_set_duration_per_note`). `FEATURE_VERSION`, `CORPUS_FORMAT_VERSION` y `RULES_CATALOG_VERSION` no cambian, y no se ha ejecutado ningún experimento.
4. **Las métricas de esfuerzo del estudio** ([#188](https://github.com/sebdavid3/Cadenza/issues/188)) la cuentan como una intervención en el compás de su ancla, como las de su clase (ADR-0039 §3.6): cambiar la figura de un acorde de tres notas es una decisión, no tres.
5. No es de ninguna familia de sugerencias: la capa no la propone.

Una clase propia («figura de un acorde») se descartó: tendría exactamente el tratamiento de `METER_EDIT_OPS` en cada sitio que las distingue (la validación, la proyección, el `before` del cliente, el dataset y la categoría), con un caso más que mantener en cada uno.

### 4. Web: la figura en la barra «Corregir»

Mismo flujo que ADR-0030, ADR-0037 y ADR-0038: una edición por orden, con el valor final y el `base_seq` del estado que se ve, sin envío optimista.

- **La figura y el puntillo se ofrecen en cualquier nota de un acorde**, con los mismos botones y teclas (del 1 al 7 y el punto). Pulsado está el valor de la figura que se dibuja, la de su primera nota; el puntillo parte de ella. La orden es una `SetChordDuration` anclada en la primera nota con la figura para todas; la nota elegida sigue elegida (la edición no la mueve) y la barra dice «Guardado: figura negra en el acorde.». Si todas las notas tienen ya esa figura, no se envía nada: «El acorde ya tiene esa figura.».
- **Tras un 409**, «Volver a aplicar» pide la misma figura sobre lo que el evento sea en el estado recargado: el acorde entero (con las notas que tenga ahora) o, si ya no es un acorde, una `SetDuration`; y al revés, una figura pedida para una nota que ahora es de un acorde va al acorde entero.
- **La historia de ediciones** la dice «figura negra en el acorde» (compás y voz); deshacerla y rehacerla eligen la primera nota del acorde, como una edición de valor (ADR-0034 §7).
- La indicación bajo los controles dice que en un acorde la altura y la alteración son de cada nota y la figura, de todas a la vez. La barra no gana controles: la de #241 (compás y tresillos) no se toca.

### 5. Contrato y migración

Ampliación compatible del contrato v1: `EditOp` gana `SetChordDuration` en `openapi.json` y `types.ts` (regenerados), en la cola de PR tras #236. Ningún campo ni ninguna respuesta cambian. No hay migración: el log guarda `op` como texto y `before`/`after` como JSON.

## Consecuencias

### Positivas
- La figura de un acorde se corrige en una decisión, una edición y un paso de deshacer, desde cualquiera de sus notas, con el ratón, el dedo o el teclado.
- El dibujo, el mapa de tiempos, la reproducción y la exportación cuadran: todas las notas del acorde llevan la figura nueva.
- Deshacer es exacto aunque las notas tuvieran figuras distintas.
- Las cifras de `results/`, el corpus, los rasgos de la capa y `exp_02` no cambian; `SetDuration` tampoco.

### Negativas / Riesgos
- Hay dos operaciones de figura: `SetDuration` (un evento) y `SetChordDuration` (un acorde). Un cliente de la API puede seguir dejando un acorde con figuras distintas con `SetDuration` en una de sus notas, como antes.
- Las métricas de esfuerzo cuentan la figura de un acorde en la clase de compás y tresillos (`METER_EDIT_OPS`): quien las separe por clase debe saberlo.
- La primera nota de un acorde con más notas sigue sin borrarse desde la vista (ADR-0033 §4): lleva la figura y las marcas del acorde. Esa parte de D61 no la resuelve este ADR.
- No hay figura de un acorde con un tresillo desde la barra: `SetTuplet` (#241) cubre los tresillos, también los que contienen acordes.

## Alternativas consideradas

1. **Varias `SetDuration` seguidas.** Descartada (§1): deshacer no sería de un paso y la orden podría quedarse a medias.
2. **Un grupo de ediciones en el log.** Descartada, como en ADR-0044 (alternativa 1): un concepto nuevo para deshacer, rehacer y la historia.
3. **`SetDuration` que en un acorde cambia todas sus notas.** Descartada (§1): cambia el significado de ediciones ya guardadas, deshacer no es exacto y `derive_edit_events` dejaría de reproducir la verdad en un acorde de figuras distintas.
4. **`after: {"duration_beats": d}`** con la instantánea de las figuras de cada nota. Descartada: el `before` no tendría la forma del `after` y la compensatoria (`create_inverse_edit` intercambia los dos) necesitaría un caso propio.
5. **Admitir el ancla en cualquier nota del acorde.** Descartada: el ancla de la edición es la que la proyecta, y la primera nota es la que el exportador usa para el acorde (como `SetTuplet` y `SetNoteMarks`).
6. **Una clase propia de `EditOp`** o **`CONTENT_EDIT_OPS`.** Descartadas (§3): la primera repite el tratamiento de `METER_EDIT_OPS`; la segunda cambiaría la cobertura de `exp_02` («de 8») con una operación que `derive_edit_events` nunca produce.
