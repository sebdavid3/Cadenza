# 07 — Formatos (MusicXML/MIDI) y Métricas de Evaluación

Formatos de representación simbólica de música (entrada/salida del sistema) y métricas para evaluar
la calidad del OMR. Alimenta la **salida del sistema** (MusicXML/MIDI) y el capítulo de
**Experimentación** de la tesis.

## Índice

| ID | Título | Año | Relevancia |
|---|---|---|---|
| FM-001 | MusicXML 4.0 (especificación W3C) | 2021 | Alta |
| FM-002 | MEI — Music Encoding Initiative | 2011 | Media |
| FM-003 | MIDI 1.0 (especificación) | 1996 | Media |
| FM-004 | music21 (paper ISMIR 2010) | 2010 | Alta |
| FM-005 | Sheet Music Benchmark (SMB) + métrica OMR-NED | 2026 | Alta |

## Fichas

### [FM-001] MusicXML 4.0 — especificación
- **Autores:** W3C Music Notation Community Group (Michael Good, et al.)
- **Año / Venue:** 2021, estándar W3C
- **DOI / URL:** https://www.w3.org/2021/06/musicxml40/
- **Tags:** musicxml, formato, estándar
- **Abstract (resumen parafraseado):**
  > MusicXML es el estándar abierto de intercambio de notación musical digital, basado en XML:
  > representa notas, ritmos, armaduras, compases, voces e instrumentos. Es el formato de
  > **salida de oemer** y el formato editable objetivo de Cadenza.
- **Relevancia para Cadenza:** Alta — define el contrato de salida del sistema y la estructura de
  datos sobre la que opera el motor de validación.
- **Notas / ideas:**
  - Conocer los elementos clave (notes, pitch, duration, divisions, voice, measure, key, time).
  - Validar la salida de oemer contra el esquema de MusicXML 4.0 (¿es válida?).

### [FM-002] The Music Encoding Initiative as a Document-Encoding Framework
- **Autores:** Andrew Hankinson, Perry Roland, Ichiro Fujinaga
- **Año / Venue:** 2011, Proc. de la 12.ª ISMIR
- **DOI / URL:** https://music-encoding.org/ (sitio oficial)
- **Tags:** mei, formato, musicología digital
- **Abstract (resumen parafraseado):**
  > MEI es un estándar XML para codificar documentos musicales con foco en la representación fiel
  > de la fuente (incluye aspectos editoriales), orientado a bibliotecas digitales y musicología.
- **Relevancia para Cadenza:** Media — comparar con MusicXML; MEI puede ser útil si se requiere
  representar dudas/correcciones del reconocimiento (niveles de certeza) o si el corpus del archivo
  lo exige.
- **Notas / ideas:**
  - Decidir temprano si la plataforma exporta solo MusicXML o también MEI.

### [FM-003] MIDI 1.0 — especificación
- **Autores:** MIDI Manufacturers Association (MMA)
- **Año / Venue:** 1996 (especificación consolidada), vigente
- **DOI / URL:** https://www.midi.org/
- **Tags:** midi, formato, estándar
- **Abstract (resumen parafraseado):**
  > MIDI es el protocolo/estándar de comunicación musical digital; como formato de archivo
  > representa eventos (nota on/off, tempo, programa) sin notación visual completa. Es el segundo
  > formato de **salida** objetivo de Cadenza.
- **Relevancia para Cadenza:** Media — como salida complementaria (reproducción/escucha de la
  transcripción) y para evaluación de exactitud de alturas/ritmos.
- **Notas / ideas:**
  - La conversión MusicXML→MIDI es directa (music21, MuseScore); la inversa pierde notación visual.

### [FM-004] music21: A Toolkit for Computer-Aided Musicology and Symbolic Music Data
- **Autores:** Michael Scott Cuthbert, Christopher Ariza
- **Año / Venue:** 2010, Proc. de la 11.ª ISMIR
- **DOI / URL:** https://web.mit.edu/music21/ · https://github.com/cuthbertLab/music21
- **Tags:** music21, python, musicxml, análisis
- **Abstract (resumen parafraseado):**
  > Ver ficha VAL-001 (misma referencia). Desde el punto de vista de formatos: música21 lee y
  > escribe MusicXML (y otros), permitiendo convertir entre formatos y analizar la salida del OMR.
