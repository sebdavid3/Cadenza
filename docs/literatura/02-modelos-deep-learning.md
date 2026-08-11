# 02 — Modelos de Aprendizaje Profundo para OMR

Arquitecturas basadas en deep learning para el reconocimiento óptico de música: CNNs, redes
secuencia-a-secuencia, *object detection* y enfoques *end-to-end*. Alimenta el **Modelo OMR base**
(oemer se basa en estos enfoques) y el Marco Teórico/Estado del Arte.

## Índice

| ID | Título | Año | Relevancia |
|---|---|---|---|
| DL-001 | End-to-End Neural Optical Music Recognition of Monophonic Scores | 2018 | Alta |
| DL-002 | End-to-end optical music recognition using neural networks | 2017 | Alta |
| DL-003 | Deep Watershed Detector for Music Object Recognition | 2020 | Media |
| DL-004 | Music Symbol Recognition Based on Imbalanced Large Margin Distribution Machine | 2022 | Media |
| DL-005 | M2-OMR: Mamba-2-Based End-to-End Full-Page OMR | 2027 | Alta |
| DL-006 | Deep learning-driven automatic music score recognition (TCMN-LSA) | 2026 | Alta |
| DL-007 | Full-page recognition and alignment of historical musical documents | 2026 | Media |
| DL-008 | Multimodal transformers for image and audio polyphonic music transcription | 2026 | Media |
| DL-009 | End-to-End Full-Page OMR for Pianoform Sheet Music | 2026 | Alta |
| DL-010 | Improved CRNN for OMR and its application in piano teaching | 2025 | Media |
| DL-011 | Classification of Handwritten and Printed Music Sheets (LBP vs AlexNet) | 2026 | Media |

## Fichas

### [DL-001] End-to-End Neural Optical Music Recognition of Monophonic Scores
- **Autores:** Jorge Calvo-Zaragoza, David Rizo
- **Año / Venue:** 2018, Applied Sciences, 8(4), 606
- **DOI / URL:** https://doi.org/10.3390/app8040606
- **Tags:** omr, end-to-end, cnn, rnn, monofónico, pianoform
- **Abstract (resumen parafraseado):**
  > Propone un enfoque end-to-end de OMR para partituras monofónicas y *pianoform* (dos pentagramas)
  > usando CNNs + RNNs (BiLSTM) + CTC, sin segmentación previa de símbolos. Entrena y evalúa sobre
  > datasets sintetizados con la técnica *Camera-Printer* (ver DS-002), reportando mejoras frente a
  > pipelines clásicos segmentados.
- **Relevancia para Cadenza:** Alta — el corpus objetivo de Cadenza (monofónicas y piano simple)
  coincide exactamente con el alcance de este trabajo; además introduce CAPTAIN (DS-002).
- **Notas / ideas:**
  - Base metodológica para justificar la elección de oemer y sus limitaciones.
  - El dataset sintetizado (CAPTAIN) puede servir como corpus inicial de pruebas mientras se consigue
    el corpus real.

### [DL-002] End-to-end optical music recognition using neural networks
- **Autores:** Jorge Calvo-Zaragoza, José J. Valero-Mas, Antonio Pertusa
- **Año / Venue:** 2017, Proc. de la 18.ª ISMIR (Suzhou, China), ISBN 978-981-11-5179-8
- **DOI / URL:** https://doi.org/10.5281/zenodo.1418333
- **Tags:** omr, end-to-end, cnn, ctc
- **Abstract (resumen parafraseado):**
  > Trabajo temprano que aplica redes neuronales (CNN + BiLSTM + CTC) directamente sobre imágenes de
  > partituras para transcribirlas a secuencias simbólicas, mostrando que el aprendizaje profundo puede
  > reemplazar la segmentación manual de símbolos en OMR.
- **Relevancia para Cadenza:** Alta — una de las primeras demostraciones de OMR end-to-end; contexto
  de la línea de investigación que sigue oemer.
- **Notas / ideas:**
  - Una de las primeras demostraciones de OMR end-to-end; contexto de la línea de investigación que sigue oemer.
  - Útil para la línea de tiempo del estado del arte (2017 → 2018 → 2020 → actualidad).

