# Fase 2 — Validación por Reglas

**Objetivo:** implementar el motor de validación sintáctica/semántica sobre el
`ScoreIR`, con reglas puras registrables y hallazgos anclados. Es el **componente
central del aporte** del proyecto.

Referencias: [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md) §5 (M2),
[ADR-0002](../../adr/ADR-0002-score-document-anchor-index.md),
[ADR-0004](../../adr/ADR-0004-persistencia-postgresql-jsonb.md).

---

## Requerimientos

1. Puerto `Validator.evaluate(ScoreIR) → list[Finding]`.
2. Reglas **puras y registrables**: `Rule.evaluate(ScoreIR) → list[Finding]`.
3. Catálogo inicial de reglas (corpus monofónico y piano simple):
   - balance de compás (suma de duraciones = métrica);
   - armadura y alteraciones consistentes; mismas armaduras entre pentagramas;
   - colisiones de voz (sin solapamiento de tiempo en una misma voz);
   - rango de alturas razonable;
   - cierres de ligaduras y elementos básicos.
4. `Finding` con `anchor`, `rule_id`, `severity`, `message`, `suggested_fix?`.
5. Persistencia de findings en PostgreSQL con columna **JSONB**.
6. Pruebas con **partituras sintéticas** por regla y, cuando aplique,
   *property-based testing* (`hypothesis`).
7. Adaptador de parseo MusicXML ↔ `ScoreIR` (`music21`), como frontera del dominio.

## Fuera de alcance (Out-of-Scope)

- Corrección automática de la partitura (el sistema **señala**, no reescribe).
- Editor HITL y captura de correcciones (Fase 3).
- Aprendizaje activo y entrenamiento (Fase 4).
- Nuevas reglas fuera del corpus objetivo declarado.

## Criterios de aceptación (Definition of Done)

- [ ] Catálogo de reglas implementado con pruebas sintéticas que pasan.
- [ ] Findings correctamente anclados a eventos del `ScoreDocument`.
- [ ] Persistencia JSONB operativa y consultable.
- [ ] Métricas del validador (precisión/recall sobre casos conocidos) reportadas.
- [ ] `PROJECT_STATE.md` actualizado.
