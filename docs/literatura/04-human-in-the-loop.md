# 04 — Interfaz de Corrección Humana (HITL)

Sistemas human-in-the-loop (HITL) y machine learning interactivo: cómo integrar la asistencia humana
en el flujo de reconocimiento. Alimenta la **Interfaz de Corrección** de Cadenza.

## Índice

| ID | Título | Año | Relevancia |
|---|---|---|---|
| HITL-001 | Power to the People: The Role of Humans in Interactive Machine Learning | 2014 | Alta |
| HITL-002 | MuRET — plataforma web de OMR con edición | 2023 (verificar) | Media |
| HITL-003 | Interactive Machine Learning for Health Informatics | 2016 | Media |
| HITL-004 | OMRAT — herramienta web de anotación semi-automática para OMR | 2024 | Alta |
| HITL-005 | Design of a Music Recognition, Encoding, and Transcription Online Tool | 2026 | Media |

## Fichas

### [HITL-001] Power to the People: The Role of Humans in Interactive Machine Learning
- **Autores:** Saleema Amershi, Maya Cakmak, William Bradley Knox, Todd Kulesza
- **Año / Venue:** 2014, AI Magazine, 35(4), 105–120
- **DOI / URL:** https://doi.org/10.1609/aimag.v35i4.2513
- **Tags:** hitl, interactive ml, diseño de interacción
- **Abstract (resumen parafraseado):**
  > Revisión de los principios del machine learning interactivo: los roles del humano (etiquetado,
  > corrección, selección de datos, evaluación), los ciclos de interacción, y pautas de diseño de
  > interfaces para sistemas de ML (feedback, explicabilidad, control).
- **Relevancia para Cadenza:** Alta — da el marco teórico para diseñar la interfaz de corrección
  y el ciclo de feedback de Cadenza.
- **Notas / ideas:**
  - Usar sus pautas de diseño para justificar decisiones de UI en la tesis (qué mostrar, cuándo pedir
    confirmación, cómo cerrar el ciclo).
  - La corrección del usuario es la materia prima del aprendizaje activo (ver tema 05).

### [HITL-002] MuRET — Music Recognition, Transcription and Editing
- **Autores:** grupo de la U. de Alicante (Rizo, Calvo-Zaragoza y colaboradores) — verificar
- **Año / Venue:** aprox. 2023, plataforma web — **verificar**
- **DOI / URL:** el sitio oficial `muret.ua.es` está actualmente sin resolución DNS (ago 2026); demo publicada en Zenodo: https://doi.org/10.5281/zenodo.10113919
- **Tags:** omr, web, edición, workflow
- **Abstract (resumen parafraseado):**
  > MuRET es una plataforma web para OMR que combina reconocimiento automático con edición manual
  > de los resultados (corrección de notas, símbolos y estructura) y exportación a formatos
  > simbólicos, pensada para digitalización en bibliotecas y archivos.
- **Relevancia para Cadenza:** Media — precedente directo de la propuesta de Cadenza como plataforma
  con asistencia humana; útil para comparar enfoques (web vs. desktop, edición por pasos).
- **Notas / ideas:**
  - Verificar la referencia exacta (paper y repositorio) antes de citar.
  - Extraer el modelo de interacción: cómo organiza el flujo reconocer → revisar → corregir → exportar.
  - Diferenciador de Cadenza: ciclo de aprendizaje activo con el feedback (MuRET no reentrena con
    correcciones, verificar).

### [HITL-003] Interactive Machine Learning for Health Informatics: When do we need the human-in-the-loop?
- **Autores:** Andreas Holzinger
- **Año / Venue:** 2016, Brain Informatics, 3(2), 119–131
- **DOI / URL:** https://doi.org/10.1007/s40708-016-0042-6
- **Tags:** hitl, interactive ml, modelos híbridos
- **Abstract (resumen parafraseado):**
  > Discute cuándo y por qué se necesita al humano en sistemas de ML: conocimiento experto,
  > datos escasos, consecuencias de errores. Propone arquitecturas híbridas (algoritmo + humano)
  > y los tipos de interacción según el contexto.
