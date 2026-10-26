"""Prototipo de fusión: notas de HOMR y marcas de Audiveris ancladas a ellas (INV-0002).

Uso: python fusion.py <carpeta de datos>

La carpeta tiene la verdad (`mondnacht.musicxml`, exportado por MuseScore 3.6.2, y el original
de OpenScore `lc4987640.mscx`) y la salida de cada motor por variante y página, como en
`comparar_mondnacht.py`.

Fusión (solo usa las salidas de los motores, nunca la verdad):
1. Empareja los compases de Audiveris con los de HOMR por su contenido (alturas), con
   programación dinámica.
2. Descarta las marcas de Audiveris en compases que se parecen poco a los de HOMR (umbral).
3. Ancla cada dinámica o regulador al ataque de HOMR más cercano del mismo grupo de
   pentagramas (voz o piano). Staccatos y calderones: los de HOMR.

Medición (aquí sí se usa la verdad de OpenScore): empareja los compases de HOMR con los de la
verdad, del mismo modo, y compara marca a marca: mismo tipo y valor, mismo grupo, mismo compás y
ataque a menos de una semicorchea (estricta) o solo mismo compás (laxa).
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from music21 import articulations, converter, dynamics, expressions, note, stream

TOLERANCE = 0.25  # negras: una semicorchea
GROUP = {0: "voz", 1: "piano", 2: "piano"}


@dataclass(frozen=True)
class Mark:
    kind: str  # dinámica, regulador, staccato, calderón
    value: str  # p, mf, cresc., dim. ...
    group: str
    measure: int  # índice global en la pieza
    onset: float


@dataclass
class Measure:
    pitches: Counter
    onsets: dict  # grupo -> ataques de notas


def load(paths: list[Path]) -> tuple[list[Measure], list[Mark]]:
    """Compases (en orden, páginas seguidas) y marcas de una o varias páginas."""
    measures: list[Measure] = []
    marks: list[Mark] = []
    for path in paths:
        score = converter.parse(str(path))
        base = len(measures)
        page_measures: dict[int, Measure] = {}
        where_of: dict[int, tuple[int, str, float]] = {}
        for staff, part in enumerate(score.parts):
            group = GROUP.get(staff, "piano")
            for i, m in enumerate(part.getElementsByClass(stream.Measure)):
                entry = page_measures.setdefault(i, Measure(Counter(), {}))
                flat = m.flatten()
                for el in flat:
                    # Al aplanar, el contexto «compás» de cada elemento pasa a ser la copia plana:
                    # los reguladores se localizan por el propio elemento.
                    where_of[id(el)] = (base + i, group, float(el.offset))
                for el in flat.notesAndRests:
                    if isinstance(el, note.Rest):
                        continue
                    onset = float(el.offset)
                    entry.onsets.setdefault(group, set()).add(onset)
                    for p in el.pitches:
                        entry.pitches[p.nameWithOctave] += 1
                    if any(isinstance(a, articulations.Staccato) for a in el.articulations):
                        marks.append(Mark("staccato", "staccato", group, base + i, onset))
                    if any(isinstance(e, expressions.Fermata) for e in el.expressions):
                        marks.append(Mark("calderón", "calderón", group, base + i, onset))
                for d in flat.getElementsByClass(dynamics.Dynamic):
                    marks.append(Mark("dinámica", d.value, group, base + i, float(d.offset)))
        # music21 guarda los reguladores del piano en la partitura, no en cada pentagrama.
        for sp in score.spannerBundle:
            if not isinstance(sp, dynamics.Crescendo | dynamics.Diminuendo):
                continue
            first = sp.getFirst()
            if first is None or id(first) not in where_of:
                continue
            index, group, onset = where_of[id(first)]
            kind = "cresc." if isinstance(sp, dynamics.Crescendo) else "dim."
            marks.append(Mark("regulador", kind, group, index, onset))
        measures.extend(page_measures[i] for i in sorted(page_measures))
    return measures, marks


def similarity(a: Counter, b: Counter) -> float:
    total = sum(a.values()) + sum(b.values())
    return 2 * sum((a & b).values()) / total if total else 1.0


def align(a: list[Measure], b: list[Measure], gap: float = 0.3) -> dict[int, tuple[int, float]]:
    """Needleman-Wunsch: compás de `a` -> (compás de `b`, parecido)."""
    n, m = len(a), len(b)
    score = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        score[i][0] = -gap * i
    for j in range(1, m + 1):
        score[0][j] = -gap * j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            score[i][j] = max(
                score[i - 1][j - 1] + similarity(a[i - 1].pitches, b[j - 1].pitches),
                score[i - 1][j] - gap,
                score[i][j - 1] - gap,
            )
    pairs, i, j = {}, n, m
    while i > 0 and j > 0:
        sim = similarity(a[i - 1].pitches, b[j - 1].pitches)
        if abs(score[i][j] - (score[i - 1][j - 1] + sim)) < 1e-9:
            pairs[i - 1] = (j - 1, sim)
            i, j = i - 1, j - 1
        elif abs(score[i][j] - (score[i - 1][j] - gap)) < 1e-9:
            i -= 1
        else:
            j -= 1
    return pairs


def fuse(
    homr: list[Measure],
    homr_marks: list[Mark],
    aud: list[Measure],
    aud_marks: list[Mark],
    threshold: float,
    snap: bool = True,
) -> list[Mark]:
    """Marcas finales en la numeración de HOMR."""
    to_homr = align(aud, homr)
    fused = [mk for mk in homr_marks if mk.kind in ("staccato", "calderón")]
    for mk in aud_marks:
        if mk.kind not in ("dinámica", "regulador") or mk.measure not in to_homr:
            continue
        target, sim = to_homr[mk.measure]
        if sim < threshold:
            continue
        onset = mk.onset
        candidates = homr[target].onsets.get(mk.group) or set().union(
            *homr[target].onsets.values() or [set()]
        )
        if snap and candidates:
            onset = min(candidates, key=lambda o: abs(o - mk.onset))
        fused.append(Mark(mk.kind, mk.value, mk.group, target, onset))
    return fused


def evaluate(
    found: list[Mark],
    to_truth: dict[int, tuple[int, float]],
    truth: list[Mark],
    kinds: tuple[str, ...],
):
    """Aciertos estrictos y laxos por tipo, emparejando cada marca de la verdad con una sola."""
    rows = {}
    for kind in kinds:
        t = [mk for mk in truth if mk.kind == kind]
        f = [
            Mark(mk.kind, mk.value, mk.group, to_truth[mk.measure][0], mk.onset)
            for mk in found
            if mk.kind == kind and mk.measure in to_truth
        ]
        lost = sum(1 for mk in found if mk.kind == kind and mk.measure not in to_truth)
        result = {}
        for label, close in (
            ("estricta", lambda x, y: abs(x.onset - y.onset) <= TOLERANCE + 1e-9),
            ("laxa", lambda x, y: True),
        ):
            free, hits = list(f), 0
            for g in t:
                match = next(
                    (
                        x
                        for x in sorted(free, key=lambda x, g=g: abs(x.onset - g.onset))
                        if x.value == g.value
                        and x.group == g.group
                        and x.measure == g.measure
                        and close(x, g)
                    ),
                    None,
                )
                if match is not None:
                    free.remove(match)
                    hits += 1
            result[label] = hits
        rows[kind] = (len(t), len(f) + lost, result["estricta"], result["laxa"])
    return rows


def report(title: str, rows: dict) -> None:
    print(f"  {title}")
    for kind, (n_truth, n_found, strict, loose) in rows.items():
        precision = strict / n_found if n_found else 0.0
        print(
            f"    {kind:10s} verdad {n_truth:3d} | propuestas {n_found:3d} | "
            f"bien colocadas {strict:3d} ({strict / n_truth:.0%} de la verdad, "
            f"{precision:.0%} de lo propuesto) | mismo compás {loose:3d}"
        )


def printed_dynamics(mscx: Path) -> set[tuple[str, int, str]]:
    """Dinámicas impresas del original de OpenScore: el MusicXML de MuseScore 3.6.2 pierde la
    marca de invisible de las 29 que OpenScore añadió solo para la reproducción."""
    root = ET.parse(mscx).getroot()
    printed = set()
    for staff in root.iter("Staff"):
        if staff.get("id") is None:
            continue
        group = GROUP.get(int(staff.get("id")) - 1, "piano")
        for i, measure in enumerate(staff.findall("Measure")):
            for dyn in measure.iter("Dynamic"):
                if dyn.findtext("visible") != "0":
                    printed.add((group, i, dyn.findtext("subtype")))
    return printed


def main(datos: Path) -> None:
    truth_measures, truth_marks = load([datos / "mondnacht.musicxml"])
    printed = printed_dynamics(datos / "lc4987640.mscx")
    truth_marks = [
        mk
        for mk in truth_marks
        if mk.kind != "dinámica" or (mk.group, mk.measure, mk.value) in printed
    ]
    print(
        "Verdad:",
        dict(Counter(mk.kind for mk in truth_marks)),
        "| dinámicas impresas:",
        sorted(printed),
    )
    for variant in ("mondnacht", "mondnacht-foto"):
        homr, homr_marks = load([datos / f"homr-{variant}-p-{p}.musicxml" for p in ("09", "10")])
        aud, aud_marks = load([datos / f"audiveris-{variant}-p-{p}.mxl" for p in ("09", "10")])
        homr_to_truth = align(homr, truth_measures)
        aud_to_truth = align(aud, truth_measures)
        aud_to_homr = align(aud, homr)
        same = sum(1 for k, (v, _) in homr_to_truth.items() if k == v)
        sims = sorted(s for _, s in aud_to_homr.values())
        print(
            f"\n=== {variant}: compases HOMR {len(homr)}, Audiveris {len(aud)}, "
            f"verdad {len(truth_measures)}; HOMR->verdad emparejados {len(homr_to_truth)} "
            f"(idénticos a su número {same}); parecido Audiveris-HOMR por compás: "
            f"mediana {sims[len(sims) // 2]:.2f}, mínimo {sims[0]:.2f}"
        )
        kinds = ("dinámica", "regulador", "staccato", "calderón")
        report(
            "Audiveris solo (sus marcas, sin fusionar)",
            evaluate(aud_marks, aud_to_truth, truth_marks, kinds),
        )
        report("HOMR solo", evaluate(homr_marks, homr_to_truth, truth_marks, kinds))
        for threshold in (0.0, 0.5, 0.7):
            fused = fuse(homr, homr_marks, aud, aud_marks, threshold)
            report(
                f"Fusión (umbral de parecido {threshold})",
                evaluate(fused, homr_to_truth, truth_marks, kinds),
            )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Uso: python fusion.py <carpeta de datos>")
    main(Path(sys.argv[1]))
