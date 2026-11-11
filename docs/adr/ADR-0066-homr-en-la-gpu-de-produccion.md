# ADR-0066: HOMR en la GPU de producción

- **Estado:** Aceptado
- **Fecha:** 2026-11-10
- **Decisores:** Responsable del proyecto (pidió que producción use la GPU y no la CPU, 2026-11-10) y Equipo de Desarrollo
- **Enmienda:** [ADR-0023](ADR-0023-despliegue-publico-con-tailscale-funnel.md) §6 («API en CPU»)
- **Relacionado:** [ADR-0018](ADR-0018-homr-como-unico-motor-omr.md), [ADR-0024](ADR-0024-transcripciones-simultaneas.md), [ADR-0029](ADR-0029-api-con-usuario-sin-privilegios.md), [ADR-0064](ADR-0064-transcripcion-en-segundo-plano-con-su-avance.md), [#268](https://github.com/sebdavid3/Cadenza/issues/268), [#269](https://github.com/sebdavid3/Cadenza/issues/269)

---

## Contexto

- ADR-0023 §6 dejó la API en CPU: la imagen instalaba `onnxruntime` de CPU y `docker-compose.prod.yml` fijaba `CADENZA_OMR_USE_GPU: "false"`. Una variante con GPU sería un issue aparte, #268, que el responsable recortó el 2026-10-27 (#272) y retomó el 2026-11-10.
- El servidor `r2d2` tiene una RTX 2060 Max-Q de 6 GB (controlador 595, CUDA 13.2), el runtime `nvidia` en Docker y la comparte con Immich (`immich_machine_learning`, imagen `-cuda`). Tiene 7,1 GiB de RAM.
- Con CUDA, HOMR usa otros pesos: los fp16 de la segmentación y del transformador, en lugar de los fp32 de la CPU. `homr --init` en la imagen solo descargaba los de la CPU, y el usuario de la API (ADR-0029) no puede escribir en el entorno virtual para descargar los otros.
- `onnxruntime-gpu` declara `CUDAExecutionProvider` aunque no haya GPU. Con eso bastaba para que `HOMREngine` creyera tenerla: sin GPU, HOMR cae en sus modelos fp16 sobre la CPU, más lentos que los fp32, y `/health` y la procedencia de cada sesión dirían `cuda`.
- `exp_11` midió en el portátil 11,6 s en CPU frente a 6,8 s en GPU para una página de 12 pentagramas. Las páginas de voz y piano se leen dos veces (ADR-0060), y HOMR calcula de una en una (ADR-0024).

## Decisión

1. **Dos variantes de la imagen, con un argumento de construcción.** `CADENZA_OMR_DEVICE` es `cpu` por defecto: la CI, el compose de desarrollo y cualquier `docker build` sin argumentos dan la imagen de siempre. Con `gpu`, una etapa `deps-gpu` sobre las dependencias cambia `onnxruntime` por `onnxruntime-gpu[cuda,cudnn]==1.26.0` (CUDA 12 y cuDNN 9 de los wheels de NVIDIA, la misma versión que el README para el desarrollo, fuera del lockfile) y descarga los pesos fp16 con la misma llamada que el adaptador (`download_weights`). Los fp32 siguen en la imagen. La etapa final copia el entorno de `deps-${CADENZA_OMR_DEVICE}`, y la construcción falla si ONNX Runtime no es el que se pidió.
2. **El compose de producción la construye con GPU y reserva una.** `build.args.CADENZA_OMR_DEVICE: gpu`, `deploy.resources.reservations.devices` con el controlador `nvidia` y `count: ${CADENZA_API_GPUS:-1}`, y `CADENZA_OMR_USE_GPU: ${CADENZA_OMR_USE_GPU:-true}`.
3. **La GPU ha de estar de verdad.** Con CUDA, el adaptador pregunta además al controlador (`cuInit` y `cuDeviceGetCount` de `libcuda`, una vez por proceso) si ve alguna GPU. Sin ella (sin `libcuda`, que el runtime de NVIDIA no monta en un contenedor sin GPU, o con `cuInit` sin dispositivo), HOMR lee en la CPU con los pesos fp32, `/health` y la procedencia dicen `cpu` y el registro lo avisa una vez.
4. **Volver a la CPU es una variable del `.env`.** Con `CADENZA_API_GPUS=0` el contenedor arranca sin GPU. Es la salida si el controlador falla, porque con la reserva Docker no arrancaría la API: con 0, Docker pide la GPU `void`, y el runtime de NVIDIA, según su documentación, hace entonces lo mismo que `runc` (comprobado solo con el controlador sano). Con `CADENZA_OMR_USE_GPU=false`, la tiene pero no la usa. Las dos se aplican recreando la API (`operacion_backend.md` §2.2, «HOMR en la GPU»).

## Alternativas descartadas

- **Una imagen base de CUDA de NVIDIA** (`nvidia/cuda:12.x-cudnn-runtime`). Es otra base distinta de la de CPU, con otro Python, y más grande; los wheels de NVIDIA que ya usa el desarrollo bastan.
- **`onnxruntime-gpu` en el lockfile.** Los dos paquetes instalan el mismo módulo `onnxruntime` y no pueden convivir en un entorno; un extra que los alternara cambiaría el lockfile para la CI y el desarrollo, que no tienen GPU.
- **Solo la imagen de GPU.** La CI no tiene GPU, y la imagen de CPU no carga con los ~2,5 GB de CUDA y cuDNN.
- **Fiarse de los proveedores de ONNX Runtime.** Con `onnxruntime-gpu` dicen CUDA haya GPU o no.

## Consecuencias

### Positivas
- Las transcripciones tardan menos, sobre todo las páginas completas (ver «Medición»), y la cola de ADR-0024 y ADR-0064 avanza antes.
- Volver a la CPU no exige código (`CADENZA_API_GPUS=0`), y entonces la API transcribe en ella y lo dice.
- En las dos imágenes medidas, HOMR da el mismo MusicXML en la GPU que en la CPU (ver «Medición»).

### Negativas
- La imagen de producción crece con CUDA y cuDNN, y su primera construcción tarda más. La de CPU no cambia.
- **La API depende de la pila de NVIDIA para arrancar.** Si Docker no puede darle la GPU (el controlador roto tras una actualización sin reiniciar, el runtime desinstalado), el contenedor no arranca hasta poner `CADENZA_API_GPUS=0`.
- La GPU se comparte con Immich. Si se queda sin memoria de vídeo, la transcripción en curso falla: ONNX Runtime lanza la excepción al ejecutar, o crea la sesión en la CPU sin avisar y el codificador de HOMR, que enlaza su salida a `cuda`, falla igual. La siguiente lo vuelve a intentar; si se repite, `CADENZA_OMR_USE_GPU=false` o `CADENZA_API_GPUS=0`.
- `onnxruntime-gpu` y sus wheels de NVIDIA no están en el lockfile: se fija su versión, no la de cada wheel de NVIDIA.
- Las latencias medidas en CPU (#269, ADR-0064) dejan de ser las de producción.
- La equivalencia del MusicXML está comprobada en dos imágenes, no en el banco del estudio (ADR-0057, medido en CPU) ni en PrIMuS (D20: el OMR-NED en GPU, 0,2341, no se comparó sin caché con el de CPU). Antes del piloto conviene repetir el banco en la GPU, o estudiar con `CADENZA_API_GPUS=0`.

## Medición

En `r2d2` el 2026-11-10, con la imagen de producción de entonces (CPU) y la de GPU construida con este `Dockerfile` (salvo el `--no-cache` de uv, que no cambia el entorno virtual). Cada configuración corre en un contenedor desechable sin red, con el tope de memoria (3 GiB) y las restricciones de la API (`cap_drop: ALL`, `no-new-privileges`) y el adaptador de este cambio. Con la API de producción en marcha, sin transcripciones. Por configuración, cuatro lecturas seguidas de cada imagen: un incipit de PrIMuS (`apps/api/tests/fixtures/incipit.png`) y una página real de voz y piano (`ellens-gesang-1-p2.png`, del conjunto de referencia de ADR-0056, que HOMR lee dos veces, ADR-0060). La primera lectura del proceso carga los modelos.

| Configuración | Dispositivo | Incipit (1.ª / siguientes) | Página de voz y piano | RAM máxima del proceso | Memoria de vídeo |
|---|---|---|---|---|---|
| Imagen de CPU (producción hasta ahora) | `cpu` | 4,39 s / 2,45–2,62 s | 62,23–62,88 s | 1 520 MiB | — |
| Imagen de GPU con la GPU | `cuda` | 4,53 s / 0,91–0,98 s | 24,57–24,82 s | 1 669 MiB | 534 MiB estable, 1 576 MiB de pico |
| Imagen de GPU sin GPU (`--gpus 0`) | `cpu` | 3,37 s / 2,38–2,62 s | 60,94–61,49 s | 1 548 MiB | — |

- En la GPU, la página tarda 2,5 veces menos y el incipit 2,7 veces menos, con las mismas notas (15 y 390). La primera lectura no mejora: crear las sesiones de CUDA cuesta lo que se ahorra.
- Sin GPU, la imagen de GPU dice `cpu` (el controlador no ve ninguna) y tarda lo mismo que la de CPU: lee con los pesos fp32, no con los fp16 en la CPU.
- **El mismo MusicXML.** Una lectura más de cada imagen con la imagen de CPU y con la de GPU (en la GPU) da un MusicXML idéntico byte a byte en las dos (`sha256` `45ae8e1d…` el incipit y `a6e1fd2b…` la página).
- En la GPU, ONNX Runtime avisa de que algunas convoluciones del codificador corren en el modo de reserva de cuDNN («running in Fallback mode», 18 avisos) y de que algunos nodos quedan en la CPU; ningún «EP Error» ni ninguna sesión creada sin GPU.
- Immich no tenía nada cargado en la GPU durante la medida (4 MiB en uso). Con los 6 GB de la tarjeta, el pico de HOMR deja unos 4,5 GB para los modelos de Immich.
