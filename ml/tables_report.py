"""El informe visual de los errores de HOMR (`ml export-tables --informe`, #415, ADR-0069).

Lee los CSV de una carpeta de `ml export-tables` y escribe en ella `informe.html`: una página sin
red ni dependencias, con los datos agregados dentro y los recortes de las fotos por su ruta
relativa (#414). Lo que dice sale de los CSV ya escritos, así que coincide con ellos.

Además de las cifras, cada barra o celda lleva a sus ejemplos: la tira de la foto del compás, lo
que leyó HOMR y lo correcto. Una opción no cuenta las correcciones de altura que solo reordenan
las notas de un acorde (mismas alturas en otro orden), que aparecen al comparar con una partitura
de referencia (la de PrIMuS, la del banco) y no en las correcciones de una persona.
"""

from __future__ import annotations

import csv
import html
import json
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

Row = dict[str, str]

REPORT_NAME = "informe.html"
TEMPLATE = Path(__file__).with_name("informe_tablas.html")
MAX_EXAMPLES = 12
"""Ejemplos por barra o celda."""
MIN_GROUP = 30
"""Notas que necesita un grupo de contexto para salir en «dónde se equivoca más»."""
MIN_SCORE_EVENTS = 10
"""Notas leídas que necesita una partitura para salir en la tabla de las que más se corrigen."""

STEPS = "CDEFGAB"
DURATIONS = {
    "0": "adorno",
    "1/16": "semifusa",
    "1/8": "fusa",
    "1/4": "semicorchea",
    "3/8": "semicorchea con puntillo",
    "1/2": "corchea",
    "3/4": "corchea con puntillo",
    "1": "negra",
    "3/2": "negra con puntillo",
    "2": "blanca",
    "3": "blanca con puntillo",
    "4": "redonda",
}
VS_KEY = {"in_key": "según la armadura", "against_key": "contra la armadura"}


