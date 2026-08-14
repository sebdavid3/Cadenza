# Notas de Investigación y Análisis de la Literatura: Cadenza

Este documento recopila las ideas principales del proyecto **Cadenza** y extrae los puntos clave de la literatura existente (repartida en los 7 temas de investigación en `docs/literatura/`), con el fin de consolidar el marco teórico, el aporte único del proyecto y la justificación de sus decisiones metodológicas.

---

## 1. Idea Principal de Cadenza

**Cadenza** es una **Plataforma de Digitalización Asistida de Partituras** (etapa de proyecto de grado). Su objetivo no es simplemente lograr un reconocimiento automático más preciso (que es el enfoque típico de la investigación pura en OMR), sino **integrar de forma usable el reconocimiento automático en el flujo de trabajo de un transcriptor humano**.

El aporte único radica en cerrar la brecha entre la salida imperfecta del modelo OMR y la partitura digital final mediante un sistema interactivo de tres pilares:
1. **Validación Automática por Reglas Musicales:** El sistema audita la salida sintáctica y teórica del OMR (duraciones de compás, coherencia de armaduras, etc.) y detecta inconsistencias automáticamente.
2. **Corrección Humana Asistida (Human-in-the-Loop - HITL):** En lugar de revisar toda la partitura de arriba abajo, el transcriptor se enfoca en las zonas señaladas como "sospechosas" por el motor de validación, ahorrando tiempo y esfuerzo cognitivo.
3. **Ciclo de Aprendizaje Activo (Active Learning - AL):** Las correcciones del usuario se aprovechan para reentrenar y mejorar progresivamente el modelo de reconocimiento, optimizando el rendimiento con el menor volumen de datos etiquetados posible.

---

## 2. Puntos Clave Extraídos de la Literatura

A continuación se detallan los hallazgos críticos de la literatura clasificados según los módulos de Cadenza:

### A. El Proceso OMR y el Modelo Base (Tema 01 y 02)
* **Taxonomía Clásica:** El pipeline clásico de OMR consta de: *Preprocesado* $\rightarrow$ *Detección/Eliminación de Pentagramas* $\rightarrow$ *Detección de Símbolos* $\rightarrow$ *Clasificación* $\rightarrow$ *Ensamblaje y Reconstrucción Musical* (Calvo-Zaragoza et al., 2020).
* **Enfoque End-to-End (E2E):** Los sistemas modernos de Deep Learning (como CNN+BiLSTM+CTC o Transformers) eliminan la segmentación manual de símbolos, leyendo secuencias directamente (Calvo-Zaragoza & Rizo, 2018). Sin embargo, siguen teniendo dificultades en partituras polifónicas complejas o partituras manuscritas debido a la variabilidad de trazos (Ríos-Vila et al., 2026).
* **Tecnología Base (oemer):** Se utilizará la librería Python `oemer` como transcriptor base. Es un pipeline neuronal completo que exporta a MusicXML. Documentar sus fallas recurrentes (ej. acordes densos, alteraciones) servirá de insumo para afinar las reglas de validación.

### B. Validación Musical Post-OMR (Tema 03)
* **El Vacío en la Literatura:** Este es el componente con **menor literatura consolidada**. La mayoría de los trabajos post-OMR proponen modelos de lenguaje estadísticos (n-gramas o transformers aplicados al texto musical) para reordenar las predicciones del OMR.
* **Aporte de Cadenza:** Cadenza usará una aproximación basada en **reglas de teoría musical** robustas e interpretables implementadas con la biblioteca `music21` (Cuthbert & Ariza, 2010).
* **Reglas de Validación Clave:**
  * **Consistencia Rítmica:** Suma de duraciones de notas/silencios en cada compás $\equiv$ indicación de compás (Time Signature).
  * **Consistencia Tonal:** Notas alteradas frente a la armadura (Key Signature) y alteraciones accidentales dentro del mismo compás.
  * **Rango Físico:** Altura de notas que excedan rangos físicamente lógicos para el pentagrama/instrumento.
  * **Sintaxis de Notación:** Cierre de ligaduras de expresión (slurs), llaves y barras de compás.

