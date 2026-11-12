"""`ml export-tables --recortes` (#414): las tablas y los recortes de las fotos, en una sola salida.

Una base SQLite temporal con una foto de dos sistemas de un pentagrama (dibujada aquí, como en
`test_export_staves`) y sesiones que entran con su foto, sin captura (entra en las tablas, sin
recorte) y de cuentas del registro con y sin el permiso de uso de los datos vigente. Un corpus de
PrIMuS de dos incipits, con la imagen de uno solo.
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

from .suggestions_support import SPLIT_SEED, incipit_id, write_corpus

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


def _session(session_id: str, owner: str, image: str, *, captured: bool = True) -> SessionData:
    score = _score()
    document = ScoreDocument(
        id=f"doc-{session_id}",
        score=score,
        anchors=build_anchor_index(score),
        provenance=Provenance(omr_engine="homr", source_image_hash=image),
        omr_capture=_capture() if captured else None,
    )
    return SessionData(
        id=session_id,
        document_id=document.id,
        omr_engine="homr",
        document=document.to_primitive(),
        image_artifact=image,
        status="finalized",
        owner_id=owner,
    )


def _user(user_id: str, *, self_registered: bool = False, consent: str | None = None) -> User:
    user = User(
        id=user_id,
        username=user_id,
        password_hash=secrets.token_hex(8),
        role=Role.TRANSCRIPTOR,
        self_registered=self_registered,
    )
    if consent is not None:
        user = replace(
            user,
            data_consent_at=datetime(2026, 11, 10, tzinfo=UTC),
            data_consent_version=consent,
        )
    return user


@pytest.fixture
def base(tmp_path: Path) -> tuple[str, Path]:
    db_url = f"sqlite:///{(tmp_path / 'copia.db').as_posix()}"
    artifacts = tmp_path / "artefactos"
    engine = create_engine_for_url(db_url)
    create_schema(engine)
    with session_scope(create_session_factory(engine)) as db:
        users = SqlAlchemyUserRepository(db)
        users.add(_user("ana"))
        users.add(_user("visita", self_registered=True, consent=DATA_CONSENT_VERSION))
        users.add(_user("anonima", self_registered=True))
        image = FilesystemArtifactStore(artifacts, db).put(
            _photo(), kind="image", media_type="image/png"
        )
        sessions = SqlAlchemySessionRepository(db)
        for session in (
            _session("s-foto", "ana", image),
            _session("s-sin-captura", "ana", image, captured=False),
            _session("s-visita", "visita", image),
            _session("s-anonima", "anonima", image),
        ):
            sessions.add(session, [])
        # En s-foto se corrigió la altura del compás 2 (sistema 1).
        SqlAlchemyEditEventRepository(db).append(
            "s-foto",
            EditEvent(
                id="e1",
                document_id="doc-s-foto",
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


def _export(output: Path, *args: str) -> int:
    return main(["export-tables", "--output-dir", str(output), *args])


def _db_args(base: tuple[str, Path]) -> list[str]:
    db_url, artifacts = base
    return ["--db-url", db_url, "--split-seed", str(SPLIT_SEED), "--artifacts-dir", str(artifacts)]


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_each_measure_of_the_tables_points_to_the_strip_of_its_photo(
    base: tuple[str, Path], tmp_path: Path
) -> None:
    output = tmp_path / "salida"
    assert _export(output, *_db_args(base), "--recortes") == 0

    strips = [r for r in _rows(output / "pentagramas.csv") if r["session_id"] == "s-foto"]
    assert [(r["sistema"], r["recorte"], r["corregido"]) for r in strips] == [
        ("1", "recortes/s-foto/s1_0-0.png", "true"),
        ("2", "recortes/s-foto/s2_0-0.png", "false"),
    ]
    for row in strips:
        assert (output / row["recorte"]).is_file()
    assert (output / "musicxml" / "s-foto-final.musicxml").is_file()

    compases = {
        int(r["measure"]): (r["sistema"], r["recorte"])
        for r in _rows(output / "compases.csv")
        if r["session_id"] == "s-foto"
    }
    assert compases == {
        1: ("1", "recortes/s-foto/s1_0-0.png"),
        2: ("1", "recortes/s-foto/s1_0-0.png"),
        3: ("2", "recortes/s-foto/s2_0-0.png"),
        4: ("2", "recortes/s-foto/s2_0-0.png"),
    }
    notas = [r for r in _rows(output / "notas.csv") if r["session_id"] == "s-foto"]
    corrected = next(r for r in notas if r["resultado"] == "corregida")
    assert (corrected["measure"], corrected["recorte"]) == ("2", "recortes/s-foto/s1_0-0.png")
    assert all(r["recorte"] for r in notas)

    # Sin captura, la sesión sigue en las tablas, sin recorte, y el motivo queda escrito.
    sin = [r for r in _rows(output / "compases.csv") if r["session_id"] == "s-sin-captura"]
    assert sin and all(r["recorte"] == "" and r["sistema"] == "" for r in sin)
    info = json.loads((output / "run_info.json").read_text(encoding="utf-8"))
    recortes = info["recortes"]
    assert recortes["sessions"] == ["s-foto"]
    assert recortes["left_out"]["s-sin-captura"].startswith("sin la captura de HOMR")
    assert (recortes["strips"], recortes["strips_corrected"]) == (2, 1)
    assert len(recortes["pentagramas_sha256"]) == 64
    assert info["format_version"] == 2


def test_without_recortes_the_columns_are_there_but_empty(
    base: tuple[str, Path], tmp_path: Path
) -> None:
    db_url, _ = base
    output = tmp_path / "solo-tablas"
    assert _export(output, "--db-url", db_url, "--split-seed", str(SPLIT_SEED)) == 0
    for name in ("notas", "faltantes", "compases"):
        with (output / f"{name}.csv").open(encoding="utf-8") as handle:
            header = next(csv.reader(handle))
        assert header[-2:] == ["sistema", "recorte"], name
    assert all(r["recorte"] == "" for r in _rows(output / "compases.csv"))
    assert not (output / "recortes").exists()
    assert not (output / "pentagramas.csv").exists()
    assert "recortes" not in json.loads((output / "run_info.json").read_text(encoding="utf-8"))


def test_the_photos_follow_the_same_filter_as_the_tables(
    base: tuple[str, Path], tmp_path: Path
) -> None:
    output = tmp_path / "con-registro"
    assert _export(output, *_db_args(base), "--recortes", "--include-self-registered") == 0
    assert (output / "recortes" / "s-visita").is_dir()
    # Sin el permiso vigente: ni tablas ni fotos.
    assert not (output / "recortes" / "s-anonima").exists()
    for written in output.rglob("*.csv"):
        assert "s-anonima" not in written.read_text(encoding="utf-8"), written.name
    info = json.loads((output / "run_info.json").read_text(encoding="utf-8"))
    assert "s-anonima" in info["left_out"]
    assert "s-anonima" not in info["recortes"]["left_out"]
    assert info["recortes"]["sessions"] == ["s-foto", "s-visita"]


def test_primus_rows_point_to_the_image_of_their_incipit(tmp_path: Path) -> None:
    corpus = write_corpus(tmp_path / "corpus.jsonl", works=1)
    found, missing = incipit_id(0, 0), incipit_id(0, 1)
    primus = tmp_path / "primus"
    folder = primus / "package_aa" / found
    folder.mkdir(parents=True)
    (folder / f"{found}.png").write_bytes(_photo())
    output = tmp_path / "primus-salida"
    assert _export(output, "--corpus", str(corpus), "--recortes", "--primus-dir", str(primus)) == 0

    copied = output / "recortes" / "primus" / f"{found}.png"
    assert copied.read_bytes() == _photo()
    notas = _rows(output / "notas.csv")
    assert {r["recorte"] for r in notas if r["incipit_id"] == found} == {
        f"recortes/primus/{found}.png"
    }
    assert {r["sistema"] for r in notas if r["incipit_id"] == found} == {"1"}
    assert {r["recorte"] for r in notas if r["incipit_id"] == missing} == {""}
    info = json.loads((output / "run_info.json").read_text(encoding="utf-8"))
    assert info["recortes"]["primus_images"] == 1
    assert info["recortes"]["primus_missing"] == [missing]


def test_the_export_refuses_unsafe_outputs_and_missing_photos(
    base: tuple[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CADENZA_ARTIFACTS_DIR", raising=False)
    db_url, _ = base
    plain = ["--db-url", db_url, "--split-seed", str(SPLIT_SEED)]
    # Con la base, los recortes necesitan las fotos.
    assert _export(tmp_path / "sin-fotos", *plain, "--recortes") == 1
    assert not (tmp_path / "sin-fotos").exists()
    # La salida ha de estar vacía: lo de una exportación anterior (quizá de alguien que ya
    # retiró su permiso) se quedaría.
    used = tmp_path / "usada"
    used.mkdir()
    (used / "viejo.png").write_bytes(b"x")
    assert _export(used, *plain) == 1
    # Ni en results/ ni en data/ del repositorio.
    repo = Path(__file__).resolve().parents[3]
    for folder in ("results", "data"):
        target = repo / folder / f"export-{secrets.token_hex(4)}"
        assert _export(target, *plain) == 1
        assert not target.exists()
