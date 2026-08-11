# Colección de Literatura — Cadenza

Repositorio de artículos, abstracts y referencias que alimentan el **estado del arte** de la tesis.
Cada archivo cubre un tema del proyecto; dentro, cada artículo se documenta con una **ficha**.

## Temas

| Archivo | Contenido |
|---|---|
| [01-omr-estado-del-arte.md](01-omr-estado-del-arte.md) | Surveys y sistemas generales de OMR |
| [02-modelos-deep-learning.md](02-modelos-deep-learning.md) | Arquitecturas de aprendizaje profundo para OMR |
| [03-validacion-musical.md](03-validacion-musical.md) | Reglas musicales, detección/corrección de errores post-OMR |
| [04-human-in-the-loop.md](04-human-in-the-loop.md) | Interfaces de corrección asistida, HITL, ML interactivo |
| [05-aprendizaje-activo.md](05-aprendizaje-activo.md) | Active learning y mejora con feedback del usuario |
| [06-datasets-corpus.md](06-datasets-corpus.md) | Datasets públicos y criterios para el corpus objetivo |
| [07-formatos-evaluacion.md](07-formatos-evaluacion.md) | MusicXML, MIDI, MEI y métricas de evaluación |

## Formato de ficha (copiar y pegar)

```markdown
### [TEMA-NNN] Título del artículo
- **Autores:** ...
- **Año / Venue:** 2024, ISMIR
- **DOI / URL:** https://doi.org/...
- **Tags:** omr, transformers
- **Abstract (resumen original o parafraseado):**
  > ...
- **Relevancia para Cadenza:** Alta | Media | Baja — por qué
- **Notas / ideas:**
  - ...
```

## Convenciones

- **ID:** `[TEMA-NNN]` con las siglas del tema (`OMR`, `DL`, `VAL`, `HITL`, `AL`, `DS`, `FM`) y número correlativo.
- **Relevancia:** Alta (se cita seguro en la tesis) · Media (apoyo/comparación) · Baja (contexto).
- **Abstract:** cuando el artículo es de pago y no hay acceso, escribir un resumen parafraseado de 3–5 líneas y marcarlo como tal.
- **Notas / ideas:** vínculo directo con componentes de Cadenza (oemer, motor de validación, UI de corrección, aprendizaje activo, corpus).
- **Verificación:** varias fichas marcadas como *"verificar"* son candidatos iniciales; **confirmar datos (año, venue, DOI) antes de citarlas en la tesis**. Cuando se cree la bibliografía BibTeX del documento de tesis, cada ficha nueva debe agregarse también a esa `.bib` con su clave.

## Índice de fichas existentes

