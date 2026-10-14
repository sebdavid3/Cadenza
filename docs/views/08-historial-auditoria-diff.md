# Vista 08: Historial de Auditoría y Diff

- **Ruta Frontend:** `/sessions/:id/history`
- **Acceso:** Protegido (requiere Bearer JWT de `investigador` o el `transcriptor` propietario)
- **Modo Impeccable:** `Read` / `Operate`

---

## 1. Propósito y Audiencia
Proporciona la trazabilidad científica de una sesión de transcripción. Permite auditar el log inmutable *append-only* de todas las operaciones realizadas, visualizar quién hizo cada cambio, cuándo ocurrió y examinar un comparador diferencial (*Diff*) que contrasta el estado del OMR original crudo frente a las correcciones humanas.

**Audiencia:** Investigadores evaluando la fidelidad de las transcripciones y transcriptores revisando su propio historial de intervenciones.

---

## 2. Contrato de API y Dependencias
- `GET /sessions/{id}`: Consulta los metadatos y el log completo de ediciones (`edits`).
- Cada evento del log incluye:
  ```json
  {
    "seq": 14,
    "base_seq": 13,
    "op": "SetPitch",
    "author": "sebdavid",
    "timestamp": "2026-10-14T15:20:12Z",
    "anchor": {"part": 0, "staff": 0, "measure": 3, "voice": 0, "order": 2},
    "before": {"pitch": "F4", "duration": "1/4"},
    "after": {"pitch": "F#4", "duration": "1/4"}
  }
  ```

---

## 3. Anatomía Visual y Layout

```
+--------------------------------------------------------------------------------------------------+
| [Logo] cadenza  AUDITORÍA FORENSE: Sesión #8a3f · Bach Invención 8          [← Volver al Atril]  |
+--------------------------------------------------------------------------------------------------+
| RESUMEN DE TRAZABILIDAD:                                                                         |
| Total de Ediciones: 14   |   Autores: sebdavid (14)   |   Concurrencia: Sin conflictos detectados|
+--------------------------------------------------------------------------------------------------+
| PANELES EN PARALELO (Split 40/60):                                                               |
|                                                                                                  |
| LÍNEA DE TIEMPO APPEND-ONLY (40%)        | COMPARADOR DIFF ESTRUCTURAL (60%)                     |
|                                          |                                                       |
| [Filtro: Operación ▾] [Autor: Todos ▾]   | Evento #14: SetPitch en compás 3 · voz 1              |
|                                          | Autor: sebdavid · 14 Oct 2026 15:20:12               |
| • #14 SetPitch (F4 ➔ F#4)                | ───────────────────────────────────────────────────── |
|   c.3:v.1:o.2 · sebdavid · hace 5m       | ESTADO PREVIO (Before):      ESTADO RESULTANTE (After):|
|                                          |                                                       |
| • #13 SetDuration (1/8 ➔ 1/4)            |   {                          {                        |
|   c.3:v.1:o.1 · sebdavid · hace 6m       | -   "pitch": "F4",       +   "pitch": "F#4",          |
|                                          |     "duration": "1/4",          "duration": "1/4",    |
| • #12 DismissFinding                     |     "staff": 0,                 "staff": 0,           |
|   c.2:v.1 · Falso positivo métrica       |     "measure": 3                "measure": 3          |
|                                          |   }                          }                        |
| • #11 InsertEvent (Silencio de negra)    |                                                       |
|   c.1:v.0:o.0 · sebdavid · hace 12m      | [ Visualizador Gráfico: Compás 3 antes vs después ]   |
+--------------------------------------------------------------------------------------------------+
```

---

## 4. Componentes y Funcionalidades

1. **Línea de Tiempo Cronológica Inmutable (Panel Izquierdo):**
   - Lista ordenada de eventos de edición (del más reciente al más antiguo).
   - Cada entrada muestra:
     - Número de secuencia (`seq`) y secuencia base (`base_seq`).
     - Tipo de operación con badge en píldora (`SetPitch`, `SetDuration`, etc.).
     - Coordenadas del ancla (`m.3:v.1`).
     - Nombre de usuario del autor fijado por el servidor ([ADR-0012](../../docs/adr/ADR-0012-autenticacion-e-identidad.md)).
     - Marca temporal relativa (*"hace 4 min"*) y absoluta al pasar el ratón.
2. **Comparador Diff Estructural (Panel Derecho):**
   - Vista de código en dos columnas (*side-by-side*) con tipografía `Geist Mono` o `JetBrains Mono`:
     - Columna izquierda en rojo semántico suave (`#DC2626` a 10% de opacidad) mostrando los atributos eliminados o modificados (`before`).
     - Columna derecha en verde esmeralda suave (`#10B981` a 10% de opacidad) mostrando los atributos aplicados (`after`).
3. **Mini-Atril de Comparación Notacional:**
   - Renderiza un fragmento gráfico SVG del compás específico antes y después de la edición para que el cambio sea inmediatamente comprensible sin leer JSON crudo.
4. **Filtro de Operaciones:**
   - Permite filtrar el historial para ver únicamente cambios de altura, cambios rítmicos o descartes de hallazgos.

---

## 5. Estados de la Pantalla
- **Cargando:** Esqueleto vertical de línea de tiempo con nodos titilantes.
- **Sin Ediciones (Sesión Prístina):** Mensaje: *"Esta sesión no ha recibido intervenciones humanas. El documento se conserva exactamente como lo generó el motor OMR."*
- **Con Ediciones:** Selección activa del evento con borde cobalto de 1px.

---

## 6. Atajos de Teclado
- <kbd>Flecha Arriba / Abajo</kbd>: Desplaza la selección por la lista de eventos.
- <kbd>Enter</kbd>: Carga el diff del evento seleccionado en el panel derecho.
- <kbd>Esc</kbd>: Vuelve al atril de edición.

---

## 7. Anti-patrones Prohibidos en esta Vista
- **Prohibido:** Permitir la edición o eliminación de eventos en esta vista; el log es append-only e inmutable por diseño arquitectónico ([ADR-0007](../../docs/adr/ADR-0007-edit-events-inmutables.md)).
- **Prohibido:** Ocultar el autor o la marca de tiempo de una edición.