def _read(folder: Path, name: str) -> list[Row]:
    with (folder / f"{name}.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def diatonic(pitch: str) -> int | None:
    """Posición diatónica de una altura como `Bb3` o `F#4`, sin la alteración."""
    if not pitch or pitch[0] not in STEPS:
        return None
    try:
        octave = int(pitch[1:].lstrip("#b-"))
    except ValueError:
        return None
    return octave * 7 + STEPS.index(pitch[0])


def _place(row: Row) -> tuple[str, ...]:
    return (row["incipit_id"], row["part"], row["staff"], row["measure"], row["voice"])


def reordered_chords(notas: list[Row]) -> set[int]:
    """Las filas de `notas` corregidas que solo cambian de sitio dentro de su acorde.

    Un acorde lo abre una nota sin `read_is_chord` y lo siguen las de `read_is_chord` del mismo
    pentagrama, compás y voz. Cuenta si todas sus notas quedaron bien o con solo la altura
    corregida, y las alturas leídas y las corregidas son las mismas en otro orden.
    """

    found: set[int] = set()

    def close(group: list[int]) -> None:
        rows = [notas[i] for i in group]
        if len(rows) < 2 or not any(r["resultado"] == "corregida" for r in rows):
            return
        if any(
            r["resultado"] not in ("bien", "corregida") or r["ops"] not in ("", "SetPitch")
            for r in rows
        ):
            return
        before = sorted(r["read_pitch"] for r in rows)
        after = sorted(r["fix_pitch"] or r["read_pitch"] for r in rows)
        if before == after:
            found.update(i for i in group if notas[i]["resultado"] == "corregida")

    group: list[int] = []
    for index, row in enumerate(notas):
        if group and row["read_is_chord"] == "true" and _place(notas[group[0]]) == _place(row):
            group.append(index)
            continue
        if group:
            close(group)
        group = [index]
    if group:
        close(group)
    return found


def _score_label(row: Row) -> str:
    """Cómo se llama una partitura en el informe. En Cadenza, la página del banco y la sesión:
    varias sesiones de la misma página no se confunden."""
    if row["source"] == "cadenza":
        if row["test_score_id"]:
            return f"{row['test_score_id']} · {row['session_id']}"
        return row["session_id"] or row["incipit_id"]
    return row["incipit_id"]


def _event(kind: str, pitch: str, beats: str) -> str:
    if kind == "rest":
        return f"silencio {beats}"
    return f"{pitch} {beats}".strip()


def _example(row: Row, label: str, *, missing: bool = False) -> dict[str, Any]:
    """Un ejemplo: dónde está, su foto y qué leyó HOMR frente a lo correcto."""
    if missing:
        read = "—"
        fixed = _event(row["ins_kind"], row["ins_pitch"], row["ins_duration_beats"])
    else:
        read = _event(row["read_kind"], row["read_pitch"], row["read_duration_beats"])
        if row["resultado"] == "borrada":
            fixed = "—"
        else:
            fixed = _event(
                row["read_kind"],
                row["fix_pitch"] or row["read_pitch"],
                row["fix_duration_beats"] or row["read_duration_beats"],
            )
    return {
        "score": label,
        "measure": row["measure"],
        "staff": f"{row['part']}-{row['staff']}",
        "img": row.get("recorte", ""),
        "read": read,
        "fix": fixed,
    }


def _key_example(row: Row, label: str, img: str) -> dict[str, Any]:
    """Un ejemplo de `clave_armadura`: la clave y la armadura leídas frente a las correctas."""

    def describe(clef: str, fifths: str) -> str:
        parts = [f"clave {clef}" if clef else "", f"armadura {fifths}" if fifths else ""]
        return ", ".join(p for p in parts if p) or "—"

    return {
        "score": label,
        "measure": row["measure"],
        "staff": f"{row['part']}-{row['staff']}",
        "img": img,
        "read": describe(row["read_clef"], row["read_key_fifths"]),
        "fix": describe(
            row["fix_clef"] or row["read_clef"], row["fix_key_fifths"] or row["read_key_fifths"]
        ),
    }


def _ops(row: Row) -> list[str]:
    return [op for op in row["ops"].split("+") if op]


class _Examples:
    """Hasta `MAX_EXAMPLES` ejemplos por categoría, sin repetir el mismo ejemplo."""

    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []
        self.index: dict[tuple[str, ...], int] = {}
        self.by_key: dict[str, list[int]] = defaultdict(list)

    def add(self, key: str, identity: tuple[str, ...], build: Callable[[], dict[str, Any]]) -> None:
        bucket = self.by_key[key]
        if len(bucket) >= MAX_EXAMPLES:
            return
        position = self.index.get(identity)
        if position is None:
            position = len(self.items)
            self.items.append(build())
            self.index[identity] = position
        if position not in bucket:
            bucket.append(position)


def _rates(
    rows: Iterable[tuple[int, Row]],
    column: str,
    wrong: Callable[[int, Row], bool],
    label: Callable[[str], str],
    examples: _Examples,
    labels: dict[str, str],
    prefix: str,
) -> list[dict[str, Any]]:
    totals: Counter[str] = Counter()
    errors: Counter[str] = Counter()
    for index, row in rows:
        if row["read_kind"] != "note":
            continue
        value = row[column] or "—"
        totals[value] += 1
        if wrong(index, row):
            errors[value] += 1
            examples.add(
                f"{prefix}:{value}",
                (str(index),),
                lambda r=row: _example(r, labels.get(r["incipit_id"], r["incipit_id"])),
            )
    rates = [
        {
            "key": f"{prefix}:{value}",
            "label": label(value),
            "n": n,
            "wrong": errors[value],
            "rate": errors[value] / n,
        }
        for value, n in totals.items()
        if n >= MIN_GROUP
    ]
    return sorted(rates, key=lambda r: (-float(r["rate"]), str(r["label"])))


def aggregate(
    tables: dict[str, list[Row]], source: str | None, skip_reordered: bool, reordered: set[int]
) -> dict[str, Any]:
    """Las cifras del informe para un origen (o todos) y con o sin los acordes reordenados."""

    def keep(row: Row) -> bool:
        return source is None or row["source"] == source

    notas = [(i, r) for i, r in enumerate(tables["notas"]) if keep(r)]
    faltantes = [r for r in tables["faltantes"] if keep(r)]
    claves = [r for r in tables["clave_armadura"] if keep(r)]
    partituras = [r for r in tables["partituras"] if keep(r)]
    labels = {r["incipit_id"]: _score_label(r) for r in partituras}
    photos = {
        (r["incipit_id"], r["part"], r["staff"], r["measure"]): r.get("recorte", "")
        for _, r in notas
        if r.get("recorte")
    }

    def result(index: int, row: Row) -> str:
        if skip_reordered and index in reordered:
            return "bien"
        return row["resultado"]

    def wrong(index: int, row: Row) -> bool:
        """Con alguna corrección (una nota sin alinear no la tiene: no se sabe cuál es)."""
        return result(index, row) in ("corregida", "borrada")

    examples = _Examples()
    outcome = Counter(result(i, r) for i, r in notas)
    ops: Counter[str] = Counter()
    steps: Counter[int] = Counter()
    durations: Counter[tuple[str, str]] = Counter()
    for index, row in notas:
        if skip_reordered and index in reordered:
            continue
        label = labels.get(row["incipit_id"], row["incipit_id"])
        for op in filter(None, row["ops"].split("+")):
            ops[op] += 1
            examples.add(f"op:{op}", (str(index),), lambda r=row, name=label: _example(r, name))
        if "SetPitch" in row["ops"]:
            a, b = diatonic(row["read_pitch"]), diatonic(row["fix_pitch"])
            if a is not None and b is not None:
                step = max(-8, min(8, b - a))
                steps[step] += 1
                examples.add(
                    f"step:{step}", (str(index),), lambda r=row, name=label: _example(r, name)
                )
        if "SetDuration" in row["ops"] and row["fix_duration_beats"]:
            pair = (row["read_duration_beats"], row["fix_duration_beats"])
            durations[pair] += 1
            examples.add(
                f"dur:{pair[0]}>{pair[1]}",
                (str(index),),
                lambda r=row, name=label: _example(r, name),
            )
    if faltantes:
        ops["InsertEvent"] = len(faltantes)
    for number, row in enumerate(faltantes):
        label = labels.get(row["incipit_id"], row["incipit_id"])
        examples.add(
            "op:InsertEvent",
            ("faltante", str(number), row["incipit_id"]),
            lambda r=row, name=label: _example(r, name, missing=True),
        )
    for number, row in enumerate(claves):
        label = labels.get(row["incipit_id"], row["incipit_id"])
        img = photos.get((row["incipit_id"], row["part"], row["staff"], row["measure"]), "")
        for op in _ops(row):
            ops[op] += 1
            examples.add(
                f"op:{op}",
                ("clave", str(number), row["incipit_id"]),
                lambda r=row, name=label, i=img: _key_example(r, name, i),
            )

    by_vs_key = _rates(
        notas, "ctx_accidental_vs_key", wrong, lambda v: VS_KEY.get(v, v), examples, labels, "vs"
    )
    by_clef = _rates(notas, "ctx_clef", wrong, lambda v: v, examples, labels, "clef")
    by_duration = _rates(
        notas,
        "read_duration_beats",
        wrong,
        lambda v: f"{DURATIONS.get(v, v)} ({v})",
        examples,
        labels,
        "readdur",
    )

    # Las correcciones de cada partitura, como `partituras.correcciones_netas`: una por operación
    # (una nota con la altura y la figura corregidas cuenta dos), las notas que faltaban y la
    # clave y la armadura.
    per_score: dict[str, list[int]] = {r["incipit_id"]: [0, 0] for r in partituras}
    for index, row in notas:
        counts = per_score.setdefault(row["incipit_id"], [0, 0])
        counts[0] += 1
        if skip_reordered and index in reordered:
            continue
        counts[1] += len(_ops(row))
        if wrong(index, row):
            examples.add(
                f"score:{row['incipit_id']}",
                (str(index),),
                lambda r=row: _example(r, labels.get(r["incipit_id"], r["incipit_id"])),
            )
    for number, row in enumerate(faltantes):
        per_score.setdefault(row["incipit_id"], [0, 0])[1] += 1
        examples.add(
            f"score:{row['incipit_id']}",
            ("faltante", str(number), row["incipit_id"]),
            lambda r=row: _example(r, labels.get(r["incipit_id"], r["incipit_id"]), missing=True),
        )
    for row in claves:
        per_score.setdefault(row["incipit_id"], [0, 0])[1] += len(_ops(row))
    sources = {r["incipit_id"]: r["source"] for r in partituras}
    top = sorted(
        (
            {
                "key": f"score:{incipit}",
                "label": labels.get(incipit, incipit),
                "source": sources.get(incipit, ""),
                "read": read,
                "fixes": fixes,
                "rate": fixes / read,
            }
            for incipit, (read, fixes) in per_score.items()
            if read >= MIN_SCORE_EVENTS
        ),
        key=lambda r: (-float(r["rate"]), -int(r["fixes"]), str(r["label"])),
    )[:15]

    return {
        "scores": len(partituras),
        "clean_scores": sum(1 for _, fixes in per_score.values() if fixes == 0),
        "read": len(notas),
        "outcome": dict(outcome),
        "missing": len(faltantes),
        "reordered": sum(1 for i, _ in notas if i in reordered),
        "ops": dict(ops),
        "steps": {str(k): v for k, v in sorted(steps.items())},
        "durations": [{"read": a, "fix": b, "n": n} for (a, b), n in durations.most_common()],
        "by_vs_key": by_vs_key,
        "by_clef": by_clef,
        "by_duration": by_duration,
        "top": top,
        "examples": examples.items,
        "example_keys": dict(examples.by_key),
    }


def report_data(folder: Path) -> dict[str, Any]:
    """Todas las variantes del informe: por origen y con o sin los acordes reordenados."""
    tables = {
        name: _read(folder, name) for name in ("partituras", "notas", "faltantes", "clave_armadura")
    }
    reordered = reordered_chords(tables["notas"])
    sources = sorted({r["source"] for r in tables["partituras"]})
    variants = {
        f"{source or 'todas'}|{int(skip)}": aggregate(tables, source, skip, reordered)
        for source in (None, *sources)
        for skip in (False, True)
    }
    return {"sources": sources, "variants": variants}


def write_report(folder: Path) -> Path:
    """Escribe `informe.html` en la carpeta de la exportación y devuelve su ruta."""
    data = report_data(folder)
    info = json.loads((folder / "run_info.json").read_text(encoding="utf-8"))
    # Ningún `<` en el script: ni `</script>` ni `<!--` pueden cortarlo. Los datos van los
    # últimos, para que un `__DATE__` dentro de ellos no se sustituya.
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    page = (
        TEMPLATE.read_text(encoding="utf-8")
        .replace("__COMMIT__", html.escape(str(info.get("commit") or "?")[:7]))
        .replace("__DATE__", html.escape(str(info.get("generated_at", ""))[:16].replace("T", " ")))
        .replace("__DATA__", payload)
    )
    target = folder / REPORT_NAME
    target.write_text(page, encoding="utf-8")
    return target