### [DL-003] Deep Watershed Detector for Music Object Recognition
- **Autores:** Lukas Tuggener, Ismail Elezi, Jürgen Schmidhuber, Thilo Stadelmann
- **Año / Venue:** 2020, Proc. de la 21.ª ISMIR
- **DOI / URL:** https://doi.org/10.5281/zenodo.4245484
- **Tags:** omr, object detection, watershed, deepscores
- **Abstract (resumen parafraseado):**
  > Propone un detector de objetos musicales (notas, figuras, alteraciones) basado en *deep watershed*
  > que mejora la detección de objetos pequeños y densos en partituras, evaluado sobre DeepScores
  > (ver DS-001).
- **Relevancia para Cadenza:** Media — referencia de la rama de detección de símbolos; útil si el
  proyecto evalúa el componente de detección de oemer.
- **Notas / ideas:**
  - Conecta con DS-001 (DeepScores) para entender datasets de detección.

### [DL-004] Music Symbol Recognition Based on Imbalanced Large Margin Distribution Machine
- **Autores:** no especificados en el abstract — verificar
- **Año / Venue:** 2022, IEEE YAC (37.ª Youth Academic Annual Conference of Chinese Association of Automation — verificar)
- **DOI / URL:** https://doi.org/10.1109/YAC57282.2022.10023625
- **Tags:** clasificación, desbalance, símbolos, cost-sensitive
- **Abstract (texto del paper):**
  > Music symbol classification is an significant step of Optical Music Recognition (OMR). Several remarkable algorithms are used to recognize music symbols. When the quantity of symbols from different classes is imbalanced, the classifying surface will incline towards the minority class. However, none of the studies considered the imbalance of the music symbols. In this paper, the Imbalanced Large margin Distribution Machine (ILDM) is proposed to increase the classification accuracy of the minority music symbols by introducing cost-sensitive penalty. We conduct tests on more than 10000 music symbols, which are handwritten and printed images. The tests show that the accuracy of the minority class is greatly improved with the increasing of the cost-sensitive penalty. The inefficiency of classification due to the over-widened gap in sample quantity of music symbols is solved by the ILDM.
- **Relevancia para Cadenza:** Media — aborda el desbalance de clases en clasificación de símbolos (símbolos raros: puntillos, ligaduras, alteraciones), relevante para la calidad del modelo base.
- **Notas / ideas:**
  - El desbalance de símbolos afecta directamente la precisión de oemer en símbolos poco frecuentes → conectar con el motor de validación (qué símbolos son más propensos a error).

### [DL-005] M2-OMR: Mamba-2-Based End-to-End Full-Page Optical Music Recognition
- **Autores:** no especificados en el abstract — verificar
- **Año / Venue:** 2027 (copyright), Springer — capítulo de conferencia LNCS (verificar conferencia; posible ICPR 2026)
- **DOI / URL:** https://doi.org/10.1007/978-981-92-3384-7_12
- **Tags:** mamba, state-space, full-page, transformers, end-to-end
- **Abstract (texto del paper):**
  > Full-page Optical Music Recognition (OMR) needs to handle very long sequences. However, standard Transformer models have a big problem with quadratic complexity, O(L2). This makes it very expensive to process high-resolution images. To save memory, most people cut the music into small patches, but this often breaks the musical structure. In this paper, we propose M2-OMR. It is an end-to-end framework based on State Space Duality. M2-OMR can model the whole sequence in linear time, O(L), without any cropping. We have two main parts. First, the Staff-Aware Feature Folding module adds staff-line geometry as a spatial anchor. Second, the Gated Structural State-Space engine helps the model find useful music symbols and ignore background noise. We tested our model on PrIMuS, DeepScores V2, and MUSCIMA++ datasets. The results show that M2-OMR is better than Transformer models for both printed and handwritten scores. It is 5× faster and uses much less memory on long sequences. Our work proves that state-space models are a fast and accurate choice for full-page OMR.
- **Relevancia para Cadenza:** Alta — estado del arte en OMR full-page (página completa sin recorte), con modelos state-space más eficientes que transformers; marca la tendencia hacia la que evoluciona el campo.
- **Notas / ideas:**
  - Procesar la página completa sin parches es clave para Cadenza (piano simple, una página).
  - Evaluado en PrIMuS, DeepScores V2 y MUSCIMA++ — mismos datasets de referencia de la tesis.

