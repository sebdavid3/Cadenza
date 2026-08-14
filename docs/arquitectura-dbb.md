# Arquitectura General y Diagrama de Bloques de Construcción (DBB)

Este documento describe la arquitectura de software extremo a extremo (E2E) de la plataforma **Cadenza**. El diseño sigue la metodología de **Diagramas de Bloques de Construcción (DBB)**, estructurada en niveles de detalle (caja negra, caja blanca y flujo de proceso).

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
Audio: "Reproducción automática\nde la canción en la página"

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
Cadenza -> Audio: "4. Reproduce automáticamente"
```

* **Entradas:** Imágenes de partituras (fotografías o escaneos en formatos PNG/JPG) procedentes de archivos personales o de los datasets públicos de evaluación (PrIMuS, SMB, MUSCIMA++).
* **Salidas:** Archivos de música simbólica en formato **MusicXML 4.0** (editable en cualquier editor convencional) y **MIDI 1.0** (para reproducción audible de la transcripción). Además, la plataforma **reproduce automáticamente la canción en la página** apenas se genera la partitura digitalizada, para que el transcriptor la verifique auditivamente sin necesidad de descargar archivos.
* **Actores:** El usuario transcriptor, quien supervisa la salida y edita activamente los errores señalados por el motor de validación.

---

## 2. Nivel 2: Arquitectura del Sistema (Caja Blanca / DBB)

En este nivel, abrimos la caja negra de **Cadenza** y exponemos su estructura interna. El sistema se organiza en **cinco bloques estructurales**: Capa de Presentación (Frontend), Motor de Transcripción, Capa de Lógica de Negocio (Backend), Módulo de Aprendizaje Activo y Capa de Datos. Este nivel es la vista **estructural** (sin aristas): el flujo de proceso numerado se detalla en el Nivel 3.

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

  presentation_layer: "Capa de Presentación (Frontend - Cliente UI)" {
    grid-rows: 5
    UI: "UI de Corrección Asistida (HITL)"
    Visor: "Visor Interactivo (Renderizado SVG/Canvas)"
    Editor: "Panel de Edición de Símbolos"
    Importador: "Importador de Partituras (Fotos/Escaneos)"
    Reproductor: "Reproductor de Partitura (Playback automático)"
  }

  omr_motor: "Motor de Transcripción (DWR)" {
    grid-rows: 1
    DWR: "Wrapper DWR (Motor OMR)"
  }

  backend_layer: "Capa de Lógica de Negocio (Backend API Server)" {
    grid-rows: 4
    Orquestador: "Orquestador & API Gateway"
    Validador: "Reglas de Teoría Musical (music21)"
    Auditor: "Auditor de Inconsistencias"
    Exportador: "Generador de Partituras (MusicXML/MIDI)"
  }

  active_learning_module: "Módulo de Aprendizaje Activo" {
    grid-rows: 2
    Selector: "Selector de Muestras de Valor"
    ALEngine: "AL Engine (TFLite — entrenamiento en el dispositivo)"
  }

  data_layer: "Capa de Datos (Almacenamiento Local)" {
    grid-rows: 3
    DB: "Base de Datos Local (SQLite/IndexedDB)" {
      shape: cylinder
    }
    Imagenes: "Imágenes de Partituras (BLOBs/URLs, filesystem)" {
      shape: page
    }
    Modelos: "Modelos de DWR (Pesos entrenados)" {
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
Plataforma_Cadenza.omr_motor.DWR.class: server
Plataforma_Cadenza.backend_layer.Orquestador.class: server
Plataforma_Cadenza.backend_layer.Validador.class: server
Plataforma_Cadenza.backend_layer.Auditor.class: server
Plataforma_Cadenza.backend_layer.Exportador.class: server
Plataforma_Cadenza.active_learning_module.Selector.class: server
Plataforma_Cadenza.active_learning_module.ALEngine.class: server
Plataforma_Cadenza.data_layer.DB.class: data
Plataforma_Cadenza.data_layer.Imagenes.class: data
Plataforma_Cadenza.data_layer.Modelos.class: data
```

Los cinco bloques estructurales, en orden:

