# ADR-0032: Varias voces en el `ScoreIR`: huecos como silencios invisibles, plicas al exportar y numeración de voces

- **Estado:** Aceptado
- **Fecha:** 2026-10-24
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0002, ADR-0010, ADR-0011, ADR-0017, ADR-0027 y ADR-0031, CLAUDE.md §9)
- **Relacionado:** [ADR-0002](ADR-0002-score-document-anchor-index.md), [ADR-0010](ADR-0010-score-ir-atributos-y-exportacion.md), [ADR-0011](ADR-0011-semantica-de-anclas-ante-ediciones.md), [ADR-0017](ADR-0017-validacion-del-contenido-de-las-ediciones.md), [ADR-0021](ADR-0021-visualizacion-de-la-transcripcion-y-marcado-de-hallazgos.md), [ADR-0026](ADR-0026-reproduccion-de-la-partitura-en-el-navegador.md), [ADR-0027](ADR-0027-seleccion-de-notas-sobre-la-partitura.md), [ADR-0031](ADR-0031-marcas-de-notacion-en-el-score-ir.md), [#218](https://github.com/sebdavid3/Cadenza/issues/218)

---

## Contexto

El `ScoreIR` ya admitía partes, pentagramas, voces y acordes (D37, #32): `Event.voice` e `is_chord`, con los eventos de cada voz uno detrás de otro y el `event_index` de las anclas contado por voz y compás (ADR-0002). Pero la importación (`notation.py`) no miraba dónde empieza cada nota: ponía las notas de cada voz seguidas desde el principio del compás. Hechos comprobados el 2026-10-24 sobre `dev` con las marcas de ADR-0031 ya fusionadas (`b41f306`):

- **El fallo.** Compás de 4/4: voz 1, un Mi5 redonda; voz 2, un `<forward>` de dos negras y después Do5 y Si4. music21 10.5 sitúa bien Do5 en 2 (no crea un silencio: el silencio oculto solo lo crea para Finale), pero el `ScoreIR` no guarda la posición: tras importar y exportar, Do5 pasa de 2 a 0 y Si4 de 3 a 1, y el validador da un error falso, «El compás 1 (voz 1) suma 2 negras y su métrica 4/4 exige 4». El mapa de tiempos (y la reproducción) y el dibujo heredan el desplazamiento.
- **Dónde importa.** No solo en el `<forward>` de otras fuentes. HOMR 0.7.0 no escribe `<forward>`, pero intercala las voces con `<backup>` que no vuelven al principio del compás: en el compás 2 de la página 9 de *Mondnacht*, la voz 6 entra en la segunda semicorchea. En las cinco salidas de HOMR con varias voces que había para verificar (*Mondnacht* p. 9 y 10, impresas y fotografiadas, y un autógrafo), entre 10 y 17 voces por página entraban a mitad del compás, y Cadenza las ponía al principio. Audiveris escribe `<forward>` al principio de una voz (20 y 17 por página de *Mondnacht*), y la transcripción de OpenScore de *Mondnacht*, `<forward>` al final y en medio (4) y 17 silencios con `print-object="no"`, todos al principio de su voz, que hoy se importaban como silencios visibles.
- **Voces que salen antes.** En todas las fuentes hay voces que acaban antes que el compás sin nada detrás: 9 por página en HOMR, 16 y 18 en Audiveris, 6 en OpenScore. El validador las marcaba como error de balance: 6 de los 8 hallazgos de balance de la transcripción de OpenScore, todos falsos.
- **Plicas.** HOMR no escribe `<stem>`, el `ScoreIR` no guarda la dirección y el exportador no la escribía. OSMD 2.2.1 (`calculateStemDirectionFromVoices`) solo fuerza hacia arriba la primera voz donde otra ataca en el mismo instante; en el resto la deja automática. En el compás 3 del piano de prueba transcrito por HOMR, las negras de la voz grave salían unas con la plica hacia abajo (Si4) y otras hacia arriba (Sol4), entre las blancas de la voz aguda.
- **Números de voz al exportar.** Al unir los pentagramas de un piano, music21 no renumera las voces del inferior si el superior ya las numera: en el MusicXML exportado de *Mondnacht* p. 9, el compás 33 usaba las voces 1 y 2 en los dos pentagramas, y la voz principal del pentagrama inferior era la 1 en unos compases y la 2 en otros. OSMD sitúa los silencios de varias voces por su número (las voces 1 y 5, arriba) y lleva hacia abajo la plica de la voz que toma por secundaria: las blancas del bajo del piano de prueba (La2 y Sol2) salían con la plica hacia abajo.
- **Experimentos.** Ningún archivo de `data/` tiene `<forward>` ni `print-object` (0 de los 455 MusicXML de predicciones), ni `<space>`, `<mSpace>`, `visible="false"` o una segunda capa (0 de los 126.986 MEI de PrIMuS). Pero 32 de las 100 verdades MEI del manifiesto tienen un `<multiRest>`, que converter21 sustituye por un silencio de compás entero **oculto** (sin `MultiMeasureRest`), y que en la partitura se ve.

## Decisión

### 1. Un hueco es un silencio invisible (`Event.hidden`)

Un silencio puede ser invisible: `Event.hidden`, que solo admite un silencio (otro evento con `hidden` es un error) y que, si es falso, no se serializa, como las marcas de ADR-0031. Un silencio invisible es **un evento más**: ocupa su tiempo en la voz, tiene ancla y cuenta en `event_index`; no se dibuja, no suena y no se puede elegir en la vista.

- **Al importar** (`_events_from_elements`), el hueco antes de un elemento de una voz (su posición en music21 pasa del final del anterior: un `<forward>` o un `<backup>` que no vuelve al principio) se convierte en un silencio invisible de esa duración. Lo que falta tras la última nota de una voz **no** es un evento: no lleva información de posición, y MusicXML no obliga a rellenarlo. Un silencio que music21 da oculto (`print-object="no"`) es invisible **solo si la partitura viene de MusicXML** (`musicxml_to_score_ir`, `read_score` de `.musicxml`, `.xml` o `.mxl`): converter21 oculta también el silencio con que sustituye un `<multiRest>` de MEI, que se ve; de MEI, **kern o un `Stream` de origen desconocido (`music21_stream_to_score_ir`) se lee como un silencio que se ve, como hasta ahora. Una nota con `print-object="no"` sigue siendo una nota que se ve.
- **Al exportar**, un silencio invisible sale como un silencio con `print-object="no"`, no como `<forward>`: la ida y vuelta da el mismo `ScoreIR` (también con el silencio invisible al final de una voz que trae el origen) y cada voz de un compás tiene al menos un elemento, lo que hace falta para numerarlas (§3). OSMD guarda el silencio pero lo pinta transparente; `osmd.ts` no lo cuenta como figura dibujada.
- **Mapa de tiempos, reproducción y validador** no cambian: el silencio invisible es un silencio con su duración, así que lo que le sigue empieza donde debe. La vista no lo reproduce (no es una nota).
- **Selección (ADR-0027).** `noteMap.ts` lo salta: no tiene figura, solo retrasa el instante de lo que le sigue, y una voz hecha solo de silencios invisibles no es una voz dibujada. No se puede elegir, pero sus anclas siguen contando en `event_index`.
- **Ediciones y deshacer (ADR-0017).** `SetDuration` lo conserva invisible (usa `replace`). La instantánea de `DeleteEvent` de un silencio invisible guarda `"hidden": true`, e `InsertEvent` admite `hidden` (booleano y solo en un silencio), de modo que deshacer el borrado lo devuelve invisible. Sin `hidden`, la instantánea es la de siempre: una guardada antes es completa y su ausencia significa «se ve».
- **Marcas (ADR-0031).** No cambian: las de una nota viajan con su evento; las dinámicas y los reguladores son posiciones del compás, y los extremos de ligadura se emparejan por su número, no por su índice. Probado con un piano con dos voces por pentagrama, en la importación y en la ida y vuelta.

**Anclas y documentos.** Los documentos guardados no se reimportan: se leen igual y sus anclas no cambian. En un documento **nuevo**, cada hueco añade un evento a su voz, y el `event_index` de lo que le sigue en esa voz y ese compás es uno mayor que el que habría tenido antes de este ADR. En las 10 salidas de HOMR comprobadas, quitar los silencios invisibles deja el `ScoreIR` idéntico al de `dev`; en las cinco con varias voces añaden 10, 11, 12, 13 y 17 eventos, en 10 a 15 compases-voz. Las monofónicas de PrIMuS no cambian (§6).

### 2. La dirección de plica se decide al exportar, por altura

El `ScoreIR` no guarda la plica: HOMR no la da y nada la edita. Al exportar (`_stem_directions`), en un compás de un pentagrama con **dos o más voces con notas**, la voz de **mayor altura media** lleva la plica hacia arriba y las demás hacia abajo; con menos de dos, la plica la decide quien dibuja (OSMD). No es la voz de número menor: HOMR no numera las voces por su altura (en el piano de prueba da la voz 1 a las negras graves y la 2 a las blancas agudas), y la regla por número cruzaba sus plicas. Una voz con solo silencios no cuenta.

### 3. Numeración de las voces

- **Al importar**, las voces se numeran desde 0 en cada compás de cada pentagrama, en el orden de su número de MusicXML: HOMR numera 1-3 las del pentagrama superior y 5-7 las del inferior, y las dos quedan 0-2. Es lo que ya hacía la importación (en el orden en que music21 las leía, que en HOMR es el mismo); ahora se ordenan por el número para no depender del orden en que las escribe el origen.
- **Al exportar** (`_number_voices_by_staff`), la voz `v` del pentagrama `s` (desde 0) es la `s · paso + v + 1`, con un paso de 4 como HOMR y MuseScore (1-4 arriba, 5-8 abajo) o mayor si un pentagrama tiene más voces. Así cada pentagrama tiene su voz principal en todos los compases, y OSMD la trata como tal. Se renumera sobre el MusicXML que escribe music21, compás a compás y pentagrama a pentagrama, en el orden en que escribe las voces del `ScoreIR`; si no cuadra, el compás se deja como está. La ida y vuelta da las mismas voces.

### 4. Balance del compás con varias voces

`measure.balance` sigue comprobando cada voz, pero **una voz puede salir antes del final del compás si otra lo completa**: con varias voces, una voz más corta no es un error si alguna suma la métrica. Sigue siendo error una voz que se pasa, o que ninguna complete el compás (entonces se señala cada voz corta, como antes). Con una sola voz no cambia nada. La prueba que esperaba un error para la segunda voz corta de un compás de piano completo (`test_piano_unbalanced_voice_in_polyphonic_measure`) expresaba la regla anterior: se sustituye por `test_piano_voice_that_overflows_a_polyphonic_measure` (la voz se pasa del compás: error), `test_a_voice_may_end_before_the_measure_if_another_completes_it` (la voz corta de antes: sin error) y `test_short_voices_are_errors_if_no_voice_completes_the_measure`.

### 5. Métricas de los experimentos

Un silencio invisible no entra en la secuencia de símbolos de la SER (`score_to_symbol_sequence`): no se dibuja ni se reconoce, y antes el `<forward>` del que sale se perdía al importar. En el diff con la verdad (`derive_edit_events`) es un evento más, para que materializar las ediciones dé la verdad. Nada de esto cambia las cifras de la tesis: ningún archivo de `data/` tiene huecos ni silencios invisibles, y los 555 que leen los experimentos (las 100 verdades MEI del manifiesto y las 455 predicciones de HOMR) se leen con `read_score` exactamente igual que antes, comprobado comparando la huella del `ScoreIR` de cada uno antes y después del cambio, sin ejecutar ningún experimento. El `<multiRest>` de las 32 verdades MEI que lo tienen sigue siendo un silencio que se ve (§1).

### 6. Contrato de la API v1 y web

- Ampliación compatible: `ScoreEventPayload.hidden`, opcional y `false` por defecto; `openapi.json` y `types.ts` se regeneran.
- La web solo cambia en `noteMap.ts` (saltar los silencios invisibles) y `osmd.ts` (no contar como figura lo que OSMD no dibuja). Las plicas y los números de voz llegan en el MusicXML exportado.

## Consecuencias

### Positivas
- Cada nota conserva dónde empieza en su voz al importar y exportar, también con las voces que HOMR intercala con `<backup>`; el mapa de tiempos, la reproducción y el dibujo lo respetan.
- Sin el error falso del validador para una voz que entra o sale a mitad del compás.
- Las plicas de dos voces no se cruzan, y cada pentagrama de un piano tiene su voz principal en todos los compases.
- Los documentos guardados, sus anclas, el contrato v1 y las cifras de los experimentos no cambian.

### Negativas / Riesgos
- En los documentos nuevos de HOMR con varias voces, el `event_index` de lo que sigue a un hueco es uno mayor que antes de este ADR.
- Se pierde información de recuerdo del validador: con varias voces, una voz que HOMR acortó por error ya no se señala si otra voz completa el compás (en *Mondnacht* p. 9 de HOMR, 4 de los 36 hallazgos de balance eran de este caso; en la transcripción de OpenScore, 6 de 8, y falsos).
- La altura media no siempre dice qué voz es la de arriba (voces que se cruzan); con tres o más voces, las de en medio también van hacia abajo.
- La selección de la vista ordena las voces por su número, no por su altura: con la numeración de HOMR, «abajo» puede llevar a la voz que se dibuja encima.
- Lo que falta tras la última nota de una voz no se guarda: un `<forward>` final del origen se pierde (music21 ya lo perdía).
- Un silencio invisible al principio de un compás lleva el ancla del «primer evento de la voz» que usa `measure.balance`.

## Alternativas consideradas

1. **Guardar el ataque de cada evento** (`Event.offset_beats`). Descartada: la secuencia de cada voz dejaría de bastar para situar sus eventos, y cada edición (`SetDuration`, `InsertEvent`, `DeleteEvent`, deshacer) tendría que mantener los ataques de los demás; los documentos guardados no los tienen.
2. **Un tipo de evento nuevo** (`EventKind.SPACE`, como `<space>` de MEI). Descartada: cambiaría un enumerado del contrato v1 y todo el código que distingue nota y silencio; un silencio invisible ya es un silencio en MusicXML.
3. **Exportar el hueco como `<forward>`.** Descartada: un silencio invisible al final de una voz se perdería en la ida y vuelta, y una voz hecha solo de huecos no tendría elementos que numerar.
4. **Rellenar al importar el final de una voz corta** con un silencio invisible. Descartada: añade eventos sin información de posición y oculta igual el balance; la regla del validador lo dice directamente.
5. **Plicas por número de voz** (la primera hacia arriba). Descartada tras verlo dibujado: HOMR no numera las voces por su altura y las plicas se cruzaban.
6. **Guardar la plica en el `ScoreIR`.** Descartada: HOMR no la da, nada la edita y obligaría a mantenerla en cada edición.
7. **Confiar en el silencio oculto de cualquier formato.** Descartada: el `<multiRest>` de 32 verdades de PrIMuS pasaría a ser invisible y cambiaría la SER de la tesis.
