# Vista 11: Centro de Datasets y Modelos (Offline)

- **Ruta Frontend:** `/admin/datasets`
- **Acceso:** Restringido (exclusivo para usuarios con rol `investigador`)
- **Modo Impeccable:** `Operate`

---

## 1. Propósito y Audiencia
Conecta el plano de cómputo online (la API web y el atril de corrección) con el **plano offline de aprendizaje automático** ([ADR-0003](../../docs/adr/ADR-0003-separacion-planos-computo.md) y [ADR-0008](../../docs/adr/ADR-0008-active-learning-model-registry.md)). Permite a los investigadores supervisar el crecimiento del dataset acumulado de partituras corregidas, seleccionar muestras de mayor incertidumbre mediante aprendizaje activo (*Active Learning*) y registrar/promocionar versiones reentrenadas del modelo OMR.

**Audiencia:** Investigadores en aprendizaje profundo e inteligencia artificial musical.

---

## 2. Contrato de API y CLI Offline
- La comunicación online/offline se realiza mediante persistencia en base de datos y el paquete `packages/learning`.
- CLI Offline (`cadenza-ml`):
  - `python -m ml build-dataset`: Genera tripletas de entrenamiento a partir de sesiones finalizadas (`image`, `ground_truth_score`, `edit_log`).
  - `python -m ml select`: Ejecuta estrategias de adquisición de aprendizaje activo (muestras con mayor número de correcciones humanas).
  - `python -m ml promote`: Registra una nueva versión de modelo para el motor OMR.

---

## 3. Anatomía Visual y Layout

```
+--------------------------------------------------------------------------------------------------+
| [Logo] cadenza  PLANO OFFLINE: DATASETS Y APRENDIZAJE ACTIVO                admin (investigador) |
+--------------------------------------------------------------------------------------------------+
| GESTIÓN DEL DATASET DE REENTRENAMIENTO                                   [ Empaquetar Dataset ]  |
|                                                                                                  |
| [ Muestras Anotadas: 342 ]   [ Nuevas Correcciones: 48 ]   [ Modelo Activo: HOMR v1.2 (Prod) ]   |
+--------------------------------------------------------------------------------------------------+
| SESIONES FINALIZADAS DISPONIBLES PARA APRENDIZAJE ACTIVO:                                        |
|                                                                                                  |
| SELECCIONAR   SESIÓN      OBRA               CORRECCIONES   DISCREPANCIA OMR  ESTRATEGIA         |
| ──────────────────────────────────────────────────────────────────────────────────────────────── |
| [x]           #8a3f01     Bach · Inv. 8      12 edits       Alta (3 alertas)  Incertidumbre (AL) |
| [x]           #4b8a11     Chopin · Preludio  18 edits       Muy Alta (8 err)  Mayor Corrección   |
| [ ]           #7c1e92     Mozart · K.545     2 edits        Baja (0 err)      Bajo Valor         |
| ──────────────────────────────────────────────────────────────────────────────────────────────── |
| 2 sesiones seleccionadas para el próximo ciclo de fine-tuning (#103)                             |
+--------------------------------------------------------------------------------------------------+
| REGISTRO DE MODELOS OMR (Model Registry):                                                        |
|                                                                                                  |
| VERSIÓN       FECHA REGISTRO     MOTOR BASE     OMR-NED      SER        ESTADO                   |
| ──────────────────────────────────────────────────────────────────────────────────────────────── |
| homr_v1.2.onnx 01 Oct 2026       HOMR ResNet-18 0.082        14.2%      [ Activo en Producción ] |
| homr_v1.1.onnx 15 Sep 2026       HOMR Baseline  0.114        19.8%      [ Archivado            ] |
| fake_v1.0      01 Sep 2026       Sintético      0.000        0.0%       [ Pruebas / Dev        ] |
+--------------------------------------------------------------------------------------------------+
```

---

## 4. Componentes y Funcionalidades

1. **Monitor de Acumulación de Datos:**
   - Contador de sesiones finalizadas aptas para el pipeline de aprendizaje.
   - Indicador del modelo activo en producción en la API (`HOMREngine`).
2. **Tabla de Selección de Muestras (Active Learning):**
   - Lista interactiva de partituras cerradas con casillas de verificación.
   - Puntuación de discrepancia: destaca las partituras donde el transcriptor tuvo que hacer más correcciones manuales, ya que son las que contienen el mayor valor informativo para reentrenar la red neuronal.
   - Botón de acción: `Empaquetar Dataset para Entrenamiento ➔`.
3. **Registro de Modelos OMR (Model Registry):**
   - Tabla que audita los pesos y archivos ONNX registrados en el sistema.
   - Métricas estándar de evaluación:
     - `OMR-NED` (Distancia de Edición Normalizada OMR).
     - `SER` (Tasa de Error de Símbolos).
   - Botón `Promover a Producción` (asigna el modelo para ser servido por la API).

---

## 5. Estados de la Pantalla
- **Sin Muestras Nuevas:** Estado con mensaje: *"Todas las sesiones finalizadas ya forman parte del dataset base."*
- **Entrenamiento en Proceso:** Indicador de ejecución del job offline en el contenedor con GPU (`docker compose --profile batch`).
- **Éxito:** Muestra el hash SHA-256 del paquete de dataset generado.

---

## 6. Atajos de Teclado
- <kbd>Ctrl+A</kbd>: Selecciona todas las sesiones con alta discrepancia.
- <kbd>Esc</kbd>: Regresa al Dashboard.

---

## 7. Anti-patrones Prohibidos en esta Vista
- **Prohibido:** Ocultar el hash SHA-256 o la versión de los modelos; la reproducibilidad de la tesis exige trazabilidad exacta de pesos.
- **Prohibido:** Gráficos de "entrenamiento con IA mágica" que simulen convergencia sin datos reales del plano offline.
