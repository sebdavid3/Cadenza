"""`ml export-tables`: los datos para reconocer los errores de HOMR, en CSV planos.

Las pruebas montan una base SQLite temporal con dos sesiones que entran (una con correcciones
de altura, figura, alteración, borrado, inserción, clave y armadura, y otra con el compás
corregido) y dos que quedan fuera (una sin terminar y otra de una cuenta del registro). Las
filas de las notas, los faltantes y las sugerencias salen de `session_records` y
`build_correction_records`: son exactamente lo que usa el entrenamiento.
"""

from __future__ import annotations

import csv
import json
import secrets
from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from cadenza.application import DATA_CONSENT_VERSION, NewSuggestion, Role, SessionData, User
from cadenza.domain import (
    Anchor,
    Clef,
    EditEvent,
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
    TimeSignature,
    build_anchor_index,
)
from cadenza.learning import derive_edit_events
from cadenza.learning.suggestions import session_records
from cadenza.learning.tables import TABLES, corpus_tables, database_tables
from cadenza.persistence import (
    SqlAlchemyEditEventRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
    create_engine_for_url,
    create_schema,
    create_session_factory,
    session_scope,
)

from ml.cli import main

from .suggestions_support import SPLIT_SEED, write_corpus

STAFF_ID = "P1-S1"


def _note(pitch: str, beats: str = "1") -> Event:
    return Event(kind=EventKind.NOTE, pitch=pitch, duration_beats=Fraction(beats))


def _score(
    *measures: tuple[Event, ...], changes: dict[int, dict[str, Any]] | None = None
) -> ScoreIR:
    changes = changes or {}
    built = []
    for index, events in enumerate(measures):
        extra = changes.get(index, {})
        built.append(
            Measure(
                number=index + 1,
                events=events,
                time_signature=extra.get("time", TimeSignature(4, 4)),
                clef=extra.get("clef", Clef.treble() if index == 0 else None),
                key_signature=extra.get("key", KeySignature(fifths=0) if index == 0 else None),
            )
        )
    return ScoreIR(parts=(Part(id="P1", staves=(Staff(id=STAFF_ID, measures=tuple(built)),)),))


def _read_and_final() -> tuple[ScoreIR, ScoreIR]:
    """Lo que «leyó» HOMR y lo que dejó la persona, compás a compás."""
    read = _score(
        (_note("C4"), _note("D4"), _note("E4"), _note("F4")),  # 1: altura
        (_note("G4"), _note("A4"), _note("B4"), _note("C5")),  # 2: alteración
        (_note("C5", "1/2"), _note("D5"), _note("E5"), _note("F5")),  # 3: figura
        (_note("G4"), _note("G4"), _note("A4"), _note("B4"), _note("C5")),  # 4: borrado
        (_note("E4"), _note("F4"), _note("G4")),  # 5: falta una nota
        (_note("C4"), _note("D4"), _note("E4"), _note("F4")),  # 6: clave y armadura
    )
    final = _score(
        (_note("D4"), _note("D4"), _note("E4"), _note("F4")),
        (_note("G4"), _note("A4"), _note("Bb4"), _note("C5")),
        (_note("C5"), _note("D5"), _note("E5"), _note("F5")),
        (_note("G4"), _note("A4"), _note("B4"), _note("C5")),
        (_note("E4"), _note("F4"), _note("G4"), _note("A4")),
        (_note("C4"), _note("D4"), _note("E4"), _note("F4")),
        changes={5: {"clef": Clef.bass(), "key": KeySignature(fifths=1)}},
    )
    return read, final


def _document(document_id: str, score: ScoreIR, *, image: str | None = None) -> ScoreDocument:
    return ScoreDocument(
        id=document_id,
        score=score,
        anchors=build_anchor_index(score),
        provenance=Provenance(
            omr_engine="homr",
            model_version="homr-0.3",
            rules_version="rules-7",
            source_image_hash=image,
            suggestions_version="sug-1",
        ),
    )


