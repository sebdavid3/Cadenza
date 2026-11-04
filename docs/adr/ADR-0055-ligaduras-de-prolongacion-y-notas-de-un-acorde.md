# ADR-0055: Poner y quitar ligaduras de prolongación y notas de un acorde

- **Estado:** Aceptado
- **Fecha:** 2026-11-01
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0007, ADR-0011, ADR-0017, ADR-0030, ADR-0032, ADR-0033, ADR-0034, ADR-0036, ADR-0037, ADR-0038, ADR-0039, ADR-0044 y ADR-0049, CLAUDE.md §9)
- **Completa:** [ADR-0033](ADR-0033-insertar-borrar-clave-y-armadura.md) §3 (insertar «sin ligadura de prolongación, sin `is_chord`») y §4 (la primera nota de un acorde no se borra: el resto de D61), y [ADR-0039](ADR-0039-anadir-y-quitar-marcas-de-notacion.md) §3.7 (clasificar cada operación nueva de `EditOp`)
- **Relacionado:** [ADR-0010](ADR-0010-score-ir-atributos-y-exportacion.md), [ADR-0026](ADR-0026-reproduccion-de-la-partitura-en-el-navegador.md), [ADR-0031](ADR-0031-marcas-de-notacion-en-el-score-ir.md), [ADR-0040](ADR-0040-catalogo-de-reglas-y-mensajes-en-lenguaje-musical.md), [ADR-0048](ADR-0048-compas-y-tresillos-desde-la-barra.md), [ADR-0050](ADR-0050-metricas-de-esfuerzo-de-la-correccion.md), [#312](https://github.com/sebdavid3/Cadenza/issues/312), [#243](https://github.com/sebdavid3/Cadenza/issues/243), [#247](https://github.com/sebdavid3/Cadenza/issues/247), [#252](https://github.com/sebdavid3/Cadenza/issues/252)

---

## Contexto

El banco del estudio (#247) pide una ligadura de prolongación en TS-03, y TS-04 tiene 111 acordes. La barra de corrección no puede poner ni quitar una ligadura de prolongación, ni añadir una nota a un acorde, ni borrar la primera nota de un acorde con más notas (D61, ADR-0033 §4). El responsable decidió el 2026-11-01 que entre antes del congelado (#252). Hechos comprobados en el código el 2026-11-01, sobre `dev` (`718720d`):

- **Una ligadura de prolongación es un valor de cada nota**, `Event.tie` (`start`, `continue`, `stop` o ninguno, ADR-0010): una ligadura entre dos notas son dos valores, uno en cada una, y las dos pueden estar en compases distintos y, al cruzar la barra, en voces con otro número (las voces se numeran en cada compás, ADR-0032 §3). El exportador escribe la ligadura de cada nota, también en las de un acorde; la regla `tie.resolution` (ADR-0040 §10) busca la nota de la misma altura en lo que sigue: en su voz dentro del compás o, al cruzar la barra, en lo que empieza el compás siguiente en cualquier voz. La reproducción de la web une las notas ligadas de la misma voz (`playback.ts`); dos notas ligadas a través de la barra en voces con distinto número sonaban dos veces.
- **Un acorde son varios eventos**: una nota y las que la siguen en su voz con `is_chord`. El exportador dibuja el acorde con la figura y las marcas de su primera nota, y la importación pone en ella las marcas del acorde (ADR-0031). El mapa de tiempos hace sonar cada nota del acorde con la primera y avanza con la figura de la primera.
- **`InsertEvent` ya admite `tie` e `is_chord`** en el servidor (ADR-0033 lo dice), pero no comprobaba dónde: una nota con `is_chord` tras un silencio, o un evento sin `is_chord` entre dos notas de un acorde, dejaban un `ScoreIR` que el exportador y el mapa de tiempos leen distinto (el silencio no forma acorde; el evento nuevo parte el acorde y las notas que siguen se pegan a él).
- **`DeleteEvent` de la primera nota de un acorde** se guardaba y dejaba la nota siguiente, con `is_chord`, pegada a lo que la precede (otra nota o acorde, o nada que la agrupe), sin la figura ni las marcas del acorde. La vista no lo ofrecía (ADR-0033 §4).
- **Lo que depende de `EditOp`** (ADR-0039 §3): `derive_edit_events` deriva del diff con la verdad las siete de contenido. Su alineación no sustituye una nota por otra con distinto `tie` o `is_chord` (coste infinito): esas diferencias salen como un borrado y una inserción con los valores de la verdad. Así, el corpus de una sesión (estado 0 frente al final) se reproduce (`verified`) aunque las correcciones se hicieran con otra operación. Las métricas de esfuerzo cuentan las intervenciones por tres clases: contenido, marcas y compás (ADR-0050, protocolo §3.4).

## Decisión

### 1. La ligadura de prolongación: una operación nueva, `SetTie`, de tipo «fijar»

Una ligadura son dos valores en dos notas que pueden estar en compases distintos: **una sola edición con sus dos extremos**, como una ligadura de expresión (ADR-0039 §1), para que se haga y se deshaga de un paso. `InsertEvent` y dos ediciones (borrar y volver a insertar cada nota) se descartan: serían cuatro ediciones por una decisión.

- **Ancla:** la nota donde empieza la ligadura (cualquier nota, también una de un acorde: la ligadura es de cada nota).
- **`after`:** `{"tie": t, "next": {"measure": m, "voice": v, "event_index": i, "tie": t2} | null}`, los valores finales de las dos notas: `t` el de la nota del ancla y `next` la otra nota, en el pentagrama del ancla, con su valor `t2`. Las claves son exactas y los valores, `"start"`, `"continue"`, `"stop"` o `null`.
- **Con `next`, pone o quita la ligadura entre las dos.** Cada valor se lee como dos marcas, «llega una ligadura» (`stop`, `continue`) y «sale una ligadura» (`start`, `continue`). El servidor exige que:
  - la otra nota sea **lo que sigue** a la nota del ancla: una nota del grupo siguiente de su voz (la nota o el acorde que empieza cuando acaba el suyo, sin contar las notas de adorno) o, si el suyo es el último de su voz en el compás, una nota del primer grupo de cualquier voz del compás siguiente de su pentagrama (que empieza con el compás); los silencios invisibles del final de su voz no cuentan, como en `tie.resolution`; las dos son notas con duración;
  - solo cambien «sale» en la nota del ancla y «llega» en la otra, las dos al mismo valor, y que algo cambie (no se guarda una ligadura que ya está, ni se quita una que no está);
  - al **poner** la ligadura, las dos tengan la **misma altura** (letra, alteración y octava); quitarla no lo exige, para poder quitar una ligadura cuya segunda nota ya se corrigió.
- **Sin `next` (`null`), solo quita marcas de la nota del ancla**: una ligadura que no llega a ninguna nota, o que llega sin salir de ninguna (lo que señala `tie.resolution`). Poner con una sola nota se rechaza, y quitar así una marca que tiene pareja (una nota con «llega» en lo que sigue, o con «sale» en lo que precede), también: se quita con ella.
- **Deshacer es exacto:** el servidor guarda en `before` los valores de las dos notas, con la misma forma, y la compensatoria intercambia los dos (`create_inverse_edit` no cambia). Rehacer reenvía el `after`. No mueve ningún evento: no desplaza anclas (`translate_anchor`, `carryAnchor`).
- Se implementa en `tie_edits` del dominio y entra por las funciones de `meter_edits`, como su clase (§4).

### 2. Añadir una nota a un acorde: `InsertEvent` con `is_chord`

Añadir una nota a un acorde, o a una nota sola para formar uno, es **insertar una nota con `is_chord: true`** tras la última nota del acorde: la operación existe, la deriva `derive_edit_events` y su compensatoria es borrarla (una nota de un acorde que no es la primera se borra con `DeleteEvent`). No hay dos formas de decir lo mismo en el log.

La validación de `InsertEvent` gana dos reglas que impiden un acorde que el exportador y el mapa de tiempos leerían distinto:

- una nota con `is_chord: true` va **justo tras otra nota** de su voz (en la posición 0 o tras un silencio se rechaza);
- una nota con `is_chord` no se añade a una nota de adorno (el acorde se dibujaría entero como adorno) ni lleva marcas (`articulations`, `fermata`, `slurs`): las del acorde van en su primera nota (ADR-0031);
- un evento **sin `is_chord` no se inserta entre las notas de un acorde** (antes de una nota con `is_chord` que sigue a otra nota): partiría el acorde. Antes del acorde entero, como inserta la vista (ADR-0033 §3), sí.

Ninguna sugerencia de las reglas ni de la capa propone una inserción así (`measure.balance` inserta al final de la voz), así que lo que la capa propone y mide (`exp_14`) no cambia. La figura de la nota nueva no se comprueba frente a la del acorde, como antes (ADR-0049, Negativas): la vista envía la del acorde.

### 3. Quitar una nota de un acorde, también la primera: `DeleteEvent` con `{"keep_chord": true}`

Una nota de un acorde que no es la primera se borra como hasta ahora (`DeleteEvent`, `after: null`). **La primera se borra con `after: {"keep_chord": true}`**: el acorde se conserva sin ella y **la nota siguiente pasa a ser la primera**, con la figura y las marcas del acorde (las articulaciones, el calderón y los extremos de ligadura de expresión de la que se borra) y sin `is_chord`. Su ligadura de prolongación es suya y no cambia. Con dos notas, la que queda es una nota sola con la figura y las marcas que tenía el acorde.

- **Validación:** `keep_chord` solo vale `true`, solo en la primera nota de un acorde de dos o más notas (agrupadas como el exportador), y **la primera nota de un acorde ya no se borra con `after: null`**: lo que dejaba era un acorde que no se dibuja como se guarda. La vista nunca lo envió, ni lo proponen las sugerencias (las reglas y la capa excluyen borrar notas de acordes).
- **Instantánea:** el `before` es el de cualquier borrado (la nota con sus marcas, ADR-0031) más `"next_in_chord": {"duration_beats", "articulations", "fermata", "slurs"}`, lo que tenía la nota siguiente como nota del acorde. `has_complete_before` lo exige cuando el `after` lleva `keep_chord`.
- **Deshacer** registra, como siempre, un `InsertEvent` con el `before` del borrado: inserta la primera nota y devuelve la siguiente a nota del acorde con lo que tenía (`next_in_chord`). Es exacto. Un cliente no puede enviar `next_in_chord` en un `InsertEvent` (422): solo lo escribe la compensatoria, como el `null` de `SetTime` (ADR-0044). Rehacer reenvía el `DeleteEvent` con su `after`.
- **Las anclas se desplazan como en cualquier borrado** (ADR-0011 §2): la primera nota desaparece y la siguiente ocupa su posición. `translate_anchor`, `origin_anchor`, `carryAnchor` y la historia no cambian, y la compensatoria es un `InsertEvent`.
- `DeleteEvent` sigue siendo una operación de contenido: el dataset, la cobertura y las métricas de esfuerzo la cuentan como un borrado, que es la decisión de quien corrige.

### 4. Política de `EditOp`: `SetTie` en `METER_EDIT_OPS`

ADR-0039 §3.7 pide clasificar cada operación nueva. **`SetTie` entra en `METER_EDIT_OPS`**, que pasa a ser «el compás y la duración de varios eventos a la vez»: una ligadura de prolongación suma las figuras de dos notas en un solo sonido, como el tresillo cambia las de un tramo y la figura de un acorde las de sus notas. Por las mismas razones que `SetTuplet` y `SetChordDuration` (ADR-0044 §4, ADR-0049 §3):

1. **`derive_edit_events` no la produce**: una ligadura mal leída sale del diff como un borrado y una inserción de cada nota (la alineación no sustituye notas con distinto `tie`). **`len(CONTENT_EDIT_OPS)` sigue siendo 7 y la cobertura de `exp_02` no cambia.** Las otras dos órdenes (§2 y §3) son `InsertEvent` y `DeleteEvent`: tampoco cambian la cuenta.
2. **`DatasetBuilder`** no hace muestras de ella y **`categorize_edit_op`** la llama `"meter"`.
3. **El corpus de correcciones y los rasgos de la capa no cambian**: no se toca `derive_edit_events`, ni los rasgos, ni `CORPUS_FORMAT_VERSION`, `FEATURE_VERSION` o `RULES_CATALOG_VERSION`; ninguna sesión guardada ni ningún archivo de `data/` tiene `SetTie` ni los `after` nuevos. Una sesión corregida con estas órdenes se sigue reproduciendo al derivar (`verified`): la ligadura y la nota añadida salen como inserciones con su `tie` y su `is_chord`, y la primera nota quitada, como la nota de la siguiente altura en su sitio y el borrado de la siguiente (`test_tie_and_chord_edits_keep_a_session_verified`). No se ha ejecutado ningún experimento.
4. **Las métricas de esfuerzo del estudio** la cuentan como una intervención en el compás de su ancla, en la clase `"meter"`: siguen siendo tres clases (protocolo §3.4). Añadir o quitar una nota de un acorde cuenta como contenido, como cualquier inserción o borrado.
5. No es de ninguna familia de sugerencias: la capa no la propone.

`MARK_EDIT_OPS` se descartó: sus ediciones no cambian lo que miden los experimentos (ADR-0031 §6), y una ligadura sí (la alineación las compara). Una clase propia añadiría una cuarta clase a las métricas de esfuerzo que el protocolo ya fijó.

### 5. Web: el grupo «Acorde y prolongación» de la barra

Mismo flujo que ADR-0030, ADR-0037 y ADR-0038: una edición por orden, con el valor final y el `base_seq` del estado que se ve, sin envío optimista; 409, 422 y los demás errores con sus mensajes, y «Volver a aplicar» tras un 409.

- **«Acorde»** (+, «Añadir una nota al acorde») y la tecla **E**: inserta una nota con `is_chord` tras la última nota del acorde de la elegida (o tras la elegida, si es una nota sola), con la figura del acorde y **una tercera por encima de su nota más aguda** dentro de la armadura (dos pasos diatónicos, como Mayús+↑ dos veces), o por debajo de la más grave si se sale del registro. La nota nueva queda elegida para corregir su altura con un paso. En un silencio o en una nota de adorno no se ofrece.
- **«Ligar»** («Ligar con la siguiente») y la tecla **U**: un conmutador pulsado si la nota elegida empieza una ligadura. Sin pulsar, pone la ligadura hasta la nota de la misma altura que la sigue (en su voz o, al cruzar la barra, la de su voz primero); si no la hay, dice por qué («Lo siguiente no es un Do 4…»). Pulsado, quita la ligadura que sale de ella con la otra nota o, si no llega a ninguna, solo la suya. La selección no se mueve.
- **«Quitar la ligadura que llega»** aparece bajo los botones cuando a la nota elegida le llega una ligadura: la quita con su nota de origen (una edición anclada en ella) o, si no viene de ninguna, solo la marca de la elegida.
- **«Borrar»** y Supr/Retroceso **borran cualquier nota de un acorde**: la primera con `keep_chord`, y la siguiente queda elegida (ocupa su sitio). Ya no hay rechazo «borra antes las demás notas».
- **Tras un 409**, «Volver a aplicar» pide lo mismo sobre el estado recargado: la nota añadida tras el mismo acorde, poner o quitar la misma ligadura desde la nota elegida llevada a él (si ya está como se pedía, lo dice), y borrar la misma nota (con `keep_chord` si ahora es la primera de un acorde).
- **La historia** las dice: «inserción de Mi 4 en el acorde», «borrado de Do 4 del acorde», «ligadura de prolongación hasta el compás 4», «quitar la ligadura de prolongación». Deshacer y rehacer eligen como cualquier inserción, borrado o cambio de valor (ADR-0034 §7); la ligadura no mueve la selección.
- **La indicación** bajo los controles en un acorde dice que al borrar su primera nota la siguiente lleva la figura y las marcas.
- **La reproducción** une también dos notas ligadas a través de la barra en voces con distinto número (misma parte, pentagrama y altura, la segunda empieza su compás cuando acaba la primera); dentro de un compás, solo las de la misma voz.

### 6. Contrato y migración

Ampliación compatible del contrato v1: `EditOp` gana `SetTie` en `openapi.json` y `types.ts` (regenerados). `DeleteEvent` admite además `after: {"keep_chord": true}`; `InsertEvent`, las dos reglas de §2. Los rechazos nuevos (la primera nota de un acorde con `after: null`, y las inserciones que parten un acorde) son de ediciones que la vista nunca envió y que dejaban un `ScoreIR` incoherente. Ningún campo ni ninguna respuesta cambian. No hay migración: el log guarda `op` como texto y `before`/`after` como JSON.

## Consecuencias

### Positivas
- La ligadura de TS-03 y los acordes de TS-04 se corrigen desde la barra, con el ratón, el dedo o el teclado, y cada orden es una edición y un paso de deshacer.
- La primera nota de un acorde se borra como cualquier otra, y el acorde conserva su figura y sus marcas: D61 queda resuelta.
- Las cifras de `results/`, el corpus, los rasgos de la capa y la cobertura de `exp_02` no cambian; las métricas de esfuerzo siguen con tres clases.
- El servidor ya no guarda inserciones ni borrados que parten o descolocan un acorde.

### Negativas / Riesgos
- Un `DeleteEvent` con `after: null` en la primera nota de un acorde, o una inserción que parte un acorde, que antes se guardaban, ahora son un 422. Ningún cliente conocido los envía.
- `DeleteEvent` y su compensatoria tienen ahora dos formas: con `keep_chord` (y `next_in_chord` en el `before`) proyectan además un cambio en la nota siguiente. Quien lea el log debe mirar el `after` del borrado.
- `SetTie` lleva en `after` la posición de la otra nota en un estado concreto: es correcta para la proyección y para deshacer (el log es una pila), como los extremos de una ligadura de expresión (ADR-0039, Negativas).
- Las métricas de esfuerzo cuentan una ligadura de prolongación en la clase del compás y los tresillos (`"meter"`): quien las separe por clase debe saberlo.
- Desde la vista no se liga una nota con otra que no sea lo que la sigue (una ligadura entre pentagramas, o a una nota más adelante), ni una nota de adorno.
- Borrar la nota donde empieza o acaba una ligadura de prolongación deja a la otra con la marca: `tie.resolution` la señala y se quita con «Ligar» o «Quitar la ligadura que llega».
- No está comprobado con un lector de pantalla real ni en un móvil físico; sí con la emulación del navegador a 1440 y 390 px.

## Alternativas consideradas

1. **Una operación nueva para quitar la primera nota de un acorde** (y otra, o la misma con otro `after`, para su compensatoria). Descartada: un borrado es un `DeleteEvent`, que ya desplaza las anclas y ya se cuenta como contenido; una operación nueva cambiaría la cobertura de `exp_02` o habría que enseñar su desplazamiento a `translate_anchor`, `origin_anchor`, `carryAnchor` y la historia.
2. **Cambiar lo que hace `DeleteEvent` con `after: null` en la primera nota de un acorde.** Descartada: cambiaría lo que significan ediciones ya guardadas y las que deriva `derive_edit_events`, y el corpus dejaría de reproducirse igual.
3. **Una operación que fija las notas de un acorde** (`{"notes": [...]}`). Descartada: cambia el número de eventos de la voz, así que desplazaría anclas según su `after`, y añadir una nota ya es un `InsertEvent`.
4. **La ligadura como dos ediciones** (una por nota) o con `InsertEvent` y `DeleteEvent`. Descartada: una orden serían varias ediciones que pueden fallar a medias.
5. **Que el servidor busque la otra nota de la ligadura** (`{"tied": true}`). Descartada: deshacer no sería exacto si la otra nota ya tenía una marca suelta, y el `after` dejaría de ser el valor final que se guarda (ADR-0017).
6. **`SetTie` en `MARK_EDIT_OPS`, o en una clase propia.** Descartadas (§4).
7. **Comprobar en `InsertEvent` que la nota añadida a un acorde tiene su figura.** Descartada: `SetDuration` ya puede dejar un acorde con figuras distintas (ADR-0049) y la vista envía la del acorde.
