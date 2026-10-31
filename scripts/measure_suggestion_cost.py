"""Mide lo que la capa de sugerencias añade a la validación de una página real (ADR-0036 §12).

    uv run --no-sync python -P scripts/measure_suggestion_cost.py \\
        --score <página.musicxml|.mei> --model <artefacto.json> [--runs 7]

Lee la página con `cadenza.interchange.read_score` (la salida de HOMR es MusicXML), valida
con las reglas y mide, en pasadas con la caché del modelo vacía, lo que tarda la capa: rasgos,
puntuación, posibles errores propios y el filtro de admisibilidad de los casos de uso. Escribe
el resultado en la salida estándar y en ningún archivo. Falla si falta la página o el
artefacto: sin datos no hay medición (CLAUDE.md §8).
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from pathlib import Path

BUDGET_MS = 300.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--score", required=True, help="Página MusicXML o MEI.")
    parser.add_argument("--model", required=True, help="Artefacto JSON de la capa.")
    parser.add_argument("--runs", type=int, default=7)
    args = parser.parse_args(argv)

    score_path, model_path = Path(args.score), Path(args.model)
    for path in (score_path, model_path):
        if not path.is_file():
            print(f"Error: no existe {path}", file=sys.stderr)
            return 1

    from cadenza.application.suggestions import suggest
    from cadenza.domain import Provenance, ScoreDocument, build_anchor_index
    from cadenza.interchange import read_score
    from cadenza.validation import ValidationEngine
    from cadenza.validation.learned import FrequencyBackoffModel

    score = read_score(score_path)
    document = ScoreDocument(
        id=score_path.stem,
        score=score,
        anchors=build_anchor_index(score),
        provenance=Provenance(omr_engine="page"),
    )
    content = model_path.read_bytes()
    validator = ValidationEngine()
    rules_ms: list[float] = []
    layer_ms: list[float] = []
    produced: list[object] = []
    for _ in range(args.runs):
        start = time.perf_counter()
        findings = validator.validate(document)
        middle = time.perf_counter()
        model = FrequencyBackoffModel.from_bytes(content, version="cost")
        loaded = time.perf_counter()
        produced = list(suggest(document, findings, model))
        end = time.perf_counter()
        rules_ms.append((middle - start) * 1000)
        layer_ms.append((end - loaded) * 1000)
    events = sum(
        len(measure.events)
        for part in score.parts
        for staff in part.staves
        for measure in staff.measures
    )
    median_layer = statistics.median(layer_ms)
    result = {
        "score": str(score_path),
        "events": events,
        "runs": args.runs,
        "rules_ms_median": round(statistics.median(rules_ms), 2),
        "layer_ms_median": round(median_layer, 2),
        "layer_ms_max": round(max(layer_ms), 2),
        "findings_with_layer": len(produced),
        "budget_ms": BUDGET_MS,
        "within_budget": median_layer <= BUDGET_MS,
        "python": platform.python_version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["within_budget"] else 2


if __name__ == "__main__":
    sys.exit(main())