def _anchor(measure: int, event_index: int = 0, voice: int = 0) -> Anchor:
    return Anchor(
        part=0, staff=0, measure=measure, voice=voice, event_index=event_index, staff_id=STAFF_ID
    )


def _finding(measure: int, rule_id: str, *, at_seq: int = 0, event_index: int = 0) -> Finding:
    return Finding(
        anchor=_anchor(measure, event_index),
        rule_id=rule_id,
        severity=Severity.ERROR,
        message="msg",
        at_seq=at_seq,
    )


def _suggestion(measure: int, pitch: str, *, level: str = "high") -> SuggestedEdit:
    return SuggestedEdit(
        op=EditOp.SET_PITCH,
        anchor=_anchor(measure),
        after={"pitch": pitch},
        confidence=0.8,
        confidence_level=level,
        source="learned",
        model_version="sug-1",
    )


def _user(user_id: str, *, self_registered: bool = False, role: Role = Role.TRANSCRIPTOR) -> User:
    return User(
        id=user_id,
        username=f"P-{user_id}",
        password_hash=secrets.token_hex(8),
        role=role,
        self_registered=self_registered,
    )


def _session(session_id: str, owner: str, score: ScoreIR, **fields: Any) -> SessionData:
    image = fields.pop("image", None)
    document = _document(f"doc-{session_id}", score, image=image)
    return SessionData(
        id=session_id,
        owner_id=owner,
        document_id=document.id,
        omr_engine="homr",
        document=document.to_primitive(),
        model_version="homr-0.3",
        source_filename="Nombre Apellido - mi partitura.png",
        created_at=datetime(2026, 11, 9, 10, tzinfo=UTC),
        **fields,
    )


