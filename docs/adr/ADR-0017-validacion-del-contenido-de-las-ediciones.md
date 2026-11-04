# ADR-0017: Validación del contenido de las ediciones y estado previo fijado por el servidor

- **Estado:** Aceptado
- **Fecha:** 2026-10-13
- **Decisores:** Equipo de Desarrollo de Cadenza
- **Relacionado:** [ADR-0007](ADR-0007-edit-events-inmutables.md), [ADR-0009](ADR-0009-capa-de-aplicacion.md), [ADR-0011](ADR-0011-semantica-de-anclas-ante-ediciones.md), [ADR-0012](ADR-0012-autenticacion-e-identidad.md), [#117](https://github.com/sebdavid3/Cadenza/issues/117)

---

## Contexto

`POST /sessions/{id}/edits` comprobaba el ancla, `base_seq` y, si el cliente lo enviaba, que
`before` coincidiera con el estado. No comprobaba `after`. El 2026-10-13, contra la API en
ejecución con el motor de prueba, estas ediciones respondieron 201 y quedaron en el log
*append-only*:

| Edición | Efecto |
|---|---|
| `SetPitch` con `after: {}` o `after: null` | la nota queda con `pitch: null` y se exporta como silencio |
| `SetPitch` con `after: {"pitch": "H9"}` | la exportación a MusicXML y MIDI responde 500 hasta que se deshace |
| `SetDuration` con `after: {}` | la nota queda con `duration_beats: null` |

La revisión del cambio encontró otros dos casos que el exportador no soporta: duraciones
enormes (`100000` pulsos o `"1e30"` dejan la exportación a MusicXML sin terminar) y
denominadores que music21 no sabe escribir (`1/17`, `3/1000`).

Además, el evento inverso de ADR-0007 (`create_inverse_edit`) intercambia `before` y `after`.
Como `before` era opcional, deshacer una edición enviada con `before: null` dejaba la nota sin
altura o sin duración, quitaba la clave o la armadura del compás y «restauraba» un evento
borrado como una nota vacía. Que deshacer funcionara dependía de que el cliente enviara un
`before` completo.

Las dos cosas incumplen el invariante de que ninguna edición inválida entra al log y las
provocaría cualquier error de formulario del frontend.

## Decisión

1. **El servidor valida `after` por operación** (`validate_after` en `packages/domain`) y
   rechaza con `InvalidEdit` (HTTP 422, `detail` como texto) sin persistir nada. Las reglas
   usan el vocabulario canónico del dominio:

   | Operación | `after` admitido |
   |---|---|
   | `SetPitch` | `{"pitch"}` con una altura canónica, solo sobre notas |
   | `SetDuration` | `{"duration_beats"}` con una duración válida |
   | `SetAccidental` | `{"accidental"}`: `null`, `""`, `"natural"`, `"#"`, `"##"`, `"x"`, `"b"`, `"-"`, `"bb"` o `"--"`; solo sobre notas y con una altura resultante canónica |
   | `InsertEvent` | `{"kind": "note" \| "rest", "duration_beats"}`; una nota requiere `pitch`; opcionales `tie` (`start`, `continue`, `stop`; no en silencios), `is_chord` (booleano; no en silencios), `bbox` (cuatro números), `confidence` (de 0 a 1) y `voice` (igual a la del ancla) |
   | `DeleteEvent` | `null` |
   | `SetClef` | `{"sign": "G" \| "F" \| "C", "line": 1–5, "octave_change": -2–2}`; o `{"clef": ...}` con esa forma, un nombre (`"treble"`, `"bass"`, `"alto"`, `"tenor"` y sus equivalentes `"sol"`, `"fa"`, `"g"`, `"f"`, `"do3"`, `"c3"`, `"do4"`, `"c4"`) o `null` para quitar el cambio de clave del compás |
   | `SetKey` | `{"fifths": -7–7, "mode": null \| "major" \| "minor"}`; o `{"key_signature": ...}` o `{"key": ...}` con esa forma, con un entero de -7 a 7 o con `null` para quitar el cambio de armadura |

   - **Altura canónica:** letra mayúscula de la A a la G, alteración opcional (`#`, `##`, `b`,
     `bb`) y octava de 0 a 9, dentro del rango MIDI (0–127): `C#4`, `Bb3`.
   - **Duración válida:** número o fracción en texto (`2`, `0.5`, `"3/4"`), mayor que 0 y como
     mucho 16 pulsos (una longa), con denominador 2^a·t, t ∈ {1, 3, 5, 7} y como mucho 128. Un
     barrido de todas esas fracciones hasta 16 pulsos se exporta sin error a MusicXML y MIDI.
   - **Alteraciones de `SetAccidental`:** son las que la proyección y el plano offline
     (`DatasetBuilder`) interpretan igual. Alias como `"sharp"` o `"flat"` se rechazan en
     `after`.
   - Se rechazan los campos que la operación no usa y los valores de tipo inesperado (listas
     u objetos donde se espera texto, números que no caben en coma flotante).

2. **El servidor fija `before`** (`snapshot_before`) con una instantánea del estado sobre el que
   se aplica la edición, igual que fija el autor (ADR-0012). Si el cliente envía `before`, se
   sigue exigiendo que coincida con el estado (422 si no; las alteraciones se comparan
   normalizadas, así que `"natural"` coincide con una nota sin alteración); en ambos casos se
   guarda la instantánea del servidor:
   - `DeleteEvent`: el evento completo (`kind`, `pitch`, `duration_beats`, `tie`, `is_chord`,
     `bbox`, `confidence`).
   - `SetClef` y `SetKey`: la clave o la armadura del compás, o `null`.
   - `InsertEvent`: no hay estado previo.

3. **Deshacer exige un estado previo suficiente** (`has_complete_before`). Una edición guardada
   antes de esta decisión sin él se rechaza al deshacer con 422 en lugar de corromper la sesión.
   Para un `DeleteEvent` antiguo basta con `kind`, `pitch` y `duration_beats`; si su `before`
   no traía `tie`, `bbox` o `confidence`, el evento se reinserta sin ellos.

## Consecuencias

### Positivas
- Ninguna edición incoherente entra al log, y tampoco al plano offline, que consume las
  ediciones de sesiones finalizadas.
- Toda edición aceptada deja la sesión exportable a MusicXML y MIDI.
- Deshacer restaura el estado previo en las siete operaciones, envíe o no el cliente `before`.
  La única excepción es el `ir_handle` de un evento borrado, que `InsertEvent` no transporta;
  hoy ningún motor lo rellena.
- Los esquemas Pydantic y `docs/api/openapi.json` no cambian.

### Negativas
- Peticiones que antes se aceptaban ahora responden 422: además de los casos del contexto,
  `InsertEvent` sin `kind` (antes se trataba como nota), `DeleteEvent` con `after: {}`,
  alias de alteración en `after` y campos que la operación no usa.
- El `before` de la respuesta de una edición es la instantánea del servidor, no lo que envió
  el cliente.
- Las ediciones que ya estuvieran guardadas con un `after` inválido no se reescriben: el log es
  inmutable y deshacerlas sigue siendo posible si tienen estado previo suficiente.

## Alternativas consideradas

- **Exigir `before` completo al cliente (422 si falta).** Rechazada: obliga al frontend a
  reconstruir instantáneas que el servidor ya tiene y rompe a los clientes que hoy envían
  `before: null` en ediciones válidas.
- **Validar en el esquema Pydantic de la API.** Rechazada: `after` depende de la operación y
  del evento anclado (una altura no se aplica a un silencio), y cambiaría `openapi.json`.
- **Aceptar todo lo que el exportador sepa escribir.** Rechazada: music21 exporta sin error
  duraciones nulas o alturas como `C10`, que no son correcciones válidas.
