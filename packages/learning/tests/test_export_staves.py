"""`ml export-staves` (#403, ADR-0067): cada pentagrama de la foto con lo que leyó HOMR y lo que
quedó corregido.

Una base SQLite temporal con una foto de dos sistemas de un pentagrama (dibujada aquí) y sesiones
que entran y que quedan fuera: sin captura, de una cuenta del registro con y sin permiso de uso
de los datos, y sin finalizar.
"""

from __future__ import annotations

import csv
import io
import json
import secrets
from dataclasses import replace
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path

import pytest
from cadenza.application import DATA_CONSENT_VERSION, Role, SessionData, User
from cadenza.domain import (
    Anchor,
    EditEvent,
    EditOp,
    Event,
    EventKind,
    Measure,
    Part,
    Provenance,
    ScoreDocument,
    ScoreIR,
    Staff,
    TimeSignature,
    build_anchor_index,
)
from cadenza.omr.adapters import homr_capture
from cadenza.persistence import (
    FilesystemArtifactStore,
    SqlAlchemyEditEventRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
    create_engine_for_url,
    create_schema,
    create_session_factory,
    session_scope,
)
from PIL import Image, ImageDraw

from ml.cli import main

PHOTO = (1000, 400)
STAFF_ID = "P1-S1"


def _photo() -> bytes:
    image = Image.new("RGB", PHOTO, "white")
    draw = ImageDraw.Draw(image)
    for center in (100, 300):  # dos pentagramas, uno por sistema
        for line in range(5):
            y = center - 20 + line * 10
            draw.line((100, y, 900, y), fill="black", width=2)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _rotated_photo() -> bytes:
    """La misma foto, guardada girada con la orientación EXIF 6, como la de un móvil: OpenCV (y
    HOMR) la ven derecha; PIL, sin `exif_transpose`, tumbada."""
    image = Image.open(io.BytesIO(_photo())).rotate(90, expand=True)
    exif = Image.Exif()
    exif[0x0112] = 6
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def _score() -> ScoreIR:
    measures = tuple(
        Measure(
            number=n,
            events=(Event(kind=EventKind.NOTE, pitch="C4", duration_beats=Fraction(4)),),
            time_signature=TimeSignature(4, 4) if n == 1 else None,
        )
        for n in range(1, 5)
    )
    return ScoreIR(parts=(Part(id="P1", staves=(Staff(id=STAFF_ID, measures=measures),)),))


def _capture() -> dict[str, object]:
    capture = homr_capture.Capture(systems=["1", "3"])
    capture.readings.append(
        homr_capture.ReadingCapture(
            mode="paired",
            image_shape=(400, 1000),
            source_shape=(400, 1000),
            autocrop=None,
            staves=[
                {"grand": False, "cx": 0.5, "cy": 0.25, "w": 0.8, "h": 0.1},
                {"grand": False, "cx": 0.5, "cy": 0.75, "w": 0.8, "h": 0.1},
            ],
        )
    )
    return homr_capture.capture_primitive(
        capture, "<score-partwise/>", homr_version="0.7.0", preprocessed=False
    )


def _broken(session: SessionData) -> SessionData:
    """Una sesión con una caja a medias en su captura."""
    document = dict(session.document)
    capture = dict(document["omr_capture"])
    capture["readings"] = [{**capture["readings"][0], "staves": [{"grand": False}]}]
    document["omr_capture"] = capture
    return replace(session, document=document)


def _session(
    session_id: str, owner: str, image: str, *, captured: bool = True, status: str = "finalized"
) -> SessionData:
    score = _score()
    document = ScoreDocument(
        id=f"doc-{session_id}",
        score=score,
        anchors=build_anchor_index(score),
        provenance=Provenance(omr_engine="homr"),
        omr_capture=_capture() if captured else None,
    )
    return SessionData(
        id=session_id,
        document_id=document.id,
        omr_engine="homr",
        document=document.to_primitive(),
        image_artifact=image,
        status=status,
        owner_id=owner,
        test_score_id="TS-04" if session_id == "s-estudio" else None,
    )


