# ADR-0041: Título, compositor e instrumento de cada parte, datos de la sesión fuera del `ScoreIR`

- **Estado:** Aceptado
- **Fecha:** 2026-10-31
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0002, ADR-0007, ADR-0009, ADR-0010, ADR-0012, ADR-0014, ADR-0026, ADR-0037 y ADR-0039, CLAUDE.md §9 y §10)
- **Relacionado:** [ADR-0010](ADR-0010-score-ir-atributos-y-exportacion.md), [ADR-0012](ADR-0012-autenticacion-e-identidad.md), [ADR-0014](ADR-0014-ciclo-de-vida-de-la-sesion.md), [ADR-0026](ADR-0026-reproduccion-de-la-partitura-en-el-navegador.md), [ADR-0037](ADR-0037-una-edicion-en-un-solo-viaje.md), [ADR-0039](ADR-0039-anadir-y-quitar-marcas-de-notacion.md), D66, [#235](https://github.com/sebdavid3/Cadenza/issues/235), [#240](https://github.com/sebdavid3/Cadenza/issues/240), [#242](https://github.com/sebdavid3/Cadenza/issues/242), [#189](https://github.com/sebdavid3/Cadenza/issues/189), [#263](https://github.com/sebdavid3/Cadenza/issues/263)

---

## Contexto

Hechos comprobados en el código el 2026-10-31:

- El `ScoreIR` solo tiene partes (`Part.id`), pentagramas y compases. No guarda título, compositor ni el nombre o el instrumento de cada parte. HOMR nombra las partes («Voice» la de un pentagrama y «Piano» la de dos en *Mondnacht*), pero la importación no conserva el nombre; el leer el título de la imagen queda fuera (#263).
- `POST /transcribe` solo recibe `file`, `condition` y `test_score_id`, y el nombre del archivo subido no se guarda: la web nombra la sesión con su id (#240).
- La exportación quita el título y el autor que music21 inventa sin metadatos (#152). La parte de un pentagrama sale con `part-name` vacío y la de dos con el `Part.id` («part-0»), sin `score-instrument` ni `midi-instrument`; el MIDI no lleva cambios de programa (suena como piano) y todas sus pistas van por el canal 1.
- El `ScoreIR` de cada estado y su MusicXML se guardan en una caché por `(sesión, seq, última edición)` (ADR-0037). Lo que cambie el MusicXML sin pasar por el log debe invalidarla o entrar en su clave (D66).
- Las cifras de la tesis dependen de la importación (`read_score` sobre los 555 archivos de `data/`), de `materialize` y de `EditOp` (ADR-0039 §6). La exportación sin metadatos no entra en ninguna cifra salvo `exp_13`, que mide su tiempo.

## Decisión

### 1. Son datos de la sesión, no del `ScoreIR`

El título, el compositor y el instrumento de cada parte los indica la persona; no los lee el OMR ni se corrigen nota a nota. Viven en la sesión: columnas `title`, `composer`, `part_instruments` (JSON, una entrada por parte) y `source_filename` de `sessions`, todas opcionales (migración `0014_session_metadata`). En el dominio, `ScoreMetadata` (título, compositor y `PartMetadata` por parte, con el `Instrument` y un nombre opcional) es un tipo de valor puro y normalizado: sin caracteres de control ni lo que no cabe en un XML 1.0 o en UTF-8 (sustitutos sueltos, U+FFFE y U+FFFF), que pasan a ser espacios, sin espacios de sobra, vacío es nulo, sin las partes vacías del final, título y compositor de hasta 200 caracteres, nombre de parte de hasta 100 y como mucho 32 partes, contados sobre el texto normalizado (la API, que publica esos límites en el contrato, los cuenta sobre el texto recibido: el cliente recorta los espacios). Dos formas de decir lo mismo son iguales. Un instrumento guardado que el código no conoce (de una versión posterior) se lee como `other` con su identificador por nombre, para que una fila no deje sin respuesta el listado. `SessionData` y `SessionSummary` lo llevan; una sesión anterior se lee sin metadatos.

El `ScoreIR`, su serialización, el `ScoreDocument`, la importación, `materialize`, `EditOp` y las anclas no cambian: las cifras de los experimentos no se mueven (comprobado con la huella del `ScoreIR` y del MIDI de los 555 archivos de `data/`, igual antes y después).

### 2. La lista cerrada de instrumentos

`Instrument`: `piano`, `voice`, `violin`, `cello`, `flute`, `clarinet`, `guitar` y `other`. Los identificadores son estables y la lista solo crece: un instrumento nuevo es una ampliación compatible del contrato. `other` admite un nombre libre (el de la parte) y suena como el piano (#240). Al exportar, cada uno tiene su nombre en español (el de la parte si no se da otro), su programa General MIDI y su `instrument-sound` de MusicXML:

| Instrumento | Nombre | Programa (MusicXML, desde 1) | `instrument-sound` |
|---|---|---|---|
| `piano` | Piano | 1 | `keyboard.piano` |
| `voice` | Voz | 53 (Choir Aahs, como la voz de MuseScore) | `voice.vocals` |
| `violin` | Violín | 41 | `strings.violin` |
| `cello` | Violonchelo | 43 | `strings.cello` |
| `flute` | Flauta | 74 | `wind.flutes.flute` |
| `clarinet` | Clarinete | 72 | `wind.reed.clarinet` |
| `guitar` | Guitarra | 25 | `pluck.guitar.nylon-string` |
| `other` | Otro | 1 | (ninguno) |

Qué muestras de sonido tiene cada uno en la web lo decide #242; un instrumento sin muestras suena como el piano.

### 3. Cómo se asignan a las partes de HOMR, y qué pasa si no se dan

- **Por posición.** La entrada `i` es la parte `i` del `ScoreIR`, en el orden en que HOMR las detecta (de arriba abajo: la voz o el instrumento de arriba, luego el piano). Las ediciones no añaden ni quitan partes, así que la posición vale en todos los estados.
- **Al transcribir**, `POST /transcribe` admite `title`, `composer`, `instruments` y `part_names`, todos opcionales; los dos últimos se repiten una vez por parte, alineados, y `''` es «sin instrumento» o «sin nombre». Se validan antes de transcribir (422). La persona no sabe cuántas partes detectará HOMR: los instrumentos de partes que HOMR no detecte se descartan, sin error. Se guarda también el nombre del archivo subido, sin la ruta y acortado a 255 caracteres, para nombrar la sesión cuando no hay título (#240).
- **Sin datos**, nada cambia: la sesión no tiene título ni instrumentos, la API devuelve `null` y `[]`, y lo exportado es lo de siempre, también en una parte concreta sin datos. No se deduce un instrumento del número de pentagramas ni del nombre que da HOMR: sería adivinar por la persona.

### 4. Cambiarlos después: `PATCH /sessions/{id}`

- Cambia lo que se envía y deja lo demás; `null` borra; `instruments` sustituye la lista entera y no puede tener más entradas que partes la partitura (422, aquí sí se sabe cuántas hay).
- Solo el dueño (ADR-0012): un transcriptor ajeno recibe 404 y un investigador ajeno, 403, como al editar.
- **No es una edición del log** (ADR-0007): no tiene `base_seq`, no cambia `current_seq` ni el estado de la sesión (una sesión `transcribed` sigue así), no añade ninguna operación a `EditOp` (la política de ADR-0039 no cambia) y no cuenta en las métricas de esfuerzo ni en el dataset, que leen el log y el `ScoreIR`.
- **Se admite con la sesión finalizada** (ADR-0014): la finalización congela la corrección, el `ScoreIR` final y sus hallazgos, y nada de eso cambia. Renombrar una partitura terminada o corregir su compositor no debe obligar a reabrirla, que sí la devuelve a `correcting`.

### 5. La exportación y la caché

- El puerto `ScoreExporter` recibe los metadatos aparte: `to_musicxml(score, metadata=None)` y `to_midi(score, metadata=None)`. Los casos de uso que exportan (la edición, deshacer y `/export`) pasan los de la sesión.
- **MusicXML.** Sobre el árbol que escribe music21: `work/work-title` al principio de `score-partwise`, `creator type="composer"` al principio de `identification`, y en cada `score-part` con datos, el `part-name` (el nombre dado o el del instrumento), `score-instrument` con `instrument-name` e `instrument-sound`, y `midi-instrument` con el mismo id, su canal (1 a 16 sin el 10, por parte) y su programa. Una parte con nombre y sin instrumento solo cambia su `part-name`. La importación ignora todo esto: el `ScoreIR` leído es el mismo.
- **MIDI.** Cada parte con instrumento fija su programa en todas sus pistas (las dos de un piano); music21 asigna entonces un canal por instrumento. Sin instrumento, como antes: sin cambio de programa.
- **Caché (D66).** El `PATCH` llama a `score_cache.invalidate(session_id)`. Además, el MusicXML guardado recuerda con qué metadatos se exportó (`CachedScoreState.musicxml_metadata`) y solo se sirve con esos mismos: una exportación con los metadatos de antes que llegue a la caché después de invalidarla (otra petición a la vez) no se sirve con los nuevos. Esto vale también con varios procesos, cada uno con su caché, sin versionar la clave. El `ScoreIR` y los tiempos no dependen de los metadatos y se siguen compartiendo.

### 6. El contrato

Ampliación compatible del contrato v1: `SessionSummaryRead`, `SessionDetailRead` y `SessionViewRead` ganan `title`, `composer`, `instruments` (`PartInstrumentRead[]`) y `source_filename`; `POST /transcribe` gana cuatro campos opcionales del formulario; nuevos `PATCH /sessions/{id}`, `SessionMetadataUpdate`, `PartInstrumentWrite`, `SessionMetadataRead` e `Instrument`. Ningún campo existente cambia. Se regeneran `openapi.json` y `types.ts`.

## Consecuencias

### Positivas
- La sesión tiene nombre (#240) y cada parte, su instrumento para la reproducción (#242) y el MIDI (#189). El MusicXML lleva el título, el compositor y los nombres de las partes; la vista no los dibuja hoy (`osmd.ts` apaga `drawTitle`, `drawComposer` y `drawPartNames`): encenderlos, con su efecto en la maquetación y en el mapa de notas de ADR-0027, es de #240.
- El `ScoreIR`, el log y todo lo que alimenta las cifras de la tesis quedan igual; una sesión sin datos nuevos exporta lo mismo que antes.
- El MusicXML descargado se abre en MuseScore con su título, su compositor y sus instrumentos.

### Negativas / Riesgos
- Los metadatos no tienen historia: el `PATCH` sustituye y no se puede deshacer desde el log. Es aceptable porque no son la corrección que mide el estudio.
- Tras el `PATCH`, el MusicXML que la vista tiene es el de antes: si #240 dibuja el título o los nombres de las partes, debe volver a pedirlo o actualizar lo que muestra con la respuesta.
- Si HOMR detecta las partes en otro orden o en otro número del que la persona esperaba, los instrumentos dados al subir quedan en la parte que no es o se descartan; se corrigen con el `PATCH`, que ya conoce las partes.
- En el MIDI con instrumentos, cada parte va por su canal: un reproductor que solo escuche el canal 1 dejaría de oír el piano. Los reproductores General MIDI los oyen todos.
- Con más de 15 partes, los canales del MusicXML se repiten; fuera del alcance (corpus monofónico y piano simple).

## Alternativas consideradas

1. **Guardarlos en el `ScoreIR` (`ScoreIR.title`, `Part.name`, `Part.instrument`).** Descartada: cambiarlos sería una edición del log (o mutar el documento crudo, contra ADR-0002 y ADR-0007), con su `EditOp` nueva y su política para el dataset y las métricas (ADR-0039), y cambiaría la serialización del `ScoreIR` y la importación de los 555 archivos de `data/` si se leyeran los nombres de las partes.
2. **Conservar el nombre que HOMR da a cada parte y deducir de él el instrumento.** Descartada: HOMR nombra por el número de pentagramas («Voice», «Piano»), no por lo que es la parte; la persona lo sabe mejor y lo indica.
3. **Una versión de los metadatos en la clave de la caché.** Descartada: con una instancia basta invalidar, y recordar los metadatos del MusicXML guardado cubre las carreras y varios procesos sin otra columna.
4. **Rechazar con 422 en `POST /transcribe` los instrumentos de más.** Descartada: se sabría después de transcribir, tras gastar el tiempo de HOMR, y la persona no puede saber antes cuántas partes saldrán.
5. **Los instrumentos del formulario como un JSON en un solo campo.** Descartada: el contrato perdería el tipo (`Instrument`) y su validación; dos listas repetidas y alineadas se escriben igual con `FormData`.
6. **No admitir el `PATCH` con la sesión finalizada.** Descartada: no cambia nada de lo que la finalización congela, y reabrir para renombrar alteraría el estado que mide el estudio.
