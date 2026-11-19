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

import base64
import csv
import html
import json
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from fractions import Fraction
from functools import partial
from pathlib import Path
from typing import Any

Row = dict[str, str]

REPORT_NAME = "informe.html"
TEMPLATE = Path(__file__).with_name("informe_tablas.html")
FONTS_DIR = Path(__file__).with_name("informe_fuentes")
FONTS = (
    ("Pixelify Sans", 700, "pixelify-sans-latin-700-normal.woff2"),
    ("Silkscreen", 400, "silkscreen-latin-400-normal.woff2"),
    ("Silkscreen", 700, "silkscreen-latin-700-normal.woff2"),
    ("Hanken Grotesk", 400, "hanken-grotesk-latin-400-normal.woff2"),
    ("Hanken Grotesk", 500, "hanken-grotesk-latin-500-normal.woff2"),
)
"""Las tipografías de Cadenza (`DESIGN.md`, OFL 1.1, de `@fontsource`), dentro de la página: el
informe se abre sin red (#418)."""
MAX_EXAMPLES = 12
"""Ejemplos por barra o celda."""
MIN_GROUP = 30
"""Notas que necesita un grupo de contexto para salir en «dónde se equivoca más»."""

STEPS = "CDEFGAB"
FIGURES = {
    Fraction(16): "longa",
    Fraction(8): "cuadrada",
    Fraction(4): "redonda",
    Fraction(2): "blanca",
    Fraction(1): "negra",
    Fraction(1, 2): "corchea",
    Fraction(1, 4): "semicorchea",
    Fraction(1, 8): "fusa",
    Fraction(1, 16): "semifusa",
    Fraction(1, 32): "garrapatea",
}
"""Las figuras por su duración en negras, de la más larga a la más corta."""
# Sin el seisillo: dura lo mismo que el tresillo de la figura siguiente (1/6 de negra es una
# semicorchea de tresillo), así que nunca se elegiría.
TUPLETS = {3: (2, "tresillo"), 5: (4, "quintillo"), 7: (4, "septillo")}
"""Grupos irregulares: notas del grupo → (notas normales que ocupan, nombre)."""
DOTS = ((0, Fraction(1)), (1, Fraction(3, 2)), (2, Fraction(7, 4)))
Part = tuple[Fraction, int, int]
"""Una figura escrita: su figura base, sus puntillos y su grupo irregular (0 si no lo tiene)."""
VS_KEY = {"in_key": "según la armadura", "against_key": "contra la armadura"}
CLEF_SIGNS = {"G": "sol", "F": "fa", "C": "do"}
USUAL_CLEF_LINE = {"G": "2", "F": "4"}
"""La clave de sol en 2.ª y la de fa en 4.ª se nombran sin la línea, como se dice siempre."""
REAL_TESTS = "pruebas"
"""El único grupo que se separa (#418): las sesiones de las pruebas reales de Cadenza, las de las
cuentas del registro público (`partituras.origen = registro`)."""
_TOKEN_BEATS = re.compile(r":([^:\s~]+)~?$")


def _value(beats: str) -> Fraction | None:
    try:
        value = Fraction(beats)
    except (ValueError, ZeroDivisionError):
        return None
    return value if value >= 0 else None


def _parts(value: Fraction) -> list[Part] | None:
    """Cómo se escribe una duración positiva: una figura (con puntillos o en un grupo irregular)
    o, si no hay ninguna, las figuras ligadas que la suman. `None` si no se puede escribir."""
    for base in FIGURES:
        for dots, factor in DOTS:
            if value == base * factor:
                return [(base, dots, 0)]
    for actual, (normal, _) in TUPLETS.items():
        plain = value * Fraction(actual, normal)
        if plain in FIGURES:
            return [(plain, 0, actual)]
    parts: list[Part] = []
    rest = value
    for base in FIGURES:
        while rest >= base and len(parts) < 4:
            parts.append((base, 0, 0))
            rest -= base
    return parts if parts and rest == 0 else None


def _part_name(part: Part) -> str:
    base, dots, tuplet = part
    name = FIGURES[base]
    if dots:
        name += " con puntillo" if dots == 1 else " con doble puntillo"
    if tuplet:
        name += f" de {TUPLETS[tuplet][1]}"
    return name