@pytest.fixture
def base(tmp_path: Path) -> tuple[str, Path]:
    db_url = f"sqlite:///{(tmp_path / 'copia.db').as_posix()}"
    artifacts = tmp_path / "artefactos"
    engine = create_engine_for_url(db_url)
    create_schema(engine)
    consent = datetime(2026, 11, 10, tzinfo=UTC)
    with session_scope(create_session_factory(engine)) as db:
        users = SqlAlchemyUserRepository(db)
        for user_id, self_registered, consented in (
            ("ana", False, False),
            ("visita", True, True),
            ("anonima", True, False),
            ("version-antigua", True, True),
        ):
            user = User(
                id=user_id,
                username=user_id,
                password_hash=secrets.token_hex(8),
                role=Role.TRANSCRIPTOR,
                self_registered=self_registered,
            )
            if consented:
                version = "0" if user_id == "version-antigua" else DATA_CONSENT_VERSION
                user = replace(user, data_consent_at=consent, data_consent_version=version)
            users.add(user)
        store = FilesystemArtifactStore(artifacts, db)
        image = store.put(_photo(), kind="image", media_type="image/png")
        rotated = store.put(_rotated_photo(), kind="image", media_type="image/jpeg")
        sessions = SqlAlchemySessionRepository(db)
        for session in (
            _session("s-estudio", "ana", image),
            _session("s-antigua", "ana", image, captured=False),
            _session("s-sin-foto", "ana", "f" * 64),
            _session("s-visita", "visita", image),
            _session("s-anonima", "anonima", image),
            _session("s-a-medias", "ana", image, status="correcting"),
            _session("s-version-antigua", "version-antigua", image),
            _session("s-girada", "ana", rotated),
            _broken(_session("s-rota", "ana", image)),
        ):
            sessions.add(session, [])
        # En el estudio se corrigió la altura del compás 2 (sistema 1).
        SqlAlchemyEditEventRepository(db).append(
            "s-estudio",
            EditEvent(
                id="e1",
                document_id="doc-s-estudio",
                seq=1,
                anchor=Anchor(
                    part=0, staff=0, measure=2, voice=0, event_index=0, staff_id=STAFF_ID
                ),
                op=EditOp.SET_PITCH,
                author="ana",
                created_at=datetime(2026, 11, 11, tzinfo=UTC),
                before={"pitch": "C4"},
                after={"pitch": "D4"},
            ),
        )
    return db_url, artifacts


def _export(output: Path, db_url: str, artifacts: Path, *extra: str) -> int:
    return main(
        [
            "export-staves",
            "--output-dir",
            str(output),
            "--db-url",
            db_url,
            "--artifacts-dir",
            str(artifacts),
            *extra,
        ]
    )


def _rows(output: Path) -> list[dict[str, str]]:
    with (output / "pentagramas.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_each_staff_of_the_photo_is_cut_and_paired_with_its_measures(
    base: tuple[str, Path], tmp_path: Path
) -> None:
    db_url, artifacts = base
    output = tmp_path / "salida"
    assert _export(output, db_url, artifacts, "--laminas") == 0

    rows = [r for r in _rows(output) if r["session_id"] == "s-estudio"]
    assert [
        (r["session_id"], r["sistema"], r["primer_compas"], r["ultimo_compas"]) for r in rows
    ] == [
        ("s-estudio", "1", "1", "2"),
        ("s-estudio", "2", "3", "4"),
    ]
    first, second = rows
    assert first["lectura"] == "c1: C4:4 | c2: C4:4"
    assert first["corregida"] == "c1: C4:4 | c2: D4:4"
    assert (first["corregido"], second["corregido"]) == ("true", "false")
    assert first["test_score_id"] == "TS-04" and first["pentagramas"] == "0-0"
    # La tira del primer sistema: el pentagrama dibujado en y 80 a 120, con su margen.
    assert int(first["y0"]) < 80 and int(first["y1"]) > 120 and int(first["y1"]) <= 200
    crop = Image.open(output / first["recorte"])
    assert crop.size == (int(first["x1"]) - int(first["x0"]), int(first["y1"]) - int(first["y0"]))
    assert (output / "musicxml" / "s-estudio-homr.musicxml").read_text() == "<score-partwise/>"
    assert "<score-partwise" in (output / "musicxml" / "s-estudio-final.musicxml").read_text()
    assert Image.open(output / "laminas" / "s-estudio.png").width == PHOTO[0]

    info = json.loads((output / "run_info.json").read_text(encoding="utf-8"))
    assert info["simulated"] is False
    # La foto girada con EXIF se endereza como la vio HOMR, y sus tiras salen igual.
    assert info["sessions"] == ["s-estudio", "s-girada"]
    turned = [r for r in _rows(output) if r["session_id"] == "s-girada"]
    assert [(r["y0"], r["y1"]) for r in turned] == [(r["y0"], r["y1"]) for r in rows]
    assert info["strips"] == 4 and info["strips_corrected"] == 1
    # Una sesión con la captura a medias queda fuera con su motivo, sin parar la exportación.
    assert info["left_out"].pop("s-rota").startswith("no se pudo exportar (KeyError")
    assert info["left_out"] == {
        "s-anonima": "cuenta del registro público",
        "s-antigua": "sin la captura de HOMR (transcrita antes de #403)",
        "s-sin-foto": "sin la imagen (ArtifactNotFound)",
        "s-version-antigua": "cuenta del registro público",
        "s-visita": "cuenta del registro público",
    }
    assert not (output / "recortes" / "s-rota").exists()
    assert len(info["csv_sha256"]) == 64
    assert info["origin"] == {"database": "sqlite:copia.db", "artifacts_dir": "artefactos"}


