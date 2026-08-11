# 01 — OMR: Estado del Arte

Reconocimiento óptico de música (OMR, *Optical Music Recognition*): convertir imágenes de partituras en
representaciones simbólicas editables. Este tema alimenta el **Modelo OMR base** de Cadenza (oemer) y el
capítulo de Estado del Arte de la tesis.

## Índice

| ID | Título | Año | Relevancia |
|---|---|---|---|
| OMR-001 | Understanding Optical Music Recognition | 2020 | Alta |
| OMR-002 | Optical music recognition: state-of-the-art and open issues | 2012 | Alta |
| OMR-003 | oemer — librería Python de OMR end-to-end | 2021 | Alta |
| OMR-004 | Audiveris — OMR open source | 2011 | Media |
| OMR-005 | The challenge of optical music recognition | 2001 | Media |
| OMR-006 | Deep Learning Algorithm Composition System Based on Music Score Recognition | 2022 | Media |
| OMR-007 | Handwritten Note Recognition in Digital Music Classroom Teaching Based on Trusted Neural Network | 2023 | Media |

## Fichas

### [OMR-001] Understanding Optical Music Recognition
- **Autores:** Jorge Calvo-Zaragoza, Jan Hajič Jr., Alexander Pacha
- **Año / Venue:** 2020, ACM Computing Surveys, vol. 53, n.º 4, pp. 1–35
- **DOI / URL:** https://doi.org/10.1145/3397499
- **Tags:** omr, survey, pipeline, datasets
- **Abstract (resumen parafraseado):**
  > Survey integral del campo OMR: presenta la tarea, el pipeline clásico (preprocesado,
  > detección de pentagramas y símbolos, clasificación, ensamblaje, reconstrucción musical),
  > las familias de enfoques (basados en reglas, probabilísticos, aprendizaje profundo),
  > los datasets existentes, las métricas de evaluación y los retos abiertos.
- **Relevancia para Cadenza:** Alta — es el punto de partida obligatorio del estado del arte y da el
  vocabulario y las fases del pipeline que Cadenza automatiza.
- **Notas / ideas:**
  - Leer antes de cualquier otra referencia.
  - Usar su taxonomía del pipeline para estructurar el Marco Teórico de la tesis.
  - Revisar la sección de evaluación: define métricas que usaremos en el capítulo de experimentación.

### [OMR-002] Optical music recognition: state-of-the-art and open issues
- **Autores:** Ana Rebelo, Ichiro Fujinaga, Filip Paszkiewicz, André R. S. Marcal, Carlos Guedes, Jaime S. Cardoso
- **Año / Venue:** 2012, International Journal of Multimedia Information Retrieval, 1(3), 173–190
- **DOI / URL:** https://doi.org/10.1007/s13735-012-0004-6
- **Tags:** omr, survey, retos abiertos
- **Abstract (resumen parafraseado):**
  > Revisión del estado del arte de OMR: taxonomía de sistemas, técnicas de cada etapa del proceso
  > y problemas abiertos (manuscritos, calidad de imagen, evaluación estandarizada).
- **Relevancia para Cadenza:** Alta — survey clásico que da contexto histórico y confirma los retos
  que Cadenza aborda (manuscritos, evaluación).
- **Notas / ideas:**
  - Complementa al survey 2020 desde la perspectiva de 2012; útil para el Marco Teórico.
  - Los problemas abiertos listados sirven como motivación de la tesis.

### [OMR-003] oemer — librería Python de OMR end-to-end
- **Autores:** BreezeWhite (mantenedor) — proyecto open source
- **Año / Venue:** ~2021 (activo), GitHub
- **DOI / URL:** https://github.com/BreezeWhite/oemer
- **Tags:** omr, end-to-end, python, musicxml, pipeline
- **Abstract (resumen parafraseado):**
  > oemer es una librería Python de OMR end-to-end que toma imágenes de partituras (escaneadas o
  > fotografiadas) y produce MusicXML. Internamente implementa un pipeline de redes neuronales:
  > eliminación de pentagramas, detección de notas/símbolos, ensamblaje y reconstrucción musical.
  > El modelo principal (modelo de detección) se entrena sobre un dataset grande de partituras de piano.
- **Relevancia para Cadenza:** Alta — es el **modelo OMR base** elegido para el proyecto.
- **Notas / ideas:**
  - Verificar si existe paper formal publicado; si no, citar el repositorio.
  - Probar su pipeline con partituras de nuestro corpus objetivo (impresas y manuscritas modernas, piano simple).
  - Identificar sus puntos débiles (notas juntas/acordes, tempo, errores de reconstrucción) → insumo
    directo para el motor de validación y la interfaz de corrección.
  - Evaluar qué tan modificable es para el ciclo de aprendizaje activo (¿reentrenable?).

