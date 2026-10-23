# ADR-0024: Transcripciones simultáneas: HOMR de una en una y tope de admisión en la API

- **Estado:** Aceptado
- **Fecha:** 2026-10-23
- **Decisores:** Equipo de Desarrollo
- **Relacionado:** [ADR-0016](ADR-0016-transcripcion-sincrona-vs-asincrona.md) (transcripción síncrona), [ADR-0018](ADR-0018-homr-como-unico-motor-omr.md) (HOMR como único motor), [ADR-0023](ADR-0023-despliegue-publico-con-tailscale-funnel.md) (despliegue público)

---

## Contexto

`POST /transcribe` es síncrono (ADR-0016): ejecuta HOMR en un hilo con `asyncio.to_thread` y responde al terminar. Antes del despliegue público, las pruebas en el servidor (#156) destaparon dos problemas cuando llegan varias transcripciones a la vez:

1. **HOMR no es seguro entre hilos.** Con cuatro imágenes distintas a la vez, en tres rondas, cada ronda acabó con uno o dos 201; el resto dio 422 con errores internos de ONNX Runtime (`ml_value->IsTensor() was false`; una salida preasignada de `MultiHeadAttention` con una forma que no coincide). Las sesiones de ONNX de HOMR y sus salidas preasignadas son estado global del proceso, y dos hilos se las pisan. Una sola transcripción cada vez funciona.
2. **Nada limita cuántas transcripciones calcula la API.** Si el cliente corta la conexión, el hilo sigue calculando. El cliente web aborta a los 30 s y sigue con la siguiente imagen de su cola, así que en CPU los cálculos lentos se acumulan. El servidor tiene 7,1 GiB compartidos con otros servicios y la API un tope de 3 GiB; con cuatro transcripciones a la vez se midió un pico de 1968 MiB.

## Decisión

1. **El adaptador de HOMR ejecuta de una en una.** Un cerrojo de proceso (`threading.Lock` de módulo en `cadenza.omr.adapters.homr`) envuelve la descarga de pesos y `process_image`. Vale para cualquier llamador del adaptador (API, CLI o experimentos), porque el estado compartido es del proceso y no de cada instancia de `HOMREngine`.
2. **La API admite un número fijo de transcripciones en curso.** `CADENZA_TRANSCRIBE_MAX_CONCURRENCY` (por defecto 2, de 1 a 8) fija los huecos (`TranscriptionSlots` en `app.state`: un `threading.BoundedSemaphore` y un grupo de hilos propio, con un hilo por hueco). Con 2, una transcripción calcula y otra espera su turno en el cerrojo de HOMR, sin que se acumulen más. El grupo propio garantiza un hilo a quien tiene hueco y evita competir con el ejecutor por defecto de `asyncio`.
3. **El hueco lo libera el trabajo, no la petición.** Se libera en el callback del futuro del trabajo, que corre una sola vez: al terminar, bien o con error, o al cancelarse si aún no había empezado. Si la petición se cancela con el trabajo en marcha (el cliente se va, el servidor se apaga), el trabajo sigue ocupando su hueco hasta acabar.
4. **El trabajo es dueño de sus recursos.** La transcripción abre su propia sesión de base de datos y su propio directorio temporal, y confirma antes de devolver. Si la petición se cancela, termina y se guarda igualmente, sin usar la sesión de la petición, que ya se habrá cerrado. Con un 2xx, la sesión ya está confirmada (#166). Esto cuadra con el aviso del cliente cuando vence su espera: puede que la sesión se haya creado.
5. **Sin hueco, 503.** Una petición espera hasta 10 s a que quede un hueco; si no lo hay, responde 503 con `Retry-After: 10`, declarada en el contrato, y un `detail` en español. Es corto frente a los 30 s del cliente: mejor un «ocupado» claro que un timeout. El cliente ya trata el 503 como servidor no disponible y pausa su cola.

## Consecuencias

### Positivas
- Una transcripción nunca falla por coincidir con otra.
- La memoria y la CPU de la API quedan acotadas aunque los clientes aborten.
- El 503 es un cambio compatible del contrato v1: se declara en `docs/api/openapi.json` y el cliente ya lo maneja.

### Negativas / Riesgos
- Las transcripciones se atienden de una en una: con varias personas a la vez, cada una espera a las anteriores, y con páginas lentas en CPU pueden recibir 503.
- Una transcripción cuyo cliente ya se fue sigue ocupando su turno hasta terminar y crea su sesión igualmente.
- Apagar la API con una transcripción en marcha espera a que termine: el grupo de hilos no se cierra antes y HOMR no se puede interrumpir.
- La espera de un hueco es por sondeo (cada 0,1 s), sin orden de llegada: bajo carga, una petición nueva puede adelantar a otra que ya esperaba.
- El tope es por proceso. Con varios procesos de uvicorn, cada uno tendría el suyo; el despliegue usa uno.

## Alternativas consideradas

1. **Un `HOMREngine` por hilo.** Descartado: el estado compartido es del módulo de HOMR, no de la instancia.
2. **Varios procesos de trabajo (cola con workers).** Descartado por ahora: es el plano asíncrono que ADR-0016 dejó fuera.
3. **Solo el límite de conexiones de Nginx.** Descartado: se libera al cortarse la conexión, no al acabar el cálculo, y es por visitante, no global.
