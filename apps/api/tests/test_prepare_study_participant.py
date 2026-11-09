"""Preparar la cuenta y las sesiones de un participante del estudio (#249, protocolo §2.4 y §5).

`scripts/prepare_study_participant.py` usa solo el contrato v1, como la web: entra como
investigador, da de alta la cuenta del participante, entra como él y transcribe el calentamiento
y sus cuatro bloques con su condición y su `test_score_id`. Aquí corre contra la API real con el
doble de OMR, sobre una base en memoria.
"""

from __future__ import annotations

import copy
import hashlib
import re
import secrets
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from cadenza.api import Settings, create_app
from cadenza.application import Role, User
from cadenza.domain import ScoreDocument
from cadenza.omr.testing import FakeOMREngine
from cadenza.persistence import (
    SqlAlchemyUserRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from fastapi.testclient import TestClient

from scripts.prepare_study_participant import (
    PrepareError,
    _detail,
    load_manifest,
    main,
    plan_sessions,
    prepare_participant,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PROTOCOL = REPO_ROOT / "docs" / "experimentos" / "protocolo_medicion_esfuerzo.md"
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
)
INVESTIGATOR = "investigadora"
INVESTIGATOR_PASSWORD = secrets.token_urlsafe(12)


# ---------------------------------------------------------------------------
# Escenario: la API con el doble de OMR, un investigador y el banco en una carpeta temporal.
# ---------------------------------------------------------------------------


def _bank(tmp_path: Path) -> tuple[dict[str, Any], Path]:
    """El manifiesto real, con los sha256 de unas imágenes de prueba distintas por partitura."""

    manifest = copy.deepcopy(load_manifest())
    bank_dir = tmp_path / "banco"
    bank_dir.mkdir()
    for index, entry in enumerate(manifest["partituras"]):
        content = PNG_BYTES + bytes([index])
        (bank_dir / entry["salida"]["imagen"]).write_bytes(content)
        entry["sha256"]["imagen"] = hashlib.sha256(content).hexdigest()
    return manifest, bank_dir


class _SlowFakeOMR(FakeOMREngine):
    """El doble de OMR, que tarda un poco como HOMR: dos sesiones seguidas no comparten la
    misma marca de tiempo, y el listado (por `created_at`) tiene un orden determinista."""

    def transcribe(self, image_path: Path) -> ScoreDocument:
        time.sleep(0.02)
        return super().transcribe(image_path)


def _client(tmp_path: Path) -> TestClient:
    engine = create_memory_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)
    settings = Settings(
        auth_secret_key="secret-key-at-least-32-bytes-long-for-testing",
        artifacts_dir=tmp_path / "artifacts",
    )
    app = create_app(session_factory, omr_engine=_SlowFakeOMR(), settings=settings)
    with session_factory() as db:
        SqlAlchemyUserRepository(db).add(
            User(
                id="inv-1",
                username=INVESTIGATOR,
                password_hash=app.state.password_hasher.hash(INVESTIGATOR_PASSWORD),
                role=Role.INVESTIGADOR,
                active=True,
            )
        )
        db.commit()
    return TestClient(app)


def _password_source(password: str) -> tuple[Callable[[bool], str], list[bool]]:
    asked: list[bool] = []

    def source(new_account: bool) -> str:
        asked.append(new_account)
        return password

    return source, asked


def _login(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", data={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _prepare(
    client: TestClient,
    manifest: dict[str, Any],
    bank_dir: Path,
    participant: str,
    password: str,
    lines: list[str] | None = None,
) -> list[bool]:
    source, asked = _password_source(password)
    prepare_participant(
        client,
        participant=participant,
        investigator=INVESTIGATOR,
        investigator_password=INVESTIGATOR_PASSWORD,
        participant_password=source,
        plan=plan_sessions(manifest, participant, bank_dir),
        report=(lines if lines is not None else []).append,
    )
    return asked


