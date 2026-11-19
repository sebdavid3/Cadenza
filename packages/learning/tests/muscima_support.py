"""Páginas MuNG sintéticas para las pruebas de MUSCIMA++ (#102)."""

from __future__ import annotations

from cadenza.learning import MungNode

GAP = 20  # distancia entre líneas del pentagrama, en píxeles


class Page:
    """Una página MuNG sintética: nodos con su caja y sus enlaces, como los de MUSCIMA++."""

    def __init__(self) -> None:
        self.nodes: dict[int, MungNode] = {}

    def add(
        self,
        class_name: str,
        top: float,
        left: float,
        width: float,
        height: float,
        outlinks: tuple[int, ...] = (),
    ) -> int:
        node_id = len(self.nodes)
        self.nodes[node_id] = MungNode(
            id=node_id,
            class_name=class_name,
            top=round(top),
            left=round(left),
            width=round(width),
            height=round(height),
            outlinks=outlinks,
        )
        return node_id

    def link(self, source: int, *targets: int) -> None:
        node = self.nodes[source]
        self.nodes[source] = MungNode(
            id=node.id,
            class_name=node.class_name,
            top=node.top,
            left=node.left,
            width=node.width,
            height=node.height,
            outlinks=(*node.outlinks, *targets),
        )


class Staff:
    """Un pentagrama: cinco líneas y seis espacios (los de fuera incluidos), con su posición."""

    def __init__(self, page: Page, top: int) -> None:
        self.page = page
        self.top = top
        self.id = page.add("staff", top, 0, 3000, 4 * GAP)
        self.positions: dict[int, int] = {}
        for i in range(5):
            y = top + i * GAP
            self.positions[4 - 2 * i] = page.add("staffLine", y - 1, 0, 3000, 3)
        for k in range(6):
            center = top - GAP / 2 + k * GAP
            self.positions[5 - 2 * k] = page.add(
                "staffSpace", center - GAP / 2 + 3, 0, 3000, GAP - 6
            )
        page.link(self.id, *self.positions.values())

    def y(self, delta: int) -> float:
        """El centro vertical de la posición `delta` (0 es la línea central; arriba, positivo)."""
        return self.top + (4 - delta) * GAP / 2

    def symbol(
        self,
        class_name: str,
        left: int,
        *children: int,
        top: float | None = None,
        height: float = 4 * GAP,
    ) -> int:
        node = self.page.add(class_name, self.top if top is None else top, left, 30, height)
        self.page.link(node, *children, self.id)
        return node

    def separator(self, left: int) -> int:
        barline = self.page.add("barline", self.top, left, 3, 4 * GAP)
        return self.symbol("measureSeparator", left, barline)

    def clef(self, class_name: str, left: int, *, line: int | None = None) -> int:
        if line is None:
            return self.symbol(class_name, left)
        center = self.y((line - 3) * 2)
        return self.symbol(class_name, left, top=center - 1.5 * GAP, height=3 * GAP)

    def key(self, left: int, *, sharps: int = 0, flats: int = 0) -> int:
        children = [
            self.page.add(
                "accidentalSharp" if sharps else "accidentalFlat", self.top, left + 8 * i, 8, 30
            )
            for i in range(sharps or flats)
        ]
        return self.symbol("keySignature", left, *children)

    def time(self, left: int, beats: int | None, beat_type: int | None = None) -> int:
        if beats is None:
            common = self.page.add("timeSigCommon", self.top + GAP, left, 20, 2 * GAP)
            return self.symbol("timeSignature", left, common)
        upper = self.page.add(f"numeral{beats}", self.top, left, 16, 2 * GAP - 2)
        lower = self.page.add(f"numeral{beat_type}", self.top + 2 * GAP + 2, left, 16, 2 * GAP - 2)
        return self.symbol("timeSignature", left, upper, lower)

    def note(
        self,
        delta: int,
        left: int,
        *,
        head: str = "noteheadFull",
        stem: int | None = None,
        new_stem: bool = True,
        beams: tuple[int, ...] = (),
        flag: str | None = None,
        dots: int = 0,
        accidental: str | None = None,
        ties: tuple[int, ...] = (),
        tuple_node: int | None = None,
    ) -> int:
        """Una cabeza en `delta`, con líneas adicionales si está fuera del pentagrama."""
        center = self.y(delta)
        links: list[int] = []
        if -5 <= delta <= 5:
            links.append(self.positions[delta])
        else:
            above = delta > 0
            count = (abs(delta) - 5) // 2 + (abs(delta) - 5) % 2
            for n in range(1, count + 1):
                ledger_delta = (4 + 2 * n) * (1 if above else -1)
                links.append(self.page.add("legerLine", self.y(ledger_delta) - 1, left - 6, 36, 3))
        if head != "noteheadWhole":
            if stem is None and new_stem:
                stem = self.page.add("stem", center - 3 * GAP, left + 22, 2, 3 * GAP)
            if stem is not None:
                links.append(stem)
        links.extend(beams)
        if flag is not None:
            links.append(self.page.add(flag, center - 3 * GAP, left + 24, 10, 20))
        for i in range(dots):
            links.append(self.page.add("augmentationDot", center - 2, left + 30 + 6 * i, 4, 4))
        if accidental is not None:
            links.append(self.page.add(accidental, center - 15, left - 14, 10, 30))
        links.extend(ties)
        if tuple_node is not None:
            links.append(tuple_node)
        node = self.page.add(head, center - GAP / 2, left, 24, GAP)
        self.page.link(node, *links, self.id)
        return node

    def rest(self, class_name: str, left: int, *, dots: int = 0) -> int:
        links = [
            self.page.add("augmentationDot", self.y(1), left + 20 + 6 * i, 4, 4)
            for i in range(dots)
        ]
        node = self.page.add(class_name, self.y(2), left, 14, 2 * GAP)
        self.page.link(node, *links, self.id)
        return node