def test_registered_accounts_enter_only_with_their_data_consent(
    base: tuple[str, Path], tmp_path: Path
) -> None:
    db_url, artifacts = base
    output = tmp_path / "salida"
    assert (
        _export(output, db_url, artifacts, "--include-self-registered", "--include-unfinished") == 0
    )
    info = json.loads((output / "run_info.json").read_text(encoding="utf-8"))
    assert info["sessions"] == ["s-a-medias", "s-estudio", "s-girada", "s-visita"]
    assert (
        info["left_out"]["s-anonima"]
        == "cuenta del registro sin el permiso de uso de los datos vigente"
    )
    # Un permiso dado a un texto anterior no vale: no es el vigente (ADR-0065).
    assert (
        info["left_out"]["s-version-antigua"]
        == "cuenta del registro sin el permiso de uso de los datos vigente"
    )


def test_the_export_needs_its_sources_and_writes_only_in_the_output_dir(
    base: tuple[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_url, artifacts = base
    monkeypatch.delenv("CADENZA_DATABASE_URL", raising=False)
    monkeypatch.delenv("CADENZA_ARTIFACTS_DIR", raising=False)
    assert main(["export-staves", "--output-dir", str(tmp_path / "x")]) == 1
    assert main(["export-staves", "--output-dir", str(tmp_path / "x"), "--db-url", db_url]) == 1

    # Una carpeta con algo dentro se rechaza: lo de una exportación anterior se quedaría.
    used = tmp_path / "usada"
    used.mkdir()
    (used / "viejo.csv").write_text("x", encoding="utf-8")
    assert _export(used, db_url, artifacts) == 1
    # Ni results/ ni data/ del repositorio.
    repository = Path(__file__).resolve().parents[3]
    for forbidden in ("results", "data"):
        assert _export(repository / forbidden / "recortes", db_url, artifacts) == 1
        assert not (repository / forbidden / "recortes").exists()
    # Ni un archivo.
    assert _export(used / "viejo.csv", db_url, artifacts) == 1

    monkeypatch.chdir(tmp_path)
    before = set(tmp_path.rglob("*"))
    output = tmp_path / "salida"
    assert _export(output, db_url, artifacts) == 0
    created = set(tmp_path.rglob("*")) - before
    assert created and all(output in p.parents or p == output for p in created)


def test_a_session_that_fails_after_its_crops_leaves_nothing_behind(
    base: tuple[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cadenza.interchange

    def broken(score: object) -> str:
        raise RuntimeError("el exportador no sabe escribir esto")

    monkeypatch.setattr(cadenza.interchange, "score_ir_to_musicxml", broken)
    db_url, artifacts = base
    output = tmp_path / "salida"
    assert _export(output, db_url, artifacts, "--laminas") == 0
    info = json.loads((output / "run_info.json").read_text(encoding="utf-8"))
    assert info["sessions"] == [] and info["strips"] == 0
    assert info["left_out"]["s-estudio"].startswith("no se pudo exportar (RuntimeError")
    assert sorted(p.name for p in output.iterdir()) == ["pentagramas.csv", "run_info.json"]
