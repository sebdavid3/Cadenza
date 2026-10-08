# ADR-0013: Revalidación bajo demanda y versionado de hallazgos

- **Estado:** Aceptado
- **Fecha:** 2026-10-07
- **Decisores:** Arquitecto de Software, Equipo de Desarrollo de Cadenza
- **Relacionado:** [ADR-0002](ADR-0002-score-document-anchor-index.md), [ADR-0007](ADR-0007-edit-events-inmutables.md), [ADR-0009](ADR-0009-capa-de-aplicacion.md), [ADR-0011](ADR-0011-semantica-de-anclas-ante-ediciones.md), [ADR-0012](ADR-0012-autenticacion-e-identidad.md)

---

## Contexto

Durante el flujo de interacción humana (HITL), el transcriptor aplica ediciones para corregir
defectos de transcripción (por ejemplo, alterar una duración que rompe la métrica de un compás).
Esto plantea dos requerimientos potencialmente contradictorios:

1. **Eliminación del hallazgo en la vista activa:** Cuando el usuario subsana un compás
   desbalanceado, el hallazgo de error debe desaparecer de la lista de pendientes para
   señalar que la partitura está corregida.
2. **Preservación del historial para análisis de esfuerzo (#38):** La plataforma de
   experimentación requiere medir el esfuerzo cognitivo y humano (cuántos errores existían
   inicialmente, cuáles fueron resueltos mediante ediciones y cuáles fueron introducidos
   accidentalmente). Por ende, el log de hallazgos no puede borrarse destructivamente (`DELETE`).
3. **Punto de ejecución de la validación:** Se debía decidir si cada adición al log
   (`POST /sessions/{id}/edits`) revalida automáticamente todo el documento o si se dispara
   de forma explícita bajo demanda (`POST /sessions/{id}/validate`).

## Decisión

### 1. Revalidación explícita bajo demanda

La revalidación de reglas sobre la partitura se ejecuta de forma explícita mediante el
endpoint `POST /sessions/{id}/validate`.

- No se ejecuta el motor de validación completo en cada inserción del log append-only
  (`POST /sessions/{id}/edits`), evitando ralentizar la interacción interactiva (batching
  o edición fluida de múltiples notas).
- La revalidación reconstruye el estado materializado actual de la partitura
  (`materialize(raw_score, edits)`), recalcula el `AnchorIndex` con las coordenadas
  heredadas del origen (ADR-0011) y somete el `ScoreDocument` al conjunto de reglas
  activas (`ValidationEngine.validate`).

### 2. Columna `sessions.validated_at_seq` y versionado de hallazgos

Se añade la columna `validated_at_seq: int` (default `0`) en la tabla `sessions`.

- Cuando se transcribe una partitura por primera vez, `validated_at_seq = 0` y los
  hallazgos del OMR crudo se guardan con `at_seq = 0`.
- Cuando el cliente solicita `POST /sessions/{id}/validate`, se calcula el `current_seq`
  de la sesión (último `seq` de `EditEvent`, o 0 si no hay ediciones).
- Los hallazgos producidos por las reglas se etiquetan con `at_seq = current_seq`.
- La operación `session_repository.replace_findings(session_id, findings, at_seq=current_seq)`
  actualiza `sessions.validated_at_seq = current_seq` e inserta los nuevos hallazgos
  en la tabla `findings`.
- **Idempotencia por `(session_id, at_seq)`:** si ya existen hallazgos con
  `at_seq = current_seq` (revalidar dos veces sin ediciones nuevas, o revalidar una
  sesión recién transcrita en `seq = 0`), se sustituyen. No es historia: es el mismo
  estado reevaluado, y conservar ambas copias duplicaría los hallazgos vigentes.
  **Los hallazgos de cualquier otro `at_seq` nunca se eliminan.**
- Los hallazgos son datos derivados del documento y del log; el log de ediciones
  (`edit_events`) sigue siendo estrictamente *append-only* (ADR-0007).

### 3. Vista de hallazgos vigentes vs. auditoría de esfuerzo

- **Hallazgos vigentes (por defecto):** Las consultas estándar (`GET /sessions/{id}`,
  `GET /sessions/{id}/findings`, y la respuesta de `POST /sessions/{id}/validate`)
  devuelven los hallazgos donde `FindingRecord.at_seq == session.validated_at_seq`
  (`latest_only=True`). Si un error fue corregido en `seq = 1`, la evaluación genera 0
  hallazgos para `seq = 1`, por lo que la lista de hallazgos vigentes queda vacía.
- **Auditoría y análisis de esfuerzo (offline / investigación):** El repositorio y la API
  admiten `latest_only=False` o filtrado explícito por `at_seq` (`GET /sessions/{id}/findings?latest_only=false`
  o `?at_seq=0`). Esto permite reconstruir la evolución temporal de la calidad de la partitura
  a lo largo del ciclo de vida de la sesión.

### 4. Permisos de seguridad (ADR-0012)

- El transcriptor dueño de la sesión puede revalidar su partitura.
- Un transcriptor que no es dueño de la sesión recibe `SessionNotFound` (HTTP 404).
- Un usuario con rol de `investigador` puede revalidar cualquier sesión (HTTP 200).
- Peticiones sin token o con credenciales inválidas responden HTTP 401.

---

## Consecuencias

### Positivas
- **Inmutabilidad y trazabilidad:** Toda la evolución de la calidad de la partitura queda
  registrada sin pérdidas destructivas.
- **Claridad cognitiva para el usuario:** Corregir un compás hace que desaparezca su advertencia
  o error en la interfaz tras revalidar.
- **Rendimiento:** Separar la inserción de eventos del cómputo de validación permite al cliente
  controlar cuándo inspeccionar reglas complejas.

### Negativas / Mitigaciones
- El cliente debe invocar explícitamente `POST /sessions/{id}/validate` para refrescar los
  hallazgos tras realizar correcciones (el visor web puede automatizar la llamada al
  pausar la edición o al pulsar un botón "Revalidar").
