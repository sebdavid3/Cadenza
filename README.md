# Cadenza

Plataforma de Digitalización Asistida de Partituras — proyecto de grado.

Convierte partituras físicas — fotos, escaneos y manuscritos — a formato editable
(MusicXML / MIDI) mediante **OMR** (reconocimiento óptico de música) con **validación
inteligente** y **retroalimentación del usuario**.

> **Estado actual:** etapa de documentación y análisis de la idea (sin código).

## Componentes clave

| Componente | Descripción |
|---|---|
| Motor OMR base — Wrapper DWR | Envoltorio del motor OMR (punto de partida: [oemer](https://github.com/BreezeWhite/oemer)) |
| Motor de validación | Reglas musicales automáticas (detección de errores) |
| Interfaz de corrección | Asistencia humana en el flujo (HITL) |
| Aprendizaje activo | Mejora continua con feedback del usuario |

**Aporte único:** no es solo reconocimiento — es convertir un modelo de investigación en
un sistema realmente usable, con validación automática y ciclo de retroalimentación integrado.

## Alcance

- Corpus: partituras **impresas y escritas a mano actuales**, monofónicas o piano simple (sin orquesta completa; sin manuscritos históricos). Evaluación: datasets públicos con ground truth (**PrIMuS/Camera-PrIMuS, SMB y MUSCIMA++**) + piloto real (10–20 partituras) para usabilidad.
- Equipo: 2 personas · 4 meses · corpus de evaluación = datasets públicos con ground truth.
- **Riesgo principal:** complejidad de las reglas de validación musical e integración del pipeline (oemer/homr) con el corpus de evaluación. ~~Disponibilidad de corpus real~~ — resuelto: se usan datasets públicos.

## Estructura del repositorio

```
docs/                → documentación del proyecto (etapa actual)
  arquitectura-dbb.md → arquitectura general E2E y diagramas DBB
  revision-literatura-prisma.md → revisión de literatura sistemática (PRISMA)
  literatura/        → artículos, abstracts y referencias por tema
latex/               → plantilla LaTeX IEEE de conferencia (original, sin modificar)
  IEEE-conference-template-062824.tex → template de conferencia
  IEEEtran.cls       → clase de documento
  IEEEtran_HOWTO.pdf → guía de uso del template
  fig1.png           → figura de ejemplo del template
```

- [Guía de documentación](docs/README.md)
- [Revisión de literatura (PRISMA)](docs/revision-literatura-prisma.md)
- [Arquitectura general (DBB)](docs/arquitectura-dbb.md)
- [Colección de literatura](docs/literatura/README.md)
- [Template LaTeX](latex/IEEE-conference-template-062824.tex)

*Nota: Commit de prueba para verificar configuración de Git.*
