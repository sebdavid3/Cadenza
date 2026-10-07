"""Prueba de punta a punta: transcripción de piano, validación, edición y exportación."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from cadenza.domain import (
    Anchor,
    EditEvent,
    EditOp,
    apply_edit,
)
from cadenza.interchange import score_ir_to_musicxml
from cadenza.omr import HOMREngine
from cadenza.validation import MeasureBalanceRule, ValidationEngine

PIANO_XML_FIXTURE = Path(__file__).parent / "fixtures" / "piano.musicxml"


def test_piano_pipeline_transcribe_validate_edit_export(tmp_path: Path) -> None:
    # 1. Imagen sintética para la entrada
    fake_image = tmp_path / "piano_score.png"
    fake_image.write_bytes(b"\x89PNG\r\n\x1a\nfake-piano-image-content")

    engine = HOMREngine(use_gpu=False, document_id="piano-session-001")
    piano_xml_content = PIANO_XML_FIXTURE.read_text(encoding="utf-8")

    # Simulamos la inferencia OMR devolviendo el MusicXML del fixture de piano
    with patch.object(HOMREngine, "transcribe_musicxml", return_value=piano_xml_content):
        doc = engine.transcribe(fake_image)

    # 2. Verificación del ScoreDocument de piano
    assert doc.id == "piano-session-001"
    assert len(doc.score.parts) == 1
    part = doc.score.parts[0]
    assert len(part.staves) == 2
    assert part.staves[0].id == "part-0-staff-0"
    assert part.staves[1].id == "part-0-staff-1"

    # 3. Validación: la partitura de piano está perfectamente balanceada
    validator = ValidationEngine([MeasureBalanceRule()])
    findings = validator.validate(doc)
    assert findings == []

    # 4. Edición: corregir la nota del acorde en mano derecha (staff 0, m 1, voice 0, ev 3)
    query_anchor = Anchor(
        part=0, staff=0, measure=1, voice=0, event_index=3, staff_id="part-0-staff-0"
    )
    target_anchor = doc.anchors.find_anchor(query_anchor)
    assert target_anchor is not None

    edit = EditEvent(
        id="edit-hitl-001",
        document_id="piano-session-001",
        seq=1,
        op=EditOp.SET_PITCH,
        author="human",
        created_at=datetime.now(UTC),
        anchor=target_anchor,
        after={"pitch": "G#4"},
    )
    edited_score = apply_edit(doc.score, edit)

    # Verificamos que la nota se alteró en el ScoreIR
    edited_chord_event = edited_score.parts[0].staves[0].measures[0].events[3]
    assert edited_chord_event.pitch == "G#4"
    assert edited_chord_event.is_chord is True

    # 5. Exportación a MusicXML
    xml_exported = score_ir_to_musicxml(edited_score)
    assert "<staves>2</staves>" in xml_exported
    assert "<step>G</step>" in xml_exported
    assert (
        "<alter>1</alter>" in xml_exported
        or "<accidental>sharp</accidental>" in xml_exported
        or "G#4" in xml_exported
    )
