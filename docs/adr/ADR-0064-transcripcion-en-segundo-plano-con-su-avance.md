# ADR-0064: Transcripción en segundo plano, con su estado y su avance

- **Estado:** Aceptado
- **Fecha:** 2026-11-09
- **Decisores:** Responsable del proyecto (quitar el límite de 30 s y decir el avance real, 2026-11-09) y Equipo de Desarrollo
- **Enmienda:** [ADR-0016](ADR-0016-transcripcion-sincrona-vs-asincrona.md) §1 y §3, [ADR-0024](ADR-0024-transcripciones-simultaneas.md) §5
- **Relacionado:** [ADR-0012](ADR-0012-autenticacion-e-identidad.md), [ADR-0059](ADR-0059-compas-por-tramos-c-y-cortado-y-tresillos-implicitos-tras-homr.md), [ADR-0060](ADR-0060-voz-por-encima-del-piano.md), [ADR-0062](ADR-0062-despliegue-continuo-desde-main-en-el-homelab.md), [#375](https://github.com/sebdavid3/Cadenza/issues/375), [#269](https://github.com/sebdavid3/Cadenza/issues/269)

---

## Contexto

- `POST /transcribe` es síncrono (ADR-0016) y la web lo esperaba 30 s (`TRANSCRIBE_TIMEOUT_MS`). Pasado el plazo decía «La transcripción tardó más de 30 s…», aunque la transcripción siguiera y la sesión apareciera después. Nginx corta a los 60 s.
- ADR-0016 midió páginas sintéticas de hasta 12 pentagramas (12 s en CPU). Una página real completa tarda más: de 12 a 45 s en la GPU del portátil (#269), y producción usa CPU. Una página de voz y piano se lee dos veces (#325, ADR-0060).
- Sin hueco libre, una petición espera 10 s y recibe un 503 (ADR-0024 §5), y la espera es por sondeo, sin orden de llegada.
- La persona no sabe qué está pasando: solo ve «Transcribiendo» y un contador de segundos.

## Decisión

1. **Rutas nuevas, el contrato solo se amplía.** `POST /transcription-jobs` admite los mismos campos que `POST /transcribe`, los comprueba antes (415, 413, 422) y responde **202** enseguida con el trabajo. `GET /transcription-jobs/{id}` dice en qué está; `GET /transcription-jobs` lista los de quien pregunta, del más antiguo al más reciente; `DELETE /transcription-jobs/{id}` quita uno en cola (no se transcribe) u olvida uno terminado (la sesión no se toca), y responde 409 si se está transcribiendo, porque HOMR no se puede interrumpir. `POST /transcribe` no cambia (lo usan `scripts/prepare_study_participant.py` y los experimentos), y `/previews` tampoco (#278).
2. **Una cola real, en orden y de uno en uno.** Un hilo propio de la API toma los trabajos en orden de llegada, de todas las personas, y transcribe cada uno con un hueco de transcripción de ADR-0024, esperándolo sin plazo: los trabajos comparten turno con `POST /transcribe`, y HOMR sigue calculando de uno en uno (`_HOMR_LOCK`). Sin brokers, Celery ni Redis (se mantiene ADR-0016 §3): es una cola en memoria, `TranscriptionJobs` en `cadenza.api.transcription_jobs`.
3. **Topes.** `CADENZA_TRANSCRIBE_JOBS_PER_USER` (10, de 1 a 100) acota los trabajos en cola o en curso de cada persona: con el tope, **429** con un `detail` que dice cuántos tiene. `CADENZA_TRANSCRIBE_JOBS_MAX` (30, de 1 a 500) acota los de todas: con el tope, **503** con `Retry-After: 60`. Cada trabajo en cola guarda su imagen (hasta 20 MB) en memoria hasta que se transcribe; con los valores por defecto, como mucho unos 600 MB en el peor caso, y lo normal son unas pocas páginas de 1 a 3 MB. Al terminar, la imagen se suelta.
4. **Estado y avance, solo con lo que de verdad se ha hecho.** Cada trabajo está en una etapa: `queued` (con `ahead`, los trabajos por delante, contando el que se transcribe), `detecting` (HOMR detecta los pentagramas de la lectura `reading`; con `reading` nulo, aún se prepara: guarda la imagen y espera su turno en HOMR, y la web dice «Preparando la lectura»), `reading` (lee el pentagrama `staff` de `staffs`), `reviewing` (la etapa del compás de ADR-0059, las reglas, las sugerencias y guardar la sesión), `done` (con `result`, como la respuesta de `POST /transcribe`) o `failed` (con `failure`: `unreadable`, sin partitura reconocible; `internal`, otro error). `reading` es `first` en la lectura de la página y `piano` en la segunda lectura de una página de voz y piano, que vuelve a detectar y a contar sus pentagramas: el avance vuelve a empezar, pero con nombre propio. La web enseña una barra solo con los pentagramas ya leídos de la lectura en curso; ningún porcentaje inventado.
5. **El avance sale de HOMR sin cambiar lo que lee.** `cadenza.omr.progress` lleva los avisos del motor a quien escucha en el hilo que transcribe (`ContextVar`); sin nadie escuchando no hace nada, y un fallo de quien escucha se registra sin tumbar la lectura. El adaptador envuelve dos funciones de `homr.staff_parsing`, como ya envuelve `detect_title` y `_select_grandstaffs`: `_get_number_of_voices`, que da los pentagramas de la lectura (voces por sistemas), y `parse_staff_image`, que se llama una vez por pentagrama. Las envolturas llaman a las originales con los mismos argumentos y devuelven lo mismo; una prueba con HOMR real comprueba que el MusicXML es idéntico con y sin seguimiento. Si una versión de HOMR no tiene esas funciones, no hay avance por pentagrama, pero la transcripción sigue.
6. **Registro en memoria, un solo proceso de la API.** El registro vive en la memoria del proceso, sin tabla ni migración: los terminados se guardan una hora (`KEEP_FINISHED_SECONDS`). **Esto supone un único proceso de la API**, como el despliegue actual (un uvicorn en Docker): con varios procesos, cada uno tendría su cola y un trabajo creado en uno no existiría en otro. Si la API se reinicia (un despliegue, ADR-0062, o una caída), lo que estaba en cola o en curso desaparece y su identificador responde 404. La web lo dice («Se interrumpió: ya no está en el servidor y no llegó a crear su sesión (el servidor pudo reiniciarse). Vuelve a subirla.»): nunca queda colgada. El texto no afirma el reinicio porque la web no puede distinguirlo de un trabajo que falló y se olvidó pasada la hora, o que se quitó desde otra pestaña.
7. **La sesión se llama como el trabajo.** Al terminar bien, la sesión creada tiene el mismo identificador que el trabajo. Así, ante un trabajo que ya no existe, la web distingue si llegó a crear su sesión (`GET /sessions/{id}`) o se interrumpió.
8. **Cada persona ve solo los suyos (ADR-0012).** Uno de otra persona responde 404 en las tres rutas que lo nombran, también para un investigador, y la lista solo trae los propios. El autor de la sesión es quien subió la imagen, fijado por el servidor.
9. **El tiempo de cada etapa, al registro.** Al terminar, una línea `transcription_job_finished` con `queued_ms`, `detecting_ms`, `reading_ms`, `piano_detecting_ms`, `piano_reading_ms`, `reviewing_ms`, `running_ms`, los pentagramas de cada lectura y el resultado (#269).
10. **La web.** La vista de transcripción sube todas las imágenes en cuanto se envían, cada una con su trabajo, y pregunta cada segundo por las de la persona con una sola petición mientras haya alguna en curso. Al entrar en la vista pide las de la persona y enseña las que siguen en el servidor, también las de antes de recargar la página o las de la portada. Las subidas que no se vieron terminar se apuntan en `localStorage` (identificador y nombre, nunca la imagen) para decir, tras recargar, cuáles se interrumpieron. Con el tope de la persona o la cola llena, las demás esperan sin error y se suben cuando termina alguna o pasa el `Retry-After`. Al salir de la página solo se pierden las que aún no se han subido. Un fallo pasajero al preguntar (sin conexión, un 5xx, un plazo) no corta el seguimiento: la cola se pone en pausa con «Reanudar» y la portada vuelve a preguntar (hasta diez seguidos). Al lector de pantalla se le anuncian los cambios de etapa, no cada pentagrama. La portada, con sesión, sube y pregunta igual; sin cuenta sigue con `/previews`, síncrona y apagada. Desaparecen la constante de 30 s de la transcripción y sus textos; la subida tiene su propio plazo (`UPLOAD_TIMEOUT_MS`, 120 s) y `/previews` conserva el suyo (`PREVIEW_TIMEOUT_MS`, 30 s).

## Alternativas descartadas

- **Hacer `POST /transcribe` asíncrono.** Rompería el contrato v1 y a sus clientes (el script del estudio, los experimentos).
- **Una tabla de trabajos con migración.** Sobreviviría a un reinicio, pero el trabajo no: HOMR no se puede reanudar, y habría que volver a encolar la imagen, guardarla en la base y limpiar los trabajos huérfanos. El responsable pidió expresamente un registro en memoria.
- **WebSockets o Server-Sent Events.** Menos consultas, pero otra conexión que Nginx y el túnel tienen que mantener abierta y otra pieza que probar; una consulta por segundo de una sola petición por persona basta.
- **Un porcentaje global estimado.** No se sabe cuántos pentagramas tiene la página hasta detectarlos, ni si habrá segunda lectura hasta terminar la primera: cualquier porcentaje de la página entera sería inventado.

## Consecuencias

### Positivas
- Ninguna transcripción falla por tardar: una página entera en CPU (TS-02, voz y piano, unos 21 a 23 s en el portátil) o una cola de varias páginas se esperan sin plazo.
- La persona ve en qué está cada imagen, y puede recargar la página, salir o volver más tarde.
- La cola es justa (en orden de llegada), a diferencia del sondeo de ADR-0024, y la memoria queda acotada por los topes.
- El tiempo de cada etapa queda en el registro para #269.

### Negativas / Riesgos
- Un reinicio de la API pierde lo que estaba en cola o en curso; la persona tiene que volver a subirlo. Con el despliegue continuo (ADR-0062), cada despliegue lo hace.
- Supone un solo proceso de la API; escalar a varios exigiría una cola compartida (la tabla descartada o un broker).
- Una consulta por segundo por persona con transcripciones en curso: unas líneas más en el registro de acceso.
- Lo apuntado en `localStorage` es por navegador: en otro navegador, una transcripción interrumpida simplemente no aparece.
