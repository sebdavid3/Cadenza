# ADR-0031: Marcas de notación en el `ScoreIR`: articulaciones, calderones, ligaduras de expresión, dinámicas y reguladores

- **Estado:** Aceptado
- **Fecha:** 2026-10-24
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0002, ADR-0007, ADR-0011, ADR-0017 y ADR-0027, CLAUDE.md §9)
- **Enmienda:** [ADR-0010](ADR-0010-score-ir-atributos-y-exportacion.md), que dejaba fuera del `ScoreIR` «dinámicas, articulaciones ni texto»
- **Relacionado:** [ADR-0002](ADR-0002-score-document-anchor-index.md), [ADR-0011](ADR-0011-semantica-de-anclas-ante-ediciones.md), [ADR-0017](ADR-0017-validacion-del-contenido-de-las-ediciones.md), [ADR-0027](ADR-0027-seleccion-de-notas-sobre-la-partitura.md), [ADR-0028](ADR-0028-notas-sin-duracion-como-notas-de-adorno.md), [#213](https://github.com/sebdavid3/Cadenza/issues/213), [#214](https://github.com/sebdavid3/Cadenza/issues/214), [#215](https://github.com/sebdavid3/Cadenza/issues/215)

---

## Contexto

La vista de una sesión solo mostraba notas y silencios. ADR-0010 dejó a propósito fuera del `ScoreIR` las dinámicas, las articulaciones y el texto: el `Event` tenía `kind`, `voice`, `pitch`, `duration_beats`, `tie`, `is_chord`, `bbox`, `confidence` e `ir_handle`, y el `Measure`, su número, sus eventos, la métrica, la clave y la armadura. Al importar el MusicXML de HOMR (`musicxml_to_score_ir`) se perdía todo lo demás, y la exportación que dibuja OSMD (ADR-0006, ADR-0021) no podía llevarlo. Hechos comprobados el 2026-10-24:

- **Lo que da HOMR 0.7.0** (en GPU y sin preprocesado, como la API): en una melodía generada, 4 `<staccato>` y 3 `<accent>`; en una página impresa de *Mondnacht* de Schumann, 30 `<staccato>` y 103 `<slur>` (52 inicios y 51 fines). Emparejados por `number` en orden de lectura, como manda MusicXML, esos 103 dan 39 ligaduras completas; 13 inicios y 12 fines no tienen pareja. HOMR puede dar también `<tenuto>`, `<fermata>` y notas de adorno; no da dinámicas ni reguladores.
- **music21 10.5**, el puente de `interchange`, lee bien las articulaciones (las de las notas de un acorde las junta en el acorde), los calderones, las ligaduras de expresión (spanners con sus notas, también entre compases y entre pentagramas) y las dinámicas (en el compás de su pentagrama, con su `<offset>`). Los **reguladores** no: ata su inicio a la nota siguiente y su fin a la anterior (a veces de otro pentagrama) y pierde el fin que va justo antes de un acorde. Al exportar sí los escribe en su sitio entre dos `SpannerAnchor`, con `<forward>`.
- Las anclas son rutas lógicas con un `event_index` por voz y compás (ADR-0002) y se desplazan con las inserciones y los borrados (ADR-0011). Deshacer debe devolver el estado exacto con la instantánea `before` que fija el servidor (ADR-0017), y la de `DeleteEvent` guardaba `kind`, `pitch`, `duration_beats`, `tie`, `is_chord`, `bbox` y `confidence`.
- Los experimentos de `ml/experiments` leen las partituras con `read_score` y calculan la SER (`score_to_symbol_sequence`), las ediciones del diff con la verdad (`derive_edit_events`), los hallazgos por compás y las muestras del dataset. Sus resultados son la evidencia de la tesis (CLAUDE.md §8) y no pueden cambiar.

## Decisión

### 1. Alcance

- **Articulaciones:** staccato, staccatissimo, acento, marcato (en MusicXML, `strong-accent`) y tenuto.
- **Calderón.**
- **Ligaduras de expresión**, que cruzan notas, compases, sistemas y pentagramas.
- **Dinámicas:** p, pp, ppp, mp, mf, f, ff, fff, sf, sfz, fp y fz.
- **Reguladores** de crescendo y diminuendo, con su inicio y su fin.

Quedan fuera los ornamentos, el texto, el pedal, las demás articulaciones (portato, spiccato…) y las demás dinámicas (sfp, rfz, pppp…), que al importar se ignoran. Tampoco se guarda la colocación (arriba o abajo) ni el tipo de calderón: al exportar, el calderón va sobre la nota.

### 2. Representación: atributos, nunca eventos

Ninguna marca es un evento: el `event_index` de las anclas no cambia (ADR-0002, ADR-0011). Hay tres clases, según a qué se pegan:

1. **De una nota.** `Event.articulations` (un conjunto: sin repetir y en el orden canónico de la lista anterior) y `Event.fermata`. En un acorde van en su primera nota (la que no tiene `is_chord`); al exportar, el acorde lleva las de todas sus notas, una vez. Un silencio puede llevar calderón.
2. **De una posición del compás.** `Measure.dynamics`: cada dinámica con su marca y su ataque en negras desde el inicio del compás (`offset_beats`, fracción exacta), ordenadas por posición. El pentagrama es el del compás; la voz no se guarda: MusicXML la hace opcional, music21 la descarta al leer y una dinámica rige su pentagrama.
3. **De varias notas**, como dos extremos con `type` y `number`, a la manera de MusicXML:
   - una **ligadura de expresión**, en `Event.slurs` de los eventos que une: `{"type": "start"|"stop", "number": n}`;
   - un **regulador**, en `Measure.wedges` de los compases donde empieza y acaba, con su posición: `{"type": "crescendo"|"diminuendo"|"stop", "number": n, "offset_beats": "…"}`; el inicio dice si es de crescendo o de diminuendo.

   El `number` identifica la marca **dentro de su parte** (cruza compases, sistemas y pentagramas) y, a diferencia de MusicXML (de 1 a 16, reutilizables), **no se reutiliza**: el emparejamiento no depende del orden de los eventos ni de las ediciones. Al importar se numeran por orden de lectura de su inicio (compás, pentagrama y evento o posición), de modo que la ida y vuelta por MusicXML da los mismos números.

Las marcas vacías **no se serializan**: un documento sin marcas se guarda exactamente igual que antes y uno guardado antes se lee igual, con las marcas vacías (probado con un documento serializado con el código anterior). La base guarda el documento como JSON: no hace falta migración.

### 3. Lectura y escritura del MusicXML (`interchange`)

- **Al importar**, las articulaciones (por su clase exacta: en music21 `Staccatissimo` deriva de `Staccato` y `StrongAccent` de `Accent`), los calderones y las dinámicas salen de music21, y las ligaduras de sus spanners, del primer al último elemento. Una ligadura incompleta en el origen (un spanner de un solo elemento) no se guarda: no se puede dibujar y music21 no dice qué extremo es. Si el origen repite un inicio con el mismo número antes de cerrarlo, music21 lo toma como continuación y la ligadura va del primer inicio al fin (12 casos en *Mondnacht*; la pauta estricta de MusicXML se quedaría con el segundo).
- **Los reguladores se leen del propio MusicXML**, no de music21: se recorre cada compás con el cursor de MusicXML (las notas que no son de acorde ni de adorno avanzan su `<duration>`; `<backup>` y `<forward>`, la suya), se suma el `<offset>` de la indicación, como hace music21 con las dinámicas, y los extremos se emparejan por `number` en orden de lectura. Se leen en `musicxml_to_score_ir` y en `read_score` de un `.musicxml`, `.xml` o `.mxl`; MEI y `**kern` (converter21) quedan sin reguladores. Si el MusicXML no se entiende o su número de pentagramas no coincide con el de music21, no hay reguladores: esto nunca impide leer la partitura.
- **Al exportar**, las articulaciones y el calderón van en la nota, el acorde o el silencio; las dinámicas, en su posición del compás; las ligaduras, como spanners entre los elementos dibujados (también una nota de adorno); los reguladores, entre dos anclas en su posición exacta. Un extremo sin pareja no se dibuja.
- **El MIDI no lleva marcas**: con dinámicas, music21 cambiaría las velocidades. El volumen según las dinámicas es [#215](https://github.com/sebdavid3/Cadenza/issues/215).

### 4. Edición y deshacer

- `SetPitch`, `SetDuration` y `SetAccidental` conservan las marcas del evento; `SetClef` y `SetKey`, las del compás.
- Las dinámicas y los reguladores son posiciones del compás: insertar o borrar un evento, o cambiar su duración, no los mueve.
- **Deshacer un borrado es exacto.** La instantánea de `DeleteEvent` guarda, además de lo de antes, las marcas que tenga el evento (`articulations`, `fermata`, `slurs`), con la misma forma que su serialización; sin marcas, la instantánea es la de siempre. `InsertEvent` las admite en `after`, validadas (articulaciones del vocabulario, `fermata` booleano, extremos `{type, number ≥ 1}` sin más claves), y su proyección las pone en el evento: el inverso de un borrado devuelve la nota con sus marcas. Una instantánea guardada antes de este ADR no tiene marcas y sigue siendo completa (`has_complete_before`): su ausencia significa «sin marcas».
- No hay operaciones para añadir ni quitar marcas: es [#214](https://github.com/sebdavid3/Cadenza/issues/214).

### 5. Ligaduras y reguladores huérfanos

Borrar la nota de inicio o de fin de una ligadura **no toca la otra nota**: sería editar un evento al que no apunta el ancla, quizá de otro compás, y deshacer necesitaría también su estado. El otro extremo queda **huérfano** en el `ScoreIR`, la API lo devuelve, la exportación no lo dibuja y **deshacer el borrado recompone la ligadura**. Lo mismo valdrá para un regulador cuando haya operaciones sobre las marcas de posición (#214), que podrán además limpiar los huérfanos.

### 6. Métricas de los experimentos

Las marcas no entran en la secuencia de símbolos de la SER, ni en el coste de alineación ni en las ediciones de `derive_edit_events`, ni en `is_structurally_equal`, ni en las reglas del validador, ni en las muestras del dataset, y leerlas no cambia los eventos que se leen. Se prueba con las dos partituras con todas las marcas, leídas con `read_score` con y sin ellas: la misma secuencia de símbolos, la misma SER, las mismas ediciones derivadas, los mismos registros por compás y las mismas muestras.

### 7. Contrato de la API v1 y web

- Ampliación compatible: `ScoreEventPayload` gana `articulations`, `fermata` y `slurs`, y `MeasurePayload`, `dynamics` y `wedges`, opcionales y con valor por defecto (`[]` o `false`). `openapi.json` y `types.ts` se regeneran.
- La web no cambia: OSMD dibuja las marcas del MusicXML exportado con sus reglas por defecto (`RenderSlurs` y `RenderSlursAcrossStaves` activas, `ArticulationPlacementFromXML`), que `osmd.ts` no toca, y las marcas no añaden figuras a las voces dibujadas, así que el mapa de selección (ADR-0027) empareja igual.

## Consecuencias

### Positivas
- Lo que HOMR lee se ve: en la verificación, los 4 staccatos y 3 acentos de la melodía, y los 30 staccatos y las 39 ligaduras de *Mondnacht*.
- La exportación y la descarga del MusicXML son más fieles al original.
- Las dinámicas y los reguladores ya se guardan y se dibujan, listos para la edición manual (#214), un segundo motor o la reproducción (#215).
- Las anclas, los documentos guardados, el contrato v1 y las métricas de los experimentos no cambian.

### Negativas / Riesgos
- No se guarda la colocación ni el tipo de calderón: el calderón de una segunda voz que iba debajo se dibuja encima.
- Las ligaduras incompletas del origen no se guardan (en *Mondnacht*, 25 de los 103 elementos `<slur>` de HOMR).
- Los reguladores solo se leen de MusicXML.
- Observado en la verificación: un diminuendo de 0 a 3 negras con un `mp` en 1/2 OSMD lo dibujó corto, bajo el `mp`, aunque el MusicXML exportado lo lleva entero (comprobado).
- Cada evento y cada compás de la respuesta de la API llevan los campos nuevos aunque estén vacíos.

## Alternativas consideradas

1. **Marcas como eventos** (`EventKind.DYNAMIC`…). Descartada: desplazaría el `event_index` de las notas (ADR-0002).
2. **La dinámica pegada a la nota** (como `@startid` en MEI). Descartada: puede caer a mitad de una nota o donde una voz no ataca, y borrar la nota la borraría.
3. **La ligadura como un objeto de la parte con sus dos anclas.** Descartada: las anclas son relativas a un estado y habría que trasladarlas con cada inserción o borrado (ADR-0011); los extremos viajan solos con sus eventos.
4. **Reutilizar los números de MusicXML (1–16).** Descartada: el emparejamiento dependería del orden y de las ediciones.
5. **Borrar en cascada el otro extremo** de una ligadura. Descartada: edita un evento fuera del ancla y complica deshacer (§5).
6. **Leer los reguladores con music21.** Descartada: pierde su posición (Contexto).
7. **Serializar siempre los campos, también vacíos.** Descartada: cambiaría todos los documentos y cualquier comparación o huella de su JSON.
