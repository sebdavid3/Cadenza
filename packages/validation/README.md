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
