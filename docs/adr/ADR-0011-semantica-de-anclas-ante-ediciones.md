# ADR-0011: Semántica de las anclas ante ediciones estructurales

- **Estado:** Aceptado
- **Fecha:** 2026-10-03
- **Decisores:** Arquitecto de Software, Dirección del proyecto Cadenza
- **Relacionado:** [ADR-0002](ADR-0002-score-document-anchor-index.md), [ADR-0007](ADR-0007-edit-events-inmutables.md), [ADR-0010](ADR-0010-score-ir-atributos-y-exportacion.md)

---

## Contexto

El ADR-0002 define el ancla como una **ruta lógica** (parte, pentagrama, compás,
voz, posición dentro de la voz) y exige que sea estable y determinista. El
ADR-0007 añade las operaciones `InsertEvent` y `DeleteEvent` y deja anotado un
riesgo sin resolver: esas operaciones desplazan la posición de los eventos
siguientes del mismo compás y la misma voz.

Sin una regla explícita, la misma ancla puede designar eventos distintos según
el momento en que se lea:

- un `Finding` calculado sobre el documento crudo apunta a otro evento después de
  una inserción o un borrado;
- dos ediciones con la misma ancla se refieren a eventos distintos según su
  `seq`;
- la `bbox` del `AnchorIndex`, construido sobre el documento crudo, deja de
  corresponder al evento que ocupa esa posición;
- el plano offline no puede asociar con seguridad una corrección a la región de
  la imagen original.

La implementación actual ya resuelve la posición de cada edición sobre el estado
materializado hasta ese punto (`cadenza.domain.projection.apply_edit`), pero esa
regla no está escrita ni cubierta para hallazgos, coordenadas y muestras de
entrenamiento.

## Decisión

El ancla sigue siendo **posicional**. Lo que se fija es **respecto a qué estado
se interpreta** y cómo se traduce entre estados.

### 1. Toda ancla es relativa a un estado

El estado de una sesión se identifica por un número de secuencia: el estado `0`
es el documento crudo del OMR y el estado `n` es el resultado de aplicar las
ediciones `1..n`.

| Dato | Estado sobre el que se interpreta su ancla |
|---|---|
| `AnchorIndex` del `ScoreDocument` persistido | Estado `0` (documento crudo) |
| `EditEvent` con `seq = n` | Estado `n − 1` (el inmediatamente anterior a la edición) |
| `Finding` | Estado `at_seq` en el que se calculó |

### 2. Regla de desplazamiento

Dentro de un mismo `(parte, pentagrama, compás, voz)`:

- `InsertEvent` en la posición `p` suma 1 a la posición de los eventos que
  estaban en `p` o después. La posición `p` puede valer desde `0` hasta el número
  de eventos de la voz, de modo que insertar al final de la voz es válido.
- `DeleteEvent` en la posición `p` resta 1 a la posición de los eventos que
  estaban después de `p`.
- El resto de operaciones no desplaza nada.

### 3. Traducción entre estados

El dominio ofrece una función pura, `origin_anchor(anchor, at_seq, edits)`, que
devuelve el ancla del mismo evento en el estado `0`, o indica que el evento fue
insertado por una edición y no existe en el documento crudo. Se obtiene
deshaciendo la regla de desplazamiento sobre el log, de `at_seq` hacia atrás.

Con ella:

- el índice de anclas de cualquier estado se deriva con `build_anchor_index`
  sobre el `ScoreIR` materializado y **hereda** `bbox` y `confidence` del evento
  de origen;
- el plano offline asocia cada corrección a la región de la imagen original;
- un hallazgo descartado se reconoce tras revalidar porque su evento de origen es
  el mismo.

### 4. Un solo escritor por sesión

El log es secuencial. Una edición construida sobre un estado obsoleto se detecta
por el conflicto de `seq` (409) o porque su valor `before` no coincide con el
estado actual (422); el cliente debe recargar la sesión y reconstruir la edición.

## Consecuencias

### Positivas
- **No cambia el modelo.** `Anchor`, `EditEvent`, el formato serializado, la API
  y el ADR-0002 quedan como están; la regla ya es la que aplica el código.
- **Determinismo preservado:** dos lecturas del mismo archivo producen las mismas
  anclas, porque la identidad sigue derivando de la posición.
- **Trazabilidad hasta la imagen:** cualquier evento del estado actual se rastrea
  hasta su origen, o se sabe que es nuevo.
- Las reglas son pocas y puras, así que admiten pruebas de propiedad con
  secuencias aleatorias de inserciones y borrados.

### Riesgos / costos
- Quien use un ancla debe saber **de qué estado es**. Un ancla sin su `seq` es
  ambigua; por eso `findings` lleva `at_seq`.
- La traducción recorre el log; en sesiones muy largas conviene memorizar el
  resultado por estado.
- `apply_edit` debe admitir la inserción al final de la voz, que hoy rechaza.
- No hay edición concurrente sobre una misma sesión.

## Alternativas consideradas

1. **Identificador estable por evento**, asignado al transcribir y conservado
   tras las ediciones. Descartado: da referencias más robustas, pero obliga a
   cambiar anclas, ediciones, API e interfaz y reemplaza parte del ADR-0002; el
   identificador, además, no se puede derivar de una nueva lectura del archivo.
2. **Usar como identidad la ruta en el documento crudo** y derivar la posición al
   materializar. Descartado por el mismo coste de migración; la función de
   traducción ofrece la misma información sin cambiar el modelo.
3. **Dejar la regla implícita en `apply_edit`.** Descartado: es el estado actual
   y deja sin resolver hallazgos, coordenadas y muestras de entrenamiento.
