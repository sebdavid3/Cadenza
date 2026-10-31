# ADR-0037: Una edición en un solo viaje, sin rehacer el estado en el servidor

- **Estado:** Aceptado
- **Fecha:** 2026-10-30
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0007, ADR-0009, ADR-0011, ADR-0012, ADR-0014, ADR-0015, ADR-0017, ADR-0023 y ADR-0035, CLAUDE.md §9 y §10)
- **Enmienda:** [ADR-0030](ADR-0030-correccion-de-altura-duracion-y-alteracion.md) §4 (tras el 201 ya no se piden el detalle, el MusicXML, los posibles errores ni los tiempos) y [ADR-0034](ADR-0034-deshacer-y-rehacer-desde-la-vista.md) §1 (lo mismo al deshacer y rehacer; el contrato sí cambia, con una ampliación compatible)
- **Relacionado:** [ADR-0007](ADR-0007-edit-events-inmutables.md), [ADR-0011](ADR-0011-semantica-de-anclas-ante-ediciones.md), [ADR-0017](ADR-0017-validacion-del-contenido-de-las-ediciones.md), [ADR-0023](ADR-0023-despliegue-publico-con-tailscale-funnel.md), [ADR-0035](ADR-0035-descartar-restaurar-y-revalidar-desde-la-vista.md), D38, [#275](https://github.com/sebdavid3/Cadenza/issues/275), [#276](https://github.com/sebdavid3/Cadenza/issues/276), [#235](https://github.com/sebdavid3/Cadenza/issues/235)

---

## Contexto

El estudio con participantes mide el tiempo de corrección (D38): cada espera de una edición se suma al esfuerzo medido. Lo que costaba una edición, leído en el código antes de este cambio:

- **Cinco peticiones seguidas, con el editor bloqueado:** `POST /edits`; después `GET /sessions/{id}`; después, en paralelo, `GET /export?format=musicxml`, `GET /findings` y `GET /timing` (ADR-0030 §4, ADR-0034 §1).
- **El estado se rehacía cuatro veces.** Las cuatro rutas que leen el estado cargaban el documento y volvían a aplicar el log entero desde el `ScoreIR` crudo (`materialize`); el detalle construía además el índice de anclas (eventos por ediciones), que la vista no usa; `/export` exportaba con music21 en cada petición.
- `append_edit` pedía `next_seq` en otra consulta, aunque el log leído ya lo da.
- El MusicXML viajaba sin comprimir (`gzip_types` de Nginx no lo incluía y, sin `gzip_proxied`, lo que llega por Funnel no se comprime).
- No se medía por etapas, y Nginx sustituía el `X-Request-ID` del cliente por el suyo.

Lo que no se toca: el `base_seq` del estado que se ve y el 409 sin reintento (ADR-0011), el log solo de añadir (ADR-0007), la edición inválida nunca guardada (ADR-0017), sin actualización optimista (ADR-0030, ADR-0034) y sin revalidar tras cada edición (ADR-0035).

## Decisión

1. **La respuesta trae el estado nuevo.** El 201 de `POST /sessions/{id}/edits` pasa a ser `EditAppliedRead`: los campos de `EditEventRead`, sin cambios, más `current_seq`, `current_score`, `status`, `musicxml` y `timing`. La respuesta de `POST /undo` (`UndoResponse`) suma `status`, `musicxml` y `timing` a los suyos. `musicxml` es el mismo texto que daría `/export` (null si music21 no pudo exportarlo: la edición queda guardada y `/export` da el error, como antes, ADR-0034 §4). `timing` es el mapa de `/timing` solo si cambia respecto del estado `base_seq` (una altura o una alteración no lo cambian); si no, null. Es una ampliación compatible del contrato v1: ningún campo existente cambia.
2. **La vista no pide nada más.** Compone el estado nuevo sobre el que ve: el log con la edición (o la compensatoria), la partitura, el MusicXML y los tiempos (los del estado anterior si no cambian), y copia los posibles errores, que no cambian sin revalidar. Solo pide el MusicXML si llega null y los tiempos si no cambian y no los tenía. Si la respuesta no trae el estado (un servidor anterior) o lo que ve ya no es `base_seq`, recarga todo como antes. Si mientras tanto llegó un estado posterior, no vuelve atrás. El 409 sigue recargando y nunca se reintenta; no hay actualización optimista: nada cambia en la vista antes de la respuesta.
3. **Caché del estado en el proceso.** `packages/application` guarda el `ScoreIR` materializado de cada estado, con su MusicXML y su mapa de tiempos cuando se calculan, por `(sesión, seq, id de la última edición)` (`InMemoryScoreStateCache`, LRU segura entre hilos, `CADENZA_SCORE_CACHE_MAX_ENTRIES`, 32 por defecto; 0 la apaga). Es válida porque el log no cambia (ADR-0007). El id de la última edición en la clave hace inalcanzable el estado de una edición cuya transacción no se confirmó. La edición, el detalle, `/export`, `/timing` y deshacer la usan; el estado nuevo de una edición es `apply_edit` sobre el anterior, el mismo que da `materialize` con el log que la incluye. La validación (`_validate_before`, `validate_after`, `apply_edit`) se hace siempre. `materialize` no cambia, ni las cifras de `exp_02` y `exp_05`. El `seq` nuevo es el del log leído más uno, sin la consulta de `next_seq`; la restricción única `(sesión, seq)` sigue dando el 409.
   - **#235:** el título y los instrumentos no son ediciones del log. El `PATCH` que los cambie debe llamar a `score_cache.invalidate(session_id)` o meter su versión en la clave. Con una sola instancia de uvicorn (ADR-0015) basta invalidar; con varios procesos haría falta la versión.
4. **El detalle sin lo que la vista no usa.** `GET /sessions/{id}?fields=view` devuelve `SessionViewRead`: los campos del detalle sin `document` ni `anchor_index`, que no se construye. Sin `fields`, la respuesta y su esquema en el contrato no cambian; `SessionViewRead` se declara en los componentes y en la descripción del parámetro.
5. **Medir.** Cada respuesta lleva `Server-Timing` por etapa, en milisegundos: `db`, `materialize` (reconstruir el estado o validar y aplicar la edición, y el índice de anclas), `export`, `timing`, `serialize` y `total`. Las etapas las marcan los casos de uso con `contextvars` (biblioteca estándar, sin romper la pureza de §10) y la API las recoge en el middleware. Las rutas de edición, deshacer, detalle y tiempos serializan el modelo una sola vez (`model_dump_json`). La web envía un `X-Request-ID` por petición (`web-` y 20 cifras hexadecimales); la API lo devuelve y lo registra si tiene la forma `[A-Za-z0-9._-]{1,64}`, y Nginx lo deja pasar con esa forma. La web marca en `performance` el envío, la respuesta y el dibujado de cada orden (`cadenza:orden-N:…`).
6. **Nginx comprime el MusicXML** (`application/vnd.recordare.musicxml+xml`) con `gzip_proxied any` y `gzip_vary on`.
7. **Experimento `exp_13`** (`ml/experiments/exp_13_edit_latency.py`): la latencia de una corrección con 0, 50 y 200 ediciones previas, en el íncipit de las pruebas de la API y en una página de 48 compases compuesta repitiéndolo, con la API en el mismo proceso (`TestClient`, SQLite temporal o `--database-url`). Compara las cinco peticiones de antes con el viaje único y guarda `Server-Timing`.

## Consecuencias

### Positivas
- Una corrección es una petición. La respuesta de la página ya no lleva el `document` ni el índice de anclas del detalle, y el estado anterior sale de la caché en lugar de rehacerse cuatro veces. Las cifras de antes y después no se citan aquí: la comparación válida es `exp_13` con `five_requests` contra el código anterior a este cambio (con #275, `five_requests` ya no reproduce aquel servidor, porque el `POST` exporta y el `GET /export` siguiente sale de la caché) frente a `single_trip` contra este, en el mismo equipo y sin otra carga, y se regenera antes de citarla (CLAUDE.md §8). Las mediciones exploratorias en local, con el equipo cargado, apuntaron a que la exportación con music21 es ahora casi todo el coste del servidor.
- El coste de una edición ya no crece con el log: el estado anterior sale de la caché.
- `Server-Timing`, el `X-Request-ID` y las marcas de la web permiten medir en producción sin herramientas nuevas.

### Negativas / Riesgos
- La exportación, los tiempos y la serialización ocurren dentro de la transacción de la edición (el commit va tras la ruta): una exportación lenta alarga la transacción. No se ha medido con PostgreSQL.
- La caché ocupa memoria del proceso (32 estados por defecto, cada uno con su `ScoreIR` y su MusicXML) y es de cada proceso: con varios workers, cada uno tendría la suya, y la invalidación de #235 tendría que ir en la clave.
- Si falla el cálculo de los tiempos (no la exportación), la edición responde 500 y no se guarda; antes se guardaba y fallaba `/timing`. `compute_timing_map` es puro y no ha fallado en las pruebas.
- `Server-Timing` va en todas las respuestas, también en las de acceso; solo dice cuánto tardó cada etapa.
- El `X-Request-ID` de una orden va en su petición; las de respaldo (la recarga tras un 409) llevan el suyo.
- **Pendiente:** medir en el servidor de producción, del clic a la respuesta y al dibujado, y fijar el objetivo propuesto en el issue (menos de 300 ms p95 en una página completa con 200 ediciones). La página de `exp_13` es sintética (el íncipit repetido); falta una página real transcrita por HOMR.

## Alternativas consideradas

1. **Instantánea del estado guardada en la base, en la misma transacción que la edición.** Descartada por ahora: necesita una migración y espacio por edición; la caché en el proceso basta con una instancia y se reconstruye sola tras un reinicio.
2. **Devolver el estado en una respuesta nueva (`POST /edits?return=state`) o un endpoint aparte.** Descartada: ampliar la respuesta es compatible y evita dos formas de editar.
3. **Actualización optimista en la vista.** Prohibida por ADR-0030 y ADR-0034.
4. **Cambiar el detalle por defecto para quitar `document` y `anchor_index`.** Rompería el contrato v1 congelado; por eso es opcional (`fields=view`).
5. **Revalidar con cada edición para devolver también los posibles errores.** Contraria a ADR-0035: la revalidación es explícita.
