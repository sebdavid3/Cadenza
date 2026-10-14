# Vista 04: Ingesta y Nueva Partitura

- **Ruta Frontend:** `/transcribe`
- **Acceso:** Protegido (requiere Bearer JWT de `transcriptor` o `investigador`)
- **Modo Impeccable:** `Operate`

---

## 1. Propósito y Audiencia
Punto de entrada de nuevos documentos a la plataforma. Permite cargar una imagen de partitura escaneada o fotografiada, configurar el motor OMR deseado y los pasos de preprocesamiento, supervisar la inferencia del modelo y generar una nueva sesión de trabajo.

**Audiencia:** Transcriptores e investigadores iniciando un nuevo trabajo de digitalización.

---

## 2. Contrato de API y Dependencias
- `POST /transcribe`:
  - **Tipo de Carga:** `multipart/form-data`.
  - **Parámetros:**
    - `file`: Archivo binario de imagen (PNG, JPEG, tamaño máx. 20 MB).
    - `omr_engine`: Opcional (`homr`, `oemer`, `fake`; por defecto usa la configuración del servidor).
    - `test_score_id`: Opcional (para pruebas con partituras sintéticas predefinidas).
  - **Respuesta 200 síncrona:**
    ```json
    {
      "session_id": "uuid-v4",
      "document_id": "uuid-v4",
      "omr_engine": "homr",
      "findings_count": 4,
      "condition": "baseline",
      "test_score_id": null
    }
    ```
  - **Respuesta 413:** Archivo excede el límite de 20 MB (`CADENZA_MAX_UPLOAD_SIZE_BYTES`).
  - **Respuesta 422:** Archivo no válido o formato de imagen corrupto.
- Tras recibir el `session_id`, la interfaz redirige automáticamente al **Atril Dual HITL** (`/sessions/{session_id}`).

---

## 3. Anatomía Visual y Layout

```
+--------------------------------------------------------------------------------------------------+
| [Logo] cadenza    [← Volver al Dashboard]       [● API Online]           admin (investigador)    |
+--------------------------------------------------------------------------------------------------+
| NUEVA DIGITALIZACIÓN DE PARTITURA                                                                |
|                                                                                                  |
| +--------------------------------------------------+  +----------------------------------------+ |
| | ZONA DE CARGA DE IMAGEN (Dropzone)               |  | CONFIGURACIÓN DE INFERENCIA            | |
| |                                                  |  |                                        | |
| |    [ Icono de Partitura en Línea Fina ]          |  | Motor OMR                              | |
| |                                                  |  | (•) HOMR (Red Neuronal End-to-End GPU) | |
| |    Arrastra la imagen de la partitura aquí       |  | ( ) oemer (Línea Base Multietapa)      | |
| |    o pulsa para explorar archivos                |  | ( ) FakeOMR (Motor de Pruebas Rápido)  | |
| |                                                  |  |                                        | |
| |    Formatos admitidos: PNG, JPEG, TIFF (máx 20MB)|  | Parámetros de Preprocesamiento         | |
| |                                                  |  | [x] Binarización adaptativa            | |
| |    [ previsualización de imagen si se carga ]    |  | [x] Enderezado de pentagramas (Deskew) | |
| |                                                  |  | [x] Reescalado a 300 DPI               | |
| |                                                  |  |                                        | |
| |                                                  |  | [ Iniciar Transcripción OMR ➔ ]        | |
| +--------------------------------------------------+  +----------------------------------------+ |
|                                                                                                  |
| [ESTADO DE PROCESAMIENTO / MONITOR TÉCNICO]:                                                     |
| [━━━━●━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━] 35%                                                      |
| Inferencia HOMR en GPU... Detectando compases y figuras rítmicas (latencia esperada: 1.2s - 4.5s) |
+--------------------------------------------------------------------------------------------------+
```

---

## 4. Componentes y Funcionalidades

1. **Dropzone de Archivos:**
   - Área de carga interactiva amplia con borde discontinuo sutil `1px dashed rgba(255, 255, 255, 0.16)`.
   - Soporte para arrastrar y soltar (*drag & drop*) o selección mediante diálogo del sistema operativo.
   - Validación en cliente antes del envío: verifica tipo MIME y tamaño menor a 20 MB.
   - Al soltar la imagen: muestra miniatura nítida con metadatos del archivo (nombre, dimensiones en píxeles y peso en MB) y botón `Reemplazar imagen`.
2. **Panel de Configuración de Inferencia:**
   - Selector de motor OMR mediante botones de radio segmentados:
     - `HOMR (Recomendado)` con badge `GPU Activa` si está disponible.
     - `oemer` (motor de comparación y línea base).
     - `FakeOMR` (modo de prueba instantáneo para desarrollo).
   - Opciones de preprocesamiento de imagen con interruptores (*toggles*) sobrios de 1px.
3. **Botón Primario de Inferencia:**
   - Blanco puro `#FFFFFF` con texto `#0C0D0F`, radio `6px`: `Iniciar Transcripción OMR ➔`.
4. **Monitor Técnico de Procesamiento (Inferencia en curso):**
   - Muestra una barra de progreso limpia con cifras tabulares.
   - Mensaje técnico no invasivo: *"Ejecutando inferencia neuronal sobre GPU... aplicando validación musical de compases..."*.
   - No muestra animaciones superfluas; mantiene al usuario informado de la latencia real (entre 0.7s y 5.0s según documento).

---

## 5. Estados de la Pantalla
- **Reposo:** Dropzone vacía esperando imagen. Botón de inicio deshabilitado.
- **Imagen Seleccionada:** Previsualización del manuscrito activa, botón de inicio habilitado.
- **Procesando:** Botón en estado de carga (*spinner* técnico monoespaciado), barra de progreso activa.
- **Error de Archivo:** Si supera los 20 MB o el formato no es válido, mensaje en caja roja semántica `#DC2626`.
- **Éxito:** Redirección inmediata sin parpadeo a `/sessions/{session_id}`.

---

## 6. Atajos de Teclado
- <kbd>Ctrl+O</kbd>: Abre el explorador de archivos para seleccionar imagen.
- <kbd>Enter</kbd>: Dispara la transcripción si hay un archivo cargado.
- <kbd>Esc</kbd>: Cancela la carga o vuelve al Dashboard.

---

## 7. Anti-patrones Prohibidos en esta Vista
- **Prohibido:** Efectos de rayos láser o escaners cyberpunk ficticios moviéndose sobre la imagen.
- **Prohibido:** Falsos porcentajes de "IA pensando 97%" que no correspondan a la ejecución real de `POST /transcribe`.
- **Prohibido:** Botones con iconos de destellos (✨) tipo "Magia de IA".
