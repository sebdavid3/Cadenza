# ADR-0009: Capa de aplicación con casos de uso

- **Estado:** Aceptado
- **Fecha:** 2026-10-03
- **Decisores:** Arquitecto de Software, Dirección del proyecto Cadenza
- **Relacionado:** [ADR-0001](ADR-0001-monolito-modular-hexagonal.md), [ADR-0003](ADR-0003-separacion-planos-computo.md), [ADR-0007](ADR-0007-edit-events-inmutables.md)

---

## Contexto

El ADR-0001 fija una arquitectura hexagonal con el dominio en el centro, pero no
dice dónde vive la **orquestación** de una operación completa. En la
implementación de las fases 0 a 6 esa orquestación quedó dentro de los *handlers*
de FastAPI (`apps/api/src/cadenza/api/main.py`): el *handler* de `/transcribe`
ejecuta el OMR, valida, construye los registros del ORM y los guarda.

Esto tiene tres consecuencias:

- La lógica solo se puede ejecutar a través de HTTP. Los experimentos
  (`ml/experiments`) y los jobs del plano offline reimplementan partes del flujo
  en lugar de reutilizarlo.
- Los *handlers* conocen a la vez FastAPI, SQLAlchemy y el dominio, que es el
  acoplamiento que la arquitectura hexagonal busca evitar.
- Las reglas de la operación no tienen un lugar propio. El caso más visible:
  `POST /sessions/{id}/edits` añade la edición al log sin comprobar que sea
  aplicable, y una edición inválida anula de forma permanente la proyección de la
  sesión, porque el log es *append-only* (ADR-0007).

## Decisión

Se introduce una **capa de aplicación** en un paquete propio,
`packages/application`, situada entre los conductores (API, CLI) y el dominio.

- Cada operación del sistema es un **caso de uso**: una función o clase que
  recibe sus puertos por inyección y devuelve tipos del dominio o DTO propios.
- Casos de uso iniciales: `transcribe_score`, `get_session`, `append_edit`,
  `revalidate`, `export_score` y `record_effort`.
- La capa declara los puertos que necesita y que aún no existen
  (`SessionRepository`, `ArtifactStore`, `ScoreExporter`) y reutiliza los ya
  definidos (`OMREngine`, `ValidationRule`, `EditEventRepository`).
- Los errores se expresan como excepciones de aplicación (`SessionNotFound`,
  `InvalidEdit`, `SequenceConflict`); cada conductor las traduce a su medio
  (códigos HTTP, códigos de salida de la CLI).
- `apps/api` queda como **raíz de composición**: construye los adaptadores,
  los inyecta en los casos de uso y traduce petición y respuesta.

Reglas de dependencia:

```text
apps/api, ml/  ──►  packages/application  ──►  packages/domain
                          │
                          └──► puertos (interfaces), nunca adaptadores concretos
```

`packages/application` no importa FastAPI, SQLAlchemy, `music21`, `homr` ni
`onnxruntime`. Un test de arquitectura lo verifica, igual que el test de pureza
del dominio.

## Consecuencias

### Positivas
- **Una sola implementación** de cada operación, compartida por la API, los
  experimentos y los jobs offline.
- **Las reglas de la operación tienen dueño**: validar una edición antes de
  añadirla, revalidar tras corregir o decidir qué se persiste son decisiones de
  la capa de aplicación, comprobables sin servidor ni base de datos.
- **Pruebas más simples**: los casos de uso se prueban con adaptadores falsos en
  memoria.
- El contrato de la API se puede congelar sin congelar la lógica.

### Riesgos / costos
- Un paquete y una capa de indirección más para un equipo pequeño.
- Hay que evitar que la capa se convierta en un simple pasamanos: un caso de uso
  que solo reenvía una llamada no justifica su existencia.
- La migración toca los cuatro *handlers* actuales y sus pruebas.

## Alternativas consideradas

1. **Mantener la lógica en los *handlers*.** Descartado: impide reutilizarla
   fuera de HTTP y mezcla tres responsabilidades.
2. **Colocar los casos de uso en `packages/domain`.** Descartado: los casos de
   uso dependen de puertos de infraestructura y de orden de operaciones; el
   dominio debe seguir siendo puro y sin efectos.
3. **Un módulo `services` dentro de `apps/api`.** Descartado: seguiría atado al
   proceso de la API y no sería importable desde `ml/` sin arrastrar FastAPI.
