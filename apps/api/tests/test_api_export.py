"""Pruebas de integración de la API para exportación MusicXML y MIDI (Issue #12, ADR-0010)."""

from __future__ import annotations

from pathlib import Path

from cadenza.api import Settings, create_app
from cadenza.application import Role, User
from cadenza.interchange import read_score
from cadenza.omr import FakeOMREngine
from cadenza.persistence import (
    SqlAlchemyUserRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from fastapi.testclient import TestClient
from music21 import midi

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
)


def _setup_api(tmp_path: Path) -> tuple[TestClient, dict[str, str]]:
    engine = create_memory_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as db:
        user_repo = SqlAlchemyUserRepository(db)
        user_repo.add(
            User(
                id="user-t1",
                username="transcriptor1",
                password_hash="hash1",
                role=Role.TRANSCRIPTOR,
                active=True,
            )
        )
        user_repo.add(
            User(
                id="user-t2",
                username="transcriptor2",
                password_hash="hash2",
                role=Role.TRANSCRIPTOR,
                active=True,
            )
        )
        user_repo.add(
            User(
                id="user-inv",
                username="investigador1",
                password_hash="hash3",
                role=Role.INVESTIGADOR,
                active=True,
            )
        )
        db.commit()

    settings = Settings(
        auth_secret_key="secret-key-at-least-32-bytes-long-for-testing",
        artifacts_dir=tmp_path / "artifacts",
    )
    app = create_app(
        session_factory,
        omr_engine=FakeOMREngine(),
        settings=settings,
    )

    tokens = {
        "t1": app.state.token_service.create_access_token(
            user_id="user-t1", role=Role.TRANSCRIPTOR
        ),
        "t2": app.state.token_service.create_access_token(
            user_id="user-t2", role=Role.TRANSCRIPTOR
        ),
        "inv": app.state.token_service.create_access_token(
            user_id="user-inv", role=Role.INVESTIGADOR
        ),
    }

    return TestClient(app), tokens


def test_export_unauthenticated_returns_401(tmp_path: Path) -> None:
    client, _ = _setup_api(tmp_path)
    res = client.get("/sessions/any-id/export?format=musicxml")
    assert res.status_code == 401


def test_export_non_existent_session_returns_404(tmp_path: Path) -> None:
    client, tokens = _setup_api(tmp_path)
    res = client.get(
        "/sessions/non-existent/export?format=musicxml",
        headers={"Authorization": f"Bearer {tokens['t1']}"},
    )
    assert res.status_code == 404


def test_export_other_user_session_returns_404_for_transcriptor(tmp_path: Path) -> None:
    client, tokens = _setup_api(tmp_path)
    h_t1 = {"Authorization": f"Bearer {tokens['t1']}"}
    h_t2 = {"Authorization": f"Bearer {tokens['t2']}"}

    # Transcriptor 1 crea una sesión
    files = {"file": ("score.png", PNG_BYTES, "image/png")}
    sid = client.post("/transcribe", files=files, headers=h_t1).json()["session_id"]

    # Transcriptor 2 intenta exportarla -> 404
    res = client.get(f"/sessions/{sid}/export?format=musicxml", headers=h_t2)
    assert res.status_code == 404


def test_export_investigator_can_export_any_session(tmp_path: Path) -> None:
    client, tokens = _setup_api(tmp_path)
    h_t1 = {"Authorization": f"Bearer {tokens['t1']}"}
    h_inv = {"Authorization": f"Bearer {tokens['inv']}"}

    files = {"file": ("score.png", PNG_BYTES, "image/png")}
    sid = client.post("/transcribe", files=files, headers=h_t1).json()["session_id"]

    res = client.get(f"/sessions/{sid}/export?format=musicxml", headers=h_inv)
    assert res.status_code == 200
    assert "score-partwise" in res.text


