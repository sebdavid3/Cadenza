"""Los ejemplos del catálogo de reglas (ADR-0040 §12), con su texto aprobado exacto.

Cada prueba da lo leído en un compás de partida y comprueba todos los hallazgos del catálogo
completo: el mensaje y el «Qué revisar» de los que deben aparecer, y que no aparece ninguno
más. Salvo que se diga otra cosa, el compás no es el primero ni el último de su pentagrama y
tiene una sola voz. El responsable dio estos textos por buenos el 2026-10-31 (#245).
"""

from __future__ import annotations

from fractions import Fraction

from cadenza.domain import EditOp, Finding, ScoreDocument, Severity, Tie
from cadenza.validation import ValidationEngine

from packages.validation.tests.rule_builders import (
    BLANCA,
    BLANCA_PUNTILLO,
    CORCHEA,
    CORCHEA_TRESILLO,
    NEGRA,
    REDONDA,
    document,
    full,
    m,
    n,
    r,
    surrounded,
)


def _findings(doc: ScoreDocument) -> list[Finding]:
    return ValidationEngine().validate(doc)


def _texts(doc: ScoreDocument) -> list[tuple[str, str, str | None]]:
    return [(f.rule_id, f.message, f.suggested_fix) for f in _findings(doc)]


# --- measure.balance -----------------------------------------------------------------------


def test_measure_balance_le_falta() -> None:
    doc = surrounded(
        m(3, n("C4", NEGRA), n("D4", NEGRA), n("E4", CORCHEA), n("F4", NEGRA), time=(4, 4))
    )
    (finding,) = _findings(doc)
    assert finding.rule_id == "measure.balance"
    assert finding.severity is Severity.ERROR
    assert finding.message == (
        "Al compás 3 le falta una corchea para completar el 4/4: las figuras se acaban antes "
        "de la segunda corchea del tiempo 4."
    )
    assert finding.suggested_fix == (
        "Revisa las figuras del compás: puede que alguna sea más larga de lo que se leyó, o "
        "que falte una nota o un silencio de corchea."
    )
    assert (finding.anchor.measure, finding.anchor.event_index) == (3, 0)


def test_measure_balance_le_sobra_una_nota_cruza_la_barra() -> None:
    doc = surrounded(m(2, n("E4", BLANCA), n("D4", NEGRA), n("C4", BLANCA)))
    assert _texts(doc) == [
        (
            "measure.balance",
            "En el compás 2 sobra una negra para el 4/4: el Do del tiempo 4, una blanca, se "
            "sale del compás.",
            "Revisa las figuras del compás: puede que alguna sea más corta de lo que se leyó, o "
            "que sobre una nota de negra.",
        )
    ]


def test_measure_balance_le_sobra_el_compas_ya_esta_lleno() -> None:
    doc = surrounded(
        m(5, n("G4", BLANCA), n("A4", NEGRA), n("B4", NEGRA), time=(3, 4)), time=(3, 4)
    )
    assert _texts(doc) == [
        (
            "measure.balance",
            "En el compás 5 sobra una negra para el 3/4: el compás ya está lleno cuando llega "
            "el Si.",
            "Revisa las figuras del compás: puede que alguna sea más corta de lo que se leyó, o "
            "que sobre una nota de negra.",
        )
    ]


def test_measure_balance_dos_voces_cortas() -> None:
    doc = surrounded(
        m(
            7,
            n("E5", BLANCA, voice=0),
            n("D5", NEGRA, voice=0),
            n("C4", BLANCA, voice=1),
            n("B3", CORCHEA, voice=1),
        )
    )
    findings = _findings(doc)
    assert [(f.rule_id, f.anchor.voice) for f in findings] == [
        ("measure.balance", 0),
        ("measure.balance", 1),
    ]
    upper, lower = findings
    assert upper.message == (
        "En el compás 7, a la voz de arriba le falta una negra para completar el 4/4: sus "
        "figuras se acaban antes del tiempo 4."
    )
    assert upper.suggested_fix == (
        "Revisa las figuras de la voz de arriba: puede que alguna sea más larga de lo que se "
        "leyó, o que falte una nota o un silencio de negra."
    )
    assert lower.message == (
        "En el compás 7, a la voz de abajo le falta una negra con puntillo para completar el "
        "4/4: sus figuras se acaban antes de la segunda corchea del tiempo 3."
    )
    assert lower.suggested_fix == (
        "Revisa las figuras de la voz de abajo: puede que alguna sea más larga de lo que se "
        "leyó, o que falte una nota o un silencio de negra con puntillo."
    )


