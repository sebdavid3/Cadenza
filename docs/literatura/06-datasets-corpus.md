# 06 — Datasets y Corpus

Datasets públicos de partituras para entrenar/evaluar OMR, y criterios para el **corpus objetivo**
de Cadenza (partituras impresas **y escritas a mano actuales**, monofónicas o piano simple — sin
orquesta completa ni manuscritos históricos; el **corpus de evaluación son datasets
públicos con ground truth** (decisión del equipo, 2026).

## Índice

| ID | Título | Año | Relevancia |
|---|---|---|---|
| DS-001 | DeepScores — dataset de partituras | 2018 | Media |
| DS-002 | CAPTAIN — dataset sintético de partituras (verificar) | 2018 | Media |
| DS-003 | HOMUS — símbolos musicales manuscritos online (ICPR 2014) | 2014 | Media |
| DS-004 | PRinS — dataset de partituras impresas (verificar) | 2023 | Media |
| DS-005 | OMR in Manuscripts from the Ricordi Archive (dataset público) | 2024 | Alta |
| DS-006 | MuNG Studio: Annotation Tool for Music Notation Graph | 2025 | Media |
| DS-007 | Smashcima: Full-Page Handwritten Music Document Synthesizer | 2025 | Media |
| DS-008 | PrIMuS / Camera-PrIMuS — partituras impresas monofónicas | 2018 | Alta |
| DS-009 | MUSCIMA++ / CVC-MUSCIMA — manuscritas modernas anotadas | 2017 | Alta |

## Fichas

### [DS-001] DeepScores — A Dataset for Segmentation, Detection and Classification of Tiny Objects
- **Autores:** Lukas Tuggener, Flavio Pantillon, Jürgen Schmidhuber, Thilo Stadelmann
- **Año / Venue:** 2018, Proc. de la 24.ª ICPR
- **DOI / URL:** https://doi.org/10.1109/ICPR.2018.8545306 · https://tuggeluk.github.io/deepscores/
- **Tags:** dataset, detección, deep learning, partituras digitales
- **Abstract (resumen parafraseado):**
  > Dataset de ~250.000 páginas de partituras sintetizadas con MuseScore, con anotaciones para
  > detección y clasificación de objetos musicales (notas, figuras, alteraciones, etc.),
  > incluyendo muchos objetos pequeños y densos.
- **Relevancia para Cadenza:** Media — útil para evaluar el componente de detección del pipeline
  (y como corpus inicial de pruebas, aunque es sintético y de música digital, no fotos).
- **Notas / ideas:**
  - No es de fotos/escaneos: no cubre degradación de imagen, pero sí variabilidad de notación.
  - Posible fuente para pre-entrenar/validar modelos si se decide reentrenar.

### [DS-002] CAPTAIN — dataset sintético de partituras (verificar)
- **Autores:** Calvo-Zaragoza, J., Rizo, D. (introducido en DL-001)
- **Año / Venue:** 2018 — **verificar** (paper específico del dataset)
- **DOI / URL:** pendiente de confirmar
- **Tags:** dataset, sintético, monofónico, pianoform
- **Abstract (resumen parafraseado):**
  > Dataset de partituras sintetizadas a partir de archivos simbólicos (procedimiento
  > *Camera-Printer*): se generan imágenes realistas de partituras monofónicas y *pianoform*
  > para entrenar y evaluar OMR end-to-end.
- **Relevancia para Cadenza:** Media — corpus inicial útil mientras se consigue el corpus real;
  coincide con el alcance (monofónicas, piano).
- **Notas / ideas:**
  - Verificar el paper exacto del dataset y el acceso (¿descargable públicamente?).

### [DS-003] HOMUS — Handwritten Online Musical Symbols (símbolos musicales manuscritos)
- **Autores:** Jorge Calvo-Zaragoza, José Oncina
- **Año / Venue:** 2014, Proc. de la 22.ª ICPR (Estocolmo), pp. 3038–3043
- **DOI / URL:** https://doi.org/10.1109/ICPR.2014.524 · sitio oficial: http://grfia.dlsi.ua.es/homus/ · catálogo: https://apacha.github.io/OMR-Datasets/#handwritten-online-musical-symbols-homus
- **Tags:** dataset, manuscrito, online, trazos, clasificación
- **Abstract (resumen parafraseado):**
  > Dataset de referencia con ~15.200 muestras para el reconocimiento de notación musical manuscrita
  > **online**: se registraron los trazos (*strokes*) que los músicos escribieron con lápiz sobre una
  > tableta Samsung, y las muestras pueden usarse tanto en escenarios online (secuencias de trazos)
  > como offline (renderizando imágenes). Contiene ~20 artefactos/misclasificaciones conocidas que
  > Alexander Pacha corrigió (github.com/apacha/Homus).
- **Relevancia para Cadenza:** Media — dataset de **símbolos aislados** manuscritos (no páginas
  completas); ahora dentro del alcance (manuscritas modernas): útil para entrenar/evaluar
  clasificadores de símbolos del subconjunto manuscrito.
- **Notas / ideas:**
  - Ojo: es de trazos online, no imágenes de partituras completas — no sirve para evaluar el pipeline
    end-to-end de Cadenza (para eso: Smashcima DS-007 o el dataset del proyecto Anonymous en AL-003).
  - Paper original: Calvo-Zaragoza & Oncina, "Recognition of Pen-Based Music Notation: The HOMUS
    Dataset", ICPR 2014.
  - El corpus objetivo de Cadenza incluye **impresas y manuscritas modernas**; las históricas quedan excluidas.

### [DS-004] PRinS — dataset de partituras impresas (verificar)
- **Autores:** Ríos-Vila, A., et al. (U. de Alicante)
- **Año / Venue:** aprox. 2023 — **verificar**
- **DOI / URL:** pendiente de confirmar
- **Tags:** dataset, impresas, omr
- **Abstract (resumen parafraseado):**
  > Dataset de partituras impresas reales (libros de piano, etc.) con anotaciones, diseñado para
  > entrenar y evaluar OMR sobre material impreso real.
- **Relevancia para Cadenza:** Media-Alta (si se confirma) — el más cercano al corpus objetivo
  (impresas, piano).
- **Notas / ideas:**
  - Confirmar disponibilidad pública y formato de anotaciones.

### [DS-005] Optical Music Recognition in Manuscripts from the Ricordi Archive
- **Autores:** no especificados en el abstract — verificar
- **Año / Venue:** 2024, ACM (verificar venue — posible DLfM/JCDL)
- **DOI / URL:** https://doi.org/10.1145/3678299.3678324
- **Tags:** archivo, manuscritos, anotación, dataset público, clasificación
- **Abstract (texto del paper):**
  > The Ricordi archive, a prestigious collection of significant musical manuscripts from renowned opera composers such as Donizetti, Verdi and Puccini, has been digitized. This process has allowed us to automatically extract samples that represent various musical elements depicted on the manuscripts, including notes, staves, clefs, erasures, and composer's annotations, among others. To distinguish between digitization noise and actual music elements, a subset of these images was meticulously grouped and labeled by multiple individuals into several classes. After assessing the consistency of the annotations, we trained multiple neural network-based classifiers to differentiate between the identified music elements. The primary objective of this study was to evaluate the reliability of these classifiers, with the ultimate goal of using them for the automatic categorization of the remaining unannotated data set. The dataset, complemented by manual annotations, models, and source code used in these experiments are publicly accessible for replication purposes.
- **Relevancia para Cadenza:** Alta — caso real de digitalización de un archivo musical (Donizetti, Verdi, Puccini) con **dataset, anotaciones, modelos y código públicos**; precedente directo para el riesgo principal del proyecto (acceso a corpus de un archivo).
- **Notas / ideas:**
  - El flujo "digitalizar → muestrear → anotar (multi-persona) → evaluar consistencia → clasificar" es un modelo a seguir para el corpus de Cadenza.
  - Anotación multi-anotador + medición de consistencia → aplicar en la interfaz de corrección (¿cuándo confiar en el usuario?).

### [DS-006] MuNG Studio: Annotation Tool for Music Notation Graph
- **Autores:** no especificados en el abstract — verificar
- **Año / Venue:** 2025, ACM DLfM (verificar)
- **DOI / URL:** https://dl.acm.org/doi/10.1145/3748336.3748379
- **Tags:** anotación, mung, muscima++, visualización, web
- **Abstract (texto del paper):**
  > This paper introduces MuNG Studio, a new annotation tool for the Music Notation Graph (MuNG) format. MuNG is a high-detail graphical annotation format designed for Optical Music Recognition tasks, originally proposed for the MUSCIMA++ dataset in 2017. MUSCIMA++ had a significant impact on the OMR community; however, most subsequent datasets made little use of the full MuNG format. This was likely due to the lack of user-friendly tools supporting the format. The new MuNG Studio seeks to provide an easy-to-install web-based viewer and editor for the MuNG format with the goal of expanding and supporting the now growing ecosystem around MuNG.
- **Relevancia para Cadenza:** Media — herramienta de anotación (visor/editor web) del formato MuNG; útil si Cadenza genera o consume anotaciones de nivel gráfico (MUSCIMA++).
- **Notas / ideas:**
  - Si el corpus necesita anotaciones detalladas (objetos + relaciones), MuNG Studio es el estándar de facto para editarlas.

### [DS-007] Smashcima: Full-Page Handwritten Music Document Synthesizer
- **Autores:** Hajič Jr., J., et al. (candidato — verificar)
- **Año / Venue:** 2025, ACM DLfM (verificar)
- **DOI / URL:** https://dl.acm.org/doi/10.1145/3748336.3748380
- **Tags:** datos sintéticos, manuscrito, musicxml, mung, aumentación
- **Abstract (texto del paper):**
  > Despite massive progress made in Optical Music Recognition (OMR) with deep learning, data scarcity remains an issue, especially for manuscripts. Synthetic data has been shown to alleviate this issue, but no tool for rendering a handwritten page from structured encoding such as MusicXML exists. This paper introduces Smashcima, a framework for the creation of synthetic handwritten full-page music images. It accepts MusicXML files and produces images with full information on their glyphs, segmentation masks, keypoints, notation graph, and semantics. It is compatible with the MuNG format and so can also be used to produce synthetic training data object detection and graph models. It can synthesize images of all levels of complexity of music notation, including pianoform music. Smashcima thus greatly increases the value of dataset acquisition, as it can expand a small manually annotated dataset to the scale of arbitrary available MusicXML data, thereby alleviating manuscript data scarcity for OMR.
- **Relevancia para Cadenza:** Media — síntesis de páginas completas (incl. pianoform) desde MusicXML con anotaciones completas; puede ampliar un corpus anotado pequeño para reentrenar el modelo.
- **Notas / ideas:**
  - Para el ciclo de aprendizaje activo: si el corpus real es pequeño, Smashcima + MusicXML existente puede generar datos de entrenamiento — ahora directamente aplicable porque las **manuscritas modernas están dentro del alcance** de Cadenza.
  - Misma línea que CAPTAIN/DeepScores (síntesis) pero con anotaciones a nivel de página completa.

### [DS-008] PrIMuS / Camera-PrIMuS — Printed Images of Music Staves (impresas monofónicas)
- **Autores:** Jorge Calvo-Zaragoza, David Rizo
- **Año / Venue:** 2018 — Applied Sciences 8(4):606 (PrIMuS); ISMIR 2018 (Camera-PrIMuS)
- **DOI / URL:** sitio oficial: https://grfia.dlsi.ua.es/primus/ · paper PrIMuS: https://doi.org/10.3390/app8040606 · paper Camera-PrIMuS: http://ismir2018.ircam.fr/doc/pdfs/33.pdf
- **Tags:** dataset, impresas, monofónico, incipits, ground truth
- **Abstract (resumen parafraseado):**
  > PrIMuS contiene 87.678 incipits de música real (tomados del catálogo RISM) en cinco formatos:
  > imagen PNG, MIDI, MEI y dos codificaciones propias (agnostic y semantic). Camera-PrIMuS
  > extiende el mismo corpus con distorsiones que simulan fotografías tomadas en condiciones
  > reales. Es el dataset estándar para OMR end-to-end monofónico.
- **Relevancia para Cadenza:** Alta — **corpus oficial de evaluación** para el subconjunto impreso
  monofónico; ground truth simbólico listo para comparar contra la salida MusicXML.
- **Notas / ideas:**
  - El paper de PrIMuS es el mismo DL-001 (Applied Sciences 2018).
  - Camera-PrIMuS cubre el caso "foto de partitura" sin necesidad de corpus físico.
  - Licencia no especificada — confirmar condiciones de uso académico.

### [DS-009] MUSCIMA++ / CVC-MUSCIMA — manuscritas modernas anotadas
- **Autores:** Jan Hajič Jr., Pavel Pecina (MUSCIMA++); Alicia Fornés et al. (CVC-MUSCIMA)
- **Año / Venue:** 2017, ICDAR (MUSCIMA++); 2012, IJDAR 15(3) (CVC-MUSCIMA)
- **DOI / URL:** https://ufal.mff.cuni.cz/muscima · desarrollo: https://github.com/OMR-Research/muscima-pp · paper: https://doi.org/10.1109/ICDAR.2017.16
- **Tags:** dataset, manuscritas modernas, mung, detección, ground truth
- **Abstract (resumen parafraseado):**
  > MUSCIMA++ anota 91.255 símbolos (primitivas y objetos de alto nivel, como armaduras) sobre 140
  > páginas manuscritas derivadas de CVC-MUSCIMA — partituras escritas a mano por 50 músicos
  > actuales en notación moderna. Usa el formato gráfico MuNG, que explicita las relaciones entre
  > primitivas. Licencia CC BY-NC-SA 4.0. CVC-MUSCIMA (Fornés et al., 2012) es su base: 1.000
  > páginas, 50 escribas, 20 páginas cada uno.
- **Relevancia para Cadenza:** Alta — **corpus oficial de evaluación** para el subconjunto manuscrito
  moderno; ground truth a nivel de símbolo.
- **Notas / ideas:**
  - Formato MuNG: compatible con MuNG Studio (DS-006) para anotación y Smashcima (DS-007) para síntesis.
  - Al citar MUSCIMA++ debe citarse también CVC-MUSCIMA (dataset derivado).

## Corpus objetivo del proyecto (definido: alcance y fuente)

Criterios acordados en la idea del proyecto (actualizado: se incluyen manuscritas modernas):

- **Tipo:** partituras impresas (escaneos/fotos) **y partituras escritas a mano actuales** (notación moderna, papel pautado), monofónicas o piano simple.
- **Excluido:** orquesta completa, partituras muy densas, **manuscritos históricos** (notación antigua/mensural, degradados).
- **Fuente (decisión del equipo):** datasets públicos con ground truth — **terna oficial de
  evaluación**: PrIMuS/Camera-PrIMuS (impresas monofónicas, DS-008), SMB (monofonía + pianoform,
  FM-005) y MUSCIMA++ (manuscritas modernas, DS-009). Se descarta la negociación de corpus real con
  una institución: el riesgo principal de disponibilidad de corpus queda resuelto.
- **Piloto real complementario:** 10–20 partituras reales (fotos/escaneos, sin ground truth) para
  la evaluación de usabilidad — flujo completo, tiempos de corrección y errores detectados por el
  validador. No requiere negociación formal: profesores, agrupaciones locales o conocidos músicos.
- **Formato esperado de salida:** MusicXML / MIDI para comparar contra el ground truth de cada dataset.

Preguntas a resolver en la etapa de documentación:

1. Confirmar descargas y licencias de la terna (PrIMuS y Camera-PrIMuS: grfia.dlsi.ua.es/primus; SMB: Zenodo; MUSCIMA++: CC BY-NC-SA 4.0 — adecuado para fines académicos).
2. Definir splits de evaluación (SMB trae splits estándar; definir la división para PrIMuS y MUSCIMA++).
3. Definir el puente de ground truth: los formatos difieren (MEI, agnostic/semantic, **kern, MuNG) y la salida de oemer es MusicXML — fijar la métrica de comparación (SER, OMR-NED [FM-005]).
4. Decidir si Camera-PrIMuS cubre el caso "foto" o se requiere aumentación adicional.

## Dónde buscar más

- **Palabras clave:** "OMR dataset", "sheet music dataset", "printed music dataset",
  "handwritten music dataset", "music symbol dataset".
- **Venues / repos:** ISMIR papers, Zenodo, GitHub (búsqueda "OMR dataset"), datasets del grupo
  Calvo-Zaragoza (U. de Alicante).
- **Estrategia:** hacer un inventario de datasets disponibles (con acceso y licencia) en una tabla,
  y marcar cuáles sirven para: (a) pruebas iniciales, (b) pre-entrenamiento, (c) evaluación final.
