"""Tablas planas para analizar los errores de HOMR con herramientas externas (`ml export-tables`).

El análisis no se hace en la plataforma: estas tablas se escriben como CSV (una por tabla) y
se leen con pandas, R o una hoja de cálculo. El diccionario de cada columna está en
`docs/experimentos/diccionario_tablas.md`.

Las filas de `notas`, `faltantes`, `clave_armadura` y `sugerencias` son los registros del
corpus de correcciones (`build_correction_records`, `session_records`) aplanados, sin
recalcularlos: cada fila es exactamente lo que usa el entrenamiento de la capa de sugerencias.
Lo mismo sirve para un corpus JSONL (el de PrIMuS de `exp_12` o el de `build-dataset`), de modo
que las dos fuentes comparten columnas. `partituras`, `compases` y `avisos` necesitan la base:
para un corpus, `partituras` solo trae lo que dicen sus registros y las otras dos van vacías.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from fractions import Fraction
from itertools import zip_longest
from typing import Any, Final

from cadenza.application import has_current_data_consent
from cadenza.domain import Clef, KeySignature, Measure, ScoreIR, TimeSignature, materialize

from .primus import primus_work_id
from .suggestions import session_records

# --- Columnas -----------------------------------------------------------------------------------

_KEY: Final[tuple[str, ...]] = ("source", "incipit_id", "session_id", "work_id", "split")
_ANCHOR: Final[tuple[str, ...]] = ("part", "staff", "measure", "voice", "event_index")
_CONTEXT: Final[tuple[str, ...]] = (
    "ctx_clef",
    "ctx_key_fifths",
    "ctx_time_signature",
    "ctx_measure_index",
    "ctx_measures_in_staff",
    "ctx_events_in_voice",
    "ctx_measure_beats_read",
    "ctx_measure_beats_read_dec",
    "ctx_measure_capacity_beats",
    "ctx_measure_capacity_beats_dec",
    "ctx_measure_balance_beats",
    "ctx_measure_balance_beats_dec",
    "ctx_onset_beats",
    "ctx_onset_beats_dec",
    "ctx_accidental",
    "ctx_key_accidental",
    "ctx_accidental_vs_key",
    "ctx_previous_accidental_same_step",
    "prev_kind",
    "prev_pitch",
    "prev_duration_beats",
    "prev_duration_beats_dec",
    "next_kind",
    "next_pitch",
    "next_duration_beats",
    "next_duration_beats_dec",
)

_STRIP: Final[tuple[str, ...]] = ("sistema", "recorte")
"""La tira de la foto del compás (`ml export-tables --recortes`, #414); vacías sin ella."""

TABLES: Final[dict[str, tuple[str, ...]]] = {
    "partituras": (
        *_KEY,
        "participante",
        "rol",
        "origen",
        "condition",
        "test_score_id",
        "status",
        "omr_engine",
        "model_version",
        "rules_version",
        "source_image_hash",
        "suggestions_version",
        "partes",
        "pentagramas",
        "compases",
        "eventos_leidos",
        "eventos_finales",
        "ediciones_log",
        "correcciones_netas",
        "compases_con_indicacion_corregida",
        "verified",
        "versiones_capa",
        "permiso_datos",
        "created_at",
    ),
    "notas": (
        *_KEY,
        "verified",
        "aligned",
        *_ANCHOR,
        "read_kind",
        "read_pitch",
        "read_duration_beats",
        "read_duration_beats_dec",
        "read_tie",
        "read_is_chord",
        "read_hidden",
        "resultado",
        "ops",
        "fix_pitch",
        "fix_accidental_before",
        "fix_accidental_after",
        "fix_duration_beats",
        "fix_duration_beats_dec",
        *_CONTEXT,
        *_STRIP,
    ),
    "faltantes": (
        *_KEY,
        "verified",
        *_ANCHOR,
        "ins_kind",
        "ins_pitch",
        "ins_duration_beats",
        "ins_duration_beats_dec",
        "ins_tie",
        "ins_is_chord",
        "ins_hidden",
        *_CONTEXT,
        *_STRIP,
    ),
    "clave_armadura": (
        *_KEY,
        "verified",
        "part",
        "staff",
        "measure",
        "read_clef",
        "read_key_fifths",
        "ops",
        "fix_clef",
        "fix_key_fifths",
    ),
    "compases": (
        *_KEY,
        "part",
        "staff",
        "measure",
        "measure_index",
        "time_read",
        "time_final",
        "clef_read",
        "clef_final",
        "key_fifths_read",
        "key_fifths_final",
        "eventos_leidos",
        "eventos_finales",
        "notas_corregidas",
        "notas_borradas",
        "faltantes",
        "clave_corregida",
        "armadura_corregida",
        "indicacion_corregida",
        "correcciones_netas",
        "avisos_iniciales",
        "avisos_vigentes",
        "avisos_descartados",
        *_STRIP,
    ),
    "sugerencias": (
        *_KEY,
        "condition",
        "suggestion_id",
        "response",
        "es_heredada",
        "inherited_from",
        "responded_by",
        "responded_at",
        "at_seq",
        "rank",
        "op",
        *_ANCHOR,
        "after_json",
        "confidence",
        "confidence_level",
        "suggestion_source",
        "model_version",
        "linked_to_finding",
        "finding_rule_id",
        "applied_seq",
    ),
    "avisos": (
        *_KEY,
        "finding_id",
        "at_seq",
        "es_inicial",
        "es_vigente",
        "rule_id",
        "severity",
        *_ANCHOR,
        "status",
        "dismissal_reason",
        "compas_con_correccion",
    ),
}

Row = dict[str, Any]


# --- Valores ------------------------------------------------------------------------------------


def decimal(value: object) -> float | None:
    """Una fracción en texto («1/2») como decimal redondeado a seis cifras."""
    if value is None or value == "":
        return None
    return round(float(Fraction(str(value))), 6)


def _beats(row: Row, column: str, value: object) -> None:
    """Pone la fracción tal cual y, al lado, su decimal (`<columna>_dec`)."""
    row[column] = value
    row[f"{column}_dec"] = decimal(value)


def _clef_name(clef: Clef | Mapping[str, Any] | None) -> str | None:
    """«G2», «F4», «G2-1»: el mismo nombre que el contexto del corpus."""
    if clef is None:
        return None
    data = clef.to_primitive() if isinstance(clef, Clef) else clef
    change = int(data.get("octave_change") or 0)
    return f"{data['sign']}{data['line']}{f'{change:+d}' if change else ''}"


def _ops(correction: Mapping[str, Any] | None) -> str | None:
    if not correction:
        return None
    return "+".join(correction.get("ops") or ())


def _anchor_columns(row: Row, anchor: Mapping[str, Any] | None) -> None:
    anchor = anchor or {}
    for name in _ANCHOR:
        row[name] = anchor.get(name)


def _context_columns(row: Row, context: Mapping[str, Any] | None) -> None:
    context = context or {}
    for name in (
        "clef",
        "key_fifths",
        "time_signature",
        "measure_index",
        "measures_in_staff",
        "events_in_voice",
        "accidental",
        "key_accidental",
        "accidental_vs_key",
        "previous_accidental_same_step",
    ):
        row[f"ctx_{name}"] = context.get(name)
    for name in (
        "measure_beats_read",
        "measure_capacity_beats",
        "measure_balance_beats",
        "onset_beats",
    ):
        _beats(row, f"ctx_{name}", context.get(name))
    for side in ("prev", "next"):
        neighbour = context.get(side) or {}
        row[f"{side}_kind"] = neighbour.get("kind")
        row[f"{side}_pitch"] = neighbour.get("pitch")
        _beats(row, f"{side}_duration_beats", neighbour.get("duration_beats"))


def _source(record: Mapping[str, Any]) -> str:
    """De dónde sale un registro: las sesiones de Cadenza lo dicen; el corpus de exp_12, no."""
    return str(record.get("source") or "primus")


def _work_of(record: Mapping[str, Any]) -> str | None:
    work = record.get("work_id")
    if work:
        return str(work)
    if _source(record) == "primus":
        return primus_work_id(str(record["incipit_id"]))
    return None


def _key_columns(record: Mapping[str, Any]) -> Row:
    return {
        "source": _source(record),
        "incipit_id": record.get("incipit_id"),
        "session_id": record.get("session_id"),
        "work_id": _work_of(record),
        "split": record.get("split"),
    }


def _outcome(record: Mapping[str, Any]) -> str:
    correction = record.get("correction")
    if not record.get("aligned", True):
        return "sin_alinear"
    if correction is None:
        return "bien"
    if "DeleteEvent" in (correction.get("ops") or ()):
        return "borrada"
    return "corregida"


def _note_row(record: Mapping[str, Any]) -> Row:
    row = {**_key_columns(record), "verified": record.get("verified")}
    row["aligned"] = record.get("aligned")
    _anchor_columns(row, record.get("anchor"))
    read = record.get("read") or {}
    row["read_kind"] = read.get("kind")
    row["read_pitch"] = read.get("pitch")
    _beats(row, "read_duration_beats", read.get("duration_beats"))
    row["read_tie"] = read.get("tie")
    row["read_is_chord"] = read.get("is_chord")
    row["read_hidden"] = read.get("hidden")
    correction = record.get("correction") or {}
    row["resultado"] = _outcome(record)
    row["ops"] = _ops(correction)
    row["fix_pitch"] = correction.get("pitch")
    accidental = correction.get("accidental") or {}
    row["fix_accidental_before"] = accidental.get("before")
    row["fix_accidental_after"] = accidental.get("after")
    _beats(row, "fix_duration_beats", correction.get("duration_beats"))
    _context_columns(row, record.get("context"))
    return row


def _missing_row(record: Mapping[str, Any]) -> Row:
    row = {**_key_columns(record), "verified": record.get("verified")}
    _anchor_columns(row, record.get("anchor"))
    event = (record.get("correction") or {}).get("event") or {}
    row["ins_kind"] = event.get("kind")
    row["ins_pitch"] = event.get("pitch")
    _beats(row, "ins_duration_beats", event.get("duration_beats"))
    row["ins_tie"] = event.get("tie")
    row["ins_is_chord"] = event.get("is_chord")
    row["ins_hidden"] = event.get("hidden")
    _context_columns(row, record.get("context"))
    return row


def _measure_row(record: Mapping[str, Any]) -> Row:
    row = {**_key_columns(record), "verified": record.get("verified")}
    anchor = record.get("anchor") or {}
    for name in ("part", "staff", "measure"):
        row[name] = anchor.get(name)
    read = record.get("read") or {}
    correction = record.get("correction") or {}
    row["read_clef"] = read.get("clef")
    row["read_key_fifths"] = read.get("key_fifths")
    row["ops"] = _ops(correction)
    row["fix_clef"] = _clef_name(correction.get("clef"))
    row["fix_key_fifths"] = correction.get("key_fifths")
    return row


def _suggestion_row(
    record: Mapping[str, Any], persisted: Any = None, rule: str | None = None
) -> Row:
    """Una sugerencia: el registro de `session_records` y, de la base, lo que no lleva."""
    row = {**_key_columns(record), "condition": record.get("condition")}
    suggestion = record.get("suggestion") or {}
    row["suggestion_id"] = None if persisted is None else persisted.id
    row["response"] = record.get("response")
    # Un rechazo heredado repite el de `inherited_from` (ADR-0036 §4): no es otra respuesta.
    row["es_heredada"] = record.get("inherited_from") is not None
    row["inherited_from"] = record.get("inherited_from")
    row["responded_by"] = record.get("responded_by")
    row["responded_at"] = record.get("responded_at")
    row["at_seq"] = suggestion.get("at_seq")
    row["rank"] = suggestion.get("rank")
    row["op"] = suggestion.get("op")
    _anchor_columns(row, suggestion.get("anchor"))
    after = suggestion.get("after")
    row["after_json"] = None if after is None else json.dumps(after, sort_keys=True)
    row["confidence"] = suggestion.get("confidence")
    row["confidence_level"] = None if persisted is None else persisted.confidence_level
    row["suggestion_source"] = suggestion.get("source")
    row["model_version"] = suggestion.get("model_version")
    row["linked_to_finding"] = suggestion.get("linked_to_finding")
    row["finding_rule_id"] = rule
    row["applied_seq"] = suggestion.get("applied_seq")
    return row


def _empty() -> dict[str, list[Row]]:
    return {name: [] for name in TABLES}


def _record_tables(records: Iterable[Mapping[str, Any]]) -> dict[str, list[Row]]:
    """Las tablas que salen de los registros del corpus, sin la base."""
    tables = _empty()
    for record in records:
        kind = record.get("record")
        if kind == "event":
            tables["notas"].append(_note_row(record))
        elif kind == "insertion":
            tables["faltantes"].append(_missing_row(record))
        elif kind == "measure":
            tables["clave_armadura"].append(_measure_row(record))
        elif kind == "suggestion":
            tables["sugerencias"].append(_suggestion_row(record))
    return tables


def _net_ops(record: Mapping[str, Any]) -> int:
    """Las ediciones derivadas de un registro: las de su corrección (ninguna si estaba bien)."""
    if record.get("record") == "suggestion":
        return 0
    return len((record.get("correction") or {}).get("ops") or ())


def _net_corrections(records: Iterable[Mapping[str, Any]]) -> int:
    """Las correcciones netas: las ediciones que `derive_edit_events` deriva de la lectura al
    estado final (cada una está en un registro y solo en uno). Un evento con la altura y la
    figura corregidas cuenta dos; la clave y la armadura de un compás, dos."""
    return sum(_net_ops(record) for record in records)


# --- Un corpus JSONL ----------------------------------------------------------------------------


def corpus_tables(records: Sequence[Mapping[str, Any]]) -> dict[str, list[Row]]:
    """Las tablas de un corpus JSONL. `partituras` tiene una fila por incipit con lo que dicen
    sus registros; `compases` y `avisos` necesitan la base y van vacías."""
    tables = _record_tables(records)
    by_incipit: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        if record.get("record") != "suggestion":
            by_incipit.setdefault(str(record["incipit_id"]), []).append(record)
    for incipit, own in by_incipit.items():
        first = own[0]
        row: Row = dict.fromkeys(TABLES["partituras"])
        row.update(_key_columns(first))
        row["incipit_id"] = incipit
        row["eventos_leidos"] = sum(r.get("record") == "event" for r in own)
        row["correcciones_netas"] = _net_corrections(own)
        row["verified"] = first.get("verified")
        tables["partituras"].append(row)
    return tables


# --- La base de datos ---------------------------------------------------------------------------


def _origin(session: Any, owner: Any) -> str:
    if session.test_score_id:
        return "estudio"
    if owner is not None and owner.self_registered:
        return "registro"
    return "equipo"


def _effective_measures(measures: Sequence[Measure]) -> list[tuple[str | None, str | None, int]]:
    """(indicación, clave, armadura) vigentes en cada compás de un pentagrama."""
    clef: Clef | None = None
    key = KeySignature(fifths=0)
    time: TimeSignature | None = None
    found = []
    for measure in measures:
        clef = measure.clef or clef
        key = measure.key_signature or key
        time = measure.time_signature or time
        found.append((None if time is None else str(time), _clef_name(clef), key.fifths))
    return found


def _staves(score: ScoreIR) -> dict[tuple[int, int], Sequence[Measure]]:
    return {
        (p, s): staff.measures
        for p, part in enumerate(score.parts)
        for s, staff in enumerate(part.staves)
    }


def _measure_rows(
    key: Row,
    raw: ScoreIR,
    final: ScoreIR,
    records: Sequence[Mapping[str, Any]],
    findings: Sequence[Any],
    validated_at_seq: int,
) -> list[Row]:
    """Una fila por compás, comparando la lectura y el estado final compás a compás.

    Desde la vista no se insertan ni se borran compases (no hay `EditOp` para eso), así que el
    compás N leído es el compás N final; si no lo fuera, el que falte va con sus columnas vacías.
    """
    counts: dict[tuple[Any, Any, Any], Counter[str]] = {}
    for record in records:
        anchor = record.get("anchor") or {}
        where = (anchor.get("part"), anchor.get("staff"), anchor.get("measure"))
        kind = record.get("record")
        correction = record.get("correction")
        tally = counts.setdefault(where, Counter())
        tally["netas"] += _net_ops(record)
        if kind == "insertion":
            tally["faltantes"] += 1
        elif kind == "measure":
            ops = (correction.get("ops") or ()) if correction else ()
            tally["clave_corregida"] += int("SetClef" in ops)
            tally["armadura_corregida"] += int("SetKey" in ops)
        elif kind == "event" and correction is not None:
            deleted = "DeleteEvent" in (correction.get("ops") or ())
            tally["notas_borradas" if deleted else "notas_corregidas"] += 1
    for finding in findings:
        anchor = finding.anchor
        tally = counts.setdefault(
            (anchor.get("part"), anchor.get("staff"), anchor.get("measure")), Counter()
        )
        tally["avisos_iniciales"] += int(finding.at_seq == 0)
        if finding.at_seq == validated_at_seq:
            tally["avisos_vigentes"] += 1
            tally["avisos_descartados"] += int(finding.status == "dismissed")

    rows: list[Row] = []
    raw_staves, final_staves = _staves(raw), _staves(final)
    for (p, s), read_measures in raw_staves.items():
        final_measures = final_staves.get((p, s), ())
        read_eff = _effective_measures(read_measures)
        final_eff = _effective_measures(final_measures)
        pairs = zip_longest(read_measures, final_measures)
        for index, (read_m, final_m) in enumerate(pairs):
            present = read_m if read_m is not None else final_m
            assert present is not None  # zip_longest nunca da los dos vacíos
            number = present.number
            tally = counts.get((p, s, number), Counter())
            r_time, r_clef, r_key = read_eff[index] if read_m else (None, None, None)
            f_time, f_clef, f_key = final_eff[index] if final_m else (None, None, None)
            net = tally["netas"]
            rows.append(
                {
                    **key,
                    "part": p,
                    "staff": s,
                    "measure": number,
                    "measure_index": index,
                    "time_read": r_time,
                    "time_final": f_time,
                    "clef_read": r_clef,
                    "clef_final": f_clef,
                    "key_fifths_read": r_key,
                    "key_fifths_final": f_key,
                    "eventos_leidos": None if read_m is None else len(read_m.events),
                    "eventos_finales": None if final_m is None else len(final_m.events),
                    "notas_corregidas": tally["notas_corregidas"],
                    "notas_borradas": tally["notas_borradas"],
                    "faltantes": tally["faltantes"],
                    "clave_corregida": tally["clave_corregida"] > 0,
                    "armadura_corregida": tally["armadura_corregida"] > 0,
                    "indicacion_corregida": r_time != f_time,
                    "correcciones_netas": net,
                    "avisos_iniciales": tally["avisos_iniciales"],
                    "avisos_vigentes": tally["avisos_vigentes"],
                    "avisos_descartados": tally["avisos_descartados"],
                }
            )
    return rows


def _corrected_measures(rows: Iterable[Row]) -> set[tuple[int, int, int]]:
    return {
        (r["part"], r["staff"], r["measure"])
        for r in rows
        if r["correcciones_netas"] > 0 or r["indicacion_corregida"]
    }


def _finding_row(key: Row, finding: Any, validated_at_seq: int, corrected: set[Any]) -> Row:
    anchor = finding.anchor
    row = {**key, "finding_id": finding.id, "at_seq": finding.at_seq}
    row["es_inicial"] = finding.at_seq == 0
    row["es_vigente"] = finding.at_seq == validated_at_seq
    row["rule_id"] = finding.rule_id
    row["severity"] = finding.severity
    _anchor_columns(row, anchor)
    row["status"] = finding.status
    row["dismissal_reason"] = finding.dismissal_reason
    # Por compás, no por evento: el event_index cambia entre estados.
    row["compas_con_correccion"] = (
        anchor.get("part"),
        anchor.get("staff"),
        anchor.get("measure"),
    ) in corrected
    return row


def _events(score: ScoreIR) -> int:
    return sum(
        len(measure.events)
        for part in score.parts
        for staff in part.staves
        for measure in staff.measures
    )


def database_tables(
    *,
    session_repository: Any,
    edit_repository: Any,
    user_repository: Any,
    split_seed: int,
    test_fraction: float,
    include_self_registered: bool = False,
    include_unfinished: bool = False,
) -> tuple[dict[str, list[Row]], dict[str, str]]:
    """Las tablas de las sesiones de la base, y las que se dejan fuera con su motivo.

    Las sesiones son las de `session_records` (por defecto, finalizadas y sin cuentas del
    registro público); las demás van a `left_out` con su motivo.
    """
    records, left_out = session_records(
        session_repository=session_repository,
        edit_repository=edit_repository,
        user_repository=user_repository,
        split_seed=split_seed,
        test_fraction=test_fraction,
        include_self_registered=include_self_registered,
        include_unfinished=include_unfinished,
    )
    by_session: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_session.setdefault(str(record["session_id"]), []).append(record)

    tables = _empty()
    for session in session_repository.list():
        if session.id in left_out:
            continue
        if session.status != "finalized" and not include_unfinished:
            left_out[session.id] = f"sin terminar (status {session.status})"
            continue
        own = by_session.get(session.id, [])
        owner = user_repository.get(session.owner_id)
        corpus = [r for r in own if r["record"] != "suggestion"]
        suggestions = [r for r in own if r["record"] == "suggestion"]
        key = _key_columns(own[0]) if own else {"source": "cadenza", "session_id": session.id}
        key = {name: key.get(name) for name in _KEY}
        key["incipit_id"] = f"cadenza:{session.id}"

        raw = ScoreIR.from_primitive(session.document["score"])
        edits = edit_repository.list_events(session.id)
        final = materialize(raw, edits) if edits else raw
        findings = session_repository.list_findings(
            session.id, latest_only=False, include_dismissed=True
        )
        measures = _measure_rows(key, raw, final, corpus, findings, session.validated_at_seq)
        corrected = _corrected_measures(measures)

        record_tables = _record_tables(corpus)
        for name in ("notas", "faltantes", "clave_armadura"):
            tables[name].extend(record_tables[name])
        tables["compases"].extend(measures)
        tables["avisos"].extend(
            _finding_row(key, f, session.validated_at_seq, corrected) for f in findings
        )

        # session_records da las sugerencias en el orden de list_suggestions: se emparejan
        # con las guardadas para añadir lo que el registro no lleva.
        persisted = session_repository.list_suggestions(session.id)
        rules = {f.id: f.rule_id for f in findings}
        for record, stored in zip(suggestions, persisted, strict=True):
            rule = None if stored.finding_id is None else rules.get(stored.finding_id)
            tables["sugerencias"].append(_suggestion_row(record, stored, rule))
        layer_versions = sorted(
            {s.model_version for s in persisted if s.source == "learned" and s.model_version}
        )

        provenance = session.document.get("provenance") or {}
        staves = _staves(raw)
        first = corpus[0] if corpus else {}
        tables["partituras"].append(
            {
                **key,
                "participante": None if owner is None else owner.username,
                "rol": None if owner is None else str(owner.role),
                "origen": _origin(session, owner),
                "condition": session.condition,
                "test_score_id": session.test_score_id,
                "status": session.status,
                "omr_engine": provenance.get("omr_engine") or session.omr_engine,
                "model_version": provenance.get("model_version") or session.model_version,
                "rules_version": provenance.get("rules_version"),
                "source_image_hash": provenance.get("source_image_hash"),
                "suggestions_version": provenance.get("suggestions_version"),
                "partes": len(raw.parts),
                "pentagramas": len(staves),
                "compases": sum(len(m) for m in staves.values()),
                "eventos_leidos": _events(raw),
                "eventos_finales": _events(final),
                "ediciones_log": len(edits),
                "correcciones_netas": _net_corrections(corpus),
                "compases_con_indicacion_corregida": sum(
                    1 for r in measures if r["indicacion_corregida"]
                ),
                "verified": first.get("verified"),
                "versiones_capa": "+".join(layer_versions) or None,
                "permiso_datos": None if owner is None else has_current_data_consent(owner),
                "created_at": (
                    None if session.created_at is None else session.created_at.isoformat()
                ),
            }
        )
    return tables, left_out


# --- Escritura ----------------------------------------------------------------------------------


def cell(value: object) -> str:
    """Un valor como texto de CSV: vacío para None, `true`/`false` y punto decimal."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def merge_tables(*parts: Mapping[str, list[Row]]) -> dict[str, list[Row]]:
    merged = _empty()
    for part in parts:
        for name in TABLES:
            merged[name].extend(part.get(name, ()))
    return merged
