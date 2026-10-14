# Vista 05: Banco de Trabajo HITL (Atril Dual)

- **Ruta Frontend:** `/sessions/:id`
- **Acceso:** Protegido (requiere Bearer JWT de `transcriptor` o `investigador`; un transcriptor solo accede a sus propias sesiones)
- **Modo Impeccable:** `Operate`

---

## 1. Propósito y Audiencia
Es el **corazón operativo** de Cadenza. Proporciona el entorno de trabajo asistido (*Human-in-the-Loop*) donde el transcriptor compara la partitura escaneada original con la notación musical digital renderizada (OSMD), examina las advertencias sintácticas del validador de reglas, corrige eventos musicales con atajos de teclado y verifica la música auditivamente mediante síntesis con Tone.js.

**Audiencia:** Transcriptores musicales (operación intensiva de teclado) e investigadores supervisores.

---

## 2. Contrato de API y Dependencias
- `GET /sessions/{id}`: Obtiene el estado integral de la sesión: metadatos, estado (`in_progress`, `closed`), resumen de hallazgos y log de ediciones.
- `GET /sessions/{id}/image`: Retorna el blob binario de la imagen escaneada original para el visor izquierdo.
- `GET /sessions/{id}/export?format=musicxml`: Obtiene el MusicXML canónico actualizado para el renderizador vectorial OSMD.
- `GET /sessions/{id}/findings`: Lista de anomalías sintácticas reportadas por el validador con ancla (`part`, `staff`, `measure`, `voice`, `order`), severidad y regla violada.
- `POST /sessions/{id}/findings/{finding_id}/dismiss`: Descarta un hallazgo que el transcriptor considera un falso positivo.
- `POST /sessions/{id}/findings/{finding_id}/restore`: Restaura un hallazgo descartado previamente.
- `POST /sessions/{id}/validate`: Dispara la revalidación manual del motor de reglas tras una serie de ediciones.
- `POST /sessions/{id}/edits`:
  - **Payload estricto (ADR-0017):** `{"base_seq": int, "op": "SetPitch"|"SetDuration"|"SetAccidental"|"DeleteEvent"|"InsertEvent", "anchor": {...}, "after": {...}}`.
  - **Respuesta 200:** Evento persistido con `seq` incrementado y `before` capturado por el servidor.
  - **Respuesta 409:** Conflicto de concurrencia optimista (`base_seq` desfasado).
  - **Respuesta 422:** Edición inválida según gramática musical.
- `POST /sessions/{id}/undo`: Deshace la última edición en el servidor, restaurando el snapshot exacto previo.
- `GET /sessions/{id}/timing`: Obtiene el mapa de tiempo determinista en fracciones de pulso (`duration_beats`, `offset_beats`) para la sincronización con Tone.js.

---

## 3. Anatomía Visual y Layout (Dual-Canvas Workbench)