def _sessions(client: TestClient, headers: dict[str, str]) -> list[dict[str, Any]]:
    response = client.get("/sessions", headers=headers)
    assert response.status_code == 200, response.text
    sessions: list[dict[str, Any]] = response.json()
    return sessions


# ---------------------------------------------------------------------------
# La matriz del manifiesto es la del protocolo y es un cuadrado latino.
# ---------------------------------------------------------------------------


def _protocol_matrix() -> dict[str, list[tuple[str, str]]]:
    row = re.compile(r"^\|\s*\*\*(P\d\d)\*\*\s*\|(.+)\|\s*$")
    cell = re.compile(r"^(TS-\d\d) \(`(assisted|unassisted)`\)$")
    matrix: dict[str, list[tuple[str, str]]] = {}
    for line in PROTOCOL.read_text(encoding="utf-8").splitlines():
        match = row.match(line)
        if match is None:
            continue
        blocks = []
        for raw in match.group(2).split("|"):
            parsed = cell.match(raw.strip())
            assert parsed is not None, line
            blocks.append((parsed.group(1), parsed.group(2)))
        matrix[match.group(1)] = blocks
    return matrix


def _manifest_matrix() -> dict[str, list[tuple[str, str]]]:
    matrix = load_manifest()["estudio"]["matriz"]
    return {
        code: [(block["partitura"], block["condicion"]) for block in blocks]
        for code, blocks in matrix.items()
    }


def test_the_manifest_matrix_is_the_protocol_matrix() -> None:
    protocol = _protocol_matrix()

    assert sorted(protocol) == [f"P0{n}" for n in range(1, 9)]
    assert _manifest_matrix() == protocol


def test_the_matrix_is_a_latin_square_with_balanced_conditions() -> None:
    """Cada participante hace las cuatro partituras, dos en cada condición; cada partitura va
    dos veces en cada posición, y cada posición tiene tantas asistidas como no asistidas. No es
    un cuadrado de Williams: no equilibra qué partitura sigue a cuál."""
    matrix = _manifest_matrix()
    scores = ["TS-01", "TS-02", "TS-03", "TS-04"]

    for code, blocks in matrix.items():
        assert sorted(score for score, _ in blocks) == scores, code
        assert Counter(condition for _, condition in blocks) == {"assisted": 2, "unassisted": 2}
    pairs = Counter(pair for blocks in matrix.values() for pair in blocks)
    assert set(pairs.values()) == {4}
    for position in range(4):
        assert set(Counter(blocks[position][0] for blocks in matrix.values()).values()) == {2}
        assert Counter(blocks[position][1] for blocks in matrix.values()) == {
            "assisted": 4,
            "unassisted": 4,
        }


# ---------------------------------------------------------------------------
# El plan: calentamiento y bloques, con imágenes comprobadas antes de tocar la API.
# ---------------------------------------------------------------------------


def test_the_plan_is_the_warmup_and_the_four_blocks_of_the_participant(tmp_path: Path) -> None:
    manifest, bank_dir = _bank(tmp_path)

    plan = plan_sessions(manifest, "P03", bank_dir)

    assert [(s.block, s.test_score_id, s.condition) for s in plan] == [
        (0, "calentamiento", "assisted"),
        (1, "TS-02", "assisted"),
        (2, "TS-01", "unassisted"),
        (3, "TS-04", "assisted"),
        (4, "TS-03", "unassisted"),
    ]
    assert [s.title for s in plan] == [
        "Calentamiento",
        "Partitura 1",
        "Partitura 2",
        "Partitura 3",
        "Partitura 4",
    ]
    assert [s.instruments for s in plan] == [
        (),
        ("voice", "piano"),
        (),
        ("voice", "piano"),
        ("voice", "piano"),
    ]
    for planned in plan:
        assert "TS" not in planned.filename and "TS" not in planned.title
        assert planned.condition not in planned.filename + planned.title


