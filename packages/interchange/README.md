# cadenza-interchange

Frontera canónica de notación de Cadenza. Traduce entre formatos simbólicos y el
`ScoreIR` del dominio usando `music21`, que **no** entra en `cadenza-domain` ni
en `cadenza-validation`.

- `musicxml_to_score_ir(text)` — MusicXML (texto) → `ScoreIR`.
- `read_score(path)` — MusicXML/MEI/**kern (cualquier formato que music21 lea) → `ScoreIR`.
- `score_ir_to_musicxml(score)` — `ScoreIR` → MusicXML (base de la exportación, D11).
- `music21_stream_to_score_ir(stream)` — conversión de bajo nivel reutilizable.

Alcance: corpus objetivo (monofónico y piano simple). Las coordenadas espaciales
(`bbox`) no provienen de music21; quedan en `None` (ver D4).

## Extra opcional

```powershell
uv sync --extra converters   # añade converter21 para MEI y Humdrum (**kern)
```

Sin `converter21`, music21 sigue leyendo MusicXML; MEI/**kern pueden no
interpretarse (necesarios para los corpus PrIMuS y SMB).