def to_xml(nodes: dict[int, MungNode], document: str = "CVC-MUSCIMA_W-01_N-01_D-ideal") -> str:
    """El documento MuNG (XML de MUSCIMA++ v2.0) con estos nodos."""
    body = []
    for node in nodes.values():
        links = (
            f"<Outlinks>{' '.join(str(o) for o in node.outlinks)}</Outlinks>"
            if node.outlinks
            else ""
        )
        body.append(
            f"<Node><Id>{node.id}</Id><ClassName>{node.class_name}</ClassName>"
            f"<Top>{node.top}</Top><Left>{node.left}</Left><Width>{node.width}</Width>"
            f"<Height>{node.height}</Height>{links}</Node>"
        )
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<Nodes dataset="MUSCIMA-pp_2.0" document="{document}">{"".join(body)}</Nodes>'
    )


_TYPES = {1: "quarter", 2: "half", 4: "whole"}


def melody_musicxml(*measures: list[tuple[str, int, int]]) -> str:
    """MusicXML de una voz en 4/4 y clave de sol: (letra, octava, negras) por nota."""
    body = []
    for number, notes in enumerate(measures, start=1):
        attributes = (
            "<attributes><divisions>1</divisions><key><fifths>0</fifths></key>"
            "<time><beats>4</beats><beat-type>4</beat-type></time>"
            "<clef><sign>G</sign><line>2</line></clef></attributes>"
            if number == 1
            else ""
        )
        xml_notes = "".join(
            f"<note><pitch><step>{step}</step><octave>{octave}</octave></pitch>"
            f"<duration>{beats}</duration><voice>1</voice><type>{_TYPES[beats]}</type></note>"
            for step, octave, beats in notes
        )
        body.append(f'<measure number="{number}">{attributes}{xml_notes}</measure>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?><score-partwise version="4.0">'
        '<part-list><score-part id="P1"><part-name>M</part-name></score-part></part-list>'
        f'<part id="P1">{"".join(body)}</part></score-partwise>'
    )
