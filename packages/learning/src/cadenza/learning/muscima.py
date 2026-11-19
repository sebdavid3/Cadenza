"""Anotaciones MuNG de MUSCIMA++ v2.0 y su conversión a `ScoreIR` (#102).

MUSCIMA++ no trae la partitura de cada página, sino un grafo de primitivas (cabezas, plicas,
barras, corchetes, puntillos, alteraciones, claves, barras de compás...) con sus cajas y sus
enlaces. La altura y la duración se reconstruyen de ese grafo, como hace la inferencia de
referencia del paquete `mung` (`mung2midi/inference.py`, licencia MIT), de la que se toma la
regla de la posición en el pentagrama y de las líneas adicionales.

Solo se convierten las páginas de **un pentagrama por sistema y una voz**: la inferencia de
referencia tampoco resuelve el orden de los ataques en música polifónica, y MuNG no anota las
voces. Lo demás se rechaza con `MungConversionError`, con el motivo:

- sistemas de varios pentagramas (llave, corchete o una barra de compás que cruza pentagramas);
- polifonía (una cabeza con dos plicas, o dos plicas distintas a la misma altura horizontal);
- abreviaturas de compás (`multiMeasureRest`, `repeat1Bar`), cuyo contenido no está escrito;
- una cabeza sin posición en el pentagrama o una indicación que no se puede leer.

Las notas de adorno (cabezas pequeñas) no entran en la partitura y se cuentan aparte: el
dominio no tiene notas de adorno.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from fractions import Fraction
from itertools import pairwise
from pathlib import Path
from typing import Final

from cadenza.domain import (
    Clef,
    Event,
    EventKind,
    KeySignature,
    Measure,
    Part,
    ScoreIR,
    Staff,
    Tie,
    TimeSignature,
)

NOTEHEADS: Final[frozenset[str]] = frozenset({"noteheadFull", "noteheadHalf", "noteheadWhole"})
GRACE_NOTEHEADS: Final[frozenset[str]] = frozenset({"noteheadFullSmall", "noteheadHalfSmall"})
# Duración en negras; la redonda de silencio ocupa el compás entero (None).
RESTS: Final[dict[str, Fraction | None]] = {
    "restWhole": None,
    "restHalf": Fraction(2),
    "restQuarter": Fraction(1),
    "rest8th": Fraction(1, 2),
    "rest16th": Fraction(1, 4),
    "rest32nd": Fraction(1, 8),
    "rest64th": Fraction(1, 16),
}
FLAGS: Final[dict[str, int]] = {
    "flag8thUp": 1,
    "flag8thDown": 1,
    "flag16thUp": 2,
    "flag16thDown": 2,
    "flag32ndUp": 3,
    "flag32ndDown": 3,
    "flag64thUp": 4,
    "flag64thDown": 4,
}
ACCIDENTALS: Final[dict[str, str]] = {
    "accidentalSharp": "#",
    "accidentalFlat": "b",
    "accidentalNatural": "",
    "accidentalDoubleSharp": "##",
    "accidentalDoubleFlat": "bb",
}
CLEFS: Final[frozenset[str]] = frozenset({"gClef", "fClef", "cClef"})
GROUPINGS: Final[frozenset[str]] = frozenset({"staffGrouping", "brace", "bracket"})
SHORTHANDS: Final[tuple[str, ...]] = ("multiMeasureRest", "repeat1Bar")
STAFF_POSITIONS: Final[frozenset[str]] = frozenset({"staffLine", "staffSpace"})

_STEPS: Final[str] = "CDEFGAB"
_SHARP_ORDER: Final[str] = "FCGDAEB"
_FLAT_ORDER: Final[str] = "BEADGCF"
# Un carácter de la armadura o una alteración: la alteración que suena.
_ALTER: Final[dict[str, int]] = {"": 0, "#": 1, "##": 2, "b": -1, "bb": -2}
_ALTER_NAME: Final[dict[int, str]] = {value: name for name, value in _ALTER.items()}
# Dos cabezas de plicas distintas son simultáneas si se solapan en más de esta fracción de la
# más estrecha: en una voz, una cabeza empieza donde termina la anterior.
_OVERLAP: Final[float] = 0.5


class MungConversionError(ValueError):
    """La página no se puede convertir a `ScoreIR` (el mensaje dice por qué)."""


@dataclass(frozen=True, slots=True)
class MungNode:
    """Un objeto del grafo MuNG: su clase, su caja en píxeles y sus enlaces salientes."""

    id: int
    class_name: str
    top: int
    left: int
    width: int
    height: int
    outlinks: tuple[int, ...] = ()

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def center_y(self) -> float:
        return self.top + self.height / 2

    @property
    def center_x(self) -> float:
        return self.left + self.width / 2


def parse_mung(xml_text: str) -> dict[int, MungNode]:
    """Los nodos de un documento MuNG (XML de MUSCIMA++ v2.0), por identificador."""
    root = ET.fromstring(xml_text)
    nodes: dict[int, MungNode] = {}
    for element in root.iter("Node"):
        node = MungNode(
            id=int(_text(element, "Id")),
            class_name=_text(element, "ClassName"),
            top=int(_text(element, "Top")),
            left=int(_text(element, "Left")),
            width=int(_text(element, "Width")),
            height=int(_text(element, "Height")),
            outlinks=tuple(int(x) for x in (element.findtext("Outlinks") or "").split()),
        )
        nodes[node.id] = node
    return nodes


def read_mung(path: Path) -> dict[int, MungNode]:
    return parse_mung(path.read_text(encoding="utf-8"))


def _text(element: ET.Element, tag: str) -> str:
    value = element.findtext(tag)
    if value is None:
        raise ValueError(f"nodo MuNG sin <{tag}>")
    return value.strip()


# --- Recuentos y textura ----------------------------------------------------------------


def mung_counts(nodes: Mapping[int, MungNode]) -> dict[str, int]:
    """Lo que hay anotado en la página, sin inferir nada."""
    classes = [node.class_name for node in nodes.values()]
    return {
        "noteheads": sum(c in NOTEHEADS for c in classes),
        "grace_noteheads": sum(c in GRACE_NOTEHEADS for c in classes),
        "rests": sum(c in RESTS for c in classes),
        "staves": classes.count("staff"),
        "measure_separators": classes.count("measureSeparator"),
        "shorthands": sum(c in SHORTHANDS for c in classes),
    }


def mung_texture(nodes: Mapping[int, MungNode]) -> str:
    """`multi_staff` si algún sistema tiene varios pentagramas; si no, `single_staff`."""
    for node in nodes.values():
        if node.class_name in GROUPINGS:
            return "multi_staff"
        if node.class_name == "measureSeparator":
            staves = [o for o in node.outlinks if _class(nodes, o) == "staff"]
            if len(staves) > 1:
                return "multi_staff"
    return "single_staff"


def _class(nodes: Mapping[int, MungNode], node_id: int) -> str | None:
    node = nodes.get(node_id)
    return None if node is None else node.class_name


# --- Conversión -------------------------------------------------------------------------


@dataclass(slots=True)
class _Context:
    """La clave, la armadura y las alteraciones vigentes al leer un pentagrama de izquierda a
    derecha. La posición `delta` cuenta líneas y espacios desde la línea central (arriba,
    positiva), como en la inferencia de referencia."""

    clef: Clef = field(default_factory=Clef.treble)
    fifths: int = 0
    inline: dict[int, str] = field(default_factory=dict)

    def reference(self) -> tuple[int, int]:
        """(posición, índice diatónico) de la nota que fija la clave."""
        step = {"G": ("G", 4), "F": ("F", 3), "C": ("C", 4)}.get(self.clef.sign)
        if step is None:
            raise MungConversionError(f"clave desconocida: {self.clef.sign}")
        letter, octave = step
        return (self.clef.line - 3) * 2, octave * 7 + _STEPS.index(letter)

    def pitch(self, delta: int) -> str:
        position, index = self.reference()
        diatonic = index + (delta - position)
        letter, octave = _STEPS[diatonic % 7], diatonic // 7
        if delta in self.inline:
            alteration = self.inline[delta]
        elif self.fifths > 0 and letter in _SHARP_ORDER[: self.fifths]:
            alteration = "#"
        elif self.fifths < 0 and letter in _FLAT_ORDER[: -self.fifths]:
            alteration = "b"
        else:
            alteration = ""
        return f"{letter}{alteration}{octave}"


@dataclass(slots=True)
class _OpenMeasure:
    events: list[Event] = field(default_factory=list)
    clef: Clef | None = None
    key: KeySignature | None = None
    time: TimeSignature | None = None


@dataclass(slots=True)
class _Builder:
    """Va cerrando compases con lo que cambia (clave, armadura, compás) solo donde cambia."""

    measures: list[Measure] = field(default_factory=list)
    current: _OpenMeasure = field(default_factory=_OpenMeasure)
    pending: _OpenMeasure = field(default_factory=_OpenMeasure)
    clef: Clef | None = None
    key: KeySignature | None = None
    time: TimeSignature | None = None

    def set_clef(self, clef: Clef) -> None:
        if clef != self.clef:
            self.clef = clef
            self._target().clef = clef

    def set_key(self, key: KeySignature) -> None:
        if key != self.key:
            self.key = key
            self._target().key = key

    def set_time(self, time: TimeSignature) -> None:
        if time != self.time:
            self.time = time
            self._target().time = time

    def _target(self) -> _OpenMeasure:
        # Un cambio a mitad de compás rige después: el dominio lo pone en el compás siguiente.
        return self.pending if self.current.events else self.current

    def add(self, events: Iterable[Event]) -> None:
        self.current.events.extend(events)

    def close(self) -> None:
        if not self.current.events:
            return
        self.measures.append(
            Measure(
                number=len(self.measures) + 1,
                events=tuple(self.current.events),
                clef=self.current.clef,
                key_signature=self.current.key,
                time_signature=self.current.time,
            )
        )
        self.current, self.pending = self.pending, _OpenMeasure()


def mung_to_score(nodes: Mapping[int, MungNode], *, score_id: str = "muscima") -> ScoreIR:
    """La partitura de una página de un pentagrama por sistema y una voz.

    Los pentagramas se leen de arriba abajo y, en cada uno, los símbolos de izquierda a
    derecha. Un compás termina en una barra (`measureSeparator`); si una línea acaba sin barra,
    el compás sigue en la siguiente.
    """
    if mung_texture(nodes) != "single_staff":
        raise MungConversionError("la página tiene sistemas de varios pentagramas")
    for name in SHORTHANDS:
        if any(node.class_name == name for node in nodes.values()):
            raise MungConversionError(f"la página abrevia compases con {name}")

    children = _children_by_staff(nodes)
    staves = sorted(
        (node for node in nodes.values() if node.class_name == "staff"), key=lambda n: n.top
    )
    builder = _Builder()
    pitches: dict[int, str] = {}
    for staff in staves:
        _read_staff(nodes, staff, children.get(staff.id, []), builder, pitches)
    builder.close()
    if not builder.measures:
        raise MungConversionError("la página no tiene notas ni silencios")
    measures = _fill_whole_rests(builder.measures)
    if measures[0].key_signature is None:
        # Sin armadura anotada, la página está sin alteraciones: es lo que lee un MusicXML.
        measures[0] = replace(measures[0], key_signature=KeySignature(fifths=0))
    return ScoreIR(
        parts=(Part(id=score_id, staves=(Staff(id=f"{score_id}-1", measures=tuple(measures)),)),)
    )


def _children_by_staff(nodes: Mapping[int, MungNode]) -> dict[int, list[MungNode]]:
    by_staff: dict[int, list[MungNode]] = {}
    for node in nodes.values():
        for target in node.outlinks:
            if _class(nodes, target) == "staff":
                by_staff.setdefault(target, []).append(node)
    return by_staff


def _linked(nodes: Mapping[int, MungNode], node: MungNode, names: Iterable[str]) -> list[MungNode]:
    wanted = set(names)
    return [nodes[o] for o in node.outlinks if o in nodes and nodes[o].class_name in wanted]


def _read_staff(
    nodes: Mapping[int, MungNode],
    staff: MungNode,
    members: list[MungNode],
    builder: _Builder,
    pitches: dict[int, str],
) -> None:
    lines, deltas = _staff_geometry(nodes, staff)
    context = _Context(
        clef=builder.clef or Clef.treble(),
        fifths=0 if builder.key is None else builder.key.fifths,
    )
    groups = _event_groups(nodes, members)
    items: list[tuple[int, int, MungNode | tuple[MungNode, ...]]] = []
    for node in members:
        if node.class_name in CLEFS | {"keySignature", "timeSignature", "measureSeparator"}:
            items.append((node.left, 0, node))
    for group in groups:
        items.append((min(n.left for n in group), 1, group))
    items.sort(key=lambda item: (item[0], item[1]))

    for _, _, item in items:
        if isinstance(item, MungNode):
            if item.class_name in CLEFS:
                clef = _clef(item, lines)
                context.clef = clef
                builder.set_clef(clef)
            elif item.class_name == "keySignature":
                key = _key(nodes, item)
                context.fifths = key.fifths
                builder.set_key(key)
            elif item.class_name == "timeSignature":
                builder.set_time(_time(nodes, item))
            else:
                builder.close()
                context.inline.clear()
        else:
            builder.add(_group_events(nodes, item, staff, deltas, lines, context, pitches))


def _staff_geometry(
    nodes: Mapping[int, MungNode], staff: MungNode
) -> tuple[list[float], dict[int, int]]:
    """Los centros de las cinco líneas (de arriba abajo) y la posición de cada línea y espacio."""
    lines = sorted((n for n in _linked(nodes, staff, ("staffLine",))), key=lambda n: n.center_y)
    if len(lines) != 5:
        raise MungConversionError(f"el pentagrama {staff.id} tiene {len(lines)} líneas")
    centers = [line.center_y for line in lines]
    deltas = {line.id: 4 - 2 * i for i, line in enumerate(lines)}
    for space in _linked(nodes, staff, ("staffSpace",)):
        above = sum(1 for center in centers if center < space.center_y)
        deltas[space.id] = 5 - 2 * above
    return centers, deltas


def _clef(node: MungNode, lines: list[float]) -> Clef:
    if node.class_name == "gClef":
        return Clef.treble()
    if node.class_name == "fClef":
        return Clef.bass()
    # La clave de do se centra en la línea que marca.
    nearest = min(range(5), key=lambda i: abs(lines[i] - node.center_y))
    return Clef(sign="C", line=5 - nearest)


def _key(nodes: Mapping[int, MungNode], node: MungNode) -> KeySignature:
    sharps = len(_linked(nodes, node, ("accidentalSharp",)))
    flats = len(_linked(nodes, node, ("accidentalFlat",)))
    if sharps and flats:
        raise MungConversionError(f"armadura {node.id} con sostenidos y bemoles")
    if sharps > 7 or flats > 7:
        raise MungConversionError(f"armadura {node.id} con más de siete alteraciones")
    return KeySignature(fifths=sharps - flats)


def _digits(nodes: Iterable[MungNode]) -> int | None:
    ordered = sorted(nodes, key=lambda n: n.left)
    text = "".join(n.class_name.removeprefix("numeral") for n in ordered)
    return int(text) if text.isdigit() else None


def _time(nodes: Mapping[int, MungNode], node: MungNode) -> TimeSignature:
    if _linked(nodes, node, ("timeSigCommon",)):
        return TimeSignature(4, 4, symbol="common")
    if _linked(nodes, node, ("timeSigCutCommon",)):
        return TimeSignature(2, 2, symbol="cut")
    numerals = _linked_prefix(nodes, node, "numeral")
    upper = _digits(n for n in numerals if n.center_y < node.center_y)
    lower = _digits(n for n in numerals if n.center_y >= node.center_y)
    if upper is None or lower is None:
        raise MungConversionError(f"compás {node.id} sin numerador o sin denominador")
    try:
        return TimeSignature(upper, lower)
    except ValueError as exc:
        raise MungConversionError(f"compás {node.id}: {exc}") from exc


def _linked_prefix(nodes: Mapping[int, MungNode], node: MungNode, prefix: str) -> list[MungNode]:
    return [
        nodes[o] for o in node.outlinks if o in nodes and nodes[o].class_name.startswith(prefix)
    ]


def _event_groups(
    nodes: Mapping[int, MungNode], members: list[MungNode]
) -> list[tuple[MungNode, ...]]:
    """Las cabezas de una plica forman un acorde; una cabeza sin plica, o un silencio, va sola.
    Dos grupos que se solapan en horizontal son simultáneos: polifonía."""
    by_stem: dict[int, list[MungNode]] = {}
    loose: list[list[MungNode]] = []
    for node in members:
        if node.class_name in NOTEHEADS:
            stems = [o for o in node.outlinks if _class(nodes, o) == "stem"]
            if len(stems) > 1:
                raise MungConversionError(f"polifonía: la cabeza {node.id} tiene dos plicas")
            if stems:
                by_stem.setdefault(stems[0], []).append(node)
            else:
                loose.append([node])
        elif node.class_name in RESTS:
            loose.append([node])
    # Las redondas de un acorde no tienen plica: se juntan si se solapan.
    merged: list[list[MungNode]] = []
    for group in sorted(loose, key=lambda g: g[0].left):
        head = group[0]
        previous = merged[-1] if merged else None
        if (
            previous is not None
            and head.class_name == "noteheadWhole"
            and previous[0].class_name == "noteheadWhole"
            and _overlaps(previous, group)
        ):
            previous.extend(group)
        else:
            merged.append(group)
    groups = [tuple(g) for g in [*by_stem.values(), *merged]]
    groups.sort(key=lambda g: min(n.left for n in g))
    for before, after in pairwise(groups):
        if _overlaps(before, after):
            raise MungConversionError(
                f"polifonía: {before[0].class_name} {before[0].id} y "
                f"{after[0].class_name} {after[0].id} suenan a la vez"
            )
    return groups


def _overlaps(a: Iterable[MungNode], b: Iterable[MungNode]) -> bool:
    a_left, a_right = min(n.left for n in a), max(n.right for n in a)
    b_left, b_right = min(n.left for n in b), max(n.right for n in b)
    shared = min(a_right, b_right) - max(a_left, b_left)
    narrower = min(a_right - a_left, b_right - b_left)
    return narrower > 0 and shared > _OVERLAP * narrower


def _group_events(
    nodes: Mapping[int, MungNode],
    group: tuple[MungNode, ...],
    staff: MungNode,
    deltas: Mapping[int, int],
    lines: list[float],
    context: _Context,
    pitches: dict[int, str],
) -> list[Event]:
    first = group[0]
    if first.class_name in RESTS:
        duration = RESTS[first.class_name]
        return [Event(kind=EventKind.REST, duration_beats=_modified(nodes, first, duration))]
    heads = []
    for head in group:
        delta = _delta(nodes, head, staff, deltas, lines)
        heads.append((delta, head))
    events: list[tuple[int, str, Event]] = []
    for delta, head in heads:
        pitch, tie = _pitch_and_tie(nodes, head, delta, context, pitches)
        duration = _modified(nodes, head, _head_beats(nodes, head))
        events.append(
            (
                delta,
                pitch,
                Event(kind=EventKind.NOTE, pitch=pitch, duration_beats=duration, tie=tie),
            )
        )
    events.sort(key=lambda item: item[0])
    return [replace(event, is_chord=index > 0) for index, (_, _, event) in enumerate(events)]


def _delta(
    nodes: Mapping[int, MungNode],
    head: MungNode,
    staff: MungNode,
    deltas: Mapping[int, int],
    lines: list[float],
) -> int:
    positions = [o for o in head.outlinks if _class(nodes, o) in STAFF_POSITIONS]
    if len(positions) > 1:
        raise MungConversionError(f"la cabeza {head.id} está en dos posiciones del pentagrama")
    if positions:
        if positions[0] not in deltas:
            raise MungConversionError(f"la cabeza {head.id} está en una línea de otro pentagrama")
        return deltas[positions[0]]
    ledgers = _linked(nodes, head, ("legerLine",))
    if not ledgers:
        raise MungConversionError(f"la cabeza {head.id} no tiene posición en el pentagrama")
    above = head.center_y < lines[0]
    closest = min(ledgers, key=lambda ll: abs(ll.center_y - head.center_y))
    # En la línea si la línea adicional pasa por la mitad central de la cabeza.
    margin = head.height / 4
    on_line = head.top + margin <= closest.center_y <= head.bottom - margin
    delta = (2 * len(ledgers) - 1) + 5 + (0 if on_line else 1)
    return delta if above else -delta


def _pitch_and_tie(
    nodes: Mapping[int, MungNode],
    head: MungNode,
    delta: int,
    context: _Context,
    pitches: dict[int, str],
) -> tuple[str, Tie | None]:
    starts = stops = 0
    inherited: str | None = None
    for tie in _linked(nodes, head, ("tie",)):
        partners = [n for n in nodes.values() if tie.id in n.outlinks and n.class_name in NOTEHEADS]
        others = [n for n in partners if n.id != head.id]
        if not others:
            # Ligadura que cruza el salto de línea: el lado lo dice dónde está el arco.
            if tie.center_x > head.center_x:
                starts += 1
            else:
                stops += 1
            continue
        if all(other.left < head.left for other in others):
            stops += 1
            inherited = pitches.get(min(others, key=lambda n: n.left).id) or inherited
        else:
            starts += 1
    accidentals = _linked(nodes, head, ACCIDENTALS)
    if accidentals:
        chosen = next(
            (a for a in accidentals if a.class_name != "accidentalNatural"), accidentals[0]
        )
        context.inline[delta] = ACCIDENTALS[chosen.class_name]
    pitch = inherited if inherited is not None and not accidentals else context.pitch(delta)
    pitches[head.id] = pitch
    tie_state = (
        Tie.CONTINUE if starts and stops else Tie.START if starts else Tie.STOP if stops else None
    )
    return pitch, tie_state


def _head_beats(nodes: Mapping[int, MungNode], head: MungNode) -> Fraction:
    if head.class_name == "noteheadWhole":
        return Fraction(4)
    if head.class_name == "noteheadHalf":
        return Fraction(2)
    beams = len(_linked(nodes, head, ("beam",)))
    flags = sum(FLAGS[f.class_name] for f in _linked(nodes, head, FLAGS))
    return Fraction(1, 2 ** (beams + flags))


def _modified(
    nodes: Mapping[int, MungNode], node: MungNode, beats: Fraction | None
) -> Fraction | None:
    """Puntillos y grupos irregulares (n en el tiempo de la mayor potencia de dos por debajo)."""
    if beats is None:
        return None
    dots = len(_linked(nodes, node, ("augmentationDot",)))
    beats = beats * (2 - Fraction(1, 2**dots))
    for tuplet in _linked(nodes, node, ("tuple",)):
        number = _digits(_linked_prefix(nodes, tuplet, "numeral"))
        if number is None or number < 2:
            raise MungConversionError(f"grupo irregular {tuplet.id} sin número")
        normal = 1 << (number.bit_length() - 1)
        if normal == number:
            normal //= 2
        beats = beats * Fraction(normal, number)
    return beats


def _fill_whole_rests(measures: list[Measure]) -> list[Measure]:
    """La redonda de silencio dura lo que el compás vigente (4/4 si no hay compás)."""
    time: TimeSignature | None = None
    out: list[Measure] = []
    for measure in measures:
        time = measure.time_signature or time
        capacity = time.quarter_length if time is not None else Fraction(4)
        events = tuple(
            replace(e, duration_beats=capacity) if e.duration_beats is None else e
            for e in measure.events
        )
        out.append(replace(measure, events=events))
    return out