```
+--------------------------------------------------------------------------------------------------+
| [Logo] cadenza  #8a3f · Bach Invención 8   [HOMR GPU]  [↶ Deshacer] [↷ Rehacer] [F5 Revalidar]   | [Finalizar ⌘↵]
+--------------------------------------------------------------------------------------------------+
| PANEL IZQ (300px)   | LIENZO CENTRAL: ATRIL DUAL (Split 50/50 Ajustable)    | PANEL DERECHO (320px)      |
|                     |                                                       |                            |
| ◉ Hallazgos (3)     | +------------------------+--------------------------+ | 🎛 Inspector de Evento     |
|   [Filtro: Todos ▾] | | ESCANEO FUENTE (PNG)   | NOTACIÓN VECTORIAL (OSMD)| | Nota Seleccionada          |
|                     | |                        |                          | | Compás 3 · Voz 1 · Pos 2.0 |
| ⚠ m.3: Duración 5/4 | | [ Controles de Zoom ]  | [ Compás 1 ] [ Compás 2 ]| |                            |
|   Excede compás 4/4 | | [ + ] [ - ] [ 100% ]   |                          | | Altura: [ F#4          ]   |
|   [Ocultar] [Saltar]| |                        | [ Compás 3 (Ámbar) ]     | | Alteración: [ Sostenido ▾] |
|                     | |                        |   ♩   ♪   [ 𝅗𝅥 Azul ]    | | Duración: [ Negra (1/4) ▾] |
| ⚠ m.7: Alteración   | |                        |                          | | Voz: [ 1 ▾] Clave: [ Sol ] |
|   Choque armadura   | |                        |                          | |                            |
|   [Ocultar] [Saltar]| |                        |                          | | Paleta Rítmica Rápida      |
|                     | |                        |                          | | [𝅝 1] [𝅗𝅥 2] [♩ 4] [♪ 8]    |
| ☰ Historial Edits   | |                        |                          | |                            |
|   #12 SetPitch F#4  | |                        |                          | | [ Eliminar Evento (Del) ]  |
+---------------------+--------------------------+--------------------------+----------------------------+
| BARRA DE TRANSPORTE DE AUDIO (Tone.js - 44px fija):                                                      |
| [ ▶ Play (Espacio) ] [ ■ Stop ]   [ 00:18.42 / 01:42.00 ]   [ Tempo BPM: 120 ━━━━●━━ ]   [ Compás 3:2 ]  |
+--------------------------------------------------------------------------------------------------+
```

---

## 4. Componentes y Funcionalidades Detalladas

1. **Header de Comandos (48px):**
   - Nombre de la obra y selector de sesión.
   - Badge de motor activo: `HOMR Engine · GPU Inferencia`.
   - Botón `Deshacer` con chip <kbd>Ctrl+Z</kbd> (llama a `POST /undo` en servidor).
   - Botón `Rehacer` con chip <kbd>Ctrl+Y</kbd>.
   - Botón `Revalidar` con chip <kbd>F5</kbd> (llama a `POST /validate` y actualiza hallazgos).
   - Botón primario: Blanco puro `#FFFFFF` con texto negro semibold: `Finalizar Sesión ➔` con chip <kbd>⌘↵</kbd> (abre modal de cierre).
2. **Panel Lateral Izquierdo — Hallazgos y Lista de Corrección (300px):**
   - Cabecera con contador tabular: `Hallazgos · 3`.
   - Filtro rápido por tipo de regla: `Todos`, `Métrica/Ritmo`, `Armadura/Tonalidad`.
   - Tarjetas de hallazgos compactas con barra semántica izquierda (rojo para error de compás, ámbar para advertencia).
   - Botón directo `Saltar`: centra el compás en OSMD y enfoca la nota afectada.
   - Botón `Descartar (Ojo tachado)`: llama a `POST /dismiss`.
   - Pestaña inferior colapsable con el historial de ediciones recientes.
3. **Lienzo Central Dividido — El Atril Dual (Flex 1):**
   - **Lado Izquierdo — Visor de Escaneo Fuente:**
     - Renderiza la imagen original cargada desde `GET /sessions/{id}/image`.
     - Controles flotantes HUD discretos de zoom (25% a 400%), centrado y modo 1:1.
     - Nota crítica de motor real: con `HOMR`, no se dibujan cajas delimitadoras flotantes (INV-0001, `bbox: null`); actúa como referencia visual pura en alta definición.
   - **Lado Derecho — Notación Vectorial Viva (OSMD):**
     - Renderiza la partitura vectorial en fondo blanco puro `#FFFFFF` con tinta carbón `#0F172A`.
     - **Selección interactiva:** Al hacer clic en cualquier nota, se colorea con contorno azul cobalto `#2563EB` y actualiza el Inspector.
     - **Resaltado de anomalías:** Los compases con hallazgos activos muestran un tinte ámbar suave de fondo (`#FEF3C7`).
     - **Cursor de audio:** Una línea vertical azul avanza sincronizada compás a compás durante la reproducción.
