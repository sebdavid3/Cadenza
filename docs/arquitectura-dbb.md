# Arquitectura General y Diagrama de Bloques de Construcción (DBB)

Este documento describe la arquitectura de software extremo a extremo (E2E) de la plataforma **Cadenza** con la metodología de **Diagramas de Bloques de Construcción (DBB)**, estructurada en niveles de detalle (caja negra, caja blanca y flujo de proceso).

Es la **vista de bloques** de la arquitectura objetivo. El diseño técnico vigente —decisiones, organización de los datos, catálogo de funciones y estado de implementación— está en [`ARCHITECTURE.md`](ARCHITECTURE.md) (v1.2); ante cualquier diferencia, prevalece ese documento.

> **Diagramas:** escritos en [D2](https://d2lang.com/). Para renderizarlos, copiar el bloque `d2` a un archivo `.d2` y ejecutar `d2 archivo.d2` (o usar el [playground](https://play.d2lang.com)). El orden es determinista: el Nivel 2 usa `grid-columns`/`grid-rows` y el Nivel 3 es un diagrama de secuencia con **aristas rectas** (layout ELK con `layered.edgeRouting: "ORTHOGONAL"`), donde cada mensaje ocupa su propia fila — sin texto superpuesto. **Importante:** D2 no resuelve nombres cortos de nodos anidados — clases y aristas usan SIEMPRE la ruta completa (p. ej. `flujo.etapa1.UI`), o se crean nodos duplicados.

---

## 1. Nivel 1: Contexto del Sistema (Caja Negra)

En este nivel de abstracción más alto, la plataforma **Cadenza** se concibe como una sola entidad o caja negra. Sus interacciones principales son con el usuario final (transcriptor) y los formatos de datos externos de entrada y salida.

```d2
direction: right

classes: {
  actor: {
    shape: person
    style.fill: "#f9f"
    style.stroke: "#333"
    style.stroke-width: 2
  }
  system: {
    style.fill: "#85C1E9"
    style.stroke: "#2E86C1"
    style.stroke-width: 3
    style.border-radius: 8
  }
  format: {
    shape: page
    style.fill: "#F7DC6F"
    style.stroke: "#D68910"
    style.stroke-width: 2
  }
}

Usuario: "Usuario (Transcriptor)"
Entrada: "Imagen de Partitura\n(Foto, Scan, Datasets)"
Cadenza: "Plataforma Cadenza\n(Caja Negra)"
MusicXML: "Exportación MusicXML\n(Editable)"
MIDI: "Exportación MIDI\n(Reproducción)"
Audio: "Reproducción de la partitura\nen la página"

Usuario.class: actor
Cadenza.class: system
Entrada.class: format
MusicXML.class: format
MIDI.class: format
Audio.class: format

Entrada -> Cadenza: "1. Carga partitura"
Usuario -> Cadenza: "2. Corrige inconsistencias e interactúa"
Cadenza -> MusicXML: "3. Produce"
Cadenza -> MIDI: "3. Produce"
Cadenza -> Audio: "4. Reproduce"
```

* **Entradas:** Imágenes de partituras (fotografías o escaneos en formatos PNG/JPG, una imagen por sesión) procedentes de archivos personales o de los datasets públicos de evaluación (PrIMuS, SMB, MUSCIMA++).
* **Salidas:** Archivos de música simbólica en formato **MusicXML 4.0** (editable en cualquier editor convencional) y **MIDI 1.0** (para reproducción audible de la transcripción). Además, la plataforma **reproduce la partitura en la página** para que el transcriptor la verifique auditivamente sin descargar archivos.
* **Actores:** El usuario transcriptor, quien supervisa la salida y edita activamente los errores señalados por el motor de validación. Cada usuario inicia sesión y solo accede a sus propias partituras.

---

## 2. Nivel 2: Arquitectura del Sistema (Caja Blanca / DBB)

En este nivel se abre la caja negra de **Cadenza** y se expone su estructura interna. El sistema se organiza en **cinco bloques estructurales** repartidos en dos planos de cómputo:

* **Plano online** (peticiones del usuario): Capa de Presentación, Capa de Lógica de Negocio y Motor de Transcripción.
* **Plano offline** (trabajos por lotes): Módulo de Aprendizaje Activo.
* **Capa de Datos:** único punto de contacto entre ambos planos.

Este nivel es la vista **estructural** (sin aristas): el flujo de proceso numerado se detalla en el Nivel 3.

```d2
classes: {
  client: {
    style.fill: "#85C1E9"
    style.stroke: "#2E86C1"
    style.stroke-width: 2
    style.border-radius: 8
  }
  server: {
    style.fill: "#82E0AA"
    style.stroke: "#239B56"
    style.stroke-width: 2
    style.border-radius: 8
  }
  batch: {
    style.fill: "#D7BDE2"
    style.stroke: "#7D3C98"
    style.stroke-width: 2
    style.border-radius: 8
  }
  data: {
    style.fill: "#F5CBA7"
    style.stroke: "#D35400"
    style.stroke-width: 2
    style.border-radius: 8
  }
}

Plataforma_Cadenza: "Plataforma de Digitalización Asistida" {
  grid-columns: 5
  grid-gap: 16

  presentation_layer: "Capa de Presentación (Frontend - plano online)" {
    grid-rows: 5
    UI: "UI de Corrección Asistida (HITL)"
    Visor: "Visor Interactivo (imagen + notación SVG)"
    Editor: "Panel de Edición de Símbolos"
    Importador: "Importador de Partituras (Fotos/Escaneos)"
    Reproductor: "Reproductor de Partitura (Tone.js)"
  }

  backend_layer: "Capa de Lógica de Negocio (Backend - plano online)" {
    grid-rows: 4
    Gateway: "API Gateway (FastAPI)"
    Aplicacion: "Capa de Aplicación (casos de uso)"
    Validador: "Motor de Validación (reglas de teoría musical)"
    Exportador: "Exportador (MusicXML/MIDI)"
  }

  omr_motor: "Motor de Transcripción (plano online)" {
    grid-rows: 2
    OMR: "OMREngine (HOMR sobre onnxruntime)"
    Interchange: "Puente de notación (MusicXML -> ScoreIR)"
  }

  active_learning_module: "Módulo de Aprendizaje Activo (plano offline)" {
    grid-rows: 4
    Dataset: "DatasetBuilder"
    Selector: "Selector de Muestras (AcquisitionStrategy)"
    Trainer: "Trainer (PyTorch, por lotes en servidor)"
    Evaluador: "Evaluador (SER / OMR-NED)"
  }

  data_layer: "Capa de Datos" {
    grid-rows: 3
    DB: "Base de Datos (PostgreSQL + JSONB)" {
      shape: cylinder
    }
    Artefactos: "ArtifactStore (imágenes, MusicXML, ONNX por sha256)" {
      shape: page
    }
    Registro: "Model Registry (versiones y métricas)" {
      shape: cylinder
    }
  }
}

# D2 no resuelve shorthand para nodos anidados: usar SIEMPRE ruta completa
# en clases y aristas, o se crean nodos duplicados fuera de los contenedores.
Plataforma_Cadenza.presentation_layer.UI.class: client
Plataforma_Cadenza.presentation_layer.Visor.class: client
Plataforma_Cadenza.presentation_layer.Editor.class: client
Plataforma_Cadenza.presentation_layer.Importador.class: client
Plataforma_Cadenza.presentation_layer.Reproductor.class: client
Plataforma_Cadenza.backend_layer.Gateway.class: server
Plataforma_Cadenza.backend_layer.Aplicacion.class: server
Plataforma_Cadenza.backend_layer.Validador.class: server
Plataforma_Cadenza.backend_layer.Exportador.class: server
Plataforma_Cadenza.omr_motor.OMR.class: server
Plataforma_Cadenza.omr_motor.Interchange.class: server
Plataforma_Cadenza.active_learning_module.Dataset.class: batch
Plataforma_Cadenza.active_learning_module.Selector.class: batch
Plataforma_Cadenza.active_learning_module.Trainer.class: batch
Plataforma_Cadenza.active_learning_module.Evaluador.class: batch
Plataforma_Cadenza.data_layer.DB.class: data
Plataforma_Cadenza.data_layer.Artefactos.class: data
Plataforma_Cadenza.data_layer.Registro.class: data
```

Los cinco bloques estructurales, en orden:

| # | Bloque | Plano | Componentes | Paquetes |
|---|---|---|---|---|
| 1 | Capa de Presentación (Frontend) | Online | UI de Corrección Asistida, Visor Interactivo, Panel de Edición de Símbolos, Importador de Partituras, Reproductor de Partitura | `apps/web` |
| 2 | Capa de Lógica de Negocio (Backend) | Online | API Gateway, Capa de Aplicación, Motor de Validación, Exportador | `apps/api`, `packages/application`, `packages/validation`, `packages/interchange` |
| 3 | Motor de Transcripción | Online | `OMREngine` (HOMR), Puente de notación | `packages/omr`, `packages/interchange` |
| 4 | Módulo de Aprendizaje Activo | Offline | `DatasetBuilder`, Selector de Muestras, Trainer, Evaluador | `packages/learning`, `ml/` |
| 5 | Capa de Datos | Compartida | Base de Datos, `ArtifactStore`, *Model Registry* | `packages/persistence` |

Todos los bloques comparten el **dominio** (`packages/domain`): el `ScoreDocument`, las anclas, los `Finding` y los `EditEvent`.

---

## 3. Nivel 3: Flujo de Proceso Extremo a Extremo (E2E)

Este nivel muestra el flujo completo del sistema como **diagrama de secuencia**: cada participante es un componente de la plataforma y cada mensaje numerado (1–22) corresponde a un paso del flujo. Las flechas **sólidas** son llamadas/avance del pipeline; las **punteadas** son respuestas o retroalimentación. Los pasos 1–16 ocurren en el plano online, durante la sesión del usuario; los pasos 17–22 son un **trabajo por lotes** que se ejecuta aparte y solo se comunica con el plano online a través de la Capa de Datos.

```d2
vars: {
  d2-config: {
    layout-engine: elk {
      spacing.nodeNode: 15
      layered.spacing.nodeNodeBetweenLayers: 25
      layered.edgeRouting: "ORTHOGONAL"
    }
  }
}

flujo: "Flujo de Proceso E2E (numerado)" {
  Usuario: "Usuario (Transcriptor)"
  UI: "UI de Corrección Asistida (HITL)"
  Gateway: "API Gateway + Capa de Aplicación"
  Artefactos: "ArtifactStore"
  OMR: "OMREngine (HOMR)"
  Validador: "Motor de Validación"
  DB: "Base de Datos (PostgreSQL)"
  Exportador: "Exportador (MusicXML/MIDI)"
  Dataset: "DatasetBuilder (offline)"
  Selector: "Selector de Muestras (offline)"
  Trainer: "Trainer + Evaluador (offline)"
  Registro: "Model Registry"

  Usuario -> UI: "1. Sube imagen"
  UI -> Gateway: "2. Envía archivo"
  Gateway -> Artefactos: "3. Guarda imagen (sha256)"
  Gateway -> OMR: "4. Ejecuta transcripción"
  OMR --> Gateway: "5. ScoreDocument crudo (ScoreIR + anclas)"
  Gateway -> Validador: "6. Valida el documento"
  Validador --> Gateway: "7. Hallazgos anclados"
  Gateway -> DB: "8. Persiste sesión y hallazgos"
  Gateway --> UI: "9. Retorna documento + hallazgos"
  Usuario -> UI: "10. Revisa alertas y corrige"
  UI -> Gateway: "11. Envía corrección (EditEvent)"
  Gateway -> DB: "12. Verifica y añade al log inmutable"
  Gateway -> Validador: "13. Revalida el estado actual"
  Gateway --> UI: "14. Estado actualizado + hallazgos vigentes"
  UI -> Gateway: "15. Solicita exportación"
  Gateway -> Exportador: "16. Genera MusicXML / MIDI"
  DB -> Dataset: "17. Sesiones y correcciones"
  Dataset -> Selector: "18. Muestras de entrenamiento"
  Selector -> Trainer: "19. Lote seleccionado"
  Trainer -> Artefactos: "20. Modelo ONNX"
  Trainer -> Registro: "21. Registra versión y métricas"
  Registro --> OMR: "22. Promoción gobernada por umbral"
}
```

### Pasos del flujo (E2E)

| Paso | De → A | Descripción | Plano |
|---|---|---|---|
| 1 | Usuario → UI | Sube la imagen de la partitura | Online |
| 2 | UI → API Gateway | Envía el archivo | Online |
| 3 | Aplicación → ArtifactStore | Guarda la imagen direccionada por `sha256` | Online |
| 4 | Aplicación → OMREngine | Ejecuta la transcripción (HOMR) | Online |
| 5 | OMREngine → Aplicación | Devuelve el `ScoreDocument` crudo (`ScoreIR` + anclas + procedencia) | Online |
| 6 | Aplicación → Motor de Validación | Aplica el catálogo de reglas | Online |
| 7 | Motor de Validación → Aplicación | Devuelve los hallazgos anclados | Online |
| 8 | Aplicación → Base de Datos | Persiste la sesión y los hallazgos | Online |
| 9 | API Gateway → UI | Retorna documento y hallazgos | Online |
| 10 | Usuario → UI | Revisa las alertas y corrige | Online (HITL) |
| 11 | UI → API Gateway | Envía la corrección como `EditEvent` | Online (HITL) |
| 12 | Aplicación → Base de Datos | Comprueba que la edición es aplicable y la añade al log inmutable | Online (HITL) |
| 13 | Aplicación → Motor de Validación | Revalida el estado materializado | Online (HITL) |
| 14 | API Gateway → UI | Devuelve el estado actualizado y los hallazgos vigentes | Online (HITL) |
| 15 | UI → API Gateway | Solicita la exportación | Online |
| 16 | Aplicación → Exportador | Genera MusicXML 4.0 o MIDI 1.0 desde el estado actual | Online |
| 17 | Base de Datos → DatasetBuilder | Lee sesiones y correcciones acumuladas | Offline |
| 18 | DatasetBuilder → Selector | Produce las muestras de entrenamiento | Offline |
| 19 | Selector → Trainer | Entrega el lote seleccionado | Offline |
| 20 | Trainer → ArtifactStore | Guarda el modelo ajustado en ONNX | Offline |
| 21 | Trainer → Model Registry | Registra la versión con sus métricas (SER, OMR-NED) | Offline |
| 22 | Model Registry → OMREngine | Activa la versión solo si supera el umbral | Retroalimentación (aprendizaje) |

Los pasos 10–14 se repiten por cada corrección. La reproducción de audio ocurre en el navegador a partir del estado actual de la partitura y no requiere pasos adicionales en el servidor.

---

## 4. Descripción Detallada de los Bloques de Construcción

### Capa de Presentación (Frontend)

1. **UI de Corrección Asistida (HITL):**
   * **Descripción:** Aplicación web (React + TypeScript) donde el transcriptor carga sus partituras, visualiza los resultados y gestiona el flujo de trabajo.
   * **Responsabilidad:** Coordinar las vistas y comunicarse con el backend a través de la API REST.
2. **Visor Interactivo:**
   * **Descripción:** Vista de la imagen original y de la notación renderizada en SVG (*OpenSheetMusicDisplay*), en paralelo.
   * **Responsabilidad:** Pintar los hallazgos de validación como recuadros de advertencia sobre los eventos señalados, mediante el mapa de anclas, y sincronizar el cursor con la reproducción.
3. **Panel de Edición de Símbolos:**
   * **Descripción:** Panel de herramientas para modificar altura, duración, alteración, clave o armadura, e insertar o borrar eventos.
   * **Responsabilidad:** Convertir cada acción en un `EditEvent` anclado y enviarlo al backend; ofrecer deshacer y rehacer.
4. **Importador de Partituras:**
   * **Descripción:** Módulo de carga de partituras (fotografías y escaneos PNG/JPG).
   * **Responsabilidad:** Validar la imagen, mostrar su previsualización y enviarla al backend.
5. **Reproductor de Partitura:**
   * **Descripción:** Componente de audio del navegador (Tone.js).
   * **Responsabilidad:** Sintetizar el estado actual de la partitura para la verificación auditiva, sincronizado con el Visor.

### Capa de Lógica de Negocio (Backend)

1. **API Gateway:**
   * **Descripción:** Servidor FastAPI.
   * **Responsabilidad:** Autenticar cada petición, traducir peticiones y respuestas HTTP y componer las dependencias; no contiene lógica de negocio.
2. **Capa de Aplicación:**
   * **Descripción:** Casos de uso del sistema (`transcribe_score`, `append_edit`, `revalidate`, `export_score`, `record_effort`).
   * **Responsabilidad:** Orquestar el motor OMR, la validación, la persistencia y la exportación. Garantiza que ninguna edición inválida entre al log.
3. **Motor de Validación:**
   * **Descripción:** Catálogo de reglas puras de teoría musical sobre el `ScoreIR` (balance de compás, armadura y alteraciones, colisión de voces, rango, cierres).
   * **Responsabilidad:** Emitir hallazgos anclados, con severidad y sugerencia de corrección, al transcribir y tras cada corrección.
4. **Exportador:**
   * **Descripción:** Serializador del `ScoreIR` (sobre `music21`, en `packages/interchange`).
   * **Responsabilidad:** Generar MusicXML 4.0 y MIDI 1.0 a partir del estado actual de la partitura.

### Motor de Transcripción

1. **`OMREngine` (HOMR):**
   * **Descripción:** Adaptador del motor de reconocimiento óptico HOMR, ejecutado *in-process* sobre `onnxruntime` (CPU o GPU). `oemer` se integra como adaptador alternativo para la línea base experimental y `FakeOMREngine` para pruebas.
   * **Responsabilidad:** Tomar una imagen y producir el `ScoreDocument` crudo, usando la versión de modelo activa en el *Model Registry*.
2. **Puente de notación:**
   * **Descripción:** Conversor entre formatos simbólicos y el `ScoreIR` (`packages/interchange`).
   * **Responsabilidad:** Normalizar el MusicXML que produce el motor a la representación interna.

### Módulo de Aprendizaje Activo (plano offline)

1. **`DatasetBuilder`:**
   * **Descripción:** Constructor del conjunto de entrenamiento.
   * **Responsabilidad:** Leer sesiones y correcciones persistidas y traducirlas a muestras alineadas por anclas.
2. **Selector de Muestras:**
   * **Descripción:** Estrategias de adquisición intercambiables (incertidumbre, diversidad, híbrida).
   * **Responsabilidad:** Elegir las muestras de mayor valor. En lugar de la confianza simple (ineficaz según AL-003), la estrategia principal combina la densidad de errores del validador, la magnitud de las correcciones y la diversidad.
3. **Trainer:**
   * **Descripción:** Ajuste fino **por lotes en el servidor** (PyTorch), con configuración versionada y semillas fijas. No hay entrenamiento en el dispositivo.
   * **Responsabilidad:** Ajustar el modelo de reconocimiento con el lote seleccionado y exportarlo a ONNX.
4. **Evaluador:**
   * **Descripción:** Cálculo de métricas estándar (SER, OMR-NED).
   * **Responsabilidad:** Medir cada versión candidata contra el corpus de evaluación.

### Capa de Datos

1. **Base de Datos (PostgreSQL + JSONB):**
   * **Descripción:** Base relacional con columnas JSONB para las estructuras variables; SQLite queda como alternativa para pruebas.
   * **Responsabilidad:** Almacenar usuarios, sesiones, hallazgos, el log inmutable de correcciones y las métricas de esfuerzo.
2. **`ArtifactStore`:**
   * **Descripción:** Almacén de archivos direccionado por el `sha256` de su contenido.
   * **Responsabilidad:** Guardar imágenes originales, MusicXML y modelos ONNX fuera de la base de datos.
3. ***Model Registry*:**
   * **Descripción:** Catálogo de versiones de modelo con sus métricas, dataset y configuración.
   * **Responsabilidad:** Gobernar qué versión usa el plano online; una versión se promueve solo si supera el umbral.