def test_an_unknown_participant_code_is_rejected(tmp_path: Path) -> None:
    manifest, bank_dir = _bank(tmp_path)

    with pytest.raises(PrepareError, match="P09"):
        plan_sessions(manifest, "P09", bank_dir)


def test_a_missing_or_altered_bank_image_is_rejected(tmp_path: Path) -> None:
    manifest, bank_dir = _bank(tmp_path)
    (bank_dir / "TS-03.png").write_bytes(b"otra imagen")
    (bank_dir / "TS-04.png").unlink()

    with pytest.raises(PrepareError) as excinfo:
        plan_sessions(manifest, "P01", bank_dir)

    message = str(excinfo.value)
    assert "TS-03.png" in message and "TS-04.png" in message
    assert "build_study_bank.py" in message


# ---------------------------------------------------------------------------
# Preparar: la cuenta, las cinco sesiones en el orden de los bloques y nada del estudio a la vista.
# ---------------------------------------------------------------------------


def test_prepare_creates_the_account_and_the_sessions_in_block_order(tmp_path: Path) -> None:
    client = _client(tmp_path)
    manifest, bank_dir = _bank(tmp_path)
    password = secrets.token_urlsafe(12)
    lines: list[str] = []

    asked = _prepare(client, manifest, bank_dir, "P02", password, lines)

    assert asked == [True]
    inv = _login(client, INVESTIGATOR, INVESTIGATOR_PASSWORD)
    users = {u["username"]: u for u in client.get("/users", headers=inv).json()}
    assert users["P02"]["role"] == "transcriptor"
    assert users["P02"]["active"] is True
    assert users["P02"]["self_registered"] is False

    listed = _sessions(client, _login(client, "P02", password))
    assert [s["title"] for s in listed] == [
        "Calentamiento",
        "Partitura 1",
        "Partitura 2",
        "Partitura 3",
        "Partitura 4",
    ]
    assert [(s["test_score_id"], s["condition"]) for s in listed] == [
        ("calentamiento", "assisted"),
        ("TS-01", "unassisted"),
        ("TS-02", "assisted"),
        ("TS-03", "unassisted"),
        ("TS-04", "assisted"),
    ]
    for session in listed:
        assert "TS" not in (session["source_filename"] or "")
        assert session["status"] == "transcribed"
    # El doble de OMR lee una sola parte: de voz y piano queda la voz (ADR-0041).
    assert [[i["instrument"] for i in s["instruments"]] for s in listed] == [
        [],
        [],
        ["voice"],
        ["voice"],
        ["voice"],
    ]
    assert all(password not in line for line in lines)
    assert any("creada" in line for line in lines)


def test_prepare_is_idempotent(tmp_path: Path) -> None:
    client = _client(tmp_path)
    manifest, bank_dir = _bank(tmp_path)
    password = secrets.token_urlsafe(12)
    _prepare(client, manifest, bank_dir, "P05", password)
    headers = _login(client, "P05", password)
    first = _sessions(client, headers)
    lines: list[str] = []

    asked = _prepare(client, manifest, bank_dir, "P05", password, lines)

    assert asked == [False]
    assert _sessions(client, headers) == first
    assert sum("ya existía" in line for line in lines) == 6


def test_prepare_resumes_after_an_interrupted_run(tmp_path: Path) -> None:
    client = _client(tmp_path)
    manifest, bank_dir = _bank(tmp_path)
    password = secrets.token_urlsafe(12)
    plan = plan_sessions(manifest, "P07", bank_dir)
    source, _ = _password_source(password)
    # Se corta tras las dos primeras transcripciones (los bloques 4 y 3, que se crean primero).
    prepare_participant(
        client,
        participant="P07",
        investigator=INVESTIGATOR,
        investigator_password=INVESTIGATOR_PASSWORD,
        participant_password=source,
        plan=plan,
        report=lambda line: None,
        limit=2,
    )

    _prepare(client, manifest, bank_dir, "P07", password)

    listed = _sessions(client, _login(client, "P07", password))
    assert [s["title"] for s in listed] == [
        "Calentamiento",
        "Partitura 1",
        "Partitura 2",
        "Partitura 3",
        "Partitura 4",
    ]


