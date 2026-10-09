# Fase 7 — Alineación con la Arquitectura Objetivo

**Objetivo:** cerrar las brechas entre la implementación de las fases 0 a 6 y la
arquitectura objetivo de [`ARCHITECTURE.md`](../../ARCHITECTURE.md) v1.2, de modo
que el backend quede completo y con un contrato estable **antes** de diseñar el
frontend y las interfaces de usuario.

Referencias: [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md) §6, §7 y §10,
[ADR-0009](../../adr/ADR-0009-capa-de-aplicacion.md),
[ADR-0010](../../adr/ADR-0010-score-ir-atributos-y-exportacion.md),
[ADR-0011](../../adr/ADR-0011-semantica-de-anclas-ante-ediciones.md),
[ADR-0012](../../adr/ADR-0012-autenticacion-e-identidad.md),
[`../../PROJECT_STATE.md`](../../PROJECT_STATE.md).

Seguimiento: milestone
[Fase 7: Alineación con la arquitectura objetivo](https://github.com/sebdavid3/Cadenza/milestone/1)
e issue de seguimiento [#1](https://github.com/sebdavid3/Cadenza/issues/1).

---

## Requerimientos

1. **Análisis de brechas** entre el estado actual y la arquitectura objetivo.
2. **Dominio completo:** `ScoreIR` con clave, armadura y ligaduras; todas las
   operaciones de `EditOp` proyectables.
3. **Datos:** `ArtifactStore` direccionado por contenido, esquema relacional de
   `ARCHITECTURE.md` §7.2 y verificación sobre PostgreSQL real.
4. **Capa de aplicación:** casos de uso fuera de los *handlers* de la API.
5. **API completa:** autenticación con sesiones privadas, motor OMR configurable,
   imagen persistida, ediciones validadas, revalidación, exportación
   MusicXML/MIDI y métricas de esfuerzo.
6. **OMR y validación:** `bbox` reales, preprocesado, línea base `OemerEngine`,
   catálogo de reglas y su precisión y *recall*.
7. **Plano offline:** dataset desde la base de datos, *Model Registry*
   persistente, CLI de jobs, entrenador real y experimentos sobre datos reales.
8. **Infraestructura y cierre:** integración continua y contrato OpenAPI
   congelado.

## Fuera de alcance (Out-of-Scope)

- Diseño del frontend y de las interfaces de usuario: render con OSMD,
  reproducción con Tone.js y editor (D11 parte de interfaz, D12).
- Entrada PDF y partituras de varias páginas: cada sesión parte de una imagen
  (decisión del 2026-10-03, [#38](https://github.com/sebdavid3/Cadenza/issues/38)).
- Despliegue distribuido y autoescalado.
- **TFLite / Edge Learning** y **LLM / VLM**.

## Bloques e issues

| Bloque | Issue | Contenido | Deuda |
|---|---|---|---|
| **A** Análisis | [#1](https://github.com/sebdavid3/Cadenza/issues/1) | Matriz de brechas y seguimiento de la fase | — |
| **B** Dominio y datos | [#2](https://github.com/sebdavid3/Cadenza/issues/2) | `ScoreIR` con clave, armadura y ligaduras | — |
| | [#3](https://github.com/sebdavid3/Cadenza/issues/3) | Proyección de `SetClef`, `SetKey` y `SetAccidental` | — |
| | [#28](https://github.com/sebdavid3/Cadenza/issues/28) | Anclas ante inserciones y borrados: función de traducción (ADR-0011) | D33 |
| | [#32](https://github.com/sebdavid3/Cadenza/issues/32) | Soporte de piano (dos pentagramas) verificado | D37 |
| | [#4](https://github.com/sebdavid3/Cadenza/issues/4) | `ArtifactStore` direccionado por `sha256` | — |
| | [#5](https://github.com/sebdavid3/Cadenza/issues/5) | Migración de esquema de `sessions` y `findings` | — |
| | [#6](https://github.com/sebdavid3/Cadenza/issues/6) | Persistencia verificada en PostgreSQL | D10 |
| **C** Aplicación y API | [#7](https://github.com/sebdavid3/Cadenza/issues/7) | Capa de aplicación (`packages/application`) | D22 |
| | [#8](https://github.com/sebdavid3/Cadenza/issues/8) | Configuración tipada y motor OMR configurable | D3, D5 |
| | [#9](https://github.com/sebdavid3/Cadenza/issues/9) | Imagen persistida y endpoint de imagen | — |
| | [#10](https://github.com/sebdavid3/Cadenza/issues/10) | Validación de ediciones antes de añadirlas al log | — |
| | [#11](https://github.com/sebdavid3/Cadenza/issues/11) | Revalidación tras las correcciones | — |
| | [#12](https://github.com/sebdavid3/Cadenza/issues/12) | Exportación MusicXML y MIDI | D11 (backend) |
| | [#13](https://github.com/sebdavid3/Cadenza/issues/13) | Métricas de esfuerzo persistidas | D13 |
| | [#27](https://github.com/sebdavid3/Cadenza/issues/27) | Listado de sesiones (`GET /sessions`) | D32 |
| | [#39](https://github.com/sebdavid3/Cadenza/issues/39) | Autenticación e identidad de usuario (ADR-0012), seguimiento | D10 |
| | [#43](https://github.com/sebdavid3/Cadenza/issues/43) | Usuarios y propiedad de las sesiones | D10 |
| | [#44](https://github.com/sebdavid3/Cadenza/issues/44) | Inicio de sesión con token de acceso | D10 |
| | [#45](https://github.com/sebdavid3/Cadenza/issues/45) | Usuario actual, propiedad y autoría fijada por el servidor | D10 |
| | [#46](https://github.com/sebdavid3/Cadenza/issues/46) | Gestión de cuentas | D10 |
| | [#48](https://github.com/sebdavid3/Cadenza/issues/48) | Estado actual de la sesión y ediciones con `base_seq` | D46 |
| | [#34](https://github.com/sebdavid3/Cadenza/issues/34) | Ciclo de vida de la sesión | D39 |
| | [#35](https://github.com/sebdavid3/Cadenza/issues/35) | Deshacer en el servidor como evento compensatorio | D40 |
| | [#36](https://github.com/sebdavid3/Cadenza/issues/36) | Descartar un hallazgo como falso positivo | D41 |
| **D** OMR y validación | [#14](https://github.com/sebdavid3/Cadenza/issues/14) | Investigación de `bbox` reales desde HOMR | D4 |
| | [#15](https://github.com/sebdavid3/Cadenza/issues/15) | Preprocesado configurable | D2 |
| | [#16](https://github.com/sebdavid3/Cadenza/issues/16) | `OemerEngine` como línea base | D1 |
| | [#17](https://github.com/sebdavid3/Cadenza/issues/17) | Catálogo de reglas de validación | D6 |
| | [#18](https://github.com/sebdavid3/Cadenza/issues/18) | Precisión y *recall* del validador | D8 |
| | [#31](https://github.com/sebdavid3/Cadenza/issues/31) | Confianza real del modelo OMR | D36 |
| **E** Plano offline | [#19](https://github.com/sebdavid3/Cadenza/issues/19) | `DatasetBuilder` desde la base de datos | D16, D18 |
| | [#20](https://github.com/sebdavid3/Cadenza/issues/20) | `EditEvent` derivados del diff HOMR↔*ground truth* | D21 |
| | [#21](https://github.com/sebdavid3/Cadenza/issues/21) | *Model Registry* persistente y modelo activo | — |
| | [#22](https://github.com/sebdavid3/Cadenza/issues/22) | CLI de jobs offline | D16 |
| | [#23](https://github.com/sebdavid3/Cadenza/issues/23) | Entrenador real (PyTorch → ONNX), alcance condicional | D14 |
| | [#24](https://github.com/sebdavid3/Cadenza/issues/24) | Experimentos sobre datos reales | D17, D19 |
| | [#29](https://github.com/sebdavid3/Cadenza/issues/29) | Evaluación sobre SMB y MUSCIMA++ | D34 |
| | [#30](https://github.com/sebdavid3/Cadenza/issues/30) | SER sobre transcripciones reales | D35 |
| | [#33](https://github.com/sebdavid3/Cadenza/issues/33) | Protocolo de medición de esfuerzo con participantes | D38 |
| **F** Infraestructura y cierre | [#25](https://github.com/sebdavid3/Cadenza/issues/25) | Integración continua | — |
| | [#26](https://github.com/sebdavid3/Cadenza/issues/26) | Contrato de la API v1 congelado | — |

## Alcance por decidir

Estas piezas están registradas como issues **fuera del milestone**. Cada una
empieza por decidir si entra en el alcance; si no entra, se cierra con el motivo.

| Issue | Contenido | Deuda |
|---|---|---|
| [#37](https://github.com/sebdavid3/Cadenza/issues/37) | Transcripción asíncrona con consulta de estado | D42 |
| [#40](https://github.com/sebdavid3/Cadenza/issues/40) | Operación del backend | D44 |
| [#41](https://github.com/sebdavid3/Cadenza/issues/41) | Retirar el prototipo `legacy/` | D45 |
| [#42](https://github.com/sebdavid3/Cadenza/issues/42) | Mapa tiempo→ancla para la reproducción | D12 |

Fuera del milestone queda también [#47](https://github.com/sebdavid3/Cadenza/issues/47) (inicio de sesión en el visor web,
D47): es trabajo de frontend, pero debe ir a la par de la autenticación para no
romper el visor.

## Criterios de aceptación (Definition of Done)

- [x] Todos los issues del milestone cerrados, o reclasificados con justificación
      ([#14](https://github.com/sebdavid3/Cadenza/issues/14) y [#31](https://github.com/sebdavid3/Cadenza/issues/31) cerrados con resultado negativo documentado en INV-0001; [#23](https://github.com/sebdavid3/Cadenza/issues/23) implementado con PyTorch condicional y ONNX; todos los 42 issues cerrados).
- [x] Flujo de punta a punta sobre el motor real: imagen → HOMR/Oemer → validación →
      corrección → exportación MusicXML/MIDI.
- [x] Ida y vuelta MusicXML → `ScoreIR` → MusicXML sin pérdida de clave,
      armadura, métrica, alturas, duraciones ni ligaduras.
- [x] Ninguna edición inválida puede entrar al log de ediciones.
- [x] Todos los endpoints exigen autenticación y cada usuario solo accede a sus
      sesiones.
- [x] Migraciones aplicadas y pruebas verdes sobre PostgreSQL (migraciones 0001–0011).
- [x] `packages/application` y `packages/domain` superan sus tests de
      arquitectura.
- [x] Experimentos de esfuerzo y de aprendizaje activo reproducidos sobre datos
      reales (exp_01 a exp_10).
- [x] CI verde: `pytest`, `mypy --strict`, `ruff`, `black`, `vitest`.
- [x] Contrato OpenAPI v1 publicado y tipos del frontend generados a partir de él.
- [x] `PROJECT_STATE.md` actualizado (fase, deuda, bitácora).
