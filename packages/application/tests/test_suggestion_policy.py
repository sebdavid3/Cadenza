"""La política de qué sugerencias se muestran (ADR-0036, enmienda 19).

El filtro va en el camino de producción, en la aplicación y no en el modelo: solo se
muestran (y por tanto solo se guardan y se pueden aplicar) las sugerencias con un nivel de
confianza al menos el mínimo y de una familia permitida. Los hallazgos de las reglas no
cambian, aunque se queden sin sugerencias; los `learned.*` de una familia no permitida, o sin
ninguna sugerencia que pase el filtro, no se emiten.
"""

from __future__ import annotations

from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path

import pytest
from cadenza.application import (
    InMemoryEditEventRepository,
    InMemorySessionRepository,
    PolicySuggestionModel,
    Role,
    SuggestionModel,
    SuggestionPolicy,
    User,
    revalidate,
    transcribe_score,
)
from cadenza.application.suggestions import suggest, suggestion_family
from cadenza.domain import (
    Anchor,
    EditOp,
    Event,
    EventKind,
    Finding,
    KeySignature,
    Measure,
    Part,
    Provenance,
    ScoreDocument,
    ScoreIR,
    Severity,
    Staff,
    SuggestedEdit,
    SuggestedFinding,
    SuggestionResult,
    TimeSignature,
    build_anchor_index,
)
from cadenza.omr import OMREngine
from cadenza.validation import ValidationEngine

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
STAFF = "P1-S1"


def _score() -> ScoreIR:
    """4/4 en Fa mayor: el compás 1 tiene tres negras (a `measure.balance` le falta una) y el
    2, un Si natural que las reglas no ven."""
    measures = (
        Measure(
            number=1,
            events=tuple(
                Event(kind=EventKind.NOTE, pitch=p, duration_beats=Fraction(1))
                for p in ("C4", "D4", "E4")
            ),
            time_signature=TimeSignature(4, 4),
            key_signature=KeySignature(fifths=-1),
        ),
        Measure(
            number=2,
            events=tuple(
                Event(kind=EventKind.NOTE, pitch=p, duration_beats=Fraction(1))
                for p in ("B4", "A4", "G4", "F4")
            ),
        ),
    )
    return ScoreIR(parts=(Part(id="P1", staves=(Staff(id=STAFF, measures=measures),)),))


def _document() -> ScoreDocument:
    score = _score()
    return ScoreDocument(
        id="doc", score=score, anchors=build_anchor_index(score), provenance=Provenance("fake")
    )


class _Engine(OMREngine):
    @property
    def engine_id(self) -> str:
        return "fake"

    def transcribe(self, image_path: Path) -> ScoreDocument:
        return _document()


def _anchor(measure: int, index: int) -> Anchor:
    return Anchor(part=0, staff=0, measure=measure, voice=0, event_index=index, staff_id=STAFF)


def _edit(op: EditOp, anchor: Anchor, after: dict[str, object] | None, level: str) -> SuggestedEdit:
    return SuggestedEdit(
        op=op,
        anchor=anchor,
        after=after,
        confidence=0.9 if level == "high" else 0.4,
        confidence_level=level,
        explanation="…",
        source="learned",
        model_version="sug-mixed",
    )


def _learned(family: str, edit: SuggestedEdit) -> SuggestedFinding:
    return SuggestedFinding(
        Finding(
            anchor=edit.anchor,
            rule_id=f"learned.{family}",
            severity=Severity.WARNING,
            message="Puede que…",
        ),
        (edit,),
    )


