# ADR-0016: Transcripción síncrona de página única frente a colas asíncronas

- **Estado:** En revisión — la evidencia medida el 2026-10-12 contradice la decisión (ver nota)
- **Fecha:** 2026-10-08
- **Decisores:** Arquitecto de Software, Equipo de Desarrollo de Cadenza
- **Relacionado:** [ADR-0001](ADR-0001-monolito-modular-hexagonal.md), [ADR-0003](ADR-0003-separacion-planos-computo.md), [ADR-0005](ADR-0005-motor-omr-homr-baseline-oemer.md), [ADR-0014](ADR-0014-ciclo-de-vida-de-la-sesion.md), [ADR-0015](ADR-0015-operacion-y-despliegue-del-backend.md)

---

> **Revisión del 2026-10-12.** La evidencia original de este ADR no eran mediciones,
> sino constantes escritas en `exp_11_latency_benchmark.py` (peor caso de 7,35 s). Se
> sustituyó por mediciones reales con HOMR ([#97](https://github.com/sebdavid3/Cadenza/issues/97)), que **no respaldan la decisión
> tal como estaba redactada**: 18 de 126 peticiones en caliente tardaron 30 s o más.
>
> La decisión definitiva queda pendiente del responsable del proyecto
> ([#106](https://github.com/sebdavid3/Cadenza/issues/106)). Mientras tanto, el contrato v1 no cambia.

## Contexto

El issue #37 (deuda técnica D42) planteó el análisis de si la operación de transcripción inicial (`POST /transcribe`) debía evolucionar hacia un modelo asíncrono desacoplado basado en trabajos en segundo plano (*background jobs* con sondeo de estado mediante identificador de tarea o WebSockets, colas de mensajería como Celery/Redis/RabbitMQ, y estados de sesión intermedios como `PENDING`/`PROCESSING`).

La inquietud inicial radicaba en que el motor OMR principal (`HOMREngine`), al ejecutarse sobre imágenes densas de páginas completas, pudiera sobrepasar los tiempos de expiración (*timeouts*) convencionales de navegadores web y balanceadores de carga / proxies inversos (30 a 60 segundos), degradando la experiencia de usuario o bloqueando peticiones concurrentes en el servidor.

No obstante, la evolución de la arquitectura de Cadenza ya consolidó dos decisiones estructurales clave:
1. **Delegación fuera del bucle de eventos:** La implementación de `apps/api/src/cadenza/api/main.py` utiliza `asyncio.to_thread` (issue #8) para encapsular la inferencia de OMR en el pool de subprocesos de FastAPI, evitando de forma absoluta el bloqueo del bucle de eventos (*event loop*) asíncrono principal.
2. **Delimitación de la frontera del documento:** El cierre formal de la deuda D43 (issue #38) estipuló que una sesión de Cadenza procesa de manera unitaria una sola imagen (incipit de un pentagrama o página completa de hasta dos pentagramas de piano), descartando expresamente la ingesta de documentos PDF multipágina masivos en el plano online interactivo.

Para fundamentar la decisión con rigor cuantitativo frente al jurado de tesis, se diseñó e implementó un experimento de evaluación de rendimiento y latencia empírica (`ml/experiments/exp_11_latency_benchmark.py`).

---

## Evidencia medida (2026-10-12)

Mediciones reales con `ml/experiments/exp_11_latency_benchmark.py` ([#97](https://github.com/sebdavid3/Cadenza/issues/97)), que
cronometra `HOMREngine.transcribe_musicxml`. Sustituyen a la tabla anterior, que eran
constantes escritas en el código.

- **Motor:** HOMR 0.7.0 sobre onnxruntime-gpu 1.26.0.
- **Equipo:** Intel64 Family 6 Model 183 Stepping 1, GenuineIntel (16 hilos); GPU NVIDIA GeForce RTX 5050 Laptop GPU.
- **Entradas:** 5 incipits de PrIMuS y páginas de 4, 8 y 12 pentagramas compuestas apilando las primeras 4, 8 y 12 imágenes del manifiesto. No hay un corpus de página completa descargado: la composición es sintética y la inferencia es real.
- **Protocolo:** 3 repeticiones por imagen y ejecución; cada dispositivo en procesos separados (CPU: 3, GPU: 3 ejecuciones). La primera llamada de cada proceso se cuenta aparte como arranque en frío.
- **Referencia:** *timeout* de cliente de 30 s.

### Latencia en caliente (segundos)

| Entrada | Dispositivo | n | Mediana | Media | p95 | Máximo | Peticiones ≥ 30 s |
|---|---|---|---|---|---|---|---|
| Incipit (1 pentagrama) | GPU | 36 | 1,8 | 7,9 | 34,3 | 36,8 | 4 |
| Página de 4 pentagramas | GPU | 9 | 3,1 | 6,4 | 20,2 | 28,5 | 0 |
| Página de 8 pentagramas | GPU | 9 | 5,4 | 13,3 | 33,7 | 39,3 | 1 |
| Página de 12 pentagramas | GPU | 9 | 13,2 | 31,5 | 71,3 | 71,8 | 4 |
| Incipit (1 pentagrama) | CPU | 36 | 3,2 | 8,3 | 36,7 | 39,2 | 3 |
| Página de 4 pentagramas | CPU | 9 | 7,7 | 16,3 | 54,8 | 85,5 | 1 |
| Página de 8 pentagramas | CPU | 9 | 13,6 | 26,3 | 68,2 | 80,6 | 3 |
| Página de 12 pentagramas | CPU | 9 | 17,6 | 27,1 | 64,8 | 73,7 | 2 |

### Arranque en frío (primera petición del proceso)

- **GPU:** 39,8 s, 26,5 s, 39,0 s (3 procesos).
- **CPU:** 27,2 s, 33,7 s, 4,1 s (3 procesos).

### Lectura de los datos

- Máximo en caliente: 85,5 s. Máximo en frío: 39,8 s.
- Regla de decisión, escrita en el script antes de ejecutar las mediciones: ASYNCHRONOUS_REQUIRED si alguna petición en caliente alcanza el timeout; SYNCHRONOUS_WITH_WARMUP si solo lo alcanza el arranque en frío; SYNCHRONOUS_SUFFICIENT en otro caso.
- Resultado de la regla: **`ASYNCHRONOUS_REQUIRED`**.

### Límites de esta medición

- **Se cronometra el motor, no la petición.** Las cifras son de
  `HOMREngine.transcribe_musicxml`. `POST /transcribe` añade la conversión al modelo
  interno, la validación y la persistencia, y aquí no hay concurrencia: son una cota
  inferior de lo que ve el cliente.
- **El equipo es un portátil en uso, no una máquina aislada.** Los picos llegan en
  rachas contiguas (en una ejecución de CPU, cinco llamadas seguidas de 27 a 39 s) y la
  misma imagen varía entre 1,6 y 36,8 s en GPU. Eso apunta más a contención del equipo
  que al motor, pero no está demostrado.
- **La causa de los picos no está identificada.** HOMR vuelve a crear el modelo de
  segmentación en cada llamada, mientras que el codificador y el decodificador quedan
  cargados en el proceso; esa recarga también la pagan las llamadas rápidas, así que
  por sí sola no explica los picos. Se investiga en [#106](https://github.com/sebdavid3/Cadenza/issues/106).
- **Arranque en frío y primeras llamadas.** En la primera ejecución de GPU, las tres
  llamadas siguientes al arranque en frío tardaron de 30 a 37 s y cuentan como «en
  caliente».
- **Muestras pequeñas en las páginas.** Con n = 9, el p95 es casi el máximo.
- **Páginas sintéticas.** Son composiciones de incipits, no páginas reales.
- **Una imagen falla siempre.** La tercera del manifiesto da «No staffs found»; sus
  intentos se cuentan como fallos y no como latencias.
- **Trazabilidad.** Las mediciones se tomaron con la versión del script de este mismo
  cambio antes de confirmarlo; `results/exp_11_run_info.json` registra el commit
  anterior. La regla de decisión no tiene un registro previo independiente.

---

## Decisión

**Estado tras medir (2026-10-12): en revisión.** La regla de decisión, escrita antes de
ejecutar las mediciones, da `ASYNCHRONOUS_REQUIRED` en ambos dispositivos. Hasta que se cierre
[#106](https://github.com/sebdavid3/Cadenza/issues/106):

1. El contrato v1 se mantiene: `POST /transcribe` sigue siendo síncrono.
2. Los clientes deben usar un *timeout* holgado sobre el máximo observado (85,5 s);
   se recomienda 120 s, y mostrar progreso.
3. Quedan dos salidas, a elegir con la evidencia de #106: mantener el modelo síncrono
   si cargar los modelos una sola vez elimina los picos, o pasar a un modelo asíncrono
   (petición aceptada y consulta de estado), que cambia el contrato de la API.

### Decisión original (2026-10-08)

Se adoptó el **modelo de transcripción síncrona en el plano online** para Cadenza:

1. **Persistencia del endpoint síncrono:** `POST /transcribe` continúa procesando la petición y devolviendo directamente la sesión creada (`SessionResponse`) con su documento de partitura (`ScoreDocumentResponse`) y sus hallazgos iniciales (`findings`).
2. **Concurrencia mediante pool de hilos:** Toda inferencia OMR se invoca a través de `asyncio.to_thread`, garantizando que las peticiones concurrentes de lectura, edición y exportación no sufran inanición en el servidor FastAPI.
3. **Rechazo de colas asíncronas distribuidas:** Se desestima expresamente la incorporación de brokers de mensajería (RabbitMQ, Redis) y gestores de tareas distribuidas (Celery, Dramatiq) en el plano online.
4. **Acotamiento del alcance:** Queda ratificado que documentos de volumen masivo o multipágina pertenecen a pipelines de procesamiento batch offline y no al flujo interactivo del editor.

---

## Consecuencias de la decisión original

> Las consecuencias siguientes se redactaron con la evidencia simulada. Las mediciones
> del 2026-10-12 contradicen las que hablan de respuesta predecible: 18 de 126
> peticiones tardaron 30 s o más, y un cliente con *timeout* de 30 s las habría perdido.

### Positivas
- **Simplicidad arquitectónica radical (YAGNI):** Se evita introducir complejidad accidental (múltiples servicios de infraestructura, gestión de reconexiones en brokers, persistencia de estados efímeros de tareas y sincronización distribuida).
- **Experiencia de usuario lineal y predecible:** El frontend no requiere orquestar máquinas de estados complejas de sondeo periódico (*polling*) ni reconexiones WebSockets durante la carga de un archivo; la transición de carga a visualización en el lienzo es atómica y determinista.
- **Estabilidad del contrato de API y tipos:** Los contratos OpenAPI 3.0 v1.0.0 congelados (`docs/api/openapi.json`) y las interfaces tipadas en TypeScript (`apps/web/src/types.ts`) se preservan sin romper compatibilidad.
- **Cero latencia de encolado:** Al no existir overhead de serialización hacia colas externas, el usuario percibe la respuesta en el menor tiempo físico posible.

### Negativas / Mitigaciones
- **Concurrencia alta en servidores sin GPU:** Si una multitud de usuarios remite imágenes simultáneamente a una única instancia en CPU, el pool de subprocesos saturará los núcleos disponibles y las latencias podrían degradarse.
  - *Mitigación:* Para el alcance de la investigación y entornos de laboratorio de transcripción asistida, el tráfico concurrente es moderado. Si en un despliegue futuro en producción se requiere atender alta concurrencia, el patrón estándar es el escalado horizontal de réplicas sin estado del contenedor de la API (mediante balanceadores de carga como Traefik/Nginx) o la asignación de GPU NVIDIA con `Dockerfile.ml-cuda` y Docker Compose (ADR-0015).
