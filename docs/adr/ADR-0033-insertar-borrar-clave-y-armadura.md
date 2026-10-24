# ADR-0033: Insertar y borrar eventos, y cambiar la clave y la armadura desde la vista de una sesión

- **Estado:** Aceptado
- **Fecha:** 2026-10-24
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0010, ADR-0011, ADR-0017, ADR-0027, ADR-0030, ADR-0031 y ADR-0032, CLAUDE.md §9)
- **Relacionado:** [ADR-0010](ADR-0010-score-ir-atributos-y-exportacion.md), [ADR-0011](ADR-0011-semantica-de-anclas-ante-ediciones.md), [ADR-0017](ADR-0017-validacion-del-contenido-de-las-ediciones.md), [ADR-0027](ADR-0027-seleccion-de-notas-sobre-la-partitura.md), [ADR-0030](ADR-0030-correccion-de-altura-duracion-y-alteracion.md), [ADR-0031](ADR-0031-marcas-de-notacion-en-el-score-ir.md), [ADR-0032](ADR-0032-varias-voces-huecos-y-plicas.md), [#184](https://github.com/sebdavid3/Cadenza/issues/184)

---

## Contexto

La vista de una sesión ya corrige la altura, la duración y la alteración de la nota elegida ([#183](https://github.com/sebdavid3/Cadenza/issues/183), ADR-0030): cada orden es un `POST /sessions/{id}/edits` con el `base_seq` del estado que se ve, sin envío optimista, y el 409, el 422 y los demás errores tienen sus mensajes. Faltan las otras cuatro operaciones del contrato. Hechos comprobados en el código y contra la API real el 2026-10-24:

- `InsertEvent` inserta antes de la posición anclada (la posición puede ser también la siguiente al último evento de la voz) y exige `kind` y `duration_beats`, y `pitch` en una nota; admite `tie`, `is_chord`, `voice` (igual a la del ancla), las marcas de la nota (ADR-0031) y `hidden` en un silencio (ADR-0032). `DeleteEvent` lleva `after: null` y su instantánea guarda las marcas y `hidden`, para deshacer. Insertar y borrar desplazan las anclas siguientes de su voz y compás (ADR-0011 §2).
- `SetClef` y `SetKey` cambian un atributo del compás del ancla (`Measure.clef`, `Measure.key_signature`), que rige hasta el siguiente compás de su pentagrama que tenga el suyo; `{"clef": null}` y `{"key_signature": null}` quitan el cambio del compás. El servidor solo comprueba que el compás exista; ADR-0010 ancla estas ediciones al primer evento del compás. No tocan las notas: la altura de cada una sigue siendo la que era.
- HOMR escribe la clave y la armadura en el primer compás y donde cambian (en una página impresa de *Mondnacht*, la clave de fa también repetida en el compás 3); una melodía transcrita no traía armadura. En esa página hay acordes (123 y 75 notas con `is_chord` en los dos pentagramas del piano) y silencios invisibles.
- El exportador dibuja un acorde con la duración y las marcas de su primera nota, y agrupa como acorde una nota con las siguientes marcadas `is_chord`. Borrar esa primera nota dejaría la siguiente, con `is_chord`, unida a lo que la precede.
- OSMD 2.2.1, si el primer compás de una parte no tiene `<key>` (o `<clef>`), toma el primero que encuentra y lo dibuja desde el compás 1: comprobado en el navegador con el MusicXML exportado de una sesión real, una armadura de dos sostenidos puesta en el compás 2 salía en el compás 1, y sus notas con becuadros. Con `<key><fifths>0</fifths></key>` en el compás 1, sale en el 2.

## Decisión

1. **Controles: tres grupos más en la barra «Corregir»** (ADR-0030), con el mismo conmutador de 44 px:
   - **«Insertar antes o borrar»:** «+ Nota», «+ Silencio» y «Borrar» (un aspa de píxel). En una barra estrecha (menos de 34rem), «Borrar» queda en su aspa, con su nombre para el lector, y los tres caben en una fila a 390 px; «Nota» y «Silencio» se ven siempre, porque el más no dice qué se inserta.
   - **«Clave · compases 3 a 8»:** sol, fa, do en tercera y do en cuarta, con la que rige el compás pulsada. El rótulo dice hasta dónde llega una clave puesta en el compás elegido: hasta el anterior al siguiente cambio de su pentagrama, o el último.
   - **«Armadura · compases 3 a 8»:** un desplegable con las quince («7 bemoles» … «Sin alteraciones» … «7 sostenidos», lo que se cuenta en la imagen) y «Cambiar». El desplegable solo propone: con el teclado, cada flecha cambia su valor y cada valor no es una edición. Propone la armadura que rige el compás y vuelve a ella al cambiar el compás o su armadura, sin montarse de nuevo, para que el foco siga en «Cambiar» tras guardar.
2. **Teclado sobre la partitura**, sin tocar las teclas de la selección ni las de ADR-0030: **N** inserta una nota y **S** un silencio antes del evento elegido (con Mayús o sin ella), y **Supr** o **Retroceso** lo borran (en un Mac, la tecla de borrar es Retroceso). Con Ctrl, ⌘ o Alt nada es de la vista. La clave y la armadura no tienen teclas: son cambios raros, y sus controles se alcanzan con el tabulador.
3. **Insertar antes del evento elegido**, una edición con el valor final:
   - con la figura del evento elegido; si el servidor no la admitiría (una nota de adorno, sin duración, o un denominador que no es 2^a·t), una negra;
   - una nota, con la altura de la nota elegida; ante un silencio, la de la línea central de la clave que rige el compás, con la alteración de su armadura (Si4 en clave de sol, Re3 en la de fa), para corregirla después con un paso;
   - sin ligadura de prolongación, sin `is_chord`, sin marcas (añadirlas es [#214](https://github.com/sebdavid3/Cadenza/issues/214)) y sin `voice` en `after` (la fija el ancla); el ancla, sin `bbox` ni `confidence`;
   - ante una nota de un acorde, antes del acorde entero: entre dos notas de un acorde, la nueva partiría el acorde.

   No se ofrece insertar después: para añadir una nota al final de una voz se inserta una copia antes de la última y se corrige esta, las mismas ediciones que insertar después y corregir la nueva.
4. **Borrar el evento elegido** (`DeleteEvent`). La primera nota de un acorde con más notas no se borra, y la barra dice por qué («lleva su figura y sus marcas: borra antes las demás notas del acorde»); las demás notas del acorde, sí. Un silencio se borra, no se convierte en otro: borrar no es dejar un silencio, que es otra orden (S).
5. **Qué queda elegido tras guardar** (ADR-0011): tras insertar, el evento nuevo, para corregirlo enseguida; tras borrar, el evento que pasa a ocupar su sitio en la voz (el siguiente que se ve) o, si no hay, el anterior; si su voz se queda sin nada que se vea en el compás, el primero del compás siguiente de su pentagrama (de la misma voz o de la primera) o el último del anterior, como los movimientos de la selección; si no queda nada, ninguno. Se calcula sobre el estado en que se dio la orden con la regla de desplazamiento, y se elige con el `seq` del 201: si la vista pasa después a un estado posterior, se lleva a él como siempre (ADR-0030 §6). Solo se cambia si sigue elegido el evento sobre el que se dio la orden: lo que la persona eligiera mientras se guardaba se respeta. Con la misma ancla puede haber otro evento (borrar el elegido deja el siguiente en su posición): la selección guarda qué edición la dejó (`placedBy`) y la vista la anuncia y, si no se ve (un borrado puede dejarla en otro sistema), la trae a la vista como un movimiento con el teclado (`nearest`: si se ve, no se mueve nada). Si el 201 llega pero el estado nuevo no se puede cargar, la elige la recarga que se pide. La clave y la armadura no mueven la selección.
6. **La clave y la armadura del compás del evento elegido**, una edición por orden:
   - ancladas al primer evento del compás (ADR-0010), o a la posición 0 de la primera voz si no tiene eventos;
   - del pentagrama del evento elegido: en un piano, cada pentagrama se cambia por separado, como los guarda el `ScoreIR` y como los lee HOMR;
   - si la elegida es la que el compás trae de los anteriores y el compás tiene su propio cambio, se quita ese cambio (`{"clef": null}`, `{"key_signature": null}`) en lugar de escribir uno que no cambia nada; en el primer compás la clave se escribe siempre, y la armadura «sin alteraciones» es no tenerla, como la da HOMR;
   - la armadura conserva el modo de la que rige si es mayor o menor, los que admite el servidor (otro, como un dórico que music21 leyera, se omite);
   - **las notas conservan su altura**, y la barra lo dice al guardar («Guardado: clave de fa en los compases 2 a 6. Las notas conservan su altura.»): SetClef y SetKey solo cambian el atributo del compás.
7. **Marcas de notación (ADR-0031).** Las articulaciones y el calderón de una nota borrada se van con ella; la instantánea del servidor las guarda para deshacer ([#185](https://github.com/sebdavid3/Cadenza/issues/185)). Si la nota lleva el extremo de una ligadura de expresión cuyo otro extremo está en la parte, el otro se queda huérfano y la ligadura deja de dibujarse (ADR-0031 §5): se borra igual, sin pedir confirmación (no hay modos, y el borrado se deshace en el servidor), y la barra lo dice («Su ligadura de expresión ya no se dibuja.»). No se borra el otro extremo: sería editar un evento fuera del ancla. Las dinámicas y los reguladores son posiciones del compás: insertar o borrar no los mueve, se quedan en su tiempo y no se dice nada.
8. **Silencios invisibles y voces secundarias (ADR-0032).** Un silencio invisible no se elige, así que no se borra ni se inserta ante él desde la vista. Insertar antes de la nota que sigue a un hueco la inserta entre el hueco y la nota, y borrar esa nota deja el hueco donde estaba. Una voz secundaria se edita como la primera: el ancla lleva la voz del evento elegido; si se queda solo con silencios invisibles en un compás, deja de dibujarse en él y la selección pasa a otro evento (punto 5).
9. **409, 422 y los demás errores, como en ADR-0030.** Tras un 409, «Volver a aplicar» pide la misma edición sobre el estado recargado: insertar lo mismo antes del mismo evento en su posición nueva (y, como la primera vez, queda elegido el evento nuevo: también se lleva al estado recargado el evento elegido, que en un acorde no es el ancla de la inserción), borrar el mismo evento si sigue, y la clave o la armadura elegidas en el mismo compás, calculadas de nuevo (si ya las tiene, «El compás ya tiene esa clave.»). Los mensajes dicen el compás sin la voz cuando la edición es del compás: «No se guardó: clave de fa en los compases 2 a 6 (compás 2)».
10. **El primer compás para OSMD.** Antes de dibujar, `osmd.ts` escribe en el primer compás de cada parte `<key><fifths>0</fifths></key>` si no tiene armadura y otro compás sí, y la clave de sol en cada pentagrama que no tenga clave en el primer compás y sí en otro: sin ellas, OSMD dibuja desde el principio el primer cambio. Es lo que la vista ya entiende por un compás sin armadura o sin clave (`activeFifths`, `activeClef`). Solo cambia lo que se dibuja: la descarga es el MusicXML exportado tal cual, que ya era correcto.

## Consecuencias

### Positivas
- Se corrige una nota que falta o que sobra, y la clave o la armadura mal leídas, sin salir de la vista y con el ratón, el dedo o el teclado. Medido contra la API real con HOMR: una melodía de 6 compases, un piano de 4 y una página de *Mondnacht* de 34; inserción y borrado de notas y silencios con botones y con N, S, Supr y Retroceso, la clave de fa en los compases 2 a 6 y su vuelta con `{"clef": null}`, dos sostenidos desde el compás 2 y su vuelta con `{"key_signature": null}`, un 409 provocado con una inserción hecha fuera de la vista y su «Volver a aplicar» sobre la posición desplazada, un 422 del servidor, una nota con ligadura y una voz secundaria tras su hueco. A 390 px, insertar y borrar con un toque dejaron la página en el mismo `scrollY` y el foco en el botón.
- El log guarda cada decisión como una edición, con la operación del contrato que la expresa (D38).
- La selección sigue el trabajo: tras insertar, la nota nueva está lista para corregirla; tras borrar, la siguiente para seguir borrando.
- Una armadura o una clave puesta a mitad de una partitura que no tenía ninguna se dibuja en su compás.

### Negativas / Riesgos
- Cambiar la clave o la armadura no cambia la altura de las notas. Si HOMR leyó mal la clave, sus alturas también están mal (las calculó con ella) y se corrigen nota a nota; una operación que reinterprete las notas del compás conservando su línea sería un cambio del contrato.
- En un piano, la armadura de los dos pentagramas se cambia en dos ediciones.
- Un hueco (silencio invisible) no se puede quitar ni acortar desde la vista.
- La primera nota de un acorde solo se borra después de las demás (relacionado con D61).
- Borrar todos los eventos de un compás lo deja sin nada que elegir: desde la vista ya no se inserta en él hasta que se pueda deshacer ([#185](https://github.com/sebdavid3/Cadenza/issues/185)).
- Insertar puede sobrellenar un compás y borrar dejarlo corto: el validador lo señala al revalidar ([#186](https://github.com/sebdavid3/Cadenza/issues/186)).
- Insertar entre dos notas unidas por una ligadura de prolongación deja la ligadura entre la primera y la nueva, que no lleva su fin.
- En una partitura donde la selección no se ofrece (D62, como la página de *Mondnacht*), tampoco se inserta ni se borra.
- Una dinámica o un regulador pueden quedar sobre otra nota tras insertar o borrar: siguen en su posición del compás.
- No está comprobado con un lector de pantalla real ni en un móvil físico; sí con la emulación táctil del navegador.

## Alternativas consideradas

1. **Insertar después del evento elegido**, o en los dos sentidos. Descartada: para el final de una voz basta insertar antes y corregir la última, con las mismas ediciones; dos botones más por grupo no caben a 390 px.
2. **Borrar dejando un silencio en su lugar**, como MuseScore. Descartada: `DeleteEvent` quita el evento, y un silencio es otra decisión (otra edición); se hace con S y Supr.
3. **Confirmar antes de borrar una nota con marcas o con ligadura.** Descartada: añade un modo, y el borrado se deshace en el servidor con sus marcas (#185).
4. **Borrar también el otro extremo de la ligadura.** Descartada por ADR-0031 §5.
5. **La armadura con − y + (una quinta por pulsación).** Descartada: pasar de ninguna a cuatro sostenidos serían cuatro ediciones para una decisión.
6. **Enviar la armadura al cambiar el desplegable.** Descartada: con el teclado, el desplegable cambia de valor a cada flecha.
7. **Cambiar con la clave las alturas, para que las notas conserven su línea.** Descartada: SetClef no lo hace y serían tantas ediciones como notas.
8. **Cambiar la armadura en todos los pentagramas de la parte a la vez.** Descartada: una orden serían varias ediciones, que pueden fallar a medias.
9. **Escribir la armadura y la clave de partida en el exportador.** Descartada: el MusicXML exportado es correcto (sin armadura es sin alteraciones) y lo descargan otros programas; el problema es cómo lo interpreta OSMD.
10. **Prohibir insertar y borrar dentro de un acorde.** Descartada: borrar una nota sobrante de un acorde es una corrección corriente; solo la primera tiene el problema.
