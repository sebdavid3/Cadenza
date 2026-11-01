# ADR-0050: Medir el esfuerzo de la corrección en la vista, con un solo registro por sesión que acumula tramos

- **Estado:** Aceptado
- **Fecha:** 2026-11-01
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0004, ADR-0007, ADR-0009, ADR-0011, ADR-0012, ADR-0014, ADR-0034, ADR-0035, ADR-0036, ADR-0039, ADR-0040, ADR-0043, ADR-0044 y ADR-0047, CLAUDE.md §9), sobre las definiciones que fijó el responsable en [#244](https://github.com/sebdavid3/Cadenza/issues/244) (protocolo §3.4)
- **Completa:** [ADR-0043](ADR-0043-finalizar-y-reabrir-desde-la-vista.md) §16 (lo medido se envía antes de finalizar, no desde su 200) y [ADR-0009](ADR-0009-capa-de-aplicacion.md) (`record_effort`, #13, sigue como está)
- **Relacionado:** [ADR-0034](ADR-0034-deshacer-y-rehacer-desde-la-vista.md), [ADR-0035](ADR-0035-descartar-restaurar-y-revalidar-desde-la-vista.md), [ADR-0036](ADR-0036-capa-de-sugerencias-aprendida.md), [ADR-0039](ADR-0039-anadir-y-quitar-marcas-de-notacion.md), [ADR-0044](ADR-0044-compas-con-su-simbolo-y-tresillos-como-edicion.md), [ADR-0047](ADR-0047-ver-aplicar-y-rechazar-sugerencias-desde-la-vista.md), [#188](https://github.com/sebdavid3/Cadenza/issues/188), [#187](https://github.com/sebdavid3/Cadenza/issues/187), [#250](https://github.com/sebdavid3/Cadenza/issues/250), [#251](https://github.com/sebdavid3/Cadenza/issues/251)

---

## Contexto

El estudio con participantes (D38, `docs/experimentos/protocolo_medicion_esfuerzo.md`) mide el esfuerzo de cada corrección. El responsable fijó en #244 (§3.4 del protocolo):

- **Duración:** solo el tiempo con la página de la sesión visible (`document.visibilityState`) y con actividad. Se descuenta lo que la pestaña estuvo oculta y, de cada pausa sin teclado, ratón ni toque más larga que un umbral, todo salvo el umbral. Umbral: 2 minutos, confirmado por el responsable el 2026-11-01 (#244). Las recargas no cortan la medición: se acumula sobre el mismo registro. Una partitura sin finalizar no entra en el análisis.
- **Tiempo hasta la primera edición:** con la misma regla de tiempo visible.
- **Intervenciones:** cada edición guardada cuenta en el compás de su ancla, también deshacer y rehacer (ADR-0034), y las marcas, el compás y los tresillos, contados por su clase (`CONTENT_EDIT_OPS`, `MARK_EDIT_OPS`, `METER_EDIT_OPS`). Descartar y restaurar un posible error, y aplicar o rechazar una sugerencia, se cuentan aparte.
- **Reabrir:** un solo registro por sesión, que acumula todo hasta la última finalización.

Lo que había (leído en el código el 2026-11-01, `dev` en `340039f`):

- `POST /sessions/{id}/effort` (#13) guarda **una fila nueva** en `effort_metrics` cada vez, con `duration_ms`, `time_to_first_edit_ms` e `interventions` tal como las manda el cliente; `GET` las lista todas. Nadie la usaba: la web no medía nada.
- `exp_10` tomaba la fila más reciente de **todas** las sesiones de las cuentas del estudio, finalizadas o no, y daba 0 ms a una sesión sin fila.
- `compute_interventions_from_edits` ya contaba las ediciones del log por compás de su ancla.
- Deshacer es una edición compensatoria del log, de la misma operación (ADR-0007, ADR-0034); rehacer reenvía la edición como nueva. Aplicar una sugerencia es una edición con `suggestion_id` que la deja `accepted`; rechazarla guarda `rejected`, y un rechazo heredado por una revalidación repite la respuesta con `inherited_from` (ADR-0036 §4). Restaurar un descarte borra sus datos: el estado de los posibles errores no dice cuántas veces se descartó o restauró.
- Una sesión finalizada no admite ediciones ni órdenes sobre los posibles errores (409, ADR-0014, ADR-0043).

## Decisión

### 1. Lo que solo sabe la página, la página; lo que sabe el servidor, el servidor

- **La página mide el tiempo**: es la única que sabe si se ve y si hay actividad.
- **El servidor cuenta las intervenciones** a partir del log (que es inmutable y es la verdad de lo que se guardó), **los descartes y las restauraciones** al guardarlos, y **las sugerencias aplicadas y rechazadas** a partir de sus respuestas guardadas. Que el cliente los contara y los enviara añadiría una copia que puede perderse en una recarga o discrepar del log.

### 2. Un registro por sesión que suma tramos

- **`PUT /sessions/{id}/effort/segments/{segment_id}`** con `EffortSegmentUpdate` (`active_ms`, `first_edit_ms`, `idle_threshold_ms`) guarda lo que midió una pestaña hasta ahora. El servidor mantiene **un solo registro por sesión** (`effort_metrics.accumulated`, con un índice único parcial) y suma sus tramos: `duration_ms` es la suma de `active_ms`.
- **Un tramo es una pestaña**, con un identificador aleatorio que se guarda en `sessionStorage` con lo medido: una recarga sigue el mismo tramo desde donde iba, y un tramo nuevo (otra pestaña, o sin `sessionStorage`) se suma a los demás. Así la recarga acumula sin depender de que el último envío llegara.
- **Un tramo solo crece**: el servidor guarda el máximo de `active_ms` y la primera `first_edit_ms` que conoce. Repetir una petición o recibir tarde una anterior no cuenta dos veces; ninguna petición resta. Quien lee el registro para reescribirlo lo bloquea (`SELECT … FOR UPDATE` en PostgreSQL), así que dos tramos a la vez no se pisan. Sin `sessionStorage`, lo que no llegó a enviarse de una carga se pierde (como mucho el intervalo de envío, o nada si salió el envío al ocultar la página).
- **El tiempo hasta la primera edición** es el de los tramos anteriores al que guardó la primera edición del log (la de `seq` 1) más el de ese tramo hasta guardarla. La página apunta ese tiempo al recibir el 201 de una orden con `seq` 1 y lo envía en el acto. Si ningún tramo lo dice, es `null`: no se sabe, y no se inventa.
- **`idle_threshold_ms`** va con cada tramo: el registro dice con qué umbral se midió, para comprobar que todo el estudio usó el mismo.
- **Solo el dueño**: 404 a un transcriptor ajeno y 403 a un investigador ajeno (ADR-0012). **409 si la sesión está finalizada**: lo que se mide después de finalizar no es corrección. **422** si el tramo no puede ser: identificador de 1 a 64 caracteres `[A-Za-z0-9_-]`, tiempos negativos, una primera edición posterior al tiempo del tramo, más de 500 tramos o una duración que no cabe en la columna.

### 3. Lo que sale del log se vuelve a contar con cada tramo y al finalizar

- Con cada tramo, y **al finalizar** (`finalize_session` con `effort_repository`), se vuelven a calcular del log `interventions` (todas las ediciones por compás del ancla) e `interventions_by_class` (`content`, `mark` y `meter` por compás, siempre las tres), y de las sugerencias `suggestions_applied` y `suggestions_rejected` (sin los rechazos heredados).
- **Deshacer y rehacer cuentan**: son ediciones del log. Una compensatoria cuenta en la clase de la operación que deshace. **Una sugerencia aplicada es también una edición guardada**: cuenta como intervención en su compás y, aparte, en `suggestions_applied`; el análisis puede restarlas si lo necesita.
- **Finalizar** recuenta sin crear el registro si no existe: una sesión sin tramos no se midió. **Reabrir y volver a finalizar** sigue sumando en el mismo registro: el log ya contiene todo hasta la última finalización.

### 4. Descartar y restaurar se cuentan al guardarse

`dismiss_finding` y `restore_finding` reciben el repositorio de esfuerzo y suman `findings_dismissed` o `findings_restored` **solo si la orden cambia el estado** del posible error (de activo a descartado, o al revés): repetirla no es otra acción. La suma se hace en la base (`UPDATE … SET n = n + 1`) y crea el registro si aún no lo hay; guardar un tramo no toca esos contadores.

### 5. La vista

- **Se mide a quien transcribió la sesión mientras está abierta** (`useEffortMeter`, `pages/session/effort.ts`), desde que carga su detalle. Una sesión ajena o finalizada no se mide ni envía nada.
- **El reloj** (`EffortClock`, puro y probado con un reloj falso) usa `performance.now()`: cuenta con la página visible y la medición en marcha; cada `keydown`, `pointerdown`, `pointermove`, `wheel` o `touchstart` acaba la pausa en curso, de la que solo suma el umbral. Cargar la vista o volver a la pestaña empieza una pausa, como si se acabara de mover el ratón.
- **El umbral** es `EFFORT_IDLE_THRESHOLD_MS` en `apps/web/src/config.ts`, el único sitio donde se fija (2 minutos, confirmado por el responsable el 2026-11-01, #244).
- **Cuándo se envía:** al empezar a medir (crea el registro), cada 10 s si cambió, al guardarse la primera edición, al ocultar o dejar la página (`visibilitychange`, `pagehide`, con `fetch` y `keepalive`, que lleva el token a diferencia de `sendBeacon`) y antes de finalizar. Los envíos van de uno en uno; tras un rechazo (409, 404, 403) el reloj se para y no se envía nada hasta volver a medir: lo de después de finalizar en otra pestaña no es corrección.
- **Finalizar** (enmienda de ADR-0043 §16): al confirmar, el reloj se para y lo medido se envía **antes** de `POST /finalize`, porque una sesión finalizada ya no admite más tiempo. Si no llega la confirmación de ese envío, no se finaliza y se dice «No se finalizó: no llegó la confirmación del servidor…», sin hablar de la medición; un rechazo deja que finalizar responda con su propio mensaje. Si la sesión no queda finalizada, el reloj sigue; al reabrir, vuelve a contar en el mismo tramo.
- **Salir sin finalizar**: lo medido queda guardado en el registro (el envío al dejar la página) y sigue sumando al volver; la sesión no entra en el análisis hasta que se finalice.
- **Nada de esto se muestra**: ni el tiempo, ni las intervenciones, ni la condición o el `test_score_id`. En la condición no asistida la vista ya no muestra nada del validador (ADR-0040 §13); la medición es la misma en las dos condiciones.

### 6. `exp_10`

Lee solo las **sesiones finalizadas** de las cuentas del estudio, con **el registro acumulado** de cada una si tiene algún tramo (o, si no, el registro suelto más reciente de `POST /effort`). Un registro acumulado sin tramos no es una medición: lo crea también un descarte. Una sesión finalizada sin medición no se midió: no entra en las filas y el resumen la nombra en `finalized_sessions_without_effort`. Las filas llevan, del registro acumulado, las intervenciones por clase y los cuatro contadores; los datos sintéticos los dejan vacíos.

### 7. Contrato y migración

Ampliación compatible: la ruta nueva, `EffortSegmentUpdate` y `EffortSegmentRead`, y campos nuevos con valor por defecto en `EffortMetricsRead`. `POST /effort` y `GET /effort` siguen igual (el `GET` lista también el registro acumulado, con `accumulated: true`). **Migración 0015** (`0015_effort_accumulated`): `accumulated`, `segments`, `interventions_by_class`, los cuatro contadores y `updated_at` en `effort_metrics`, y el índice único parcial `uq_effort_metrics_accumulated_session`; los registros anteriores quedan sueltos, sin tramos y a cero.

## Consecuencias

### Positivas
- La duración, la latencia y las intervenciones siguen la definición del protocolo, y las intervenciones son exactamente las del log, por compás y por clase.
- Una recarga, una pestaña nueva o reabrir no cortan ni duplican la medición: el servidor suma y los envíos son idempotentes.
- `exp_10` deja de analizar sesiones sin finalizar y deja de dar 0 ms a una sesión sin medir.

### Negativas / riesgos
- **Dos pestañas visibles a la vez** (dos ventanas lado a lado) contarían el tiempo dos veces, y **duplicar una pestaña** copia su `sessionStorage`: las dos siguen el mismo tramo y se cuenta solo la que más midió. El protocolo corrige en una pestaña.
- **Lo no enviado se pierde** si el navegador se cierra de golpe sin `pagehide` y sin `sessionStorage` (como mucho 10 s), y la primera edición queda en `null` si se guardó y la página se cerró antes de enviarla.
- **El primer tramo y el primer descarte a la vez** podrían crear el registro dos veces: el índice único rechaza el segundo y esa petición falla sin contar nada (la vista reenvía el tramo; un descarte se repite a mano). La vista crea el registro al cargar, antes de poder descartar nada.
- **Dos descartes simultáneos del mismo posible error** leen los dos «activo» y suman dos. La vista no lo permite (las órdenes sobre los posibles errores van de una en una, ADR-0035 §6, ADR-0047 §5); un cliente de la API sí podría.
- **El tiempo de la página es el del navegador**: una pestaña en segundo plano con el temporizador frenado no suma porque no está visible; un equipo suspendido con la pestaña visible suma como mucho el umbral.
- **Finalizar necesita dos peticiones**: si la red cae entre las dos, lo medido ya está guardado y finalizar se repite con el mensaje de siempre.

## Alternativas consideradas

| Alternativa | Motivo del descarte |
|---|---|
| Medir en el cliente y enviar todo una vez con `POST /effort` al finalizar | Una recarga o una pestaña cerrada perderían lo medido; reabrir crearía otra fila; las intervenciones serían una copia del log que puede discrepar. |
| Que `POST /effort` sustituya o sume sobre una sola fila | Cambia lo que hace una ruta del contrato congelado (ADR-0009, #13). |
| Enviar incrementos («suma estos ms») | Un reintento o una petición repetida contaría dos veces; el máximo por tramo es idempotente. |
| Contar en el cliente los descartes y las restauraciones | El servidor los ve al guardarlos, en la misma transacción; el estado de los hallazgos no los conserva, así que hace falta un contador. |
| Enviar lo medido desde el 200 de finalizar (ADR-0043 §16) | Con la sesión ya finalizada, aceptar más tiempo dejaría abierta la puerta a sumar lo de después de finalizar. |
| `navigator.sendBeacon` al dejar la página | No lleva el token (`Authorization`); `fetch` con `keepalive` sí. |
| Contar `scroll` o `focus` como actividad | El protocolo nombra teclado, ratón y toque; la rueda y el puntero ya cubren desplazarse con ellos. |