def test_measure_balance_tresillos_sin_marcar() -> None:
    eighths = [n(pitch, CORCHEA) for pitch in ("C5", "D5", "E5", "F5", "G5", "A5")]
    doc = surrounded(m(2, *eighths, time=(2, 4)), time=(2, 4))
    assert _texts(doc) == [
        (
            "measure.balance",
            "En el compás 2 sobra una negra para el 2/4: sus seis corcheas van en grupos de "
            "tres, como los tresillos.",
            "Si en la partitura son tresillos, márcalos como tresillos; si no, revisa las "
            "figuras.",
        )
    ]


def test_measure_balance_no_dispara_en_la_anacrusa() -> None:
    doc = document(
        [
            m(1, n("D4", NEGRA), time=(3, 4)),
            full(2, (3, 4)),
            full(3, (3, 4)),
            full(4, (3, 4)),
        ]
    )
    assert _findings(doc) == []


def test_measure_balance_no_dispara_si_el_ultimo_compas_completa_la_anacrusa() -> None:
    doc = document(
        [
            m(1, n("D4", NEGRA), time=(3, 4)),
            full(2, (3, 4)),
            full(3, (3, 4)),
            m(4, n("C5", BLANCA), time=(3, 4)),
        ]
    )
    assert _findings(doc) == []


def test_measure_balance_no_dispara_con_un_silencio_de_compas() -> None:
    doc = surrounded(m(2, r(REDONDA), time=(3, 4)), time=(3, 4))
    assert _findings(doc) == []


# --- time.signature ------------------------------------------------------------------------


def test_time_signature_en_todo_el_tramo() -> None:
    four = [n(pitch, NEGRA) for pitch in ("C5", "D5", "E5", "F5")]
    doc = document(
        [
            m(1, n("D4", NEGRA), time=(3, 4)),
            m(2, *four, time=(3, 4)),
            m(3, *four, time=(3, 4)),
            m(4, n("C5", BLANCA_PUNTILLO), time=(3, 4)),
        ]
    )
    (finding,) = _findings(doc)
    assert finding.rule_id == "time.signature"
    assert finding.severity is Severity.WARNING
    assert finding.message == (
        "Los compases 2 y 3 suman cuatro negras y la indicación de compás es 3/4."
    )
    assert finding.suggested_fix == (
        "Revisa la indicación de compás del compás 1: puede que sea 4/4 (C). Mientras no "
        "cambie, la duración de cada compás se comprueba con cuatro negras."
    )
    assert (finding.anchor.measure, finding.anchor.event_index) == (1, 0)


def test_time_signature_desde_un_compas() -> None:
    three = [n(pitch, NEGRA) for pitch in ("C5", "D5", "E5")]
    two = [n(pitch, NEGRA) for pitch in ("C5", "D5")]
    doc = document(
        [
            m(1, n("D4", NEGRA), time=(3, 4)),
            *(m(number, *three, time=(3, 4)) for number in range(2, 9)),
            *(m(number, *two, time=(3, 4)) for number in range(9, 12)),
            m(12, n("G4", BLANCA_PUNTILLO), time=(3, 4)),
        ]
    )
    (finding,) = _findings(doc)
    assert finding.rule_id == "time.signature"
    assert finding.message == (
        "Desde el compás 9, los compases suman dos negras y la indicación sigue siendo 3/4."
    )
    assert finding.suggested_fix == "Revisa si en el compás 9 cambia el compás: puede que sea 2/4."
    assert finding.anchor.measure == 9


