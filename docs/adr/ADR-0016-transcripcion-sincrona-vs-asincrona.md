# ADR-0016: Transcripción síncrona de página única frente a colas asíncronas

- **Estado:** En revisión — la mitigación del OCR de título (#106) eliminó los picos en incipits, pero la inferencia de páginas densas mantiene la regla en `ASYNCHRONOUS_REQUIRED` (ver nota del 2026-10-13)
- **Fecha:** 2026-10-08
- **Decisores:** Arquitecto de Software, Equipo de Desarrollo de Cadenza
- **Relacionado:** [ADR-0001](ADR-0001-monolito-modular-hexagonal.md), [ADR-0003](ADR-0003-separacion-planos-computo.md), [ADR-0005](ADR-0005-motor-omr-homr-baseline-oemer.md), [ADR-0014](ADR-0014-ciclo-de-vida-de-la-sesion.md), [ADR-0015](ADR-0015-operacion-y-despliegue-del-backend.md)

---

> **Revisión del 2026-10-13 (Issue #106).** Se identificó y resolvió la causa de la cola
> de latencia y de los `TimeoutError`: la detección de título de HOMR (`detect_title` con RapidOCR
> en un ejecutor mono-hilo con espera de 60 s), un dato que Cadenza no utiliza. Al desactivarla
> en el adaptador (`packages/omr/src/cadenza/omr/adapters/homr.py`):
> - En **incipits de 1 pentagrama**, desapareció la cola: 0 de 36 peticiones alcanzaron los 30 s
>   (máximos de 5,1 s en GPU y 14,1 s en CPU; medianas de 4,1 s y 1,2 s).
> - En **páginas compuestas de 12 pentagramas en GPU** (máx 37,6 s) y de **4 a 12 pentagramas en CPU**
>   (máx 126,8 s), la inferencia musical pura aún sobrepasa los 30 s de *timeout*.
> - La regla predefinida arroja **`ASYNCHRONOUS_REQUIRED`**. Conforme a la directriz del responsable
>   del proyecto, no se toma una decisión definitiva unilateral: se fusiona la mitigación (reduce la
>   latencia), el ADR permanece **«En revisión»** con las cifras nuevas, y el issue #106 queda abierto.

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

## Perfil de la cola de latencia y mitigación (#106)

El 2026-10-13 se midió de forma aislada la función de detección de título (`detect_title(debug, staffs[0])` en `homr/main.py:275`, que invoca `homr/title_detection.py` con RapidOCR en un `ThreadPoolExecutor(max_workers=1)` y espera el resultado hasta 60 s con `title_future.result(60)`).

Sobre 15 imágenes consecutivas del manifiesto (índices 40 a 54) con HOMR en GPU en un proceso nuevo:

| | Con OCR de título | Sin OCR de título |
|---|---|---|
| Suma de las 15 | unos 270 s | 11,9 s |
| Máximo | 47,9 s (47,0 s de OCR) | 4,0 s (primera llamada) |
| Transcripciones lentas (más de 10 s) | 9 de 15 | 0 de 15 |
| Resto de llamadas | 0,4 a 3,1 s | 0,3 a 0,7 s |

En las 9 transcripciones lentas el OCR explicaba entre el 64 % y el 98 % del tiempo. Sin OCR, las transcripciones musicales son idénticas byte a byte a las de la línea base. Cadenza no utiliza el título en el dominio ni en el `ScoreIR`.

### Mitigación adoptada
En el adaptador `packages/omr/src/cadenza/omr/adapters/homr.py`, al importar HOMR (`_import_homr`), se sustituye `homr_main.detect_title` de forma idempotente y para todo el proceso por una función que retorna un `Future` ya resuelto con cadena vacía (`""`). Si `homr.main` carece del atributo `detect_title`, la importación falla explícitamente para evitar que una versión futura de HOMR reintroduzca la cola en silencio.

---

## Evidencia medida

Mediciones reales con `ml/experiments/exp_11_latency_benchmark.py` cronometrando `HOMREngine.transcribe_musicxml`.

- **Motor:** HOMR 0.7.0 sobre onnxruntime-gpu 1.26.0.
- **Equipo:** Intel64 Family 6 Model 183 Stepping 1, GenuineIntel (16 hilos); GPU NVIDIA GeForce RTX 5050 Laptop GPU.
- **Entradas:** 5 incipits de PrIMuS y páginas de 4, 8 y 12 pentagramas compuestas apilando las primeras 4, 8 y 12 imágenes del manifiesto (composición sintética, inferencia real).
- **Protocolo:** 3 repeticiones por imagen y ejecución; cada dispositivo en 3 procesos independientes (acumulando muestras tras `--reset`). La primera llamada de cada proceso se cuenta aparte como arranque en frío.
- **Referencia:** *timeout* de cliente de 30 s.

### Antes (2026-10-12, con OCR de título)

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

- **Arranque en frío antes:**
  - GPU: 39,8 s, 26,5 s, 39,0 s (3 procesos).
  - CPU: 27,2 s, 33,7 s, 4,1 s (3 procesos).

### Después (2026-10-13, sin OCR de título)

| Entrada | Dispositivo | n | Mediana | Media | p95 | Máximo | Peticiones ≥ 30 s |
|---|---|---|---|---|---|---|---|
| Incipit (1 pentagrama) | GPU | 36 | 4,1 | 3,1 | 5,1 | 5,1 | 0 |
| Página de 4 pentagramas | GPU | 9 | 13,7 | 9,9 | 14,0 | 14,1 | 0 |
| Página de 8 pentagramas | GPU | 9 | 24,7 | 17,3 | 25,7 | 25,9 | 0 |
| Página de 12 pentagramas | GPU | 9 | 23,2 | 22,6 | 37,4 | 37,6 | 3 |
| Incipit (1 pentagrama) | CPU | 36 | 1,2 | 3,7 | 13,3 | 14,1 | 0 |
| Página de 4 pentagramas | CPU | 9 | 4,5 | 16,5 | 45,8 | 46,0 | 2 |
| Página de 8 pentagramas | CPU | 9 | 45,4 | 46,0 | 82,6 | 86,0 | 6 |
| Página de 12 pentagramas | CPU | 9 | 11,9 | 43,2 | 126,7 | 126,8 | 4 |

- **Arranque en frío después:**
  - GPU: 12,4 s, 10,3 s, 3,1 s (3 procesos).
  - CPU: 2,0 s, 2,1 s, 2,1 s (3 procesos).

### Lectura de los datos
- En **incipits (1 pentagrama)**, tanto en GPU como en CPU, el 100 % de las peticiones queda cómodamente por debajo de los 30 s (máximos de 5,1 s y 14,1 s).
- En páginas densas (12 pentagramas en GPU con máx 37,6 s; y 4, 8 y 12 pentagramas en CPU con máx 126,8 s), la inferencia supera el umbral de 30 s.
- Regla de decisión prefijada: `ASYNCHRONOUS_REQUIRED` si alguna petición en caliente alcanza el timeout; `SYNCHRONOUS_WITH_WARMUP` si solo lo alcanza el arranque en frío; `SYNCHRONOUS_SUFFICIENT` en otro caso.
- Resultado de la regla: **`ASYNCHRONOUS_REQUIRED`**.

### Límites de esta medición
- **Se cronometra el motor, no la petición HTTP.** Las cifras son de `HOMREngine.transcribe_musicxml`. La petición `POST /transcribe` añade parsing a `ScoreIR`, validación inicial y persistencia en base de datos.
- **El equipo es un portátil en uso, no una máquina aislada.** No fue posible medir en un entorno aislado sin otra carga.
- **Páginas sintéticas.** Las páginas de 4, 8 y 12 pentagramas son composiciones sintéticas de incipits apilados verticalmente, no páginas históricas de corpus completo.

---

## Decisión

**Estado: En revisión (pendiente de decisión del responsable del proyecto).**
La regla de decisión de `exp_11` mantiene el veredicto `ASYNCHRONOUS_REQUIRED` debido al coste computacional intrínseco de procesar páginas de 12 pentagramas.

Bajo la directriz condicionada del proyecto:
1. No se decide unilateralmente el paso a colas asíncronas en este issue.
2. Se fusiona la mitigación del adaptador (#106), que elimina la cola artificial de RapidOCR y garantiza que la transcripción de incipits sea predecible y rápida (≤ 5,1 s en GPU).
3. El contrato v1 se mantiene síncrono (`POST /transcribe`).
4. Para clientes que ingieran páginas densas o ejecuten sobre CPU, se documenta un *timeout* recomendado de 120 s (o superior) en `docs/api/frontend-handoff.md`.
5. El ADR-0016 permanece **En revisión** y el issue #106 queda abierto con los resultados reportados.

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