### [OMR-004] Audiveris — OMR open source
- **Autores:** Hervé Bitteur y comunidad
- **Año / Venue:** 2011 (origen), activo; GitHub
- **DOI / URL:** https://github.com/Audiveris/audiveris
- **Tags:** omr, java, ui, correccion manual
- **Abstract (resumen parafraseado):**
  > Audiveris es un sistema OMR de escritorio que convierte partituras escaneadas a MusicXML,
  > con una interfaz gráfica que permite corregir manualmente los errores del reconocimiento
  > (notas, símbolos, agrupaciones) antes de exportar.
- **Relevancia para Cadenza:** Media — referencia de comparación; su UI de corrección manual es un
  precedente directo de la interfaz de corrección de Cadenza.
- **Notas / ideas:**
  - Estudiar cómo Audiveris organiza la corrección por pasos (deformables, grupos, enlaces) para
    inspirar el diseño de nuestra UI.
  - No es reentrenable con feedback → contraste con el aporte de Cadenza.

### [OMR-005] The challenge of optical music recognition
- **Autores:** David Bainbridge, Tim Bell
- **Año / Venue:** 2001, Computers and the Humanities, 35(2), 95–121
- **DOI / URL:** https://doi.org/10.1023/a:1002485918032
- **Tags:** omr, retos, historia
- **Abstract (resumen parafraseado):**
  > Artículo seminal que describe por qué OMR es difícil en comparación con OCR de texto:
  > la notación musical es bidimensional, densa y con semántica implícita. Analiza los retos
  > de cada etapa y las limitaciones de los sistemas de la época.
- **Relevancia para Cadenza:** Media — contexto histórico para la introducción y motivación.
- **Notas / ideas:**
  - Cita clásica para justificar por qué "no es solo OCR".
  - Buen punto de partida para el párrafo de motivación de la tesis.

### [OMR-006] Deep Learning Algorithm Composition System Based on Music Score Recognition
- **Autores:** no especificados en el abstract — verificar
- **Año / Venue:** 2022, IEEE ICKECS (verificar nombre completo de la conferencia)
- **DOI / URL:** https://doi.org/10.1109/ICKECS56523.2022.10060542
- **Tags:** omr, deep learning, clasificación, aplicación
- **Abstract (texto del paper):**
  > With the development of computer science and music technology, algorithms have been widely studied and applied in the field of computer composition. The "computer generated art" evolved from this belongs to the category of algorithmic art. The creators can make the computer automatically generate and create music or assist the creators to complete music creation by writing programs and formulating relevant limiting rules. Music composition system based on deep learning algorithm of music score recognition is a method of creating deep neural network to recognize and classify music scores. The main idea behind this method is to use deep learning algorithm to generate features from the input data, and then use these features to classify music scores. The deep learning algorithm helps to identify patterns in the input data by using multi-layer artificial neurons or by training learning nodes. These layers may be stacked one after another to form a network with many hidden layers. In other words, this is an attempt to discover patterns in large data sets by using techniques such as clustering and analysis.
- **Relevancia para Cadenza:** Media — ejemplo aplicado de reconocimiento/clasificación de partituras con deep learning; útil como referencia de aplicaciones, aunque de calidad media.
- **Notas / ideas:**
  - Usar como ejemplo de aplicación en el estado del arte, sin profundizar.

### [OMR-007] Handwritten Note Recognition in Digital Music Classroom Teaching Based on Trusted Neural Network
- **Autores:** no especificados en el abstract — verificar
- **Año / Venue:** 2023, IEEE ICETCI (verificar nombre completo de la conferencia)
- **DOI / URL:** https://doi.org/10.1109/ICETCI57876.2023.10176637
- **Tags:** manuscrito, eliminación de pentagramas, LBP, XGBoost, preprocesado
- **Abstract (texto del paper):**
  > Optical music score recognition mainly studies how to form music score images into computer recognizable semantic symbols. Especially for handwritten music score images, it is particularly difficult to recognize and delete spectral lines due to the complexity and variety of handwritten notes and the addition of various deformations and noises. Therefore, the study of spectral line deletion in handwritten music score images has important theoretical significance and practical value. In this paper, a handwritten music score line deletion algorithm based on multi-scale and multi-directional LBP and XGBoost is proposed. LBP features are designed according to the characteristics of music score images. LBP features can be automatically learned through supervised learning. Spectral line deletion is always performed pixel by pixel, and the test takes a long time. Therefore, the parallel design can be used to improve the efficiency of the operation. The results of this paper have certain reference value for handwritten note recognition in digital music classroom teaching based on trusted neural network.
- **Relevancia para Cadenza:** Media — etapa de preprocesado (eliminación de pentagramas) en manuscritos; ahora directamente relevante porque el alcance de Cadenza incluye **manuscritas modernas** (las históricas quedan excluidas).
- **Notas / ideas:**
  - LBP multi-escala/multi-direccional + XGBoost píxel a píxel con diseño paralelo para eficiencia.

## Dónde buscar más

- **Palabras clave:** "optical music recognition", "OMR survey", "end-to-end OMR", "music object detection".
- **Venues principales:** ISMIR, IJDAR (Int. Journal on Document Analysis and Recognition), ICDAR, DAS, ICPR.
- **Estrategia:** buscar citas hacia y desde OMR-001 y OMR-002 en Google Scholar (snowballing).