class MixedModel:
    """A cada hallazgo de regla le pone sugerencias de varias familias y niveles, y propone
    posibles errores propios de alteración (alta y media), de duración y de altura."""

    version = "sug-mixed"

    def __init__(self) -> None:
        self.calls = 0

    def suggest(self, document: ScoreDocument, findings: Sequence[Finding]) -> SuggestionResult:
        self.calls += 1
        ranked = []
        for finding in findings:
            anchor = finding.anchor
            ranked.append(
                SuggestedFinding(
                    finding,
                    (
                        _edit(EditOp.SET_DURATION, anchor, {"duration_beats": "2"}, "high"),
                        _edit(EditOp.SET_ACCIDENTAL, anchor, {"accidental": "#"}, "medium"),
                        _edit(
                            EditOp.INSERT_EVENT,
                            anchor,
                            {"kind": "rest", "duration_beats": "1", "voice": 0},
                            "high",
                        ),
                        _edit(EditOp.SET_ACCIDENTAL, anchor, {"accidental": "b"}, "high"),
                    ),
                )
            )
        return SuggestionResult(
            findings=(
                *ranked,
                _learned(
                    "accidental",
                    _edit(EditOp.SET_ACCIDENTAL, _anchor(2, 0), {"accidental": "b"}, "high"),
                ),
                _learned(
                    "accidental",
                    _edit(EditOp.SET_ACCIDENTAL, _anchor(2, 1), {"accidental": "#"}, "medium"),
                ),
                _learned(
                    "duration",
                    _edit(EditOp.SET_DURATION, _anchor(2, 2), {"duration_beats": "2"}, "high"),
                ),
                _learned(
                    "pitch",
                    _edit(EditOp.SET_PITCH, _anchor(2, 3), {"pitch": "E4"}, "high"),
                ),
            )
        )


def _shown(
    policy: SuggestionPolicy | None, model: SuggestionModel | None = None
) -> list[tuple[str, int, list[tuple[str, str | None]]]]:
    document = _document()
    findings = ValidationEngine().validate(document)
    inner = model or MixedModel()
    wrapped = inner if policy is None else PolicySuggestionModel(inner, policy)
    return [
        (
            finding.rule_id,
            finding.anchor.measure,
            [(s.op.value, s.confidence_level) for s in suggestions],
        )
        for finding, suggestions in suggest(document, findings, wrapped)
    ]


# --- La política ---------------------------------------------------------------------------


def test_a_policy_is_parsed_from_its_configuration() -> None:
    policy = SuggestionPolicy.parse(" High ", "accidental, Duration ,")
    assert policy == SuggestionPolicy(
        min_level="high", families=frozenset({"accidental", "duration"})
    )
    assert SuggestionPolicy.parse("medium", "insertion").families == frozenset({"insertion"})


@pytest.mark.parametrize(
    ("min_level", "families"),
    [
        ("low", "accidental"),
        ("", "accidental"),
        ("high", ""),
        ("high", " , "),
        ("high", "accidental,tempo"),
    ],
)
def test_an_invalid_policy_is_rejected(min_level: str, families: str) -> None:
    with pytest.raises(ValueError):
        SuggestionPolicy.parse(min_level, families)


def test_the_family_of_a_suggestion_is_that_of_its_operation() -> None:
    anchor = _anchor(1, 0)
    assert [
        suggestion_family(SuggestedEdit(op=op, anchor=anchor, after=None))
        for op in (
            EditOp.SET_ACCIDENTAL,
            EditOp.SET_DURATION,
            EditOp.SET_PITCH,
            EditOp.DELETE_EVENT,
            EditOp.INSERT_EVENT,
            EditOp.SET_CLEF,
        )
    ] == ["accidental", "duration", "pitch", "delete", "insertion", None]


# --- Qué se muestra ------------------------------------------------------------------------


def test_without_a_policy_everything_admissible_is_shown() -> None:
    shown = _shown(None)
    assert [rule for rule, _, _ in shown] == [
        "measure.balance",
        "learned.accidental",
        "learned.accidental",
        "learned.duration",
        "learned.pitch",
    ]
    assert len(shown[0][2]) == 3