### [DL-006] Deep learning-driven automatic music score recognition and digital transcription algorithm (TCMN-LSA)
- **Autores:** no especificados en el abstract — verificar
- **Año / Venue:** 2026, Discover Computing (Springer)
- **DOI / URL:** https://doi.org/10.1007/s43926-026-00332-8
- **Tags:** transformer, cnn, lstm, ctc, optimización, end-to-end
- **Abstract (texto del paper):**
  > Automatic music score recognition, also known as Optical Music Recognition (OMR), is required for transforming printed or handwritten sheet music to a digital, editable version. Traditional rule-based OMR systems often fail under complex staff layouts, noise, and stylistic variations, resulting in reduced transcription reliability. This research proposes a deep learning framework named Transformer-based Convo Memory Network optimized with Locust Swarm Algorithm (TCMN-LSA) to enhance recognition accuracy, convergence stability, and robustness across diverse music manuscripts. The model is trained and evaluated using the Sheet Music Transformer dataset, which includes the GrandStaff and Camera-GrandStaff subsets containing real-world distortions. Preprocessing improves image consistency using Z-score normalization and Wiener filtering. The TCMN-LSA architecture integrates a CNN feature extractor for spatial symbol detection, a Transformer encoder to model contextual dependencies, and an LSTM module for temporal sequence learning. A Transformer-based decoder produces structured symbolic notation. The Locust Swarm Algorithm (LSA) performs adaptive optimization, improving convergence efficiency and reducing parameter instability. Connectionist Temporal Classification (CTC) enables alignment-free transcription for variable-length polyphonic inputs. Experiments are performed using Python, TensorFlow, and PyTorch, ensuring high-performance training and large-scale batch processing. Evaluation metrics include precision, recall, accuracy, CER, SER, and LER. The proposed model achieves 95.84% of precision, 82.67% of recall, and 88.41% of accuracy, significantly outperforming classical approaches. On the GrandStaff dataset, TCMN-LSA attains 1.62% CER, 2.10% SER, and 6.45% LER, and 1.21% CERbug, demonstrating improved symbol recognition and transcription stability.
- **Relevancia para Cadenza:** Alta — arquitectura híbrida CNN+Transformer+LSTM con métricas reportadas (CER/SER/LER) sobre piano (GrandStaff) con distorsiones reales (fotos); referencia de comparación de métricas.
- **Notas / ideas:**
  - El dataset Sheet Music Transformer (GrandStaff/Camera-GrandStaff) incluye fotos reales → relevante para el corpus de Cadenza.
  - Usar sus métricas (CER, SER, LER) como referencia de comparación en la experimentación.

### [DL-007] Full-page recognition and alignment of historical musical documents
- **Autores:** no especificados en el abstract — verificar
- **Año / Venue:** 2026, International Journal on Document Analysis and Recognition (IJDAR)
- **DOI / URL:** https://doi.org/10.1007/s10032-026-00574-w
- **Tags:** manuscritos históricos, transcripción, alineación, transformers
- **Abstract (texto del paper):**
  > Optical Music Recognition aims to transcribe musical manuscript images into digital formats by using automatic methods for enhanced accessibility and preservation. This task is challenging for handwritten historical musical pieces from the Late Middle Ages, Early Renaissance, and previous time periods. This music has the interesting characteristic that both musical and lyrical elements are present with an implicit time alignment between them. This paper introduces techniques for simultaneously transcribing the musical and lyrical elements. We research how to automatically obtain the time alignment for an accurate musicological interpretation. Convolutional and Recurrent Neural Networks and Transformer models are explored for holistically transcribing and aligning historical pieces. This paper explores different techniques to improve the training of the models in limited data scenarios. Experiments are conducted on two different datasets from the same time period. Our findings highlight the potential of Transformer models in overcoming the alignment challenge, providing the best alignment capabilities without compromising the quality of transcriptions and offering a promising direction for future research in the automatic recognition of historical musical documents.
