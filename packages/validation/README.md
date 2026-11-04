# cadenza-validation

Motor de validación del `ScoreDocument`. Declara:

- `ValidationRule` — regla pura de **solo lectura**:
  `evaluate(document) -> list[Finding]`.
- `ValidationEngine` — orquesta reglas inyectadas y aplana sus hallazgos.
- `MeasureBalanceRule` — primera regla: la suma de duraciones de un compás debe
  coincidir con su métrica (`TimeSignature`).

Usa `music21` para interpretar la métrica (`meter.TimeSignature`) y los
`Fraction` del dominio para las duraciones. Los hallazgos se anclan al primer
evento del compás problemático.

## Capa de sugerencias (`cadenza.validation.learned`, ADR-0036)

- Las reglas que saben qué arreglos cuadran los entregan como `Finding.candidates`
  (`measure.balance`, `key.consistency`).
- `features`: la función de rasgos versionada (`FEATURE_VERSION`), la misma para el corpus,
  el entrenamiento y la inferencia, y las etiquetas de cada corrección por familia.
- `FrequencyBackoffModel`: lee el artefacto JSON (frecuencias suavizadas con retroceso),
  ordena los candidatos de las reglas y emite los posibles errores propios `learned.*`.
  Cumple por estructura el puerto `SuggestionModel` de `cadenza.application`, sin importarlo.