# --- tuplet.incomplete ---------------------------------------------------------------------


def test_tuplet_incomplete() -> None:
    doc = surrounded(
        m(6, n("C5", CORCHEA_TRESILLO), n("D5", CORCHEA_TRESILLO), n("E5", NEGRA), time=(2, 4)),
        time=(2, 4),
    )
    (finding,) = _findings(doc)
    assert finding.rule_id == "tuplet.incomplete"
    assert finding.severity is Severity.ERROR
    assert finding.message == (
        "En el compás 6, al tresillo de corcheas del tiempo 1 le falta una corchea."
    )
    assert finding.suggested_fix == (
        "Revisa el tresillo: puede que falte una nota o que una de sus corcheas sea más larga."
    )
    assert (finding.anchor.measure, finding.anchor.event_index) == (6, 0)
    assert finding.candidates == ()


# --- accidental.repeated -------------------------------------------------------------------


def test_accidental_repeated_becuadro() -> None:
    doc = document([m(1, n("F#4", NEGRA), n("F#4", NEGRA), n("G4", BLANCA), fifths=0), full(2)])
    (finding,) = _findings(doc)
    assert finding.rule_id == "accidental.repeated"
    assert finding.severity is Severity.WARNING
    assert finding.message == (
        "El Fa♯ del tiempo 2 repite el sostenido del Fa del tiempo 1, y la armadura no lo lleva."
    )
    assert finding.suggested_fix == (
        "Mira si en la partitura este Fa lleva becuadro: entonces es Fa, no Fa♯."
    )
    assert (finding.anchor.measure, finding.anchor.event_index) == (1, 1)
    (candidate,) = finding.candidates
    assert candidate.op is EditOp.SET_ACCIDENTAL
    assert candidate.anchor == finding.anchor
    assert dict(candidate.after or {}) == {"accidental": ""}


def test_accidental_repeated_bemol() -> None:
    doc = document(
        [
            full(1, (2, 4)),
            full(2, (2, 4)),
            full(3, (2, 4)),
            m(4, n("Eb4", CORCHEA), n("D4", CORCHEA), n("Eb4", NEGRA), time=(2, 4), fifths=-1),
            full(5, (2, 4)),
        ]
    )
    assert _texts(doc) == [
        (
            "accidental.repeated",
            "El Mi♭ del tiempo 2 repite el bemol del Mi del tiempo 1, y la armadura no lo lleva.",
            "Mira si en la partitura este Mi lleva becuadro: entonces es Mi, no Mi♭.",
        )
    ]


def test_accidental_repeated_no_dispara_en_la_sensible_escrita() -> None:
    """Ni `accidental.repeated`, que solo señala repeticiones, ni `key.consistency`, que antes
    señalaba un sostenido con armadura de bemoles."""
    doc = surrounded(m(3, n("F#4", NEGRA), n("G4", NEGRA), time=(2, 4), fifths=-2), time=(2, 4))
    assert _findings(doc) == []


def test_accidental_repeated_no_dispara_tras_un_becuadro_intermedio() -> None:
    doc = surrounded(m(2, n("F#4", NEGRA), n("F4", NEGRA), n("F#4", BLANCA), fifths=0))
    assert _findings(doc) == []


# --- key.consistency -----------------------------------------------------------------------