def figure_name(beats: str) -> str:
    """La figura musical de una duración en negras (`1/2` → «corchea»), para no enseñar fracciones
    (#418). Una duración que no es una figura sola se escribe como las figuras ligadas que la
    suman («blanca + corchea»)."""
    value = _value(beats)
    if value is None:
        return "figura desconocida"
    if value == 0:
        return "adorno"
    parts = _parts(value)
    if parts is None:
        return "figura irregular"
    return " + ".join(_part_name(part) for part in parts)


def figure_symbol(beats: str) -> list[dict[str, Any]]:
    """Lo que necesita la página para dibujar el símbolo de la figura (#418): una entrada por
    figura escrita, con su nombre base, sus puntillos, su grupo irregular y si es de adorno.
    Vacío si no se puede escribir con figuras."""
    value = _value(beats)
    if value is None:
        return []
    if value == 0:
        return [{"figure": "corchea", "dots": 0, "tuplet": 0, "grace": True}]
    return [
        {"figure": FIGURES[base], "dots": dots, "tuplet": tuplet, "grace": False}
        for base, dots, tuplet in _parts(value) or []
    ]


def clef_name(clef: str) -> str:
    """La clave en lenguaje musical (#418): `G2` → «clave de sol», `F3` → «clave de fa en 3.ª»,
    `C1` → «clave de do en 1.ª», `G2-1` → «clave de sol (octava baja)»."""
    match = re.fullmatch(r"([GFC])(\d)([+-]\d)?", clef)
    if match is None:
        return f"clave {clef}" if clef else "sin clave"
    sign, line, octave = match.groups()
    name = f"clave de {CLEF_SIGNS[sign]}"
    if USUAL_CLEF_LINE.get(sign) != line:
        name += f" en {line}.ª"
    if octave:
        shift = int(octave)
        times = "octava" if abs(shift) == 1 else f"{abs(shift)} octavas"
        name += f" ({times} {'alta' if shift > 0 else 'baja'})"
    return name


