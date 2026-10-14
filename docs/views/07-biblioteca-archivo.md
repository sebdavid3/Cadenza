# Vista 07: Biblioteca / Archivo Histórico

- **Ruta Frontend:** `/library`
- **Acceso:** Protegido (requiere Bearer JWT de `transcriptor` o `investigador`)
- **Modo Impeccable:** `Read` / `Operate`

---

## 1. Propósito y Audiencia
Actúa como el repositorio permanente de partituras digitalizadas, validadas y cerradas (`closed`). Ofrece un catálogo de consulta de solo lectura para musicólogos, estudiantes y transcriptores que desean revisar obras terminadas, escuchar su reproducción o descargar los archivos finales sin riesgo de modificar accidentalmente los datos.

**Audiencia:** Transcriptores e investigadores consultando el acervo de partituras digitalizadas.

---

## 2. Contrato de API y Dependencias
- `GET /sessions?status=closed`: Filtra y lista únicamente las sesiones en estado cerrado/finalizado.
- `GET /sessions/{id}`: Consulta metadatos completos de la obra (compositor, instrumentación, fecha de digitalización, autor del transcriptor).
- `GET /sessions/{id}/export?format=musicxml|midi`: Descarga directa sin abrir el editor.

---

## 3. Anatomía Visual y Layout

```
+--------------------------------------------------------------------------------------------------+
| [Logo] cadenza  [Buscar en el archivo... Ctrl+K]      [● API Online]        admin (investigador) |
+--------------------------------------------------------------------------------------------------+
| BIBLIOTECA DE OBRAS DIGITALIZADAS                                        [ 28 Partituras Verificadas ]
|                                                                                                  |
| [Buscar por compositor, obra, tonalidad...                 ]  [Filtro: Época ▾] [Descargar Todo] |
+--------------------------------------------------------------------------------------------------+
| CATÁLOGO EN CUADRÍCULA (Cards de Archivo):                                                       |
|                                                                                                  |
| +-------------------------+ +-------------------------+ +-------------------------+              |
| | [ Miniatura Escaneo ]   | | [ Miniatura Escaneo ]   | | [ Miniatura Escaneo ]   |              |
| | J. S. Bach              | | W. A. Mozart            | | F. Chopin               |              |
| | Invención No. 8 en Fa M | | Sonata Facile K.545     | | Preludio Op. 28 No. 4   |              |
| | 18 compases · 2 voces   | | 72 compases · Piano     | | 25 compases · Mi menor  |              |
| | Finalizada: 14 Oct 2026 | | Finalizada: 12 Oct 2026 | | Finalizada: 08 Oct 2026 |              |
| | Transcriptor: sebdavid  | | Transcriptor: maria_r   | | Transcriptor: carlos_m  |              |
| |                         | |                         | |                         |              |
| | [XML] [MIDI] [Ver ➔]    | | [XML] [MIDI] [Ver ➔]    | | [XML] [MIDI] [Ver ➔]    |              |
| +-------------------------+ +-------------------------+ +-------------------------+              |
|                                                                                                  |
| Mostrando 1-3 de 28 obras cerradas                                            [Paginación: 1 2 3] |
+--------------------------------------------------------------------------------------------------+
```

---

## 4. Componentes y Funcionalidades

1. **Barra de Búsqueda y Filtros Facetados:**
   - Campo de búsqueda amplio con icono de lupa de trazo fino.
   - Filtros por:
     - Compositor (Bach, Mozart, Beethoven, etc.).
     - Tonalidad y compás (Fa Mayor, 4/4, 3/4).
     - Transcriptor responsable.
2. **Selector de Vista (Cards vs. Tabla):**
   - **Vista Cuadrícula (Recomendada):** Tarjetas de 280px con miniatura del manuscrito original, título en tipografía `Newsreader` y badge verde esmeralda `Verificada`.
   - **Vista Tabla:** Lista compacta para exportaciones masivas.
3. **Acciones Rápidas por Tarjeta:**
   - Botón `Descargar MusicXML` (icono XML).
   - Botón `Descargar MIDI` (icono MIDI).
   - Botón `Inspeccionar Partitura ➔` (abre visor de solo lectura).
4. **Visor de Partitura de Solo Lectura (Modal o pantalla dedicada):**
   - Muestra la partitura completa en OSMD con reproductor de audio Tone.js activo, pero sin paneles de edición ni botones de mutación, garantizando la integridad de la obra.

---

## 5. Estados de la Pantalla
- **Cargando:** Esqueletos de tarjetas con efecto de pulso sutil sobre `#1A1C22`.
- **Vacío:** Mensaje: *"Aún no se han finalizado partituras en este catálogo. Las obras aparecerán aquí una vez cerradas en el atril."*
- **Con Obras:** Cuadrícula fluida con espaciado de 16px.

---

## 6. Atajos de Teclado
- <kbd>Ctrl+K</kbd>: Búsqueda rápida en el catálogo.
- <kbd>/</kbd>: Coloca el cursor directamente en la caja de búsqueda.
- <kbd>Esc</kbd>: Limpia los filtros aplicados.

---

## 7. Anti-patrones Prohibidos en esta Vista
- **Prohibido:** Permitir la edición accidental de notas desde esta vista; es un archivo de lectura y preservación.
- **Prohibido:** Tarjetas con sombras de colores extravagantes o bordes iluminados.
