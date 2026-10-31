# Architecture Decision Records (ADR) — Cadenza

Este directorio registra, de forma **inmutable y fechada**, las decisiones
arquitectónicas significativas del sistema Cadenza. Cada ADR documenta el
contexto, la decisión, sus consecuencias y las alternativas descartadas, de modo
que el capítulo de Diseño e Implementación de la tesis pueda justificar cada
elección técnica frente al jurado.

El documento maestro que integra y da coherencia a todas estas decisiones es
[`../ARCHITECTURE.md`](../ARCHITECTURE.md).

---

## Convención

- **Formato de archivo:** `ADR-NNNN-titulo-en-kebab-case.md` (numeración de
  cuatro dígitos, sin reutilizar números).
- **Plantilla mínima:** Estado, Fecha, Contexto, Decisión, Consecuencias
  (positivas / riesgos) y Alternativas consideradas.
- **Estados:** `Propuesto`, `Aceptado`, `Rechazado`, `Reemplazado por ADR-NNNN`.
- **Inmutabilidad:** una decisión aceptada no se edita; si cambia, se crea un
  nuevo ADR que la reemplaza y se marca el anterior como `Reemplazado`.

---

## Índice de decisiones

| ID | Título | Estado | Módulo(s) afectado(s) |
|---|---|---|---|
| [ADR-0001](ADR-0001-monolito-modular-hexagonal.md) | Monolito modular hexagonal (Puertos y Adaptadores) | Aceptado | Transversal |
| [ADR-0002](ADR-0002-score-document-anchor-index.md) | `ScoreDocument` con `AnchorIndex` como fuente de verdad | Aceptado | Transversal |
| [ADR-0003](ADR-0003-separacion-planos-computo.md) | Separación estricta de planos de cómputo Online / Offline | Aceptado | M1, M4 |
| [ADR-0004](ADR-0004-persistencia-postgresql-jsonb.md) | Persistencia con PostgreSQL + JSONB y Storage de artefactos | Aceptado | M2, M3, M4 |
| [ADR-0005](ADR-0005-motor-omr-homr-baseline-oemer.md) | HOMR/ONNX como motor OMR base, oemer como línea base | Aceptado; punto 3 reemplazado y punto 4 precisado por ADR-0018 | M1 |
| [ADR-0006](ADR-0006-render-editor-osmd-verovio-zustand.md) | Renderizado reactivo (OSMD/Verovio) y estado editorial (Zustand) | Aceptado | M3 |
| [ADR-0007](ADR-0007-edit-events-inmutables.md) | Correcciones HITL como eventos inmutables sobre anclas | Aceptado | M3, M4 |
| [ADR-0008](ADR-0008-active-learning-model-registry.md) | Estrategia de Active Learning y Model Registry | Aceptado | M4 |
| [ADR-0009](ADR-0009-capa-de-aplicacion.md) | Capa de aplicación con casos de uso | Aceptado | Transversal |
| [ADR-0010](ADR-0010-score-ir-atributos-y-exportacion.md) | Atributos de compás en el `ScoreIR` y exportación en `interchange` | Aceptado, enmendado por ADR-0031 | Dominio, M2, M3 |
| [ADR-0011](ADR-0011-semantica-de-anclas-ante-ediciones.md) | Semántica de las anclas ante ediciones estructurales | Aceptado | Dominio, M2, M3, M4 |
| [ADR-0012](ADR-0012-autenticacion-e-identidad.md) | Autenticación e identidad de usuario | Aceptado | Transversal |
| [ADR-0013](ADR-0013-revalidacion-y-versionado-de-hallazgos.md) | Revalidación bajo demanda y versionado de hallazgos | Aceptado | M2, M3, M4 |
| [ADR-0014](ADR-0014-ciclo-de-vida-de-la-sesion.md) | Ciclo de vida de la sesión (estados, finalización y reapertura) | Aceptado, enmendado por ADR-0043 | M2, M3, M4 |
| [ADR-0015](ADR-0015-operacion-y-despliegue-del-backend.md) | Operación y despliegue del backend | Aceptado | API, Infra |
| [ADR-0016](ADR-0016-transcripcion-sincrona-vs-asincrona.md) | Transcripción síncrona de página única frente a colas asíncronas | Aceptado | API, Plano Online |
| [ADR-0017](ADR-0017-validacion-del-contenido-de-las-ediciones.md) | Validación del contenido de las ediciones y estado previo fijado por el servidor | Aceptado | Dominio, API, M3, M4 |
| [ADR-0018](ADR-0018-homr-como-unico-motor-omr.md) | HOMR como único motor OMR | Aceptado | M1, API |
| [ADR-0019](ADR-0019-base-del-cliente-web.md) | Base del cliente web (Fase 8) | Aceptado | Web |
| [ADR-0020](ADR-0020-sesion-del-cliente-web.md) | Sesión del cliente web: token, recuperación y caducidad | Aceptado | Web |
| [ADR-0021](ADR-0021-visualizacion-de-la-transcripcion-y-marcado-de-hallazgos.md) | Visualización de la transcripción y marcado de hallazgos por compás | Aceptado | Web, M2 |
| [ADR-0022](ADR-0022-registro-de-cuentas-con-activacion.md) | Registro de cuentas con activación por un investigador (enmienda ADR-0012 §1) | Aceptado, enmendado por ADR-0025 | API, Persistencia, Web |
| [ADR-0023](ADR-0023-despliegue-publico-con-tailscale-funnel.md) | Despliegue público en el homelab con Tailscale Funnel | Aceptado | Infra, Web |
| [ADR-0024](ADR-0024-transcripciones-simultaneas.md) | Transcripciones simultáneas: HOMR de una en una y tope de admisión en la API | Aceptado | OMR, API |
| [ADR-0025](ADR-0025-registro-abierto-sin-aprobacion.md) | Registro abierto: la cuenta queda activa al crearse (enmienda ADR-0022 §4 y §9) | Aceptado | API, Web |
| [ADR-0026](ADR-0026-reproduccion-de-la-partitura-en-el-navegador.md) | Reproducción de la partitura en el navegador: notas del mapa de tiempos, Tone.js con reloj por `setTimeout` y la CSP sin cambios | Aceptado | Web |
| [ADR-0027](ADR-0027-seleccion-de-notas-sobre-la-partitura.md) | Selección de notas sobre la partitura dibujada: mapa ancla→caja por evento emparejado con OSMD, puntero, teclado y estado en Zustand | Aceptado, enmendado por ADR-0028 | Web |
| [ADR-0028](ADR-0028-notas-sin-duracion-como-notas-de-adorno.md) | Notas sin duración como notas de adorno en el MusicXML | Aceptado | Interchange, Web |
| [ADR-0029](ADR-0029-api-con-usuario-sin-privilegios.md) | La API corre con un usuario sin privilegios (UID 10001), con la migración de los volúmenes anteriores | Aceptado | Infra, API |
| [ADR-0030](ADR-0030-correccion-de-altura-duracion-y-alteracion.md) | Corrección de la altura, la duración y la alteración de la nota elegida: controles, teclado, `base_seq` sin envío optimista y el 409 recargado | Aceptado, enmendado por ADR-0037 | Web |
| [ADR-0031](ADR-0031-marcas-de-notacion-en-el-score-ir.md) | Marcas de notación en el `ScoreIR`: articulaciones y calderón en el evento, dinámicas y reguladores por posición del compás, extremos de ligadura con número único por parte (enmienda ADR-0010) | Aceptado | Dominio, Interchange, API |
| [ADR-0032](ADR-0032-varias-voces-huecos-y-plicas.md) | Varias voces: el hueco de una voz como silencio invisible (`Event.hidden`), plicas por altura y voces numeradas por pentagrama al exportar, y una voz que sale antes no es un error de balance | Aceptado | Dominio, Interchange, Validación, Web |
| [ADR-0033](ADR-0033-insertar-borrar-clave-y-armadura.md) | Insertar y borrar eventos y cambiar la clave y la armadura desde la vista: antes del evento elegido, qué queda elegido tras guardar, el acorde, las ligaduras huérfanas, los huecos y el primer compás para OSMD | Aceptado | Web |
| [ADR-0034](ADR-0034-deshacer-y-rehacer-desde-la-vista.md) | Deshacer y rehacer desde la vista: `POST /undo`, rehacer como la misma edición otra vez, las pilas leídas del log, el teclado fuera de los campos de texto, qué queda elegido y la historia de ediciones | Aceptado, enmendado por ADR-0037 | Web |
| [ADR-0035](ADR-0035-descartar-restaurar-y-revalidar-desde-la-vista.md) | Descartar, restaurar y revalidar los posibles errores desde la vista: cada posible error con su motivo opcional, el lenguaje honesto, la revalidación explícita con el `current_seq` que devuelve, quién puede hacerlo y que una revalidación solo herede los descartes de la validación vigente | Aceptado | Web, Aplicación |
| [ADR-0036](ADR-0036-capa-de-sugerencias-aprendida.md) | Capa de sugerencias que aprende de las correcciones: frecuencias suavizadas con retroceso, rasgos de lo leído, las reglas acotan y la capa ordena, sugerencias estructuradas que la persona aplica o rechaza, umbral por validación cruzada, registro propio y promoción solo si mejora en la partición fija | Aceptado | Aprendizaje, Validación, Aplicación, API |
| [ADR-0037](ADR-0037-una-edicion-en-un-solo-viaje.md) | Una edición en un solo viaje: el 201 de `POST /edits` y `POST /undo` devuelven el estado nuevo, caché del estado materializado por `(sesión, seq)`, `GET /sessions/{id}?fields=view` y `Server-Timing` (enmienda ADR-0030 §4 y ADR-0034 §1) | Aceptado | API, Aplicación, Web, Infra |
| [ADR-0038](ADR-0038-redibujar-tras-una-edicion-y-ordenes-en-espera.md) | Redibujar tras una edición en una sola instancia de OSMD, antes de pintar y entera (OSMD no dibuja un sistema suelto); la marca de la nota elegida que espera al dibujo nuevo; una sola orden en espera mientras se guarda, planeada de nuevo sobre el estado nuevo y nunca reintentada; y la reproducción que sigue tras una edición | Aceptado | Web |
| [ADR-0039](ADR-0039-anadir-y-quitar-marcas-de-notacion.md) | Añadir y quitar marcas de notación: cuatro operaciones de tipo «fijar» (`SetNoteMarks`, `SetDynamic`, `SetSlur`, `SetWedge`), ligaduras y reguladores con sus dos extremos en una edición, y la política de `EditOp` para el dataset y las métricas (`CONTENT_EDIT_OPS` y `MARK_EDIT_OPS`) | Aceptado | Dominio, Aprendizaje, API, Web |
| [ADR-0040](ADR-0040-catalogo-de-reglas-y-mensajes-en-lenguaje-musical.md) | Catálogo de reglas del validador y mensajes en lenguaje musical: figuras, tiempos y nombres de notas sin fracciones, «Qué revisar» en la vista, `time.signature`, `tuplet.incomplete` y `accidental.repeated` nuevas, `key.consistency` reducida a las armaduras de un piano, anacrusa, último compás, silencio de compás y notas de adorno sin falsos positivos, y la condición no asistida sin nada del validador | Aceptado | Validación, Web, Aplicación |
| [ADR-0042](ADR-0042-login-con-el-mismo-trabajo-de-hash.md) | El inicio de sesión hace el mismo trabajo de hash en los tres casos del 401: una verificación siempre, contra el hash de la cuenta o el de relleno que `PasswordHasher.dummy_hash()` calcula con los parámetros reales | Aceptado | Aplicación, API |
| [ADR-0043](ADR-0043-finalizar-y-reabrir-desde-la-vista.md) | Finalizar y reabrir una sesión desde la vista: finalizar valida como una revalidación (conserva los descartes de la validación vigente, D65; nada en `unassisted`), devuelve los activos y da 409 si ya está finalizada; confirmación, resultado de la validación final, solo lectura y «Reabrir» en la web | Aceptado | Aplicación, API, Web |


