"""`ml export-pairs` (#420, ADR-0071): los pares imagen-partitura para entrenar un lector.

Una base SQLite temporal con una foto de dos sistemas de un pentagrama (como en
`test_export_tables_recortes`): sesiones que entran, sin captura, sin finalizar, sin verificar,
de tres páginas (una del banco subida también sin su partitura de prueba), con un cambio de
clave, de dos cuentas anteriores al registro (la del equipo y la semilla) y de cuentas del registro
con el permiso vigente, con el de un texto anterior y sin él (nunca dado o retirado: retirarlo
borra las dos columnas, ADR-0065 §1). Aparte, una página de voz y piano con el gran pentagrama.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import secrets
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from cadenza.application import DATA_CONSENT_VERSION, SessionData, User
from cadenza.domain import (
    Anchor,
    Clef,
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
from cadenza.interchange import musicxml_to_score_ir
from cadenza.learning import assign_split, derive_edit_events
from cadenza.learning.suggestions import correction_verified, shared_works
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

from .suggestions_support import SPLIT_SEED

PHOTO = (1000, 400)
STAFF_ID = "P1-S1"
TEST_FRACTION = 0.5


def _photo(page: int = 0) -> bytes:
    image = Image.new("RGB", PHOTO, "white")
    draw = ImageDraw.Draw(image)
    for center in (100, 300):  # dos pentagramas, uno por sistema
        for line in range(5):
            y = center - 20 + line * 10
            draw.line((100, y, 900, y), fill="black", width=2)
        if page:  # otra página: un punto en cada pentagrama
            draw.ellipse((200 + 40 * page, center - 4, 208 + 40 * page, center + 4), fill="black")
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


def _session(
    session_id: str,
    owner: str,
    image: str,
    *,
    captured: bool = True,
    status: str = "finalized",
    test_score_id: str | None = None,
) -> SessionData:
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
        status=status,
        owner_id=owner,
        test_score_id=test_score_id,
    )


def _user(user_id: str, *, self_registered: bool = False, consent: str | None = None) -> User:
    user = User(
        id=user_id,
        username=user_id,
        password_hash=secrets.token_hex(8),
        self_registered=self_registered,
    )
    if consent is not None:
        user = replace(
            user,
            data_consent_at=datetime(2026, 11, 10, tzinfo=UTC),
            data_consent_version=consent,
        )
    return user


def _pages_on_both_sides() -> tuple[str, str]:
    """Dos partituras de prueba que la partición pone una en `train` y otra en `test`."""
    found: dict[str, str] = {}
    for number in range(100):
        name = f"TS-{number:02d}"
        side = assign_split(f"test_score:{name}", seed=SPLIT_SEED, test_fraction=TEST_FRACTION)
        found.setdefault(side, name)
        if len(found) == 2:
            return found["train"], found["test"]
    raise AssertionError("ninguna partitura de prueba cae en las dos particiones")


TRAIN_PAGE, TEST_PAGE = _pages_on_both_sides()


@pytest.fixture
def base(tmp_path: Path) -> tuple[str, Path]:
    db_url = f"sqlite:///{(tmp_path / 'copia.db').as_posix()}"
    artifacts = tmp_path / "artefactos"
    engine = create_engine_for_url(db_url)
    create_schema(engine)
    with session_scope(create_session_factory(engine)) as db:
        users = SqlAlchemyUserRepository(db)
        users.add(_user("ana"))  # una cuenta del equipo
        users.add(_user("semilla"))  # otra anterior al registro, sin este permiso (ADR-0070)
        users.add(_user("visita", self_registered=True, consent=DATA_CONSENT_VERSION))
        # El permiso del texto anterior (#427 subió la versión): ya no está vigente.
        users.add(_user("antigua", self_registered=True, consent="2026-11-09"))
        users.add(_user("anonima", self_registered=True))
        store = FilesystemArtifactStore(artifacts, db)
        image, train_image, test_image = (
            store.put(_photo(page), kind="image", media_type="image/png") for page in range(3)
        )
        sessions = SqlAlchemySessionRepository(db)
        for session in (
            # s-foto, s-otra-foto y s-visita son de la misma foto: la misma obra.
            _session("s-foto", "ana", image),
            _session("s-otra-foto", "ana", image),
            _session("s-train", "semilla", train_image, test_score_id=TRAIN_PAGE),
            _session("s-test", "ana", test_image, test_score_id=TEST_PAGE),
            # La misma página del banco, subida sin su partitura de prueba: es la misma foto.
            _session("s-banco", "ana", test_image),
            _session("s-sin-captura", "ana", image, captured=False),
            _session("s-abierta", "ana", image, status="transcribed"),
            _session("s-visita", "visita", image),
            _session("s-antigua", "antigua", image),
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
        # En s-test se puso la clave de fa del compás 1: rige también en el sistema 2.
        clef = ScoreIR(
            parts=(
                Part(
                    id="P1",
                    staves=(
                        Staff(
                            id=STAFF_ID,
                            measures=(
                                replace(_score().parts[0].staves[0].measures[0], clef=Clef("F", 4)),
                                *_score().parts[0].staves[0].measures[1:],
                            ),
                        ),
                    ),
                ),
            )
        )
        edits = SqlAlchemyEditEventRepository(db)
        for edit in derive_edit_events(_score(), clef, document_id="doc-s-test", author="ana"):
            edits.append(
                "s-test",
                replace(edit, before=_as_stored(edit.before), after=_as_stored(edit.after)),
            )
    return db_url, artifacts


def _export(output: Path, *args: str) -> int:
    return main(["export-pairs", "--output-dir", str(output), *args])


def _db_args(base: tuple[str, Path]) -> list[str]:
    db_url, artifacts = base
    return [
        "--db-url",
        db_url,
        "--artifacts-dir",
        str(artifacts),
        "--split-seed",
        str(SPLIT_SEED),
        "--test-fraction",
        str(TEST_FRACTION),
    ]


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _info(output: Path) -> dict[str, Any]:
    info: dict[str, Any] = json.loads((output / "run_info.json").read_text(encoding="utf-8"))
    return info


def _pitches(score: ScoreIR) -> list[tuple[int, list[str | None]]]:
    return [
        (m.number, [e.pitch for e in m.events])
        for part in score.parts
        for staff in part.staves
        for m in staff.measures
    ]


def test_each_strip_is_a_pair_of_its_photo_and_its_two_scores(
    base: tuple[str, Path], tmp_path: Path
) -> None:
    output = tmp_path / "pares"
    assert _export(output, *_db_args(base)) == 0

    rows = [r for r in _rows(output / "pares.csv") if r["session_id"] == "s-foto"]
    split = rows[0]["split"]
    assert [
        (r["par"], r["sistema"], r["primer_compas"], r["ultimo_compas"], r["corregido"])
        for r in rows
    ] == [
        ("s-foto/s1_0-0", "1", "1", "2", "true"),
        ("s-foto/s2_0-0", "2", "3", "4", "false"),
    ]
    first = rows[0]
    assert first["imagen"] == f"{split}/s-foto/s1_0-0.png"
    assert first["homr"] == f"{split}/s-foto/s1_0-0.homr.musicxml"
    assert first["corregida"] == f"{split}/s-foto/s1_0-0.musicxml"
    assert first["work_id"].startswith("image:")
    assert first["homr_version"] == "0.7.0"
    for row in rows:
        for column in ("imagen", "homr", "corregida"):
            content = (output / row[column]).read_bytes()
            assert hashlib.sha256(content).hexdigest() == row[f"{column}_sha256"]

    # La imagen es la tira de la foto: el pentagrama de arriba, a todo lo ancho de la caja.
    with Image.open(output / first["imagen"]) as strip:
        assert strip.size == (int(first["ancho"]), int(first["alto"]))
        assert strip.size[0] > 800 and strip.size[1] <= PHOTO[1] / 2

    # Lo que leyó HOMR y lo corregido, en MusicXML: solo los compases de la tira.
    read = musicxml_to_score_ir((output / first["homr"]).read_text(encoding="utf-8"))
    fixed = musicxml_to_score_ir((output / first["corregida"]).read_text(encoding="utf-8"))
    assert _pitches(read) == [(1, ["C4"]), (2, ["C4"])]
    assert _pitches(fixed) == [(1, ["C4"]), (2, ["D4"])]
    # La segunda tira empieza en el compás 3, con el compás de la obra aunque no se repita.
    second = musicxml_to_score_ir((output / rows[1]["corregida"]).read_text(encoding="utf-8"))
    opening = second.parts[0].staves[0].measures[0]
    assert (opening.number, opening.time_signature) == (3, TimeSignature(4, 4))
    # Sin corrección, los dos MusicXML son el mismo; con ella, difieren.
    for row in rows:
        same = (output / row["homr"]).read_bytes() == (output / row["corregida"]).read_bytes()
        assert same == (row["corregido"] == "false")
    assert {r["source_image_hash"] for r in rows} == {first["work_id"].removeprefix("image:")}


def test_a_clef_correction_marks_every_strip_it_rules(
    base: tuple[str, Path], tmp_path: Path
) -> None:
    output = tmp_path / "pares"
    assert _export(output, *_db_args(base)) == 0
    rows = [r for r in _rows(output / "pares.csv") if r["session_id"] == "s-test"]
    assert [r["corregido"] for r in rows] == ["true", "true"]
    second = musicxml_to_score_ir((output / rows[1]["corregida"]).read_text(encoding="utf-8"))
    assert second.parts[0].staves[0].measures[0].clef == Clef("F", 4)
    read = musicxml_to_score_ir((output / rows[1]["homr"]).read_text(encoding="utf-8"))
    assert read.parts[0].staves[0].measures[0].clef != Clef("F", 4)


def test_the_same_base_gives_the_same_pairs(base: tuple[str, Path], tmp_path: Path) -> None:
    one, two = tmp_path / "una", tmp_path / "otra"
    assert _export(one, *_db_args(base)) == 0
    assert _export(two, *_db_args(base)) == 0
    assert (one / "pares.csv").read_bytes() == (two / "pares.csv").read_bytes()
    assert _info(one)["sha256"]["pares.csv"] == _info(two)["sha256"]["pares.csv"]


def test_the_partition_is_by_work_without_leaks(base: tuple[str, Path], tmp_path: Path) -> None:
    output = tmp_path / "pares"
    assert _export(output, *_db_args(base)) == 0
    rows = _rows(output / "pares.csv")

    sides: dict[str, set[str]] = {}
    for row in rows:
        sides.setdefault(row["work_id"], set()).add(row["split"])
        assert row["imagen"].startswith(f"{row['split']}/")
    assert all(len(found) == 1 for found in sides.values()), sides
    # Las dos sesiones de la misma foto, del mismo lado; cada partitura de prueba, del suyo.
    split_of = {r["session_id"]: r["split"] for r in rows}
    assert split_of["s-foto"] == split_of["s-otra-foto"] == split_of["s-visita"]
    assert (split_of["s-train"], split_of["s-test"]) == ("train", "test")
    # La página del banco subida sin su partitura de prueba va con ella: es la misma foto.
    assert {r["work_id"] for r in rows if r["session_id"] in ("s-test", "s-banco")} == {
        f"test_score:{TEST_PAGE}"
    }
    for column in ("source_image_hash", "imagen_sha256"):
        found: dict[str, set[str]] = {}
        for row in rows:
            found.setdefault(row[column], set()).add(row["split"])
        assert all(len(sides) == 1 for sides in found.values()), column
    assert sorted(p.name for p in output.iterdir() if p.is_dir()) == ["test", "train"]

    counts = _info(output)["counts"]
    assert counts["pairs"] == len(rows) == 12
    assert counts["by_split"]["test"]["pairs"] == sum(1 for r in rows if r["split"] == "test")
    assert counts["works"] == len(sides) == 3
    filters = _info(output)["filters"]
    assert (filters["split_seed"], filters["test_fraction"]) == (SPLIT_SEED, TEST_FRACTION)


def _nothing_of(output: Path, session_id: str) -> None:
    """Ni un archivo, ni una fila, ni su identificador en la ficha o en `run_info.json`."""
    assert not any(session_id in str(p.relative_to(output)) for p in output.rglob("*"))
    for name in ("pares.csv", "README.md", "run_info.json"):
        assert session_id not in (output / name).read_text(encoding="utf-8"), name


def test_registered_accounts_with_the_current_consent_enter_by_default(
    base: tuple[str, Path], tmp_path: Path
) -> None:
    # Decisión del responsable del 2026-11-19 (#422): por defecto entran.
    output = tmp_path / "por-defecto"
    assert _export(output, *_db_args(base)) == 0
    info = _info(output)
    exported = {r["session_id"] for r in _rows(output / "pares.csv")}
    # El permiso vigente y las cuentas anteriores al registro (a las que no se les pide).
    assert {"s-visita", "s-foto", "s-train"} <= exported
    # Sin el permiso vigente (de otro texto, o nunca dado o retirado): fuera, solo contadas.
    for session_id in ("s-antigua", "s-anonima"):
        _nothing_of(output, session_id)
    assert info["consent"] == {
        "version": DATA_CONSENT_VERSION,
        "sessions_without_current_consent": 2,
        "sessions_excluded_by_option": 0,
    }
    assert info["filters"]["exclude_self_registered"] is False
    assert "quedan siempre fuera: 2 sesiones" in (output / "README.md").read_text(encoding="utf-8")


def test_an_option_leaves_out_every_registered_account(
    base: tuple[str, Path], tmp_path: Path
) -> None:
    output = tmp_path / "sin-registro"
    assert _export(output, *_db_args(base), "--exclude-self-registered") == 0
    info = _info(output)
    for session_id in ("s-visita", "s-antigua", "s-anonima"):
        _nothing_of(output, session_id)
    # Las que no tienen el permiso siguen contadas por eso, no por la opción.
    assert (
        info["consent"]["sessions_without_current_consent"],
        info["consent"]["sessions_excluded_by_option"],
    ) == (2, 1)
    exported = {r["session_id"] for r in _rows(output / "pares.csv")}
    assert {"s-foto", "s-train"} <= exported


def test_sessions_without_capture_unfinished_or_unverified_are_left_out(
    base: tuple[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Ninguna corrección hecha desde la vista cambia el número de compases, que es lo que la
    # alineación no explica: aquí se simula una sesión cuya corrección no se puede verificar.
    unverified = {"doc-s-otra-foto"}

    def fake(raw: ScoreIR, final: ScoreIR, *, document_id: str) -> bool:
        return document_id not in unverified and correction_verified(
            raw, final, document_id=document_id
        )

    monkeypatch.setattr("ml.export_pairs_cli.correction_verified", fake)
    output = tmp_path / "pares"
    assert _export(output, *_db_args(base)) == 0
    info = _info(output)
    exported = {r["session_id"] for r in _rows(output / "pares.csv")}

    assert info["left_out"]["s-sin-captura"].startswith("sin la captura de HOMR")
    assert info["left_out"]["s-otra-foto"].startswith("la corrección no se verifica")
    assert "s-abierta" not in exported and "s-abierta" not in info["left_out"]
    assert exported == {"s-foto", "s-train", "s-test", "s-banco", "s-visita"}
    assert exported == set(info["sessions"])
    assert info["filters"]["status"] == "finalized"
    assert info["filters"]["verified_only"] is True


def test_run_info_and_the_dataset_card(base: tuple[str, Path], tmp_path: Path) -> None:
    output = tmp_path / "pares"
    assert _export(output, *_db_args(base)) == 0
    info = _info(output)

    assert info["simulated"] is False
    assert "commit" in info and info["format"]["score"] == "musicxml"
    for name in ("pares.csv", "README.md"):
        assert info["sha256"][name] == hashlib.sha256((output / name).read_bytes()).hexdigest()
    # La altura de s-foto (una tira) y la clave de s-test (sus dos tiras).
    assert info["counts"]["pairs_corrected"] == 3
    assert info["homr_versions"] == {"0.7.0": 6}

    card = (output / "README.md").read_text(encoding="utf-8")
    for heading in ("## Origen", "## Licencias", "## Permiso", "## Partición", "## Limitaciones"):
        assert heading in card, heading
    assert "INV-0001" in card and "PrIMuS" in card and str(SPLIT_SEED) in card
    # De la base, solo el dialecto y el nombre: ni usuario, ni host, ni contraseña.
    assert info["origin"]["database"] == "sqlite:copia.db"


def test_the_export_refuses_unsafe_outputs_and_missing_arguments(
    base: tuple[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CADENZA_ARTIFACTS_DIR", raising=False)
    monkeypatch.delenv("CADENZA_DATABASE_URL", raising=False)
    db_url, artifacts = base
    args = _db_args(base)
    # Sin la semilla de la partición, sin las fotos, sin la base o con una fracción imposible.
    assert _export(tmp_path / "a", *args[:4]) == 1
    assert _export(tmp_path / "b", "--db-url", db_url, "--split-seed", "1") == 1
    assert _export(tmp_path / "c", "--artifacts-dir", str(artifacts), "--split-seed", "1") == 1
    assert _export(tmp_path / "d", *args[:6], "--test-fraction", "1.5") == 1
    assert not any((tmp_path / name).exists() for name in "abcd")
    # La salida ha de estar vacía.
    used = tmp_path / "usada"
    used.mkdir()
    (used / "viejo.png").write_bytes(b"x")
    assert _export(used, *args) == 1
    # Ni en results/ ni en data/ del repositorio.
    repo = Path(__file__).resolve().parents[3]
    for folder in ("results", "data"):
        target = repo / folder / f"pares-{secrets.token_hex(4)}"
        assert _export(target, *args) == 1
        assert not target.exists()


# --- Voz y piano: el gran pentagrama es un par con sus dos pentagramas -------------------------


def _staff(staff_id: str, extra: int | None = None) -> Staff:
    measures = []
    for n in range(1, 5):
        events = [Event(kind=EventKind.NOTE, pitch="C4", duration_beats=Fraction(4))]
        if n == extra:  # en lo corregido, una nota que HOMR no vio
            events = [
                Event(kind=EventKind.NOTE, pitch="C4", duration_beats=Fraction(2)),
                Event(kind=EventKind.NOTE, pitch="D4", duration_beats=Fraction(2)),
            ]
        measures.append(
            Measure(
                number=n,
                events=tuple(events),
                time_signature=TimeSignature(4, 4) if n == 1 else None,
            )
        )
    return Staff(id=staff_id, measures=tuple(measures))


def _voice_and_piano(extra: int | None = None) -> ScoreIR:
    return ScoreIR(
        parts=(
            Part(id="P1", staves=(_staff("P1-S1"),)),
            Part(id="P2", staves=(_staff("P2-S1"), _staff("P2-S2", extra))),
        )
    )


def _piano_capture() -> dict[str, object]:
    capture = homr_capture.Capture(systems=["1", "3"])
    capture.readings.append(
        homr_capture.ReadingCapture(
            mode="paired",
            image_shape=(600, 1000),
            source_shape=(600, 1000),
            autocrop=None,
            staves=[
                {"grand": False, "cx": 0.5, "cy": 0.1, "w": 0.8, "h": 0.05},
                {"grand": True, "cx": 0.5, "cy": 0.3, "w": 0.8, "h": 0.15},
                {"grand": False, "cx": 0.5, "cy": 0.6, "w": 0.8, "h": 0.05},
                {"grand": True, "cx": 0.5, "cy": 0.8, "w": 0.8, "h": 0.15},
            ],
        )
    )
    return homr_capture.capture_primitive(
        capture, "<score-partwise/>", homr_version="0.7.0", preprocessed=False
    )


def _as_stored(value: Any) -> Any:
    """Como lo guarda la API: las figuras en texto («1/2»), no como Fraction."""
    if isinstance(value, Mapping):
        return {k: _as_stored(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_as_stored(v) for v in value]
    return str(value) if isinstance(value, Fraction) else value


def test_a_grand_staff_is_one_pair_with_both_staves(tmp_path: Path) -> None:
    db_url = f"sqlite:///{(tmp_path / 'piano.db').as_posix()}"
    artifacts = tmp_path / "artefactos"
    engine = create_engine_for_url(db_url)
    create_schema(engine)
    read, final = _voice_and_piano(), _voice_and_piano(extra=2)
    with session_scope(create_session_factory(engine)) as db:
        SqlAlchemyUserRepository(db).add(_user("ana"))
        buffer = io.BytesIO()
        Image.new("RGB", (1000, 600), "white").save(buffer, format="PNG")
        image = FilesystemArtifactStore(artifacts, db).put(
            buffer.getvalue(), kind="image", media_type="image/png"
        )
        document = ScoreDocument(
            id="doc-s-piano",
            score=read,
            anchors=build_anchor_index(read),
            provenance=Provenance(omr_engine="homr", source_image_hash=image),
            omr_capture=_piano_capture(),
        )
        SqlAlchemySessionRepository(db).add(
            SessionData(
                id="s-piano",
                document_id=document.id,
                omr_engine="homr",
                document=document.to_primitive(),
                image_artifact=image,
                status="finalized",
                owner_id="ana",
            ),
            [],
        )
        edits = SqlAlchemyEditEventRepository(db)
        for edit in derive_edit_events(read, final, document_id="doc-s-piano", author="ana"):
            edits.append(
                "s-piano",
                replace(edit, before=_as_stored(edit.before), after=_as_stored(edit.after)),
            )

    output = tmp_path / "pares"
    args = ["--db-url", db_url, "--artifacts-dir", str(artifacts), "--split-seed", str(SPLIT_SEED)]
    assert _export(output, *args) == 0
    rows = {r["par"]: r for r in _rows(output / "pares.csv")}
    assert sorted(rows) == [
        "s-piano/s1_0-0",
        "s-piano/s1_1-0+1-1",
        "s-piano/s2_0-0",
        "s-piano/s2_1-0+1-1",
    ]
    piano = rows["s-piano/s1_1-0+1-1"]
    assert (piano["pentagramas"], piano["corregido"]) == ("1-0+1-1", "true")
    assert rows["s-piano/s1_0-0"]["corregido"] == "false"

    fixed = musicxml_to_score_ir((output / piano["corregida"]).read_text(encoding="utf-8"))
    (part,) = fixed.parts
    upper, lower = part.staves
    assert [m.number for m in upper.measures] == [1, 2] == [m.number for m in lower.measures]
    # La nota que faltaba, en la mano izquierda del compás 2, solo en lo corregido.
    assert [e.pitch for e in lower.measures[1].events] == ["C4", "D4"]
    read_back = musicxml_to_score_ir((output / piano["homr"]).read_text(encoding="utf-8"))
    assert [e.pitch for e in read_back.parts[0].staves[1].measures[1].events] == ["C4"]


def test_sessions_that_share_a_test_score_or_a_photo_are_one_work() -> None:
    def session(sid: str, test_score: str | None, image: str | None) -> SessionData:
        return SessionData(
            id=sid,
            document_id=f"doc-{sid}",
            omr_engine="homr",
            document={},
            image_artifact=image,
            test_score_id=test_score,
        )

    works = shared_works(
        [
            session("a", "TS-02", "h1"),
            session("b", None, "h1"),  # la foto de TS-02, sin su partitura de prueba
            session("c", None, "h2"),
            session("d", "TS-01", "h3"),
            session("e", "TS-03", "h3"),  # dos partituras con la misma foto: la menor
            session("f", None, None),
        ]
    )
    assert works == {
        "a": "test_score:TS-02",
        "b": "test_score:TS-02",
        "c": "image:h2",
        "d": "test_score:TS-01",
        "e": "test_score:TS-01",
    }
