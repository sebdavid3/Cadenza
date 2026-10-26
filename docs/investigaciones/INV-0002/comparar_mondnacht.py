"""Mondnacht: HOMR y Audiveris frente a la verdad de OpenScore, página a página (INV-0002).

Uso: python comparar_mondnacht.py <carpeta de datos>

La carpeta tiene la verdad (`mondnacht.musicxml`) y la salida de cada motor por variante y
página: `homr-<variante>-p-<página>.musicxml` y `audiveris-<variante>-p-<página>.mxl`, con
variante `mondnacht` (limpia) o `mondnacht-foto` y página `09` o `10`.

Dos medidas, porque los motores pueden reorganizar pentagramas y compases:
- sin estructura: notas (altura y duración) y marcas de toda la página, sin mirar dónde están;
- por pentagrama: notas de cada pentagrama (voz, mano derecha, mano izquierda), sin mirar el compás.
"""

import sys
from collections import Counter
from pathlib import Path

from music21 import articulations, converter, dynamics, expressions, note, stream

PAGES = {"09": range(1, 35), "10": range(35, 69)}
KINDS = {
    articulations.Staccato: "staccato",
    articulations.Accent: "acento",
    articulations.Tenuto: "tenuto",
    articulations.StrongAccent: "marcato",
}


def read(path: Path, measures: range | None = None):
    score = converter.parse(str(path))
    staves, marks = [], Counter()
    for part in score.parts:
        notes = Counter()
        for measure in part.getElementsByClass(stream.Measure):
            if measures is not None and measure.number not in measures:
                continue
            for el in measure.recurse():
                if isinstance(el, dynamics.Dynamic):
                    marks[f"dinámica {el.value}"] += 1
                elif isinstance(el, note.Rest):
                    continue
                elif isinstance(el, note.GeneralNote) and not isinstance(el, note.Unpitched):
                    for p in el.pitches:
                        notes[(p.nameWithOctave, el.quarterLength)] += 1
                    for a in el.articulations:
                        kind = next((v for k, v in KINDS.items() if isinstance(a, k)), None)
                        marks[kind or type(a).__name__] += 1
                    if any(isinstance(e, expressions.Fermata) for e in el.expressions):
                        marks["calderón"] += 1
        for sp in part.spannerBundle:
            if isinstance(sp, dynamics.Crescendo | dynamics.Diminuendo):
                first = sp.getFirst()
                where = first.getContextByClass(stream.Measure) if first is not None else None
                if measures is None or (where is not None and where.number in measures):
                    kind = "cresc." if isinstance(sp, dynamics.Crescendo) else "dim."
                    marks["regulador " + kind] += 1
        staves.append(notes)
    return staves, marks


def overlap(a: Counter, b: Counter) -> int:
    return sum((a & b).values())


def main(datos: Path) -> None:
    totals: dict[str, Counter] = {}
    for page, measures in PAGES.items():
        truth_staves, truth_marks = read(datos / "mondnacht.musicxml", measures)
        truth_all = sum(truth_staves, Counter())
        print(
            f"\n=== Página {page} (compases {measures.start}-{measures.stop - 1}): "
            f"{sum(truth_all.values())} notas en {len(truth_staves)} pentagramas "
            f"{[sum(s.values()) for s in truth_staves]}; marcas {dict(sorted(truth_marks.items()))}"
        )
        for variant in ("mondnacht", "mondnacht-foto"):
            for engine, path in (
                ("HOMR", datos / f"homr-{variant}-p-{page}.musicxml"),
                ("Audiveris", datos / f"audiveris-{variant}-p-{page}.mxl"),
            ):
                staves, marks = read(path)
                all_notes = sum(staves, Counter())
                hit = overlap(truth_all, all_notes)
                pitch_hit = overlap(
                    Counter(p for p, _ in truth_all.elements()),
                    Counter(p for p, _ in all_notes.elements()),
                )
                per_staff = [overlap(t, s) for t, s in zip(truth_staves, staves, strict=False)]
                mark_hit = overlap(truth_marks, marks)
                key = f"{engine} {'foto' if 'foto' in variant else 'limpio'}"
                t = totals.setdefault(key, Counter())
                t.update(
                    {
                        "notas": sum(truth_all.values()),
                        "leídas": sum(all_notes.values()),
                        "aciertos": hit,
                        "altura": pitch_hit,
                        "marcas": sum(truth_marks.values()),
                        "marcas_ok": mark_hit,
                        "marcas_leídas": sum(marks.values()),
                    }
                )
                print(
                    f"  {key:16s} pentagramas {len(staves)} {[sum(s.values()) for s in staves]} | "
                    f"notas leídas {sum(all_notes.values())}, aciertos {hit} "
                    f"({hit / sum(truth_all.values()):.0%}), solo altura {pitch_hit} | "
                    f"por pentagrama {per_staff} | marcas {mark_hit}/{sum(truth_marks.values())} "
                    f"(leídas {sum(marks.values())}: {dict(sorted(marks.items()))})"
                )

    print("\n=== Total de las dos páginas")
    for key, t in totals.items():
        print(
            f"  {key:16s} notas {t['aciertos']}/{t['notas']} ({t['aciertos'] / t['notas']:.0%}) "
            f"con altura y duración, {t['altura'] / t['notas']:.0%} solo altura, "
            f"leídas {t['leídas']} | marcas {t['marcas_ok']}/{t['marcas']} "
            f"(leídas {t['marcas_leídas']})"
        )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Uso: python comparar_mondnacht.py <carpeta de datos>")
    main(Path(sys.argv[1]))
