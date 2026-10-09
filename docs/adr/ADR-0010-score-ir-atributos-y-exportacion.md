# ADR-0010: Atributos de compás en el `ScoreIR` y exportación en `interchange`

- **Estado:** Aceptado
- **Fecha:** 2026-10-03
- **Decisores:** Arquitecto de Software, Dirección del proyecto Cadenza
- **Relacionado:** [ADR-0002](ADR-0002-score-document-anchor-index.md), [ADR-0006](ADR-0006-render-editor-osmd-verovio-zustand.md), [ADR-0007](ADR-0007-edit-events-inmutables.md)

---

## Contexto

El ADR-0002 establece el `ScoreDocument` como fuente de verdad y MusicXML como
una serialización de entrada y salida. Para que eso se sostenga, el `ScoreIR`
debe contener todo lo necesario para **regenerar** una partitura equivalente.

El `ScoreIR` implementado modela, por compás, solo la métrica, y por evento, la
altura y la duración. No modela clave, armadura ni ligaduras. Las consecuencias
son concretas:

- La exportación a MusicXML pierde información: una partitura en clave de fa o
  con tres sostenidos se exporta sin ellos.
- La evaluación de calidad del OMR tuvo que saltarse el `ScoreIR` y comparar el
  MusicXML nativo de HOMR (`HOMREngine.transcribe_musicxml`) para no penalizar
  esa pérdida.
- Las operaciones `SetClef` y `SetKey` existen en `EditOp` (ADR-0007) pero no se
  pueden proyectar, porque no hay dónde aplicar el cambio.
- Las reglas de armadura y alteraciones previstas para el validador no tienen
  datos sobre los que operar.

Por otro lado, `ARCHITECTURE.md` v1.0 preveía un paquete `packages/export` para
la serialización. En la fase 6 se creó `packages/interchange`, que ya concentra
`music21` y ya implementa `score_ir_to_musicxml`. Un segundo paquete con la misma
dependencia y la misma frontera duplicaría la responsabilidad.

## Decisión

### 1. El `ScoreIR` porta los atributos de compás y la ligadura

```text
Measure(number, events, time_signature, clef, key_signature)
Event(kind, voice, pitch, duration_beats, tie, bbox?, confidence?, ir_handle?)
```

- `clef` y `key_signature` son tipos de valor propios del dominio, inmutables y
  sin dependencias, análogos a `TimeSignature`.
- Son opcionales por compás: un valor ausente significa "se mantiene el del
  compás anterior". Así la representación es compacta y la serialización de
  documentos antiguos sigue siendo válida.
- `tie` indica si el evento inicia, continúa o cierra una ligadura.
- El `ScoreIR` sigue siendo código puro: ninguno de estos tipos importa
  `music21`.

### 2. Todas las operaciones de `EditOp` son proyectables

`apply_edit` implementa `SetClef` y `SetKey` sobre el compás del ancla, y
`SetAccidental` deja de ser un alias de `SetPitch`.

### 3. La exportación vive en `packages/interchange`

- `packages/interchange` es la **única** frontera con `music21`, en ambos
  sentidos: lectura (MusicXML, MEI, `**kern` → `ScoreIR`) y exportación
  (`ScoreIR` → MusicXML 4.0 y MIDI 1.0).
- Implementa el puerto `ScoreExporter` que consume la capa de aplicación
  ([ADR-0009](ADR-0009-capa-de-aplicacion.md)).
- No se crea el paquete `packages/export`.

## Consecuencias

### Positivas
- **Exportación fiel**: la ida y vuelta MusicXML → `ScoreIR` → MusicXML conserva
  clave, armadura, métrica, alturas, duraciones y ligaduras.
- El `ScoreIR` puede ser el insumo del renderizado (ADR-0006) y de la evaluación,
  sin atajos por el MusicXML nativo del motor.
- Habilita las reglas de armadura y alteraciones del validador.
- `music21` queda confinado a un solo paquete.

### Riesgos / costos
- Cambia el formato serializado del `ScoreDocument`. Los documentos ya
  persistidos se leen como válidos porque los campos nuevos son opcionales, pero
  hay que cubrirlo con pruebas de compatibilidad.
- El `AnchorIndex` no cambia: clave y armadura son atributos del compás, no
  eventos anclados. Las ediciones `SetClef`/`SetKey` se anclan al primer evento
  del compás afectado.
- El alcance sigue siendo monofonía y piano simple; no se modelan dinámicas,
  articulaciones ni texto.

## Alternativas consideradas

1. **Modelar clave y armadura como eventos** (`EventKind.CLEF`, `EventKind.KEY`).
   Descartado: desplazaría el `event_index` de las notas y rompería la
   estabilidad de las anclas que exige el ADR-0002.
2. **Conservar el MusicXML original y parchearlo al exportar.** Descartado:
   convertiría de nuevo a MusicXML en fuente de verdad, contra el ADR-0002.
3. **Crear `packages/export` como estaba previsto.** Descartado: duplicaría la
   frontera con `music21` que ya resuelve `packages/interchange`.
