# ADR-0039: Añadir y quitar marcas de notación, y la política de `EditOp` para el dataset y las métricas

- **Estado:** Aceptado
- **Fecha:** 2026-10-31
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0002, ADR-0007, ADR-0011, ADR-0017, ADR-0030, ADR-0031, ADR-0033, ADR-0034, ADR-0036, ADR-0037 y ADR-0038, CLAUDE.md §9)
- **Completa:** [ADR-0031](ADR-0031-marcas-de-notacion-en-el-score-ir.md) §4 («No hay operaciones para añadir ni quitar marcas: es #214») y §5 (limpiar los extremos huérfanos)
- **Relacionado:** [ADR-0007](ADR-0007-edit-events-inmutables.md), [ADR-0011](ADR-0011-semantica-de-anclas-ante-ediciones.md), [ADR-0017](ADR-0017-validacion-del-contenido-de-las-ediciones.md), [ADR-0030](ADR-0030-correccion-de-altura-duracion-y-alteracion.md), [ADR-0033](ADR-0033-insertar-borrar-clave-y-armadura.md), [ADR-0034](ADR-0034-deshacer-y-rehacer-desde-la-vista.md), [ADR-0036](ADR-0036-capa-de-sugerencias-aprendida.md), [ADR-0037](ADR-0037-una-edicion-en-un-solo-viaje.md), [ADR-0038](ADR-0038-redibujar-tras-una-edicion-y-ordenes-en-espera.md), [#214](https://github.com/sebdavid3/Cadenza/issues/214), [#236](https://github.com/sebdavid3/Cadenza/issues/236), [#243](https://github.com/sebdavid3/Cadenza/issues/243), [#188](https://github.com/sebdavid3/Cadenza/issues/188), [#262](https://github.com/sebdavid3/Cadenza/issues/262)

---

## Contexto

Con #213 (ADR-0031) el `ScoreIR` guarda y la vista dibuja las articulaciones, los calderones, las ligaduras de expresión, las dinámicas y los reguladores, pero ninguna operación de `EditOp` los añade ni los quita: solo se conservan al editar y al deshacer. HOMR 0.7.0 no reconoce dinámicas ni reguladores y su reconocimiento con Audiveris queda fuera de la entrega ([#262](https://github.com/sebdavid3/Cadenza/issues/262), INV-0002): ponerlos a mano es la única vía. Hechos comprobados en el código el 2026-10-31:

- `EditOp` tenía siete operaciones. Las anclas son rutas lógicas con un `event_index` por voz y compás (ADR-0002) que solo desplazan `InsertEvent` y `DeleteEvent` (ADR-0011 §2, `translate_anchor`, `carryAnchor` en la web). Una edición lleva una sola ancla.
- Una marca se pega a tres sitios (ADR-0031 §2): a una nota (`Event.articulations`, `Event.fermata`), a una posición del compás (`Measure.dynamics`), o a dos puntos que pueden estar en compases, sistemas y pentagramas distintos, identificados por un `number` libre en la parte (`Event.slurs`, `Measure.wedges`).
- El servidor valida `after` (`validate_after`) y fija `before` (`snapshot_before`, ADR-0017); la compensatoria intercambia `before` y `after` salvo en `InsertEvent` y `DeleteEvent` (`create_inverse_edit`, ADR-0007). Deshacer aplica la compensatoria sin volver a validarla. Rehacer reenvía la edición deshecha tal cual (ADR-0034).
- **Lo que depende de `EditOp` fuera del editor**, y cuyos resultados en `results/` son evidencia de la tesis (CLAUDE.md §8):
  - `derive_edit_events` (`cadenza.learning.alignment`) deriva del diff con la verdad solo las siete de contenido; las marcas no entran en la alineación (ADR-0031 §6). `count_edits_by_op` cuenta esas siete.
  - `exp_02` calcula la cobertura de operaciones de un lote como `len(op_counts) / len(EditOp)`: añadir miembros a `EditOp` cambiaría esa cifra sin que cambie nada medido.
  - `DatasetBuilder` convierte cada edición vigente de una sesión finalizada en una muestra (`TrainingSample`); `compute_correction_magnitude` da 1.0 a una operación que no conoce.
  - `test_edit_event.py` fija el conjunto de `EditOp`.
  - El corpus de correcciones (#255), la capa de sugerencias (#256, ADR-0036) y su medición (#257) comparan el estado 0 con el final (`materialize` + `derive_edit_events`) y solo proponen las operaciones de su familia.
  - `categorize_edit_op` clasifica las ediciones derivadas para la cobertura del validador.

## Decisión

### 1. Cuatro operaciones de tipo «fijar»

`EditOp` gana cuatro operaciones. Todas fijan un valor completo: el `after` es el estado final de lo que tocan, el servidor guarda en `before` el estado que sustituyen, con la misma forma, y la compensatoria intercambia los dos (`create_inverse_edit`, sin cambios). Ninguna mueve un evento: no desplazan anclas.

| Operación | Ancla | `after` (y `before`, con la misma forma) |
|---|---|---|
| `SetNoteMarks` | el evento | `{"articulations": [...], "fermata": bool}`: todas sus articulaciones, sin repetir, del vocabulario de ADR-0031, y su calderón |
| `SetDynamic` | el compás (como `SetClef`, ADR-0010) | `{"offset_beats": "1/2", "mark": "mf" \| null}`: la dinámica de esa posición del compás, o ninguna |
| `SetSlur` | el evento del inicio (o, si no lo hay, el del fin) | `{"number": n, "start": {"staff", "measure", "voice", "event_index"} \| null, "stop": {…} \| null}` |
| `SetWedge` | el compás del inicio (o del fin) | `{"number": n, "start": {"staff", "measure", "offset_beats", "type": "crescendo" \| "diminuendo"} \| null, "stop": {"staff", "measure", "offset_beats"} \| null}` |

- **Por qué cuatro y no una por marca y acción** (`AddSlur`/`RemoveSlur`…): una operación «fijar» se deshace intercambiando `before` y `after`, como las de valor, y rehacer reenvía la misma. Cuatro clases de sitio, cuatro operaciones.
- **Una ligadura o un regulador es una edición con sus dos extremos**, aunque estén en compases o pentagramas distintos: los extremos van en `after`, con la forma de un ancla (sin la parte, que es la del ancla). Con los dos, la edición **crea** la marca; con los dos a `null`, la **quita entera**: sus dos extremos o el que quede de un huérfano (ADR-0031 §5). La compensatoria de quitar un huérfano lo devuelve solo (un `after` con un extremo): de un cliente, eso se rechaza.
- **El `number` lo elige el cliente** y debe estar libre en la parte (el siguiente al mayor que haya); el servidor lo comprueba. Quitar exige que exista. Mover los extremos de una que existe no se admite: son dos ediciones (quitarla y crearla).
- Los extremos de `after` son relativos al estado `base_seq`, como el ancla (ADR-0011): la proyección aplica las ediciones en orden y deshacer actúa sobre el estado que dejó la edición (el log es una pila, ADR-0034), así que nunca se trasladan.

### 2. Validación (ADR-0017)

Todas: claves exactas (ni más ni menos), tipos estrictos (los booleanos no valen como enteros), 422 sin persistir nada.

- `SetNoteMarks`: el evento existe; una nota de un acorde que no es la primera se rechaza (las marcas del acorde van en su primera nota, ADR-0031); un silencio solo lleva calderón; un silencio invisible (ADR-0032), nada.
- `SetDynamic`: el compás existe; la marca es una de las doce de ADR-0031 o `null`; la posición es ≥ 0, exacta en las 10 080 divisiones por negra con que exporta music21 (ADR-0031: una que no cabe no vuelve exacta) y no pasa del final del compás (su duración en el mapa de tiempos, la métrica o lo que dura su voz más larga). Si la posición tiene ya dos dinámicas (no ocurre con HOMR ni con estas ediciones), se rechaza: la instantánea guarda una.
- `SetSlur`: los dos extremos son notas (no silencios), primeras de su acorde, de la parte del ancla; el fin va después del inicio (antes en el tiempo o, a la vez en la misma voz, después en ella: una nota de adorno y su nota); el ancla es el inicio.
- `SetWedge`: los dos extremos están en compases de la parte, con posiciones válidas como las de la dinámica (el fin puede ser el final del compás); el fin va estrictamente después del inicio; el ancla está en el compás del inicio.
- `has_complete_before`: las claves de su forma (`articulations` y `fermata`; `offset_beats` y `mark`; `number`, `start` y `stop`).
- Un `before` enviado por el cliente se compara con la instantánea del servidor sin depender del orden de las articulaciones ni de la grafía de las posiciones («1/2», «0.5»).

### 3. Política de `EditOp` para el dataset y las métricas

Las marcas de notación no entran en las métricas de los experimentos (ADR-0031 §6), así que **las ediciones de marcas tampoco**. El dominio parte `EditOp` en dos clases (`cadenza.domain`):

- **`CONTENT_EDIT_OPS`**: las siete de contenido (`SetPitch`, `SetDuration`, `SetAccidental`, `InsertEvent`, `DeleteEvent`, `SetClef`, `SetKey`). Son las que deriva `derive_edit_events`, las que cuentan la SER y la cobertura del validador y las que son muestras del dataset.
- **`MARK_EDIT_OPS`**: las cuatro de este ADR.

Y fija:

1. **`exp_02`** calcula la cobertura sobre `len(CONTENT_EDIT_OPS)`, no `len(EditOp)`: sus cifras no cambian («de 7 posibles» sigue siendo cierto).
2. **`DatasetBuilder`** no hace muestras de las ediciones de marcas. Siguen en el log y no cambian el ancla de origen de las demás (no mueven anclas).
3. **`derive_edit_events`, `count_edits_by_op`, `EditSummary`, el corpus (#255), la capa de sugerencias (#256) y su medición (#257)** no cambian: comparan contenido y nunca producen una edición de marcas. La capa no propone marcas (no hay familia `learned.*` de marcas).
4. **`categorize_edit_op`** da `"marks"` a una edición de marcas, para que no se confunda con `"other"`; ninguna edición derivada la recibe.
5. **`test_edit_event.py`** fija las once operaciones, y `test_mark_edit_ops.py`, la partición.
6. **Las métricas de esfuerzo del estudio** (D38, [#188](https://github.com/sebdavid3/Cadenza/issues/188)) cuentan las ediciones de marcas como intervenciones de la persona en el compás de su ancla (son trabajo), y las dan también por separado con `MARK_EDIT_OPS`, para que las ediciones de contenido se puedan comparar con las de antes de este ADR.
7. **Operaciones futuras** ([#236](https://github.com/sebdavid3/Cadenza/issues/236), [#243](https://github.com/sebdavid3/Cadenza/issues/243)): una operación nueva se clasifica al crearla en una de las dos clases (o en una clase nueva, con su ADR). Si es de contenido, `derive_edit_events` debe poder producirla o el ADR dice por qué no, y cambiar `len(CONTENT_EDIT_OPS)` cambia la cobertura de `exp_02`: esa cifra se regenera y se cita como nueva medición, no como la anterior. Ningún experimento usa `len(EditOp)`.

### 4. Web: la barra «Corregir»

Mismo flujo que ADR-0030 y ADR-0033: una edición por orden, con el valor final, el `base_seq` del estado que se ve, sin envío optimista; el 201 trae el estado nuevo (ADR-0037); una orden que llega mientras se guarda otra espera (ADR-0038); 409, 422 y los demás errores con los mensajes de ADR-0030 §7–§8, y «Volver a aplicar» tras un 409.

- **«Articulaciones y calderón»**: picado (staccato), staccatissimo, acento, marcato, tenuto y calderón, conmutadores de 44 px con icono de píxel, pulsados si el evento los tiene. Cada pulsación es un `SetNoteMarks` con el conjunto final. En un acorde actúan sobre su primera nota; ante un silencio, solo el calderón.
- **«Dinámica»**: un desplegable con «Sin dinámica» y las doce, y «Poner» o «Quitar», en la posición del evento elegido (su ataque en el compás; en un acorde, el de su primera nota). Como el de la armadura, el desplegable solo propone.
- **«Ligadura y regulador»**: «Inicio» marca el evento elegido como principio (no es una edición: lo dice la región `aria-live` y queda pulsado); después, con el final elegido, «Ligadura», «Cresc.» y «Dim.» crean la marca entre los dos en el orden en que suenan (elegir antes el final da lo mismo). El inicio se lleva a cada estado nuevo con la regla de desplazamiento (ADR-0011 §2) y se olvida al crear la marca, con «Olvidar el inicio» o si su evento desaparece. Una ligadura une dos notas distintas; un regulador va del ataque del primer evento al final del último, también sobre una sola nota (un regulador bajo una nota larga). Debajo, un botón «Quitar …» por cada ligadura que empieza o acaba en el evento elegido y cada regulador de su pentagrama que cubre su posición (o tiene un extremo suelto en su compás): quita la marca entera.
- **Teclado sobre la partitura**, sin tocar las teclas anteriores: **P**, **A**, **M** y **T** ponen o quitan el picado, el acento, el marcato y el tenuto; **C**, el calderón; **I** marca el inicio, y **L**, **<** y **>** crean desde él una ligadura, un crescendo o un diminuendo hasta el evento elegido. Con Ctrl, ⌘ o Alt nada es de la vista (Ctrl+C copia, Ctrl+P imprime). El staccatissimo, la dinámica y quitar una ligadura o un regulador no tienen tecla: se alcanzan con el tabulador.
- **Qué queda elegido**: las marcas no mueven la selección; deshacer y rehacer `SetNoteMarks` eligen su evento, como un cambio de valor (ADR-0034 §7), y los demás no la mueven, como la clave.
- **Historia de ediciones**: cada una se dice por lo que cambia respecto de su instantánea («acento y sin picado», «dinámica mf», «ligadura de expresión de los compases 1 a 3», «quitar el crescendo en el compás 3»); la dinámica y el regulador, en su compás sin voz.

### 5. Contrato de la API v1

Ampliación compatible: `EditOp` gana cuatro valores en `openapi.json` y `types.ts` (regenerados). Ningún campo ni ninguna respuesta existente cambian; un cliente que no conoce las operaciones nuevas no las envía y lee el log como antes (`op` es `EditOp | string`). No hay migración: el log guarda `op` como texto (`String(32)`) y `before`/`after` como JSON.

## Consecuencias

### Positivas
- Se corrigen las marcas que HOMR lee mal o no lee (las dinámicas y los reguladores, nunca), y se limpian los extremos huérfanos que deja un borrado.
- Deshacer y rehacer son exactos sin código nuevo: las cuatro son «fijar».
- Las cifras de `results/` no cambian: la cobertura de `exp_02` es sobre las siete de contenido y el dataset no ve las marcas. Hay una regla escrita para #236 y #243.
- Las anclas, `translate_anchor`, `origin_anchor` y el traslado de la selección no cambian: las marcas no mueven eventos.

### Negativas / Riesgos
- Una ligadura o un regulador llevan en `after` la posición de su segundo extremo en un estado concreto: es correcta para la proyección y para deshacer (el log es una pila), pero no se puede reinterpretar en otro estado sin la regla de desplazamiento. Tras un 409, la web lleva los dos extremos al estado recargado y elige otro `number`; para volver a quitar una, comprueba que el número sigue siendo la misma marca (un número libre se puede reutilizar).
- Tras un 409, volver a aplicar unas marcas de nota envía el mismo conjunto final: si otra pestaña añadió una articulación a esa nota, se pierde (el mensaje dice qué cambia).
- Validar `SetDynamic`, `SetSlur` y `SetWedge` calcula el mapa de tiempos de la partitura (unos 22 ms con 300 compases y dos pentagramas en la revisión, frente a menos de 1 ms con una página).
- Cambiar los extremos de una ligadura son dos ediciones (quitarla y crearla).
- Una posición con dos dinámicas (que solo podría venir de un MusicXML importado) no se puede editar hasta quitar una, y desde la vista no se puede: no ocurre con HOMR.
- «Inicio» es un estado de la vista, aunque visible y anunciado: si la persona lo olvida, el siguiente «Ligadura» crea la marca desde él (lo dice el mensaje de guardado, que nombra los compases, y se deshace).
- El staccatissimo y la dinámica no tienen tecla; las letras P, A, M, T, C, I y L ya no quedan libres para otras órdenes.
- No está comprobado con un lector de pantalla real ni en un móvil físico; sí con la emulación del navegador a 1440 y 390 px.

## Alternativas consideradas

1. **Operaciones de añadir y quitar** (`AddArticulation`, `RemoveArticulation`, `AddSlur`…). Descartada: el doble de operaciones, una compensatoria propia para cada una, y una pulsación de un conmutador dependería del estado para saber si añade o quita.
2. **Una ligadura como dos ediciones**, una por extremo (`SetSlurs` del evento). Descartada: una orden serían dos ediciones que pueden fallar a medias, y entre ellas la ligadura estaría incompleta en el log.
3. **El `number` lo elige el servidor.** Descartada: el `after` dejaría de ser el valor final que se guarda (ADR-0017) y rehacer no reenviaría la misma edición.
4. **La dinámica anclada al evento** en vez de al compás. Descartada: la dinámica es una posición del compás (ADR-0031 §2); el ancla del compás es la convención de la clave y la armadura (ADR-0010).
5. **Contar las marcas en la cobertura de `exp_02`** (`len(EditOp)`). Descartada: cambiaría una cifra de `results/` sin cambiar nada medido, y el plan de cierre exige que no cambien.
6. **Muestras del dataset con las marcas.** Descartada por ADR-0031 §6: ni el modelo ni las métricas las usan, y su magnitud sería un 1.0 arbitrario.
7. **Un modo de selección de rango** (Mayús+flechas) para la ligadura. Descartada: cambiaría la selección de ADR-0027 y sus teclas; «Inicio» es un paso visible y deshacible.