- **Relevancia para Cadenza:** Media — los manuscritos históricos quedaron **fuera del alcance** (solo manuscritas modernas), pero el paper es útil por sus técnicas para escenarios de datos limitados y como referencia de la dificultad del subproblema.
- **Notas / ideas:**
  - Técnicas para "limited data scenarios" → aplicar a Cadenza si el corpus real es pequeño.

### [DL-008] Multimodal transformers for image and audio polyphonic music transcription
- **Autores:** no especificados en el abstract — verificar
- **Año / Venue:** 2026, Applied Soft Computing (Elsevier)
- **DOI / URL:** https://doi.org/10.1016/j.asoc.2026.114643
- **Tags:** multimodal, imagen+audio, transformers, transcripción polifónica
- **Abstract (texto del paper):**
  > The attainment of structured representations of music sources—commonly referred to as music transcription—has long been a central challenge in the field of Music Information Retrieval. Traditionally, research has addressed this task through Optical Music Recognition for sheet music and through Automatic Music Transcription for audio recordings. More recently, multimodal approaches that integrate both image and audio modalities have emerged, aiming to exploit their complementary strengths. However, these existing methods have so far been evaluated only in controlled settings with monophonic music. In this work, we present the first multimodal image-and-audio framework for polyphonic music transcription, built upon the Transformer architecture. Specifically, we design and evaluate six distinct modality-fusion strategies, differing in the stage at which the modalities are integrated (early, intermediate, or late fusion). Our results demonstrate that multimodality can be beneficial for polyphonic transcription—producing comparable or superior performance across all datasets tested and, in the best-performing experiments, improving the performance of the best unimodal transcription scenario by 9% on average—but its impact depends on the strategy: some fusion schemes yield consistent gains, whereas others fail to improve upon the unimodal baseline.
- **Relevancia para Cadenza:** Media — idea interesante (imagen + audio como validación cruzada de la transcripción), aunque fuera del alcance actual; anotar como trabajo futuro.
- **Notas / ideas:**
  - Potencial futuro: usar el audio (si existe) para validar la transcripción de Cadenza.

### [DL-009] End-to-End Full-Page Optical Music Recognition for Pianoform Sheet Music
- **Autores:** Ríos-Vila, A., Calvo-Zaragoza, J., Paquet, E. (candidato — verificar)
- **Año / Venue:** 2026, International Journal of Computer Vision (IJCV)
- **DOI / URL:** https://doi.org/10.1007/s11263-025-02654-6
- **Tags:** end-to-end, full-page, pianoform, transformers, curriculum learning
- **Abstract (texto del paper):**
  > Optical Music Recognition (OMR) has made significant progress since its inception, with various approaches now capable of accurately transcribing music scores into digital formats. Despite these advancements, most so-called end-to-end OMR approaches still rely on multi-stage processing pipelines for transcribing full-page score images, which entails challenges such as the need for dedicated layout analysis and specific annotated data, thereby limiting the general applicability of such methods. In this paper, we present the first truly end-to-end approach for page-level OMR in complex layouts. Our system, which combines convolutional layers with autoregressive Transformers, processes an entire music score page and outputs a complete transcription in a music encoding format. This is made possible by both the architecture and the training procedure, which utilizes curriculum learning through incremental synthetic data generation. We evaluate the proposed system using pianoform corpora, which is one of the most complex sources in the OMR literature. This evaluation is conducted first in a controlled scenario with synthetic data, and subsequently against two real-world corpora of varying conditions. Our approach is compared with leading commercial OMR software. The results demonstrate that our system not only successfully transcribes full-page music scores but also outperforms the commercial tool in both zero-shot settings and after fine-tuning with the target domain, representing a significant contribution to the field of OMR.
- **Relevancia para Cadenza:** Alta — coincide con el corpus objetivo (pianoform); primer enfoque verdaderamente end-to-end de página completa que supera software comercial. Referencia central del estado del arte.
- **Notas / ideas:**
  - Curriculum learning con datos sintéticos incrementales → estrategia a considerar para entrenar con corpus pequeño.
  - Comparar con oemer: ¿qué gana Cadenza con oemer vs. este enfoque? (documentar en la tesis)

