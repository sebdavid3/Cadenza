# ADR-0028: Notas sin duración como notas de adorno en el MusicXML

- **Estado:** Aceptado
- **Fecha:** 2026-10-23
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0021 y ADR-0027, CLAUDE.md §9)
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
- El MIDI se sigue generando.
- OSMD dibuja la nota de adorno en la columna de la nota siguiente, antes de ella, con `IsGrace`. Si va al final del compás, la dibuja después de la última nota.
- VexFlow anida el SVG de la nota de adorno en los modificadores de la nota a la que adorna.

## Decisión

1. **Una nota o un acorde de duración cero o nula se escribe como nota de adorno.** Se usa music21 `getGrace()`, que da `<grace/>` con la figura por defecto y la barra. La nota no adelanta el instante de la siguiente, así que lo dibujado suma lo mismo que el `ScoreIR`, el mapa de tiempos y el validador.
2. **Un silencio de duración cero o nula sigue saliendo como silencio de negra.** MusicXML no tiene silencios de adorno, y HOMR no los da en el corpus medido.
3. **La selección de notas (ADR-0027) lo sigue.** A una nota sin duración le corresponde exactamente una figura de adorno, con sus alturas y sin sumar tiempo; a un silencio sin duración, un silencio de negra. La caja de cada nota es la de su cabeza propia: no la de las notas de adorno que VexFlow anida en ella ni la de sus puntillos.
4. **Dibujar ahora la negra de antes es un desajuste.** Si una nota sin duración aparece dibujada como negra (un exportador anterior), el emparejamiento la da por no coincidente y la selección no se ofrece.

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
- **MIDI.** Lo que hace music21 con una nota de adorno al escribir el MIDI no se ha escuchado. La reproducción de la vista no usa el MIDI (ADR-0026).
- **Silencio de duración cero.** Sigue dibujándose como negra, sin correspondencia exacta.

## Alternativas consideradas

1. **Escribirla con una duración mínima (una semifusa).** Descartada: seguiría sumando tiempo al compás e inventaría una duración.
2. **No escribirla.** Descartada: la nota existe en el `ScoreIR` y debe poder verse y elegirse para corregirla.
3. **Dejar la negra y avisar.** Descartada: es lo que hacía D60. El dibujo contradice la duración del compás justo donde el validador puede señalar un posible error.
