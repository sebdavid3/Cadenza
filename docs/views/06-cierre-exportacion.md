# Vista 06: Resumen de Cierre y Exportación

- **Ruta Frontend:** `/sessions/:id/finalize` (o modal integrado en `/sessions/:id`)
- **Acceso:** Protegido (requiere Bearer JWT de `transcriptor` o `investigador`)
- **Modo Impeccable:** `Operate`

---

## 1. Propósito y Audiencia
Formaliza el cierre de una sesión de transcripción. Presenta el balance final del trabajo realizado, envía la telemetría de esfuerzo cognitivo al backend (`POST /effort`), finaliza la sesión (`POST /finalize`) y ofrece la descarga directa de los artefactos musicales validados (MusicXML 4.0 y MIDI 1.0 estándar).

**Audiencia:** Transcriptores terminando su jornada de digitalización e investigadores recopilando datos de evaluación.

---

## 2. Contrato de API y Dependencias
- `POST /sessions/{id}/effort`:
  - **Payload:** `{"duration_seconds": float, "first_edit_latency_seconds": float, "interventions_per_measure": float, "total_edits": int}`.
  - Registra las métricas de esfuerzo cognitivo para el estudio científico.
- `POST /sessions/{id}/finalize`:
  - Cambia el estado de la sesión de `in_progress` a `closed`.
  - Impide nuevas ediciones directas (responde `409 SessionClosed` ante nuevos `POST /edits`).
- `GET /sessions/{id}/export?format=musicxml`: Descarga el archivo de notación editable listo para Sibelius, Finale o MuseScore.
- `GET /sessions/{id}/export?format=midi`: Descarga el archivo MIDI para secuenciadores o DAW.

---

## 3. Anatomía Visual y Layout

```
+--------------------------------------------------------------------------------------------------+
| RESUMEN DE FINALIZACIÓN EDITORIAL                                                [ Cerrar (Esc)] |
| Sesión #8a3f · Bach Invención No. 8 en Fa Mayor (18 compases)                                    |
+--------------------------------------------------------------------------------------------------+
|                                                                                                  |
| [ RESUMEN DE ESFUERZO COGNITIVO ]                                                                |
|                                                                                                  |
|   Tiempo Total de Sesión:           04m 32s                                                      |
|   Latencia hasta Primera Edición:   14.8s                                                        |
|   Total de Correcciones Humanas:    12 intervenciones                                            |
|   Densidad de Corrección:           0.66 ediciones / compás                                      |
|   Hallazgos Resueltos:              3 de 3 advertencias subsanadas                               |
|                                                                                                  |
+--------------------------------------------------------------------------------------------------+
| DESCARGA DE ARTEFACTOS VALIDADOS:                                                                |
|                                                                                                  |
|  +-------------------------------------+  +------------------------------------+                 |
|  | [ Icono Partitura XML ]             |  | [ Icono MIDI ]                     |                 |
|  | Partitura MusicXML 4.0              |  | Archivo MIDI 1.0 Estándar          |                 |
|  | Para MuseScore, Sibelius, Dorico    |  | Para DAWs, sintetizadores y audio  |                 |
|  | bach_invention_08_corregido.musicxml|  | bach_invention_08.mid              |                 |
|  | [ Descargar MusicXML ➔ ]            |  | [ Descargar MIDI ➔ ]               |                 |
|  +-------------------------------------+  +------------------------------------+                 |
|                                                                                                  |
+--------------------------------------------------------------------------------------------------+
| ACCIÓN FINAL:                                                                                    |
| [ Deseo continuar editando ]                 [ Confirmar y Cerrar Sesión Definitivamente (⌘↵) ]  |
+--------------------------------------------------------------------------------------------------+
```

---

## 4. Componentes y Funcionalidades

1. **Encabezado del Diálogo:**
   - Título formal en `Newsreader` o `Geist Sans` semibold: *«Finalización y Cierre de Sesión»*.
   - Metadatos de la obra (título, compositor, número de compases y autor).
2. **Tarjeta de Métricas de Esfuerzo (Telemetría HITL):**
   - Superficie `#141519` con borde de 1px.
   - Datos numéricos renderizados en fuente monoespaciada con cifras tabulares (`tabular-nums`):
     - Tiempo de sesión activo en minutos y segundos.
     - Latencia de inspección inicial (tiempo transcurrido entre la carga de la partitura y la primera pulsación de tecla).
     - Desglose de operaciones realizadas (`SetPitch`, `SetDuration`, etc.).
3. **Módulo de Descarga Directa de Archivos:**
   - Dos tarjetas simétricas de descarga con botones de acento azul cobalto `#2563EB`:
     - **MusicXML 4.0:** Archivo XML estructurado con la ortografía musical exacta.
     - **MIDI 1.0:** Archivo con mapa de velocidades, pistas de voz y tempo de 120 BPM.
4. **Botón Primario de Cierre Definitivo:**
   - Botón blanco puro `#FFFFFF` de alto contraste: `Confirmar y Cerrar Sesión ➔`.
   - Llama en secuencia a `POST /effort` y `POST /finalize`.
   - Muestra confirmación exitosa con badge verde esmeralda y redirige al Dashboard (`/dashboard`).

---

## 5. Estados de la Pantalla
- **Revisión Previa:** Muestra el balance y permite descargar sin cerrar aún.
- **Enviando Cierre:** Botón en estado cargando mientras la API procesa la finalización.
- **Cierre Confirmado:** Mensaje de felicitación: *"Sesión guardada en el archivo histórico"*.
- **Error:** Si la API devuelve un fallo de persistencia, permite reintentar el guardado sin perder los archivos descargables.

---

## 6. Atajos de Teclado
- <kbd>Esc</kbd>: Vuelve al atril de edición sin cerrar la sesión.
- <kbd>Ctrl+Enter</kbd> / <kbd>⌘+Enter</kbd>: Dispara la confirmación y cierre definitivo.
- <kbd>Ctrl+D</kbd>: Descarga directa del archivo MusicXML.

---

## 7. Anti-patrones Prohibidos en esta Vista
- **Prohibido:** Animaciones de confeti, globos o fuegos artificiales de videojuego; es una herramienta de transcripción científica profesional.
- **Prohibido:** Forzar la descarga antes de enviar la telemetría de esfuerzo al backend.
- **Prohibido:** Gráficos circulares de "eficiencia del 98%"; mostrar las cifras reales medidas en segundos y compases.