def test_key_consistency() -> None:
    upper = [full(8), m(9, n("D5", REDONDA), fifths=2), full(10)]
    lower = [full(8), m(9, n("D3", REDONDA), fifths=1), full(10)]
    upper[0] = m(8, n("D5", REDONDA), fifths=2)
    lower[0] = m(8, n("D3", REDONDA), fifths=2)
    doc = document(upper, lower)
    (finding,) = _findings(doc)
    assert finding.rule_id == "key.consistency"
    assert finding.severity is Severity.WARNING
    assert finding.message == (
        "En el compás 9, la armadura del pentagrama de abajo (un sostenido) no coincide con la "
        "de arriba (dos sostenidos)."
    )
    assert finding.suggested_fix == (
        "Revisa las dos armaduras: en los pentagramas de un mismo piano suelen ser iguales."
    )
    assert (finding.anchor.staff, finding.anchor.measure, finding.anchor.event_index) == (1, 9, 0)
    (candidate,) = finding.candidates
    assert candidate.op is EditOp.SET_KEY
    assert dict(candidate.after or {}) == {"fifths": 2}


# --- pitch.range ---------------------------------------------------------------------------


def test_pitch_range() -> None:
    doc = surrounded(m(4, n("A5", NEGRA), n("C8", NEGRA), time=(2, 4)), time=(2, 4))
    (finding,) = _findings(doc)
    assert finding.rule_id == "pitch.range"
    assert finding.message == (
        "El Do8 del tiempo 2 está muy por encima de lo que se escribe en clave de sol (de Sol2 "
        "a Do7)."
    )
    assert finding.suggested_fix == (
        "Revisa la octava de la nota o la clave del pentagrama: puede que sea Do7."
    )
    (candidate,) = finding.candidates
    assert candidate.op is EditOp.SET_PITCH
    assert dict(candidate.after or {}) == {"pitch": "C7"}


# --- tie.resolution ------------------------------------------------------------------------


def test_tie_resolution_otra_altura() -> None:
    doc = document(
        [
            full(1),
            full(2),
            m(3, n("C4", NEGRA), n("D4", NEGRA), n("E4", NEGRA), n("G4", NEGRA, tie=Tie.START)),
            m(4, n("A4", BLANCA), n("B4", BLANCA)),
            full(5),
        ]
    )
    (finding,) = _findings(doc)
    assert finding.rule_id == "tie.resolution"
    assert finding.severity is Severity.WARNING
    assert finding.message == (
        "La ligadura del Sol del tiempo 4 no llega a otro Sol: lo siguiente es un La, en el "
        "compás 4."
    )
    assert finding.suggested_fix == (
        "Si en la partitura une notas distintas, es una ligadura de expresión y este aviso se "
        "puede descartar; si no, revisa la altura del La."
    )
    assert (finding.anchor.measure, finding.anchor.event_index) == (3, 3)


def test_tie_resolution_silencio() -> None:
    doc = surrounded(
        m(2, n("C5", NEGRA), r(NEGRA, tie=Tie.START), n("D5", NEGRA), time=(3, 4)), time=(3, 4)
    )
    assert _texts(doc) == [
        (
            "tie.resolution",
            "El silencio de negra del tiempo 2 tiene una ligadura, y los silencios no se ligan.",
            "Revisa si en la partitura ese silencio es una nota.",
        )
    ]


# --- voice.collision -----------------------------------------------------------------------


def test_voice_collision() -> None:
    doc = surrounded(
        m(
            2,
            n("C4", NEGRA),
            n("E4", CORCHEA, chord=True),
            n("G4", NEGRA, chord=True),
            n("B4", BLANCA_PUNTILLO),
        )
    )
    (finding,) = _findings(doc)
    assert finding.rule_id == "voice.collision"
    assert finding.severity is Severity.ERROR
    assert (
        finding.message == "En el acorde del tiempo 1, el Mi es una corchea y el Do es una negra."
    )
    assert finding.suggested_fix == (
        "Si en la partitura suenan juntas, iguala la figura; si el Mi va aparte, es de otra voz."
    )
    assert (finding.anchor.measure, finding.anchor.event_index) == (2, 1)


def test_voice_collision_no_dispara_en_una_nota_de_adorno() -> None:
    doc = surrounded(m(2, n("G#4", Fraction(0)), n("A4", NEGRA), n("B4", BLANCA_PUNTILLO)))
    assert _findings(doc) == []
