# ADR-0054: Transcribir sin cuenta desde la portada y reclamarlo al entrar

- **Estado:** Aceptado
- **Fecha:** 2026-11-01
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0004, ADR-0007, ADR-0012, ADR-0016, ADR-0022, ADR-0023, ADR-0024, ADR-0025 y ADR-0053, CLAUDE.md §9)
- **Amplía:** [ADR-0012](ADR-0012-autenticacion-e-identidad.md) (dos rutas más fuera de la sesión: `POST /previews` sin ella y `POST /previews/{id}/claim` con ella)
- **Relacionado:** [ADR-0053](ADR-0053-subir-y-ver-la-transcripcion-desde-la-portada.md), [ADR-0022](ADR-0022-registro-de-cuentas-con-activacion.md), [ADR-0024](ADR-0024-transcripciones-simultaneas.md), [#278](https://github.com/sebdavid3/Cadenza/issues/278), [#277](https://github.com/sebdavid3/Cadenza/issues/277), [#248](https://github.com/sebdavid3/Cadenza/issues/248), [#194](https://github.com/sebdavid3/Cadenza/issues/194)

---

## Contexto

#277 (ADR-0053) puso en la portada un recuadro que transcribe una imagen, pero exige sesión: todas las rutas la piden salvo `/version`, `/health`, `/auth/login` y `/auth/register` (ADR-0012, ADR-0022). Una sesión siempre tiene dueño (`sessions.owner_id` no admite nulos) y una imagen subida se queda para siempre en el almacén de artefactos (D59). HOMR tiene dos huecos por defecto, compartidos con el estudio (ADR-0024), y el servidor es público por Tailscale Funnel (ADR-0023), con Nginx delante.

#278 pide que alguien sin cuenta suba una imagen, vea su transcripción y, si quiere editarla, entre o se registre y la transcripción pase a ser una sesión suya sin volver a ejecutar HOMR. Abrir algo sin cuenta obliga a decidir los límites contra el abuso. Las políticas completas del registro abierto (D59, #194) siguen fuera de la entrega.

## Decisión

### 1. Dos rutas, una ampliación compatible del contrato v1

- **`POST /previews`**, sin sesión. Multipart como `POST /transcribe`: `file` y, opcionales, `title`, `composer`, `instruments` y `part_names` (ADR-0041); sin `condition` ni `test_score_id`, que son del estudio. Responde **201** con `PreviewResponse`: `preview_id`, `claim_token`, `expires_at`, `findings_count`, `musicxml` (null si no se pudo exportar), `score` (`ScoreIRPayload`), `timing` (`TimingMapRead`, con el `preview_id` como `session_id`), `title`, `composer`, `instruments` y `source_filename`. Lo que la web necesita para enseñarlo viene en la respuesta, sin otra petición.
- **`POST /previews/{preview_id}/claim`**, con sesión. Cuerpo `{"claim_token": "…"}`. Responde **201** con `TranscribeResponse`, como `POST /transcribe`.

Se regeneran `openapi.json` y `types.ts`. Ninguna ruta existente cambia.

### 2. Dónde vive: una tabla propia, no una sesión

La migración **0016** crea `previews`: `id`, `token_hash`, `document` (el `ScoreDocument` que leyó HOMR), `image` (los bytes, `BYTEA`), `image_media_type`, los datos de la partitura (las columnas de ADR-0041), `source_filename`, `created_at` y `expires_at` (con índice). La 0015 es de #188 (`0015_effort_accumulated`), hecha en paralelo sobre la misma base: al rebasar sobre `dev`, la 0016 pasa a colgar de ella (`down_revision`), para que Alembic no tenga dos cabezas.

- **No es una sesión:** no tiene dueño, log, hallazgos ni sugerencias guardadas, y `sessions.owner_id` no cambia. Ningún listado, ni el de un investigador, la ve; tampoco el dataset del plano offline.
- **La imagen va en la fila**, no en el almacén de artefactos. Así, reclamar es una sola transacción (borrar la fila y crear la sesión), y caducar es borrar filas sin mirar si otra sesión usa la misma imagen, que en el almacén direccionado por contenido sería la misma entrada (ADR-0004). El tope de §5 acota lo que ocupa.
- **Del token solo se guarda su SHA-256.** Son 32 bytes aleatorios (`secrets.token_urlsafe`); se comparan con `hmac.compare_digest`.

### 3. Caducidad y limpieza

Una transcripción sin cuenta caduca a la hora (`CADENZA_ANONYMOUS_PREVIEW_TTL_SECONDS`, 3600 por defecto, de 60 a 86 400). Caducada no se puede reclamar. Las caducadas se borran, con su imagen, que va en la fila, al arrancar la API, en cada `POST /previews` y en cada reclamación. No hay una tarea periódica: con la API en marcha y sin tráfico pueden esperar más de una hora (como mucho, las del tope de §5), pero apagar el interruptor y reiniciar la API las borra.

### 4. Reclamarla: la misma sesión que `POST /transcribe`, una sola vez

Con sesión y el token, `claim_preview`:

1. Busca la transcripción. Si no existe, si caducó o si el token no es el suyo, responde **404**, igual en los tres casos: no se puede averiguar cuáles existen.
2. Borra la fila con un `DELETE` condicionado. Si dos peticiones la reclaman a la vez, la base deja borrar a una sola y la otra recibe 404: el token vale una vez.
3. Guarda la imagen en el almacén de artefactos y crea la sesión con `create_session_from_document`, la misma función que usa ahora `transcribe_score`. Así se evalúan las reglas y la capa de sugerencias (si está encendida) sobre el mismo documento, se fija la procedencia y la sesión nace en condición asistida. HOMR no vuelve a ejecutarse.
4. El dueño es quien reclama, fijado por el servidor con su token (ADR-0012). Antes de reclamarla no hay autor ni edición posible, así que nada entra en el log sin cuenta.

Los posibles errores se cuentan al transcribir y se vuelven a evaluar al reclamar. Si las reglas cambian entre medias (una hora como mucho), el número puede variar.

### 5. Límites contra el abuso

- **Interruptor.** `CADENZA_ANONYMOUS_PREVIEW_ENABLED`, apagado por defecto. Apagado, las dos rutas responden **404** (tras recibir el cuerpo, que FastAPI lee antes de las dependencias), como el registro (#248). Va apagado durante el estudio. Como el registro, encendido exige CORS cerrado al origen de la interfaz (no `*`): si no, cualquier web podría gastar los huecos de HOMR desde el navegador de sus visitantes. La web lo recibe en el build (`VITE_ANONYMOUS_PREVIEW_ENABLED`); un 404 de la API, con la web todavía encendida, vuelve a pedir que se entre.
- **HOMR.** Como mucho una transcripción sin cuenta a la vez (un semáforo propio), y nunca espera un hueco: si los de ADR-0024 están ocupados, por el estudio o por quien entró, responde **503** con `Retry-After: 10` al momento. Con dos huecos, quien entra conserva al menos uno. El semáforo se toma antes de comprobar el tope, para que no se rebase entre la comprobación y el alta, y lo suelta una sola vez quien lo tenga: el trabajo si llega a empezar, o la petición si falla o se cancela antes. La exportación del MusicXML y los tiempos también corren en el hilo del trabajo, fuera del bucle de eventos.
- **Por IP.** `CADENZA_ANONYMOUS_PREVIEW_RATE_LIMIT_MAX_ATTEMPTS` intentos (5) por ventana (`…_WINDOW_SECONDS`, 3600) y por IP (la red /64 en IPv6, como el registro), contados antes de transcribir y también los que fallan. Por encima, **429** con `Retry-After`. La IP es la que resuelven Nginx y uvicorn tras Funnel (ADR-0023). Nginx añade zonas propias para `/api/previews`: una por minuto por visitante, con ráfagas de tres, y una conexión abierta a la vez (aparte de las de `/api/transcribe`). Nginx solo admite tasas por segundo o por minuto (`rate=6r/h` no pasa `nginx -t`), así que es una primera barrera más laxa: el límite por hora lo pone la API.
- **Tope global.** Como mucho `CADENZA_ANONYMOUS_PREVIEW_MAX_ACTIVE` (20) guardadas a la vez, vengan de las IP que vengan. Con el tope, **503** con `Retry-After: 60`, antes de ejecutar HOMR. Con 20 MB por imagen, a lo sumo unos 400 MB en la base.
- **Tamaño y tipo.** Las comprobaciones de `POST /transcribe`: hasta 20 MB (413) y una imagen por sus primeros bytes (415). Nginx ya limita el cuerpo a 21 MB.

### 6. La web

El recuadro de ADR-0053 cambia solo sin sesión, y solo si el build lo abre:

- El formulario ofrece «Transcribir la imagen», que envía `POST /previews` sin token, y dice que sin cuenta la transcripción se guarda una hora. El resultado se enseña como con sesión (`ResultView`): el nombre, los posibles errores, la reproducción y la partitura en solo lectura. Viene todo en la respuesta. Las acciones son «Entrar para editarla», «Crear una cuenta» (si el registro está abierto) y «Transcribir otra imagen», con la hora a la que caduca.
- Al transcribir, la web apunta en `sessionStorage` el id, el token, la caducidad y el nombre (`cadenza.portada.reclamar`), **nunca la imagen**. «Entrar para editarla» lleva a entrar o a crear la cuenta con `state.from = "/#transcribir"`. Al volver con sesión, la portada la reclama sola y abre `/sesiones/:id`. Lo hace también tras una recarga: entonces solo queda el token, y la portada dice que hay una transcripción sin cuenta pendiente. Con sesión, en lugar de entrar, «Editar» la reclama.
- La imagen se queda en memoria hasta reclamarla. Si la reclamación responde 404 (caducó o ya se usó), con la imagen aún en memoria se ofrece transcribirla con la cuenta (`POST /transcribe`); sin ella, se dice que hay que volver a elegirla.
- Un 404 de `POST /previews` (la API lo apagó) deja el recuadro como en ADR-0053: pide entrar, «Ahora no se puede transcribir sin cuenta», y no lo vuelve a intentar mientras no se salga de la sesión. El 429 dice cuándo volver a probar o que se entre; el 503, el 413, el 415 y el 422 se dicen como en la cola.
- Con sesión, la portada sigue usando `POST /transcribe` (ADR-0053).

## Consecuencias

### Positivas
- Cadenza se puede probar desde la primera pantalla sin crear una cuenta, y lo transcrito no se pierde al entrar.
- Ni las sesiones, ni su dueño, ni el log, ni el dataset cambian: lo transcrito sin cuenta vive aparte hasta que una cuenta lo reclama, y entonces es una sesión como cualquier otra.
- Apagado (el valor por defecto y el del estudio), el sistema se comporta exactamente como antes.

### Negativas / Riesgos
- Gasta HOMR en visitantes sin cuenta. Por eso se despliega después del estudio y nunca espera un hueco. Aun así, con un hueco ocupado por una transcripción sin cuenta, quien entra tiene uno menos durante unos segundos.
- Las imágenes sin cuenta ocupan la base hasta caducar (el tope acota cuánto) y entran en las copias de seguridad de esa hora.
- El límite por IP vive en la memoria de la API, como el del registro: se reinicia con ella, y varias personas tras una misma IP lo comparten.
- Las caducadas se borran al arrancar, al transcribir otra y al reclamar; con la API en marcha y sin tráfico, pueden quedarse más de una hora (como mucho, las del tope).
- El tope global es barato de agotar: unas pocas IP (o redes /64) dentro de su límite lo mantienen lleno una hora, y mientras tanto `POST /previews` responde 503. Se acepta para una portada de demostración; quien tiene cuenta no se ve afectado.
- El 503 de huecos ocupados o del tope cuenta en el límite por IP, como cualquier intento.
- En un equipo compartido, si alguien deja una transcripción sin cuenta y otra persona entra en la misma pestaña desde «Entrar para editarla», la reclama a su nombre.
- El token en `sessionStorage` permite reclamar tras una recarga en esa pestaña. Quien tenga acceso a la pestaña antes de que caduque podría reclamarla con su cuenta; es lo mismo que ver su resultado, que no tiene dueño.

## Alternativas consideradas

1. **Una sesión con `owner_id` nulo o con un usuario anónimo.** Descartada: cambiaría una invariante del modelo (toda sesión tiene dueño), y los listados, el acceso de los investigadores, el log y el dataset tendrían que distinguir sesiones sin dueño.
2. **La imagen en el almacén de artefactos.** Descartada: caducar tendría que saber si otra sesión usa la misma imagen (mismo contenido, mismo hash), y reclamar sería dos almacenes en dos pasos.
3. **Guardar los hallazgos con la transcripción sin cuenta.** Descartada: al reclamarla se vuelven a evaluar sobre el mismo documento, y así la sesión nace igual que con `POST /transcribe`, con la capa de sugerencias incluida.
4. **Un hueco de HOMR reservado para lo transcrito sin cuenta.** Descartada: con dos huecos, reservar uno dejaría al estudio con uno. Compartir los huecos sin esperar nunca, y como mucho uno a la vez, protege a quien entró.
5. **Una tarea periódica de limpieza.** Descartada por ahora: la API no tiene planificador; limpiar en cada `POST /previews`, con el tope global, acota lo guardado sin añadir otro proceso.
6. **Reclamar con el token en la URL.** Descartada: quedaría en el historial y en los registros de Nginx; va en el cuerpo de un POST con sesión.
