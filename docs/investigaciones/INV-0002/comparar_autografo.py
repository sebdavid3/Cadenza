"""Autógrafo de An die Musik: HOMR y Audiveris frente a la verdad de OpenScore (INV-0002).

Uso: python comparar_autografo.py <carpeta de datos>

La carpeta tiene la verdad (`an-die-musik.musicxml`) y la salida de cada motor
(`homr-autografo.musicxml` y `audiveris-autografo.mxl`). La comparación no depende de la
estructura: cuenta notas (altura y duración), silencios y marcas de toda la página.
"""

import sys
from collections import Counter
from pathlib import Path

from music21 import articulations, converter, dynamics, expressions, note, stream

KINDS = {
    articulations.Staccato: "staccato",
    articulations.Accent: "acento",
    articulations.Tenuto: "tenuto",
    articulations.StrongAccent: "marcato",
}


def summary(path: Path):
    score = converter.parse(str(path))
    parts = list(score.parts)
    measures = [len(p.getElementsByClass(stream.Measure)) for p in parts]
    notes, rests = Counter(), Counter()
    marks = Counter()
    for part in parts:
        for el in part.recurse():
            if isinstance(el, dynamics.Dynamic):
                marks[f"dinámica {el.value}"] += 1
            elif isinstance(el, note.Rest):
                rests[el.quarterLength] += 1
            elif isinstance(el, note.GeneralNote) and not isinstance(el, note.Unpitched):
                for p in el.pitches:
                    notes[(p.nameWithOctave, el.quarterLength)] += 1
                for a in el.articulations:
                    kind = next((v for k, v in KINDS.items() if isinstance(a, k)), None)
                    marks[kind or type(a).__name__] += 1
                for e in el.expressions:
                    if isinstance(e, expressions.Fermata):
                        marks["calderón"] += 1
        for sp in part.spannerBundle:
            if isinstance(sp, dynamics.Crescendo | dynamics.Diminuendo):
                kind = "cresc." if isinstance(sp, dynamics.Crescendo) else "dim."
                marks["regulador " + kind] += 1
    return parts, measures, notes, rests, marks


def main(datos: Path) -> None:
    truth = summary(datos / "an-die-musik.musicxml")
    _, t_measures, t_notes, t_rests, t_marks = truth
    print(
        f"VERDAD: {len(truth[0])} partes/pentagramas, compases {t_measures}, "
        f"notas {sum(t_notes.values())}, silencios {sum(t_rests.values())}"
    )
    print("        marcas:", dict(sorted(t_marks.items())))
    for engine, path in (
        ("HOMR", datos / "homr-autografo.musicxml"),
        ("Audiveris", datos / "audiveris-autografo.mxl"),
    ):
        parts, measures, notes, rests, marks = summary(path)
        hit_notes = sum((t_notes & notes).values())
        hit_pitch = sum(
            (
                Counter(p for p, _ in t_notes.elements()) & Counter(p for p, _ in notes.elements())
            ).values()
        )
        print(f"\n{engine}: {len(parts)} partes/pentagramas, compases {measures}")
        print(
            f"   notas leídas {sum(notes.values())} de {sum(t_notes.values())}; "
            f"coinciden en altura y duración {hit_notes}, solo en altura {hit_pitch}"
        )
        print(f"   silencios leídos {sum(rests.values())} de {sum(t_rests.values())}")
        print("   marcas:", dict(sorted(marks.items())))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Uso: python comparar_autografo.py <carpeta de datos>")
    main(Path(sys.argv[1]))
