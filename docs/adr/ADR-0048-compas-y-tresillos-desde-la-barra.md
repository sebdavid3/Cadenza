# ADR-0048: Cambiar el compás y poner o quitar tresillos desde la barra de corrección

- **Estado:** Aceptado
- **Fecha:** 2026-11-01
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0011, ADR-0030, ADR-0033, ADR-0034, ADR-0037, ADR-0038, ADR-0039 y ADR-0044, CLAUDE.md §9)
- **Completa:** [ADR-0044](ADR-0044-compas-con-su-simbolo-y-tresillos-como-edicion.md) §6 («La barra para cambiar el compás y los tresillos es #241»)
- **Enmienda:** [ADR-0030](ADR-0030-correccion-de-altura-duracion-y-alteracion.md) §1 (una duración de tresillo ya no es «sin figura», §3 de este ADR)
- **Relacionado:** [ADR-0011](ADR-0011-semantica-de-anclas-ante-ediciones.md), [ADR-0033](ADR-0033-insertar-borrar-clave-y-armadura.md), [ADR-0034](ADR-0034-deshacer-y-rehacer-desde-la-vista.md), [ADR-0037](ADR-0037-una-edicion-en-un-solo-viaje.md), [ADR-0038](ADR-0038-redibujar-tras-una-edicion-y-ordenes-en-espera.md), [ADR-0039](ADR-0039-anadir-y-quitar-marcas-de-notacion.md), [#236](https://github.com/sebdavid3/Cadenza/issues/236), [#241](https://github.com/sebdavid3/Cadenza/issues/241)

---

## Contexto

#236 (ADR-0044) dejó en el contrato `SetTime` y `SetTuplet` y la historia de ediciones ya las dice, pero la barra «Corregir» no las pedía. Hechos comprobados en el código y contra la API real el 2026-11-01:

- `SetTime` va anclada al primer evento del compás, cambia desde él hasta el siguiente cambio (el **tramo**: los compases que llevan la misma indicación, métrica y grafía, o ninguna) en todos los pentagramas de la parte, admite `measures` y rechaza `time_signature: null` (422). Si los pentagramas de la parte no llevan la misma indicación en el compás, o no cambian en los mismos compases, 422.
- `SetTuplet` fija las figuras de n eventos seguidos de la voz del ancla: todas pasan por 2/3 (poner) o todas por 3/2 (quitar); una figura con puntillo por 2/3 sería otra sin tresillo y se rechaza; una nota de adorno lleva `null`; el tramo no empieza ni acaba a mitad de un acorde.
- `figureOf` (`edits.ts`) trataba una duración de tresillo como «sin figura»: la barra no pulsaba ninguna figura en una corchea de tresillo, y pulsar una figura la convertía en figura sin tresillo.
- `carryAnchor` (`edits.ts`) solo sabía que no mueven anclas las operaciones de valor, la clave, la armadura y las marcas: tras un `SetTime` o un `SetTuplet` (también deshechos o de otra pestaña) la nota elegida se olvidaba.
- La página del responsable de la Sonata *Claro de luna* (no se versiona): HOMR lee 3/2 donde hay ¢ y doce corcheas sin tresillo por compás; con ¢ y tresillos, la mano derecha de los compases 1 a 4 cuadra.

## Decisión

### 1. Grupo «Tresillo», bajo «Figura»

Tres botones de 44 px con texto breve (el nombre accesible, que empieza por él, y el `title` lo dicen entero), para que el grupo quepa en una fila a 390 px. Cada pulsación es **un `SetTuplet`**: una edición, un paso de deshacer.

| Botón | Nombre accesible | A qué eventos de la voz elegida, en su compás |
|---|---|---|
| «Tres» | Tresillo en tres figuras desde la elegida | Si la elegida no lo lleva, ella y las dos figuras siguientes; si lo lleva, se quita a **su grupo de tres** (las figuras con tresillo seguidas, de tres en tres desde la primera). |
| «Compás» | Tresillo en todo el compás | Todas. Si unas lo llevan y otras no, se pone a las que no, si van seguidas (HOMR lee a veces el «3» solo en el primer grupo); si no, se pide hacerlo por grupos. |
| «Tramo» | Tramo: tresillo desde el inicio hasta la elegida | Del inicio marcado (el «Inicio» de «Ligadura y regulador», ADR-0039) a la elegida, en el orden en que suenan; en la misma voz del mismo compás. |

- **Poner o quitar** lo decide lo que hay: si ninguna lo lleva se pone y, si todas, se quita. El botón está **pulsado** cuando su orden lo quitaría, como un conmutador de marcas (ADR-0039). Un tramo a medias se rechaza sin enviar nada.
- **Un acorde cuenta como una figura** y sus notas cambian con él; el tramo empieza en la primera nota del acorde de la elegida y acaba tras la última del último. Una nota de adorno no cuenta, lleva `null` y no cambia. El mensaje cuenta, como la historia de ediciones (ADR-0044 §6), los eventos cuya figura cambia: un acorde de dos notas son dos.
- **Un hueco de la voz** (silencio invisible, ADR-0032) no es una figura: «Compás» va de la primera figura a la última, así que el hueco con que entra una segunda voz se queda como está, y un hueco dentro del tramo se dice sin enviar nada.
- **Lo que el servidor rechazaría se dice antes**, en la región `aria-live` y sin enviar nada: una figura con puntillo («quítale antes el puntillo»), una que no es de un tresillo de 3:2 al quitarlo (2/9), una duración que el servidor no admite (ADR-0017), menos de tres figuras desde la elegida, un tramo a medias, «Tramo» sin inicio marcado. Por eso esos botones no se ven inactivos: pulsarlos (o R) dice por qué; solo se inactivan sin nota elegida o mientras no sale ninguna orden.
- **El ancla es el primer evento del tramo**; la selección no se mueve (ADR-0030 §6). Deshacer y rehacer eligen el primer evento del tramo, como un cambio de valor (ADR-0034 §7).
- Creado el tresillo desde el inicio, el inicio se olvida, como al crear una ligadura (ADR-0039).
- Quintillos, septillos y tresillos de otra proporción siguen siendo una figura por edición (ADR-0044 §3).

**Doce corcheas de un compás pasan a cuatro tresillos con dos acciones**: elegir una nota del compás y pulsar «Compás» (o Mayús+R).

### 2. Teclado

**R** pone o quita el tresillo de tres figuras desde la elegida (con Bloq Mayús también) y **Mayús+R**, el de todo el compás; con Ctrl, ⌘ o Alt no es de la vista. La leyenda de teclas lo dice. «Tramo» no tiene tecla: se alcanza con el tabulador, como la dinámica (ADR-0039 §4). El compás tampoco, como la clave y la armadura (ADR-0033 §2): es un cambio raro, de una vez por pieza.

### 3. La figura de una nota de tresillo (enmienda ADR-0030 §1)

`figureOf` reconoce la figura de tresillo (la duración por 3/2 es una figura de la barra): una corchea de tresillo pulsa «Corchea», y la barra de la selección ya la nombraba («corchea de tresillo»). **La figura conserva el tresillo**, como conserva el puntillo: «Negra» sobre una corchea de tresillo da una negra de tresillo (2/3). **El puntillo no se pone a una figura de tresillo** («quita antes el tresillo»): con él duraría lo que otra figura sin tresillo. Una duración que no es figura, con puntillo ni de tresillo (5/4, 2/9, una nota de adorno) sigue pasando a la figura elegida sin puntillo.

### 4. Grupo «Compás · compases a a b»

- Un desplegable con «C (4/4)», «¢ (2/2)» y las indicaciones con números más usadas (2/4 a 6/4, 2/2 a 4/2, 3/8, 5/8, 6/8, 7/8, 9/8 y 12/8) y «Cambiar». Si la que rige no está en la lista, se ofrece también. Como el de la armadura (ADR-0033 §1), el desplegable solo propone: propone la que rige el compás elegido y vuelve a ella al cambiar de compás o de indicación, sin montarse de nuevo, para que el foco siga en «Cambiar».
- Una pulsación es **un `SetTime` desde el compás elegido hasta el siguiente cambio**, sin `measures`: el rótulo dice el tramo («Compás · compases 1 a 11»), calculado como el servidor. C y 4/4 con números son la misma métrica pero no la misma grafía: pasar de uno a otro es una edición. Con la misma indicación y la misma grafía, «Cambiar» se ve inactivo, como el de la armadura (y tras un 409 se dice «El compás ya tiene esa indicación.»).
- Para quitar un cambio se pone la del compás anterior (ADR-0044 §2): no hay «sin indicación».
- Si los pentagramas de la parte no llevan la misma en el compás o no cambian en los mismos compases, pulsar «Cambiar» lo dice sin enviar nada.
- **Las figuras no cambian**, y se dice al guardar («Guardado: compás ¢ en los compases 1 a 11. Las figuras no cambian: revalida para ver los compases que no cuadran.»). No mueve la selección. Sus mensajes dicen el compás sin pentagrama ni voz, porque es de toda la parte; con varias partes, dicen cuál («parte 2, compás 3»).

### 5. 409, 422, órdenes en espera, deshacer y rehacer

Como ADR-0030, ADR-0037 y ADR-0038: una edición con el valor final y el `base_seq` del estado que se ve, sin envío optimista; el 201 trae el estado nuevo; una orden que llega mientras se guarda otra espera su turno; el 422 y los demás errores, con los mensajes de siempre. Tras un 409, «Volver a aplicar» pide **el mismo compás en el mismo compás**, con el tramo calculado de nuevo, y **el mismo tresillo con el mismo alcance** sobre la nota elegida (y el inicio) llevados al estado recargado; si ahora haría lo contrario (otra pestaña ya lo puso o lo quitó), no hay nada que volver a aplicar y se dice. Deshacer y rehacer, de un paso, por el log (ADR-0034).

### 6. Las anclas no se mueven

`SetTime` y `SetTuplet` se añaden a las operaciones que no desplazan anclas en `carryAnchor` (ADR-0011 §2, ADR-0044): la nota elegida, el inicio marcado y las sugerencias llevadas a otro estado siguen en su evento tras ellas.

### 7. Contrato

Sin cambios: la barra usa `SetTime` y `SetTuplet` tal como los dejó #236. No hay migración.

## Consecuencias

### Positivas
- La Sonata *Claro de luna* se corrige desde la vista, medido contra la API real con HOMR: «¢ (2/2)» y «Cambiar» en el compás 1 (una edición, compases 1 a 11, los dos pentagramas) y Mayús+R en cada uno de los compases 1 a 4 (una edición por compás). Revalidada, la mano derecha de los compases 1 a 4 no tiene ningún `measure.balance`; OSMD dibuja la ¢ y los corchetes con su «3»; el MusicXML lleva `<time symbol="cut">` y 48 `<time-modification>`; la reproducción sigue el mapa de tiempos (cada compás de los dos primeros, 2 s a 120 negras por minuto). Deshacer y rehacer, de un paso.
- Una nota de tresillo se ve como su figura y se corrige sin perder el tresillo.
- La selección ya no se pierde tras un cambio de compás o de tresillo, también deshecho o hecho en otra pestaña.

### Negativas / Riesgos
- El grupo de tres se cuenta por figuras, no por duración: en un tresillo de negra y corchea, «Tres» toma tres figuras (que pueden no ser el grupo); para eso está «Tramo».
- Quitar el tresillo con «Tres» parte la racha de tresillos de tres en tres desde su primera figura: si la lectura tiene un tresillo de otra forma, el grupo puede no ser el escrito (se ve en el mensaje y se deshace).
- La lista de compases no tiene todas las indicaciones posibles (11/8, 5/16…): la que rige se ofrece siempre, pero una nueva que no está en la lista no se puede poner desde la vista.
- `SetTime` no cambia las figuras: tras cambiar el compás, el validador señala al revalidar los compases que no cuadran.
- Un silencio invisible (ADR-0032) no se elige ni se borra desde la vista: en *Claro de luna*, HOMR deja uno de negra en la mano izquierda de los compases 3 y 4 y su `measure.balance` sigue (ADR-0033, consecuencias).
- La letra R ya no queda libre; «Inicio» sirve ahora también para el tramo del tresillo, aunque su nombre siga siendo el de la ligadura y el regulador.
- No está comprobado con un lector de pantalla real ni en un móvil físico; sí con la emulación del navegador a 1440 y 390 px.

## Alternativas consideradas

1. **Elegir el número de figuras del tresillo** (un desplegable 2, 3, 4…). Descartada: casi siempre son tres figuras o el compás entero, y un tramo distinto ya lo da «Tramo».
2. **Tresillos con el ratón arrastrando sobre las notas** (selección de rango). Descartada por ADR-0039 alternativa 7: cambiaría la selección de ADR-0027 y sus teclas.
3. **Un «Inicio» propio en el grupo «Tresillo».** Descartada: dos botones con la misma función confundirían, y el inicio es el mismo estado de la vista.
4. **Dos campos numéricos para el compás.** Descartada: dos valores que validar y un botón de símbolo aparte para algo que casi siempre es una de las dieciséis de la lista; la que rige se ofrece siempre.
5. **`SetTime` solo en el compás elegido** (`measures: 1`). Descartada: corregir una pieza leída con otro compás serían tantas ediciones como compases; el tramo lo dice el rótulo.
6. **Una tecla para el compás.** Descartada como la de la clave y la armadura (ADR-0033 §2).
7. **Que la figura sobre una nota de tresillo lo quite** (ADR-0030 tal cual). Descartada: corregir la figura de una nota de un tresillo es lo corriente, y perderlo descuadraría el compás.
