# ADR-0014: Ciclo de vida de la sesión (estados, finalización y reapertura)

- **Estado:** Aceptado
- **Fecha:** 2026-10-07
- **Decisores:** Arquitecto de Software, Equipo de Desarrollo de Cadenza
- **Relacionado:** [ADR-0007](ADR-0007-edit-events-inmutables.md), [ADR-0008](ADR-0008-active-learning-model-registry.md), [ADR-0009](ADR-0009-capa-de-aplicacion.md), [ADR-0011](ADR-0011-semantica-de-anclas-ante-ediciones.md), [ADR-0012](ADR-0012-autenticacion-e-identidad.md), [ADR-0013](ADR-0013-revalidacion-y-versionado-de-hallazgos.md)

---

## Contexto

El issue #5 incorporó la columna `sessions.status` en la base de datos, pero hasta este momento
ningún módulo definía formalmente los estados admisibles ni sus transiciones de ciclo de vida.

En el flujo de interacción humana (HITL), el transcriptor carga una partitura, revisa los hallazgos
detectados por las reglas de validación y aplica ediciones en el log *append-only*.
Sin embargo, sin un ciclo de vida formal surgen los siguientes problemas:

1. **Ambigüedad en el consumo offline (#19, #26):** El constructor del dataset de aprendizaje
   activo (`DatasetBuilder`) necesita distinguir entre sesiones completamente corregidas y revisadas
   de aquellas abandonadas, preliminares o a medio corregir. Entrenar sobre sesiones incompletas
   contamina las muestras supervisadas con errores que el transcriptor aún no había corregido.
2. **Inmutabilidad y cierre de la corrección:** Una vez que el usuario considera completada la
   partitura, debe existir un cierre formal que congele la versión final, ejecute una revalidación
   definitiva y registre la secuencia final (`final_seq`).
3. **Flexibilidad operativa:** Si tras finalizar una partitura se descubre un error omitido,
   debe permitirse la reapertura explícita sin destruir el log de ediciones previas.

## Decisión

### 1. Estados del ciclo de vida (`SessionStatus`)

Se definen cuatro estados mutuamente excluyentes para una sesión:

```
 [transcribe_score]
         │
         ▼
    transcribed ────────(append_edit)───────► correcting
         │                                       ▲    │
         │                                       │    │
         │(finalize_session)       (reopen_session)   │(finalize_session)
         │                                       │    │
         ▼                                       │    ▼
         └───────────────────────────────────► finalized

 (failed: reservado para abortos o fallos irrecuperables del pipeline)
```

1. **`transcribed`:** Estado inicial tras la ejecución exitosa de `transcribe_score`.
   Contiene el documento crudo del OMR y los hallazgos iniciales en `seq = 0`.
2. **`correcting`:** La sesión se encuentra activamente en proceso de corrección humana.
   Transiciona automáticamente a este estado en cuanto se registra la primera edición
   exitosa en `append_edit`, o al reabrir una sesión finalizada.
3. **`finalized`:** La sesión ha sido cerrada formalmente por el usuario. No admite más
   ediciones salvo reapertura explícita.
4. **`failed`:** Estado terminal para sesiones cuyo procesamiento no pudo completarse.

### 2. Finalización de la sesión (`finalize_session`)

El cierre de la sesión se invoca mediante el caso de uso `finalize_session` y el endpoint
`POST /sessions/{id}/finalize`:

1. **Revalidación integral:** Se materializa el `ScoreIR` actual con todas las ediciones
   registradas y se ejecuta `ValidationEngine.validate`.
2. **Actualización de hallazgos:** Los hallazgos vigentes se asocian a `current_seq`
   y se actualiza `sessions.validated_at_seq` (ADR-0013).
3. **Cierre de estado:** El campo `sessions.status` transiciona a `finalized`.
4. **Respuesta tipada:** Devuelve `FinalizeResponse` con el ID de la sesión, `status = "finalized"`,
   el `final_seq` alcanzado y la lista de hallazgos vigentes.

### 3. Bloqueo de ediciones sobre sesiones finalizadas

El caso de uso `append_edit` verifica el estado de la sesión antes de procesar cualquier edición:
- Si `session.status == "finalized"`, se aborta la operación lanzando `SessionClosed(session_id)`.
- La API traduce esta excepción a **HTTP 409 Conflict**, con un mensaje claro que indica
  que la sesión está cerrada y debe ser reabierta explícitamente para admitir nuevas ediciones.
- Esto preserva la inmutabilidad del estado final y evita modificaciones accidentales.

### 4. Reapertura explícita (`reopen_session`)

Para subsanar correcciones omitidas, el caso de uso `reopen_session` y el endpoint
`POST /sessions/{id}/reopen` permiten reabrir una sesión:
- El estado transiciona de nuevo a `correcting` (o `transcribed` si nunca tuvo ediciones).
- El log *append-only* existente se conserva intacto.
- A partir de este momento, `append_edit` vuelve a admitir nuevas ediciones con `base_seq = current_seq`.

### 5. Consumo exclusivo de sesiones finalizadas en `DatasetBuilder` (#19)

El componente `DatasetBuilder.build` en `packages/learning`:
- Incorpora el parámetro `status: str = "finalized"`.
- Si el estado de la sesión no es `"finalized"`, retorna una tupla vacía `()`.
- Garantiza que solo los documentos completamente revisados y cerrados generen muestras
  de entrenamiento (`TrainingSample`).

### 6. Filtrado y consultas en repositorio y API (#27)

- El puerto `SessionRepository.list(owner_id=..., status=...)` y sus adaptadores
  (`SqlAlchemySessionRepository`, `InMemorySessionRepository`) soportan filtrado por estado.
- Esto permite al plano offline y al endpoint `GET /sessions` listar sesiones por estado
  (por ejemplo, consultar todas las sesiones en corrección o todas las finalizadas).

### 7. Autorización (ADR-0012)

- El usuario propietario de la sesión puede finalizarla y reabrirla.
- Un usuario con rol `transcriptor` que intente operar sobre una sesión ajena recibe `SessionNotFound` (HTTP 404).
- Un usuario con rol `investigador` sobre una sesión ajena recibe `Forbidden` (HTTP 403).
- Peticiones sin token o inválidas reciben HTTP 401.

---

## Consecuencias

### Positivas
- **Alineación offline/online:** El aprendizaje activo solo consume datos de alta fidelidad,
  cerrados por transcritores humanos.
- **Inmutabilidad protegida:** Se previene la mutación accidental de partituras ya aprobadas.
- **Flexibilidad sin pérdida de historia:** La reapertura permite ajustes posteriores sin
  romper el invariante *append-only*.
- **Trazabilidad:** Al finalizar se revalida y se registra de forma determinista el `final_seq`.

### Neutras / Negativas
- El cliente o usuario debe emitir una petición adicional (`POST /sessions/{id}/finalize`)
  cuando considere terminada la partitura, y manejar HTTP 409 si intenta editar sin reabrir.