4. **Panel Lateral Derecho — Inspector de Eventos Musicales (320px):**
   - Muestra las coordenadas exactas del evento seleccionado: compás, pentagrama, voz y orden.
   - Formulario de edición quirúrgica (ADR-0017):
     - Campo de texto de altura canónica con validación en tiempo real (`A`-`G` con alteraciones `#`, `b`, `n` y octava 1–8).
     - Selector de figura rítmica con botones directos: Redonda (1), Blanca (2), Negra (4), Corchea (8), Semicorchea (16), Fusa (32) y silencios.
     - Botón de alteración accidental (`Sostenido`, `Bemol`, `Becuadro`).
     - Botón destructivo sobrio: `Eliminar Nota (Delete)` que envía `DeleteEvent` con `after: null`.
5. **Barra de Transporte de Audio Inferior (44px fija):**
   - Anclada al borde inferior de la ventana (nunca flota tapando la música).
   - Botón Play/Pausa con señalización <kbd>Espacio</kbd>.
   - Barra de progreso interactiva para mover la posición de reproducción (*scrubbing*).
   - Control continuo de tempo (BPM: 40 a 240) con actualización reactiva en Tone.js.
   - Cifras tabulares monoespaciadas para el tiempo transcurrido y compás actual.

---

## 5. Estados de la Pantalla
- **Cargando:** Spinner técnico mientras se obtienen la imagen, el MusicXML y los hallazgos en paralelo.
- **Modo Edición Normal:** Interfaz completamente reactiva. Cada edición (`POST /edits`) actualiza el estado local y regenera el MusicXML en OSMD en menos de 100ms.
- **Conflicto de Concurrencia (409 Conflict):** Si otro proceso o pestaña modificó la secuencia, aparece un toast informativo: *"Sesión desfasada. Sincronizando último estado..."* y recarga automáticamente sin perder el trabajo.
- **Edición Inválida (422):** Alerta contextual debajo del input de altura explicando la regla rota (ej. *"La figura excede la capacidad restante del compás"*).
- **Sesión Cerrada (`closed`):** Si la sesión ya fue finalizada, la interfaz pasa a modo lectura (*read-only*) con banner superior que permite a un investigador reabrirla.

---

## 6. Atajos de Teclado del Transcriptor
- <kbd>Espacio</kbd>: Reproducir / Pausar audio.
- <kbd>Ctrl+Z</kbd>: Deshacer edición en servidor.
- <kbd>Ctrl+Y</kbd>: Rehacer edición.
- <kbd>F5</kbd>: Revalidar reglas musicales.
- <kbd>Flecha Izquierda / Derecha</kbd>: Seleccionar nota anterior / siguiente.
- <kbd>A</kbd>, <kbd>B</kbd>, <kbd>C</kbd>, <kbd>D</kbd>, <kbd>E</kbd>, <kbd>F</kbd>, <kbd>G</kbd>: Fijar altura musical de la nota seleccionada.
- <kbd>1</kbd>, <kbd>2</kbd>, <kbd>4</kbd>, <kbd>8</kbd>: Cambiar duración a redonda, blanca, negra, corchea.
- <kbd>+</kbd> / <kbd>-</kbd>: Subir o bajar una octava.
- <kbd>Delete</kbd> / <kbd>Backspace</kbd>: Eliminar evento musical.
- <kbd>⌘+Enter</kbd> / <kbd>Ctrl+Enter</kbd>: Abrir diálogo de finalización de sesión.

---

## 7. Anti-patrones Prohibidos en esta Vista
- **Prohibido:** Halos borrosos de neón o destellos en la nota seleccionada; la selección debe ser vectorial nítida.
- **Prohibido:** Reproductor de audio flotante en medio de la pantalla tapando los compases.
- **Prohibido:** Falsos medidores de confianza de OCR en los hallazgos.
- **Prohibido:** Unidades acústicas físicas como hercios (`Hz`) o nombres de archivos de audio (`.wav`) en el inspector.