def test_an_existing_session_with_another_condition_stops_everything(tmp_path: Path) -> None:
    client = _client(tmp_path)
    manifest, bank_dir = _bank(tmp_path)
    password = secrets.token_urlsafe(12)
    inv = _login(client, INVESTIGATOR, INVESTIGATOR_PASSWORD)
    created = client.post(
        "/users",
        json={"username": "P01", "role": "transcriptor", "password": password},
        headers=inv,
    )
    assert created.status_code == 201
    headers = _login(client, "P01", password)
    # P01 hace TS-04 sin asistencia en el bloque 4; aquí ya hay una TS-04 asistida.
    wrong = client.post(
        "/transcribe",
        files={"file": ("x.png", PNG_BYTES, "image/png")},
        data={"condition": "assisted", "test_score_id": "TS-04"},
        headers=headers,
    )
    assert wrong.status_code == 201

    with pytest.raises(PrepareError, match="TS-04"):
        _prepare(client, manifest, bank_dir, "P01", password)

    assert len(_sessions(client, headers)) == 1


def test_a_session_created_out_of_order_stops_everything(tmp_path: Path) -> None:
    client = _client(tmp_path)
    manifest, bank_dir = _bank(tmp_path)
    password = secrets.token_urlsafe(12)
    inv = _login(client, INVESTIGATOR, INVESTIGATOR_PASSWORD)
    client.post(
        "/users",
        json={"username": "P01", "role": "transcriptor", "password": password},
        headers=inv,
    )
    headers = _login(client, "P01", password)
    # El calentamiento se crea el último: si ya está y faltan bloques, el listado quedaría
    # desordenado al crearlos.
    client.post(
        "/transcribe",
        files={"file": ("x.png", PNG_BYTES, "image/png")},
        data={"condition": "assisted", "test_score_id": "calentamiento"},
        headers=headers,
    )

    with pytest.raises(PrepareError, match="orden"):
        _prepare(client, manifest, bank_dir, "P01", password)

    assert len(_sessions(client, headers)) == 1


def test_a_wrong_password_for_an_existing_account_is_reported(tmp_path: Path) -> None:
    client = _client(tmp_path)
    manifest, bank_dir = _bank(tmp_path)
    _prepare(client, manifest, bank_dir, "P04", secrets.token_urlsafe(12))

    with pytest.raises(PrepareError, match="P04"):
        _prepare(client, manifest, bank_dir, "P04", secrets.token_urlsafe(12))


@pytest.mark.parametrize("kind", ["self_registered", "investigador", "inactive"])
def test_an_account_that_is_not_a_study_transcriber_is_refused(tmp_path: Path, kind: str) -> None:
    client = _client(tmp_path)
    manifest, bank_dir = _bank(tmp_path)
    password = secrets.token_urlsafe(12)
    app: Any = client.app
    with app.state.session_factory() as db:
        SqlAlchemyUserRepository(db).add(
            User(
                id="p06",
                username="P06",
                password_hash=app.state.password_hasher.hash(password),
                role=Role.INVESTIGADOR if kind == "investigador" else Role.TRANSCRIPTOR,
                active=kind != "inactive",
                self_registered=kind == "self_registered",
            )
        )
        db.commit()

    with pytest.raises(PrepareError, match="P06"):
        _prepare(client, manifest, bank_dir, "P06", password)


def test_an_account_without_the_investigator_role_cannot_prepare(tmp_path: Path) -> None:
    client = _client(tmp_path)
    manifest, bank_dir = _bank(tmp_path)
    password = secrets.token_urlsafe(12)
    _prepare(client, manifest, bank_dir, "P08", password)
    source, _ = _password_source(password)

    with pytest.raises(PrepareError, match="investigador"):
        prepare_participant(
            client,
            participant="P01",
            investigator="P08",
            investigator_password=password,
            participant_password=source,
            plan=plan_sessions(manifest, "P01", bank_dir),
            report=lambda line: None,
        )


