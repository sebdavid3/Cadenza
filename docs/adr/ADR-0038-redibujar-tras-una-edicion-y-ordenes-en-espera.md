# ADR-0038: Redibujar tras una edición en una sola instancia de OSMD, una orden en espera mientras se guarda y la reproducción que sigue

- **Estado:** Aceptado
- **Fecha:** 2026-10-30
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0006, ADR-0011, ADR-0026, ADR-0027, ADR-0030, ADR-0033, ADR-0034, ADR-0035 y ADR-0037, CLAUDE.md §9 y §10)
- **Relacionado:** [ADR-0006](ADR-0006-render-editor-osmd-verovio-zustand.md), [ADR-0011](ADR-0011-semantica-de-anclas-ante-ediciones.md), [ADR-0026](ADR-0026-reproduccion-de-la-partitura-en-el-navegador.md), [ADR-0027](ADR-0027-seleccion-de-notas-sobre-la-partitura.md), [ADR-0030](ADR-0030-correccion-de-altura-duracion-y-alteracion.md), [ADR-0034](ADR-0034-deshacer-y-rehacer-desde-la-vista.md), [ADR-0035](ADR-0035-descartar-restaurar-y-revalidar-desde-la-vista.md), [ADR-0037](ADR-0037-una-edicion-en-un-solo-viaje.md), D38, [#275](https://github.com/sebdavid3/Cadenza/issues/275), [#276](https://github.com/sebdavid3/Cadenza/issues/276)

---

## Contexto

El estudio con participantes mide el tiempo de corrección (D38). Tras #275 una edición es una sola petición y su respuesta trae el estado nuevo (ADR-0037), pero la vista seguía haciendo tosca cada edición. Leído en el código antes de este cambio:

- **Se dibujaba todo desde cero.** Cada estado creaba otra instancia de OpenSheetMusicDisplay en un contenedor oculto, leía el MusicXML (`load`) y dibujaba la partitura entera (`render`) tras pintar; ADR-0006 ya lo señalaba como riesgo.
- **La marca de la nota elegida desaparecía** hasta que llegaba el dibujo nuevo, y las flechas y los clics se ignoraban mientras tanto.
- **La barra parpadeaba:** al guardar, sus unos 25 botones pasaban a inactivos, con borde discontinuo.
- **Una orden dada mientras se guardaba se perdía sin aviso.**
- **La reproducción se cortaba:** cada estado nuevo descartaba el motor de Tone.

Lo que no se toca: sin actualización optimista (ADR-0030, ADR-0034), cada edición con el `base_seq` del estado que se ve y sin reintento con otro `seq` (ADR-0011), la selección vale para una sesión y un `seq` (ADR-0027) y el editor espera mientras se revalida (ADR-0035).

### Lo que permite OSMD 2.2.1 (leído en su código, versión fijada en `package.json`)

- `load(Document)` es síncrono en la práctica: analiza el documento, crea la hoja (`MusicSheetReader`) y su gráfico, y devuelve una promesa ya cumplida. No quita lo dibujado. Vuelve al zoom 1.
- `render()` es síncrono: vacía el contenedor, vuelve a maquetar la partitura entera (`reCalculate`) y la dibuja.
- **No dibuja un sistema suelto.** Los rangos `MinMeasureToDrawIndex`/`MaxMeasureToDrawIndex` maquetan solo esos compases (otra maquetación) y el dibujo incremental (`renderNext`) añade sistemas al final de una maquetación que crece; ninguno sustituye un sistema ya dibujado. Hacerlo exigiría tocar sus partes privadas (`renderAppend`, `LazyDrawSystemsFromIndex`).
- **Dónde está el coste**, medido con las marcas de «Medir» en una página real transcrita por HOMR (Mondnacht, p. 10: 34 compases, 2 pentagramas, 404 figuras): crear la instancia cuesta unos milisegundos; casi todo es leer el MusicXML (`load`) y dibujarlo (`render`, del que maquetar es buena parte). Las cifras no se citan aquí: se regeneran como dice «Medir».

## Decisión

1. **Una instancia de OSMD por vista** (`createScoreRenderer`, `osmd.ts`). Se crea al montar la vista y cada estado se dibuja en ella: `draw(xml)` lee el MusicXML y dibuja la partitura de forma síncrona. Un MusicXML igual al dibujado no se vuelve a leer ni a dibujar; volver a maquetar al cambiar el ancho solo dibuja. Si un estado no se puede leer o dibujar, no queda nada dibujado y la vista lo dice; el siguiente se dibuja en la misma instancia. Cada dibujo invalida el anterior: un `RenderedScore` viejo no da compases ni cajas.
2. **Se dibuja antes de pintar.** La vista pide el dibujo en un efecto de maquetación y refleja lo dibujado como un almacén externo (`useSyncExternalStore`): el estado nuevo, su partitura, sus marcas y la nota elegida aparecen juntos, sin un fotograma con las marcas de otro dibujo ni un contenedor oculto.
3. **Se dibuja la partitura entera**, porque OSMD no permite otra cosa (Contexto).
4. **El mapa de notas se recalcula entero** con cada dibujo (ADR-0027). Medido en la misma página, casi todo su coste es la maquetación del SVG nuevo que el navegador hace en la primera lectura de una caja, y que haría igualmente antes de pintar; consultar las cabezas y sus cajas es una parte pequeña. Al dibujar antes de pintar, esa maquetación cae dentro de la medida del mapa (antes caía a veces fuera, en el fotograma intermedio). Reutilizar las cajas de los compases que no cambian ahorraría esos milisegundos a cambio de un riesgo: decidir que un compás «no cambió» exige comparar todo lo que mueve sus cabezas (la clave y la armadura vigentes, las alteraciones, las plicas, el sistema en que cae), y una comparación incompleta daría cajas falsas.
5. **La marca de la nota elegida no desaparece.** Si la selección pasa a un estado que aún no está dibujado (una orden guardada deja elegido su evento antes de que llegue su dibujo, ADR-0033), la marca se queda sobre la última nota marcada hasta que llega, y entonces pasa a la nota que corresponde. Lo que se elige sobre el dibujo de un estado anterior se elige en ese estado, y la vista lo lleva al actual con la regla de desplazamiento de ADR-0011 §2, como al guardar una edición.
6. **Sin parpadeo:** mientras se guarda, los botones de la barra no cambian de aspecto; la espera la dicen el texto de la barra («Guardando…») y la región `aria-live`. Siguen inactivos cuando de verdad no se puede editar (sin respuesta del servidor, tras un 403, mientras se revalida).
7. **Una orden en espera, nunca reintentada.** Una orden (una corrección, deshacer o rehacer, del botón o del teclado) que llega mientras se guarda otra no se pierde:
   - **Espera una sola.** Cuando la anterior se guarda y la vista muestra su estado, se vuelve a planear sobre ese estado, con la nota elegida entonces (la que dejó elegida la anterior, o la que la persona eligiera mientras tanto), y sale con su `base_seq`. Es una orden nueva sobre el estado que se ve, no un reintento: ninguna edición se reenvía con otro `seq` (ADR-0011).
   - **Si la anterior no se guardó** (un 409, un 422, sin respuesta…), la que esperaba no sale y se dice: «No se envió la orden que esperaba: la anterior no se guardó.» Se planeó para después de algo que no ocurrió.
   - **Una tercera orden** mientras otra espera no sale y se dice: «Ya hay una orden esperando a que se guarde la anterior: esta no se envió.»
   - Si al planearla no se puede (la nota ya no está, ya tiene ese valor), se dice como cualquier orden rechazada.
   - Mientras se revalida no se encola: el editor espera a la revalidación (ADR-0035).
   - Sin actualización optimista: nada cambia en la vista hasta la respuesta de cada orden.
8. **La reproducción sigue.** Una edición no descarta el motor de Tone: le da la partitura nueva (`update`), que la vuelve a programar desde el punto en que está el transporte, sin pararlo. Lo anterior a ese punto ya sonó; si la partitura nueva acaba antes, termina como al llegar al final; al volver al principio se programa entera. Sin nada que sonar, se detiene. Otra sesión monta otra vista y otro motor (ADR-0026).
9. **Medir.** Cada etapa del dibujo de un estado queda en `performance` como `cadenza:dibujo:leer`, `cadenza:dibujo:dibujar` y `cadenza:dibujo:mapa`, con la sesión y el `seq` en `detail`, junto a las marcas de cada orden de ADR-0037. `apps/web/scripts/medir-redibujado.js`, pegado en la consola de una sesión con una nota elegida, envía correcciones de altura alternas, espera cada dibujo con su mapa y resume las medidas (mediana, p95 y máximo); falla si falta la partitura, la nota elegida o alguna marca. Las cifras se regeneran antes de citarlas (CLAUDE.md §8), comparando las dos versiones intercaladas en el mismo equipo: la carga del equipo cambia más las cifras que la diferencia entre versiones.

## Consecuencias

### Positivas
- La marca de la nota elegida, el foco y la página no saltan al editar; el estado nuevo aparece de una vez.
- Una persona que corrige deprisa (dos pasos de altura seguidos, insertar y subir la nota insertada) no pierde órdenes, y cada una sigue siendo una edición del log con el `base_seq` del estado que se veía al enviarla.
- La reproducción no se corta al corregir mientras suena.
- Las etapas del dibujo se pueden medir en producción sin herramientas nuevas.

### Negativas / Riesgos
- **El objetivo propuesto en #276 (menos de 500 ms p95 del clic a la partitura dibujada en una página completa) no se alcanza con OSMD dibujando la página entera** en el equipo en que se midió: leer y dibujar el MusicXML de una página cuesta del orden de cientos de milisegundos y no depende de este cambio. Las palancas que quedan, fuera de este ADR: aplicar las ediciones sencillas sobre la hoja de OSMD sin volver a leer el MusicXML (riesgo de que lo dibujado se separe del MusicXML exportado, que es lo que vale) o dibujar solo los sistemas afectados con las partes privadas de OSMD (frágil ante una actualización).
- Dibujar antes de pintar bloquea el hilo principal mientras OSMD dibuja; antes también lo bloqueaba, después de pintar. El texto de la barra y la lectura de la nota elegida se actualizan con el dibujo, no un fotograma antes.
- El dibujo síncrono depende de que `load(Document)` de OSMD siga siendo síncrono: la versión está fijada (2.2.1) y, si dejara de serlo, `draw` lo detecta (`IsReadyToRender`) y la vista dice que no pudo dibujar la partitura, en lugar de dibujar a medias.
- Una orden en espera se planea sobre la nota elegida cuando sale, no sobre la que estaba elegida al darla: si la persona elige otra nota mientras se guarda, la orden va a esa.
- Las notas que el transporte ya había programado dentro de su margen de anticipación (unos 100 ms) suenan como estaban antes de la edición.

## Alternativas consideradas

1. **Avisar de que la orden se ignoró, sin encolarla.** Descartada: el estudio mide el tiempo de corrección, y quien pulsa dos veces una flecha para subir dos pasos tendría que esperar a cada guardado o repetir la orden.
2. **Encolar todas las órdenes.** Descartada: las órdenes planeadas sobre estados que aún no existen se encadenarían a ciegas, y un fallo en medio dejaría varias sin sentido. Una sola en espera cubre la corrección rápida y deja claro qué pasó con cada orden.
3. **Enviar la orden en espera con el `base_seq` que tenía al darla, o reintentarla con el nuevo.** Prohibido por ADR-0011.
4. **Seguir dibujando en un contenedor oculto y sustituir el anterior al terminar.** Descartada: crea otra instancia y otro SVG por estado y deja un intervalo en que la vista no corresponde a lo que se ve.
5. **Reutilizar por compás las cajas del mapa de notas.** Descartada por ahora (Decisión, punto 4).
6. **Parar la reproducción y reanudarla en el mismo compás con un motor nuevo.** Descartada: crea otro contexto de audio fuera del gesto de la persona y corta lo que suena.