| ID | Tema | Título corto | Relevancia |
|---|---|---|---|
| OMR-001 | [01](01-omr-estado-del-arte.md) | Understanding Optical Music Recognition (survey 2020) | Alta |
| OMR-002 | [01](01-omr-estado-del-arte.md) | OMR: state-of-the-art and open issues (2012) | Alta |
| OMR-003 | [01](01-omr-estado-del-arte.md) | oemer — librería OMR end-to-end | Alta |
| OMR-004 | [01](01-omr-estado-del-arte.md) | Audiveris — OMR con UI de corrección | Media |
| OMR-005 | [01](01-omr-estado-del-arte.md) | The challenge of OMR (2001) | Media |
| DL-001 | [02](02-modelos-deep-learning.md) | End-to-End Neural OMR of Monophonic Scores | Alta |
| DL-002 | [02](02-modelos-deep-learning.md) | End-to-end OMR using neural networks (ISMIR 2017) | Alta |
| DL-003 | [02](02-modelos-deep-learning.md) | Deep Watershed Detector (ISMIR 2020) | Media |
| VAL-001 | [03](03-validacion-musical.md) | music21 — toolkit de teoría musical | Alta |
| VAL-002 | [03](03-validacion-musical.md) | Language models para post-procesamiento OMR | Media (verificar) |
| HITL-001 | [04](04-human-in-the-loop.md) | Power to the People: Interactive ML | Alta |
| HITL-002 | [04](04-human-in-the-loop.md) | MuRET — plataforma web de OMR | Media (verificar) |
| HITL-003 | [04](04-human-in-the-loop.md) | Interactive ML for Health Informatics | Media |
| AL-001 | [05](05-aprendizaje-activo.md) | Active Learning Literature Survey (Settles) | Alta |
| AL-002 | [05](05-aprendizaje-activo.md) | Active Learning (libro, Settles 2012) | Media |
| DS-001 | [06](06-datasets-corpus.md) | DeepScores | Media |
| DS-002 | [06](06-datasets-corpus.md) | CAPTAIN (verificar) | Media |
| DS-003 | [06](06-datasets-corpus.md) | HOMUS — símbolos manuscritos online (ICPR 2014) | Media |
| DS-004 | [06](06-datasets-corpus.md) | PRinS (verificar) | Media |
| FM-001 | [07](07-formatos-evaluacion.md) | MusicXML 4.0 (W3C) | Alta |
| FM-002 | [07](07-formatos-evaluacion.md) | MEI — Music Encoding Initiative | Media |
| FM-003 | [07](07-formatos-evaluacion.md) | MIDI 1.0 | Media |
| FM-004 | [07](07-formatos-evaluacion.md) | music21 (paper ISMIR 2010) | Alta |
| OMR-006 | [01](01-omr-estado-del-arte.md) | Deep Learning Algorithm Composition System (ICKECS) | Media |
| OMR-007 | [01](01-omr-estado-del-arte.md) | Handwritten Note Recognition (ICETCI, LBP+XGBoost) | Media |
| DL-004 | [02](02-modelos-deep-learning.md) | Imbalanced Large Margin Distribution Machine (ILDM) | Media |
| DL-005 | [02](02-modelos-deep-learning.md) | M2-OMR: Mamba-2 full-page OMR | Alta |
| DL-006 | [02](02-modelos-deep-learning.md) | TCMN-LSA: deep learning OMR (Discover Computing) | Alta |
| DL-007 | [02](02-modelos-deep-learning.md) | Full-page recognition and alignment (IJDAR) | Media |
| DL-008 | [02](02-modelos-deep-learning.md) | Multimodal transformers image+audio (ASOC) | Media |
| DL-009 | [02](02-modelos-deep-learning.md) | End-to-End Full-Page OMR for Pianoform (IJCV) | Alta |
| DL-010 | [02](02-modelos-deep-learning.md) | Improved CRNN for OMR (piano teaching) | Media |
| DL-011 | [02](02-modelos-deep-learning.md) | LBP vs AlexNet para clasificar impreso/manuscrito | Media |
| HITL-004 | [04](04-human-in-the-loop.md) | OMRAT — anotación semi-automática online | Alta |
| HITL-005 | [04](04-human-in-the-loop.md) | Design of a Music Recognition/Transcription Tool | Media |
| AL-003 | [05](05-aprendizaje-activo.md) | Active and Sequential Learning in a Medieval Manuscript | Alta |
| AL-004 | [05](05-aprendizaje-activo.md) | Pseudo-Labeling con incertidumbre GMM | Media |
| DS-005 | [06](06-datasets-corpus.md) | OMR in Manuscripts from the Ricordi Archive | Alta |
| DS-006 | [06](06-datasets-corpus.md) | MuNG Studio: annotation tool | Media |
| DS-007 | [06](06-datasets-corpus.md) | Smashcima: sintetizador de manuscritos | Media |
| DS-008 | [06](06-datasets-corpus.md) | PrIMuS / Camera-PrIMuS — impresas monofónicas | Alta |
| DS-009 | [06](06-datasets-corpus.md) | MUSCIMA++ / CVC-MUSCIMA — manuscritas modernas | Alta |
| FM-005 | [07](07-formatos-evaluacion.md) | Sheet Music Benchmark (SMB) + OMR-NED | Alta |
