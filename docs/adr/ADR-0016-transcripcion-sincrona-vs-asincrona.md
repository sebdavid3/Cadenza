# ADR-0016: Transcripción síncrona de página única frente a colas asíncronas

- **Estado:** Aceptado
- **Fecha:** 2026-10-08 (ratificado y cerrado el 2026-10-13 tras #106)
- **Decisores:** Arquitecto de Software, Equipo de Desarrollo de Cadenza
- **Relacionado:** [ADR-0001](ADR-0001-monolito-modular-hexagonal.md), [ADR-0003](ADR-0003-separacion-planos-computo.md), [ADR-0005](ADR-0005-motor-omr-homr-baseline-oemer.md), [ADR-0014](ADR-0014-ciclo-de-vida-de-la-sesion.md), [ADR-0015](ADR-0015-operacion-y-despliegue-del-backend.md)

---

> **Revisión del 2026-10-13 (Cierre definitivo de #106).** Se completó la resolución de los
> picos de latencia en dos etapas:
> 
> 1. **Eliminación del OCR de título (#109):** La detección de título de HOMR (`detect_title` con RapidOCR)
>    causaba la cola inicial y los `TimeoutError`. Al desactivarla en el adaptador, desaparecieron los picos
>    en incipits.
> 2. **Identificación y corrección de la limitación de energía de Windows 11 (EcoQoS / Power Throttling):**
>    Las cifras «después» publicadas en el PR #109 reflejaban una contaminación inadvertida: el proceso fue
>    confinado por Windows 11 a los 4 núcleos de eficiencia (E-cores) del procesador Intel Core i5-13450HX.
>    - *Evidencia 1 (Régimen bimodal):* Al repetir `exp_11`, la CPU alternaba entre régimen normal (incipit 1,3 s;
>      página de 12: 11,4 s) y régimen lento (incipit 10–14 s; página de 12: hasta 127 s), consumiendo el benchmark
>      solo el 22–24 % de CPU (unos 3,6 de 16 hilos).
>    - *Evidencia 2 (Prueba controlada y control independiente):* Con `SetProcessInformation(ProcessPowerThrottling)`,
>      forzar la limitación reproduce el comportamiento lento observado en el PR #109 (el control arrojó 78 s en
>      página de 8 y 119 s en página de 12 en CPU con ~3,6 hilos, frente a las muestras del PR #109 de 86 s y 127 s;
>      en claro contraste con 7,8 s y 11,6 s con limitación desactivada y ~12,7 hilos).
>    - *Mitigación:* Se implementó la renuncia explícita del proceso a la limitación de energía en Windows
>      (`cadenza.omr.power`, ADR-0015), activada al arrancar la API y en el arnés experimental de `exp_11`.
> 
> Con la limitación desactivada, 0 de 126 peticiones alcanzaron los 30 s (máximo absoluto de 7,6 s en GPU y
> 12,0 s en CPU). La regla arroja **`SYNCHRONOUS_SUFFICIENT`** en ambos dispositivos. Se mantiene la transcripción
> síncrona en la API v1 sin modificaciones de contrato.

## Contexto

El issue #37 (deuda técnica D42) planteó el análisis de si la operación de transcripción inicial (`POST /transcribe`) debía evolucionar hacia un modelo asíncrono desacoplado basado en trabajos en segundo plano (*background jobs* con sondeo de estado mediante identificador de tarea o WebSockets, colas de mensajería como Celery/Redis/RabbitMQ, y estados de sesión intermedios como `PENDING`/`PROCESSING`).

La inquietud inicial radicaba en que el motor OMR principal (`HOMREngine`), al ejecutarse sobre imágenes densas de páginas completas, pudiera sobrepasar los tiempos de expiración (*timeouts*) convencionales de navegadores web y balanceadores de carga / proxies inversos (30 a 60 segundos), degradando la experiencia de usuario o bloqueando peticiones concurrentes en el servidor.

No obstante, la evolución de la arquitectura de Cadenza ya consolidó dos decisiones estructurales clave:
1. **Delegación fuera del bucle de eventos:** La implementación de `apps/api/src/cadenza/api/main.py` utiliza `asyncio.to_thread` (issue #8) para encapsular la inferencia de OMR en el pool de subprocesos de FastAPI, evitando de forma absoluta el bloqueo del bucle de eventos (*event loop*) asíncrono principal.
2. **Delimitación de la frontera del documento:** El cierre formal de la deuda D43 (issue #38) estipuló que una sesión de Cadenza procesa de manera unitaria una sola imagen (incipit de un pentagrama o página completa de hasta dos pentagramas de piano), descartando expresamente la ingesta de documentos PDF multipágina masivos en el plano online interactivo.

Para fundamentar la decisión con rigor cuantitativo frente al jurado de tesis, se diseñó e implementó un experimento de evaluación de rendimiento y latencia empírica (`ml/experiments/exp_11_latency_benchmark.py`).

---

## Perfil de la cola de latencia y mitigaciones (#106)

### 1. Eliminación del OCR de título
El 2026-10-13 se midió de forma aislada la función de detección de título (`detect_title(debug, staffs[0])` en `homr/main.py:275`, que invoca `homr/title_detection.py` con RapidOCR en un `ThreadPoolExecutor(max_workers=1)` y espera el resultado hasta 60 s con `title_future.result(60)`). Sobre 15 imágenes consecutivas del manifiesto con HOMR en GPU, el OCR explicaba entre el 64 % y el 98 % del tiempo en las transcripciones lentas. Cadenza no utiliza el título en el dominio ni en el `ScoreIR`. En el adaptador `packages/omr/src/cadenza/omr/adapters/homr.py` se sustituyó `homr_main.detect_title` de forma idempotente por un `Future` resuelto con cadena vacía.

### 2. Desactivación de Power Throttling en Windows 11 (EcoQoS)
En procesadores híbridos Intel de 12.ª generación o posterior, Windows 11 confina de forma predeterminada los procesos en segundo plano a los núcleos de eficiencia (E-cores), reduciendo el uso de hilos a ~3,6 y aumentando la latencia hasta un orden de magnitud. Se incorporó `set_power_throttling` en `cadenza.omr.power` (reexportado en `cadenza.api`) para renunciar explícitamente a esta limitación vía `kernel32.SetProcessInformation(ProcessPowerThrottling)`, permitiendo que HOMR utilice el conjunto completo de núcleos de rendimiento (P-cores, ~12,7 a 13,2 hilos de CPU efectivos).

---

## Evidencia medida

Mediciones reales con `ml/experiments/exp_11_latency_benchmark.py` cronometrando `HOMREngine.transcribe_musicxml`.

- **Motor:** HOMR 0.7.0 sobre onnxruntime-gpu 1.26.0.
- **Equipo:** Intel64 Family 6 Model 183 Stepping 1, GenuineIntel (16 hilos); GPU NVIDIA GeForce RTX 5050 Laptop GPU.
- **Entradas:** 5 incipits de PrIMuS y páginas de 4, 8 y 12 pentagramas compuestas apilando las primeras 4, 8 y 12 imágenes del manifiesto (composición sintética, inferencia real).
- **Protocolo:** 3 repeticiones por imagen y ejecución; cada dispositivo en 3 procesos independientes (acumulando muestras tras `--reset`). La primera llamada de cada proceso se cuenta aparte como arranque en frío. Modo de energía: `power_throttling=disabled`.
- **Referencia:** *timeout* de cliente de 30 s.

### Antes (2026-10-12, con OCR de título y limitación no controlada)

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

### Después (2026-10-13, sin OCR de título y con limitación de energía desactivada)

| Entrada | Dispositivo | n | Mediana | Media | p95 | Máximo | Peticiones ≥ 30 s |
|---|---|---|---|---|---|---|---|
| Incipit (1 pentagrama) | GPU | 36 | 0,7 | 0,7 | 0,8 | 0,9 | 0 |
| Página de 4 pentagramas | GPU | 9 | 2,3 | 2,4 | 2,7 | 2,7 | 0 |
| Página de 8 pentagramas | GPU | 9 | 4,3 | 4,5 | 5,1 | 5,2 | 0 |
| Página de 12 pentagramas | GPU | 9 | 6,4 | 6,8 | 7,5 | 7,6 | 0 |
| Incipit (1 pentagrama) | CPU | 36 | 1,2 | 1,2 | 1,4 | 1,5 | 0 |
| Página de 4 pentagramas | CPU | 9 | 4,4 | 4,3 | 4,6 | 4,6 | 0 |
| Página de 8 pentagramas | CPU | 9 | 7,8 | 7,8 | 8,1 | 8,2 | 0 |
| Página de 12 pentagramas | CPU | 9 | 11,6 | 11,6 | 11,9 | 12,0 | 0 |

- **Arranque en frío después:**
  - GPU: 4,2 s, 3,6 s, 3,5 s (3 procesos).
  - CPU: 2,0 s, 2,0 s, 2,0 s (3 procesos).

### Lectura de los datos
- En **incipits (1 pentagrama)**, tanto en GPU (mediana 0,7 s, máx 0,9 s) como en CPU (mediana 1,2 s, máx 1,5 s), el tiempo de respuesta es inmediato y totalmente predecible.
- En **páginas densas compuestas (hasta 12 pentagramas)**, la inferencia en GPU requiere como máximo 7,6 s (mediana 6,4 s) y en CPU un máximo de 12,0 s (mediana 11,6 s).
- No existe un «coste intrínseco» que exceda los 30 s en páginas densas: los picos anteriores de hasta 126,8 s se debían exclusivamente al confinamiento del proceso a núcleos de eficiencia bajo EcoQoS (unos 3,6 hilos de CPU frente a los 12,7–13,2 hilos en régimen sin limitación).
- Regla de decisión prefijada: `ASYNCHRONOUS_REQUIRED` si alguna petición en caliente alcanza el timeout; `SYNCHRONOUS_WITH_WARMUP` si solo lo alcanza el arranque en frío; `SYNCHRONOUS_SUFFICIENT` en otro caso.
- Resultado de la regla: **`SYNCHRONOUS_SUFFICIENT`** en ambos dispositivos con un margen mínimo del 59,9 % frente al *timeout* de 30 s.

### Límites de esta medición
- **Se cronometra el motor, no la petición HTTP.** Las cifras de las tablas corresponden a `HOMREngine.transcribe_musicxml`. La petición `POST /transcribe` añade parsing a `ScoreIR`, validación inicial y persistencia en base de datos. Medido contra la API en vivo en GPU: 0,69–0,76 s por incipit (motor: mediana 0,70 s) y 4,16–4,48 s para la página de 8 pentagramas (motor: 4,42 s), arrojando un sobrecoste habitualmente contenido entre 10 y 60 ms en régimen caliente.
- **Renuncia a Power Throttling requerida en Windows 11.** Se mide con la limitación de energía desactivada para el proceso. En Windows 11, sin esta renuncia explícita (`SetProcessInformation`), el backend en segundo plano puede ser confinado por el sistema operativo a los núcleos de eficiencia, cayendo al régimen lento (~78 s en página de 8 pentagramas, ~119 s en 12 pentagramas en CPU).
- **El equipo es un portátil en uso.** No fue necesario aislar térmicamente la máquina tras desactivar la limitación de energía.
- **Páginas sintéticas.** Las páginas de 4, 8 y 12 pentagramas son composiciones sintéticas de incipits apilados verticalmente, no páginas históricas de corpus completo.

---

## Decisión

**Estado: Aceptado.**

Se ratifica el **modelo de transcripción síncrona en el plano online** para Cadenza:

1. **Persistencia del endpoint síncrono:** `POST /transcribe` continúa procesando la imagen y devolviendo directamente la sesión creada (`SessionResponse`) con su documento de partitura (`ScoreDocumentResponse`) y sus hallazgos iniciales (`findings`).
2. **Concurrencia mediante pool de hilos:** Toda inferencia OMR se invoca a través de `asyncio.to_thread`, garantizando que las peticiones concurrentes de lectura, edición y exportación no sufran inanición en el servidor FastAPI.
3. **Rechazo de colas asíncronas distribuidas:** Se desestima la incorporación de brokers de mensajería (RabbitMQ, Redis) y gestores de tareas distribuidas (Celery, Dramatiq) en el plano online.
4. **Acotamiento del alcance:** Queda ratificado que documentos de volumen masivo o multipágina pertenecen a pipelines de procesamiento batch offline y no al flujo interactivo del editor.
5. **Configuración de energía en Windows:** La API solicita desactivar la limitación de energía del proceso al arrancar (`CADENZA_DISABLE_POWER_THROTTLING=true`, ADR-0015). Esta renuncia solo existe en Windows (vía `SetProcessInformation`) y puede fallar o no ser concedida por el sistema operativo, en cuyo caso el servicio continúa su ejecución emitiendo una advertencia en el registro.

---

## Consecuencias de la decisión

### Positivas
- **Simplicidad arquitectónica radical (YAGNI):** Se evita introducir complejidad accidental (múltiples servicios de infraestructura, gestión de reconexiones en brokers, persistencia de estados efímeros de tareas y sincronización distribuida).
- **Experiencia de usuario lineal y predecible:** El frontend no requiere orquestar máquinas de estados complejas de sondeo periódico (*polling*) ni reconexiones WebSockets durante la carga de un archivo; la transición de carga a visualización en el lienzo es atómica y determinista (menos de 1 s en GPU y ~1,2 s en CPU para incipits).
- **Estabilidad del contrato de API y tipos:** Los contratos OpenAPI 3.1.0 v1.0.0 congelados (`docs/api/openapi.json`) y las interfaces tipadas en TypeScript (`apps/web/src/types.ts`) se preservan sin romper compatibilidad.
- **Cero latencia de encolado:** Al no existir overhead de serialización hacia colas externas, el usuario percibe la respuesta en el menor tiempo físico posible.

### Negativas / Mitigaciones
- **Concurrencia alta en servidores sin GPU:** Si una multitud de usuarios remite imágenes simultáneamente a una única instancia en CPU, el pool de subprocesos saturará los núcleos disponibles y las latencias podrían degradarse.
  - *Mitigación:* Para el alcance de la investigación y entornos de laboratorio de transcripción asistida, el tráfico concurrente es moderado. Si en un despliegue futuro en producción se requiere atender alta concurrencia, el patrón estándar es el escalado horizontal de réplicas sin estado del contenedor de la API (mediante balanceadores de carga como Traefik/Nginx) o la asignación de GPU NVIDIA con `Dockerfile.ml-cuda` y Docker Compose (ADR-0015).
