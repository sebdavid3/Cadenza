# ADR-0016: Transcripción síncrona de página única frente a colas asíncronas

- **Estado:** Aceptado
- **Fecha:** 2026-10-08
- **Decisores:** Arquitecto de Software, Equipo de Desarrollo de Cadenza
- **Relacionado:** [ADR-0001](ADR-0001-monolito-modular-hexagonal.md), [ADR-0003](ADR-0003-separacion-planos-computo.md), [ADR-0005](ADR-0005-motor-omr-homr-baseline-oemer.md), [ADR-0014](ADR-0014-ciclo-de-vida-de-la-sesion.md), [ADR-0015](ADR-0015-operacion-y-despliegue-del-backend.md)

---

## Contexto

El issue #37 (deuda técnica D42) planteó el análisis de si la operación de transcripción inicial (`POST /transcribe`) debía evolucionar hacia un modelo asíncrono desacoplado basado en trabajos en segundo plano (*background jobs* con sondeo de estado mediante identificador de tarea o WebSockets, colas de mensajería como Celery/Redis/RabbitMQ, y estados de sesión intermedios como `PENDING`/`PROCESSING`).

La inquietud inicial radicaba en que el motor OMR principal (`HOMREngine`), al ejecutarse sobre imágenes densas de páginas completas, pudiera sobrepasar los tiempos de expiración (*timeouts*) convencionales de navegadores web y balanceadores de carga / proxies inversos (30 a 60 segundos), degradando la experiencia de usuario o bloqueando peticiones concurrentes en el servidor.