- **Relevancia para Cadenza:** Media — argumento para justificar la asistencia humana en OMR
  (el error automático es costoso de corregir después) y para el diseño del ciclo de feedback.
- **Notas / ideas:**
  - Ejemplo transversal de HITL (no es de música) pero muy citado para justificar el enfoque.

### [HITL-004] An Online Tool for Semi-Automatically Annotating Music Scores for Optical Music Recognition (OMRAT)
- **Autores:** no especificados en el abstract — verificar
- **Año / Venue:** 2024, ACM (posible DLfM 2024 — verificar)
- **DOI / URL:** https://dl.acm.org/doi/10.1145/3660570.3660571
- **Tags:** anotación, semi-automático, omr, mei, edición humana
- **Abstract (texto del paper):**
  > The paper describes an online tool, OMRAT, for semi-automatic annotation of music scores for Optical Music Recognition (OMR) systems. OMRAT uses deep neural networks, machine learning, and music notation ontologies at different stages to respectively detect musical objects, establish relationships between them, and convert them into a machine-readable format MEI. A human editor verifies the output of the recognition stage to correct potential errors and remove incorrect labels as needed. The tool can create training/testing datasets for OMR systems and may be used for notation editors or audio synthesizers.
- **Relevancia para Cadenza:** Alta — precedente directo de la interfaz de corrección (editor humano verifica/corrige la salida del reconocimiento) y de la generación de datasets con anotaciones.
- **Notas / ideas:**
  - Comparar el flujo de OMRAT (detectar → relacionar → convertir a MEI → verificación humana) con el diseño de la interfaz de Cadenza.
  - Exporta a MEI, no MusicXML: evaluar si esa elección aplica a Cadenza.

### [HITL-005] Design of a Music Recognition, Encoding, and Transcription Online Tool
- **Autores:** David Rizo, Jorge Calvo-Zaragoza, Juan C. Martínez-Sevilla, Adrián Roselló, Eliseo Fuentes-Martínez
- **Año / Venue:** 2023, CMMR (16.º International Symposium on Computer Music Multidisciplinary Research, Tokio); versión publicada en volumen Springer (2026)
- **DOI / URL:** https://doi.org/10.1007/978-3-032-02042-0_24 · preprint: https://doi.org/10.5281/zenodo.10109915
- **Tags:** herramienta web, workflow OMR, transcriptor, diseño
- **Abstract (texto del paper):**
  > In recent years, Optical Music Recognition (OMR) technologies have experienced a notable boost thanks mainly to the use of new pipelines based on machine learning, especially on deep neural networks. These methods are usually studied just from the point of view of the accuracy of the output of the networks. However, from a practical perspective in a real-world context, this is not enough. In this paper, we present a design of a tool devised for allowing the scientific study of the complete OMR workflow in different scenarios and notations, including both the possibility of analyzing the real impact of improvements in automatic recognition models and how they are integrated for practical purposes in the work of the transcriber.
- **Relevancia para Cadenza:** Media — diseño de herramienta para estudiar el flujo OMR completo en el trabajo real del transcriptor; marco conceptual útil para la arquitectura de la plataforma.
- **Notas / ideas:**
  - Argumento de apoyo: la precisión del modelo no basta; el flujo completo (reconocer → integrar → transcribir) es lo que hace usable un sistema (mismo mensaje que Cadenza).

## Dónde buscar más

- **Palabras clave:** "interactive machine learning", "human-in-the-loop", "interactive OMR",
  "crowdsourcing music transcription", "human correction OCR".
- **Venues:** AI Magazine, CHI, IUI, HCOMP, ISMIR.
- **Estrategia:** buscar "interactive OMR" y "OMR editing tool" para encontrar sistemas similares
  recientes (MuRET, Audiveris ya fichado en el tema 01, etc.) y posicionar la propuesta de Cadenza.
