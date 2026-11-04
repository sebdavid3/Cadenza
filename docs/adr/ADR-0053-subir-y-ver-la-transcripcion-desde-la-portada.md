# ADR-0053: Subir una imagen y ver su transcripción desde la portada

- **Estado:** Aceptado
- **Fecha:** 2026-11-01
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0012, ADR-0016, ADR-0020, ADR-0021, ADR-0024, ADR-0026, ADR-0040 y ADR-0045, CLAUDE.md §9)
- **Relacionado:** [ADR-0045](ADR-0045-nombre-e-instrumentos-de-la-sesion-en-la-web.md), [ADR-0020](ADR-0020-sesion-del-cliente-web.md), [ADR-0024](ADR-0024-transcripciones-simultaneas.md), [ADR-0027](ADR-0027-seleccion-de-notas-sobre-la-partitura.md), [#277](https://github.com/sebdavid3/Cadenza/issues/277), [#240](https://github.com/sebdavid3/Cadenza/issues/240), [#278](https://github.com/sebdavid3/Cadenza/issues/278)

---

## Contexto

La portada (`/`) presentaba el proyecto y llevaba a «Entrar»; para transcribir había que entrar e ir a `/transcripcion`, donde la cola solo decía «Sesión xxxxxxxx» de cada resultado, sin enlace. `POST /transcribe` exige sesión (ADR-0012) y es síncrono, hasta 30 s en el cliente (ADR-0016); con los huecos de HOMR ocupados responde 503 con `Retry-After` (ADR-0024). #240 (ADR-0045) dejó el formulario de los datos de la partitura (`ScoreDataFields`) listo para reutilizarse aquí, y #278 ampliará el recuadro para transcribir sin cuenta.

El contrato de la API no cambia.

## Decisión

### 1. Un recuadro en la portada, bajo el titular

La sección «Transcribe una partitura» (`#transcribir`) va justo después del titular y antes de la demostración: es lo primero que se puede hacer. Pide **una** imagen (la zona de subida de la cola con `multiple={false}`), con las mismas comprobaciones previas (`precheck` de `queue.ts`: PNG o JPEG, no vacía, hasta 20 MB); varias soltadas a la vez se rechazan y se remite a la transcripción por lotes. Con la imagen elegida aparece «Antes de transcribir» con `ScoreDataFields` y las dos partes de ADR-0045 §1; el foco va al nombre. Todo es opcional y nada se envía hasta pulsar.

### 2. Con sesión: se transcribe y se ve el resultado aquí

«Transcribir la imagen» envía `POST /transcribe` con la imagen y los datos (`appendScoreData`) y el timeout de la cola. Mientras HOMR trabaja, la zona de subida se sustituye por un bloque de espera honesto: qué imagen, los segundos que lleva y que puede llegar a 30 s; el foco va a él. Con el 201, el recuadro enseña el resultado:

- el nombre de la sesión (`sessionName`), el número de posibles errores (`findings_count` del 201) y el recordatorio de que las reglas no lo detectan todo; en una sesión no asistida no se habla de posibles errores (ADR-0040 §13.2);
- la reproducción (`PlaybackBar` y `usePlayer`, ADR-0026), con el instrumento de cada parte;
- la partitura con `ScoreView` en **solo lectura**: sin marcas de compás, sin barra de corrección y, con la propiedad nueva `notesSelectable={false}`, sin selección de notas (ADR-0027): es una imagen con nombre, como cuando no hay nada que elegir;
- «Editar», un enlace a `/sesiones/:id`, y «Transcribir otra imagen», que vuelve a empezar.

Lo que se enseña sale de las mismas consultas que la vista de la sesión (`GET /sessions/{id}?fields=view`, `/export` y `/timing`), con sus claves de caché: «Editar» abre la sesión sin volver a pedirlo. Las marcas de los compases no se dibujan: verlos, decidir y corregir es trabajo de la vista de la sesión.

### 3. Sin sesión: se pide entrar y la transcripción sigue al volver

Al elegir la imagen sin sesión, el formulario aparece igual, pero en lugar de «Transcribir» dice que hace falta entrar, que la imagen y sus datos esperan y que una recarga obliga a elegirla otra vez, con «Entrar y transcribir» y, si el build abre el registro (`VITE_REGISTRATION_ENABLED`, #248), «Crear una cuenta». Los dos enlaces llevan `state.from = "/#transcribir"`, y `/entrar` y `/registro` vuelven ahí tras entrar o tras crear la cuenta y entrar con ella (`destination` en `auth/destination.ts`, que solo acepta rutas internas; `/entrar` y `/registro` se pasan ese estado entre sí). Al volver con la sesión iniciada (con el ancla `#transcribir` que pone esa vuelta), la portada trae la sección a la vista y transcribe sola, sin volver a elegir el archivo. Si se entra por otro camino (se volvió atrás sin entrar y se entró después desde la cabecera), la imagen sigue elegida pero no se envía nada sin pulsar «Transcribir la imagen».

- **La imagen vive en memoria.** Un almacén de Zustand fuera de la vista (`pages/landing/uploadStore.ts`) guarda el `File`, los datos y el estado; ir a entrar es navegar dentro de la aplicación, sin recargar. La imagen no se guarda en el navegador: ni `sessionStorage`, ni IndexedDB, ni una URL de datos.
- **Recarga.** Al ir a entrar se apunta en `sessionStorage` solo el **nombre** del archivo (`cadenza.portada.pendiente`). Si al montar la portada hay nombre apuntado y no hay imagen en memoria, la página se recargó: un aviso dice qué imagen se perdió, que Cadenza no la guarda y que hay que volver a elegirla con sus datos. El apunte se borra al transcribir, al descartar o al avisar.
- **Autoría.** El autor de la sesión es quien entra, fijado por el servidor con su token (ADR-0012); la portada no envía nada sin él. Una imagen elegida sin cuenta es de quien entra para transcribirla; una elegida con la sesión de otra persona (que caducó) se olvida si entra alguien distinto.

### 4. Errores, como en la cola

Los errores se dicen con los mensajes de `transcribeErrorMessage`, que ahora distingue el 503 de huecos ocupados («El servidor está ocupado con otras transcripciones. Vuelve a probar en N s.», con `Retry-After`) también en la cola. 413, 415, 422 y la red tienen los de siempre. Si vence la espera, la portada dice que la sesión puede haberse creado y enlaza a las sesiones (`/transcripcion`) antes de volver a intentarlo, porque aquí no hay listado a la vista. La imagen y los datos se conservan y el botón pasa a «Volver a intentarlo»; el foco va al aviso. Un 401 cierra la sesión como caducada (ADR-0020) y el recuadro vuelve a pedir entrar con «Tu sesión caducó antes de transcribirla», que se lleva el foco, conservando la imagen: al volver, sigue sola.

### 5. Ciclo de vida y lo pendiente

- Tras el 201 la imagen se suelta: ya está en el servidor. Hasta que llega el detalle, el resultado se nombra con el nombre dado o el del archivo.
- Mientras se transcribe, cerrar o recargar la pestaña pide confirmación (`registerPendingWork`), como la cola.
- Al salir de la sesión («Salir») se olvida todo; si entra otra persona en la pestaña, el resultado de la anterior deja de enseñarse. Una sesión que caduca conserva la imagen.
- La portada bloquea los archivos soltados fuera de la zona mientras se ve el recuadro (también durante la espera y con el resultado), como `/transcripcion`: el navegador los abriría y se perdería lo elegido o lo transcrito.

### 6. La cola enlaza cada resultado

En `/transcripcion`, cada imagen transcrita de la cola tiene «Abrir la sesión» (con el nombre de la imagen en su nombre accesible), un enlace a `/sesiones/:id`, en lugar del «Sesión xxxxxxxx» sin enlace.

## Consecuencias

### Positivas
- Se puede probar Cadenza desde la primera pantalla y ver lo que lee HOMR antes de entrar en la vista de trabajo.
- Ninguna ruta ni respuesta de la API cambia; el recuadro reutiliza la zona de subida, el formulario de #240, la vista de la partitura y la reproducción.
- #278 solo tiene que añadir el camino sin cuenta: `ResultView` recibe la partitura, el MusicXML y los tiempos venga de donde venga.

### Negativas / Riesgos
- Una recarga en medio de entrar pierde la imagen y sus datos (se avisa). Guardarla en el navegador lo evitaría, pero el issue lo excluye: una imagen de hasta 20 MB de otra persona no debe quedarse en un equipo compartido.
- Sin sesión, el recuadro pide entrar hasta que exista #278; con el registro cerrado durante el estudio (#248), solo pueden transcribir desde aquí las cuentas del equipo.
- El timeout del cliente (30 s) puede vencer con la sesión creada en el servidor; el mensaje lo dice, como en la cola, y un reintento crearía otra.
- El resultado no marca los compases con posibles errores: solo los cuenta.

## Alternativas consideradas

1. **Llevar a `/transcripcion` con la imagen ya en la cola.** Descartada: el issue pide ver el resultado en la propia portada y la cola es la vista de trabajo por lotes.
2. **Guardar la imagen en IndexedDB para sobrevivir a una recarga.** Descartada: el issue lo excluye y dejaría imágenes ajenas en el navegador.
3. **Recordar la imagen pendiente en la URL (`?continuar`).** Descartada: la marca en `sessionStorage` con solo el nombre basta para avisar y no queda en el historial ni en los enlaces que se comparten.
4. **Dibujar las marcas de los compases y dejar elegir notas.** Descartada: sin corrección, elegir notas no lleva a nada y la barra de la selección explicaría teclas que aquí no editan; los posibles errores se revisan en la sesión.
