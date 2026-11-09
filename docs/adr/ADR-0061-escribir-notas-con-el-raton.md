# ADR-0061: Escribir notas con el ratón: el modo «Escribir» y la nota fantasma

- **Estado:** Aceptado
- **Fecha:** 2026-11-08
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0011, ADR-0017, ADR-0027, ADR-0030, ADR-0033, ADR-0038, ADR-0055 y ADR-0058, CLAUDE.md §9); el responsable eligió el 2026-11-08 qué hace el clic sobre una figura y entre dos (#350)
- **Enmienda:** [ADR-0058](ADR-0058-elegir-y-corregir-los-huecos-de-una-voz.md) §2 (`SetEventKind` se aplica también a un silencio que se ve, solo para escribir una nota en su lugar)
- **Relacionado:** [ADR-0027](ADR-0027-seleccion-de-notas-sobre-la-partitura.md), [ADR-0030](ADR-0030-correccion-de-altura-duracion-y-alteracion.md), [ADR-0033](ADR-0033-insertar-borrar-clave-y-armadura.md), [ADR-0038](ADR-0038-redibujar-tras-una-edicion-y-ordenes-en-espera.md), [ADR-0055](ADR-0055-ligaduras-de-prolongacion-y-notas-de-un-acorde.md), [#350](https://github.com/sebdavid3/Cadenza/issues/350), [#341](https://github.com/sebdavid3/Cadenza/issues/341)

---

## Contexto

Tras la mesa de corrección (#341), el responsable pidió que escribir fuera más intuitivo: poder corregir con clics además de con atajos, como en MuseScore o Flat, eligiendo la figura y viendo con el ratón, en modo fantasma, dónde caerá la nota antes de ponerla. Hasta ahora, la barra corregía la nota elegida: la altura por pasos (flechas u octavas), la figura con sus botones, insertar antes con N o S y añadir al acorde con E. Llevar una nota de Sol 4 a Re 5 eran cuatro pasos, y escribir una nota nueva, insertar y después subirla o bajarla.

Hechos comprobados el 2026-11-08 sobre `dev` (`354b8b3`):

- **La caja de cada compás** (`measureBox`, ADR-0021) sale del modelo de OSMD y abarca ocho espacios: dos por encima de la quinta línea, las cinco líneas y dos por debajo. Con ella se sabe en qué línea o espacio cae el puntero.
- **El modelo y el dibujo no siempre coinciden.** En TS-01 (en Sol mayor), en el segundo sistema la posición del modelo y la de las cabezas que dibuja VexFlow difieren en medio espacio: medida solo con el modelo, la nota del puntero salía un paso más alta. Las cabezas dibujadas sí están donde dice su altura.
- **Un silencio que se ve no se podía convertir en nota en una edición.** `SetEventKind` solo se aplicaba a un hueco (ADR-0058 §2), y `SetPitch` no se aplica a un silencio: escribir una nota en el lugar de un silencio eran dos ediciones (insertarla y borrar el silencio), con dos pasos de deshacer.
- **El ancho de la partitura cambiaba al abrir una leyenda.** En la mesa, si la barra crece y el panel de la partitura pasa a desplazarse, aparece su barra de desplazamiento: la partitura pierde ancho, el SVG de OSMD (con `max-width: 100%`) se encoge y, hasta que se vuelve a maquetar, las cajas medidas quedan desplazadas.

## Decisión

### 1. El modo «Escribir»

- **Un conmutador «Escribir»** en la primera fila de la barra de corrección, junto a «Atajos» (`aria-pressed`, `aria-keyshortcuts="W"`), y la tecla **W** con la partitura enfocada. Al entrar se abre la pestaña «Nota».
- **La figura y el puntillo de la barra eligen con qué se escribe** mientras dura el modo: no envían nada y se pueden pulsar siempre (también con las teclas 1 a 7 y el punto). El modo empieza con la figura de la nota elegida o, sin ninguna, con una negra.
- **Se sale** con el conmutador, con W, con **Esc** (antes que quitar la nota elegida; también con el foco en la barra, salvo en un campo o un diálogo) y al finalizar la sesión. Fuera del modo, la vista se comporta como antes: el clic elige.
- **La indicación** bajo los controles dice cómo se escribe: con el ratón o, en una pantalla táctil, con el dedo. La leyenda de teclas añade W y Esc.

### 2. La nota fantasma

Con el ratón o el lápiz, en el modo, el puntero lleva una **nota fantasma** sobre la partitura (una capa SVG que no recibe el puntero, por encima de las marcas): la cabeza (blanca en la blanca y la redonda), la plica (hacia arriba bajo la línea central y hacia abajo en ella y por encima; sin plica la redonda), los corchetes, el puntillo y las líneas adicionales que necesite, en violeta translúcido (pide una acción, DESIGN.md), con una etiqueta: «Sol4 · negra», «Insertar Sol4 · negra», «Sol4 al acorde» o, cuando el clic no escribiría, con filete discontinuo: «Espera: se está guardando» mientras se guarda otra corrección o hay una en cola, y «Ahora no se puede escribir» con el editor parado (un estado sin confirmar, una revalidación…). Mayús cambia el fantasma al acorde sin mover el ratón. La etiqueta no se lee (`aria-hidden`): el modo es para el puntero. El cursor es una cruz. Solo aparece sobre el estado que se ve dibujado: las anclas del mapa de notas son de ese estado.

### 3. Dónde cae el puntero

- **El pentagrama.** El compás cuya franja (de cuatro espacios por encima de la quinta línea a cuatro por debajo de la primera) contiene el punto; si hay varios, el de centro más cercano. Las líneas salen de su caja (un espacio es un octavo de su alto; la quinta línea, dos espacios bajo su borde) y se **ajustan con las cabezas dibujadas** del compás: la mediana de la diferencia entre donde está cada cabeza y donde debería estar por su altura y su clave. Un compás sin cabezas usa la caja tal cual.
- **La altura.** El punto se redondea a la línea o el espacio más cercano, hasta cuatro líneas adicionales por encima y por debajo. La altura es la nota de esa línea en la clave vigente del compás, con la alteración de la armadura vigente (`staffPitch`); otra alteración se pone después con su grupo. Sobre una nota, en su misma línea o espacio, se conserva su altura con su alteración: cambiar solo la figura de un Fa#4 en Do mayor no lo deja en Fa4.
- **La voz y la columna.** La voz es la del evento más cercano (en horizontal y, a igualdad, en vertical). Sus eventos se agrupan en columnas (las notas de un acorde forman una). Si el punto cae sobre una columna (su caja y 0,6 espacios a cada lado), apunta a ella: al evento de la columna más cercano en vertical. Si no, apunta a **insertar** antes de la columna siguiente (y antes de sus notas de adorno, que van con ella) o, tras la última, al final de la voz; la línea de inserción se dibuja en el hueco, a no más de dos espacios de la figura o de su primer adorno. **Ante un hueco no se inserta**: se escribe en él, como en la barra (ADR-0058 §4, «antes» y «en» son el mismo sitio). **En una voz con un solo silencio** (el de compás, en el centro), cualquier punto del compás escribe en él.

### 4. Qué hace el clic (decisión del responsable)

| Dónde | Qué se envía | Queda elegida |
|---|---|---|
| Sobre una nota | `SetPitch` si cambia la altura y `SetDuration` (o `SetChordDuration` en un acorde) si cambia la figura: hasta dos ediciones | la nota |
| Sobre un hueco | `SetEventKind` a nota (ADR-0058) y la figura si cambia | la nota escrita |
| Sobre un silencio que se ve | `SetEventKind` a nota (§5) y la figura si cambia | la nota escrita |
| Mayús + clic sobre una nota | `InsertEvent` de una nota con `is_chord` tras la última del acorde, con la figura del acorde (ADR-0055) | la nota añadida |
| Entre dos figuras, antes de la primera o tras la última | `InsertEvent` de una nota con la figura elegida en ese sitio (ADR-0033) | la nota nueva |

- **Cada orden es una edición**, con su `base_seq` y sin envío optimista (ADR-0030, ADR-0038). Cuando un clic da dos, la segunda espera su turno en la cola del editor y se vuelve a planear sobre la nota que dejó elegida la primera; cada una es un paso de deshacer. Sobre una nota va primero la altura; sobre un silencio o un hueco, primero la figura, para que la nota tome la elegida y un silencio importado con una figura que las ediciones no admiten no rechace la nota.
- **Lo que ya es así no se envía** (la misma altura y la misma figura; una altura que ya está en el acorde). **Lo que no se puede** (fuera del registro, una nota que se uniría a un acorde, un acorde sobre un silencio) lo dice el editor con sus mensajes, sin enviar nada.
- **El clic escribe lo que enseña el fantasma**: si el clic cae a no más de 1,5 px del último punto del puntero (aunque el fantasma no cambiara al pasar por él), se usa el fantasma que se ve. El navegador puede redondear de forma distinta el punto del clic y el del movimiento y, en el borde entre dos alturas, el clic daría la de al lado.
- **Mientras se guarda otra corrección**, hay una en cola o el editor está parado, el clic no escribe: el fantasma lo dice.
- **Con el dedo** no hay puntero que siga: el primer toque enseña el fantasma y el segundo, en el mismo sitio, escribe. Si el navegador no dice con qué puntero se hizo el clic, vale el del último `pointerdown`.

### 5. Dominio: un silencio que se ve pasa a ser una nota (enmienda ADR-0058 §2)

- `SetEventKind` se aplica a un **silencio**, se vea o no. Sobre un silencio que se ve solo admite escribir una nota (`{"kind": "note", "pitch": …, "hidden": false}`), con su misma figura: un silencio que se ve no pasa a ser un hueco (se borra o se cambia su figura) y escribir otro silencio no cambia nada (422 en los dos casos). Una nota sigue corrigiéndose con las demás operaciones. Lo demás de ADR-0058 §2 (la nota no se une a un acorde, la figura admitida, conserva las marcas) vale igual.
- **La compensatoria** devuelve el silencio que era: el `before` es `{"kind": "rest", "pitch": null, "hidden": false}`.
- **La historia** lo dice: «Sol 4 en lugar del silencio», y deshacerlo, «vuelta al silencio».
- **Política de `EditOp` sin cambios** (ADR-0058 §3): `SetEventKind` sigue en `GAP_EDIT_OPS`, fuera del dataset de la capa y de la cobertura de `exp_02`, y las métricas de esfuerzo la cuentan como contenido. El corpus de correcciones no cambia: `derive_edit_events` reproduce una sesión con una nota escrita sobre un silencio solo con operaciones de contenido (`test_a_shown_rest_written_as_a_note_keeps_a_session_verified`).
- **Contrato:** solo cambia la descripción de la operación en `openapi.json` y `types.ts` (regenerados); ningún campo ni ninguna respuesta. Sin migración.

### 6. La mesa reserva el hueco de las barras de desplazamiento

En la mesa (desde 960 px), el panel de la partitura y la partitura reservan desde el principio el hueco de su barra de desplazamiento (`scrollbar-gutter: stable`): abrir el modo o una leyenda ya no cambia el ancho de la partitura, que no se vuelve a maquetar ni deja las cajas desplazadas mientras tanto.

## Consecuencias

### Positivas
- Una nota se escribe con un clic donde va, con la altura y la figura que enseña el fantasma, y se ve antes de ponerla. Los atajos y la barra siguen igual.
- Escribir una nota en el lugar de un silencio es una edición y un paso de deshacer.
- Comprobado en local con la API real y el navegador (2026-11-08, TS-01 a 1600×1000): sobre las 17 cabezas, el fantasma da la altura de la nota (también en el segundo sistema, gracias al ajuste); el clic cambia altura y figura, inserta entre dos figuras y añade al acorde con Mayús, y todo se guarda.

### Negativas / Riesgos
- Las alteraciones fuera de la armadura (salvo la de la nota sobre la que se escribe, en su línea) y las notas de adorno no se escriben con el clic: se corrigen después con la barra. Las alteraciones accidentales anteriores del compás tampoco cuentan.
- En un compás con varias voces, la voz es la del evento más cercano: para escribir en otra hay que acercarse a sus figuras.
- Un compás sin cabezas dibujadas (solo silencios) usa la caja del modelo sin ajustar y puede dar un paso de diferencia donde el modelo y el dibujo no coinciden.
- Con Mayús, la figura elegida no cuenta: la nota añadida lleva la del acorde.
- No está comprobado con un lector de pantalla ni en un móvil físico (sí, la maqueta y la indicación, con la emulación del navegador a 375 px); el modo es para el puntero y la corrección con el teclado no cambia.
- Depende de que OSMD 2.2.1 y VexFlow dibujen las cabezas donde dice su altura y de la caja de compás de ADR-0021.

## Alternativas consideradas

1. **El clic sobre una nota solo cambia su altura.** Descartada por el responsable: la figura elegida también debe escribirse, como en los editores de partituras.
2. **El clic entre dos figuras no hace nada o corrige la más cercana.** Descartada por el responsable: entre dos figuras se inserta.
3. **Una nota en el lugar de un silencio borrando e insertando.** Descartada: dos ediciones y dos pasos de deshacer por una decisión (ADR-0058, Alternativa 1).
4. **`SetPitch` sobre un silencio lo convierte en nota.** Descartada por lo mismo que en ADR-0058 (Alternativa 2): cambia una operación de contenido que deriva `derive_edit_events` y mide `exp_02`.
5. **La altura solo con la caja del modelo.** Descartada: en el segundo sistema de TS-01 salía un paso más alta.
6. **Dibujar el fantasma en la partitura de OSMD.** Descartada: obligaría a volver a maquetar en cada movimiento; la capa propia no toca la partitura ni lo que se descarga.