### C. Human-in-the-Loop (HITL) y Experiencia de Usuario (Tema 04)
* **El Problema de la Edición Convencional:** Trabajos como Rizo et al. (2023) demuestran que corregir una partitura mal reconocida en un editor tradicional (como MuseScore o Sibelius) consume tanto tiempo como transcribirla desde cero.
* **Precedentes de Interfaz:** Herramientas como *Audiveris*, *MuRET* y *OMRAT* proponen corregir visualmente sobre la imagen original. Cadenza debe adoptar esta filosofía:
  * Mostrar la partitura original (imagen) con cajas de colisión interactivas que resalten los errores de validación.
  * Facilitar la corrección rápida (por ejemplo, corregir una altura arrastrando la nota o cambiar la duración con un atajo de teclado).

### D. Aprendizaje Activo (Active Learning) y Sus Retos (Tema 05)
* **Hallazgo Crítico (MLSP 2025):** El primer estudio que aplicó Aprendizaje Activo en OMR sobre manuscritos concluyó que **la selección por incertidumbre (uncertainty sampling a nivel de píxel/caja) NO fue efectiva** debido a la alta correlación y redundancia en partituras.
* **Estrategia Adaptativa para Cadenza:**
  1. En lugar de seleccionar muestras a nivel de símbolo individual, Cadenza debe explorar la selección **a nivel de partitura completa** o fragmento musical significativos (compás, sistema).
  2. Implementar estrategias basadas en la **diversidad de las muestras** y la consistencia teórica del motor de validación (ej. priorizar partituras donde el validador encuentre patrones de error inusuales o nuevos tipos de fallas).
  3. Utilizar enfoques semi-supervisados (como modelado de incertidumbre GMM o Pseudo-Labeling) para integrar las correcciones humanas sin corromper el modelo base.

### E. Estrategia de Corpus y Evaluación (Tema 06 y 07)
* **Resolución del Riesgo de Corpus:** Se descarta depender de la negociación y acceso a archivos reales (históricamente lento e incierto). La evaluación cuantitativa de Cadenza se realizará sobre una **terna de datasets públicos con Ground Truth**:
  1. **PrIMuS y Camera-PrIMuS:** Para música impresa monofónica (el segundo introduce distorsiones físicas realistas de cámara).
  2. **Sheet Music Benchmark (SMB):** Estándar de la industria (2026) que incluye monofonía y formato piano (*pianoform*).
  3. **MUSCIMA++:** Para el subconjunto de manuscritos modernos.
* **Piloto Real:** Se complementará con 10–20 partituras fotografiadas reales para una evaluación heurística de usabilidad y esfuerzo de edición (tiempo de corrección).
* **Métricas Clave:**
  * **SER (Symbol Error Rate):** Métrica clásica de alineación de símbolos.
  * **OMR-NED (OMR Normalized Edit Distance):** Introducida en 2026 por el SMB, detalla los errores por tipo (cabezas de nota, ligaduras, alteraciones, alturas y duraciones).
  * **Tasa de reducción de esfuerzo:** Tiempo de corrección con la UI de Cadenza vs. edición tradicional.

---

## 3. Conclusiones para la Tesis

1. **Justificación del Aporte:** La tesis se posicionará no como una mejora algorítmica de OMR, sino como un **diseño de interacción inteligente** (Machine Learning Interactivo) y un **motor de reglas semánticas** que hacen viable la digitalización en el mundo real.
2. **Definición de Alcance Clara:** Monofonía e impreso/manuscrito moderno (piano simple). Excluye manuscritos históricos y orquestas complejas.
3. **Estrategia Metodológica:** Usar `music21` para validación, datasets públicos para métricas reproducibles (SER y OMR-NED), y medir el factor humano mediante el piloto real.