| # | Bloque | Componentes |
|---|---|---|
| 1 | Capa de Presentación (Frontend) | UI de Corrección Asistida, Visor Interactivo, Panel de Edición de Símbolos, Importador de Partituras, Reproductor de Partitura |
| 2 | Motor de Transcripción (DWR) | Wrapper DWR (motor OMR) |
| 3 | Capa de Lógica de Negocio (Backend) | Orquestador & API Gateway, Reglas de Teoría Musical, Auditor de Inconsistencias, Generador de Partituras |
| 4 | Módulo de Aprendizaje Activo | Selector de Muestras de Valor, AL Engine (TFLite) |
| 5 | Capa de Datos (Almacenamiento Local) | Base de Datos Local, Imágenes de Partituras, Modelos de DWR |

---

## 3. Nivel 3: Flujo de Proceso Extremo a Extremo (E2E)

Este nivel muestra el flujo completo del sistema como **diagrama de secuencia**: cada participante es un componente de la plataforma y cada mensaje numerado (1–20) corresponde a un paso del flujo. Las flechas **sólidas** son llamadas/avance del pipeline; las **punteadas** son respuestas o retroalimentación (resultados que vuelven al llamador, ciclo de corrección HITL y ciclo de aprendizaje activo). Cada mensaje ocupa su propia fila del diagrama, por lo que no hay texto superpuesto; la descripción completa de cada paso está en la tabla de pasos más abajo.

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
  PartituraImg: "Partitura Original (imagen/scan)"
  Usuario: "Usuario (Transcriptor)"
  UI: "UI de Corrección Asistida (HITL)"
  Orquestador: "Orquestador & API Gateway"
  DWR: "Wrapper DWR (Motor OMR)"
  Validador: "Reglas de Teoría Musical (music21)"
  Auditor: "Auditor de Inconsistencias"
  DB: "Base de Datos Local (SQLite/IndexedDB)"
  Selector: "Selector de Muestras de Valor"
  ALEngine: "AL Engine (TFLite — entrenamiento en el dispositivo)"
  Exportador: "Generador de Partituras (MusicXML/MIDI)"
  SalidaXML: "Archivo MusicXML (Editable)"
  SalidaMIDI: "Archivo MIDI (Reproducción)"
  Reproductor: "Reproductor de Partitura (Playback automático)"
  Visor: "Visor Interactivo (SVG/Canvas)"
  Editor: "Panel de Edición de Símbolos"

  PartituraImg -> UI: "1. Sube imagen"
  UI -> Orquestador: "2. Envía archivo"
  Orquestador --> UI: "3. Muestra previsualización"
  Orquestador -> DWR: "4. Ejecuta pipeline OMR"
  DWR --> Orquestador: "5. Genera MusicXML crudo"
  Orquestador -> Validador: "6. Envía para auditoría"
  Validador -> Auditor: "7. Aplica reglas musicales"
  Auditor --> Orquestador: "8. Reporta zonas sospechosas (JSON)"
  Orquestador -> DB: "9. Almacena estado de la sesión"
  Orquestador --> UI: "10. Retorna imagen + XML + errores"
  Usuario -> Editor: "11. Revisa alertas y edita"
  Editor -> Visor: "12. Corrige alturas, ritmos y duraciones"
  Visor --> UI: "13. Guarda partitura corregida"
  UI -> Orquestador: "14. Envía correcciones"
  Orquestador -> DB: "15. Almacena par original/corregido"
  DB -> Selector: "16. Selecciona muestras de valor"
  Selector -> ALEngine: "17. Entrena/ajusta en el dispositivo"
  ALEngine --> DWR: "18. Actualiza pesos del modelo"
  Orquestador -> Exportador: "19. Genera partitura digitalizada"
  Exportador -> SalidaXML: "Exporta MusicXML editable"
  Exportador -> SalidaMIDI: "Exporta MIDI"
  Exportador -> Reproductor: "20. Reproduce la canción automáticamente"
  Reproductor --> Visor: "Sincroniza audio con la partitura"
}
```

### Pasos del flujo (E2E)

| Paso | De → A | Descripción | Tipo |
|---|---|---|---|
| 1 | Partitura Original → UI | Sube imagen | Pipeline |
| 2 | UI → Orquestador | Envía archivo | Pipeline |
| 3 | Orquestador → UI | Muestra previsualización de la imagen cargada | Pipeline |
| 4 | Orquestador → Wrapper DWR | Ejecuta pipeline OMR | Pipeline |
| 5 | Wrapper DWR → Orquestador | Genera MusicXML crudo | Pipeline |
| 6 | Orquestador → Reglas de Teoría Musical | Envía para auditoría | Pipeline |
| 7 | Reglas de Teoría Musical → Auditor | Aplica reglas musicales (music21) | Pipeline |
| 8 | Auditor → Orquestador | Reporta zonas sospechosas (JSON) | Pipeline |
| 9 | Orquestador → Base de Datos Local | Almacena estado de la sesión | Pipeline |
| 10 | Orquestador → UI | Retorna imagen + XML + errores | Pipeline |
| 11 | Usuario → Editor | Revisa alertas y edita | Pipeline |
| 12 | Editor → Visor | Corrige alturas, ritmos y duraciones | Pipeline |
| 13 | Visor → UI | Guarda partitura corregida | Retroalimentación (HITL) |
| 14 | UI → Orquestador | Envía correcciones | Retroalimentación (HITL) |
| 15 | Orquestador → Base de Datos Local | Almacena par original/corregido | Pipeline |
| 16 | Base de Datos Local → Selector | Selecciona muestras de valor | Pipeline |
| 17 | Selector → AL Engine | Entrena/ajusta en el dispositivo (TFLite) | Pipeline |
| 18 | AL Engine → Wrapper DWR | Actualiza pesos del modelo | Retroalimentación (aprendizaje) |
| 19 | Orquestador → Generador de Partituras | Genera partitura digitalizada | Pipeline |
| 20 | Generador de Partituras → Reproductor | Reproduce la canción automáticamente | Pipeline |

Flujo continuo (sin numerar): `UI → Visor` y `UI → Editor` (renderizado y herramientas de edición), `Generador → MusicXML/MIDI` (exportación de archivos) y `Reproductor → Visor` (sincronización de audio).

> **Nota:** el diagrama de secuencia y esta tabla son equivalentes: cada mensaje numerado (1–20) corresponde a una fila de la tabla; los mensajes sin número (exportación de archivos y sincronización de audio) son los flujos continuos.

---

## 4. Descripción Detallada de los Bloques de Construcción

### Capa de Presentación (Frontend)

1. **UI de Corrección Asistida (HITL):**
   * **Descripción:** Interfaz de usuario interactiva (desarrollada en HTML5/JS) donde el transcriptor carga sus partituras, visualiza los resultados y gestiona el flujo de trabajo.
   * **Responsabilidad:** Coordinar las vistas y comunicarse con el backend API a través de llamadas REST.
2. **Visor Interactivo:**
   * **Descripción:** Canvas o visor SVG interactivo (basado en librerías de renderizado musical simbólico como *OpenSheetMusicDisplay*) que dibuja la partitura digital sobrepuesta a la imagen original o de manera paralela.
   * **Responsabilidad:** Pintar los errores de validación mediante recuadros de advertencia (overlays de color rojo/amarillo) en los compases o notas que fallaron las pruebas sintácticas, y sincronizar la reproducción de audio con el cursor sobre la partitura.
3. **Panel de Edición de Símbolos:**
   * **Descripción:** Panel de herramientas rápido que permite al usuario modificar la altura, duración o presencia de un símbolo musical (notas, alteraciones, compás) directamente sobre la partitura renderizada.
   * **Responsabilidad:** Capturar las acciones de edición y actualizar el modelo simbólico de la partitura.
4. **Importador de Partituras:**
   * **Descripción:** Módulo de carga de partituras físicas (fotografías y escaneos PNG/JPG) desde el dispositivo o datasets.
   * **Responsabilidad:** Validar la imagen cargada, mostrar su previsualización en la UI y enviarla al backend para su procesamiento.
5. **Reproductor de Partitura (Playback Automático):**
   * **Descripción:** Componente de audio del frontend (p. ej. MIDI.js / Web Audio) que sintetiza la partitura digitalizada en sonido.
   * **Responsabilidad:** Reproducir automáticamente la canción en la página apenas el backend genera la partitura digitalizada (MusicXML/MIDI ya validado), para que el transcriptor la verifique auditivamente sin exportar archivos. La reproducción se sincroniza con el Visor Interactivo.

### Motor de Transcripción (DWR)

1. **Wrapper DWR (Motor OMR):**
   * **Descripción:** Envoltorio del motor de reconocimiento óptico de música (punto de partida: la biblioteca `oemer`) para segmentación de pentagramas, clasificación de glifos y ensamblaje de la partitura.
   * **Responsabilidad:** Tomar una imagen cruda y generar el archivo MusicXML inicial (que contiene errores nativos del reconocimiento), y recibir los pesos actualizados por el ciclo de aprendizaje activo.

### Capa de Lógica de Negocio (Backend)

1. **Orquestador & API Gateway:**
   * **Descripción:** Servidor API en Python (FastAPI/Flask) que coordina los subsistemas del backend y responde a las solicitudes del Frontend.
   * **Responsabilidad:** Recibir la imagen, llamar al motor OMR, dirigir la validación, persistir el estado de la sesión y empaquetar los resultados para el cliente.
2. **Reglas de Teoría Musical (music21):**
   * **Descripción:** Motor de reglas lógicas construido utilizando el toolkit de musicología computacional `music21`.
   * **Responsabilidad:** Parsear el MusicXML y aplicar chequeos lógicos (ej. sumar las duraciones en cada compás para compararlas con la métrica definida).
3. **Auditor de Inconsistencias:**
   * **Descripción:** Compilador de alertas de error.
   * **Responsabilidad:** Transformar los errores detectados en el paso de reglas teóricas en una lista estructurada (en formato JSON) con coordenadas de compás, tipo de error y notas sospechosas para que el frontend las dibuje.
4. **Generador de Partituras (Exportador):**
   * **Descripción:** Serializador final de datos.
   * **Responsabilidad:** Convertir el archivo MusicXML ya corregido y validado a su versión final editable, sintetizar el audio/evento en formato MIDI y entregar la partitura digitalizada al **Reproductor** del frontend para su reproducción automática en la página.

### Módulo de Aprendizaje Activo

1. **Selector de Muestras de Valor:**
   * **Descripción:** Algoritmo del ciclo de Aprendizaje Activo encargado de la estrategia de selección de muestras (Active Learning Pool).
   * **Responsabilidad:** En lugar de seleccionar por confianza simple (la cual es ineficaz según AL-003), selecciona partituras basadas en su **diversidad de errores** reportados por el Auditor y en la magnitud de las correcciones del transcriptor.
2. **AL Engine (TFLite):**
   * **Descripción:** Pipeline de reentrenamiento/ajuste fino que corre **en el dispositivo** (TFLite, sin servidor de entrenamiento).
   * **Responsabilidad:** Tomar los pares de imágenes y MusicXML corregidos por el usuario, formatearlos como datos de entrenamiento y ajustar los pesos del Wrapper DWR (fine-tuning de los modelos de detección de símbolos).

### Capa de Datos (Persistencia)

1. **Base de Datos Local (SQLite/IndexedDB):**
   * **Descripción:** Base de datos relacional ligera local (SQLite en el backend; IndexedDB en el navegador).
   * **Responsabilidad:** Almacenar de forma segura el historial de transcripciones, los metadatos de las correcciones del usuario (insumo para medir el esfuerzo cognitivo y evaluar la UX) y el estado de cada sesión.
2. **Imágenes de Partituras (BLOBs/URLs, filesystem):**
   * **Descripción:** Almacenamiento de las imágenes originales cargadas.
   * **Responsabilidad:** Guardar las partituras físicas digitalizadas como BLOBs/URLs en el filesystem local, asociadas a su transcripción.
3. **Modelos de DWR (Pesos entrenados):**
   * **Descripción:** Almacenamiento de los pesos de los modelos del motor OMR.
   * **Responsabilidad:** Persistir las versiones de pesos actualizadas por el ciclo de aprendizaje activo para su uso en nuevas transcripciones.