def test_only_high_accidentals_are_shown_and_rule_findings_stay() -> None:
    shown = _shown(SuggestionPolicy(min_level="high", families=frozenset({"accidental"})))
    # El hallazgo de la regla sigue, con solo la alteración de confianza alta; de los propios
    # queda la alteración alta: la media, la duración y la altura no se emiten.
    assert shown == [
        ("measure.balance", 1, [("SetAccidental", "high")]),
        ("learned.accidental", 2, [("SetAccidental", "high")]),
    ]


def test_a_rule_finding_without_suggestions_that_pass_stays_without_them() -> None:
    shown = _shown(SuggestionPolicy(min_level="high", families=frozenset({"pitch"})))
    assert shown == [
        ("measure.balance", 1, []),
        ("learned.pitch", 2, [("SetPitch", "high")]),
    ]


def test_medium_shows_both_levels_of_the_allowed_families() -> None:
    shown = _shown(
        SuggestionPolicy(min_level="medium", families=frozenset({"accidental", "insertion"}))
    )
    assert shown == [
        (
            "measure.balance",
            1,
            [("SetAccidental", "medium"), ("InsertEvent", "high"), ("SetAccidental", "high")],
        ),
        ("learned.accidental", 2, [("SetAccidental", "high")]),
        ("learned.accidental", 2, [("SetAccidental", "medium")]),
    ]


def test_an_unscored_candidate_counts_as_medium() -> None:
    class Unscored(MixedModel):
        def suggest(self, document: ScoreDocument, findings: Sequence[Finding]) -> SuggestionResult:
            return SuggestionResult(
                findings=tuple(
                    SuggestedFinding(
                        finding,
                        (
                            SuggestedEdit(
                                op=EditOp.SET_ACCIDENTAL,
                                anchor=finding.anchor,
                                after={"accidental": "b"},
                            ),
                        ),
                    )
                    for finding in findings
                )
            )

    accidental = frozenset({"accidental"})
    assert _shown(SuggestionPolicy("high", accidental), Unscored()) == [("measure.balance", 1, [])]
    assert _shown(SuggestionPolicy("medium", accidental), Unscored()) == [
        ("measure.balance", 1, [("SetAccidental", None)])
    ]


def test_the_filtered_layer_keeps_the_version_of_its_model() -> None:
    model = MixedModel()
    policy = SuggestionPolicy(min_level="high", families=frozenset({"accidental"}))
    wrapped = PolicySuggestionModel(model, policy)
    assert wrapped.version == "sug-mixed"
    assert wrapped.policy is policy and wrapped.model is model


# --- En los casos de uso -------------------------------------------------------------------


def test_only_what_the_policy_shows_is_stored(tmp_path: Path) -> None:
    edits = InMemoryEditEventRepository()
    sessions = InMemorySessionRepository(edit_repository=edits)
    owner = User(id="u1", username="ana", password_hash="h", role=Role.TRANSCRIPTOR)
    model = PolicySuggestionModel(
        MixedModel(), SuggestionPolicy(min_level="high", families=frozenset({"accidental"}))
    )
    image = tmp_path / "page.png"
    image.write_bytes(PNG)
    result = transcribe_score(
        image,
        omr_engine=_Engine(),
        validator=ValidationEngine(),
        session_repository=sessions,
        current_user=owner,
        suggestion_model=model,
        condition="assisted",
    )

    def stored() -> list[tuple[str, list[tuple[str, str]]]]:
        return [
            (f.rule_id, [(s.op, s.confidence_level) for s in f.suggestions])
            for f in sessions.list_findings(result.session_id)
        ]

    expected = [
        ("measure.balance", [("SetAccidental", "high")]),
        ("learned.accidental", [("SetAccidental", "high")]),
    ]
    assert stored() == expected
    document = sessions.get(result.session_id)
    assert document is not None
    assert document.document["provenance"]["suggestions_version"] == "sug-mixed"

    revalidate(
        result.session_id,
        validator=ValidationEngine(),
        session_repository=sessions,
        edit_repository=edits,
        current_user=owner,
        suggestion_model=model,
    )
    assert stored() == expected