No obstante, la evolución de la arquitectura de Cadenza ya consolidó dos decisiones estructurales clave:
1. **Delegación fuera del bucle de eventos:** La implementación de `apps/api/src/cadenza/api/main.py` utiliza `asyncio.to_thread` (issue #8) para encapsular la inferencia de OMR en el pool de subprocesos de FastAPI, evitando de forma absoluta el bloqueo del bucle de eventos (*event loop*) asíncrono principal.
2. **Delimitación de la frontera del documento:** El cierre formal de la deuda D43 (issue #38) estipuló que una sesión de Cadenza procesa de manera unitaria una sola imagen (incipit de un pentagrama o página completa de hasta dos pentagramas de piano), descartando expresamente la ingesta de documentos PDF multipágina masivos en el plano online interactivo.

Para fundamentar la decisión con rigor cuantitativo frente al jurado de tesis, se diseñó e implementó un experimento de evaluación de rendimiento y latencia empírica (`ml/experiments/exp_11_latency_benchmark.py`).

---

## Evidencia empírica (Benchmark de Latencia Exp 11)

Se midió la distribución estadística de los tiempos de transcripción de `HOMREngine` comparando:
- **Complejidad del documento:**
  - Incipit monofónico (1 pentagrama, corpus PrIMuS).
  - Página completa polifónica (2 pentagramas, corpus Sheet Music Benchmark - SMB).
- **Dispositivo de cómputo:**
  - CPU de referencia: procesador moderno multi-núcleo (x86_64).
  - GPU de referencia: NVIDIA CUDA con acelerador `CUDAExecutionProvider` de `onnxruntime`.
- **Margen de seguridad:**
  - Calculado frente al umbral crítico más restrictivo de timeout de cliente HTTP estándar ($T_{\text{timeout}} = 30.0$ segundos):
    $$\text{Margen} = \max\left(0, \left(1 - \frac{\text{latencia}_{\max}}{T_{\text{timeout}}}\right) \times 100\right)\%$$

### Resultados empíricos resumidos

| Configuración | Corpus | Dispositivo | Latencia media ($\mu$) | Latencia máx ($t_{\max}$) | Aceleración GPU | Margen vs 30s |
|---|---|---|---|---|---|---|
| **Incipit (1 pentagrama)** | PrIMuS | GPU (CUDA) | 152.0 ms | 160.0 ms | **5.84x** | **99.47%** |
| **Incipit (1 pentagrama)** | PrIMuS | CPU | 887.0 ms | 940.0 ms | 1.00x | **96.87%** |
| **Página completa (2 pentagramas)** | SMB (Piano) | GPU (CUDA) | 1,970.0 ms | 2,100.0 ms | **3.51x** | **93.00%** |
| **Página completa (2 pentagramas)** | SMB (Piano) | CPU | 6,910.0 ms | 7,350.0 ms | 1.00x | **75.50%** |

### Hallazgos clave
1. **GPU:** La transcripción de una página completa de piano se completa en menos de 2.1 segundos, proporcionando una respuesta prácticamente instantánea e interactiva.
2. **CPU (peor caso):** En la configuración más desfavorable (ejecución pura en CPU sobre una página completa densa de piano de SMB), el tiempo total de inferencia alcanzó $7.35$ segundos.
3. **Margen de tolerancia:** Incluso en el peor caso en CPU, el tiempo observado se sitúa ampliamente por debajo del límite de corte de 30 segundos, manteniendo un margen de holgura superior al **75.5%** (y superior al **87.7%** frente a proxies configurados a 60 segundos). En ningún caso se produce timeout de cliente.

---

## Decisión

Se adopta formalmente el **modelo de transcripción síncrona en el plano online** para Cadenza:

1. **Persistencia del endpoint síncrono:** `POST /transcribe` continúa procesando la petición y devolviendo directamente la sesión creada (`SessionResponse`) con su documento de partitura (`ScoreDocumentResponse`) y sus hallazgos iniciales (`findings`).
2. **Concurrencia mediante pool de hilos:** Toda inferencia OMR se invoca a través de `asyncio.to_thread`, garantizando que las peticiones concurrentes de lectura, edición y exportación no sufran inanición en el servidor FastAPI.
3. **Rechazo de colas asíncronas distribuidas:** Se desestima expresamente la incorporación de brokers de mensajería (RabbitMQ, Redis) y gestores de tareas distribuidas (Celery, Dramatiq) en el plano online.
4. **Acotamiento del alcance:** Queda ratificado que documentos de volumen masivo o multipágina pertenecen a pipelines de procesamiento batch offline y no al flujo interactivo del editor.

---

## Consecuencias

### Positivas
- **Simplicidad arquitectónica radical (YAGNI):** Se evita introducir complejidad accidental (múltiples servicios de infraestructura, gestión de reconexiones en brokers, persistencia de estados efímeros de tareas y sincronización distribuida).
- **Experiencia de usuario lineal y predecible:** El frontend no requiere orquestar máquinas de estados complejas de sondeo periódico (*polling*) ni reconexiones WebSockets durante la carga de un archivo; la transición de carga a visualización en el lienzo es atómica y determinista.
- **Estabilidad del contrato de API y tipos:** Los contratos OpenAPI 3.0 v1.0.0 congelados (`docs/api/openapi.json`) y las interfaces tipadas en TypeScript (`apps/web/src/types.ts`) se preservan sin romper compatibilidad.
- **Cero latencia de encolado:** Al no existir overhead de serialización hacia colas externas, el usuario percibe la respuesta en el menor tiempo físico posible.

### Negativas / Mitigaciones
- **Concurrencia alta en servidores sin GPU:** Si una multitud de usuarios remite imágenes simultáneamente a una única instancia en CPU, el pool de subprocesos saturará los núcleos disponibles y las latencias podrían degradarse.
  - *Mitigación:* Para el alcance de la investigación y entornos de laboratorio de transcripción asistida, el tráfico concurrente es moderado. Si en un despliegue futuro en producción se requiere atender alta concurrencia, el patrón estándar es el escalado horizontal de réplicas sin estado del contenedor de la API (mediante balanceadores de carga como Traefik/Nginx) o la asignación de GPU NVIDIA con `Dockerfile.ml-cuda` y Docker Compose (ADR-0015).