### [DL-010] Research on optical music recognition based on improved CRNN network and its application in piano teaching
- **Autores:** no especificados en el abstract — verificar
- **Año / Venue:** 2025, International Journal of Computational Science and Mathematics (Inderscience — verificar nombre exacto de la revista)
- **DOI / URL:** https://doi.org/10.1504/IJCSM.2025.149900
- **Tags:** crnn, atención, squeeze-excitation, eficiencia
- **Abstract (texto del paper):**
  > The traditional optical music recognition method has the problem of low recognition accuracy and efficiency. An optical music recognition method based on convolutional recurrent neural network (CRNN) is proposed. Firstly, residual depthwise separable convolution is introduced into convolutional layer of CRNN network. Then, after convolution operation, squeeze-excitation module in attention mechanism is introduced. Finally, parameters of cross entropy function are adjusted at transcription layer. The results reveal that error rate of note recognition and sequence recognition in optical music is 1.26% and 7.31% respectively, which is significantly lower than those of CRNN model and SE-bi-directional long short-term memory (SE-BiLSTM) model. This model can improve training speed, and its recognition time is only 6.44 s, which is 7.89 s and 14.65 s lower than that of other two methods, respectively. It shows that recognition efficiency of the proposed model is significantly improved, which can meet the actual teaching needs of piano classrooms.
- **Relevancia para Cadenza:** Media — mejora incremental sobre CRNN con atención; útil como referencia de eficiencia (tiempo de reconocimiento) para el pipeline en tiempo real.
- **Notas / ideas:**
  - La eficiencia (6.44 s por partitura) es un punto de comparación para el rendimiento de la plataforma.

### [DL-011] Automatic Classification of Handwritten and Printed Music Sheets Using LBP and AlexNet
- **Autores:** no especificados en el abstract — verificar
- **Año / Venue:** 2026, IEEE ICSCAN (verificar nombre completo de la conferencia)
- **DOI / URL:** https://doi.org/10.1109/ICSCAN66520.2026.11588445
- **Tags:** clasificación, impreso vs manuscrito, LBP, alexnet, preprocesado
- **Abstract (texto del paper):**
  > Automatic classification of handwritten and printed music sheet images is an important preprocessing step in document image analysis and Optical Music Recognition systems. This paper presents a comparative framework using two feature extraction approaches: Local Binary Pattern (LBP) and AlexNet-based deep features for binary music sheet classification. To ensure fair evaluation, seven common classifiers were tested for both methods. Experimental results show that the LBP-based framework consistently outperformed the AlexNet approach. The highest accuracy of 98.40% was achieved using LBP with Cubic SVM, while the best AlexNet-based model obtained 96.38%. The results indicate that handcrafted texture descriptors remain highly effective for music document image classification and can be efficiently applied in Optical Music Recognition applications.
- **Relevancia para Cadenza:** Media — etapa de clasificación del tipo de documento (impreso/manuscrito) como preprocesado; útil para enrutar el flujo de Cadenza según el tipo de entrada.
- **Notas / ideas:**
  - Si Cadenza acepta ambos tipos, un clasificador previo (LBP+SVM, simple y eficaz) puede elegir el pipeline adecuado.

## Candidatos a verificar (agregar ficha completa tras confirmar datos)

- **OMR con Transformers / arquitecturas modernas:** Ríos-Vila, A., Calvo-Zaragoza, J., Paquet, E.
  (aprox. 2022–2024) — trabajos de OMR end-to-end con transformers y *vision transformers* para
  partituras impresas y manuscritas. Buscar en ISMIR/IJDAR.
- **Reconocimiento de manuscritos musicales con seq2seq + atención:** Calvo-Zaragoza et al.
  (aprox. 2019) — transcripción de manuscritos con redes con atención. Buscar en IJDAR/ICDAR.
- **Búsqueda:** "transformer optical music recognition", "vision transformer sheet music",
  "OMR sequence to sequence attention".

## Dónde buscar más

- **Palabras clave:** "end-to-end OMR", "OMR deep learning", "music symbol detection",
  "handwritten music recognition deep learning".
- **Venues:** ISMIR, IJDAR, ICDAR, DAS, ICPR, Applied Sciences.
- **Estrategia:** seguir la línea de autores del grupo de Calvo-Zaragoza (U. de Alicante) — son los
  más productivos en OMR con deep learning; revisar sus publicaciones recientes.
