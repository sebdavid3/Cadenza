# ADR-0002: `ScoreDocument` con `AnchorIndex` como fuente de verdad

- **Estado:** Aceptado
- **Fecha:** 2026-09-20
- **Decisores:** Arquitecto de Software, Dirección del proyecto Cadenza
- **Relacionado:** [ADR-0001](ADR-0001-monolito-modular-hexagonal.md), [ADR-0007](ADR-0007-edit-events-inmutables.md)

---

## Contexto

Los cuatro módulos de Cadenza necesitan **referirse a la misma entidad musical**:

- el validador (M2) emite hallazgos ("la suma de duraciones del compás 7 no
  cuadra") que deben señalar un evento concreto;
- la interfaz HITL (M3) permite editar ese evento y registrar la corrección;
- el módulo de aprendizaje activo (M4) construye pares de entrenamiento a partir
  del diff entre la lectura cruda del OMR y la versión corregida por el humano;
- la UI (M3) dibuja *overlays* de error sobre las notas correspondientes.

MusicXML, pese a ser el formato de intercambio objetivo, **no sirve como fuente
de verdad** para este propósito:

- Sus identificadores de evento no son estables ni obligatorios; distintos
  productores (HOMR, oemer, MuseScore) los generan o los omiten de forma
  distinta.
- Un ciclo de parseo → serialización → parseo puede reordenar o renumerar
  elementos, rompiendo cualquier referencia externa.
- Su estructura permite múltiples representaciones equivalentes de la misma
  música (voces implícitas, *chords*, *voices*, tuplets), lo que hace ambigua la
  comparación y el diff.

Sin un modelo canónico con referencias estables, cada módulo terminaría
inventando su propia noción de "la nota X", con el consiguiente acoplamiento y
pérdida de trazabilidad.

## Decisión

Se define el **`ScoreDocument`** como la **fuente de verdad** del sistema,
compuesto por tres elementos:

```
ScoreDocument = (ScoreIR, AnchorIndex, Provenance)
```

### 1. `ScoreIR` (representación intermedia simbólica)
Notación normalizada construida sobre `music21`, que resuelve las
ambigüedades de MusicXML a una estructura canónica: partes, pentagramas,
compases, voces y eventos (notas, silencios, alteraciones, claves, armaduras).
MusicXML pasa a ser **una serialización de entrada/salida**, no la
representación interna.

### 2. `AnchorIndex` (identificadores estables de evento)
Un índice que asigna a cada evento musical un **ancla estable**, concebida como
una ruta lógica, no como un índice de array:

```text
Anchor = {
  part:        int,      # índice de parte
  staff:       int,      # índice de pentagrama dentro de la parte
  measure:     int,      # número de compás lógico (1-based)
  voice:       int,      # índice de voz dentro del pentagrama
  event_index: int,      # posición del evento dentro de la voz
  staff_id:    string    # identificador estable de pentagrama (uuid determinista)
}
```

Reglas de diseño del ancla:

- **Estabilidad:** el ancla se deriva de la posición **lógica** (compás, voz,
  orden de evento), no de punteros de memoria ni de IDs de MusicXML.
- **Determinismo:** dos parseos del mismo MusicXML producen las mismas anclas.
- **Opcionalidad controlada:** el ancla puede portar metadatos adicionales no
  esenciales, como `bbox` (coordenadas en la imagen original) y `confidence`
  (confianza del OMR), usados por la UI y por M4 sin ser obligatorios.
- **Direccionabilidad:** los `Finding`, los eventos de edición y los pares de
  entrenamiento **solo** referencian eventos mediante anclas.

```text
AnchorIndex : Map<Anchor, EventRef>
EventRef    = { kind: note|rest|clef|key|time|..., ir_handle, bbox?, confidence? }
```

### 3. `Provenance` (trazabilidad del origen)
Metadatos que documentan de dónde proviene el documento y cada modificación:

- motor y **versión de modelo** de OMR que produjo el `ScoreIR`;
- versión del validador y reglas aplicadas;
- historial de ediciones humanas (referencias a los eventos de edición, ADR-0007);
- hash de contenido del artefacto de imagen de origen.

## Consecuencias

### Positivas
- **Referencias estables** compartidas por M2, M3 y M4: una nota es la misma nota
  para todos, incluso tras serializar a MusicXML y volver a parsear.
- **Diff significativo:** comparar `raw` vs `corrected` se reduce a comparar por
  ancla, habilitando la métrica de magnitud de corrección del aprendizaje activo.
- **Desacoplamiento de MusicXML:** se puede cambiar el OMR de origen sin que los
  consumidores se enteren.
- **Trazabilidad académica:** `Provenance` permite reproducir un experimento
  indicando motor, versión de modelo y reglas.

### Riesgos / costos
- **Complejidad de alineación:** definir el ancla correcta para casos límite
  (voces cruzadas, *tuplets*, acordes, compases anacrúsicos) es trabajo de diseño
  no trivial.
- **Capa de traducción obligatoria:** toda entrada/salida MusicXML debe pasar por
  un *mapper* `MusicXML ↔ ScoreDocument`, que hay que construir y probar.
- Riesgo de sobre-modelar el dominio antes de tener corpus real; se mitiga
  congelando la primera versión del ancla y versionándola (ADR de evolución si
  cambia).

## Alternativas consideradas

1. **Usar MusicXML directamente como modelo de dominio.** Descartado: IDs
   inestables y representaciones ambiguas rompen la referencia cruzada entre
   módulos.
2. **Usar los IDs internos de `music21` (p. ej. `id(...)`).** Descartado: no
   sobreviven a la serialización ni a la reconstrucción del grafo.
3. **Identificadores propios insertados en el propio MusicXML** (atributos
   `id` personalizados). Descartado como fuente de verdad: contamina el formato
   de salida y depende de que todos los productores los preserven; puede usarse
   como *hint* transpirable, pero no como autoridad.
