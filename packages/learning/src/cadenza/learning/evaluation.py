"""Métricas de evaluación simbólica: SER, distancia de edición y serialización a símbolos."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Final

from cadenza.domain import Clef, EventKind, KeySignature, ScoreIR, TimeSignature

_FRACTION_TO_DURATION_NAME: Final[dict[Fraction, str]] = {
    Fraction(4, 1): "whole",
    Fraction(3, 1): "dotted_half",
    Fraction(2, 1): "half",
    Fraction(3, 2): "dotted_quarter",
    Fraction(1, 1): "quarter",
    Fraction(3, 4): "dotted_eighth",
    Fraction(1, 2): "eighth",
    Fraction(3, 8): "dotted_sixteenth",
    Fraction(1, 4): "sixteenth",
    Fraction(3, 16): "dotted_thirty_second",
    Fraction(1, 8): "thirty_second",
    Fraction(1, 16): "sixty_fourth",
}

_SHARPS_ORDER: Final[tuple[str, ...]] = ("F", "C", "G", "D", "A", "E", "B")
_FLATS_ORDER: Final[tuple[str, ...]] = ("B", "E", "A", "D", "G", "C", "F")


def format_duration_symbol(duration: Fraction | None) -> str:
    """Convierte una duración en fracción a su etiqueta simbólica en el vocabulario.

    Usa nombres estándar (whole, half, quarter, eighth, etc.) o la fracción
    irreducible 'num/den' para figuras compuestas o irregulares (tresillos, etc.).
    """
    if duration is None:
        return "unspecified"
    if duration in _FRACTION_TO_DURATION_NAME:
        return _FRACTION_TO_DURATION_NAME[duration]
    return f"{duration.numerator}/{duration.denominator}"


def resolve_pitch_with_key_signature(pitch: str | None, fifths: int) -> str | None:
    """Aplica la alteración de la armadura si la altura no contiene alteración explícita.

    En notaciones como MEI o partituras donde la armadura rige los tonos de la escala,
    una nota en la línea de Si en Mib mayor (3 bemoles) representa Sib, a menos
    que esté explícitamente alterada (p. ej. con becuadro o sostenido).
    """
    if not pitch:
        return pitch
    step = pitch[0].upper()
    rest = pitch[1:]
    if rest and rest[0] in ("#", "b", "x", "-", "+"):
        return pitch

    acc = ""
    if fifths > 0 and step in _SHARPS_ORDER[:fifths]:
        acc = "#"
    elif fifths < 0 and step in _FLATS_ORDER[: abs(fifths)]:
        acc = "b"
    return f"{step}{acc}{rest}"


def format_clef_symbol(clef: Clef | None) -> str | None:
    """Formatea una clave musical: 'clef:G2', 'clef:F4', 'clef:C3', 'clef:G2-1'."""
    if clef is None:
        return None
    octave_str = f"{clef.octave_change:+d}" if clef.octave_change != 0 else ""
    return f"clef:{clef.sign}{clef.line}{octave_str}"


def format_key_signature_symbol(key_signature: KeySignature | None) -> str | None:
    """Formatea una armadura de clave: 'key:0', 'key:1#', 'key:3b', etc."""
    if key_signature is None:
        return None
    fifths = key_signature.fifths
    if fifths == 0:
        return "key:0"
    if fifths > 0:
        return f"key:{fifths}#"
    return f"key:{abs(fifths)}b"


def format_time_signature_symbol(time_signature: TimeSignature | None) -> str | None:
    """Formatea una métrica de compás: 'time:3/4', 'time:4/4', 'time:6/8'."""
    if time_signature is None:
        return None
    return f"time:{time_signature.beats}/{time_signature.beat_type}"


def score_to_symbol_sequence(
    score: ScoreIR,
    *,
    apply_key_signature: bool = True,
) -> list[str]:
    """Serializa un `ScoreIR` a una secuencia canónica de símbolos atómicos.

    Vocabulario documentado:
    - Claves:         'clef:{sign}{line}[{octave_change}]' (p. ej. 'clef:G2', 'clef:F4')
    - Armaduras:      'key:{0|N#|Nb}'                      (p. ej. 'key:0', 'key:3b', 'key:1#')
    - Métricas:       'time:{beats}/{beat_type}'           (p. ej. 'time:3/4', 'time:4/4')
    - Notas:          'note:{pitch}:{duration}'            (p. ej. 'note:C4:quarter')
    - Silencios:      'rest:{duration}'                    (p. ej. 'rest:quarter', 'rest:sixteenth')
    - Barras:         'barline'                            (al final de cada compás)

    Si `apply_key_signature` es True (por defecto), las alturas que carecen de alteración
    explícita heredan la alteración tonal de la armadura activa del compás.
    """
    symbols: list[str] = []
    active_fifths = 0

    for part in score.parts:
        for staff in part.staves:
            for measure in staff.measures:
                # 1. Clave
                clef_sym = format_clef_symbol(measure.clef)
                if clef_sym is not None:
                    symbols.append(clef_sym)

                # 2. Armadura
                if measure.key_signature is not None:
                    active_fifths = measure.key_signature.fifths
                    key_sym = format_key_signature_symbol(measure.key_signature)
                    if key_sym is not None:
                        symbols.append(key_sym)

                # 3. Métrica
                time_sym = format_time_signature_symbol(measure.time_signature)
                if time_sym is not None:
                    symbols.append(time_sym)

                # 4. Eventos musicales
                for event in measure.events:
                    duration_str = format_duration_symbol(event.duration_beats)
                    if event.kind == EventKind.REST:
                        symbols.append(f"rest:{duration_str}")
                    elif event.kind == EventKind.NOTE:
                        p = event.pitch
                        if apply_key_signature and p is not None:
                            p = resolve_pitch_with_key_signature(p, active_fifths)
                        pitch_str = p if p is not None else "none"
                        symbols.append(f"note:{pitch_str}:{duration_str}")

                # 5. Barra de compás
                symbols.append("barline")

    return symbols


score_to_symbols = score_to_symbol_sequence


@dataclass(frozen=True, slots=True)
class SerResult:
    """Resultado del cálculo de Symbol Error Rate (SER) entre dos secuencias o partituras."""

    reference_symbols: int
    hypothesis_symbols: int
    edit_distance: int
    ser: float

    def to_primitive(self) -> dict[str, Any]:
        return {
            "reference_symbols": self.reference_symbols,
            "hypothesis_symbols": self.hypothesis_symbols,
            "edit_distance": self.edit_distance,
            "ser": self.ser,
        }


def _levenshtein(reference: Sequence[str], hypothesis: Sequence[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for row, ref in enumerate(reference, start=1):
        current = [row]
        for column, hyp in enumerate(hypothesis, start=1):
            cost = 0 if ref == hyp else 1
            current.append(
                min(previous[column] + 1, current[column - 1] + 1, previous[column - 1] + cost)
            )
        previous = current
    return previous[-1]


def symbol_error_rate(reference: Sequence[str], hypothesis: Sequence[str]) -> float:
    """Fracción de símbolos incorrectos respecto a la referencia (acotada a 1.0)."""
    if not reference:
        return 0.0 if not hypothesis else 1.0
    return min(1.0, _levenshtein(reference, hypothesis) / len(reference))


def score_ser_pair(
    reference: ScoreIR | Sequence[str],
    hypothesis: ScoreIR | Sequence[str],
    *,
    apply_key_signature: bool = True,
) -> SerResult:
    """Calcula la SER y la distancia de Levenshtein entre dos `ScoreIR` o secuencias de símbolos."""
    if isinstance(reference, ScoreIR):
        ref_seq = score_to_symbol_sequence(reference, apply_key_signature=apply_key_signature)
    else:
        ref_seq = list(reference)

    if isinstance(hypothesis, ScoreIR):
        hyp_seq = score_to_symbol_sequence(hypothesis, apply_key_signature=apply_key_signature)
    else:
        hyp_seq = list(hypothesis)

    dist = _levenshtein(ref_seq, hyp_seq)
    ref_len = len(ref_seq)
    ser_val = (min(1.0, dist / ref_len)) if ref_len > 0 else (0.0 if not hyp_seq else 1.0)

    return SerResult(
        reference_symbols=ref_len,
        hypothesis_symbols=len(hyp_seq),
        edit_distance=dist,
        ser=ser_val,
    )


def normalized_edit_distance(reference: Sequence[str], hypothesis: Sequence[str]) -> float:
    """Distancia de edición normalizada por la longitud máxima (OMR-NED simplificada)."""
    denominator = max(len(reference), len(hypothesis))
    if denominator == 0:
        return 0.0
    return _levenshtein(reference, hypothesis) / denominator
