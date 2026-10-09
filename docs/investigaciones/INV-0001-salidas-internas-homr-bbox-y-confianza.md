# INV-0001: Salidas internas de HOMR — Coordenadas espaciales (bbox) y confianza del modelo

- **Fecha:** 2026-10-07
- **Autores:** Equipo de Arquitectura de Cadenza
- **Issues asociados:** [#14](https://github.com/sebdavid3/Cadenza/issues/14) y [#31](https://github.com/sebdavid3/Cadenza/issues/31)
- **Relacionado:** [ADR-0005](../adr/ADR-0005-motor-omr-homr-baseline-oemer.md), [ADR-0008](../adr/ADR-0008-active-learning-model-registry.md), [ADR-0002](../adr/ADR-0002-score-document-anchor-index.md)
- **Estado:** Completada (Resultado negativo documentado para granularidad por evento)

---

## 1. Motivación y objetivos

El modelo `ScoreDocument` y las anclas (`Anchor`) de Cadenza contemplan dos campos opcionales:
- `bbox`: Coordenadas rectangulares `(x1, y1, x2, y2)` para proyectar *overlays* visuales interactivos sobre la imagen escaneada en el visor web (HITL).
- `confidence`: Nivel de certidumbre del reconocedor `[0.0, 1.0]` por evento para guiar estrategias de aprendizaje activo por incertidumbre (`UncertaintyAcquisition`).

Actualmente, solo el adaptador de pruebas (`FakeOMREngine`) genera rectángulos sintéticos y confianzas simuladas. Con el motor real (`HOMREngine`), las partituras se obtienen a través del MusicXML producido por HOMR (`homr>=0.7`), el cual se procesa con `music21` hacia el `ScoreIR` neutral. La salida carece de coordenadas y de confianza.

Esta investigación técnica examina en profundidad las entrañas del paquete `homr==0.7.0` (código fuente y grafos ONNX) para responder:
1. **Issue #14:** ¿Es posible extraer coordenadas espaciales reales por evento, compás o pentagrama desde HOMR?
2. **Issue #31:** ¿Es posible extraer probabilidades o niveles de certidumbre del decodificador de HOMR?

---

## 2. Análisis del flujo interno de HOMR (`homr==0.7.0`)

HOMR desacopla el reconocimiento en dos etapas independientes:

### Etapa 1: Segmentación y detección de pentagramas (`homr.segmentation`)
1. **SegNet ONNX (`inference_segnet.py`):** Red de segmentación semántica que clasifica píxeles en cinco canales: `staff`, `symbols`, `notehead`, `stems_rests` y `clefs_keys`.
2. **Extracción morfológica (`bounding_boxes.py`, `staff_detection.py`):**
   - Agrupa píxeles de pentagrama en fragmentos y los ajusta para derivar instancias `MultiStaff` y `Staff` con coordenadas absolutas en la imagen (`min_x`, `max_x`, `min_y`, `max_y`).
   - Detecta candidatos elípticos de cabezas de nota (`BoundingEllipse`) y barras de compás/plicas (`RotatedBoundingBox`).
   - HOMR permite exportar estas coordenadas de pentagramas a disco si `write_staff_positions=True` (`save_staff_positions(...)` en `staff_position_save_load.py`).

### Etapa 2: Reconocimiento secuencial con Transformer (`homr.transformer` / TrOmr)
1. **Recorte y dewarping del pentagrama (`staff_dewarping.py`, `staff_parsing.py`):**
   - Para cada pentagrama detectado, HOMR recorta la tira horizontal de la imagen, endereza las líneas de pentagrama (*dewarping*) y redimensiona el recorte a un lienzo normalizado de tamaño fijo `(max_height=192, max_width=2048)`.
2. **Encoder-Decoder Transformer (`Staff2Score`, `ScoreDecoder` en `decoder_inference.py`):**
   - El Encoder procesa el lienzo del pentagrama produciendo un mapa de características contextuales `context`.
   - **Crucial:** El Transformer **no** recibe ni utiliza los bounding boxes morfológicos calculados en la etapa de segmentación. La predicción de notas es puramente secuencial autorregresiva de izquierda a derecha.
3. **Generación de MusicXML (`music_xml_generator.py`):**
   - Los símbolos predichos (`EncodedSymbol`) se transforman sintácticamente en compases, notas, silencios y alteraciones, y se serializan a un archivo `.musicxml` en disco.

---

## 3. Hallazgos sobre Coordenadas Espaciales (Issue #14)

### 3.1 Lo que expone HOMR internamente
- **A nivel de pentagrama (`Staff`):**
  - HOMR calcula y almacena con alta precisión los polígonos y cajas envolventes de cada sistema/pentagrama en la imagen original (`MultiStaff.staffs`).
  - Las posiciones están disponibles antes de la invocación del Transformer y son serializables mediante `save_staff_positions`.
- **A nivel de eventos individuales (notas, figuras):**
  - En la clase `ScoreDecoder.generate()`, cada token generado registra un atributo `coordinates = attention` a partir del mapa de atención cruzada del decodificador.
  - No obstante, los propios autores de HOMR documentan en `homr/transformer/vocabulary.py` (líneas 282–286):
    > *"These coordinates are derived from transformer attention and are inherently imprecise, since the model is optimized for predictive accuracy rather than spatial localization. Because patch tokens are processed in raster order (top-to-bottom, left-to-right), this ordering can be used to reject cases where attention-based coordinates violate monotonic scan constraints and are therefore unreliable."*
  - Al generar el MusicXML final (`music_xml_generator.py`), HOMR **descarta por completo estas coordenadas de atención**. El archivo XML resultante no contiene atributos espaciales (`default-x`, `default-y`).

### 3.2 Conclusión técnica para el Issue #14
- **Negativo para eventos individuales:** No es técnica ni científicamente viable obtener `bbox` precisas por evento musical desde HOMR sin sustituir o complementar el motor con un detector de objetos explícito (p. ej. YOLO-OBB o Mask R-CNN entrenado sobre símbolos musicales). Las coordenadas de atención son meramente aproximadas y colapsan en acordes, polifonía o compases densos.
- **Viable a nivel de pentagrama:** Es factible obtener la caja envolvente de cada pentagrama/sistema (`staff bbox`).

### 3.3 Recomendación de diseño
- **Interfaz HITL / Visor web:** No condicionar la usabilidad del editor a overlays de notas individuales sobre la imagen escaneada para motores de transcripción basados en secuencias (como HOMR o TrOCR). El visor debe apoyarse primordialmente en la partitura vectorial interactiva renderizada con OSMD/Verovio, utilizando el recorte o resaltado del pentagrama activo (`staff bbox`) como referencia visual en la imagen original.

---

## 4. Hallazgos sobre Confianza del Modelo (Issue #31)

### 4.1 Lo que expone el decodificador de HOMR
- En `homr/transformer/decoder_inference.py`, el método `ScoreDecoder.generate()` ejecuta la sesión ONNX con `io_binding` y recupera los logits directos:
  ```python
  rhythmsp = outputs[0].numpy()
  pitchsp = outputs[1].numpy()
  liftsp = outputs[2].numpy()
  ```
- Inmediatamente aplica decodificación voraz (*greedy decoding*) mediante `argmax`:
  ```python
  rhythm_sample = np.array([[rhythmsp[:, -1, :].argmax()]])
  pitch_sample = np.array([[pitchsp[:, -1, :].argmax()]])
  ```
- **HOMR no calcula softmax**, no calcula entropía ni probabilidades normalizadas posteriores, ni guarda los logits en `EncodedSymbol`.
- La interfaz pública de HOMR escribe el resultado en un archivo `.musicxml`. El estándar MusicXML 4.0 no cuenta con campos para almacenar la probabilidad de reconocimiento de un modelo de machine learning.

### 4.2 Conclusión técnica para el Issue #31
- **Resultado negativo documentado:** El motor HOMR en su API e integración estándar no expone probabilidades de certidumbre. Hackear el runtime de ONNX para interceptar los tensores requeriría bifurcar (*fork*) el paquete `homr`, recalcular softmax en 6 ramas independientes de logits por token y definir un mecanismo ad-hoc para transportar esos escalares fuera de MusicXML.

### 4.3 Ajuste al diseño de Aprendizaje Activo (ADR-0008)
- En Cadenza, `UncertaintyAcquisition` opera sobre `sample.error_density` (densidad de violaciones de reglas de teoría musical detectadas por el módulo `validation`).
- Esta formulación es plenamente coherente con la naturaleza **neuro-simbólica** de Cadenza: a falta de probabilidades calibradas del modelo de caja negra, el conocimiento musical del dominio actúa como estimador de incertidumbre y necesidad de corrección.
- Se documenta esta correspondencia formal: en Cadenza, la "incertidumbre" de la línea base es la incertidumbre informada por reglas simbólicas (`error_density`), contrastada con la diversidad del embedding (`DiversityAcquisition`) y la estrategia híbrida (`HybridAcquisition`).

---

## 5. Decisiones y cierre de issues

1. **Cierre de Issue #14:** Concluido con resultado negativo documentado para `bbox` por evento, y factibilidad documentada a nivel de pentagrama. No se creará issue de implementación para bounding boxes individuales en HOMR; el diseño del visor se basará en renderizado vectorial interactivo y referencia por pentagrama.
2. **Cierre de Issue #31:** Concluido con resultado negativo documentado para probabilidades directas de HOMR. Se mantiene la señal simbólica de densidad de errores como métrica de selección de la línea base de incertidumbre, quedando explícitamente documentado en `ADR-0008` y en el código de `UncertaintyAcquisition`.
