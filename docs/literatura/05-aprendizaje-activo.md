# 05 — Aprendizaje Activo

*Aprendizaje activo (active learning)*: el sistema selecciona qué ejemplos debe etiquetar/corregir
el humano para mejorar el modelo con el menor esfuerzo posible. Alimenta el componente de
**Aprendizaje Activo** de Cadenza — el ciclo de mejora continua con feedback del usuario.

> 💡 **Estado del hueco (actualizado 2026):** el aprendizaje activo aplicado específicamente a OMR
> sigue siendo muy escaso, pero ya existe un primer estudio directo ([AL-003](#al-003-experimenting-active-and-sequential-learning-in-a-medieval-music-manuscript), 2025)
> con resultados **mixtos e importantes**: la selección por incertidumbre NO fue efectiva en su
> manuscrito medieval, y los autores recomiendan métodos más utilizables en escenarios de datos
> escasos. Para Cadenza esto es clave: el diseño del ciclo de aprendizaje activo debe partir de ese
> hallazgo, justificar su estrategia (p. ej. selección a nivel de partitura, diversidad + confianza)
> y posicionarse como uno de los pocos sistemas que integran AL en un flujo OMR usable.

## Índice

| ID | Título | Año | Relevancia |
|---|---|---|---|
| AL-001 | Active Learning Literature Survey | 2009 | Alta |
| AL-002 | Active Learning (libro) | 2012 | Media |
| AL-003 | Experimenting Active and Sequential Learning in a Medieval Music Manuscript | 2025 | Alta |
| AL-004 | Enhancing Pseudo-Labeling Performance in Object Detection Using GMM Uncertainty | 2024 | Media |

## Fichas

### [AL-001] Active Learning Literature Survey
- **Autores:** Burr Settles
- **Año / Venue:** 2009, Computer Sciences Technical Report 1648, University of Wisconsin–Madison
- **DOI / URL:** https://minds.wisconsin.edu/handle/1793/60660 · https://burrsettles.com/pub/settles.activelearning.pdf
- **Tags:** active learning, survey, selección de datos
- **Abstract (resumen parafraseado):**
  > Survey de referencia del campo: escenarios (consultivo, de flujo, por pool), estrategias de
  > selección (uncertainty sampling, query-by-committee, expected error reduction, etc.), métodos
  > para reducir el esfuerzo humano (etiquetado por lotes, multidimensión) y aplicaciones.
- **Relevancia para Cadenza:** Alta — fundamento teórico para elegir la estrategia de selección de
  correcciones que pide Cadenza al usuario.
- **Notas / ideas:**
  - Decidir el escenario: por *pool* (lote de partituras pendientes) encaja con el flujo de Cadenza.
  - *Uncertainty sampling* sobre la confianza del motor de validación es la vía natural: corregir
    primero lo que el sistema detecta como más dudoso.

### [AL-002] Active Learning (libro)
- **Autores:** Burr Settles
- **Año / Venue:** 2012, Synthesis Lectures on Artificial Intelligence and Machine Learning, Morgan & Claypool
- **DOI / URL:** https://doi.org/10.2200/S00429ED1V01Y201207AIM018
- **Tags:** active learning, libro, teoría
- **Abstract (resumen parafraseado):**
  > Versión extendida del survey anterior en formato libro: formaliza los marcos teóricos
  > (bayesiano, minimización de error), los algoritmos principales y casos de estudio.
- **Relevancia para Cadenza:** Media — profundización si la tesis necesita formalizar la estrategia.
- **Notas / ideas:**
  - Leer solo los capítulos de selección y lotes si el tiempo es limitado (4 meses).

### [AL-003] Experimenting Active and Sequential Learning in a Medieval Music Manuscript
- **Autores:** no especificados en el abstract — verificar (proyecto Anonymous, Italia)
- **Año / Venue:** 2025, IEEE MLSP (Machine Learning for Signal Processing Workshop)
- **DOI / URL:** https://doi.org/10.1109/MLSP62443.2025.11204321
- **Tags:** active learning, sequential learning, yolo, manuscrito, incertidumbre
- **Abstract (texto del paper):**
  > Optical Music Recognition (OMR) is a cornerstone of music digitization initiatives in cultural heritage, yet it remains limited by the scarcity of annotated data and the complexity of historical manuscripts. In this paper, we present a preliminary study of Active Learning (AL) and Sequential Learning (SL) tailored for object detection and layout recognition in an old medieval music manuscript. Leveraging YOLOv8, our system selects samples with the highest uncertainty (lowest prediction confidence) for iterative labeling and retraining. Our approach starts with a single annotated image and successfully boosts performance while minimizing manual labeling. Experimental results indicate that comparable accuracy to fully supervised training can be achieved with significantly fewer labeled examples. We test the methodology as a preliminary investigation on a novel dataset offered to the community by the Anonymous project, which studies laude, a poetical-musical genre spread across Italy during the 12th-16th Century. We show that in the manuscript at-hand, uncertainty-based AL is not effective and advocates for more usable methods in data-scarcity scenarios.
- **Relevancia para Cadenza:** Alta — el primer trabajo que aplica aprendizaje activo directamente a OMR (detección de objetos musicales con YOLOv8 y selección por incertidumbre). Lectura obligatoria para el diseño del ciclo de AL de Cadenza.
- **Notas / ideas:**
  - Resultado clave: AL por incertidumbre (menor confianza) NO fue efectivo en ese manuscrito → probar estrategias alternativas (diversidad de muestras, selección a nivel de partitura/página, query-by-committee) y medir antes de comprometerse con una.
  - Comienza con UNA imagen anotada: referencia para el arranque con corpus pequeño de Cadenza.

### [AL-004] Enhancing Pseudo-Labeling Performance in Object Detection Using Gaussian Mixture Modeled Uncertainty
- **Autores:** no especificados en el abstract — verificar
- **Año / Venue:** 2024, IEEE ICEIC (International Conference on Electronics, Information and Communication)
- **DOI / URL:** https://doi.org/10.1109/ICEIC61013.2024.10457103
- **Tags:** semi-supervised, pseudo-labeling, incertidumbre, gmm, detección
- **Abstract (texto del paper):**
  > Object detection research has been rapidly advancing. However, it requires large amounts of training data, where labeling massive datasets incurs great cost and time. To address this problem, semi-supervised learning techniques have been increasingly explored, among which pseudo-labeling has become popular due to its straightforward approach. However, pseudo-labeling has limitations with confidence score-based filtering. In this paper, we propose a method to extract uncertainties using Gaussian mixture models and effectively incorporate them into the labeling process to overcome these limitations. The proposed method achieves more reliable pseudo-labeling results and experiments show a 0.8% performance improvement compared to the existing approach.
- **Relevancia para Cadenza:** Media — técnica relacionada (etiquetado semi-supervisado con incertidumbre modelada por GMM) que complementa el ciclo de AL: usar las correcciones del usuario como pseudo-etiquetas fiables.
- **Notas / ideas:**
  - La incertidumbre con GMM mejora el filtrado por confianza → candidata para decidir qué correcciones del usuario reentrenan el modelo.

## Candidatos a verificar (agregar ficha completa tras confirmar datos)

- **Active learning en clasificación de contenido musical:** Valero-Mas, J. J., Calvo-Zaragoza, J.,
  et al. (aprox. 2019–2021) — estudios de active learning en tareas de MIR (clasificación de
  instrumentos, género). Buscar "Valero-Mas active learning music".
- **Active learning en OCR / documentos:** hay trabajos de selección de muestras para reentrenar OCR
  (p. ej. etiquetado selectivo). Buscar "active learning OCR", "active learning document analysis".

## Dónde buscar más

- **Palabras clave:** "active learning", "human feedback loop machine learning", "active learning
  document recognition", "uncertainty sampling".
- **Venues:** ICML, NeurIPS, UAI, IJDAR, ICDAR.
- **Estrategia:** confirmar que no existe active learning específico para OMR (búsqueda de
  "active learning optical music recognition"); si se confirma el hueco, documentarlo como parte del
  aporte diferencial del proyecto en la introducción de la tesis.