def _as_stored(edit: EditEvent) -> EditEvent:
    """La edición como la guarda la API: las figuras en texto («1/2»), no como Fraction."""

    def plain(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {k: plain(v) for k, v in value.items()}
        if isinstance(value, list | tuple):
            return [plain(v) for v in value]
        return str(value) if isinstance(value, Fraction) else value

    return replace(edit, before=plain(edit.before), after=plain(edit.after))


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    """Una base con dos sesiones que entran y dos que quedan fuera."""
    url = f"sqlite:///{(tmp_path / 'cadenza.db').as_posix()}"
    engine = create_engine_for_url(url)
    create_schema(engine)
    factory = create_session_factory(engine)
    read, final = _read_and_final()
    with session_scope(factory) as db:
        users = SqlAlchemyUserRepository(db)
        users.add(_user("ana"))
        users.add(_user("luis", role=Role.INVESTIGADOR))
        # Del registro: con el permiso vigente, sin permiso y con el de un texto anterior.
        consent = datetime(2026, 11, 10, tzinfo=UTC)
        users.add(
            replace(
                _user("visita", self_registered=True),
                data_consent_at=consent,
                data_consent_version=DATA_CONSENT_VERSION,
            )
        )
        users.add(_user("anonima", self_registered=True))
        users.add(
            replace(
                _user("antigua", self_registered=True),
                data_consent_at=consent,
                data_consent_version="0",
            )
        )
        sessions = SqlAlchemySessionRepository(db)
        edits = SqlAlchemyEditEventRepository(db)

        # 1. Estudio: todas las correcciones de notas, clave y armadura, con sugerencias.
        sessions.add(
            _session("s-estudio", "ana", read, status="finalized", test_score_id="TS-01"),
            [
                _finding(1, "pitch.range"),
                _finding(3, "measure.balance"),
                _finding(2, "accidental.courtesy"),
                _finding(4, "measure.balance"),
                _finding(7, "time.signature"),  # un compás sin corregir
            ],
            [
                [NewSuggestion(_suggestion(1, "D4"))],
                [NewSuggestion(_suggestion(3, "E5", level="medium"))],
                [NewSuggestion(_suggestion(2, "Bb4"))],
                [],
                [],
            ],
        )
        derived = derive_edit_events(read, final, document_id="doc-s-estudio", author="ana")
        for edit in derived:
            edits.append("s-estudio", _as_stored(edit))
        by_rule = {s.anchor["measure"]: s for s in sessions.list_suggestions("s-estudio")}
        sessions.respond_suggestion(
            "s-estudio", by_rule[1].id, response="accepted", user="ana", applied_seq=1
        )
        rejected = sessions.respond_suggestion(
            "s-estudio", by_rule[3].id, response="rejected", user="ana"
        )
        # Revalidación: hereda el rechazo y uno de sus posibles errores se descarta.
        last = len(derived)
        current = sessions.replace_findings(
            "s-estudio",
            [
                _finding(3, "measure.balance", at_seq=last),
                _finding(4, "measure.balance", at_seq=last),
            ],
            at_seq=last,
            suggestions=[[NewSuggestion(_suggestion(3, "E5"), inherited=rejected)], []],
        )
        sessions.dismiss_finding("s-estudio", current[1].id, user="ana", reason="falso positivo")

        # 2. Equipo: solo el compás corregido (derive_edit_events no lo alinea).
        two = _score(
            (_note("C4"), _note("D4"), _note("E4")), (_note("F4"), _note("G4"), _note("A4"))
        )
        sessions.add(
            _session("s-compas", "luis", two, status="finalized", image="ab" * 32),
            [_finding(1, "measure.balance")],
        )
        edits.append(
            "s-compas",
            EditEvent(
                id="time-1",
                document_id="doc-s-compas",
                seq=1,
                anchor=_anchor(1),
                op=EditOp.SET_TIME,
                author="luis",
                created_at=datetime(2026, 11, 9, 11, tzinfo=UTC),
                before={"time_signature": {"beats": 4, "beat_type": 4}, "measures": 2},
                after={"time_signature": {"beats": 3, "beat_type": 4}, "measures": 2},
            ),
        )

        # 3. Sin terminar y 4. del registro: fuera.
        sessions.add(_session("s-abierta", "ana", read, test_score_id="TS-02"), [])
        sessions.add(
            _session("s-registro", "visita", read, status="finalized", image="cd" * 32), []
        )
        # 5. y 6. Del registro sin el permiso vigente: fuera también con la opción.
        for session_id, owner in (("s-sin-permiso", "anonima"), ("s-permiso-antiguo", "antigua")):
            sessions.add(
                _session(session_id, owner, read, status="finalized", image="ef" * 32), []
            )
    return url


def _export(output: Path, *args: str) -> int:
    return main(["export-tables", "--output-dir", str(output), *args])


def _csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def _by_measure(rows: list[dict[str, str]], session: str) -> dict[int, dict[str, str]]:
    return {int(r["measure"]): r for r in rows if r["session_id"] == session}


@pytest.fixture
def exported(db_url: str, tmp_path: Path) -> Iterator[Path]:
    output = tmp_path / "salida"
    assert _export(output, "--db-url", db_url, "--split-seed", str(SPLIT_SEED)) == 0
    yield output


def test_the_export_writes_one_csv_per_table_and_the_run_info(exported: Path) -> None:
    assert sorted(p.name for p in exported.iterdir()) == sorted(
        [f"{name}.csv" for name in TABLES] + ["run_info.json"]
    )
    for name, columns in TABLES.items():
        header, _ = _csv(exported / f"{name}.csv")
        assert header == list(columns), name
        assert all(c == c.lower() and " " not in c for c in columns)
    info = json.loads((exported / "run_info.json").read_text(encoding="utf-8"))
    assert info["simulated"] is False
    assert info["filters"]["include_self_registered"] is False
    assert info["filters"]["include_unfinished"] is False
    assert info["left_out"] == {
        "s-abierta": "sin terminar (status transcribed)",
        "s-registro": "cuenta del registro público",
        "s-sin-permiso": "cuenta del registro público",
        "s-permiso-antiguo": "cuenta del registro público",
    }
    for name in TABLES:
        _, rows = _csv(exported / f"{name}.csv")
        assert info["tables"][name]["rows"] == len(rows)
        assert len(info["tables"][name]["sha256"]) == 64
    assert "commit" in info and "generated_at" in info


def test_partituras_has_one_row_per_session_without_the_file_name(exported: Path) -> None:
    header, rows = _csv(exported / "partituras.csv")
    assert "source_filename" not in header
    for written in exported.iterdir():
        assert "Apellido" not in written.read_text(encoding="utf-8"), written.name
    sessions = {r["session_id"]: r for r in rows}
    assert set(sessions) == {"s-estudio", "s-compas"}
    study = sessions["s-estudio"]
    assert study["participante"] == "P-ana"
    assert study["rol"] == "transcriptor"
    assert study["origen"] == "estudio"
    assert study["source"] == "cadenza"
    assert study["omr_engine"] == "homr" and study["model_version"] == "homr-0.3"
    assert study["rules_version"] == "rules-7"
    assert (study["partes"], study["pentagramas"], study["compases"]) == ("1", "1", "6")
    assert study["eventos_leidos"] == "24" and study["eventos_finales"] == "24"
    assert study["ediciones_log"] == "7"
    assert study["correcciones_netas"] == "7"  # = ediciones derivadas
    assert study["verified"] == "true"
    assert study["versiones_capa"] == "sug-1"
    assert sessions["s-compas"]["origen"] == "equipo"
    assert sessions["s-compas"]["rol"] == "investigador"
    assert sessions["s-compas"]["source_image_hash"] == "ab" * 32
    # verified no mira la indicación de compás: se ve en compases_con_indicacion_corregida.
    assert sessions["s-compas"]["verified"] == "true"
    assert sessions["s-compas"]["correcciones_netas"] == "0"
    assert sessions["s-compas"]["compases_con_indicacion_corregida"] == "2"


def test_notas_classifies_each_read_event(exported: Path) -> None:
    _, rows = _csv(exported / "notas.csv")
    study = [r for r in rows if r["session_id"] == "s-estudio"]
    assert len(study) == 24
    results = Counter(r["resultado"] for r in study)
    assert results == {"bien": 20, "corregida": 3, "borrada": 1}
    corrected = {int(r["measure"]): r for r in study if r["resultado"] == "corregida"}
    assert corrected[1]["ops"] == "SetPitch" and corrected[1]["fix_pitch"] == "D4"
    assert corrected[2]["ops"] == "SetAccidental"
    assert (corrected[2]["fix_accidental_before"], corrected[2]["fix_accidental_after"]) == (
        "",
        "b",
    )
    assert corrected[3]["ops"] == "SetDuration"
    assert corrected[3]["read_duration_beats"] == "1/2"
    assert corrected[3]["read_duration_beats_dec"] == "0.5"
    assert corrected[3]["fix_duration_beats"] == "1"
    deleted = next(r for r in study if r["resultado"] == "borrada")
    assert deleted["ops"] == "DeleteEvent" and deleted["measure"] == "4"
    # El contexto, aplanado con prefijos.
    first = next(r for r in study if r["measure"] == "1" and r["event_index"] == "0")
    assert first["ctx_clef"] == "G2" and first["ctx_key_fifths"] == "0"
    assert first["ctx_time_signature"] == "4/4"
    assert first["prev_kind"] == "" and first["next_pitch"] == "D4"
    assert first["ctx_accidental_vs_key"] == "in_key"


def test_faltantes_and_clave_armadura(exported: Path) -> None:
    _, missing = _csv(exported / "faltantes.csv")
    assert [(r["session_id"], r["measure"], r["ins_pitch"]) for r in missing] == [
        ("s-estudio", "5", "A4")
    ]
    assert missing[0]["ins_duration_beats_dec"] == "1.0"
    assert missing[0]["ctx_events_in_voice"] == "3"
    _, measures = _csv(exported / "clave_armadura.csv")
    assert len(measures) == 1
    row = measures[0]
    assert row["measure"] == "6" and row["ops"] == "SetClef+SetKey"
    assert (row["fix_clef"], row["fix_key_fifths"]) == ("F4", "1")


def test_compases_compares_the_read_and_final_measures(exported: Path) -> None:
    _, rows = _csv(exported / "compases.csv")
    study = _by_measure(rows, "s-estudio")
    assert sorted(study) == [1, 2, 3, 4, 5, 6]
    assert study[1]["correcciones_netas"] == "1" and study[1]["notas_corregidas"] == "1"
    assert (study[4]["eventos_leidos"], study[4]["eventos_finales"]) == ("5", "4")
    assert study[4]["notas_borradas"] == "1"
    assert study[5]["faltantes"] == "1"
    assert (study[6]["clef_read"], study[6]["clef_final"]) == ("G2", "F4")
    assert (study[6]["key_fifths_read"], study[6]["key_fifths_final"]) == ("0", "1")
    assert study[6]["clave_corregida"] == "true" and study[6]["armadura_corregida"] == "true"
    assert study[6]["correcciones_netas"] == "2"  # SetClef y SetKey
    # Posibles errores iniciales (at_seq 0) y descartados en la validación vigente.
    assert study[3]["avisos_iniciales"] == "1" and study[4]["avisos_iniciales"] == "1"
    assert study[4]["avisos_descartados"] == "1" and study[3]["avisos_descartados"] == "0"
    assert study[3]["avisos_vigentes"] == "1" and study[1]["avisos_vigentes"] == "0"
    # El compás que derive_edit_events no alinea se ve aquí.
    meter = _by_measure(rows, "s-compas")
    assert (meter[1]["time_read"], meter[1]["time_final"]) == ("4/4", "3/4")
    assert meter[1]["indicacion_corregida"] == "true"
    assert meter[1]["correcciones_netas"] == "0"


def test_sugerencias_marks_inherited_rejections(exported: Path) -> None:
    _, rows = _csv(exported / "sugerencias.csv")
    assert Counter(r["response"] for r in rows) == {
        "accepted": 1,
        "rejected": 2,
        "ignored": 1,
    }
    inherited = [r for r in rows if r["es_heredada"] == "true"]
    assert len(inherited) == 1 and inherited[0]["response"] == "rejected"
    original = next(r for r in rows if r["suggestion_id"] == inherited[0]["inherited_from"])
    assert original["es_heredada"] == "false" and original["response"] == "rejected"
    accepted = next(r for r in rows if r["response"] == "accepted")
    assert accepted["finding_rule_id"] == "pitch.range"
    assert accepted["confidence_level"] == "high" and accepted["applied_seq"] == "1"
    assert accepted["suggestion_source"] == "learned" and accepted["model_version"] == "sug-1"
    assert json.loads(accepted["after_json"]) == {"pitch": "D4"}
    assert original["confidence_level"] == "medium"
    assert accepted["linked_to_finding"] == "true" and original["linked_to_finding"] == "true"


def test_avisos_joins_the_correction_by_measure(exported: Path) -> None:
    _, rows = _csv(exported / "avisos.csv")
    study = [r for r in rows if r["session_id"] == "s-estudio"]
    assert len(study) == 7
    initial = [r for r in study if r["es_inicial"] == "true"]
    current = [r for r in study if r["es_vigente"] == "true"]
    assert len(initial) == 5 and len(current) == 2
    assert {r["measure"] for r in current} == {"3", "4"}
    dismissed = [r for r in study if r["status"] == "dismissed"]
    assert len(dismissed) == 1 and dismissed[0]["dismissal_reason"] == "falso positivo"
    by_measure = {(r["at_seq"], r["measure"]): r["compas_con_correccion"] for r in study}
    assert by_measure[("0", "1")] == "true"
    assert by_measure[("0", "7")] == "false"
    assert sum(r["compas_con_correccion"] == "true" for r in study) == 6
    meter = next(r for r in rows if r["session_id"] == "s-compas")
    assert meter["compas_con_correccion"] == "true"  # el compás cambió de indicación


def test_the_run_info_hides_the_database_credentials() -> None:
    from ml.export_tables_cli import _safe_url

    secret = secrets.token_hex(6)
    url = f"postgresql+psycopg://cadenza:{secret}@db.local:5432/cadenza?password={secret}"
    assert _safe_url(url) == "postgresql:cadenza"
    assert _safe_url("sqlite:///C:/Users/alguien/copia.db") == "sqlite:copia.db"


def test_options_include_the_sessions_left_out(db_url: str, tmp_path: Path) -> None:
    output = tmp_path / "todas"
    args = ["--db-url", db_url, "--split-seed", str(SPLIT_SEED)]
    assert _export(output, *args, "--include-self-registered", "--include-unfinished") == 0
    _, rows = _csv(output / "partituras.csv")
    origins = {r["session_id"]: r["origen"] for r in rows}
    assert origins == {
        "s-estudio": "estudio",
        "s-compas": "equipo",
        "s-abierta": "estudio",
        "s-registro": "registro",
    }
    assert {r["session_id"]: r["permiso_datos"] for r in rows}["s-registro"] == "true"
    info = json.loads((output / "run_info.json").read_text(encoding="utf-8"))
    # Las cuentas del registro solo entran con el permiso de la versión vigente del texto
    # (ADR-0065, como `ml export-staves`, ADR-0067).
    assert info["left_out"] == {
        "s-sin-permiso": "cuenta del registro sin el permiso de uso de los datos vigente",
        "s-permiso-antiguo": "cuenta del registro sin el permiso de uso de los datos vigente",
    }


def test_each_row_is_the_record_used_for_training(db_url: str) -> None:
    factory = create_session_factory(create_engine_for_url(db_url))
    with session_scope(factory) as db:
        repos: dict[str, Any] = {
            "session_repository": SqlAlchemySessionRepository(db),
            "edit_repository": SqlAlchemyEditEventRepository(db),
            "user_repository": SqlAlchemyUserRepository(db),
        }
        records, _ = session_records(**repos, split_seed=SPLIT_SEED, test_fraction=0.2)
        tables, _ = database_tables(**repos, split_seed=SPLIT_SEED, test_fraction=0.2)
    kinds = Counter(r["record"] for r in records)
    assert len(tables["notas"]) == kinds["event"]
    assert len(tables["faltantes"]) == kinds["insertion"]
    assert len(tables["clave_armadura"]) == kinds["measure"]
    assert len(tables["sugerencias"]) == kinds["suggestion"]
    events = [r for r in records if r["record"] == "event"]
    for record, row in zip(events, tables["notas"], strict=True):
        assert row["incipit_id"] == record["incipit_id"]
        assert row["event_index"] == record["anchor"]["event_index"]
        assert row["read_pitch"] == record["read"]["pitch"]
        assert row["split"] == record["split"]


def test_the_corpus_converts_with_the_same_columns(exported: Path, tmp_path: Path) -> None:
    corpus = write_corpus(tmp_path / "corpus.jsonl", works=2)
    records = [json.loads(line) for line in corpus.read_text(encoding="utf-8").splitlines()]
    output = tmp_path / "primus"
    assert _export(output, "--corpus", str(corpus)) == 0
    for name in TABLES:
        assert _csv(output / f"{name}.csv")[0] == _csv(exported / f"{name}.csv")[0], name
    _, notes = _csv(output / "notas.csv")
    assert len(notes) == sum(r["record"] == "event" for r in records)
    assert {r["source"] for r in notes} == {"primus"}
    assert {r["session_id"] for r in notes} == {""}
    _, scores = _csv(output / "partituras.csv")
    assert {r["incipit_id"] for r in scores} == {r["incipit_id"] for r in records}
    assert all(r["source"] == "primus" for r in scores)
    assert _csv(output / "compases.csv")[1] == [] and _csv(output / "avisos.csv")[1] == []
    info = json.loads((output / "run_info.json").read_text(encoding="utf-8"))
    assert info["origins"]["corpus"]["records"] == len(records)
    assert "database" not in info["origins"]


def test_both_origins_go_to_the_same_tables(db_url: str, tmp_path: Path) -> None:
    corpus = write_corpus(tmp_path / "corpus.jsonl", works=1)
    output = tmp_path / "ambas"
    args = ["--corpus", str(corpus), "--db-url", db_url, "--split-seed", str(SPLIT_SEED)]
    assert _export(output, *args) == 0
    _, notes = _csv(output / "notas.csv")
    assert {r["source"] for r in notes} == {"primus", "cadenza"}


def test_a_joined_corpus_does_not_duplicate_the_database_sessions(
    db_url: str, exported: Path, tmp_path: Path
) -> None:
    # El corpus de build-dataset ya trae las sesiones de Cadenza: con la base, no se repiten.
    corpus = write_corpus(tmp_path / "corpus.jsonl", works=1)
    factory = create_session_factory(create_engine_for_url(db_url))
    with session_scope(factory) as db:
        records, _ = session_records(
            session_repository=SqlAlchemySessionRepository(db),
            edit_repository=SqlAlchemyEditEventRepository(db),
            user_repository=SqlAlchemyUserRepository(db),
            split_seed=SPLIT_SEED,
            test_fraction=0.2,
        )
    with corpus.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
    output = tmp_path / "unido"
    args = ["--corpus", str(corpus), "--db-url", db_url, "--split-seed", str(SPLIT_SEED)]
    assert _export(output, *args) == 0
    _, scores = _csv(output / "partituras.csv")
    cadenza = [r["incipit_id"] for r in scores if r["source"] == "cadenza"]
    assert sorted(cadenza) == ["cadenza:s-compas", "cadenza:s-estudio"]
    _, notes = _csv(output / "notas.csv")
    _, alone = _csv(exported / "notas.csv")
    assert sum(r["source"] == "cadenza" for r in notes) == len(alone)
    info = json.loads((output / "run_info.json").read_text(encoding="utf-8"))
    assert info["origins"]["corpus"]["cadenza_records_dropped"] == len(records)
    assert info["origins"]["corpus"]["file"] == "corpus.jsonl"


def test_corpus_tables_keeps_the_source_of_a_joined_corpus() -> None:
    record = {
        "record": "event",
        "source": "cadenza",
        "session_id": "s1",
        "incipit_id": "cadenza:s1",
        "split": "train",
        "verified": True,
        "aligned": True,
        "anchor": {"part": 0, "staff": 0, "measure": 1, "voice": 0, "event_index": 0},
        "read": {"kind": "note", "pitch": "C4", "duration_beats": "1"},
        "correction": None,
        "context": {},
    }
    tables = corpus_tables([record])
    assert tables["notas"][0]["source"] == "cadenza"
    assert tables["notas"][0]["session_id"] == "s1"


def test_the_export_fails_clearly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CADENZA_DATABASE_URL", raising=False)
    with pytest.raises(SystemExit):
        main(["export-tables"])  # --output-dir es obligatorio
    assert _export(tmp_path / "a") == 1  # sin base ni corpus
    assert _export(tmp_path / "b", "--corpus", str(tmp_path / "no.jsonl")) == 1
    url = f"sqlite:///{(tmp_path / 'vacia.db').as_posix()}"
    create_schema(create_engine_for_url(url))
    assert _export(tmp_path / "c", "--db-url", url) == 1  # falta --split-seed


def test_the_export_writes_only_in_the_output_dir(db_url: str, tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[3]
    results = repo / "results"
    before = sorted(results.rglob("*")) if results.exists() else []
    output = tmp_path / "solo-aqui"
    assert _export(output, "--db-url", db_url, "--split-seed", str(SPLIT_SEED)) == 0
    after = sorted(results.rglob("*")) if results.exists() else []
    assert before == after
    assert {p.parent for p in output.rglob("*")} == {output}
