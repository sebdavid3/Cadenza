# Documentación Técnica — Cadenza

Documentación del proyecto de grado **Cadenza: Plataforma de Digitalización Asistida de Partituras**.

---

## Objetivo del Proyecto

Convertir partituras físicas (fotografías, escaneos y manuscritos) a formatos editables y reproducibles (**MusicXML 4.0** y **MIDI 1.0**) mediante OMR (*Optical Music Recognition*) con validación sintáctica de teoría musical y un ciclo de aprendizaje activo con retroalimentación humana (*Human-in-the-Loop*).

---

## Contenido de la Carpeta

| Ruta | Descripción |
|---|---|
| [`revision-literatura-prisma.md`](revision-literatura-prisma.md) | Metodología de revisión sistemática de la literatura bajo el estándar PRISMA (458 registros identificados, 31 estudios incluidos). |
| [`arquitectura-dbb.md`](arquitectura-dbb.md) | Especificación de la arquitectura extremo a extremo (E2E) con Diagramas de Bloques de Construcción (DBB Niveles 1, 2 y 3). |
| [`literatura/`](literatura/) | Colección de 43 fichas bibliográficas organizadas por área temática y componentes del sistema. |

---

## Áreas Temáticas de la Literatura

| # | Archivo | Foco Principal | Componente de Cadenza |
|---|---|---|---|
| 01 | [`01-omr-estado-del-arte.md`](literatura/01-omr-estado-del-arte.md) | Evolución histórica y taxonomía del OMR | Pipeline base de transcripción |
| 02 | [`02-modelos-deep-learning.md`](literatura/02-modelos-deep-learning.md) | Redes CNN, CRNN, Transformers y Mamba-2 | Motor de reconocimiento OMR |
| 03 | [`03-validacion-musical.md`](literatura/03-validacion-musical.md) | Validación sintáctica y corrección de errores | Motor de reglas (`music21`) |
| 04 | [`04-human-in-the-loop.md`](literatura/04-human-in-the-loop.md) | Interfaces interactivas y control de esfuerzo cognitivo | UI de corrección asistida |
| 05 | [`05-aprendizaje-activo.md`](literatura/05-aprendizaje-activo.md) | Muestreo por incertidumbre y ajuste fino continuo | Módulo de *Active Learning* (TFLite) |
| 06 | [`06-datasets-corpus.md`](literatura/06-datasets-corpus.md) | Corpus públicos y delimitación de alcance | Terna de evaluación |
| 07 | [`07-formatos-evaluacion.md`](literatura/07-formatos-evaluacion.md) | Formatos simbólicos y métricas (SER, OMR-NED) | Protocolo de experimentación |

---

## Corpus y Datasets Oficiales de Evaluación

El protocolo experimental de Cadenza se estructura sobre la **terna oficial de datasets públicos con ground truth**:

| Dataset | Tipo de Partitura | Volumen / Contenido | Rol en la Evaluación |
|---|---|---|---|
| **PrIMuS / Camera-PrIMuS** | Impresas monofónicas | 87.678 incipits reales con y sin distorsiones fotográficas | Evaluación cuantitativa de transcripción base y robustez visual |
| **Sheet Music Benchmark (SMB)** | Impresas (monofonía y pianoform) | 685 páginas completas con divisiones estándar y métrica OMR-NED | Evaluación de página completa y análisis de errores estructurados |
| **MUSCIMA++** | Manuscritas modernas | 140 páginas con más de 91.000 símbolos anotados a nivel de glifo | Evaluación de adaptabilidad a trazos manuscritos modernos |

---

## Articulación con el Documento de Tesis (LaTeX)

El contenido teórico y metodológico de esta carpeta alimenta directamente el documento maestro de tesis en [`../latex/main.tex`](../latex/main.tex):
* **Revisión PRISMA:** Secciones de Estado del Arte y Metodología.
* **Arquitectura DBB:** Capítulo de Diseño e Implementación del Sistema.
* **Corpus y Métricas:** Capítulo de Diseño Experimental y Resultados.
