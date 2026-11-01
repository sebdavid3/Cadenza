# ADR-0046: Cada parte suena con su instrumento en la vista, sintetizado y sin muestras

- **Estado:** Aceptado
- **Fecha:** 2026-10-31
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0026, ADR-0038 y ADR-0041, CLAUDE.md §9)
- **Enmienda:** [ADR-0026](ADR-0026-reproduccion-de-la-partitura-en-el-navegador.md) §3 (el sintetizador de ADR-0026 pasa a ser el sonido del piano y de las partes sin instrumento; las demás partes suenan con el de su instrumento) y [ADR-0041](ADR-0041-titulo-compositor-e-instrumentos-de-la-sesion.md) §2 (sin muestras, cada instrumento suena con su sonido sintetizado; solo «otro» y las partes sin instrumento suenan como el piano)
- **Relacionado:** [ADR-0026](ADR-0026-reproduccion-de-la-partitura-en-el-navegador.md), [ADR-0038](ADR-0038-redibujar-tras-una-edicion-y-ordenes-en-espera.md), [ADR-0041](ADR-0041-titulo-compositor-e-instrumentos-de-la-sesion.md), [#242](https://github.com/sebdavid3/Cadenza/issues/242), [#235](https://github.com/sebdavid3/Cadenza/issues/235), [#215](https://github.com/sebdavid3/Cadenza/issues/215)

---

## Contexto

Hechos comprobados en el código el 2026-10-31:

- **Un solo sonido.** La vista reproduce todas las partes con el mismo `PolySynth` de Tone.js 15.1.22 (`pages/session/toneEngine.ts`): onda triangular, ataque de 10 ms, caída de 120 ms, sostenimiento de 0,4, liberación de 200 ms y −10 dB (ADR-0026 §3).
- **Cada parte tiene ya su instrumento** (#235, ADR-0041): `SessionViewRead.instruments` es una lista de `PartInstrumentRead`, en la que la entrada `i` es la parte `i` de `current_score`. La lista de instrumentos es cerrada y solo crece: `piano`, `voice`, `violin`, `cello`, `flute`, `clarinet`, `guitar` y `other`. `other` suena como el piano, y ADR-0041 deja a #242 qué muestras tiene cada uno; un instrumento sin muestras suena como el piano.
- **Cada nota sabe ya de qué parte es.** `buildPlayback` une el mapa de tiempos con las alturas por ancla (ADR-0026 §1), y el ancla lleva `part`.
- **CSP de producción** (`deploy/nginx/cadenza.conf`): `default-src 'self'`, `script-src 'self'` y `connect-src 'self'`, sin `worker-src` ni `media-src` propios. Unas muestras tendrían que servirse desde el propio servidor.
- **No hay muestras de sonido en el repositorio.** Tampoco hay ningún `.mp3`, `.ogg`, `.wav` ni `.sf2`. Descargar unas exige el permiso del responsable: la licencia, la atribución y el peso son decisión suya.
- **Lo que hay en Tone.js sin muestras ni Worklets.** El `Synth` con osciladores básicos o «gordos» (`fattriangle`: varias ondas desafinadas entre sí), el `Filter`, un `BiquadFilterNode` nativo, y el `Vibrato`, un `LFO` sobre un `Delay`. Ninguno usa `AudioWorklet`, que se carga desde `blob:` como el Worker del reloj; sí lo usan, por ejemplo, `BitCrusher`, `Freeverb` y `JCReverb`.

## Decisión

1. **Un sonido por instrumento, sintetizado con Tone.js y sin muestras.** No se descarga ni se sirve ningún archivo de audio. El sonido de cada parte sale de su instrumento:
   - `soundOf` en `pages/session/sounds.ts`;
   - la tabla `SOUNDS`, con datos que se prueban sin audio.

   | Instrumento | Onda | Ataque, caída, sostenimiento y liberación | Volumen | Paso bajo | Vibrato |
   |---|---|---|---|---|---|
   | `piano`, `other`, sin instrumento | triangular | 10 ms, 120 ms, 0,4, 200 ms | −10 dB | — | — |
   | `voice` | triangular «gorda» (3 ondas, 20 cents) | 100 ms, 200 ms, 0,85, 350 ms | −12 dB | 1800 Hz | 5 Hz, 0,15 |
   | `violin` | diente de sierra | 50 ms, 100 ms, 0,9, 250 ms | −16 dB | 3500 Hz | 5,5 Hz, 0,12 |
   | `cello` | diente de sierra | 70 ms, 100 ms, 0,9, 300 ms | −14 dB | 1500 Hz | 5 Hz, 0,1 |
   | `flute` | senoidal | 40 ms, 100 ms, 0,85, 200 ms | −8 dB | — | 4,5 Hz, 0,08 |
   | `clarinet` | cuadrada | 30 ms, 100 ms, 0,9, 150 ms | −18 dB | 2200 Hz | — |
   | `guitar` | triangular | 2 ms, 1,2 s, 0, 400 ms (se apaga sola) | −8 dB | 3000 Hz | — |

   El piano es el sintetizador de ADR-0026 tal cual: una sesión sin instrumentos suena como antes. Los demás se distinguen por cómo entran (suave o de golpe), si se sostienen o se apagan solos, su timbre (la onda y el filtro) y su vibrato. **No imitan de cerca el instrumento real.** Sirven para reconocer qué parte suena y para oír las voces por separado. El vibrato de Tone mueve un retardo de hasta 5 ms: una profundidad de 0,1 a 5 Hz es una oscilación de unos ±13 cents, y la de la tabla va de unos ±10 cents (flauta) a unos ±18 (violín) y ±20 (voz).
2. **Las notas llevan su sonido.** `PlayedNote.sound` lo fija `buildPlayback(score, timing, instruments)` con el instrumento de la parte de su ancla (`instruments[anchor.part]`). Una parte sin entrada, con la entrada sin instrumento, con `other` o con un instrumento que esta versión no conoce (la lista solo crece, ADR-0041) suena como el piano. El mapa de tiempos, los compases, el final y la unión de ligaduras no cambian.
3. **Una cadena de audio por sonido en el motor.** Cada sonido tiene su `PolySynth` (16 notas a la vez), su filtro y su vibrato si los tiene, y su ganancia, por la que se funde (ADR-0026 §5): sintetizador → filtro → vibrato → ganancia → salida. La cadena se crea al programar la primera nota de ese sonido, ya dentro del motor que nace con el primer «Reproducir». Pausar, detener y salir funden y liberan todas las cadenas con sus efectos; pausar y detener crean de inmediato las de los sonidos de la partitura, como ADR-0026 hacía con su única voz.
4. **Cuándo se carga.** Lo único que se descarga es el trozo de Tone.js al abrir la vista, como en ADR-0026 §4. Mide 247,07 kB, o 61,81 kB con gzip (antes, 235,60 y 59,51 kB, en el mismo build): el `Filter` y el `Vibrato` añaden 11,5 kB, o 2,3 kB con gzip. Las voces se crean al pulsar «Reproducir», no al abrir la vista. No hay muestras que pedir, así que no hay espera ni fallo de carga propios de un instrumento.
5. **La CSP no cambia.** Sin muestras no hay peticiones de audio, y ninguno de los nodos usados carga un `AudioWorklet` desde `blob:`. Funciona sin red externa.
6. **Una edición sigue sonando** (ADR-0038 §8). `update` vuelve a programar desde el último pulso disparado, como antes, y cada nota busca la cadena de su sonido al sonar. Si el instrumento de una parte cambia mientras suena (otro estado del detalle tras un `PATCH`), lo que sigue suena con el nuevo y lo que ya sonaba termina con su caída. La cadena que queda sin uso se libera al pausar, al detener o al salir, y no se vuelve a crear.

## Consecuencias

### Positivas

- La voz y el piano de una página como *Mondnacht* se oyen por separado, cada uno con lo suyo, sin pesos nuevos, sin licencias ni atribuciones, y sin tocar la CSP ni el contrato.
- Una sesión sin instrumentos suena exactamente como antes.
- Se prueba sin audio: qué cadena recibe cada nota, con qué onda, envolvente y volumen, por qué filtro y vibrato y en qué orden van conectados; que los compases y el final no cambian; y la pausa, la edición mientras suena, la cadena que deja de usarse y la liberación con varios sonidos.

### Negativas / Riesgos

- **Nadie lo ha escuchado.** Un navegador sin interfaz no oye. Quedan por comprobar a mano:
  - que cada instrumento se reconozca;
  - el equilibrio de volumen entre partes (los decibelios de la tabla compensan a ojo lo fuerte que suena cada onda);
  - que el vibrato no suene desafinado;
  - que la guitarra no se apague demasiado pronto en notas largas;
  - el móvil.
- No es el timbre real: la voz no canta vocales y el violín no tiene el ruido del arco. Para eso harían falta muestras (abajo).
- Cada sonido con vibrato y filtro son unos nodos de audio más por parte (el oscilador del vibrato sigue en marcha durante la pausa); en un equipo lento, una página con varias partes podría consumir algo más. No se ha medido.

## Alternativas consideradas

1. **Muestras grabadas con el `Sampler` de Tone.js, servidas desde el propio servidor.** Es lo que pedía #242 y suena más real. Pendiente: exige descargar audio de terceros, y eso lo decide el responsable, que no lo ha autorizado en este cambio. Para decidirlo, haría falta:
   - **Elegir las fuentes y comprobar su licencia y su atribución.** Candidatas, todas a confirmar antes de descargar:
     - el piano Salamander Grand Piano de Alexander Holm (CC BY 3.0 en su versión 3; hay que comprobar si la vigente es de dominio público);
     - los instrumentos de VSCO 2 Community Edition de Versilian Studios (CC0), con cuerdas y maderas, pero que no parece tener coro;
     - los sonidos de la fuente General MIDI FluidR3_GM de Frank Wen, que son los únicos de la lista con coro («Choir Aahs», el programa 53 de ADR-0041), con su licencia por comprobar en la distribución que se use.
   - **Fijar su peso.** Una muestra cada tres semitonos en la tesitura de cada instrumento (de 10 a 16 archivos) y en OGG o MP3 son, a ojo, de unos cientos de kB a 1 MB por instrumento, que hay que medir. Se pedirían al pulsar «Reproducir» y solo para los instrumentos de la sesión, con una espera y un fallo de carga propios.
   - **Servirlas desde `apps/web/public`.** Con `connect-src 'self'` la CSP no cambia.
   - **Mantener la tabla de este ADR** como reserva para los instrumentos sin muestras y para cuando no lleguen.
2. **Un sonido para el piano y otro para todo lo demás.** Descartada: cumple el mínimo de #242 (el piano y la voz), pero los otros cinco instrumentos de la lista sonarían igual, y distinguirlos cuesta solo una fila de la tabla.
3. **`PluckSynth` para la guitarra (Karplus-Strong).** Descartada: no es una voz `Monophonic` y no cabe en un `PolySynth`, así que dos notas a la vez exigirían otra forma de gestionar las voces. La envolvente que se apaga sola basta para reconocerla.
4. **Reverberación (`Freeverb`, `JCReverb`).** Descartada: usan `AudioWorklet` desde `blob:`, que la CSP de producción bloquearía como el Worker del reloj (ADR-0026).