def test_export_unsupported_format_returns_422(tmp_path: Path) -> None:
    client, tokens = _setup_api(tmp_path)
    h_t1 = {"Authorization": f"Bearer {tokens['t1']}"}

    files = {"file": ("score.png", PNG_BYTES, "image/png")}
    sid = client.post("/transcribe", files=files, headers=h_t1).json()["session_id"]

    res = client.get(f"/sessions/{sid}/export?format=wav", headers=h_t1)
    assert res.status_code == 422
    assert "wav" in res.json()["detail"]


def test_export_musicxml_headers_and_content(tmp_path: Path) -> None:
    client, tokens = _setup_api(tmp_path)
    h_t1 = {"Authorization": f"Bearer {tokens['t1']}"}

    files = {"file": ("score.png", PNG_BYTES, "image/png")}
    sid = client.post("/transcribe", files=files, headers=h_t1).json()["session_id"]

    res = client.get(f"/sessions/{sid}/export?format=musicxml", headers=h_t1)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/vnd.recordare.musicxml+xml")
    assert f'filename="session-{sid}.musicxml"' in res.headers["content-disposition"]
    assert "<?xml" in res.text
    assert "<score-partwise" in res.text

    # Re-leer MusicXML y verificar compatibilidad
    xml_file = tmp_path / "test.musicxml"
    xml_file.write_text(res.text, encoding="utf-8")
    reloaded_score = read_score(xml_file)
    assert len(reloaded_score.parts) > 0


def test_export_midi_headers_and_content(tmp_path: Path) -> None:
    client, tokens = _setup_api(tmp_path)
    h_t1 = {"Authorization": f"Bearer {tokens['t1']}"}

    files = {"file": ("score.png", PNG_BYTES, "image/png")}
    sid = client.post("/transcribe", files=files, headers=h_t1).json()["session_id"]

    res = client.get(f"/sessions/{sid}/export?format=midi", headers=h_t1)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("audio/midi")
    assert f'filename="session-{sid}.mid"' in res.headers["content-disposition"]

    # Verificar que los bytes son un MIDI válido
    content = res.content
    assert content.startswith(b"MThd")

    mf = midi.MidiFile()
    mf.readstr(content)
    stream_m21 = midi.translate.midiFileToStream(mf)
    assert len(list(stream_m21.recurse().notes)) > 0


def test_export_reflects_edits_on_materialized_score(tmp_path: Path) -> None:
    client, tokens = _setup_api(tmp_path)
    h_t1 = {"Authorization": f"Bearer {tokens['t1']}"}

    files = {"file": ("score.png", PNG_BYTES, "image/png")}
    sid = client.post("/transcribe", files=files, headers=h_t1).json()["session_id"]

    # Primera nota del FakeOMREngine es C4. Aplicamos una edición para cambiarla a D4
    edit_payload = {
        "base_seq": 0,
        "anchor": {
            "part": 0,
            "staff": 0,
            "measure": 1,
            "voice": 0,
            "event_index": 0,
            "staff_id": "part-0-staff-0",
        },
        "op": "SetPitch",
        "before": {"pitch": "C4"},
        "after": {"pitch": "D4"},
    }
    res_edit = client.post(f"/sessions/{sid}/edits", json=edit_payload, headers=h_t1)
    assert res_edit.status_code == 201

    # Exportar MusicXML
    res_xml = client.get(f"/sessions/{sid}/export?format=musicxml", headers=h_t1)
    assert res_xml.status_code == 200
    xml_path = tmp_path / "edited.musicxml"
    xml_path.write_text(res_xml.text, encoding="utf-8")
    reloaded = read_score(xml_path)
    first_note = reloaded.parts[0].staves[0].measures[0].events[0]
    assert first_note.pitch == "D4"

    # Exportar MIDI
    res_midi = client.get(f"/sessions/{sid}/export?format=midi", headers=h_t1)
    assert res_midi.status_code == 200
    mf = midi.MidiFile()
    mf.readstr(res_midi.content)
    stream_m21 = midi.translate.midiFileToStream(mf)
    notes = list(stream_m21.recurse().notes)
    # Primera nota debe ser D4
    assert notes[0].nameWithOctave == "D4"