- **Relevancia para Cadenza:** Alta — puente práctico entre MusicXML, MIDI y el motor de validación.
- **Notas / ideas:**
  - Herramienta central para el prototipo: parsear salida de oemer, validar, exportar MIDI.

### [FM-005] Sheet Music Benchmark (SMB): Standardized Optical Music Recognition Evaluation
- **Autores:** J. C. Martinez-Sevilla, J. Cerveto-Serrano, N. Luna, G. Chapman, C. Sapp, D. Rizo, J. Calvo-Zaragoza (según línea de copyright del paper)
- **Año / Venue:** 2026 (Zenodo — verificar venue, posible ISMIR 2026)
- **DOI / URL:** https://doi.org/10.5281/zenodo.17706531
- **Tags:** benchmark, evaluación, omr-ned, ser, humdrum, **kern
- **Abstract (texto del paper):**
  > In this work, we introduce the Sheet Music Benchmark (SMB), a dataset of six hundred and eighty-five pages specifically designed to benchmark Optical Music Recognition (OMR) research. SMB encompasses a diverse array of musical textures, including monophony, pianoform, quartet, and others, all encoded in Common Western Modern Notation using the Humdrum **kern format. Alongside SMB, we introduce the OMR Normalized Edit Distance (OMR-NED), a new metric tailored explicitly for evaluating OMR performance. OMR-NED builds upon the widely-used Symbol Error Rate (SER), offering a finegrained and detailed error analysis that covers individual musical elements such as note heads, beams, pitches, accidentals, and other critical notation features. The resulting numeric score provided by OMR-NED facilitates clear comparisons, enabling researchers and end-users alike to identify optimal OMR approaches. Our work thus addresses a long-standing gap in OMR evaluation, and we support our contributions with baseline experiments using standardized SMB dataset splits for training and assessing state-of-the-art methods.
- **Relevancia para Cadenza:** Alta — benchmark estandarizado que incluye **monofonía y pianoform** (el corpus objetivo de Cadenza) con splits estándar y una métrica nueva (OMR-NED) sobre SER → candidato principal para la evaluación de la plataforma.
- **Notas / ideas:**
  - Adoptar OMR-NED (o al menos SER con su desglose por elemento) como métrica de referencia en la experimentación.
  - Humdrum **kern como formato de ground truth → evaluar si Cadenza necesita convertirlo (music21 puede leer **kern).
  - Agregar a la tabla de métricas candidatas de la tesis (sección siguiente).

## Métricas de evaluación (a definir en la tesis)

Candidatas iniciales (completar con la sección de evaluación del survey OMR-001):

| Métrica | Qué mide | Nivel |
|---|---|---|
| Error a nivel de nota (note-level accuracy) | % de notas correctas (altura+duración) | Nota |
| Symbol error rate (SER) | errores de símbolos tras alineación | Símbolo |
| Exactitud de compases/voces | consistencia métrica | Estructural |
| Precisión de armadura/tonalidad | corrección de la signatura | Global |
| Tasa de correcciones manuales | cuántos errores detecta/corrige el usuario | UX |
| Esfuerzo de corrección (tiempo/partitura) | eficiencia de la interfaz | UX |
| Reducción de errores con feedback | mejora del modelo tras correcciones (aprendizaje activo) | Sistema |

## Dónde buscar más

- **Palabras clave:** "MusicXML", "MEI", "OMR evaluation metrics", "symbolic music representation",
  "score comparison metrics".
- **Venues:** ISMIR, Music Encoding Conference, W3C.
- **Estrategia:** fijar el conjunto de métricas ANTES de la experimentación (para no mover el
  criterio después); revisar cómo evalúan oemer/Audiveris/MuRET para comparabilidad.