def _read(folder: Path, name: str) -> list[Row]:
    with (folder / f"{name}.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _is_real_test(row: Row) -> bool:
    return row["source"] == "cadenza" and row.get("origen") == "registro"


def _origin_label(row: Row) -> str:
    """De dónde sale una partitura, para la tabla de las que más se corrigen."""
    if row["source"] != "cadenza":
        return "PrIMuS"
    return {"registro": "Prueba real", "estudio": "Banco del estudio"}.get(
        row.get("origen", ""), "Equipo"
    )


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
        session = row["session_id"] or row["incipit_id"]
        short = session[:8]  # basta para distinguirlas; el id entero está en las tablas
        if row["test_score_id"]:
            return f"{row['test_score_id']} · sesión {short}"
        return f"Sesión {short}"
    return row["incipit_id"]


def _event(kind: str, pitch: str, beats: str, *, hidden: bool = False) -> str:
    if hidden:
        # Un silencio invisible que marca el hueco de una voz (ADR-0032): como en las tiras.
        return f"hueco de {figure_name(beats)}"
    if kind == "rest":
        return f"silencio de {figure_name(beats)}"
    return f"{pitch} {figure_name(beats)}".strip()


def key_name(fifths: str) -> str:
    """La armadura en palabras: «armadura de 2 bemoles», «armadura sin alteraciones»."""
    try:
        value = int(fifths)
    except ValueError:
        return f"armadura {fifths}" if fifths else ""
    if value == 0:
        return "armadura sin alteraciones"
    count, sign = abs(value), ("sostenido" if value > 0 else "bemol")
    plural = sign if count == 1 else ("sostenidos" if value > 0 else "bemoles")
    return f"armadura de {count} {plural}"


Place = tuple[str, int | None, int | None]
"""Dónde dibujar un ejemplo: el compás (`bars`) y la posición del evento en lo que leyó HOMR y
en lo correcto (`None` si no está en ese lado)."""


def _bar_key(row: Row) -> tuple[str, ...]:
    return (row["incipit_id"], row["part"], row["staff"], row["measure"], row["voice"])


class _Bars:
    """Los compases de los ejemplos, para dibujarlos como partitura bajo la foto (#418): lo que
    leyó HOMR y lo correcto, evento a evento, con la clave y la armadura de la lectura. Solo se
    guardan los compases que algún ejemplo usa."""

    def __init__(self, tables: dict[str, list[Row]]) -> None:
        self.notas = tables["notas"]
        self.faltantes = tables["faltantes"]
        self.groups: dict[tuple[str, ...], tuple[list[int], list[int]]] = {}
        for index, row in enumerate(self.notas):
            self.groups.setdefault(_bar_key(row), ([], []))[0].append(index)
        for index, row in enumerate(self.faltantes):
            self.groups.setdefault(_bar_key(row), ([], []))[1].append(index)
        self.bars: dict[str, dict[str, Any]] = {}
        self.ids: dict[tuple[str, ...], str] = {}
        self.read_at: dict[int, int] = {}
        self.fix_at: dict[int, int] = {}
        self.missing_at: dict[int, int] = {}

    def _build(self, key: tuple[str, ...]) -> str:
        if key in self.ids:
            return self.ids[key]
        read_rows, missing_rows = self.groups[key]
        read_rows = sorted(read_rows, key=lambda i: int(self.notas[i]["event_index"] or 0))
        missing_rows = sorted(
            missing_rows, key=lambda i: int(self.faltantes[i]["event_index"] or 0)
        )
        read: list[list[Any]] = []
        fixed: list[list[Any]] = []

        def insert_missing(before: int | None) -> None:
            while missing_rows:
                position = int(self.faltantes[missing_rows[0]]["event_index"] or 0)
                if before is not None and position > before:
                    return
                index = missing_rows.pop(0)
                row = self.faltantes[index]
                if row["ins_hidden"] == "true":
                    continue
                self.missing_at[index] = len(fixed)
                fixed.append(
                    [
                        "r" if row["ins_kind"] == "rest" else "n",
                        row["ins_pitch"],
                        row["ins_duration_beats"],
                        int(row["ins_is_chord"] == "true"),
                    ]
                )

        for index in read_rows:
            row = self.notas[index]
            insert_missing(int(row["event_index"] or 0))
            if row["read_hidden"] == "true":
                continue
            kind = "r" if row["read_kind"] == "rest" else "n"
            chord = int(row["read_is_chord"] == "true")
            self.read_at[index] = len(read)
            read.append([kind, row["read_pitch"], row["read_duration_beats"], chord])
            if row["resultado"] != "borrada":
                self.fix_at[index] = len(fixed)
                fixed.append(
                    [
                        kind,
                        row["fix_pitch"] or row["read_pitch"],
                        row["fix_duration_beats"] or row["read_duration_beats"],
                        chord,
                    ]
                )
        insert_missing(None)
        first = self.notas[read_rows[0]] if read_rows else self.faltantes[self.groups[key][1][0]]
        bar_id = f"b{len(self.bars)}"
        self.bars[bar_id] = {
            "clef": first["ctx_clef"],
            "key": int(first["ctx_key_fifths"] or 0),
            "read": read,
            "fixed": fixed,
        }
        self.ids[key] = bar_id
        return bar_id

    def note(self, index: int) -> Place:
        bar_id = self._build(_bar_key(self.notas[index]))
        return bar_id, self.read_at.get(index), self.fix_at.get(index)

    def missing(self, index: int) -> Place:
        bar_id = self._build(_bar_key(self.faltantes[index]))
        return bar_id, None, self.missing_at.get(index)


def _example(
    row: Row, label: str, *, missing: bool = False, place: Place | None = None
) -> dict[str, Any]:
    """Un ejemplo: dónde está, su foto, qué leyó HOMR frente a lo correcto (con la duración de
    cada lado para el símbolo de su figura) y, si se sabe, su compás para dibujarlo. `kind` dice
    qué pasó: `change` (se corrigió), `extra` (HOMR la leyó de más) o `missing` (no la leyó)."""
    read_beats = fix_beats = ""
    if missing:
        kind, read = "missing", ""
        fix_beats = row["ins_duration_beats"]
        fixed = _event(
            row["ins_kind"], row["ins_pitch"], fix_beats, hidden=row.get("ins_hidden") == "true"
        )
    else:
        read_beats = row["read_duration_beats"]
        read = _event(
            row["read_kind"],
            row["read_pitch"],
            read_beats,
            hidden=row.get("read_hidden") == "true",
        )
        if row["resultado"] == "borrada":
            kind, fixed = "extra", ""
        else:
            kind = "change"
            fix_beats = row["fix_duration_beats"] or read_beats
            fixed = _event(row["read_kind"], row["fix_pitch"] or row["read_pitch"], fix_beats)
    example: dict[str, Any] = {
        "score": label,
        "measure": row["measure"],
        "staff": f"{row['part']}-{row['staff']}",
        "img": row.get("recorte", ""),
        "kind": kind,
        "read": read,
        "fix": fixed,
        "read_beats": read_beats,
        "fix_beats": fix_beats,
    }
    if place is not None:
        example["bar"], example["at_read"], example["at_fix"] = place
    return example


def _key_example(row: Row, label: str, img: str) -> dict[str, Any]:
    """Un ejemplo de `clave_armadura`: la clave y la armadura leídas frente a las correctas, en
    lenguaje musical («clave de fa en 3.ª, armadura de 2 bemoles»)."""

    def describe(clef: str, fifths: str) -> str:
        parts = [clef_name(clef) if clef else "", key_name(fifths)]
        return ", ".join(p for p in parts if p) or "—"

    return {
        "score": label,
        "measure": row["measure"],
        "staff": f"{row['part']}-{row['staff']}",
        "img": img,
        "kind": "change",
        "read": describe(row["read_clef"], row["read_key_fifths"]),
        "fix": describe(
            row["fix_clef"] or row["read_clef"], row["fix_key_fifths"] or row["read_key_fifths"]
        ),
        "read_beats": "",
        "fix_beats": "",
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
    build: Callable[[int, Row], dict[str, Any]],
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
            examples.add(f"{prefix}:{value}", (str(index),), lambda i=index, r=row: build(i, r))
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
    tables: dict[str, list[Row]],
    only: set[str] | None,
    skip_reordered: bool,
    reordered: set[int],
    bars: _Bars | None = None,
) -> dict[str, Any]:
    """Las cifras del informe para unas partituras (`incipit_id`; todas con `None`) y con o sin
    los acordes reordenados. Con `bars`, cada ejemplo lleva su compás para dibujarlo."""

    def keep(row: Row) -> bool:
        return only is None or row["incipit_id"] in only

    notas = [(i, r) for i, r in enumerate(tables["notas"]) if keep(r)]
    faltantes = [(i, r) for i, r in enumerate(tables["faltantes"]) if keep(r)]
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

    def note_example(index: int, row: Row) -> dict[str, Any]:
        place = bars.note(index) if bars is not None else None
        return _example(row, labels.get(row["incipit_id"], row["incipit_id"]), place=place)

    def missing_example(index: int, row: Row) -> dict[str, Any]:
        place = bars.missing(index) if bars is not None else None
        label = labels.get(row["incipit_id"], row["incipit_id"])
        return _example(row, label, missing=True, place=place)

    examples = _Examples()
    outcome = Counter(result(i, r) for i, r in notas)
    ops: Counter[str] = Counter()
    steps: Counter[int] = Counter()
    durations: Counter[tuple[str, str]] = Counter()
    for index, row in notas:
        if skip_reordered and index in reordered:
            continue
        build = partial(note_example, index, row)
        for op in filter(None, row["ops"].split("+")):
            ops[op] += 1
            examples.add(f"op:{op}", (str(index),), build)
        if "SetPitch" in row["ops"]:
            a, b = diatonic(row["read_pitch"]), diatonic(row["fix_pitch"])
            if a is not None and b is not None:
                step = max(-8, min(8, b - a))
                steps[step] += 1
                examples.add(f"step:{step}", (str(index),), build)
        if "SetDuration" in row["ops"] and row["fix_duration_beats"]:
            pair = (row["read_duration_beats"], row["fix_duration_beats"])
            durations[pair] += 1
            examples.add(f"dur:{pair[0]}>{pair[1]}", (str(index),), build)
    if faltantes:
        ops["InsertEvent"] = len(faltantes)
    for index, row in faltantes:
        examples.add(
            "op:InsertEvent",
            ("faltante", str(index)),
            partial(missing_example, index, row),
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
        notas,
        "ctx_accidental_vs_key",
        wrong,
        lambda v: VS_KEY.get(v, v),
        examples,
        note_example,
        "vs",
    )
    by_clef = _rates(notas, "ctx_clef", wrong, clef_name, examples, note_example, "clef")
    by_duration = _rates(
        notas, "read_duration_beats", wrong, figure_name, examples, note_example, "readdur"
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
                f"score:{row['incipit_id']}", (str(index),), partial(note_example, index, row)
            )
    for index, row in faltantes:
        per_score.setdefault(row["incipit_id"], [0, 0])[1] += 1
        examples.add(
            f"score:{row['incipit_id']}",
            ("faltante", str(index)),
            partial(missing_example, index, row),
        )
    # La clave y la armadura cuentan y también enseñan su ejemplo: una partitura con solo esa
    # corrección no puede decir «sin ninguna corrección» en el historial.
    for number, row in enumerate(claves):
        per_score.setdefault(row["incipit_id"], [0, 0])[1] += len(_ops(row))
        if _ops(row):
            label = labels.get(row["incipit_id"], row["incipit_id"])
            img = photos.get((row["incipit_id"], row["part"], row["staff"], row["measure"]), "")
            examples.add(
                f"score:{row['incipit_id']}",
                ("clave", str(number), row["incipit_id"]),
                partial(_key_example, row, label, img),
            )

    return {
        "scores": len(partituras),
        "clean_scores": sum(1 for _, fixes in per_score.values() if fixes == 0),
        "read": len(notas),
        "outcome": dict(outcome),
        "missing": len(faltantes),
        "reordered": sum(1 for i, _ in notas if i in reordered),
        "ops": dict(ops),
        "steps": {str(k): v for k, v in sorted(steps.items())},
        "durations": [
            {"read": a, "fix": b, "read_name": figure_name(a), "fix_name": figure_name(b), "n": n}
            for (a, b), n in durations.most_common()
        ],
        "by_vs_key": by_vs_key,
        "by_clef": by_clef,
        "by_duration": by_duration,
        # Para el historial: notas leídas y correcciones de cada partitura, en esta variante.
        "per_score": per_score,
        "examples": examples.items,
        "example_keys": dict(examples.by_key),
    }


def session_strips(folder: Path, partituras: list[Row]) -> list[dict[str, Any]]:
    """Las tiras de cada sesión (`pentagramas.csv`, con `--recortes`), en el orden del CSV: lo
    que leyó HOMR y lo corregido de cada pentagrama de cada sistema. Vacío sin recortes."""
    path = folder / "pentagramas.csv"
    if not path.is_file():
        return []
    labels = {r["session_id"]: _score_label(r) for r in partituras if r["session_id"]}
    real = {r["session_id"] for r in partituras if r["session_id"] and _is_real_test(r)}
    sessions: dict[str, dict[str, Any]] = {}
    for row in _read(folder, "pentagramas"):
        session = sessions.setdefault(
            row["session_id"],
            {
                "session": row["session_id"],
                "label": labels.get(row["session_id"], row["session_id"]),
                "real": row["session_id"] in real,
                "strips": [],
            },
        )
        session["strips"].append(
            {
                "system": row["sistema"],
                "staves": row["pentagramas"],
                "first": row["primer_compas"],
                "last": row["ultimo_compas"],
                "img": row["recorte"],
                "read": row["lectura"],
                "fixed": row["corregida"],
                "corrected": row["corregido"] == "true",
            }
        )
    return list(sessions.values())


def history(tables: dict[str, list[Row]], real: set[str]) -> list[dict[str, Any]]:
    """El historial de todas las transcripciones de la exportación (#418): una fila por partitura,
    con su nombre, de dónde sale, su fecha y la foto de su primer pentagrama, para buscarla y ver
    sus correcciones. Las cifras de cada una están en `per_score` de cada variante. No lleva el
    nombre de la cuenta: el informe nombra cada sesión por su página y su identificador."""
    photos: dict[str, str] = {}
    for row in tables["notas"]:
        if row.get("recorte"):
            photos.setdefault(row["incipit_id"], row["recorte"])
    return [
        {
            "id": row["incipit_id"],
            "label": _score_label(row),
            "origin": _origin_label(row),
            "date": (row.get("created_at") or "")[:10],
            "real": row["incipit_id"] in real,
            "img": photos.get(row["incipit_id"], ""),
        }
        for row in tables["partituras"]
    ]


def figures(tables: dict[str, list[Row]], sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """El nombre y el símbolo de cada duración que sale en el informe: las de las notas, las que
    faltaban y las de las tiras (`F4:3/4`, `r:1`, `+A4:1/2~`). La página no enseña fracciones."""
    beats = {r["read_duration_beats"] for r in tables["notas"]}
    beats |= {r["fix_duration_beats"] for r in tables["notas"]}
    beats |= {r["ins_duration_beats"] for r in tables["faltantes"]}
    for session in sessions:
        for strip in session["strips"]:
            for text in (strip["read"], strip["fixed"]):
                for token in text.split():
                    match = _TOKEN_BEATS.search(token)
                    if match:
                        beats.add(match.group(1))
    return {
        value: {"name": figure_name(value), "symbol": figure_symbol(value)}
        for value in sorted(beats - {""})
    }


def report_data(folder: Path) -> dict[str, Any]:
    """Todas las variantes del informe: todas las partituras y, si las hay, solo las de las
    pruebas reales de Cadenza (#418), con o sin los acordes reordenados; y las tiras de cada
    sesión."""
    tables = {
        name: _read(folder, name) for name in ("partituras", "notas", "faltantes", "clave_armadura")
    }
    reordered = reordered_chords(tables["notas"])
    groups: dict[str, set[str] | None] = {"todas": None}
    real = {r["incipit_id"] for r in tables["partituras"] if _is_real_test(r)}
    if real:
        groups[REAL_TESTS] = real
    bars = _Bars(tables)
    variants = {
        f"{name}|{int(skip)}": aggregate(tables, only, skip, reordered, bars)
        for name, only in groups.items()
        for skip in (False, True)
    }
    sessions = session_strips(folder, tables["partituras"])
    sources = Counter(r["source"] for r in tables["partituras"])
    return {
        "groups": [name for name in groups if name != "todas"],
        "counts": {"primus": sources["primus"], "cadenza": sources["cadenza"], "real": len(real)},
        "variants": variants,
        "sessions": sessions,
        "figures": figures(tables, sessions),
        "bars": bars.bars,
        "history": history(tables, real),
    }


def _font_faces() -> str:
    """`@font-face` con cada tipografía en base64; las que falten, a las de reserva del CSS."""
    faces = []
    for family, weight, name in FONTS:
        path = FONTS_DIR / name
        if not path.is_file():
            continue
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        faces.append(
            f"@font-face{{font-family:'{family}';font-style:normal;font-weight:{weight};"
            f"font-display:swap;src:url(data:font/woff2;base64,{data}) format('woff2')}}"
        )
    return "\n".join(faces)


def write_report(folder: Path) -> Path:
    """Escribe `informe.html` en la carpeta de la exportación y devuelve su ruta."""
    data = report_data(folder)
    info = json.loads((folder / "run_info.json").read_text(encoding="utf-8"))
    # Ningún `<` en el script: ni `</script>` ni `<!--` pueden cortarlo. Los datos van los
    # últimos, para que un `__DATE__` dentro de ellos no se sustituya.
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    page = (
        TEMPLATE.read_text(encoding="utf-8")
        .replace("/*__FONTS__*/", _font_faces())
        .replace("__COMMIT__", html.escape(str(info.get("commit") or "?")[:7]))
        .replace("__DATE__", html.escape(str(info.get("generated_at", ""))[:16].replace("T", " ")))
        .replace("__DATA__", payload)
    )
    target = folder / REPORT_NAME
    target.write_text(page, encoding="utf-8")
    return target
