# ADR-0028: Notas sin duración como notas de adorno en el MusicXML

- **Estado:** Aceptado
- **Fecha:** 2026-10-23
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0021 y ADR-0027, CLAUDE.md §9)
- **Enmendado por:** la enmienda de [#404](https://github.com/sebdavid3/Cadenza/issues/404) (al final): las notas de adorno se escriben desde la vista
- **Relacionado:** [ADR-0021](ADR-0021-visualizacion-de-la-transcripcion-y-marcado-de-hallazgos.md), [ADR-0027](ADR-0027-seleccion-de-notas-sobre-la-partitura.md), D60, [#152](https://github.com/sebdavid3/Cadenza/issues/152), [#199](https://github.com/sebdavid3/Cadenza/issues/199)

---

## Contexto

El spike de [#182](https://github.com/sebdavid3/Cadenza/issues/182) (ADR-0027) encontró que `score_ir_to_musicxml` escribía como negra una nota de duración cero o nula (D60). Hay dos causas distintas:

- **Duración cero:** music21 ignora `quarterLength=0` y pone su duración por defecto.
- **Duración nula:** la cambia por 1 el propio exportador (`_build_voice_elements`).

En ninguno de los dos casos la figura suma tiempo para el `ScoreIR`: el mapa de tiempos (`compute_timing_map`) y el validador cuentan una duración nula o cero como 0, y la reproducción no toca esas notas. La partitura dibujada mostraba, por tanto, un compás más lleno que el transcrito.

**Datos medidos.** Hay 13 notas de duración 0 en 7 de 99 sesiones reales de HOMR 0.7.0, sin ninguna de duración nula. Todas son notas, ninguna es un silencio, y suelen preceder a otra nota (por ejemplo, Sol#4 antes de La4). Es la forma en que HOMR deja una nota de adorno: music21 la importa con `quarterLength` 0. Esto no se ha comprobado contra las imágenes una por una.

**Spike del 2026-10-23**, con music21 y OSMD 2.2.1 fuera del repositorio:

- Con `getGrace()`, music21 escribe `<grace slash="yes"/>`, sin `<duration>`.
- La importación devuelve duración 0, también para la que era nula.
- El MIDI se genera, pero music21 escribe el note-off de una nota de duración 0 antes que su note-on, en el mismo instante: la nota de adorno se queda sonando sin fin. Con un acorde de adorno, quedan todas sus notas.
- OSMD dibuja la nota de adorno en la columna de la nota siguiente, antes de ella, con `IsGrace`. Si va al final del compás, la dibuja después de la última nota.
- VexFlow anida el SVG de la nota de adorno en los modificadores de la nota a la que adorna.

## Decisión

1. **Una nota o un acorde de duración cero o nula se escribe como nota de adorno.** Se usa music21 `getGrace()`, que da `<grace/>` con la figura por defecto y la barra. La nota no adelanta el instante de la siguiente, así que lo dibujado suma lo mismo que el `ScoreIR`, el mapa de tiempos y el validador.
2. **Un silencio de duración cero o nula sigue saliendo como silencio de negra.** MusicXML no tiene silencios de adorno, y HOMR no los da en el corpus medido. Ocupa el tiempo de la negra que se escribe, de modo que una nota de adorno que lo siga no se adelanta a él.
3. **El MIDI deja fuera las notas de adorno.** No ocupan tiempo y la vista no las reproduce (ADR-0026); dentro del MIDI quedarían sonando sin fin.
4. **La selección de notas (ADR-0027) lo sigue.** A una nota sin duración le corresponde exactamente una figura de adorno, con sus alturas y sin sumar tiempo; a un silencio sin duración, un silencio de negra. La caja de cada nota es la de su cabeza propia: no la de las notas de adorno que VexFlow anida en ella ni la de sus puntillos.
5. **Dibujar ahora la negra de antes es un desajuste.** Si una nota sin duración aparece dibujada como negra (un exportador anterior), el emparejamiento la da por no coincidente y la selección no se ofrece.

## Consecuencias

### Positivas
- La partitura dibujada y el MusicXML descargado ya no muestran negras que el `ScoreIR` no tiene. El compás suma lo que dice el validador.
- La importación conserva la duración cero.
- Medido el 2026-10-23 con el código de este cambio, sobre las mismas 99 sesiones de ADR-0027 y a 1100 y 340 px, sin escribir en `results/`:
  - el mapa sale completo en las 99 sesiones y empareja 1534 de 1534 eventos;
  - el MusicXML lleva 13 notas de adorno, y cada una de las 13 notas de duración 0 empareja con la suya;
  - las 1331 cabezas, también las de adorno, caen en su línea o espacio, con un desvío máximo de 0,001 unidades.

### Negativas / Riesgos
- **Figura y barra de adorno.** El `ScoreIR` no guarda la figura ni si la nota de adorno lleva barra. Se escribe con la de music21 (negra con barra), que puede no ser la del original.
- **Duración nula.** Una duración nula, que no es lo mismo que cero, también se dibuja como nota de adorno, y al reimportarla queda en 0.
- **MIDI.** Las notas de adorno no suenan en el MIDI exportado, tampoco en su descarga (#189). Se comprueba leyendo el MIDI de vuelta: ninguna nota se queda sin soltar. Nadie lo ha escuchado.
- **Navegación.** Una nota de adorno empieza en el mismo instante que la nota a la que adorna: al pasar de voz o de pentagrama con ↑ y ↓, el empate se resuelve a favor de la nota.
- **Silencio de duración cero.** Sigue dibujándose como negra, sin correspondencia exacta.

## Alternativas consideradas

1. **Escribirla con una duración mínima (una semifusa).** Descartada: seguiría sumando tiempo al compás e inventaría una duración.
2. **No escribirla.** Descartada: la nota existe en el `ScoreIR` y debe poder verse y elegirse para corregirla.
3. **Dejar la negra y avisar.** Descartada: es lo que hacía D60. El dibujo contradice la duración del compás justo donde el validador puede señalar un posible error.

## Enmienda de #404 (2026-11-11): las notas de adorno se escriben desde la vista

**El problema.** Las notas de adorno que lee HOMR se importan, se dibujan, se eligen, se validan y se exportan, y se les puede cambiar la altura, borrarlas o devolverlas a nota normal eligiendo una figura. Pero ninguna edición podía crear una: `check_duration` exigía `0 < duración` en `InsertEvent` y `SetDuration`. Si HOMR no ve una nota de adorno, no se podía añadir, y el error no aparecía en el corpus de correcciones. Si la lee como nota normal, solo se podía borrar, y el corpus lo contaba como una nota sobrante en lugar de «era un adorno». El responsable decidió el 2026-11-11 que se puedan escribir, para que esos errores de HOMR queden bien registrados.

**Decisión.**

1. **El dominio admite la duración 0 en una nota.** `InsertEvent` y `SetDuration` aceptan `duration_beats` 0 (`check_duration(..., allow_grace=True)`), pero solo en una nota visible (no en un silencio ni en un hueco), sin ligadura de prolongación y fuera de un acorde. Una nota con `is_chord` tampoco se añade a una nota de adorno de duración 0 (antes solo se impedía con la nula). La nota que ya es de adorno no se vuelve a convertir. El resto de usos de `check_duration` (`SetTuplet`, `SetChordDuration`, rellenar un hueco) siguen exigiendo una duración positiva. Deshacer es exacto en los dos sentidos, porque la compensatoria intercambia `before` y `after`, como en cualquier `SetDuration`.
2. **En la barra, un conmutador «Nota de adorno» en el grupo «Figura».** Con una nota elegida, la convierte en nota de adorno; con una nota de adorno, la devuelve a **corchea**, la figura con que la dibuja el exportador (§1). Está pulsado cuando la nota elegida es de adorno. Con un silencio, una nota de un acorde o una nota ligada, pulsarlo dice por qué no se puede, en lugar de no hacer nada. El botón no está en el modo «Escribir» (#350), donde la barra elige con qué figura se escribe y las notas de adorno no se escriben con el ratón; G y Mayús+G siguen valiendo en ese modo, como las demás teclas.
3. **Teclas: G y Mayús+G.** G hace lo mismo que el conmutador. Mayús+G inserta una nota de adorno con la altura de la nota elegida, antes de ella (antes del acorde entero, si es de un acorde), y la deja elegida para subirla o bajarla. Con el ratón se llega a lo mismo con «Nota» (que inserta una copia de la nota antes de ella, ADR-0033) y después el conmutador. No hay un botón aparte para insertarla: en la mesa (#363), la paleta de la pestaña «Nota» cabía justa a 1440 px (975 de 982 px), y un botón con texto la habría desbordado en 123 px. El conmutador, de 32 px, la desborda en 28, que se recorren con el desplazamiento horizontal que la paleta ya tiene.
4. **Cómo se nombra.** La barra y el anuncio dicen «Sol4 · nota de adorno» (antes, «sin duración»); el historial, «nota de adorno» para la conversión e «inserción de Sol 4, nota de adorno» para la inserción.

5. **Lo vecino también reconoce la duración 0** (lo trajo la revisión independiente). El tresillo (`SetTuplet`) y la ligadura de prolongación (`SetTie`, `following`) solo trataban como adorno la duración nula, y HOMR da las notas de adorno con duración 0: un tresillo que contuviera una respondía 422 (o 500, si el cliente le daba una figura), y la ligadura la tomaba por la nota siguiente. Ahora, en el dominio y en la web, una nota de duración 0 o nula no ocupa tiempo en los dos: el tresillo la deja sin figura (`null` o `0`) y la ligadura la salta y no la liga. «Ya es de adorno» reconoce también la nula. Una nota tampoco se inserta ante una nota con `is_chord` que sigue a un silencio, porque se la llevaría a su acorde (y, de adorno, el exportador dibujaría el acorde entero como adorno). «Volver a aplicar» tras un 409 repasa las mismas reglas que el conmutador, sin alternar.

**Lo que no cambia.** No se guardan la figura ni la barra de la nota de adorno (la apoyatura y la acciaccatura siguen siendo iguales), no hay acordes de adorno desde la barra, las notas de adorno siguen sin sonar (ADR-0026) y la importación no cambia. El corpus de correcciones no necesitó cambios: `derive_edit_events` ya derivaba `SetDuration` a 0 e `InsertEvent` con duración 0, y `build_correction_records` los registra con `duration_beats: "0"`.

**Consecuencias.**

- Los dos errores de HOMR con las notas de adorno (la que no ve y la que lee como nota normal) se corrigen desde la vista y llegan al corpus como una inserción y una corrección de figura con duración 0. Lo prueban `packages/domain/tests/test_grace_note_edits.py`, `packages/learning/tests/test_correction_corpus.py` y `apps/api/tests/test_api_edit_payload.py`.
- Comprobado en local el 2026-11-11 con una sesión de `TS-04` transcrita con HOMR 0.7.0: la nota de adorno del compás 1 vuelve a corchea y otra vez a adorno con G; Mayús+G inserta un Sol4 de adorno antes de la nota siguiente; Ctrl+Z lo deshace; el MusicXML exportado lleva las dos `<grace/>` y el MIDI se exporta.
- **La barra de la mesa ya no cabe entera a 1440 px** en la pestaña «Nota»: el final del grupo «Acorde y prolongación» queda tras el desplazamiento horizontal. En un móvil, el noveno botón de «Figura» tampoco cabe en la fila de 390 px y se alcanza desplazando la paleta (la página no se desplaza).

