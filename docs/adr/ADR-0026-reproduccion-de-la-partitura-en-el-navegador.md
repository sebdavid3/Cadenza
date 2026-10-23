# ADR-0026: Reproducción de la partitura en el navegador

- **Estado:** Aceptado
- **Fecha:** 2026-10-23
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0006 y con la tabla de stack de `ARCHITECTURE.md`, CLAUDE.md §9)
- **Relacionado:** [ADR-0006](ADR-0006-render-editor-osmd-verovio-zustand.md), [ADR-0019](ADR-0019-base-del-cliente-web.md), [ADR-0021](ADR-0021-visualizacion-de-la-transcripcion-y-marcado-de-hallazgos.md), [ADR-0023](ADR-0023-despliegue-publico-con-tailscale-funnel.md), D11, D12, [#42](https://github.com/sebdavid3/Cadenza/issues/42), [#177](https://github.com/sebdavid3/Cadenza/issues/177)

---

## Contexto

La vista de una sesión (`/sesiones/:id`) dibuja la partitura con OSMD y marca los compases con posibles errores (ADR-0021). Falta escucharla, con el compás que suena resaltado sobre la notación. `ARCHITECTURE.md` y `frontend-handoff.md` fijan Tone.js con el cursor a partir de `GET /sessions/{id}/timing`. Había que decidir de dónde salen las notas, el tempo y el instrumento, y cómo encaja el reloj de Tone.js con la CSP de producción.

**Fuentes de notas candidatas.** `GET /sessions/{id}/timing` (`TimingMapRead`, #42) da, en negras y como fracciones exactas, el inicio de cada compás (`measure_offsets`) y de cada evento con su ancla, pero no las alturas. Las alturas están en `current_score` (`GET /sessions/{id}`), del mismo estado materializado. El `event_index` del ancla cuenta los eventos de su voz dentro del compás. La otra fuente es el MIDI de `GET /sessions/{id}/export?format=midi`, que genera music21 (`score_ir_to_midi`).

**Comparación de las dos fuentes.** Se hizo el 2026-10-23 con un script fuera del repositorio, sin escribir en `results/`. Se compararon las notas (inicio, altura MIDI y duración) del mapa de tiempos con las alturas del `ScoreIR`, uniendo las ligaduras, con las del MIDI exportado. La muestra fueron 47 sesiones reales sin ediciones de dos bases locales (HOMR 0.7.0, incipits de PrIMuS). Resultados:

- Hay 579 notas en cada fuente.
- Coinciden exactamente en 45 de las 47 sesiones.
- Las 2 restantes son la misma imagen, subida dos veces. Su compás 2 está incompleto (2,75 de 3 negras). El MIDI coloca los compases uno tras otro y adelanta 1/4 de negra todo lo que sigue. El mapa de tiempos conserva la rejilla de compases (un compás incompleto que no es el primero ocupa su métrica) y es el que ubica el compás que suena.
- El MIDI lleva 120 negras por minuto en las 47.

**CSP de producción.** `deploy/nginx/cadenza.conf` sirve `script-src 'self'` sin `worker-src`, así que un Worker desde `blob:` queda bloqueado. Tone.js 15.1.22 crea su reloj (`Ticker`) con un Worker desde `blob:` dentro de un `try/catch`. Medido en Chrome 152 con esa misma CSP:

- `new Worker(blob:)` **no lanza ninguna excepción**;
- se produce una violación `worker-src` y un error asíncrono;
- el Worker no llega a correr (0 tics en 1 s).

El `try/catch` no se entera, y el transporte de Tone se quedaría parado sin avisar. Además, el módulo principal de `tone` crea un contexto de audio con ese reloj en cuanto se importa.

**Gesto.** Los navegadores solo dejan sonar un contexto de audio creado o reanudado dentro de un gesto de la persona.

## Decisión

1. **Fuente de notas: el mapa de tiempos con las alturas de `current_score`** del mismo estado (`seq`), unidas por ancla en el cliente (`buildPlayback`).
   - Las notas ligadas de la misma voz y altura que se tocan suenan como una sola, también de un compás al siguiente.
   - Las notas de un acorde suenan a la vez.
   - Los silencios y las notas sin una altura que se entienda no suenan.
   - El cliente no lee el MIDI.
2. **Tempo: 120 negras por minuto por defecto**, el del MIDI exportado y el valor por defecto del dominio (`EventTiming.offset_seconds`). Un control lo cambia de 40 a 200 en pasos de 10, también mientras suena.
3. **Instrumento sintetizado**, sin muestras ni recursos de terceros: `PolySynth` de Tone.js con voces `Synth` de onda triangular. Envolvente: ataque de 10 ms, caída de 120 ms, sostenimiento de 0,4 y liberación de 200 ms. Volumen de −10 dB y 16 voces.
4. **Reloj y CSP: la CSP no cambia.**
   - Contexto propio con el reloj por `setTimeout`: `new Context({ clockSource: "timeout", latencyHint: "interactive", lookAhead: 0.1 })`, registrado con `setContext`.
   - Tone.js se importa por sus módulos (`tone/build/esm/classes.js` y `tone/build/esm/core/Global.js`), no por `tone`, para que no cree al importarse el contexto con el Worker. Por esas rutas internas, la versión queda fijada (`"tone": "15.1.22"`).
   - Se carga bajo demanda, en su propio trozo, cuando la vista tiene notas que sonar. Mide 234,94 kB, o 59,23 kB con gzip.
   - Se le pide que no escriba su versión en la consola (`TONE_SILENCE_LOGGING`).
5. **Sincronización.**
   - Las notas y los cambios de compás se programan en el transporte en pulsos (ticks). Así, un cambio de tempo los recoloca sin volver a programar.
   - La vista recibe cada cambio de compás cuando suena, con un `setTimeout` hasta ese instante, y no cuando el transporte lo programa (unos 0,1 s antes).
   - El transporte arranca en `context.now()`, el instante actual más el margen.
   - Pausar se hace en el instante actual (`context.immediate()`), o en el del arranque si aún no ha llegado: `Clock.pause` de Tone no actúa en un instante anterior al arranque, y una «Pausa» en los 100 ms siguientes a «Reproducir» no haría nada. Al reanudar, Tone vuelve a programar la nota y el compás de ese margen.
   - Detener se hace en el instante actual: cancela también un arranque pendiente.
   - Si se pausa o se detiene mientras el contexto aún se reanuda, el transporte no arranca cuando termina de reanudarse.
   - Al pausar, detener o salir, la voz se funde en 30 ms y se desecha, lo que corta sin chasquido lo que suena y lo ya programado dentro del margen. Al llegar al final no se funde: la última nota termina con su caída.
6. **Gesto.** El contexto se crea y se reanuda dentro del clic de «Reproducir», sin esperas antes. El módulo ya está cargado porque se pide al abrir la vista.
7. **Ciclo de vida.** El motor se libera al salir de la vista, al cambiar de sesión o si cambia el estado que se reproduce. Al salir de la vista o cambiar de sesión, además, se cierra el contexto de audio, y con él su reloj; el siguiente «Reproducir» crea otro dentro de su gesto. Si la página deja de verse, se pausa: el navegador frena el reloj por `setTimeout` en segundo plano y las notas llegarían a destiempo. Si no llega el trozo de Tone.js (por ejemplo, tras un redespliegue), la vista lo dice y deja volver a pedirlo.
8. **Resaltado del compás que suena.**
   - Usa la geometría de las marcas de ADR-0021 (`measureBox`), en cada pentagrama donde está el compás, y solo si OSMD dibujó los mismos compases que el `ScoreIR`.
   - Es un contorno de tinta de 3 px por detrás de las notas y una banda maciza de 6 px colgada bajo la caja, fuera de ella para no tapar plicas, barras ni notas graves. No es violeta: no pide nada a la persona.
   - La banda entra con un barrido a saltos de 240 ms (`steps(6)`).
   - El compás que suena se trae a la vista solo si el anterior estaba a la vista: a quien bajó a mirar la imagen o la lista no se le devuelve a la partitura.
   - Con `prefers-reduced-motion` no hay barrido, y el compás se trae a la vista sin desplazamiento suave.
9. **Accesibilidad.** «Reproducir» y «Pausa» son el mismo botón (el foco no se pierde al cambiar), junto a «Detener» y al tempo, todos botones nativos. Una región `aria-live` anuncia los cambios de estado: «Reproduciendo.», «En pausa.», «Detenido.», «Fin de la partitura.» y los fallos. El compás se ve, pero no se anuncia, porque cambiaría sin parar.

## Consecuencias

### Positivas

- Sin cambios en la CSP de producción y sin violaciones al reproducir. Comprobado con el build servido con la CSP de `cadenza.conf`, a 1440 y 390 px.
- El compás que suena sigue la misma rejilla que el mapa de tiempos, también con compases incompletos o sobrellenados.
- No hace falta otra dependencia (un lector de MIDI) ni otra petición.
- La programación de notas, el compás en curso, la pausa (también justo después de arrancar o mientras el audio se reanuda), el final y el tempo en vivo se prueban con un reloj falso, sin audio real. El transporte falso modela lo leído en el código de Tone 15.1.22 (`Clock`, `Transport` y `TickSource`): es un modelo, no Tone.
- Medido contra la API real a 120 negras por minuto, muestreando la vista cada 50 ms y tomando como referencia el primer cambio de compás: los siguientes llegaron entre 48 y 58 ms más tarde de lo que da el mapa. El desfase parece sistemático y no se ha investigado. Además, el compás se marca según `context.currentTime`, que va por delante de lo que se oye en la latencia de salida del dispositivo: decenas de milisegundos, y más con auriculares Bluetooth.

### Negativas

- Las rutas internas de Tone.js atan la actualización de la dependencia: subir de versión exige comprobar que siguen existiendo y que el índice no ha cambiado de comportamiento.
- En segundo plano se pausa en lugar de seguir sonando.
- Nadie ha escuchado el resultado: un navegador sin interfaz no oye. Quedan por comprobar a mano el timbre, el volumen, la continuidad de las ligaduras, la pausa y la reanudación sin cortes, y el móvil (en iOS, el interruptor de silencio puede callar el audio web).
- La reproducción es la de la transcripción: dinámicas, articulaciones, repeticiones y adornos no suenan, porque el `ScoreIR` no los tiene.

## Alternativas consideradas

- **El MIDI de `/export` con un lector en el cliente:** se descarta. Con un compás incompleto se aparta de la rejilla con la que se resalta el compás (2 de 47 sesiones), añade una dependencia y una petición, y el MIDI no dice en qué compás está cada nota.
- **Reloj en un Worker con `worker-src 'self' blob:` en la CSP:** se descarta. Amplía la CSP de producción para un reloj que, con la página a la vista, no hace falta.
- **Web Audio directamente, sin Tone.js:** es viable, pero el stack fija Tone.js, que ya da las voces, el transporte y el cambio de tempo en vivo.
- **El cursor de OSMD:** se descarta. La geometría por compás ya existe (ADR-0021) y no ata la vista a otra API de OSMD.
