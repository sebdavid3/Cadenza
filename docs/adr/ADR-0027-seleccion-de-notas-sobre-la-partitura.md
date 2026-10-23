# ADR-0027: Selección de notas sobre la partitura dibujada

- **Estado:** Aceptado
- **Fecha:** 2026-10-23
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0006, ADR-0011 y ADR-0021, CLAUDE.md §9)
- **Relacionado:** [ADR-0006](ADR-0006-render-editor-osmd-verovio-zustand.md), [ADR-0011](ADR-0011-semantica-de-anclas-ante-ediciones.md), [ADR-0021](ADR-0021-visualizacion-de-la-transcripcion-y-marcado-de-hallazgos.md), [ADR-0026](ADR-0026-reproduccion-de-la-partitura-en-el-navegador.md), [INV-0001](../investigaciones/INV-0001-salidas-internas-homr-bbox-y-confianza.md), D11, [#152](https://github.com/sebdavid3/Cadenza/issues/152), [#182](https://github.com/sebdavid3/Cadenza/issues/182)

---

## Contexto

La corrección sobre la partitura empieza por elegir un evento concreto (una nota o un silencio) y obtener su ancla (`AnchorPayload`), que es lo que llevan las ediciones ([#183](https://github.com/sebdavid3/Cadenza/issues/183)). ADR-0006 pide un mapa ancla→elemento SVG sobre OSMD. La vista de una sesión ya sitúa compases (`measureBox`, ADR-0021) pero no notas.

Restricciones:

- HOMR devuelve siempre `bbox: null` (INV-0001): la selección sale de la notación dibujada, no de la imagen.
- OSMD 2.2.1 dibuja el MusicXML de `GET /sessions/{id}/export`, no el `ScoreIR`. Desde #152 el exportador reproduce el `ScoreIR` compás a compás, pero escribe un acorde como una figura, parte en notas ligadas una duración que no cabe en una figura y no conserva anclas.
- El `event_index` de un ancla cuenta los eventos de su voz dentro del compás (`compute_timing_map` y `build_anchor_index`).
- OSMD no expone el ancla de una nota: hay que leer su modelo gráfico (`GraphicalMeasure.staffEntries[].graphicalVoiceEntries[].notes[]`, con `sourceNote`) y el SVG que dibuja VexFlow.

**Spike del 2026-10-23.** Se exploró el modelo gráfico de OSMD en la consola de la vista local y después se midió con el código de este ADR (`osmd.ts` y `noteMap.ts` importados desde el servidor de Vite), sin escribir en `results/`:

- **Corpus.** Una base local nueva con HOMR 0.7.0 en GPU. Por la vista de transcripción se subieron las 100 imágenes de `data/manifest.json` (HOMR transcribió 91 y no reconoció las otras 9, la línea base conocida) y 10 incipits de PrIMuS con ligaduras en su referencia (transcribió 8). En total, 99 sesiones sin ediciones.
- **Método.** Para cada sesión y a dos anchos (1100 px, zoom 1, y 340 px, zoom 0,75): se dibuja el MusicXML con `renderScore`, como la vista; se comprueba que OSMD dibuja los mismos compases que el `ScoreIR` (ADR-0021); se construye el mapa con `buildNoteMap` y se cuentan los eventos emparejados. Como comprobación independiente, el centro de la caja de cada nota emparejada ha de caer en la línea o el espacio de su altura según la clave activa (±0,25 unidades), y las cajas de cada voz han de avanzar de izquierda a derecha en el orden del `ScoreIR`.
- **Resultado.** El mapa es completo en las 99 sesiones a los dos anchos: 1534 de 1534 eventos, 1331 de 1331 notas y 203 de 203 silencios. Por duración, todas al 100 %: 0 (13 eventos), 1/16 (12), 1/8 (52), 1/4 (307), 3/8 (15), 1/2 (529), 3/4 (31), 1 (280), 3/2 (47), 2 (176), 3 (34), 4 (37) y 11/2 negras (1).
  - Las 1331 cabezas caen en su línea o espacio, con un desvío máximo de 0,001 unidades.
  - Orden: ninguna inversión a 1100 px y una a 340 px. Es un compás sobrellenado por HOMR (4¼ negras en un 3/4) que OSMD comprime y dibuja con figuras superpuestas.
- **Lo que las sesiones reales no traen.** HOMR 0.7.0 no dio acordes, ligaduras, varias voces ni varios pentagramas en este corpus (ninguna ligadura, tampoco en los 8 incipits que la tienen en la referencia). Se comprobaron con 10 partituras construidas con el exportador real: acorde con las alturas desordenadas, ligaduras dentro del compás y entre compases, figuras partidas (5/4 y 5/2 negras), tresillo, dos voces, piano con dos pentagramas, dos partes, cambio de clave y armadura, compás vacío, incompleto y sobrellenado, duración nula o cero y unísono en un acorde. Todas emparejan. Es una comprobación del comportamiento de OSMD, no una medición.
- **Hallazgos sobre OSMD y el exportador.**
  - OSMD ordena las notas de un acorde de grave a agudo, no en el orden del `ScoreIR`.
  - OSMD guarda aparte la parte entera de una duración: 11/8 de redonda es `WholeValue` 1 más 3/8.
  - Un evento de duración cero se dibuja como una negra, porque music21 ignora `quarterLength=0` (13 notas en 7 de las 99 sesiones; D60).
  - La posición que OSMD da a una nota es el centro de su cabeza: en las 91 sesiones del manifiesto, con un desvío de 0,09 unidades o menos en horizontal y ninguno en vertical. Para un silencio da solo un punto de referencia, no la extensión de su glifo, que según la figura mide de 0,5 a 2,9 unidades de alto.
- **Densidad.** A 340 px, entre figuras consecutivas de un mismo sistema hay una mediana de 26,2 px, un p10 de 16 px y un mínimo de 0 px (las superpuestas), sobre 1283 separaciones. 1117 (87 %) están por debajo de 44 px y 527 (41 %) por debajo de 24 px. 96 de las 99 sesiones ocupan más de un sistema.

## Decisión

1. **Emparejamiento por voz, clase, duración y altura, imitando al exportador.**
   - Cada compás del `ScoreIR` se empareja con su compás dibujado (el de ADR-0021), voz con voz por el orden de su número.
   - Dentro de una voz, los eventos se agrupan como los escribe el exportador: un silencio solo, y una nota con las que la siguen marcadas como acorde (`is_chord`).
   - Cada grupo consume, en orden, las figuras dibujadas cuya duración suma la suya: una, o varias si el exportador la partió. Han de ser de su misma clase (nota o silencio) y, en las notas, de las mismas alturas, comparadas por número MIDI y nombre de nota para distinguir enarmonías. Las notas de un acorde se emparejan por altura.
   - Una duración nula o cero cuenta como una negra, que es como la escribe music21.
   - Ha de consumir todas las figuras de la voz, sin notas de adorno.
   - El ancla se construye como `compute_timing_map`: parte, pentagrama, número de compás, voz, `event_index` por voz y `staff_id`, con el `bbox` y la `confidence` del evento.
2. **Todo o nada.** Si un compás no cuadra, o un evento no es nota ni silencio con altura, el mapa no se ofrece: no se elige ninguna nota y la vista dice cuántos eventos no coinciden con lo dibujado. Si OSMD dibuja otros compases que el `ScoreIR`, tampoco. Las marcas por compás y la reproducción siguen igual. Como en ADR-0021, no se ofrece una selección dudosa.
3. **Geometría del SVG, recalculada en cada maquetación.**
   - La caja de una nota es la de su cabeza (`.vf-notehead`) dentro del elemento que da `getSVGGElement()` de VexFlow. En un acorde, es la cabeza más cercana a la altura en que OSMD sitúa la nota.
   - La de un silencio es la de su glifo entero.
   - Una figura partida tiene una caja por figura y la que las abarca.
   - Las cajas se miden relativas al contenedor de OSMD, el mismo origen que `measureBox`, y se recalculan cada vez que OSMD vuelve a maquetar (el contador `layout` de ADR-0021).
4. **Elegir con el puntero.** Un clic o un toque elige, entre los eventos del compás tocado, el más cercano en horizontal y, a igual distancia (las notas de un acorde), el más cercano en vertical. Fuera de los compases no elige nada. No hay un objetivo de 44 px por nota: a 340 px las notas distan menos (87 %). La alternativa equivalente (WCAG 2.5.8) son los botones «Anterior» y «Siguiente» de la barra, de 44 px, que llegan a cualquier evento.
5. **Elegir con el teclado.** La partitura es un único elemento enfocable con el anillo de foco del sistema:
   - ← y → recorren la voz y pasan de compás.
   - Ctrl o ⌘ más ← y →, o Re Pág y Av Pág, saltan al compás anterior o siguiente.
   - Inicio y Fin van al primer o al último evento de la voz en el compás.
   - ↑ y ↓ pasan por las voces del pentagrama y después a los pentagramas vecinos, al evento que empieza más cerca.
   - Esc quita la selección.
   - Sin nada elegido, la primera tecla elige el primer evento. En un borde, la selección se queda donde está.
   - Al moverse con el teclado o los botones, la nota se trae a la vista, sin desplazamiento suave con movimiento reducido. Al tocarla, no.
6. **Accesibilidad.**
   - Con el mapa completo, la partitura tiene `role="application"`, para que el lector de pantalla le pase las flechas. Su nombre es el de la imagen que era (con los compases con posibles errores) y la invitación a usar las flechas, y la leyenda de teclas la describe.
   - Lo elegido se anuncia en una región `aria-live` 300 ms después del último movimiento, con compás, voz, altura o silencio, duración y, si procede, pentagrama, «en acorde» y «ligada». Al moverse deprisa solo se anuncia dónde se detiene; al quitarla se anuncia «Sin nota elegida.».
   - Las alturas van en solfeo («Fa#5», dicho «Fa sostenido 5») y las duraciones con su nombre («corchea con puntillo», «negra de tresillo»).
7. **Estado.** La selección vive en Zustand (`useSelectionStore`, ADR-0006) como `{ sessionId, seq, anchor }`: el ancla es relativa a un estado (ADR-0011) y la vista solo la muestra para su sesión y su `seq`. Se olvida al salir de la sesión. Es lo que #183 usará para editar.
8. **Marca.** La nota elegida se marca con una caja de papel por detrás de su cabeza, un aro de papel y un filete violeta de 3 px, sin movimiento. Es violeta porque pide acción (`DESIGN.md`). Abre un hueco en la trama del compás dudoso y convive con el contorno de tinta del compás que suena (ADR-0026). Una franja propia entre el transporte y la partitura dice qué está elegido, con los pasos y la leyenda de teclas. En una pantalla táctil, la leyenda se oculta y, en una partitura estrecha, los pasos quedan como flechas.

## Consecuencias

### Positivas
- Cada evento del `ScoreIR` se elige sobre su figura dibujada y da su ancla, sin coordenadas del motor OMR.
- El emparejamiento no depende del orden en que OSMD guarda un acorde ni de cómo parte una duración.
- La comprobación geométrica independiente sitúa todas las notas de las sesiones reales en su línea o espacio.
- Si el exportador o OSMD cambian de forma que lo dibujado ya no cuadra, la vista deja de ofrecer la selección y lo dice, en lugar de elegir mal.
- Se prueba con Vitest sobre un doble de OSMD con la misma forma que lo que se lee.

### Negativas / Riesgos
- Depende de la estructura interna de OSMD 2.2.1 (`staffEntries`, `graphicalVoiceEntries`, `sourceNote`, `GetExpandedNumerator`, `getHalfTone`) y del SVG de VexFlow (`getSVGGElement`, `.vf-notehead`). Subir de versión exige repetir la medición. La versión ya está fijada.
- Imita reglas del exportador (agrupación de acordes y negra para la duración cero); si cambian, hay que cambiar el emparejamiento a la vez.
- En un compás sobrellenado y estrecho, OSMD puede superponer figuras. El mapa sigue siendo correcto, pero el toque elige la primera de las superpuestas; el teclado y los botones llegan a todas (1 de 1534 eventos a 340 px).
- En un unísono dentro de un acorde, las dos notas tienen la misma caja: cuál es cuál es indiferente para el dibujo, pero el toque elige la primera.
- La caja de una nota marca su cabeza, no la plica ni las alteraciones.
- Las sesiones reales no tienen acordes, ligaduras, voces ni varios pentagramas: esos casos están comprobados con el exportador y con pruebas, no medidos sobre transcripciones de HOMR.
- Elegir una nota no la edita todavía: eso es #183.

## Alternativas consideradas

1. **Emparejar solo por orden, sin comprobar clase, duración ni altura.** Descartada: una figura partida o un acorde desplazarían todas las anclas siguientes sin avisar.
2. **Ofrecer la selección en los compases que cuadran aunque otros no.** Descartada: una partitura con unas notas elegibles y otras no confunde, y lo que no cuadra suele señalar que el dibujo no es el `ScoreIR`.
3. **Cajas a partir de las unidades de OSMD, como `measureBox`.** Descartada: OSMD no da el tamaño de una nota y, para un silencio, ni su altura. El SVG da la caja exacta de lo dibujado.
4. **Un elemento enfocable por nota (`listbox` con `aria-activedescendant`).** Descartada: la navegación tiene más de un eje (voz, compás y pentagrama), y el lector de pantalla anunciaría cada paso intermedio. Con `application` y la región `aria-live` se anuncia dónde se detiene.
5. **Objetivos táctiles de 44 px por nota.** Imposible sin solaparse: a 340 px el 87 % de las notas consecutivas distan menos de 44 px. Se sustituye por el toque a la más cercana y los pasos de 44 px.
6. **Recolorear en violeta la nota elegida dentro del SVG.** Descartada: ata la marca al marcado de VexFlow y se pierde al volver a maquetar. Una capa propia por detrás de las notas basta.
