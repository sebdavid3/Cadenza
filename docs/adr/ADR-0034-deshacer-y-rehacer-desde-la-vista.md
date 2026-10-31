# ADR-0034: Deshacer y rehacer desde la vista de una sesión

- **Estado:** Aceptado
- **Fecha:** 2026-10-24
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0006, ADR-0007, ADR-0011, ADR-0017, ADR-0019, ADR-0030, ADR-0031, ADR-0032 y ADR-0033, CLAUDE.md §9)
- **Enmendado por:** [ADR-0037](ADR-0037-una-edicion-en-un-solo-viaje.md), que devuelve el estado nuevo con la respuesta de deshacer y de rehacer: ya no se pide aparte (§1 y «Sin cambios en el contrato ni en el backend»)
- **Relacionado:** [ADR-0006](ADR-0006-render-editor-osmd-verovio-zustand.md), [ADR-0007](ADR-0007-edit-events-inmutables.md), [ADR-0011](ADR-0011-semantica-de-anclas-ante-ediciones.md), [ADR-0017](ADR-0017-validacion-del-contenido-de-las-ediciones.md), [ADR-0030](ADR-0030-correccion-de-altura-duracion-y-alteracion.md), [ADR-0031](ADR-0031-marcas-de-notacion-en-el-score-ir.md), [ADR-0032](ADR-0032-varias-voces-huecos-y-plicas.md), [ADR-0033](ADR-0033-insertar-borrar-clave-y-armadura.md), [#185](https://github.com/sebdavid3/Cadenza/issues/185)

---

## Contexto

La vista de una sesión ya corrige la nota elegida con las siete operaciones del contrato ([#183](https://github.com/sebdavid3/Cadenza/issues/183), [#184](https://github.com/sebdavid3/Cadenza/issues/184)). ADR-0006 pide una pila de deshacer y rehacer alineada con los eventos, y ADR-0007, que deshacer y rehacer registren eventos nuevos sin borrar historia. Hechos comprobados en el código y contra la API real el 2026-10-24:

- `POST /sessions/{id}/undo` con `{"base_seq": n}` deshace la **última edición vigente**: el servidor recorre el log como una pila (`get_last_active_edit`), en la que cada edición compensatoria (`reverts_edit_id`) retira la que revierte, y registra la inversa (`create_inverse_edit`): borrar lo insertado, volver a insertar lo borrado con la instantánea de su `before` (marcas de ADR-0031 y `hidden` de ADR-0032 incluidos) y, en lo demás, volver al valor previo. Responde 200 con el `current_seq` nuevo y `undone_edit_id`. Con otro `base_seq`, 409; con la sesión finalizada, 409.
- Responde **422 por dos causas** que el `status` no distingue: no hay nada que deshacer (`NoEditsToUndo`) o la edición no guardó su estado previo completo (`has_complete_before`, ediciones anteriores a ADR-0017). La vista no muestra `detail` (ADR-0019).
- **No hay endpoint de rehacer.** El servidor guarda el `after` de cada edición tal como llegó y fija siempre el `before`; tras deshacer una edición, el estado es el previo a ella, de modo que su ancla vuelve a ser válida (ADR-0011).
- La API sobre SQLite devuelve `created_at` sin zona (`2026-10-24T17:25:27.538815`), aunque el servidor lo registra en UTC; leído tal cual, el navegador lo toma como hora local.

## Decisión

1. **Deshacer es `POST /undo`** con el `base_seq` del estado que se ve, sin envío optimista y sin otra orden mientras tanto: el mismo flujo que una corrección (ADR-0030 §4). Con el 200 se pide el detalle y, antes de mostrarlo, el MusicXML, los posibles errores y los tiempos de ese estado; la vista pasa a él de una vez.
2. **Rehacer es volver a enviar la última edición deshecha** como edición nueva: la misma operación, la misma ancla y el mismo `after`, con `before: null` (lo fija el servidor) y el `base_seq` actual. Ni caso de uso ni endpoint nuevos: el contrato v1 no cambia, y el servidor valida la edición como cualquier otra.
3. **Las pilas se leen del log** (`edits` de `GET /sessions/{id}`), no de la memoria de la pestaña (`readLog` en `pages/session/history.ts`). La de deshacer es la del servidor (la última vigente). La de rehacer recibe cada edición que deshace una compensatoria; una edición igual a la última de esa pila (operación, posición del ancla y `after` con las claves ordenadas) la rehace y la saca, porque deja el mismo estado que rehacerla; **cualquier otra la vacía**, porque lo deshecho ya no se aplicaría sobre su estado. Así la pila sobrevive a una recarga y sigue lo que se haga en otra pestaña: una edición hecha allí también la vacía.
4. **Controles: un grupo «Deshacer y rehacer»** al principio de la barra «Corregir», con dos botones de 44 px con su icono de píxel y su palabra a la vista, que no dependen de la nota elegida. Debajo, qué harían («Deshace: altura Re 4 (compás 2, voz 1).») o «Nada que deshacer ni rehacer.»; sin nada que hacer, o mientras hay una orden en curso, el botón está `aria-disabled` y su `title` lo dice. Los botones declaran `aria-keyshortcuts`: a diferencia de las teclas de ADR-0030, estas valen con el foco en ellos. El grupo también aparece si la partitura no se puede dibujar, para deshacer la edición que la dejó así.
5. **Teclado en toda la vista** mientras se pueda editar: Ctrl+Z o ⌘Z deshacen; Ctrl+Mayús+Z, ⌘Mayús+Z o Ctrl+Y rehacen (⌘Y no: es la historia del navegador en un Mac). En un campo de texto (`input` de texto, `textarea`, `contenteditable`) Ctrl+Z es el deshacer del navegador y la vista no lo toma. Con Alt no es de la vista (AltGr llega como Ctrl y Alt). La repetición automática no encadena órdenes. Sin nada que deshacer o rehacer, la tecla lo dice en la región `aria-live` («Nada que deshacer.»).
6. **Mensajes** con el verbo de cada orden: «Deshaciendo…», «Deshecho: altura Re 4 (compás 2, voz 1).», «Rehecho: …». Dicen dónde, porque lo que cambia puede no ser la nota elegida. El 409 recarga, distingue la sesión finalizada y **no se reintenta ni se ofrece volver a aplicar**: sobre el estado recargado, deshacer sería otra orden, y los botones ya dicen qué harían. El 422 al deshacer una edición sin estado previo tiene su mensaje («No se puede deshacer la edición 1 (…): es de antes de que el servidor guardara el estado previo de cada edición, y deshacerla alteraría la partitura. No se cambió nada.»); para elegirlo, el cliente mira el `before` de la edición como `has_complete_before`, pero no deja de enviarla: lo decide el servidor. Otro 422, «El servidor no aceptó deshacer (…): no se cambió nada.»; al rehacer, «… rehacer (…): no se guardó nada.». El 403, el 404, la red, el 5xx y el estado que no se carga, como en ADR-0030, con su verbo.
7. **Qué queda elegido** (ADR-0011, ADR-0033): el evento que cambia, para ver qué se deshizo o rehízo aunque esté en otro sistema; se trae a la vista y se anuncia (`placedBy`). Un cambio de valor deja elegido su evento; una inserción, el evento insertado; un borrado, el que ocupa su sitio (la regla de ADR-0033 §5); la clave y la armadura no mueven la selección. Se calcula sobre el estado en que se da la orden y se elige con el `seq` de la respuesta; si la persona eligió otra nota mientras se guardaba, se respeta. Si el evento ya estaba elegido y solo cambia de valor, no se vuelve a anunciar (ADR-0030 §10).
8. **Marcas y silencios invisibles.** La vista no recompone nada: muestra el estado que devuelve el servidor, cuya compensatoria lleva la instantánea con las marcas y `hidden`. Un silencio invisible nunca queda elegido: rehacer su inserción o deshacer su borrado no mueven la selección, y la regla del borrado lo salta. Los mensajes lo nombran («inserción de un silencio invisible de negra»), porque no se ve en la partitura.
9. **Historia de ediciones** en la columna de los posibles errores, también en solo lectura: cuántas hay y cuántas deshechas, y la lista plegada, de la más reciente a la primera, con su número, qué hace (una compensatoria, «Deshace la 5: …»; una edición que rehace otra, «Rehace la 3: …»), dónde y cuándo. Lo deshecho se tacha y lo dice con una etiqueta («Deshecha en la 6»), no solo con el estilo. La hora se lee en UTC aunque llegue sin zona (`parseUtc`).

## Consecuencias

### Positivas
- Se deshace y se rehace con el ratón, el dedo o el teclado, con el mismo control de concurrencia que las correcciones. Verificado contra la API real con HOMR (una melodía de 6 compases, un piano de 2 pentagramas y otra melodía de 4 compases transcritas en local) a 1440 y 390 px: deshacer un borrado devolvió la nota con su staccato (3 → 4 `<staccato>` en el MusicXML exportado); Ctrl+Mayús+Z, Ctrl+Z y Ctrl+Y con el teclado real; una edición nueva vació la pila de rehacer; Ctrl+Z en un campo de texto deshizo el texto sin tocar la sesión; un 409 de una edición hecha por la API antes de deshacer y otro de una sesión finalizada; un 422 de una edición sin `before` (puesta así en la base de prueba); un silencio invisible insertado y borrado por la API, rehecho y deshecho desde la vista sin quedar elegido, y de vuelta con `print-object="no"`. A 390 px, un toque en «Rehacer» dejó la página en el mismo `scrollY` y el foco en el botón.
- El log sigue siendo append-only y la pila es la del servidor: la vista nunca ofrece deshacer algo distinto de lo que deshace `POST /undo`.
- Sin cambios en el contrato ni en el backend.

### Negativas / Riesgos
- Una edición que rehace otra es una edición más, sin marca en el log: la vista la reconoce porque es igual a la deshecha, y una corrección manual igual a ella cuenta como rehacerla. Para las métricas de esfuerzo (D38, [#188](https://github.com/sebdavid3/Cadenza/issues/188)) hará falta decidir cómo contar las compensatorias y las que rehacen.
- La pila es de la sesión, no de la pestaña: Ctrl+Z puede deshacer una edición hecha en otra pestaña, si la vista ya la muestra (el botón dice cuál).
- Una edición sin estado previo (anterior a ADR-0017) impide deshacer más allá de ella: el botón sigue disponible y cada intento recibe el 422 con su mensaje.
- Deshacer o rehacer puede llevar la selección a otro sistema de la partitura (se trae a la vista).
- Descartar y restaurar posibles errores no se deshace desde aquí ([#186](https://github.com/sebdavid3/Cadenza/issues/186)).
- No está comprobado con un lector de pantalla real ni en un móvil físico; sí con la emulación táctil del navegador.

## Alternativas consideradas

1. **Un endpoint de rehacer** (`POST /redo`) o una referencia a la edición rehecha. Descartada: reenviar la edición basta, el servidor ya la valida y no cambia el contrato.
2. **La pila de rehacer en la memoria de la pestaña** (Zustand). Descartada: se pierde al recargar y no se entera de lo que se edita en otra pestaña; el log es la fuente de verdad.
3. **Deshacer en local, de forma optimista.** Prohibida por ADR-0007 y la guía de integración (§5.3).
4. **Ctrl+Z solo con el foco en la partitura.** Descartada: en un editor se espera en toda la vista; los campos de texto conservan el suyo.
5. **Desactivar deshacer si la edición no guardó su estado previo.** Descartada: lo decide el servidor (ADR-0017); el cliente solo elige el mensaje del 422.
6. **«Volver a aplicar» tras un 409 al deshacer o rehacer.** Descartada: sobre el estado recargado sería otra orden; los botones dicen qué harían ahora.
7. **Dejar la selección donde estaba.** Descartada: deshacer puede actuar lejos de la nota elegida, y elegir lo que cambia muestra qué se deshizo.
8. **La historia en una página o un diálogo aparte.** Descartada: en la columna lateral se consulta sin salir de la partitura.
