# Borrador — Introducción de la tesis (Cadenza)

> **Estado:** borrador v0.1 — escrito siguiendo la plantilla de 6 bloques detectada en las
> introducciones de trabajos de grado de la Universidad del Norte (contexto general → hueco →
> contexto local → fundamentación → propuesta → cierre).
>
> **Marcas `[COMPLETAR: ...]`:** datos que deben confirmarse con la institución del corpus o el
> director antes de usar el texto.
>
> **Citas:** numeradas [1]–[10]; la lista de referencias está al final y mapea a las fichas de
> `docs/literatura/`. Los números se trasladan a BibTeX cuando se estructure el documento LaTeX.

---

## Introducción

La digitalización del patrimonio musical constituye una necesidad creciente para archivos,
bibliotecas, academias y agrupaciones musicales que conservan partituras físicas en papel. El
reconocimiento óptico de música (OMR, por sus siglas en inglés) es la disciplina que aborda la
conversión automática de imágenes de partituras en representaciones simbólicas editables, y ha
sido objeto de investigación durante más de cinco décadas [1], evolucionando desde sistemas
basados en reglas hasta flujos de aprendizaje profundo que transcriben partituras completas de
forma automática [2][3].

A pesar de estos avances, los sistemas OMR modernos cometen errores que impiden su uso directo en
entornos reales: notas con alturas o duraciones incorrectas, compases ritmicamente incorrectos, armaduras
inconsistentes y símbolos omitidos [3]. Los modelos de reconocimiento se estudian
predominantemente desde la precisión de su salida automática, mientras que la integración del
reconocimiento en el trabajo práctico de un transcriptor ha recibido mucha menos atención [5].
Como consecuencia, quien digitaliza partituras debe revisar manualmente cada símbolo en un editor
musical convencional — un proceso tan lento como la transcripción manual — o aceptar resultados
erróneos sin verificarlos. En el caso de los manuscritos musicales modernos, esta situación se
agudiza, pues la variabilidad de la escritura degrada aún más la confiabilidad del reconocimiento
automático [10]. Del mismo modo, el aprovechamiento de las correcciones del usuario para mejorar
el sistema — mediante ciclos de aprendizaje activo — es un problema prácticamente inexplorado en
OMR, con resultados iniciales incluso contradictorios [8].


En el contexto global, instituciones conservan colecciones
de partituras impresas y escritas a mano que requieren digitalización para su preservación,
consulta y difusión. La transcripción manual de estas colecciones representa un costo de tiempo
considerable, y las herramientas de reconocimiento existentes no ofrecen un flujo de trabajo que
garantice la calidad del resultado. La digitalización de colecciones musicales en archivos ha sido
abordada recientemente con metodologías de anotación y clasificación automática [10], lo que
evidencia tanto la viabilidad como la necesidad de sistemas adaptados a este tipo de corpus.

Desde el punto de vista disciplinar, un sistema de digitalización asistida de partituras puede
estructurarse sobre tres pilares: el pipeline clásico de OMR — preprocesado, detección de
pentagramas, detección y clasificación de símbolos, ensamblaje y reconstrucción musical [1] —, la
validación de la salida mediante reglas de teoría musical [6], y la corrección asistida por un
humano en el ciclo [7]. La validación automática permite detectar errores estructurales (métrica,
duraciones, armaduras) sin intervención humana, reduciendo el espacio de revisión a los puntos
sospechosos. El aprendizaje activo complementa el ciclo al seleccionar qué correcciones del
usuario tienen mayor valor para mejorar el reconocimiento [8].

En este contexto, el presente proyecto propone el diseño e implementación de **Cadenza**, una
plataforma de digitalización asistida de partituras que integra cuatro componentes: un modelo OMR
base (oemer [9]) encargado de la transcripción automática a MusicXML; un motor de validación
basado en reglas musicales que detecta y señala errores probables; una interfaz de corrección
asistida que permite al usuario revisar y corregir la transcripción sobre la imagen original; y un
ciclo de aprendizaje activo que aprovecha las correcciones del usuario para priorizar la revisión
y mejorar progresivamente el sistema. La plataforma se orienta a partituras impresas y escritas a
mano actuales, monofónicas o de piano simple, excluyendo orquestaciones completas y manuscritos
históricos, cuyo tratamiento excede el alcance de este trabajo.

El aporte principal de este proyecto consiste en transformar un modelo de reconocimiento de
investigación en un sistema realmente usable, integrando validación automática y un ciclo de
retroalimentación con el usuario. De esta manera, Cadenza contribuye a cerrar la brecha entre la
precisión del reconocimiento y su aplicabilidad en el trabajo real de digitalización de
partituras. 
---

## Referencias citadas

| # | Ficha | Referencia |
|---|---|---|
| [1] | OMR-001 | J. Calvo-Zaragoza, J. Hajič Jr., A. Pacha, "Understanding Optical Music Recognition", ACM Computing Surveys, vol. 53, n.º 4, 2020. |
| [2] | OMR-002 | A. Rebelo et al., "Optical music recognition: state-of-the-art and open issues", IJ-MIR, vol. 1, n.º 3, 2012. |
| [3] | DL-001 | J. Calvo-Zaragoza, D. Rizo, "End-to-End Neural Optical Music Recognition of Monophonic Scores", Applied Sciences, 8(4), 2018. |
| [4] | DL-009 | A. Ríos-Vila, J. Calvo-Zaragoza, E. Paquet, "End-to-End Full-Page Optical Music Recognition for Pianoform Sheet Music", IJCV, 2026. *(verificar autores)* |
| [5] | HITL-005 | D. Rizo et al., "Design of a Music Recognition, Encoding, and Transcription Online Tool", CMMR 2023 / Springer, 2026. |
| [6] | VAL-001 | M. S. Cuthbert, C. Ariza, "music21: A Toolkit for Computer-Aided Musicology and Symbolic Music Data", ISMIR 2010. |
| [7] | HITL-001 | S. Amershi et al., "Power to the People: The Role of Humans in Interactive Machine Learning", AI Magazine, 35(4), 2014. |
| [8] | AL-003 | "Experimenting Active and Sequential Learning in a Medieval Music Manuscript", IEEE MLSP 2025. *(autores por verificar)* |
| [9] | OMR-003 | BreezeWhite, "oemer: A Python Library for End-to-End Optical Music Recognition", GitHub. |
| [10] | DS-005 | "Optical Music Recognition in Manuscripts from the Ricordi Archive", ACM, 2024. *(autores por verificar)* |

## Notas para revisión

1. **[8] se usa en dos lugares** (hueco del aprendizaje activo y fundamentación) — verificar si el
   paper de MLSP 2025 es la mejor cita para ambos; alternativas: Settles 2009 (AL-001).
2. **El párrafo de contexto local es el que hay que personalizar** con datos reales de la
   institución del corpus — es el análogo de las cifras de Barranquilla en el ejemplo de
   siniestros viales.
3. **Revisar coherencia con el título elegido** (ver análisis de títulos) y con la estructura de
   secciones del documento final.
4. Las referencias [4], [8] y [10] siguen marcadas "verificar" en las fichas de literatura.
