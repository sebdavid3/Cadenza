# ADR-0030: Corrección de la altura, la duración y la alteración de la nota elegida

- **Estado:** Aceptado
- **Fecha:** 2026-10-24
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0006, ADR-0011, ADR-0012, ADR-0014, ADR-0017, ADR-0019 y ADR-0027, CLAUDE.md §9)
- **Relacionado:** [ADR-0006](ADR-0006-render-editor-osmd-verovio-zustand.md), [ADR-0011](ADR-0011-semantica-de-anclas-ante-ediciones.md), [ADR-0012](ADR-0012-autenticacion-e-identidad.md), [ADR-0014](ADR-0014-ciclo-de-vida-de-la-sesion.md), [ADR-0017](ADR-0017-validacion-del-contenido-de-las-ediciones.md), [ADR-0019](ADR-0019-base-del-cliente-web.md), [ADR-0027](ADR-0027-seleccion-de-notas-sobre-la-partitura.md), [#182](https://github.com/sebdavid3/Cadenza/issues/182), [#183](https://github.com/sebdavid3/Cadenza/issues/183)

---

## Contexto

Con la selección de una nota ([#182](https://github.com/sebdavid3/Cadenza/issues/182), ADR-0027), la vista de una sesión ya da el ancla del evento elegido, relativa a un estado (`{ sessionId, seq, anchor }` en Zustand). Falta corregirlo con `POST /sessions/{id}/edits` y las operaciones `SetPitch`, `SetDuration` y `SetAccidental`. Hechos del contrato, comprobados en el código:

- El cuerpo es `{base_seq, op, anchor, before, after}` con `extra="forbid"` y el ancla completa. El 201 devuelve la edición guardada (con su `seq`), no la partitura: el estado nuevo se pide aparte.
- Una altura canónica es una letra de la A a la G, una alteración opcional (`#`, `##`, `b`, `bb`) y una octava de 0 a 9 dentro de MIDI 0–127 (`is_canonical_pitch`). `SetDuration` va en negras, mayor que 0 y como mucho 16, con denominador 2^a·t (t ∈ {1, 3, 5, 7}) de hasta 128, y vale también para silencios. `SetAccidental` conserva la letra y la octava; `null`, `""` o `"natural"` quitan la alteración.
- Con `before: null` el servidor guarda su instantánea (ADR-0017).
- El 409 tiene dos causas: `SequenceConflict` (se editó antes) y `SessionClosed` (sesión finalizada, ADR-0014). Solo edita el propietario: un investigador ante una sesión ajena recibe 403; un transcriptor, 404 (ADR-0012).
- Las teclas de la selección (#182) son ←/→ (con Ctrl o ⌘, de compás en compás), ↑/↓, Re Pág/Av Pág, Inicio/Fin y Esc. Alt+← es «atrás» en el navegador y Ctrl+↑, con o sin Mayús, es Mission Control en macOS.
- La vista se montaba de nuevo con cada `seq` (`key={seq}`): tras una edición se vaciaba la partitura mientras OSMD dibujaba la nueva, la página saltaba y el foco se perdía.
- El protocolo de esfuerzo (D38) cuenta las intervenciones por compás y las ediciones del log: la granularidad de las ediciones es parte de la medida.

## Decisión

1. **Controles: una barra «Corregir» bajo la de la selección**, con tres grupos de botones contiguos de 44 px (el conmutador del sistema) y su rótulo:
   - **Altura:** «Bajar un paso», «Subir un paso», «Bajar una octava» y «Subir una octava». El paso es diatónico **dentro de la armadura** del compás (la última que aparece hasta él en su pentagrama): la nota pasa a la línea o el espacio vecinos con la alteración que la armadura da a esa letra (Mi4 sube a Fa#4 en Sol mayor). Una alteración accidental no se arrastra. La octava conserva la letra y la alteración. No se ofrece subir o bajar un semitono: eso es cambiar la alteración, que tiene su propio control.
   - **Alteración:** doble bemol, bemol, becuadro, sostenido y doble sostenido. El becuadro se envía como `"natural"`.
   - **Figura:** de la semifusa a la redonda (siete figuras, las que aparecen en las sesiones reales medidas en ADR-0027, salvo la cuadrada) y el puntillo. La figura conserva el puntillo y el puntillo conserva la figura; una duración que no es una figura simple (un tresillo, una duración partida o una nota de adorno) pasa a la figura elegida sin puntillo.
   - El valor que ya tiene la nota es un botón pulsado (`aria-pressed`, bloque de tinta); lo que no se puede, `aria-disabled` con filete discontinuo. Iconos de píxel propios para las figuras, las alteraciones y la octava (de 8×12 los signos musicales, que necesitan la altura de una plica), con nombre accesible y `title`. En una partitura estrecha (menos de 34rem) la barra deja solo los iconos: a 390 px cada grupo cabe en una fila (la de figura y puntillo mide 331 px).
2. **Cada orden es una edición completa**, con el valor final: un paso, una figura o una alteración por clic o por tecla, una edición en el log. Antes de enviarla se comprueba lo que el servidor rechazaría (un silencio no tiene altura ni alteración, el registro de 0 a 9 y MIDI 0–127, una duración que no es figura no admite puntillo) y, si no se puede, se dice por qué en la región `aria-live` sin enviar nada. En un **acorde** no se cambia la figura: el exportador dibuja el acorde con la duración de su primera nota, y cambiar la de una nota sola daría un `ScoreIR` que no se ve; queda para cuando se pueda cambiar el acorde entero.
3. **Teclado sobre la partitura**, sin tocar las teclas de la selección: Mayús+↑/↓, un paso; Mayús+Re Pág/Av Pág, una octava; del **1 al 7**, la figura de semifusa a redonda (la numeración de MuseScore); el **punto**, el puntillo; **+ − =**, sostenido, bemol y becuadro (cuenta el carácter: llevan Mayús en unos teclados y no en otros). Con Ctrl, ⌘ o Alt nada es de la vista, para no quitar el zoom ni los atajos del sistema. Mantener una tecla pulsada no encadena ediciones (se ignora la repetición automática): cuántas salieran dependería de lo que tarde cada una en guardarse. La leyenda de teclas describe la partitura (los botones no declaran `aria-keyshortcuts`: esas teclas no valen con el foco en ellos); en una pantalla táctil la leyenda se oculta.
4. **Nada se da por guardado sin el 201, y sin envío optimista.** Mientras se guarda, la barra dice «Guardando…» y no sale otra orden (su `base_seq` dejaría de ser el del servidor). Tras el 201 se pide el detalle de la sesión y, antes de mostrarlo, el MusicXML, los posibles errores y el mapa de tiempos de ese estado; después la vista pasa a él de una vez (`setQueryData`). Hasta que la vista muestra el estado que se sabe que tiene el servidor no se edita.
5. **La partitura se redibuja sin vaciarse.** La vista ya no se monta de nuevo con cada `seq`: recibe un estado entero (MusicXML, `ScoreIR` y `seq`) y dibuja el nuevo con OSMD oculto encima del anterior, con su mismo ancho, y lo sustituye al terminar. Mientras tanto la marca de la nota elegida espera (es de otro estado) y no se elige sobre el dibujo viejo, pero lo que es la nota (la barra de la selección y la de corrección) ya sale del estado nuevo. La página no salta y el foco se queda donde estaba, en la partitura o en el botón pulsado. Si el estado nuevo no se puede dibujar, el anterior no se deja a la vista como si fuera este.
6. **La nota elegida sigue elegida** cuando la vista pasa a un estado posterior (una corrección, una recarga), con su ancla llevada a ese estado por la regla de desplazamiento de ADR-0011 §2: recorriendo en orden las ediciones de en medio, una inserción en su misma voz y compás, en su posición o antes, la retrasa una, y un borrado anterior la adelanta una; las demás operaciones no la mueven. Si se borró su evento, o una edición no se sabe desplazar, se olvida y se anuncia «Sin nota elegida.». Se traslada antes de pintar. Una selección de otro estado no se muestra (ADR-0027) y la barra de corrección pide elegir una nota.
7. **El 409 se recarga y nunca se reintenta solo.** La vista recarga la sesión y distingue las dos causas por su `status`, no por el texto de `detail`:
   - **Se editó en otra parte:** «No se guardó: altura Re 4 (compás 2, voz 1). La sesión cambió en otra pestaña o dispositivo antes de guardarlo; ya ves su estado actual.» Si el ancla se puede llevar al estado recargado (la misma regla) y el evento no tiene ya ese valor, se ofrece «Volver a aplicar»: una edición nueva, con el mismo valor final y el `base_seq` del estado recargado, que solo sale si la persona la pide (ADR-0011: el cliente recarga y reconstruye la edición). Si no, se dice por qué.
   - **La sesión está finalizada:** «… La sesión está finalizada y ya no admite correcciones.», y la vista queda en solo lectura.
8. **Los demás errores, con mensajes propios** y sin mostrar nunca `detail` (ADR-0019): el 422 (y cualquier otro rechazo del servidor), «El servidor no aceptó el cambio (…): no se guardó nada.»; el 403, que solo corrige quien hizo la transcripción, y no se envía nada más; el 404 lleva a «Sesión no encontrada». Sin respuesta (red, tiempo agotado) o con una que no lo confirma (5xx) no se sabe si se guardó: se dice así, distinguiendo los dos casos, no se edita encima y se ofrece «Recargar la sesión». Si el 201 llega pero el estado nuevo no se puede cargar, se dice que se guardó y se pide recargar. Una orden que no se puede (un silencio no tiene altura, la nota ya tiene ese valor) se dice sin borrar un aviso que hay que conservar, como el de un 409, y un rechazo repetido se vuelve a anunciar. La barra sigue a la vista aunque el estado nuevo no se pueda dibujar.
9. **Quién corrige.** La barra solo aparece si la sesión es de quien la ve y no está finalizada. Un investigador ante una sesión ajena la ve en solo lectura y la entradilla lo dice; las teclas de corrección no hacen nada (la API respondería 403). Una sesión finalizada también es de solo lectura hasta que se pueda reabrir ([#187](https://github.com/sebdavid3/Cadenza/issues/187)).
10. **Anuncios y foco.** El resultado de cada orden va en una región `aria-live` de la barra («Guardado: altura Sol sostenido 4.»), con las alturas dichas en solfeo. La selección no se vuelve a anunciar cuando la nota elegida cambia de valor: ya lo dice la barra. Si desaparece el control que tenía el foco («Volver a aplicar» al enviarse, «Recargar la sesión» al terminar, los botones cuando un 409 deja la sesión finalizada), el foco pasa a la partitura o, si no lo puede tomar, a los mensajes de la barra; nunca se queda en el documento.

## Consecuencias

### Positivas
- Se corrige con el ratón, el dedo o el teclado sin perder el sitio: medido contra la API real, una edición por teclado a 390 px dejó la página en el mismo `scrollY` y con la misma altura, y el foco en la partitura.
- El log separa las correcciones de altura (`SetPitch`) de las de alteración (`SetAccidental`), las dos categorías de error que distingue el validador, y cada edición es una decisión completa.
- El `base_seq` de cada edición es siempre el del estado que se ve, y un 409 nunca se convierte en una edición sobre otro estado sin que la persona lo vea y lo pida.
- La partitura, los posibles errores, la reproducción y la descarga pasan juntas al estado nuevo.
- Se prueba con Vitest: las reglas de altura, figura y alteración y el traslado del ancla, aparte; la vista, con el envío, el 201, el 409 de las dos causas, el 403, el 422, el error de red, el 201 sin estado nuevo, el teclado, el silencio y los casos de solo lectura.

### Negativas / Riesgos
- Una corrección de varios pasos son varias ediciones; si importa para el esfuerzo, [#188](https://github.com/sebdavid3/Cadenza/issues/188) puede agrupar las seguidas sobre la misma nota.
- El paso dentro de la armadura no acierta cuando la nota correcta lleva una alteración accidental: hace falta, además, cambiar la alteración (una segunda edición).
- La figura de un acorde no se cambia desde la vista. HOMR no dio acordes en las 99 sesiones medidas en ADR-0027.
- No hay doble puntillo ni cuadrada; una duración así se corrige a otra figura, pero no se crea.
- Tras editar, los posibles errores siguen siendo los de la última validación (el servidor no revalida al editar) y la lista lo dice; revalidar es [#186](https://github.com/sebdavid3/Cadenza/issues/186).
- Mientras OSMD dibuja el estado nuevo, la marca de la nota elegida desaparece un momento.
- No está comprobado con un lector de pantalla real ni en un móvil físico; sí con la emulación táctil del navegador.

## Alternativas consideradas

1. **Subir y bajar por semitonos, como MuseScore.** Descartada: duplica el control de alteración, mezcla en `SetPitch` correcciones que son de alteración y obliga a elegir una ortografía para cada semitono.
2. **Paso diatónico que conserva la alteración.** Descartada como regla por defecto: deja Fa natural en Sol mayor al subir desde Mi; el paso dentro de la armadura acierta con la nota de la escala, que es lo que más se corrige.
3. **Envío optimista** (mostrar el cambio y deshacerlo si falla). Descartada: el issue exige no dar nada por guardado sin el 201, y un 409 dejaría a la vista un estado que nunca existió.
4. **Reintentar el 409 con el `seq` nuevo.** Prohibido por ADR-0011: cambiaría el evento al que apunta el ancla.
5. **Un borrador de altura que se confirma con Intro.** Descartada: añade un modo y otra tecla para algo que casi siempre es un paso.
6. **Seguir montando la vista de nuevo con cada `seq`.** Descartada: vacía la partitura, la página salta y el foco se pierde en cada corrección.
7. **Mayús, Ctrl o ⌘ con ↑/↓ para la octava.** Descartada: Ctrl+↑ es Mission Control en macOS, también con Mayús.
