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
| `notas-investigacion.md` | Análisis de la literatura y síntesis de la idea principal del proyecto |
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

## Próximos pasos sugeridos

1. Leer el survey principal de OMR ([01-omr-estado-del-arte.md](literatura/01-omr-estado-del-arte.md), entrada OMR-001) para tener el panorama general.
2. Estudiar oemer (OMR-003) y sus limitaciones conocidas → insumos para el capítulo de Estado del Arte.
3. Revisar `03-validacion-musical.md` y `05-aprendizaje-activo.md`: son los temas con menos literatura consolidada y donde está el aporte del proyecto.
4. Descargar y preparar el corpus de evaluación (datasets públicos: PrIMuS/Camera-PrIMuS, SMB, MUSCIMA++) con los criterios de `06-datasets-corpus.md`.
5. Estructurar el documento de tesis sobre la plantilla `../latex/IEEE-conference-template-062824.tex` (secciones y bibliografía en BibTeX cuando se defina).
