# Fase 7 — Alineación con la Arquitectura Objetivo

**Objetivo:** cerrar las brechas entre la implementación de las fases 0 a 6 y la
arquitectura objetivo de [`ARCHITECTURE.md`](../../ARCHITECTURE.md) v1.1, de modo
que el backend quede completo y con un contrato estable **antes** de diseñar el
frontend y las interfaces de usuario.

Referencias: [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md) §6, §7 y §10,
[ADR-0009](../../adr/ADR-0009-capa-de-aplicacion.md),
[ADR-0010](../../adr/ADR-0010-score-ir-atributos-y-exportacion.md),
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
5. **API completa:** motor OMR configurable, imagen persistida, ediciones
   validadas, revalidación, exportación MusicXML/MIDI y métricas de esfuerzo.
6. **OMR y validación:** `bbox` reales, preprocesado, línea base `OemerEngine`,
   catálogo de reglas y su precisión y *recall*.
7. **Plano offline:** dataset desde la base de datos, *Model Registry*
   persistente, CLI de jobs, entrenador real y experimentos sobre datos reales.
8. **Infraestructura y cierre:** integración continua y contrato OpenAPI
   congelado.

## Fuera de alcance (Out-of-Scope)

- Diseño del frontend y de las interfaces de usuario: render con OSMD,
  reproducción con Tone.js y editor (D11 parte de interfaz, D12).
- Autenticación de la API, despliegue distribuido y autoescalado.
- **TFLite / Edge Learning** y **LLM / VLM**.

## Bloques e issues

| Bloque | Issue | Contenido | Deuda |
|---|---|---|---|
| **A** Análisis | [#1](https://github.com/sebdavid3/Cadenza/issues/1) | Matriz de brechas y seguimiento de la fase | — |
| **B** Dominio y datos | [#2](https://github.com/sebdavid3/Cadenza/issues/2) | `ScoreIR` con clave, armadura y ligaduras | — |
| | [#3](https://github.com/sebdavid3/Cadenza/issues/3) | Proyección de `SetClef`, `SetKey` y `SetAccidental` | — |
| | [#28](https://github.com/sebdavid3/Cadenza/issues/28) | Estabilidad de las anclas tras inserciones y borrados | D33 |
| | [#4](https://github.com/sebdavid3/Cadenza/issues/4) | `ArtifactStore` direccionado por `sha256` | — |
| | [#5](https://github.com/sebdavid3/Cadenza/issues/5) | Migración de esquema de `sessions` y `findings` | — |
| | [#6](https://github.com/sebdavid3/Cadenza/issues/6) | Persistencia verificada en PostgreSQL | D10 |
| **C** Aplicación y API | [#7](https://github.com/sebdavid3/Cadenza/issues/7) | Capa de aplicación (`packages/application`) | — |
| | [#8](https://github.com/sebdavid3/Cadenza/issues/8) | Configuración tipada y motor OMR configurable | D3, D5 |
| | [#9](https://github.com/sebdavid3/Cadenza/issues/9) | Imagen persistida y endpoint de imagen | — |
| | [#10](https://github.com/sebdavid3/Cadenza/issues/10) | Validación de ediciones antes de añadirlas al log | — |
| | [#11](https://github.com/sebdavid3/Cadenza/issues/11) | Revalidación tras las correcciones | — |
| | [#12](https://github.com/sebdavid3/Cadenza/issues/12) | Exportación MusicXML y MIDI | D11 (backend) |
| | [#13](https://github.com/sebdavid3/Cadenza/issues/13) | Métricas de esfuerzo persistidas | D13 |
| | [#27](https://github.com/sebdavid3/Cadenza/issues/27) | Listado de sesiones (`GET /sessions`) | D32 |
| **D** OMR y validación | [#14](https://github.com/sebdavid3/Cadenza/issues/14) | Investigación de `bbox` reales desde HOMR | D4 |
| | [#15](https://github.com/sebdavid3/Cadenza/issues/15) | Preprocesado configurable | D2 |
| | [#16](https://github.com/sebdavid3/Cadenza/issues/16) | `OemerEngine` como línea base | D1 |
| | [#17](https://github.com/sebdavid3/Cadenza/issues/17) | Catálogo de reglas de validación | D6 |
| | [#18](https://github.com/sebdavid3/Cadenza/issues/18) | Precisión y *recall* del validador | D8 |
| **E** Plano offline | [#19](https://github.com/sebdavid3/Cadenza/issues/19) | `DatasetBuilder` desde la base de datos | D16, D18 |
| | [#20](https://github.com/sebdavid3/Cadenza/issues/20) | `EditEvent` derivados del diff HOMR↔*ground truth* | D21 |
| | [#21](https://github.com/sebdavid3/Cadenza/issues/21) | *Model Registry* persistente y modelo activo | — |
| | [#22](https://github.com/sebdavid3/Cadenza/issues/22) | CLI de jobs offline | D16 |
| | [#23](https://github.com/sebdavid3/Cadenza/issues/23) | Entrenador real (PyTorch → ONNX), alcance condicional | D14 |
| | [#24](https://github.com/sebdavid3/Cadenza/issues/24) | Experimentos sobre datos reales | D17, D19 |
| **F** Infraestructura y cierre | [#25](https://github.com/sebdavid3/Cadenza/issues/25) | Integración continua | — |
| | [#26](https://github.com/sebdavid3/Cadenza/issues/26) | Contrato de la API v1 congelado | — |

## Criterios de aceptación (Definition of Done)

- [ ] Todos los issues del milestone cerrados, o reclasificados con justificación
      ([#14](https://github.com/sebdavid3/Cadenza/issues/14) e [#23](https://github.com/sebdavid3/Cadenza/issues/23) pueden cerrarse con un resultado negativo documentado).
- [ ] Flujo de punta a punta sobre el motor real: imagen → HOMR → validación →
      corrección → exportación MusicXML/MIDI.
- [ ] Ida y vuelta MusicXML → `ScoreIR` → MusicXML sin pérdida de clave,
      armadura, métrica, alturas, duraciones ni ligaduras.
- [ ] Ninguna edición inválida puede entrar al log de ediciones.
- [ ] Migraciones aplicadas y pruebas verdes sobre PostgreSQL.
- [ ] `packages/application` y `packages/domain` superan sus tests de
      arquitectura.
- [ ] Experimentos de esfuerzo y de aprendizaje activo reproducidos sobre datos
      reales.
- [ ] CI verde: `pytest`, `mypy --strict`, `ruff`, `black`, `vitest`.
- [ ] Contrato OpenAPI v1 publicado y tipos del frontend generados a partir de él.
- [ ] `PROJECT_STATE.md` actualizado (fase, deuda, bitácora).
