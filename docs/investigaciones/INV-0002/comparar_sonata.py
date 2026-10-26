"""Sonata «Claro de luna»: HOMR frente a Audiveris, con y sin tresillos implícitos (INV-0002).

Uso: python comparar_sonata.py <carpeta de datos>

La carpeta tiene la salida de cada motor para la página al doble de tamaño:
`homr-pagina-x2.musicxml`, `audiveris-x2-implicit-false.mxl` y `audiveris-x2-implicit-true.mxl`.
No hay verdad: el script compara los motores entre sí y muestra qué hace Cadenza con cada
lectura (importación, validación con las reglas de la versión instalada y exportación).
"""

import re
import sys
import zipfile
from collections import Counter
from fractions import Fraction
from pathlib import Path

from cadenza.domain import Provenance, ScoreDocument, build_anchor_index
from cadenza.interchange import musicxml_to_score_ir, score_ir_to_musicxml
from cadenza.validation import ValidationEngine
from music21 import converter, dynamics, stream

HOMR = "homr-pagina-x2.musicxml"
AUDIVERIS = "audiveris-x2-implicit-false.mxl"
AUDIVERIS_IMPLICIT = "audiveris-x2-implicit-true.mxl"


def xml_of(path: Path) -> str:
    if path.suffix == ".mxl":
        with zipfile.ZipFile(path) as z:
            name = next(
                n for n in z.namelist() if n.endswith(".xml") and not n.startswith("META-INF")
            )
            return z.read(name).decode("utf-8")
    return path.read_text(encoding="utf-8")


def time_signatures(raw: str) -> list[str]:
    return [" ".join(t.split()) for t in re.findall(r"<time(?:\s[^>]*)?>.*?</time>", raw, re.S)]


def measures_report(path: Path) -> None:
    """Compás, tresillos y sumas por voz de cada compás, y los posibles errores de Cadenza."""
    raw = xml_of(path)
    print(
        f"=== {path.name} | compás {time_signatures(raw)} "
        f"| <time-modification> {raw.count('<time-modification')}"
        f" | <tuplet> {len(re.findall(r'<tuplet ', raw))} | <forward> {raw.count('<forward>')}"
        f" | <backup> {raw.count('<backup>')} | compases {len(re.findall(r'<measure ', raw))}"
    )
    score = musicxml_to_score_ir(raw)
    for p, part in enumerate(score.parts):
        for s, staff in enumerate(part.staves):
            for m in staff.measures:
                evs = [e for e in m.events if not getattr(e, "hidden", False)]
                sums: dict[int, Fraction] = {}
                for e in evs:
                    if not e.is_chord and e.duration_beats:
                        sums[e.voice] = sums.get(e.voice, Fraction(0)) + Fraction(e.duration_beats)
                durs = sorted({str(e.duration_beats) for e in evs})
                trip = sum(
                    1
                    for e in evs
                    if e.duration_beats and Fraction(e.duration_beats).denominator % 3 == 0
                )
                voices = ", ".join(f"{k}: {v}" for k, v in sums.items())
                print(
                    f"  parte {p} pent {s} c{m.number:>2}: {len(evs):>2} ev, tresillo {trip:>2}, "
                    f"duraciones {durs}, suma por voz {{{voices}}}"
                )
    doc = ScoreDocument(
        id="p",
        score=score,
        anchors=build_anchor_index(score),
        provenance=Provenance(omr_engine="comparación"),
    )
    found = [
        (f.rule_id, f.anchor.part, f.anchor.staff, f.anchor.measure)
        for f in ValidationEngine().validate(doc)
    ]
    print("  posibles errores:", found)


def pitches(measure) -> Counter:
    found = Counter()
    for e in measure.events:
        if getattr(e, "hidden", False):
            continue
        for p in getattr(e, "pitches", ()) or ():
            found[str(p)] += 1
        if getattr(e, "pitch", None) is not None:
            found[str(e.pitch)] += 1
    return found


def engines_report(datos: Path) -> None:
    """Atributos de cada compás y alturas por compás: Audiveris con tresillos implícitos y HOMR."""
    engines = {
        "Audiveris": musicxml_to_score_ir(xml_of(datos / AUDIVERIS_IMPLICIT)),
        "HOMR": musicxml_to_score_ir(xml_of(datos / HOMR)),
    }
    for name, score in engines.items():
        for s, staff in enumerate(score.parts[0].staves):
            attrs = [
                (m.number, m.time_signature, m.clef, m.key_signature)
                for m in staff.measures
                if m.time_signature or m.clef or m.key_signature
            ]
            print(f"{name} pent {s}: {attrs}")
    a, h = engines["Audiveris"], engines["HOMR"]
    for s in range(2):
        pairs = zip(a.parts[0].staves[s].measures, h.parts[0].staves[s].measures, strict=False)
        for ma, mh in pairs:
            pa, ph = pitches(ma), pitches(mh)
            common = sum((pa & ph).values())
            print(
                f"pent {s} c{ma.number:>2}: Audiveris {sum(pa.values()):>2} alturas, "
                f"HOMR {sum(ph.values()):>2}, comunes {common:>2} | "
                f"solo Audiveris {dict(pa - ph)} | solo HOMR {dict(ph - pa)}"
            )


def marks_report(datos: Path) -> None:
    """Marcas de cada motor y dónde pone Audiveris cada dinámica."""
    for name in (AUDIVERIS_IMPLICIT, HOMR):
        raw = xml_of(datos / name)
        print(
            f"{name} | dinámicas {re.findall(r'<dynamics[^>]*>\s*<(\w+)', raw)}"
            f" | ligaduras de expresión {len(re.findall(r'<slur ', raw))}"
            f" | reguladores {len(re.findall(r'<wedge ', raw))}"
            f" | textos {re.findall(r'<words[^>]*>([^<]*)<', raw)[:5]}"
        )
    score = converter.parse(str(datos / AUDIVERIS_IMPLICIT))
    for s, part in enumerate(score.parts):
        for m in part.getElementsByClass(stream.Measure):
            for d in m.recurse().getElementsByClass(dynamics.Dynamic):
                print(f"pentagrama {s} compás {m.number} ataque {float(d.offset)}: {d.value}")


def round_trip_report(datos: Path) -> None:
    """¿Conserva Cadenza los tresillos y el ¢ de Audiveris al importar y volver a exportar?"""
    raw = xml_of(datos / AUDIVERIS_IMPLICIT)
    out = score_ir_to_musicxml(musicxml_to_score_ir(raw))
    for name, text in (("Audiveris", raw), ("exportado por Cadenza", out)):
        times = sorted(set(time_signatures(text)))
        print(
            f"{name}: compás {times} | <time-modification> {text.count('<time-modification')}"
            f" | <tuplet {len(re.findall(r'<tuplet ', text))}"
        )


def main(datos: Path) -> None:
    for name in (AUDIVERIS, AUDIVERIS_IMPLICIT, HOMR):
        measures_report(datos / name)
    print()
    engines_report(datos)
    print()
    marks_report(datos)
    print()
    round_trip_report(datos)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Uso: python comparar_sonata.py <carpeta de datos>")
    main(Path(sys.argv[1]))
