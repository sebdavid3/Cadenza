# ADR-0045: Nombre e instrumentos de la sesión en la web: datos antes de transcribir, el nombre en toda la web y cambiarlos desde la vista

- **Estado:** Aceptado
- **Fecha:** 2026-11-01
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0012, ADR-0014, ADR-0021, ADR-0027, ADR-0037, ADR-0038 y ADR-0041, CLAUDE.md §9 y §10)
- **Relacionado:** [ADR-0041](ADR-0041-titulo-compositor-e-instrumentos-de-la-sesion.md), [ADR-0021](ADR-0021-visualizacion-de-la-transcripcion-y-marcado-de-hallazgos.md), [ADR-0038](ADR-0038-redibujar-tras-una-edicion-y-ordenes-en-espera.md), [#240](https://github.com/sebdavid3/Cadenza/issues/240), [#235](https://github.com/sebdavid3/Cadenza/issues/235), [#147](https://github.com/sebdavid3/Cadenza/issues/147), [#176](https://github.com/sebdavid3/Cadenza/issues/176), [#242](https://github.com/sebdavid3/Cadenza/issues/242), [#277](https://github.com/sebdavid3/Cadenza/issues/277)

---

## Contexto

Con #235 (ADR-0041) la API guarda el título, el compositor, el instrumento de cada parte y el nombre del archivo subido: `POST /transcribe` los admite, `PATCH /sessions/{id}` los cambia y el listado, el detalle y la vista los devuelven. La web no los usaba:

- La transcripción por lotes (#147) enviaba cada imagen nada más elegirla, sin ningún dato.
- El listado nombraba cada sesión con los ocho primeros caracteres de su id, y la cabecera de la vista y el título de la pestaña decían «Sesión xxxxxxxx».
- `osmd.ts` no dibuja el título, el compositor ni los nombres de las partes, y ADR-0041 dejó a #240 decidir si se dibujan y cómo se actualiza lo que se ve tras el `PATCH`.

El contrato no cambia.

## Decisión

### 1. Antes de transcribir: las imágenes elegidas esperan a «Transcribir»

Elegir o soltar imágenes ya no las envía. Las que pasan la comprobación previa esperan en un recuadro, «Antes de transcribir», bajo la zona de subida; las que no la pasan van a la cola como rechazadas, como antes. Nada sale hasta pulsar «Transcribir la imagen» o «Transcribir N imágenes», que las pone en la cola con sus datos; la cola sigue enviándolas de una en una (#147). «Descartar» y «Quitar» no envían nada.

- **Los datos:** el nombre de la partitura (el `title`), el compositor y el instrumento de dos partes, «Parte de arriba» (la voz o el instrumento superior) y «Segunda parte» (el piano que acompaña), de la lista cerrada de ADR-0041 §2 con «Sin indicar» primero. «Otro» pide el nombre del instrumento (`part_names`) y avisa de que suena como el piano. El formulario no pide nombre de parte para los demás instrumentos.
- **Todo es opcional y tiene valores por defecto:** sin nombre, sin compositor y los instrumentos «Sin indicar». Con los valores por defecto no se envía ningún campo: la petición, la sesión y lo exportado son los de siempre (ADR-0041 §3). No se elige por defecto «Voz» ni «Piano»: sería adivinar por la persona.
- **Dos partes:** el corpus del estudio son incipits de una voz y piezas de voz o instrumento con piano. La persona no sabe cuántas partes detectará HOMR; las de sobra se descartan sin error (ADR-0041 §3) y se corrigen después con el `PATCH`, que ya conoce las partes.
- **En un lote:** los datos del recuadro valen para todas las imágenes; cada una tiene «Cambiar los datos», que le da los suyos (copiados de los comunes en ese momento) y «Usar los datos comunes» para volver. Con varias imágenes, cada fila dice cómo se llamará su sesión. Lo que se ve es lo que se envía: si al quitar imágenes queda una sola con datos propios, esos pasan a ser los comunes que enseña el recuadro; al quitar la última, el formulario vuelve a sus valores por defecto, como al descartar.
- **Al enviar,** los textos se recortan (la API cuenta los límites sobre lo recibido), los instrumentos y los nombres van alineados hasta la última parte con datos y el recuadro vuelve a sus valores por defecto. Los campos limitan el texto a 200 caracteres (nombre y compositor) y a 100 (instrumento), los del contrato.
- **Foco:** al aparecer el recuadro tras elegir imágenes, el foco va al nombre (no si la vista vuelve a montarse con imágenes que ya esperaban); al enviar, al título de la cola; al descartar o quitar la última imagen, a «Elegir imágenes». El número de imágenes elegidas se anuncia al cambiar.
- **Estado:** lo preparado y los datos comunes viven en el almacén de la cola, que es de quien entró: si entra otra persona en la pestaña se olvidan, como la cola. Lo preparado no cuenta como trabajo pendiente al cerrar la pestaña: aún no se ha enviado nada.

El recuadro de la portada (#277) usará el mismo formulario (`ScoreDataFields`) cuando se haga.

### 2. El nombre de la sesión en toda la web

El nombre de una sesión es su `title`; sin él, su `source_filename`; sin ninguno de los dos, «Sesión» y los ocho primeros caracteres del id (`sessionName` en `pages/transcription/scoreData.ts`). Es el enlace de cada sesión en el listado, el título de su vista y el de la pestaña («nombre · Cadenza»), y la cola lo dice de cada imagen enviada con nombre. La cabecera de la vista enseña además el compositor, los instrumentos de las partes («Voz · Piano»: el nombre dado o el del instrumento, «Sin indicar» en una parte sin datos antes de otra que sí los tiene) y, si la sesión tiene nombre propio, el archivo subido. La condición y la partitura del estudio (`condition`, `test_score_id`) no se muestran en ninguna parte.

### 3. Cambiarlos desde la vista

Quien transcribió la sesión tiene «Cambiar los datos» en la cabecera, también con la sesión finalizada (ADR-0041 §4): abre debajo un formulario con el nombre, el compositor y un desplegable por cada parte de `current_score` («Parte 1 · 1 pentagrama»). «Guardar» envía `PATCH /sessions/{id}` con todos los campos (`null` lo vacío; `instruments`, una entrada por parte, o `[]` si no hay ninguno); el nombre guardado de una parte se conserva mientras no se cambie su instrumento. Nadie más ve el botón; un investigador ante una sesión ajena la ve en solo lectura.

- Nada se da por guardado sin el 200, y se muestra lo que devuelve (el servidor normaliza el texto). Mientras se guarda, «Guardar» no vuelve a enviar. El 422, el 404, el 403 y la falta de respuesta tienen mensajes propios; lo escrito se conserva.
- No es una corrección: no pasa por el log ni tiene `base_seq`. Pero guardar los datos y corregir no se cruzan: «Guardar» espera mientras haya una corrección, una revalidación, un descarte o finalizar en curso («Espera a que termine lo que está en curso»), y mientras se guarda, las correcciones esperan como al revalidar (el `held` del editor). Si se cruzaran, la respuesta de una corrección traería el MusicXML exportado con los datos de antes (ADR-0037), y `GET /export`, que da el estado actual del servidor, podría guardarse en la caché bajo el `seq` de otro estado. Lo guardado desde la vista manda además sobre el detalle en caché, que se actualiza con la respuesta.
- Tras el 200 se vuelve a pedir el MusicXML del estado que se ve (solo esa clave): lo descargado lleva el título, el compositor y los instrumentos nuevos (ADR-0041 §5). La partitura se redibuja con él como tras una edición, en la misma instancia de OSMD, sin vaciarse y con la nota elegida (ADR-0038). El listado queda por actualizar.
- Sin partes en la partitura (no debería pasar: la vista exige `current_score`), el `PATCH` no envía `instruments`, para no borrarlos.

### 4. OSMD sigue sin dibujar el título, el compositor ni los nombres de las partes

El nombre, el compositor y los instrumentos se leen en la cabecera, en HTML, que se actualiza con la respuesta del `PATCH` sin esperar al MusicXML. Dibujarlos además en la partitura los repetiría, quitaría alto al primer sistema (y ancho, con los nombres de las partes a la izquierda, que a 390 px deja menos compases por sistema) y cambiaría la maquetación sobre la que se sitúan las marcas de los compases (ADR-0021) y el mapa de notas (ADR-0027). `osmd.ts` no cambia.

### 5. La descarga conserva su nombre

«Descargar MusicXML» sigue guardando `cadenza-<8 primeros caracteres del id>.musicxml` (#176): el nombre de la sesión puede repetirse, cambiar con el `PATCH` y llevar caracteres que un sistema de archivos no admite, y un nombre determinista sirve para relacionar un archivo con su sesión.

## Consecuencias

### Positivas
- Cada sesión se reconoce por su nombre, y los instrumentos indicados llegan a lo descargado y a la reproducción por instrumento (#242).
- Subir sin datos sigue siendo una petición sin datos: nada cambia para una sesión creada así.

### Negativas / Riesgos
- Subir pide un clic más («Transcribir»), también sin datos.
- Los instrumentos se asignan por posición: si HOMR detecta otras partes de las esperadas, quedan en la que no es (ADR-0041); se corrigen desde la vista.
- Lo guardado en otra pestaña no se ve en esta hasta recargarla; y si esta vista guardó antes, lo suyo manda sobre lo que traiga un detalle posterior mientras siga abierta. La exclusión con las correcciones es de una pestaña: una corrección hecha a la vez desde otra puede llevarse el MusicXML con los datos de antes.
- La cola dice el nombre recortado, no normalizado como lo guarda el servidor (espacios internos, caracteres de control): puede diferir un poco del de la sesión.
- Volver a pedir el MusicXML tras guardar redibuja la partitura aunque no cambie lo que se ve.

## Alternativas consideradas

1. **Un formulario siempre visible encima de la zona de subida y envío inmediato, como antes.** Descartada: los datos tendrían que elegirse antes que las imágenes y no se podrían cambiar en cada una, porque la primera sale al instante.
2. **Cambiar los datos de cada imagen en la cola, mientras espera.** Descartada: con la GPU, una imagen espera uno o dos segundos; no da tiempo.
3. **Valores por defecto «Voz» y «Piano».** Descartada: cambiaría lo exportado de toda sesión creada sin elegir nada y sería adivinar por la persona.
4. **Dibujar el título y los nombres de las partes con OSMD.** Descartada por §4.
5. **Nombrar la descarga con el título.** Descartada por §5.
6. **Guardar los datos sin esperar a las correcciones ni detenerlas.** Descartada en la revisión: la respuesta de una corrección cruzada traería el MusicXML con los datos de antes, y volver a pedir el MusicXML podría emparejar el de un estado con el `ScoreIR` de otro.