# ---------------------------------------------------------------------------
# Revisión: contraseñas en los errores, cortes del proxy, fallos y huecos en el orden.
# ---------------------------------------------------------------------------


def test_a_short_password_is_refused_without_showing_it(tmp_path: Path) -> None:
    client = _client(tmp_path)
    manifest, bank_dir = _bank(tmp_path)
    short = secrets.token_urlsafe(5)
    assert len(short) == 7

    with pytest.raises(PrepareError) as excinfo:
        _prepare(client, manifest, bank_dir, "P01", short)

    assert "8 caracteres" in str(excinfo.value)
    assert short not in str(excinfo.value)


def test_the_error_detail_never_repeats_what_was_sent() -> None:
    secret = secrets.token_urlsafe(12)
    response = httpx.Response(
        422,
        json={
            "detail": [
                {
                    "type": "string_too_short",
                    "loc": ["body", "password"],
                    "msg": "String should have at least 8 characters",
                    "input": secret,
                }
            ]
        },
    )

    detail = _detail(response)

    assert secret not in detail
    assert detail == "HTTP 422: password: String should have at least 8 characters"


class _Proxy:
    """El cliente de prueba detrás de un proxy que puede cortar `POST /transcribe`.

    `mode` decide qué pasa con la transcripción número `at` (desde 1): `cut` la deja llegar a la
    API y devuelve un 504, como Nginx a los 60 s; `timeout` la deja llegar y lanza un error de
    red; `lost` devuelve el 504 sin que llegue; `busy` responde 503 sin que llegue.
    """

    def __init__(self, client: TestClient, mode: str, at: int = 1) -> None:
        self._client = client
        self._mode = mode
        self._at = at
        self._count = 0

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        response: httpx.Response = self._client.get(url, **kwargs)
        return response

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        if url != "/transcribe":
            passed: httpx.Response = self._client.post(url, **kwargs)
            return passed
        self._count += 1
        if self._count != self._at:
            through: httpx.Response = self._client.post(url, **kwargs)
            return through
        if self._mode in ("cut", "timeout"):
            assert self._client.post(url, **kwargs).status_code == 201
            if self._mode == "timeout":
                raise httpx.ReadTimeout("sin respuesta")
            return httpx.Response(504)
        return httpx.Response(504 if self._mode == "lost" else 503, json={"detail": "ocupado"})


def _prepare_through(
    proxy: _Proxy,
    manifest: dict[str, Any],
    bank_dir: Path,
    participant: str,
    password: str,
    lines: list[str],
    sleeps: list[float],
) -> None:
    source, _ = _password_source(password)
    prepare_participant(
        proxy,  # type: ignore[arg-type]  # un doble con get y post, como httpx.Client
        participant=participant,
        investigator=INVESTIGATOR,
        investigator_password=INVESTIGATOR_PASSWORD,
        participant_password=source,
        plan=plan_sessions(manifest, participant, bank_dir),
        report=lines.append,
        wait_s=30,
        poll_s=10,
        sleep=sleeps.append,
    )


@pytest.mark.parametrize("mode", ["cut", "timeout"])
def test_a_proxy_cut_waits_for_the_session_instead_of_repeating_it(
    tmp_path: Path, mode: str
) -> None:
    client = _client(tmp_path)
    manifest, bank_dir = _bank(tmp_path)
    password = secrets.token_urlsafe(12)
    lines: list[str] = []
    sleeps: list[float] = []

    _prepare_through(_Proxy(client, mode, at=2), manifest, bank_dir, "P03", password, lines, sleeps)

    listed = _sessions(client, _login(client, "P03", password))
    assert [s["title"] for s in listed] == [
        "Calentamiento",
        "Partitura 1",
        "Partitura 2",
        "Partitura 3",
        "Partitura 4",
    ]
    assert sleeps == [10]
    assert sum("tras un corte del proxy" in line for line in lines) == 1


