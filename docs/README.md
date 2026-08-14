# Documentación — Cadenza

Documentación del proyecto de grado **Cadenza: Plataforma de Digitalización Asistida de Partituras**.

> **Estado actual:** etapa de documentación y análisis de la idea (sin código).

## Objetivo del proyecto

Convertir partituras físicas — fotos, escaneos y manuscritos — a formato editable
(MusicXML / MIDI) mediante OMR (reconocimiento óptico de música) con validación
inteligente y retroalimentación del usuario.

## Contenido de la carpeta

| Ruta | Descripción |
|---|---|
| `introduccion-borrador.md` | Borrador de la introducción de la tesis (plantilla de 6 bloques) |
| `revision-literatura-prisma.md` | Revisión sistemática de la literatura bajo el modelo PRISMA |
| `arquitectura-dbb.md` | Diseño de la arquitectura general extremo a extremo (E2E) con diagramas DBB |
| `literatura/` | Colección de artículos, abstracts y referencias organizados por tema (revisión de literatura / estado del arte) |

Otros directorios relevantes del repo:

| Ruta | Descripción |
|---|---|
| `../latex/` | Plantilla LaTeX IEEE de conferencia (original, sin modificar) — base para el documento de tesis |

## Temas de literatura

| # | Tema | Componente del proyecto que alimenta |
|---|---|---|
| [01](literatura/01-omr-estado-del-arte.md) | OMR: estado del arte | Modelo OMR base (oemer) |
| [02](literatura/02-modelos-deep-learning.md) | Modelos de aprendizaje profundo para OMR | Modelo OMR base |
| [03](literatura/03-validacion-musical.md) | Validación musical y corrección de errores | Motor de validación |
| [04](literatura/04-human-in-the-loop.md) | Interfaz de corrección humana (HITL) | Interfaz de corrección |
| [05](literatura/05-aprendizaje-activo.md) | Aprendizaje activo | Ciclo de mejora continua |
| [06](literatura/06-datasets-corpus.md) | Datasets y corpus | Corpus objetivo + evaluación |
| [07](literatura/07-formatos-evaluacion.md) | Formatos (MusicXML/MIDI) y métricas | Salida del sistema + evaluación |

## Corpus y datasets del proyecto

Datasets identificados en la revisión de literatura (fichas `DS-*` y `FM-005` de [06-datasets-corpus.md](literatura/06-datasets-corpus.md) y [07-formatos-evaluacion.md](literatura/07-formatos-evaluacion.md)) y su rol en Cadenza:

| ID | Dataset | Tipo | Rol en Cadenza |
|---|---|---|---|
| DS-008 | **PrIMuS / Camera-PrIMuS** | Impresas monofónicas — 87.678 incipits reales (RISM), con y sin distorsión de foto | **Se trabaja — terna oficial de evaluación** |
| FM-005 | **Sheet Music Benchmark (SMB)** | Impresas — monofonía + pianoform, con splits estándar | **Se trabaja — terna oficial de evaluación** |
| DS-009 | **MUSCIMA++ / CVC-MUSCIMA** | Manuscritas modernas — 140 páginas anotadas a nivel de símbolo (MuNG) | **Se trabaja — terna oficial de evaluación** |
| DS-001 | DeepScores | Partituras sintetizadas con MuseScore (~250.000 páginas) | Complementario — detección de objetos y pruebas |
| DS-002 | CAPTAIN | Sintéticas (procedimiento Camera-Printer) | Complementario — corpus inicial (verificar) |
| DS-003 | HOMUS | Símbolos manuscritos online (~15.200 muestras) | Complementario — clasificador de símbolos manuscritos |
| DS-004 | PRinS | Impresas reales (libros de piano) | Candidato — verificar disponibilidad pública |
| DS-005 | Ricordi Archive | Manuscritos del archivo Ricordi (Verdi, Donizetti, Puccini) | Referencial — caso de estudio metodológico (históricos, fuera del alcance del corpus) |
| DS-006 | MuNG Studio | Herramienta web de anotación MuNG | Herramienta — anotar/editar datos MUSCIMA++ |
| DS-007 | Smashcima | Sintetizador de páginas manuscritas desde MusicXML | Herramienta — aumentación de datos para reentrenamiento |

**Decisión del equipo (2026):** el corpus de evaluación sobre el que **se trabajará** es la terna oficial **PrIMuS/Camera-PrIMuS, SMB y MUSCIMA++** — datasets públicos con ground truth que cubren el alcance del proyecto (impresas monofónicas/pianoform y manuscritas modernas). Se complementa con un piloto real de 10–20 partituras (fotos/escaneos, sin ground truth) para la evaluación de usabilidad. El resto de datasets cumplen roles de apoyo (detección, clasificación de símbolos, aumentación) o sirven de referencia metodológica.

## Próximos pasos sugeridos

1. Leer el survey principal de OMR ([01-omr-estado-del-arte.md](literatura/01-omr-estado-del-arte.md), entrada OMR-001) para tener el panorama general.
2. Estudiar oemer (OMR-003) y sus limitaciones conocidas → insumos para el capítulo de Estado del Arte.
3. Revisar `03-validacion-musical.md` y `05-aprendizaje-activo.md`: son los temas con menos literatura consolidada y donde está el aporte del proyecto.
4. Descargar y preparar el corpus de evaluación (datasets públicos: PrIMuS/Camera-PrIMuS, SMB, MUSCIMA++) con los criterios de `06-datasets-corpus.md`.
5. Estructurar el documento de tesis sobre la plantilla `../latex/IEEE-conference-template-062824.tex` (secciones y bibliografía en BibTeX cuando se defina).
