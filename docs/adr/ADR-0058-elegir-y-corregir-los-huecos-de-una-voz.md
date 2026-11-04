# ADR-0058: Elegir y corregir los huecos de una voz (silencios invisibles)

- **Estado:** Aceptado
- **Fecha:** 2026-11-02
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0011, ADR-0017, ADR-0037, ADR-0038, ADR-0039 y ADR-0055, CLAUDE.md §9; el responsable decidió el 2026-11-02 resolverlo antes del congelado, #252)
- **Enmienda:** [ADR-0027](ADR-0027-seleccion-de-notas-sobre-la-partitura.md) §1 y §2 (un hueco también se empareja y se elige), [ADR-0032](ADR-0032-varias-voces-huecos-y-plicas.md) §1 («no se puede elegir en la vista»), [ADR-0033](ADR-0033-insertar-borrar-clave-y-armadura.md) §5 y §8 (un hueco se elige, se borra y se escribe en él) y [ADR-0034](ADR-0034-deshacer-y-rehacer-desde-la-vista.md) §7 (deshacer y rehacer eligen también un hueco) y [ADR-0050](ADR-0050-metricas-de-esfuerzo-de-la-correccion.md) §3 (la clase «contenido» de las intervenciones incluye `GAP_EDIT_OPS`)
- **Relacionado:** [ADR-0036](ADR-0036-capa-de-sugerencias-aprendida.md), [ADR-0039](ADR-0039-anadir-y-quitar-marcas-de-notacion.md), [ADR-0050](ADR-0050-metricas-de-esfuerzo-de-la-correccion.md), [ADR-0055](ADR-0055-ligaduras-de-prolongacion-y-notas-de-un-acorde.md), [#247](https://github.com/sebdavid3/Cadenza/issues/247), [#317](https://github.com/sebdavid3/Cadenza/issues/317)

---

## Contexto

ADR-0032 importa el hueco antes de un elemento de una voz (un `<forward>`, o un `<backup>` de HOMR que no vuelve al principio del compás) como un silencio invisible (`Event.hidden`): ocupa su tiempo y retrasa lo que le sigue. La vista no lo elige (ADR-0032 §1, ADR-0033 §8), así que no se puede borrar, acortar ni rellenar. Hechos comprobados el 2026-11-02 sobre `dev` (`1771ffc`):

- **TS-03 del banco del estudio** (#247, *Frühlingstraum*, cc. 14-21), transcrito por HOMR contra la API real: siete huecos. En la voz, uno de semicorchea en el c. 1 donde va un Fa#4 (la nota que falta) y otro de semicorchea que sobra, uno de corchea en el c. 2 y uno de semicorchea en el c. 5; en la mano derecha, uno de semicorchea en los cc. 1 y 5 y uno de negra al principio de la segunda voz del c. 2. Los que sobran desplazan las notas que los siguen (en el c. 1, Sol#4 y Sol#4 entran una semicorchea tarde) y ninguna corrección de la barra los quita. La segunda voz de la mano derecha del c. 2 (un Do#4 negra con puntillo ligado a una corchea) empieza con el hueco de negra y lleva un Mi4 que HOMR puso ahí: sin elegir el hueco, esa voz no se puede escribir; al borrar el Mi4, la voz se queda solo con el hueco y deja de dibujarse. La partitura no se podía corregir entera.
- **OSMD 2.2.1 guarda el silencio invisible y VexFlow lo pinta transparente** (`fill="#00000000"`) en su sitio, con su caja en el SVG: en TS-03, las siete cabezas transparentes miden de 8 a 12 px de ancho y están en la columna del tiempo que ocupa el hueco. También la del hueco de una voz que no tiene nada más que se vea.
- `SetDuration` ya conserva un hueco invisible (ADR-0032) y `DeleteEvent` lo borra, con `"hidden": true` en la instantánea para deshacerlo. Ninguna operación lo hace visible ni lo convierte en una nota: `SetPitch` solo se aplica a notas.

## Decisión

### 1. Cómo se ve y se elige un hueco

- **Emparejamiento (enmienda ADR-0027 §1).** `osmd.ts` da también las figuras de los silencios que OSMD no dibuja (`PrintObject` falso), marcadas `hidden`, con la caja de su glifo transparente. `noteMap.ts` empareja las voces que se ven como antes (las figuras invisibles no cuentan para decidir qué voz es cuál) y, dentro de cada una, cada hueco con los silencios transparentes que hay en su sitio y suman su duración (music21 escribe en dos figuras el que no cabe en una). Las voces hechas solo de huecos se emparejan entre ellas si OSMD guarda tantas como el `ScoreIR`.
- **Todo o nada para lo que se ve; los huecos, si se sabe dónde están (enmienda ADR-0027 §2).** Si en el sitio de un hueco no hay silencio transparente (OSMD no lo guardó), o los silencios transparentes no cuadran con los huecos del compás, esos huecos no se ofrecen y el compás se empareja como antes de este ADR, sin ellos: sus notas y silencios siguen elegibles. Un hueco no hace que la partitura deje de ofrecer la selección. Los huecos no cuentan en el total de eventos que dice la barra cuando el mapa no se ofrece.
- **Solo se corrige el hueco que se ofrece.** Si un borrado o deshacer deja elegido un hueco que la vista no ofrece, la barra no lo toma como el evento elegido: no hay nada que corregir sin su marca.
- **Cómo se ve.** Cada hueco ofrecido se señala en la capa de marcas, por detrás de las notas, con la **trama de puntos de tinta** de lo secundario (DESIGN.md: el estado se dice con un patrón de la familia, no con un color ni con un signo nuevo) sobre la caja de su silencio transparente. No se dibuja nada en la partitura de OSMD ni en el MusicXML que se descarga: la partitura no gana un signo que no tiene.
- **Cómo se elige.** Como cualquier evento: con el toque (el más cercano en horizontal), con ← y → por su voz, Inicio y Fin, ↑ y ↓ por las voces, y los pasos «Anterior» y «Siguiente». La barra de la selección lo dice: «Hueco de semicorchea», y el lector de pantalla oye «hueco de semicorchea, un silencio invisible». Elegido, lleva la marca de la nota elegida (ADR-0027 §8).

### 2. Qué admite un hueco y con qué edición

| Orden | Edición | `before` del servidor | `after` | Deshacer |
|---|---|---|---|---|
| Borrarlo | `DeleteEvent` (sin cambios) | la instantánea del borrado, con `"hidden": true` | `null` | `InsertEvent` con la instantánea: vuelve invisible |
| Hacerlo un silencio que se ve | `SetEventKind` (nueva) | `{"kind": "rest", "pitch": null, "hidden": true}` | `{"kind": "rest", "pitch": null, "hidden": false}` | la compensatoria intercambia `before` y `after` |
| Escribir una nota en su lugar | `SetEventKind` | igual | `{"kind": "note", "pitch": "F#4", "hidden": false}` | igual |
| Cambiar su figura | `SetDuration` (sin cambios, lo conserva invisible) | `{"duration_beats": …}` | `{"duration_beats": …}` | intercambia |

- **`SetEventKind`, de tipo «fijar».** Fija lo que es el evento anclado, con su misma figura: `after` y `before` tienen la forma `{"kind": "note" | "rest", "pitch": str | null, "hidden": bool}`, con las claves exactas. No mueve ningún evento ni desplaza anclas (`translate_anchor`, `carryAnchor`): el hueco ya ocupaba su tiempo. El mapa de tiempos solo cambia en la clase del evento.
- **Validación (ADR-0017).** El evento anclado ha de ser un hueco (un silencio con `hidden`): una nota o un silencio que se ve se corrigen con las demás operaciones. El `after` es una nota con una altura canónica y `hidden: false`, o un silencio sin altura y `hidden: false` (un hueco que sigue siendo hueco no cambia nada). Una nota en el hueco no se admite si lo que lo sigue en su voz es una nota con `is_chord`: tras un silencio esa nota empieza su propio grupo, y tras una nota se uniría a su acorde (ADR-0055 §2). La figura del hueco ha de ser una que admiten las ediciones (ADR-0017: hasta una longa, con denominador $2^a \cdot t$): un hueco importado que no lo sea se acorta antes con su figura. La nota nueva no lleva ligadura ni acorde; conserva las marcas que traiga el hueco (la importación guarda, por ejemplo, el calderón de un silencio invisible), y deshacer lo devuelve igual.
- **Solo la compensatoria devuelve un evento a hueco**: deshacer aplica la inversa sin validarla (el log es una pila, ADR-0034, así que el evento es exactamente el que dejó la edición) y la proyección lo vuelve a silencio invisible sin ligadura ni acorde. Rehacer reenvía el `after` sobre el hueco que devolvió deshacer.
- **Por qué una operación nueva y no dos ediciones.** Borrar el hueco e insertar una nota en su sitio son dos ediciones para una decisión: dos pasos de deshacer, dos viajes (ADR-0037) y una mitad que puede fallar. Cambiar el significado de `SetPitch` sobre un silencio cambiaría una operación de contenido que deriva `derive_edit_events` y cuenta `exp_02`.

### 3. Política de `EditOp`: una clase nueva, `GAP_EDIT_OPS`

ADR-0039 §3.7 pide clasificar cada operación nueva. `SetEventKind` forma una clase propia, **`GAP_EDIT_OPS`**:

1. **`derive_edit_events` no la produce**: un silencio que se ve no se empareja con uno invisible (ADR-0032 §5), así que un hueco convertido sale del diff como su borrado y una inserción. **`len(CONTENT_EDIT_OPS)` sigue siendo 7 y la cobertura de `exp_02` no cambia.**
2. **`DatasetBuilder`** no hace muestras de ella y **`categorize_edit_op`** la llama `"gap"`.
3. **El corpus de correcciones y los rasgos de la capa no cambian**: no se tocan `derive_edit_events`, los rasgos, `CORPUS_FORMAT_VERSION`, `FEATURE_VERSION` ni `RULES_CATALOG_VERSION`, y ninguna sesión guardada ni ningún archivo de `data/` tiene `SetEventKind`. Una sesión corregida con estas órdenes se sigue reproduciendo al derivar (`test_gap_edits_keep_a_session_verified`). `exp_14` se volvió a ejecutar en el scratchpad con el corpus y el reparto de `results/` y da las mismas cifras que `results/rules_catalog_v2/exp_14` (§Consecuencias).
4. **Las métricas de esfuerzo del estudio** la cuentan como **contenido**: escribir una nota o un silencio es una decisión sobre el contenido, como insertar o borrar. Siguen siendo tres clases (protocolo §3.4, ADR-0050), pero la clase «contenido» ya no es exactamente `CONTENT_EDIT_OPS`: es `CONTENT_EDIT_OPS` más `GAP_EDIT_OPS` (enmienda ADR-0050 §3). Es una definición del protocolo (#244): el responsable la confirmó el 2026-11-02, frente a la alternativa de contarla aparte, en una cuarta clase.
5. No es de ninguna familia de sugerencias: la capa no la propone.

`METER_EDIT_OPS` se descartó (no es el compás ni la duración de varios eventos), y `CONTENT_EDIT_OPS` también (cambiaría la cobertura de `exp_02` sin que `derive_edit_events` la produzca).

### 4. Web: el grupo «Hueco» de la barra

Mismo flujo que ADR-0030, ADR-0037 y ADR-0038: una edición por orden, con el valor final y el `base_seq` del estado que se ve, sin envío optimista; una orden que llega mientras se guarda otra espera; 409, 422 y los demás errores con sus mensajes, y «Volver a aplicar» tras un 409.

- **Con un hueco elegido, el grupo «Insertar antes o borrar» pasa a ser «Hueco»** con los mismos tres botones y las mismas teclas: **«Nota» o N** escribe una nota en él, **«Silencio» o S** lo hace un silencio que se ve y **«Borrar» o Supr/Retroceso** lo borra (lo que lo sigue se adelanta). Un hueco no tiene figura dibujada: antes de él y en él son el mismo sitio, así que no se ofrece insertar antes de un hueco (se escribe en él, o se acorta con la figura y se escribe).
- **La nota escrita** lleva la figura del hueco y la altura de la nota anterior de su voz en el compás o, si no la hay, la de la siguiente; sin ninguna, la de la línea central de la clave con la alteración de la armadura, como al insertar ante un silencio (ADR-0033 §3). Se corrige después con un paso. **Queda elegida**, como tras un cambio de valor (ADR-0030 §6).
- **Lo que un hueco no admite** (la altura, la alteración, las articulaciones, el calderón, añadir una nota al acorde o ligar) se rechaza sin enviar nada: «Un hueco no tiene altura ni marcas: escribe antes una nota en él (N) o hazlo un silencio (S).». Su figura se cambia con la barra como la de un silencio.
- **Una orden en espera (ADR-0038)** se planea sobre lo que esté elegido cuando le toca: dos N seguidas sobre un hueco escriben una nota en él y después insertan otra antes de esa nota.
- **Tras borrar (enmienda ADR-0033 §5)** queda elegido lo que ocupa su sitio, también un hueco; deshacer y rehacer eligen el evento de la edición también si es un hueco (enmienda ADR-0034 §7).
- **Tras un 409**, «Volver a aplicar» escribe lo mismo en el hueco llevado al estado recargado; si ya no es un hueco, lo dice y no envía nada.
- **La historia** las dice: «Fa sostenido 4 en el hueco», «silencio en el hueco», «vuelta al hueco» (la compensatoria), «borrado de un hueco de semicorchea».
- **La indicación** bajo los controles dice qué es un hueco y qué se puede hacer con él, y la leyenda de teclas, que N y S escriben en él.

### 5. Contrato y migración

Ampliación compatible del contrato v1: `EditOp` gana `SetEventKind` en `openapi.json` y `types.ts` (regenerados). Ningún campo ni ninguna respuesta cambian. No hay migración: el log guarda `op` como texto y `before`/`after` como JSON.

## Consecuencias

### Positivas
- **TS-03 se corrige entera desde la vista**, contra la API real con HOMR (2026-11-02, sesión local en `127.0.0.1:8317`): 28 ediciones con el teclado y el ratón (escribir el Fa#4 en el hueco del c. 1 de la voz y bajarlo un paso, borrar los otros seis huecos, escribir desde su hueco la segunda voz de la mano derecha del c. 2 y ligarla, corregir su primera voz, añadir el Re5 al último acorde, ligar el acorde de la mano izquierda del c. 2 y poner 6/8 en las dos partes), más un deshacer y un rehacer. El estado final coincide con la verdad del banco en todo lo que se ve (inicio, clase, altura, figura y ligadura de cada evento de los tres pentagramas, sin mirar el número de voz) y en la clave, la armadura y el compás que rigen cada compás, sin ningún silencio invisible.
- Cada orden es una edición y un paso de deshacer; las anclas no se mueven al escribir en un hueco.
- La partitura dibujada y la descarga no cambian: el hueco se señala en la capa de la vista.
- Las cifras de `results/`, el corpus, los rasgos de la capa y la cobertura de `exp_02` no cambian; las métricas de esfuerzo siguen con tres clases.

### Negativas / Riesgos
- Depende de que OSMD 2.2.1 guarde y pinte transparente el silencio invisible (`PrintObject`, `getSVGGElement`): subir de versión exige comprobarlo (ADR-0027, Negativas).
- La caja del hueco es la del glifo transparente que VexFlow sitúa: en una segunda voz puede quedar por debajo del pentagrama, donde VexFlow pone los silencios de la voz inferior (en TS-03, el hueco de la segunda voz de la mano derecha del c. 2 queda entre los dos pentagramas del piano).
- Un hueco cuyo silencio transparente OSMD no guarda, o que no cuadra con lo que guarda, no se ofrece, como antes.
- Desde la vista no se inserta antes de un hueco; se escribe en él o se acorta.
- Las métricas de esfuerzo cuentan `SetEventKind` como contenido, aunque `CONTENT_EDIT_OPS` no la incluya: quien separe las ediciones por operación debe saberlo.
- No está comprobado con un lector de pantalla real ni en un móvil físico; sí con la emulación del navegador a 1440 y 390 px.

## Alternativas consideradas

1. **Borrar el hueco e insertar una nota (dos ediciones).** Descartada: dos pasos de deshacer y dos viajes por una decisión, con una mitad que puede fallar (§2).
2. **`SetPitch` sobre un silencio lo convierte en nota.** Descartada: cambia el significado de una operación de contenido que deriva `derive_edit_events` y mide `exp_02`, y no dice cómo hacerlo visible sin nota.
3. **Una operación general para cambiar cualquier evento de clase** (una nota en silencio, un silencio en nota). Descartada para esta entrega: la nota tiene ligadura, acorde y marcas que habría que decidir qué hacer con ellos; aquí solo hace falta el hueco, que no tiene ninguna.
4. **Dibujar el hueco en la partitura** (un silencio gris o un signo propio en el MusicXML que se dibuja). Descartada: la partitura ganaría un signo que no tiene, distinto de lo que se descarga, y OSMD ya guarda la posición en el silencio transparente.
5. **Ofrecer insertar antes de un hueco y escribir en él con botones distintos.** Descartada: cinco botones no caben en una fila a 390 px y, sin figura dibujada, «antes» y «en» son el mismo sitio.
6. **Rellenar los huecos al importar** (quitarlos o hacerlos visibles). Descartada: cambiaría la lectura de ADR-0032 y los documentos de HOMR, y el hueco a veces es correcto (una voz que entra a mitad del compás).