def test_a_cut_transcription_that_never_appears_stops_and_says_to_wait(tmp_path: Path) -> None:
    client = _client(tmp_path)
    manifest, bank_dir = _bank(tmp_path)
    password = secrets.token_urlsafe(12)
    sleeps: list[float] = []

    with pytest.raises(PrepareError, match="espera"):
        _prepare_through(
            _Proxy(client, "lost", at=1), manifest, bank_dir, "P03", password, [], sleeps
        )

    assert sleeps == [10, 10, 10]
    assert _sessions(client, _login(client, "P03", password)) == []


def test_a_failed_transcription_stops_and_a_new_run_resumes_in_order(tmp_path: Path) -> None:
    client = _client(tmp_path)
    manifest, bank_dir = _bank(tmp_path)
    password = secrets.token_urlsafe(12)

    with pytest.raises(PrepareError, match="Vuelve a ejecutar"):
        _prepare_through(_Proxy(client, "busy", at=3), manifest, bank_dir, "P06", password, [], [])
    headers = _login(client, "P06", password)
    assert [s["title"] for s in _sessions(client, headers)] == ["Partitura 3", "Partitura 4"]

    _prepare(client, manifest, bank_dir, "P06", password)

    assert [s["title"] for s in _sessions(client, headers)] == [
        "Calentamiento",
        "Partitura 1",
        "Partitura 2",
        "Partitura 3",
        "Partitura 4",
    ]


def _participant_with(
    client: TestClient, participant: str, password: str, sessions: list[tuple[str, str]]
) -> dict[str, str]:
    inv = _login(client, INVESTIGATOR, INVESTIGATOR_PASSWORD)
    created = client.post(
        "/users",
        json={"username": participant, "role": "transcriptor", "password": password},
        headers=inv,
    )
    assert created.status_code == 201
    headers = _login(client, participant, password)
    for score_id, condition in sessions:
        response = client.post(
            "/transcribe",
            files={"file": ("x.png", PNG_BYTES, "image/png")},
            data={"condition": condition, "test_score_id": score_id},
            headers=headers,
        )
        assert response.status_code == 201
    return headers


def test_two_sessions_of_the_same_score_stop_everything(tmp_path: Path) -> None:
    client = _client(tmp_path)
    manifest, bank_dir = _bank(tmp_path)
    password = secrets.token_urlsafe(12)
    # P01 hace TS-04 sin asistencia en el bloque 4.
    twice = [("TS-04", "unassisted"), ("TS-04", "unassisted")]
    headers = _participant_with(client, "P01", password, twice)

    with pytest.raises(PrepareError, match="más de una sesión de TS-04"):
        _prepare(client, manifest, bank_dir, "P01", password)

    assert len(_sessions(client, headers)) == 2


def test_a_gap_in_the_middle_of_the_blocks_stops_everything(tmp_path: Path) -> None:
    client = _client(tmp_path)
    manifest, bank_dir = _bank(tmp_path)
    password = secrets.token_urlsafe(12)
    # P01: bloque 4 TS-04 y bloque 2 TS-02, sin asistencia; falta el bloque 3 (TS-03).
    with_gap = [("TS-04", "unassisted"), ("TS-02", "unassisted")]
    headers = _participant_with(client, "P01", password, with_gap)

    with pytest.raises(PrepareError, match="orden"):
        _prepare(client, manifest, bank_dir, "P01", password)

    assert len(_sessions(client, headers)) == 2


def test_main_fails_clearly_without_the_bank(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "vacio"
    empty.mkdir()

    code = main(
        [
            "P01",
            "--api-url",
            "http://127.0.0.1:9",
            "--investigator",
            INVESTIGATOR,
            "--bank-dir",
            str(empty),
        ]
    )

    assert code == 1
    assert "build_study_bank.py" in capsys.readouterr().err
