"""Experimento 15: HOMR sobre el conjunto de referencia del compás, los tresillos, las armaduras
y la voz con piano (#234, ADR-0056). Es la línea base de #237, #238 y #239.

El conjunto lo fija un manifiesto versionado (`reference_set_manifest.json`, junto a este
script): páginas impresas reales de IMSLP (dominio público) con su verdad de OpenScore Lieder
(CC0), y las predicciones de HOMR que ya hay de PrIMuS para el numerador del compás. Los PDF,
las verdades y las predicciones no se versionan (`data/`); el manifiesto guarda su sha256.

Cada página se rasteriza del PDF con `pdftoppm` (poppler) a 300 ppp en `data/reference/pages/`
(`pages`, o `run` si falta la imagen): las imágenes no se dejan hechas a mano, y su sha256
tiene que ser el del manifiesto. Después se transcribe con `HOMREngine` (en CPU, como en
producción, salvo `--gpu`) y se compara con la verdad de los compases de esa página, rasgo a
rasgo:

1. **El compás por tramo, con su símbolo.** Cada inicio de tramo que la página imprime (al
   principio de la pieza, a mitad de página o al principio de una página que cambia) se busca
   entre los cambios que leyó HOMR en cada pentagrama; se dice si lo leyó, si la métrica es la
   buena y si también la grafía (C y ¢, `TimeSignature.same_notation`). Compás a compás, la
   métrica y la grafía de cada pentagrama; el símbolo, con `time_symbol_agreement` (#236). Los
   compases de un tramo que empezó en una página anterior no llevan indicación impresa: se
   cuentan aparte (`inherited`), porque HOMR no puede leerla.
2. **Los tresillos por compás.** Un evento es de tresillo si su figura tiene un 3 en el
   denominador (ADR-0044 §3). Cada compás de la verdad con tresillos se busca en la lectura
   (en cualquier pentagrama), separando los marcados de los implícitos (sin número,
   `show-number="none"` en el MusicXML de la verdad); y cada compás de la lectura con tresillos,
   en la verdad.
3. **La armadura por compás**: la del principio de la página, cada cambio a mitad de página y
   la de cada compás.
4. **Las partes y los pentagramas**: cuántas partes y cuántos pentagramas por parte (voz y
   piano son dos partes, de 1 y 2 pentagramas), y si el contenido de cada pentagrama leído va en
   el suyo, compás a compás (`staves`, ADR-0060 §3).

PrIMuS (renders de Verovio, no escaneos): el compás inicial de cada incipit, numerador y
denominador, frente a su verdad MEI, y el símbolo C y ¢ con `time_symbol_agreement`, sobre las
predicciones de HOMR que ya existen (`exp_04` y `exp_12`), sin transcribir de nuevo.

**Alineación.** HOMR numera los compases de la página desde 1 y puede leer alguno de más o de
menos (una indicación de cortesía a final de sistema o un compás partido entre dos sistemas
salen como un compás aparte). El compás p de la página (de 0 a n_verdad - 1) se compara con el
compás q = redondeo(p · (n_HOMR - 1) / (n_verdad - 1)) de la lectura, y un cambio o un tresillo
cuenta como leído si está a `--tolerance` compases o menos de q (1 por defecto). Las cifras
dependen de esa tolerancia, que va en el resultado. Un cambio que HOMR lee en el último compás
por la indicación de cortesía del cambio de la página siguiente se cuenta como `courtesy`, no
como un cambio de más. Una columna de compases vacía en todos los pentagramas leídos (la
cortesía leída como un compás aparte) se quita antes de alinear (`prepare_read_staves`).
Los pentagramas leídos se emparejan en orden con los de la verdad, que son las unidades: uno que
HOMR no lee, o una página que no lee, cuenta como no leído. Cada cambio o compás con tresillos
leído empareja como mucho uno de la verdad.

PrIMuS se lee primero y en paralelo (`--workers`); lo que el dominio no admite (una verdad o una
predicción ilegible) se registra por incipit y no se mide, como en `exp_12`. Sus proporciones se
dan sobre los incipits medidos y con los fallos de HOMR como mal leídos (`*_with_failures`).

Sin el manifiesto, o si falta uno de sus archivos o su sha256 no coincide, el experimento falla
con la lista de lo que falta: no tiene modo sintético ni valores de reserva (CLAUDE.md §8).

**La etapa del compás (#237, ADR-0059).** Con `--meter-features` (por defecto, ninguno), la
lectura de HOMR de cada página y de cada incipit pasa por la etapa de Cadenza que corre tras
HOMR en producción (`cadenza.omr.recognize_meter`) con esos rasgos antes de compararla: así se
mide la etapa rasgo a rasgo con el mismo conjunto. Sin rasgos, se mide HOMR solo. Con rasgos,
cada incipit de PrIMuS da además la SER antes y después de la etapa y, si la etapa cambió la
métrica o las figuras, el OMR-NED antes y después (MusicXML exportados del `ScoreIR` sin el
símbolo del compás, como `exp_14`, ADR-0044 §1): `omr_quality` dice si la etapa empeora el resto.

Salidas (`--output-dir`, por defecto `results/`, sin versionar):
- `reference_set_summary.json`: la medición completa, con `run_info`.
- `reference_set_pages.csv`: una fila por página.
- `reference_set_primus.csv`: una fila por incipit de PrIMuS.
- `reference_set_predictions/<caso>.musicxml`: el MusicXML de HOMR de cada página.
- `exp_15_run_info.json`.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from collections import Counter
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Protocol
from xml.etree import ElementTree

from cadenza.domain import EventKind, Measure, Part, ScoreIR, Staff, TimeSignature
from cadenza.domain.time_signature import COMMON, CUT
from cadenza.interchange import Music21ScoreExporter, musicxml_to_score_ir, read_score
from cadenza.learning import (
    omr_ned_pair,
    score_ser_pair,
    time_symbol_agreement,
    without_time_symbols,
)
from cadenza.omr.meter_stage import (
    METER_STAGE_VERSION,
    MeterFeature,
    features_label,
    parse_meter_features,
    recognize_meter,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ml.experiments.common import (  # noqa: E402
    DATA_DIR,
    RESULTS_DIR,
    get_run_info,
    sample_size_justification,
    sha256_of_file,
)

EXPERIMENT = "exp_15"
MANIFEST_PATH = Path(__file__).resolve().parent / "reference_set_manifest.json"
SUMMARY_NAME = "reference_set_summary.json"
PAGES_CSV_NAME = "reference_set_pages.csv"
PRIMUS_CSV_NAME = "reference_set_primus.csv"
RUN_INFO_NAME = "exp_15_run_info.json"
PREDICTIONS_DIR_NAME = "reference_set_predictions"
PREDICTIONS_INDEX_NAME = "index.json"
DEFAULT_TOLERANCE = 1
DEFAULT_MAX_WORKERS = 8

# Rasgos que el conjunto tiene que cubrir (criterio 1 de #234).
REQUIRED_FEATURES: tuple[str, ...] = (
    "time_numerator",
    "time_symbol_common",
    "time_symbol_cut",
    "time_change",
    "tuplets_marked",
    "tuplets_implicit",
    "key_change",
    "voice_piano",
)


class ReferenceSetError(RuntimeError):
    """El conjunto de referencia no está completo o no es el del manifiesto."""


class MusicXMLTranscriber(Protocol):
    """Lo que el experimento necesita del motor: el MusicXML nativo de una imagen."""

    def transcribe_musicxml(self, image_path: Path) -> str: ...


# --------------------------------------------------------------------------------------------
# Manifiesto
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceFile:
    """Un archivo del conjunto (un PDF o una verdad), con su ruta bajo `data/` y su sha256."""

    id: str
    path: str
    sha256: str
    meta: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PageCase:
    """Una página de un PDF con los compases de la verdad que contiene."""

    id: str
    scan: str
    pdf_page: int
    truth: str
    first_measure: int
    last_measure: int
    features: tuple[str, ...]
    image: str
    image_sha256: str
    meta: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PrimusSource:
    """Un juego de predicciones de HOMR sobre PrIMuS con su manifiesto de `data/` (cuyas rutas
    son relativas a `data/`, como las de `corpus.py` y `exp_12`)."""

    id: str
    manifest: str
    manifest_sha256: str
    predictions: str
    predictions_sha256: str
    meta: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Rasterization:
    tool: str
    tool_version: str
    dpi: int


@dataclass(frozen=True)
class ReferenceManifest:
    path: Path
    rasterization: Rasterization
    scans: Mapping[str, SourceFile]
    truths: Mapping[str, SourceFile]
    cases: tuple[PageCase, ...]
    primus: tuple[PrimusSource, ...]
    raw: Mapping[str, Any]


def _meta(item: Mapping[str, Any], known: Iterable[str]) -> dict[str, Any]:
    keys = set(known)
    return {key: value for key, value in item.items() if key not in keys}


def load_manifest(path: Path = MANIFEST_PATH) -> ReferenceManifest:
    """Lee el manifiesto; falla si no existe o le falta algún campo."""

    if not path.is_file():
        raise ReferenceSetError(f"falta el manifiesto del conjunto de referencia: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        raster = raw["rasterization"]
        scans = {
            item["id"]: SourceFile(
                item["id"], item["path"], item["sha256"], _meta(item, ("id", "path", "sha256"))
            )
            for item in raw["scans"]
        }
        truths = {
            item["id"]: SourceFile(
                item["id"], item["path"], item["sha256"], _meta(item, ("id", "path", "sha256"))
            )
            for item in raw["truths"]
        }
        case_keys = ("id", "scan", "pdf_page", "truth", "measures", "features", "image")
        cases = tuple(
            PageCase(
                id=item["id"],
                scan=item["scan"],
                pdf_page=int(item["pdf_page"]),
                truth=item["truth"],
                first_measure=int(item["measures"][0]),
                last_measure=int(item["measures"][1]),
                features=tuple(item["features"]),
                image=item["image"]["path"],
                image_sha256=item["image"]["sha256"],
                meta=_meta(item, case_keys),
            )
            for item in raw["cases"]
        )
        primus_keys = ("id", "manifest", "predictions")
        primus = tuple(
            PrimusSource(
                id=item["id"],
                manifest=item["manifest"]["path"],
                manifest_sha256=item["manifest"]["sha256"],
                predictions=item["predictions"]["path"],
                predictions_sha256=item["predictions"]["sha256"],
                meta=_meta(item, primus_keys),
            )
            for item in raw["primus"]
        )
        rasterization = Rasterization(
            tool=str(raster["tool"]),
            tool_version=str(raster["tool_version"]),
            dpi=int(raster["dpi"]),
        )
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise ReferenceSetError(f"el manifiesto {path} no es válido: {exc!r}") from exc

    for case in cases:
        if case.scan not in scans:
            raise ReferenceSetError(f"el caso {case.id} cita un PDF que no está: {case.scan}")
        if case.truth not in truths:
            raise ReferenceSetError(f"el caso {case.id} cita una verdad que no está: {case.truth}")
        if case.first_measure > case.last_measure:
            raise ReferenceSetError(f"el caso {case.id} tiene los compases al revés")
    ids = [case.id for case in cases]
    if len(set(ids)) != len(ids):
        raise ReferenceSetError("el manifiesto repite el id de un caso")
    return ReferenceManifest(path, rasterization, scans, truths, cases, primus, raw)


def predictions_digest(folder: Path) -> str:
    """Huella de un directorio de predicciones: el sha256 de la lista ordenada de los MusicXML
    y de `failures.json` con el sha256 de cada uno. Cambia si se añade, quita o cambia uno."""

    lines = [
        f"{path.name}\t{sha256_of_file(path)}\n"
        for path in sorted(folder.glob("*.musicxml"), key=lambda item: item.name)
        + ([folder / "failures.json"] if (folder / "failures.json").is_file() else [])
    ]
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def verify_sources(manifest: ReferenceManifest, data_dir: Path, *, primus: bool = True) -> None:
    """Comprueba que cada PDF, verdad (y su original `.mscx`), manifiesto y juego de predicciones
    de PrIMuS (si `primus`) existe y es el del manifiesto. Junta todos los problemas en un solo
    error."""

    problems: list[str] = []

    def check(label: str, path: Path, expected: str) -> None:
        if not path.is_file():
            problems.append(f"falta {label}: {path}")
        elif sha256_of_file(path) != expected:
            problems.append(f"{label}: su sha256 no es el del manifiesto: {path}")

    for scan in manifest.scans.values():
        check(f"el PDF {scan.id}", data_dir / scan.path, scan.sha256)
    for truth in manifest.truths.values():
        check(f"la verdad {truth.id}", data_dir / truth.path, truth.sha256)
        original = truth.meta.get("original")
        if original is not None:
            check(
                f"el original de la verdad {truth.id}",
                data_dir / str(original),
                str(truth.meta.get("original_sha256", "")),
            )
    for source in manifest.primus if primus else ():
        check(f"el manifiesto de {source.id}", data_dir / source.manifest, source.manifest_sha256)
        folder = data_dir / source.predictions
        if not folder.is_dir():
            problems.append(f"faltan las predicciones de {source.id}: {folder}")
        elif predictions_digest(folder) != source.predictions_sha256:
            problems.append(
                f"las predicciones de {source.id}: su huella no es la del manifiesto (se añadió, "
                f"quitó o cambió alguna): {folder}"
            )
    if problems:
        raise ReferenceSetError(
            "el conjunto de referencia no está completo o no es el del manifiesto "
            f"({manifest.path}):\n- " + "\n- ".join(problems)
        )


# --------------------------------------------------------------------------------------------
# Rasterizar las páginas
# --------------------------------------------------------------------------------------------


def find_pdftoppm(explicit: str | None) -> str:
    exe = explicit or shutil.which("pdftoppm")
    if exe is None:
        raise ReferenceSetError(
            "no se encuentra pdftoppm (poppler), con el que el manifiesto rasteriza las páginas: "
            "instálalo o pásalo con --pdftoppm"
        )
    return exe


def pdftoppm_version(exe: str) -> str:
    proc = subprocess.run([exe, "-v"], capture_output=True, text=True, check=False)
    match = re.search(r"version\s+([\w.]+)", proc.stderr + proc.stdout)
    if match is None:
        raise ReferenceSetError(f"no se pudo leer la versión de {exe}")
    return match.group(1)


def rasterize_page(exe: str, pdf: Path, page: int, dpi: int, target: Path) -> None:
    """Una página del PDF a PNG con `pdftoppm -r <dpi> -f <p> -l <p> -png -singlefile`."""

    target.parent.mkdir(parents=True, exist_ok=True)
    prefix = target.with_suffix("")
    proc = subprocess.run(
        [
            exe,
            "-r",
            str(dpi),
            "-f",
            str(page),
            "-l",
            str(page),
            "-png",
            "-singlefile",
            str(pdf),
            str(prefix),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    produced = prefix.with_suffix(".png")
    if proc.returncode != 0 or not produced.is_file():
        raise ReferenceSetError(
            f"pdftoppm no pudo rasterizar la página {page} de {pdf}: {proc.stderr.strip()}"
        )
    if produced != target:
        produced.replace(target)


def prepare_pages(
    manifest: ReferenceManifest,
    data_dir: Path,
    pages_dir: Path,
    pdftoppm: str | None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Rasteriza las páginas que faltan (o todas, con `force`) y comprueba que cada imagen es la
    del manifiesto. Devuelve la herramienta usada y qué páginas se generaron."""

    exe: str | None = None
    version: str | None = None
    generated: list[str] = []
    for case in manifest.cases:
        target = pages_dir / case.image
        if force or not target.is_file():
            if exe is None:
                exe = find_pdftoppm(pdftoppm)
                version = pdftoppm_version(exe)
            rasterize_page(
                exe,
                data_dir / manifest.scans[case.scan].path,
                case.pdf_page,
                manifest.rasterization.dpi,
                target,
            )
            generated.append(case.id)
    mismatched = [
        f"{case.id} ({pages_dir / case.image})"
        for case in manifest.cases
        if sha256_of_file(pages_dir / case.image) != case.image_sha256
    ]
    if mismatched:
        raise ReferenceSetError(
            "las imágenes de estas páginas no son las del manifiesto (sha256 distinto), "
            f"rasterizadas con {manifest.rasterization.tool} "
            f"{version or '(no se ha ejecutado)'}; el manifiesto se hizo con "
            f"{manifest.rasterization.tool} {manifest.rasterization.tool_version} a "
            f"{manifest.rasterization.dpi} ppp. Otra versión puede dar otros píxeles: se mediría "
            "otra entrada. Bórralas y vuelve a generarlas con esa versión, o actualiza el "
            "manifiesto a propósito:\n- " + "\n- ".join(mismatched)
        )
    return {
        "tool": manifest.rasterization.tool,
        "tool_version_used": version,
        "dpi": manifest.rasterization.dpi,
        "generated": generated,
        "pages_dir": str(pages_dir),
    }


# --------------------------------------------------------------------------------------------
# Comparación de una página
# --------------------------------------------------------------------------------------------

Notation = tuple[int, int, str | None] | None


def notation(signature: TimeSignature | None) -> Notation:
    if signature is None:
        return None
    return (signature.beats, signature.beat_type, signature.symbol)


def meter(value: Notation) -> tuple[int, int] | None:
    """La métrica sin la grafía: C y 4/4 son la misma."""

    return None if value is None else (value[0], value[1])


def notation_label(value: Notation) -> str | None:
    if value is None:
        return None
    beats, beat_type, symbol = value
    if symbol == COMMON:
        return "C"
    if symbol == CUT:
        return "¢"
    return f"{beats}/{beat_type}"


def tuplet_notes(measure: Measure) -> int:
    """Eventos de tresillo del compás: los de figura con un 3 en el denominador (ADR-0044)."""

    return sum(
        1
        for event in measure.events
        if event.duration_beats is not None and event.duration_beats.denominator % 3 == 0
    )


def effective_keys(measures: Sequence[Measure]) -> list[int]:
    """La armadura vigente en cada compás, en quintas; sin ninguna, 0 (Do mayor)."""

    keys: list[int] = []
    current = 0
    for measure in measures:
        if measure.key_signature is not None:
            current = measure.key_signature.fifths
        keys.append(current)
    return keys


def map_index(position: int, truth_count: int, read_count: int) -> int:
    """El compás de la lectura que corresponde al compás `position` de la página (proporcional)."""

    if read_count <= 0:
        raise ValueError("read_count must be > 0")
    if truth_count <= 1:
        return 0
    return math.floor(position * (read_count - 1) / (truth_count - 1) + 0.5)


def _read_changes(values: Sequence[Any], *, first_counts: bool) -> list[int]:
    """Posiciones donde la lectura cambia de valor; la primera, si `first_counts` y no es None."""

    found: list[int] = []
    for index, value in enumerate(values):
        if index == 0:
            if first_counts and value is not None:
                found.append(0)
        elif value != values[index - 1] and value is not None:
            found.append(index)
    return found


def _truth_staff(score: ScoreIR) -> tuple[Measure, ...]:
    if not score.parts or not score.parts[0].staves:
        raise ReferenceSetError("la verdad no tiene ningún pentagrama")
    return score.parts[0].staves[0].measures


def _page_indices(measures: Sequence[Measure], first: int, last: int) -> list[int]:
    indices = [i for i, m in enumerate(measures) if first <= m.number <= last]
    expected = list(range(indices[0], indices[0] + len(indices))) if indices else []
    if not indices or indices != expected or len(indices) != last - first + 1:
        raise ReferenceSetError(
            f"la verdad no tiene los compases {first}-{last} seguidos y numerados de uno en uno"
        )
    return indices


def _read_staves(score: ScoreIR) -> list[tuple[Measure, ...]]:
    return [staff.measures for part in score.parts for staff in part.staves if staff.measures]


@dataclass(frozen=True)
class ReadStaff:
    """Un pentagrama de la lectura sin los compases de cortesía.

    HOMR crea un compás sin ningún evento, en todos los pentagramas a la vez, con la indicación
    de cortesía del final de un sistema (el compás o la armadura del cambio que viene). Esa
    columna vacía se quita antes de alinear: a mitad de página, su armadura pasa al compás
    siguiente (el compás ya lo lleva por contexto); al final, queda como `trailing`, la cortesía
    del cambio de la página siguiente. Un compás vacío en un solo pentagrama no se quita: HOMR
    reparte a veces las notas de un sistema entre pentagramas de otra manera."""

    measures: tuple[Measure, ...]
    trailing: Measure | None
    dropped: int


def courtesy_columns(staves: Sequence[Sequence[Measure]]) -> set[int]:
    """Las posiciones de compás sin ningún evento en ningún pentagrama de la lectura."""

    longest = max((len(staff) for staff in staves), default=0)
    return {
        q for q in range(longest) if all(not staff[q].events for staff in staves if q < len(staff))
    }


def split_courtesy(staff: Sequence[Measure], columns: set[int]) -> ReadStaff:
    kept: list[Measure] = []
    pending: Measure | None = None
    dropped = 0
    for index, measure in enumerate(staff):
        current = measure
        if (
            pending is not None
            and pending.key_signature is not None
            and current.key_signature is None
        ):
            current = replace(current, key_signature=pending.key_signature)
        if index in columns:
            dropped += 1
            pending = current
            continue
        pending = None
        kept.append(current)
    return ReadStaff(tuple(kept), pending, dropped)


def prepare_read_staves(staves: Sequence[Sequence[Measure]]) -> list[ReadStaff]:
    columns = courtesy_columns(staves)
    return [split_courtesy(staff, columns) for staff in staves]


def _measures_score(measures: Sequence[Measure]) -> ScoreIR:
    return ScoreIR(parts=(Part(id="p", staves=(Staff(id="s", measures=tuple(measures)),)),))


def _staff_units(
    read_staves: Sequence[Sequence[Measure]], truth_staves: int | None
) -> tuple[list[ReadStaff | None], int]:
    """Un elemento por pentagrama de la verdad (o por pentagrama leído, sin `truth_staves`): el
    pentagrama leído del mismo orden, o None si HOMR no lo leyó o lo dejó vacío. Las unidades de
    las proporciones son los pentagramas de la verdad: uno que HOMR no lee cuenta como fallo, y uno
    de más no cuenta (se dice cuántos, `extra_read_staves`)."""

    prepared = prepare_read_staves(read_staves)
    units = len(prepared) if truth_staves is None else truth_staves
    paired: list[ReadStaff | None] = [
        staff if staff.measures else None for staff in prepared[:units]
    ]
    paired += [None] * (units - len(paired))
    return paired, max(0, len(prepared) - units)


def _match(
    candidates: Sequence[int],
    center: int,
    tolerance: int,
    used: set[int],
    right: Collection[int] = (),
) -> int | None:
    """El cambio leído que corresponde a uno de la verdad: dentro de la tolerancia y sin usar ya
    por otro, uno de los que leen el valor bueno (`right`) y, si no hay o si hay varios, el más
    cercano."""

    inside = [c for c in candidates if c not in used and abs(c - center) <= tolerance]
    if not inside:
        return None
    q = min(inside, key=lambda c: (c not in right, abs(c - center), c))
    used.add(q)
    return q


def compare_time(
    truth_measures: Sequence[Measure],
    page: Sequence[int],
    read_staves: Sequence[Sequence[Measure]],
    tolerance: int,
    truth_staves: int | None = None,
) -> dict[str, Any]:
    """El compás por tramo y por compás, pentagrama a pentagrama."""

    first, last = page[0], page[-1]
    n_truth = len(page)
    truth = [notation(truth_measures[i].time_signature) for i in page]
    before = notation(truth_measures[first - 1].time_signature) if first > 0 else None
    printed = [
        p
        for p in range(n_truth)
        if truth[p] is not None and truth[p] != (truth[p - 1] if p else before)
    ]
    courtesy: Notation = None  # el compás que viene en la página siguiente, si cambia
    if last + 1 < len(truth_measures):
        following = notation(truth_measures[last + 1].time_signature)
        if following is not None and following != truth[-1]:
            courtesy = following
    inherited_until = printed[0] if printed else n_truth  # compases sin indicación impresa

    segments = [
        {
            "start": p,
            "measure": truth_measures[first + p].number,
            "label": notation_label(truth[p]),
            "at_page_start": p == 0,
        }
        for p in printed
    ]
    counts: Counter[str] = Counter()
    changes_detail: list[dict[str, Any]] = []
    aligned_truth: list[Measure] = []
    aligned_read: list[Measure] = []
    staves_detail: list[dict[str, Any]] = []
    units, extra = _staff_units(read_staves, truth_staves)
    counts["extra_read_staves"] += extra
    for staff_index, prepared in enumerate(units):
        for p in printed:
            counts[f"segments_{'page_start' if p == 0 else 'mid_page'}"] += 1
        counts["courtesy_changes"] += courtesy is not None
        for p in range(n_truth):
            counts[f"{'inherited' if p < inherited_until else 'printed'}_measures"] += 1
        if prepared is None:
            counts["missing_staves"] += 1
            for p in range(n_truth):
                group = "inherited" if p < inherited_until else "printed"
                counts[f"{group}_measures_missing"] += 1
            continue
        staff = prepared.measures
        counts["empty_measures_dropped"] += prepared.dropped
        read = [notation(m.time_signature) for m in staff]
        n_read = len(read)
        read_changes = _read_changes(read, first_counts=True)
        used: set[int] = set()
        for p in printed:
            q = _match(
                read_changes,
                map_index(p, n_truth, n_read),
                tolerance,
                used,
                {c for c in read_changes if meter(read[c]) == meter(truth[p])},
            )
            kind = "page_start" if p == 0 else "mid_page"
            meter_ok = q is not None and meter(read[q]) == meter(truth[p])
            notation_ok = q is not None and read[q] == truth[p]
            counts[f"segments_{kind}_detected"] += q is not None
            counts[f"segments_{kind}_meter_correct"] += meter_ok
            counts[f"segments_{kind}_notation_correct"] += notation_ok
            changes_detail.append(
                {
                    "staff": staff_index,
                    "measure": truth_measures[first + p].number,
                    "truth": notation_label(truth[p]),
                    "read": notation_label(read[q]) if q is not None else None,
                    "read_at": q,
                    "meter_correct": meter_ok,
                    "notation_correct": notation_ok,
                }
            )
        # La cortesía del final: una columna vacía con la indicación (`trailing`) o un cambio
        # leído en los últimos compases.
        trailing = None if prepared.trailing is None else notation(prepared.trailing.time_signature)
        courtesy_read: Notation = trailing if trailing not in (None, read[-1]) else None
        if courtesy is not None:
            if courtesy_read is None:
                q = _match(read_changes, n_read - 1, tolerance, used)
                courtesy_read = None if q is None else read[q]
            counts["courtesy_changes_read"] += courtesy_read is not None
            counts["courtesy_changes_meter_correct"] += courtesy_read is not None and meter(
                courtesy_read
            ) == meter(courtesy)
        elif courtesy_read is not None:
            counts["spurious_courtesy_changes"] += 1
        spurious = [q for q in read_changes if q not in used]
        counts["spurious_changes"] += len(spurious)

        for p in range(n_truth):
            q = min(map_index(p, n_truth, n_read), n_read - 1)
            group = "inherited" if p < inherited_until else "printed"
            if read[q] is None:
                counts[f"{group}_measures_missing"] += 1
            elif meter(read[q]) == meter(truth[p]):
                counts[f"{group}_measures_meter_correct"] += 1
                counts[f"{group}_measures_notation_correct"] += read[q] == truth[p]
            if group == "printed":
                aligned_truth.append(truth_measures[first + p])
                aligned_read.append(staff[q])
        staves_detail.append(
            {
                "staff": staff_index,
                "measures": n_read,
                "empty_measures_dropped": prepared.dropped,
                "segments": [{"start": q, "label": notation_label(read[q])} for q in read_changes],
                "courtesy_read": notation_label(courtesy_read),
                "spurious_changes": spurious,
            }
        )
    symbol = time_symbol_agreement(_measures_score(aligned_read), _measures_score(aligned_truth))
    # Un pentagrama que HOMR no lee tampoco lee el símbolo de los compases que lo llevan.
    with_symbol = sum(1 for p in range(inherited_until, n_truth) if (truth[p] or (0, 0, None))[2])
    symbol["wrong"] += counts["missing_staves"] * with_symbol
    return {
        "truth_segments": segments,
        "inherited_measures_per_staff": inherited_until,
        "courtesy_after_page": notation_label(courtesy),
        "counts": dict(sorted(counts.items())),
        "symbol_agreement": symbol,
        "changes": changes_detail,
        "read_staves": staves_detail,
    }


def compare_keys(
    truth_measures: Sequence[Measure],
    page: Sequence[int],
    read_staves: Sequence[Sequence[Measure]],
    tolerance: int,
    truth_staves: int | None = None,
) -> dict[str, Any]:
    """La armadura al principio de la página, en cada cambio y en cada compás."""

    all_keys = effective_keys(truth_measures)
    first, last = page[0], page[-1]
    truth = [all_keys[i] for i in page]
    n_truth = len(truth)
    changes = [p for p in range(1, n_truth) if truth[p] != truth[p - 1]]
    courtesy = (
        all_keys[last + 1] if last + 1 < len(all_keys) and all_keys[last + 1] != truth[-1] else None
    )
    counts: Counter[str] = Counter()
    detail: list[dict[str, Any]] = []
    units, extra = _staff_units(read_staves, truth_staves)
    counts["extra_read_staves"] += extra
    for staff_index, prepared in enumerate(units):
        counts["page_starts"] += 1
        counts["changes"] += len(changes)
        counts["courtesy_changes"] += courtesy is not None
        counts["measures"] += n_truth
        if prepared is None:
            counts["missing_staves"] += 1
            continue
        staff = prepared.measures
        read = effective_keys(staff)
        n_read = len(read)
        counts["page_starts_correct"] += read[0] == truth[0]
        read_changes = _read_changes(read, first_counts=False)
        used: set[int] = set()
        for p in changes:
            q = _match(
                read_changes,
                map_index(p, n_truth, n_read),
                tolerance,
                used,
                {c for c in read_changes if read[c] == truth[p]},
            )
            counts["changes_detected"] += q is not None
            correct = q is not None and read[q] == truth[p]
            counts["changes_correct"] += correct
            detail.append(
                {
                    "staff": staff_index,
                    "measure": truth_measures[first + p].number,
                    "truth": truth[p],
                    "read": read[q] if q is not None else None,
                    "read_at": q,
                    "correct": correct,
                }
            )
        trailing = (
            None
            if prepared.trailing is None or prepared.trailing.key_signature is None
            else prepared.trailing.key_signature.fifths
        )
        courtesy_read = trailing if trailing is not None and trailing != read[-1] else None
        if courtesy is not None:
            if courtesy_read is None:
                q = _match(read_changes, n_read - 1, tolerance, used)
                courtesy_read = None if q is None else read[q]
            counts["courtesy_changes_read"] += courtesy_read is not None
            counts["courtesy_changes_correct"] += courtesy_read == courtesy
        elif courtesy_read is not None:
            counts["spurious_courtesy_changes"] += 1
        counts["spurious_changes"] += sum(1 for q in read_changes if q not in used)
        for p in range(n_truth):
            q = min(map_index(p, n_truth, n_read), n_read - 1)
            counts["measures_correct"] += read[q] == truth[p]
    return {
        "truth_start": truth[0],
        "courtesy_after_page": courtesy,
        "truth_changes": [
            {"measure": truth_measures[first + p].number, "fifths": truth[p]} for p in changes
        ],
        "counts": dict(sorted(counts.items())),
        "changes": detail,
    }


def compare_tuplets(
    truth_staves: Sequence[Sequence[Measure]],
    page: Sequence[int],
    read_staves: Sequence[Sequence[Measure]],
    kinds: Mapping[int, str],
    tolerance: int,
) -> dict[str, Any]:
    """Los compases con tresillos de la verdad (por clase) y de la lectura, en cualquier
    pentagrama, emparejados uno a uno: cada compás leído empareja como mucho uno de la verdad
    (el más cercano), para que un compás leído no cuente por dos de la verdad vecinos."""

    n_truth = len(page)
    read_staves = [prepared.measures for prepared in prepare_read_staves(read_staves)]
    truth_counts = [
        sum(tuplet_notes(staff[i]) for staff in truth_staves if i < len(staff)) for i in page
    ]
    numbers = [truth_staves[0][i].number for i in page]
    n_read = max((len(staff) for staff in read_staves), default=0)
    read_counts = [
        sum(tuplet_notes(staff[q]) for staff in read_staves if q < len(staff))
        for q in range(n_read)
    ]
    counts: Counter[str] = Counter()
    counts["truth_notes"] = sum(truth_counts)
    counts["read_notes"] = sum(read_counts)
    read_with = [q for q, c in enumerate(read_counts) if c]
    truth_with = [p for p, c in enumerate(truth_counts) if c]
    pairs = sorted(
        (abs(map_index(p, n_truth, n_read) - q), p, q)
        for p in truth_with
        for q in read_with
        if abs(map_index(p, n_truth, n_read) - q) <= tolerance
    )
    matched: dict[int, int] = {}
    for _distance, p, q in pairs:
        if p not in matched and q not in matched.values():
            matched[p] = q
    detail: list[dict[str, Any]] = []
    for p in truth_with:
        kind = kinds.get(numbers[p], "unknown")
        found = p in matched
        counts[f"truth_measures_{kind}"] += 1
        counts[f"truth_measures_{kind}_read"] += found
        detail.append(
            {
                "measure": numbers[p],
                "kind": kind,
                "truth_notes": truth_counts[p],
                "read": found,
                "read_at": matched.get(p),
            }
        )
    counts["truth_measures"] = len(truth_with)
    counts["truth_measures_read"] = len(matched)
    counts["read_measures"] = len(read_with)
    counts["read_measures_in_truth"] = len(matched)
    return {"counts": dict(sorted(counts.items())), "measures": detail}


def score_layout(score: ScoreIR) -> list[int]:
    return [len(part.staves) for part in score.parts]


def compare_layout(truth: ScoreIR, read: ScoreIR) -> dict[str, Any]:
    truth_layout, read_layout = score_layout(truth), score_layout(read)
    return {
        "truth": truth_layout,
        "read": read_layout,
        "parts_correct": len(truth_layout) == len(read_layout),
        "staves_correct": sum(truth_layout) == sum(read_layout),
        "layout_correct": truth_layout == read_layout,
    }


def _pitches(measure: Measure) -> Counter[str]:
    return Counter(
        event.pitch
        for event in measure.events
        if event.kind is EventKind.NOTE and event.pitch is not None
    )


def _pitch_f1(read: Counter[str], truth: Counter[str]) -> float:
    common = sum((read & truth).values())
    if not common:
        return 0.0
    return 2 * common / (sum(read.values()) + sum(truth.values()))


def compare_staff_content(
    truth_staves: Sequence[Sequence[Measure]],
    page: Sequence[int],
    read_staves: Sequence[Sequence[Measure]],
) -> dict[str, int]:
    """Si cada pentagrama leído tiene lo de su pentagrama de la verdad, compás a compás (#239).

    Las partes y los pentagramas por parte (`layout`) pueden cuadrar aunque HOMR junte la voz con
    la mano derecha en un sistema y deje la mano izquierda en el pentagrama de la derecha. Para
    cada pentagrama de la verdad y cada compás de la página con notas en él (las unidades), se
    toma el compás alineado del pentagrama leído del mismo orden (sin las columnas de cortesía) y
    se compara su multiconjunto de alturas con el de cada pentagrama de la verdad en ese compás
    (F1 de las alturas). Está `in_place` si se parece más a su pentagrama que a cualquier otro, o
    si lo lee entero aunque otro sea igual (una mano que dobla la voz); `elsewhere` si se parece
    más a otro (o igual, sin leerlo entero); `missing` si el pentagrama no se leyó o no comparte
    ninguna altura con ninguno. Un compás que falta en un pentagrama de la verdad cuenta como sin
    notas. La alineación es la proporcional de `map_index`: un compás de más o de menos en la
    lectura también puede dejar el contenido en `elsewhere` o en `missing`.
    """

    prepared = prepare_read_staves(read_staves)
    counts = {"units": 0, "in_place": 0, "elsewhere": 0, "missing": 0}
    for p, index in enumerate(page):
        truths = [
            _pitches(staff[index]) if index < len(staff) else Counter[str]()
            for staff in truth_staves
        ]
        for t, truth in enumerate(truths):
            if not truth:
                continue
            counts["units"] += 1
            measures = prepared[t].measures if t < len(prepared) else ()
            if not measures:
                counts["missing"] += 1
                continue
            read = _pitches(measures[map_index(p, len(page), len(measures))])
            scores = [_pitch_f1(read, other) for other in truths]
            if not any(scores):
                counts["missing"] += 1
            elif scores[t] == 1.0 or all(
                scores[t] > score for o, score in enumerate(scores) if o != t
            ):
                counts["in_place"] += 1
            else:
                counts["elsewhere"] += 1
    return counts


def page_features(
    truth: ScoreIR, first_measure: int, last_measure: int, kinds: Mapping[int, str]
) -> list[str]:
    """Los rasgos que cubre una página según su verdad (para cotejarlos con el manifiesto)."""

    measures = _truth_staff(truth)
    page = _page_indices(measures, first_measure, last_measure)
    found: set[str] = set()
    times = [notation(measures[i].time_signature) for i in page]
    before = notation(measures[page[0] - 1].time_signature) if page[0] > 0 else None
    for p, value in enumerate(times):
        if value is not None and value != (times[p - 1] if p else before):
            if p > 0:
                found.add("time_change")
            symbol = value[2]
            if symbol == COMMON:
                found.add("time_symbol_common")
            elif symbol == CUT:
                found.add("time_symbol_cut")
    keys = effective_keys(measures)
    if any(keys[i] != keys[i - 1] for i in page[1:]):
        found.add("key_change")
    numbers = {measures[i].number for i in page}
    for part in truth.parts:
        for staff in part.staves:
            for measure in staff.measures:
                if measure.number in numbers and tuplet_notes(measure):
                    kind = kinds.get(measure.number)
                    if kind is None:
                        raise ReferenceSetError(
                            f"el compás {measure.number} de la verdad tiene figuras de tresillo y "
                            'ningún <tuplet type="start">: no se sabe si es marcado o implícito'
                        )
                    if kind in ("marked", "mixed"):
                        found.add("tuplets_marked")
                    if kind in ("implicit", "mixed"):
                        found.add("tuplets_implicit")
    layout = score_layout(truth)
    if len(layout) >= 2 and 1 in layout and 2 in layout:
        found.add("voice_piano")
    return sorted(found)


def compare_page(
    truth: ScoreIR,
    read: ScoreIR,
    first_measure: int,
    last_measure: int,
    kinds: Mapping[int, str],
    tolerance: int,
) -> dict[str, Any]:
    measures = _truth_staff(truth)
    page = _page_indices(measures, first_measure, last_measure)
    read_staves = _read_staves(read)
    truth_staves = [staff.measures for part in truth.parts for staff in part.staves]
    result: dict[str, Any] = {
        "truth_measures": len(page),
        "read_measures_per_staff": [len(staff) for staff in read_staves],
        "read_measures_per_staff_without_empty": [
            len(prepared.measures) for prepared in prepare_read_staves(read_staves)
        ],
        "layout": compare_layout(truth, read),
        "staves": compare_staff_content(truth_staves, page, read_staves),
    }
    # Una lectura vacía no se salta: sus unidades cuentan como no leídas.
    result.update(
        {
            "empty_reading": not read_staves,
            "time": compare_time(measures, page, read_staves, tolerance, len(truth_staves)),
            "key": compare_keys(measures, page, read_staves, tolerance, len(truth_staves)),
            "tuplets": compare_tuplets(truth_staves, page, read_staves, kinds, tolerance),
        }
    )
    return result


# --------------------------------------------------------------------------------------------
# Tresillos marcados e implícitos en el MusicXML de la verdad
# --------------------------------------------------------------------------------------------


def _musicxml_bytes(path: Path) -> bytes:
    if path.suffix.lower() != ".mxl":
        return path.read_bytes()
    with zipfile.ZipFile(path) as archive:
        container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
        rootfile = next(
            (el.get("full-path") for el in container.iter() if el.tag.endswith("rootfile")), None
        )
        if rootfile is None:
            raise ReferenceSetError(f"{path} no dice cuál es su partitura (container.xml)")
        return archive.read(rootfile)


def tuplet_display_by_measure(path: Path) -> dict[int, str]:
    """Clase de los tresillos de cada compás de la verdad: `marked` si todos los que empiezan en
    él llevan número, `implicit` si ninguno (`show-number="none"`), `mixed` si hay de los dos."""

    root = ElementTree.fromstring(_musicxml_bytes(path))
    shown: dict[int, set[bool]] = {}
    for measure in root.iter("measure"):
        number_text = measure.get("number", "")
        if not number_text.isdigit():
            continue
        number = int(number_text)
        for tuplet in measure.iter("tuplet"):
            if tuplet.get("type") == "start":
                shown.setdefault(number, set()).add(tuplet.get("show-number") != "none")
    return {
        number: "mixed" if len(flags) > 1 else ("marked" if True in flags else "implicit")
        for number, flags in shown.items()
    }


# --------------------------------------------------------------------------------------------
# PrIMuS
# --------------------------------------------------------------------------------------------


def _first_signature(score: ScoreIR) -> TimeSignature | None:
    for part in score.parts:
        for staff in part.staves:
            for measure in staff.measures:
                if measure.time_signature is not None:
                    return measure.time_signature
    return None


def compare_primus_pair(read: ScoreIR, truth: ScoreIR) -> dict[str, Any]:
    """El compás inicial de un incipit (numerador, denominador y grafía) y la concordancia del
    símbolo en todos sus compases (`time_symbol_agreement`)."""

    t, r = _first_signature(truth), _first_signature(read)
    symbol = time_symbol_agreement(read, truth)
    return {
        "truth": notation_label(notation(t)),
        "read": notation_label(notation(r)),
        "truth_symbol": None if t is None else t.symbol,
        "read_symbol": None if r is None else r.symbol,
        "read_missing": r is None,
        "numerator_correct": t is not None and r is not None and r.beats == t.beats,
        "denominator_correct": t is not None and r is not None and r.beat_type == t.beat_type,
        "meter_correct": t is not None and r is not None and r == t,
        "notation_correct": t is not None and t.same_notation(r),
        "symbol_correct": symbol["correct"],
        "symbol_wrong": symbol["wrong"],
    }


def _export_plain(score: ScoreIR, path: Path) -> Path:
    # Sin el símbolo del compás, como `exp_14` (ADR-0044 §1): el OMR-NED no cuenta la grafía.
    path.write_text(
        Music21ScoreExporter().to_musicxml(without_time_symbols(score)), encoding="utf-8"
    )
    return path


def stage_quality(read: ScoreIR, staged: ScoreIR, truth: ScoreIR) -> dict[str, Any]:
    """La SER antes y después de la etapa del compás y, si la etapa cambió la métrica o las
    figuras, el OMR-NED antes y después. Si no cambió nada que se mida (la igualdad del `ScoreIR`
    no ve el símbolo), el OMR-NED es el mismo y no se calcula."""

    quality: dict[str, Any] = {
        "ser_before": score_ser_pair(truth, read).ser,
        "ser_after": score_ser_pair(truth, staged).ser,
        "stage_changed": staged != read,
        "omr_ned_before": None,
        "omr_ned_after": None,
        "omr_ned_error": "",
    }
    if not quality["stage_changed"]:
        return quality
    with tempfile.TemporaryDirectory(prefix="exp15-ned-") as work:
        folder = Path(work)
        try:
            truth_file = _export_plain(truth, folder / "truth.musicxml")
            before = omr_ned_pair(_export_plain(read, folder / "before.musicxml"), truth_file)
            after = omr_ned_pair(_export_plain(staged, folder / "after.musicxml"), truth_file)
            quality["omr_ned_before"] = before.omr_ned
            quality["omr_ned_after"] = after.omr_ned
        except Exception as exc:  # un par que musicdiff no lee se registra, no se imputa
            quality["omr_ned_error"] = f"{type(exc).__name__}: {exc}"
    return quality


def _primus_task(task: tuple[str, str, str, str, str]) -> dict[str, Any]:
    """Una tarea de proceso: lee la predicción y la verdad de un incipit y las compara.

    El quinto campo son los rasgos de la etapa del compás (vacío: HOMR solo)."""

    entry_id, prediction, ground_truth, expected_sha, features = task
    truth_path = Path(ground_truth)
    if sha256_of_file(truth_path) != expected_sha:
        return {"id": entry_id, "error": f"la verdad no es la del manifiesto: {truth_path}"}
    # Como en `exp_12`: lo que el dominio no admite se registra por incipit y no se mide.
    try:
        truth = read_score(truth_path)
    except Exception as exc:
        return {
            "id": entry_id,
            "status": "truth_unreadable",
            "reason": f"{type(exc).__name__}: {exc}",
        }
    try:
        read = read_score(Path(prediction))
    except Exception as exc:
        return {
            "id": entry_id,
            "status": "prediction_unreadable",
            "reason": f"{type(exc).__name__}: {exc}",
        }
    active = parse_meter_features(features)
    if not active:
        return {"id": entry_id, "status": "measured", **compare_primus_pair(read, truth)}
    staged, _ = recognize_meter(read, active)
    return {
        "id": entry_id,
        "status": "measured",
        **compare_primus_pair(staged, truth),
        **stage_quality(read, staged, truth),
    }


def _mean(values: Sequence[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _before_after(before: Sequence[float], after: Sequence[float]) -> dict[str, Any]:
    pairs = list(zip(before, after, strict=True))
    return {
        "n": len(pairs),
        "mean_before": _mean(before),
        "mean_after": _mean(after),
        "better": sum(1 for b, a in pairs if a < b),
        "worse": sum(1 for b, a in pairs if a > b),
    }


def quality_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    """La SER y el OMR-NED antes y después de la etapa sobre los incipits medidos, con cuántos
    mejoran y cuántos empeoran; None si se midió HOMR solo."""

    measured = [row for row in rows if row.get("status") == "measured" and "ser_before" in row]
    if not measured:
        return None
    ned = [
        row
        for row in measured
        if row["omr_ned_before"] is not None and row["omr_ned_after"] is not None
    ]
    delta = sum(float(row["omr_ned_after"]) - float(row["omr_ned_before"]) for row in ned)
    return {
        "incipits": len(measured),
        "stage_changed": sum(1 for row in measured if row["stage_changed"]),
        "ser": _before_after(
            [float(row["ser_before"]) for row in measured],
            [float(row["ser_after"]) for row in measured],
        ),
        # Solo los incipits que la etapa cambió: en los demás el OMR-NED es el mismo.
        "omr_ned_changed": _before_after(
            [float(row["omr_ned_before"]) for row in ned],
            [float(row["omr_ned_after"]) for row in ned],
        ),
        "omr_ned_mean_delta_over_all": round(delta / len(measured), 4),
        "omr_ned_errors": {
            row["id"]: row["omr_ned_error"] for row in measured if row.get("omr_ned_error")
        },
    }


def measure_primus(
    source: PrimusSource,
    data_dir: Path,
    workers: int,
    meter_features: Collection[MeterFeature] = (),
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads((data_dir / source.manifest).read_text(encoding="utf-8"))
    folder = data_dir / source.predictions
    failures_file = folder / "failures.json"
    failed = (
        {item["id"] for item in json.loads(failures_file.read_text(encoding="utf-8"))}
        if failures_file.is_file()
        else set()
    )
    features = ",".join(features_label(meter_features))
    tasks: list[tuple[str, str, str, str, str]] = []
    missing: list[str] = []
    for entry in manifest["entries"]:
        prediction = folder / f"{entry['id']}.musicxml"
        if prediction.is_file():
            tasks.append(
                (
                    entry["id"],
                    str(prediction),
                    str(data_dir / entry["ground_truth"]),
                    entry["ground_truth_sha256"],
                    features,
                )
            )
        elif entry["id"] not in failed:
            missing.append(entry["id"])
    if missing:
        raise ReferenceSetError(
            f"{source.id}: {len(missing)} incipits sin predicción ni fallo registrado "
            f"(p. ej. {missing[0]}); vuelve a transcribirlos o regístralos en failures.json"
        )
    if workers > 1:
        try:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                rows = list(pool.map(_primus_task, tasks, chunksize=16))
        except BrokenProcessPool as exc:
            raise ReferenceSetError(
                f"{source.id}: un proceso de lectura terminó de golpe ({exc}). En Windows le "
                "pasó al autor alguna vez (WinError 6 en la cola de procesos) y no al repetirlo: "
                "vuelve a ejecutarlo o baja --workers"
            ) from exc
    else:
        rows = [_primus_task(task) for task in tasks]
    errors = [row for row in rows if "error" in row]
    if errors:
        raise ReferenceSetError(f"{source.id}: {errors[0]['error']} (y {len(errors) - 1} más)")
    for row in rows:
        row["source"] = source.id
    unreadable = {
        status: {row["id"]: row["reason"] for row in rows if row["status"] == status}
        for status in ("truth_unreadable", "prediction_unreadable")
    }

    counts: Counter[str] = Counter()
    confusions: Counter[str] = Counter()
    by_truth: dict[str, Counter[str]] = {}
    for row in rows:
        if row["status"] != "measured":
            continue
        counts["incipits"] += 1
        for key in (
            "read_missing",
            "numerator_correct",
            "denominator_correct",
            "meter_correct",
            "notation_correct",
        ):
            counts[key] += bool(row[key])
        counts["symbol_measures_correct"] += row["symbol_correct"]
        counts["symbol_measures_wrong"] += row["symbol_wrong"]
        if not row["notation_correct"]:
            confusions[f"{row['truth']} -> {row['read']}"] += 1
        group = by_truth.setdefault(
            {"common": "C", "cut": "¢"}.get(row["truth_symbol"] or "", "numbers"), Counter()
        )
        group["incipits"] += 1
        group["meter_correct"] += bool(row["meter_correct"])
        group["notation_correct"] += bool(row["notation_correct"])
    summary = {
        "id": source.id,
        "images": source.meta.get("images"),
        "transcription": source.meta.get("transcription"),
        "entries": len(manifest["entries"]),
        "transcription_failures": len(failed),
        "truth_unreadable": unreadable["truth_unreadable"],
        "prediction_unreadable": unreadable["prediction_unreadable"],
        "counts": dict(sorted(counts.items())),
        "by_truth_notation": {key: dict(value) for key, value in sorted(by_truth.items())},
        "confusions": dict(confusions.most_common()),
    }
    quality = quality_summary(rows)
    if quality is not None:
        summary["omr_quality"] = quality
    return summary, sorted(rows, key=lambda row: str(row["id"]))


# --------------------------------------------------------------------------------------------
# Transcripción y ejecución
# --------------------------------------------------------------------------------------------


def _homr_runtime(use_gpu: bool) -> dict[str, Any]:
    info: dict[str, Any] = {"use_gpu_requested": use_gpu}
    try:
        import homr  # noqa: F401
        import onnxruntime
    except ImportError as exc:
        raise ReferenceSetError(
            f"falta HOMR o onnxruntime ({exc}): instala el extra homr (ver README)"
        ) from exc
    from importlib.metadata import version

    from cadenza.omr import get_effective_device

    info["homr_version"] = version("homr")
    info["onnxruntime_version"] = onnxruntime.__version__
    info["device"] = get_effective_device(use_gpu)
    return info


def transcribe_cases(
    manifest: ReferenceManifest,
    pages_dir: Path,
    predictions_dir: Path,
    engine: MusicXMLTranscriber,
    *,
    reuse: bool,
    engine_info: Mapping[str, Any],
    log: Callable[[str], None] = print,
) -> dict[str, dict[str, Any]]:
    """El MusicXML de HOMR de cada página, en `predictions_dir`. Con `reuse`, se reutiliza el de
    una ejecución anterior si se hizo con la misma imagen y el mismo motor (`engine_info`: versión
    de HOMR y dispositivo), según `index.json`."""

    predictions_dir.mkdir(parents=True, exist_ok=True)
    index_path = predictions_dir / PREDICTIONS_INDEX_NAME
    index: dict[str, dict[str, Any]] = {}
    if reuse and index_path.is_file():
        index = json.loads(index_path.read_text(encoding="utf-8"))
    for case in manifest.cases:
        target = predictions_dir / f"{case.id}.musicxml"
        previous = index.get(case.id)
        if (
            reuse
            and previous is not None
            and previous.get("image_sha256") == case.image_sha256
            and previous.get("engine") == dict(engine_info)
            and target.is_file()
            and sha256_of_file(target) == previous.get("prediction_sha256")
        ):
            log(f"[exp_15] {case.id}: reutilizada")
            previous["reused"] = True
            continue
        started = time.perf_counter()
        xml_text = engine.transcribe_musicxml(pages_dir / case.image)
        seconds = round(time.perf_counter() - started, 1)
        target.write_text(xml_text, encoding="utf-8")
        index[case.id] = {
            "image_sha256": case.image_sha256,
            "prediction_sha256": sha256_of_file(target),
            "engine": dict(engine_info),
            "seconds": seconds,
            "reused": False,
        }
        log(f"[exp_15] {case.id}: transcrita en {seconds} s")
        index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    index = {case.id: index[case.id] for case in manifest.cases}
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    return index


def _sum_counts(items: Iterable[Mapping[str, int] | None]) -> dict[str, int]:
    total: Counter[str] = Counter()
    for item in items:
        if item:
            total.update(item)
    return dict(sorted(total.items()))


def _ratio(cases: int, n: int) -> float | None:
    return round(cases / n, 4) if n else None


def headline(
    pages: Sequence[Mapping[str, Any]], primus: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Las proporciones principales, con su numerador y denominador."""

    time_counts = _sum_counts(page["comparison"]["time"]["counts"] for page in pages)
    key_counts = _sum_counts(page["comparison"]["key"]["counts"] for page in pages)
    tuplet_counts = _sum_counts(page["comparison"]["tuplets"]["counts"] for page in pages)
    symbol = _sum_counts(page["comparison"]["time"]["symbol_agreement"] for page in pages)
    primus_counts = Counter(_sum_counts(source["counts"] for source in primus))
    # Con los fallos de HOMR: los incipits que no transcribió o cuya lectura el dominio no admite
    # cuentan como mal leídos (los de verdad ilegible no se miden).
    primus_counts["incipits_with_failures"] = primus_counts["incipits"] + sum(
        source["transcription_failures"] + len(source["prediction_unreadable"]) for source in primus
    )

    def pair(counts: Mapping[str, int], cases: str, n: str) -> dict[str, Any]:
        return {
            "cases": counts.get(cases, 0),
            "n": counts.get(n, 0),
            "proportion": _ratio(counts.get(cases, 0), counts.get(n, 0)),
        }

    segments = {
        f"{kind}_{what}": pair(time_counts, f"segments_{kind}_{what}", f"segments_{kind}")
        for kind in ("page_start", "mid_page")
        for what in ("detected", "meter_correct", "notation_correct")
    }
    layout = [page["comparison"]["layout"] for page in pages]
    staves = _sum_counts(page["comparison"]["staves"] for page in pages)

    def share(key: str) -> dict[str, Any]:
        cases = sum(1 for item in layout if item[key])
        return {"cases": cases, "n": len(layout), "proportion": _ratio(cases, len(layout))}

    return {
        "pages": {
            "time_segments": segments,
            "time_measures_meter_correct": pair(
                time_counts, "printed_measures_meter_correct", "printed_measures"
            ),
            "time_measures_notation_correct": pair(
                time_counts, "printed_measures_notation_correct", "printed_measures"
            ),
            "time_inherited_measures_missing": pair(
                time_counts, "inherited_measures_missing", "inherited_measures"
            ),
            "time_symbol_measures_correct": {
                "cases": symbol.get("correct", 0),
                "n": symbol.get("correct", 0) + symbol.get("wrong", 0),
                "proportion": _ratio(
                    symbol.get("correct", 0), symbol.get("correct", 0) + symbol.get("wrong", 0)
                ),
            },
            "time_spurious_changes": time_counts.get("spurious_changes", 0),
            "key_page_start_correct": pair(key_counts, "page_starts_correct", "page_starts"),
            "key_changes_detected": pair(key_counts, "changes_detected", "changes"),
            "key_changes_correct": pair(key_counts, "changes_correct", "changes"),
            "key_measures_correct": pair(key_counts, "measures_correct", "measures"),
            "key_spurious_changes": key_counts.get("spurious_changes", 0),
            "tuplet_measures_marked_read": pair(
                tuplet_counts, "truth_measures_marked_read", "truth_measures_marked"
            ),
            "tuplet_measures_implicit_read": pair(
                tuplet_counts, "truth_measures_implicit_read", "truth_measures_implicit"
            ),
            "tuplet_measures_mixed_read": pair(
                tuplet_counts, "truth_measures_mixed_read", "truth_measures_mixed"
            ),
            "tuplet_read_measures_in_truth": pair(
                tuplet_counts, "read_measures_in_truth", "read_measures"
            ),
            "tuplet_notes": {
                "truth": tuplet_counts.get("truth_notes", 0),
                "read": tuplet_counts.get("read_notes", 0),
            },
            "layout_correct": share("layout_correct"),
            "parts_correct": share("parts_correct"),
            "staves_in_place": pair(staves, "in_place", "units"),
            "staves_elsewhere": pair(staves, "elsewhere", "units"),
            "staves_missing": pair(staves, "missing", "units"),
            "empty_readings": sum(1 for page in pages if page["comparison"]["empty_reading"]),
            "missing_staves": time_counts.get("missing_staves", 0),
            "extra_read_staves": time_counts.get("extra_read_staves", 0),
            "time_totals": time_counts,
            "key_totals": key_counts,
            "tuplet_totals": tuplet_counts,
        },
        "primus": {
            "numerator_correct": pair(primus_counts, "numerator_correct", "incipits"),
            "denominator_correct": pair(primus_counts, "denominator_correct", "incipits"),
            "meter_correct": pair(primus_counts, "meter_correct", "incipits"),
            "notation_correct": pair(primus_counts, "notation_correct", "incipits"),
            "read_missing": pair(primus_counts, "read_missing", "incipits"),
            "numerator_correct_with_failures": pair(
                primus_counts, "numerator_correct", "incipits_with_failures"
            ),
            "meter_correct_with_failures": pair(
                primus_counts, "meter_correct", "incipits_with_failures"
            ),
            "notation_correct_with_failures": pair(
                primus_counts, "notation_correct", "incipits_with_failures"
            ),
            "symbol_measures_correct": {
                "cases": primus_counts.get("symbol_measures_correct", 0),
                "n": primus_counts.get("symbol_measures_correct", 0)
                + primus_counts.get("symbol_measures_wrong", 0),
                "proportion": _ratio(
                    primus_counts.get("symbol_measures_correct", 0),
                    primus_counts.get("symbol_measures_correct", 0)
                    + primus_counts.get("symbol_measures_wrong", 0),
                ),
            },
        },
    }


def coverage(manifest: ReferenceManifest, primus: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_feature: dict[str, list[str]] = {feature: [] for feature in REQUIRED_FEATURES}
    for case in manifest.cases:
        for feature in case.features:
            by_feature.setdefault(feature, []).append(case.id)
    for source in primus:
        if not source["counts"].get("incipits"):
            continue
        counts = source["by_truth_notation"]
        by_feature["time_numerator"].append(source["id"])
        if counts.get("C", {}).get("incipits"):
            by_feature["time_symbol_common"].append(source["id"])
        if counts.get("¢", {}).get("incipits"):
            by_feature["time_symbol_cut"].append(source["id"])
    missing = [feature for feature in REQUIRED_FEATURES if not by_feature.get(feature)]
    return {"by_feature": by_feature, "missing": missing, "complete": not missing}


def _page_row(page: Mapping[str, Any]) -> dict[str, Any]:
    comparison = page["comparison"]
    row: dict[str, Any] = {
        "case": page["id"],
        "truth": page["truth"],
        "pdf_page": page["pdf_page"],
        "measures": f"{page['measures'][0]}-{page['measures'][1]}",
        "features": " ".join(page["features"]),
        "truth_measures": comparison["truth_measures"],
        "read_measures_per_staff": " ".join(map(str, comparison["read_measures_per_staff"])),
        "truth_layout": " ".join(map(str, comparison["layout"]["truth"])),
        "read_layout": " ".join(map(str, comparison["layout"]["read"])),
        "layout_correct": comparison["layout"]["layout_correct"],
        "seconds": page["transcription"].get("seconds"),
    }
    for key, value in comparison["staves"].items():
        row[f"staves_{key}"] = value
    for section in ("time", "key", "tuplets"):
        counts = comparison[section]["counts"]
        for key, value in counts.items():
            row[f"{section}_{key}"] = value
    row["time_symbol_correct"] = comparison["time"]["symbol_agreement"]["correct"]
    row["time_symbol_wrong"] = comparison["time"]["symbol_agreement"]["wrong"]
    return row


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields: list[str] = []
    for row in rows:
        fields.extend(key for key in row if key not in fields)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run(
    *,
    manifest_path: Path = MANIFEST_PATH,
    data_dir: Path = DATA_DIR,
    pages_dir: Path | None = None,
    output_dir: Path | None = None,
    engine: MusicXMLTranscriber | None = None,
    use_gpu: bool = False,
    tolerance: int = DEFAULT_TOLERANCE,
    workers: int = 1,
    reuse_predictions: bool = False,
    pdftoppm: str | None = None,
    meter_features: Collection[MeterFeature] = (),
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Comprueba el conjunto, rasteriza lo que falte, transcribe, compara y escribe la salida.

    Con `meter_features`, cada lectura de HOMR pasa antes por la etapa del compás (ADR-0059)."""

    if tolerance < 0:
        raise ValueError("tolerance must be >= 0")
    started = time.perf_counter()
    manifest = load_manifest(manifest_path)
    verify_sources(manifest, data_dir)
    pages_dir = pages_dir or data_dir / "reference" / "pages"
    rasterization = prepare_pages(manifest, data_dir, pages_dir, pdftoppm)
    results = output_dir or RESULTS_DIR
    results.mkdir(parents=True, exist_ok=True)

    # PrIMuS primero: no necesita el motor, y su lectura en paralelo es lo único que puede fallar
    # por el sistema (ver `measure_primus`) antes de las transcripciones, que son lo que tarda.
    primus_summaries: list[dict[str, Any]] = []
    primus_rows: list[dict[str, Any]] = []
    for source in manifest.primus:
        log(f"[exp_15] PrIMuS {source.id}: leyendo predicciones y verdades")
        summary, rows = measure_primus(source, data_dir, workers, meter_features)
        primus_summaries.append(summary)
        primus_rows.extend(rows)

    # Las verdades y sus rasgos, antes de transcribir: un rango de compases mal puesto falla ya.
    truth_scores: dict[str, ScoreIR] = {}
    truth_kinds: dict[str, dict[int, str]] = {}
    for case in manifest.cases:
        if case.truth not in truth_scores:
            truth_path = data_dir / manifest.truths[case.truth].path
            truth_scores[case.truth] = read_score(truth_path)
            truth_kinds[case.truth] = tuplet_display_by_measure(truth_path)
        derived = page_features(
            truth_scores[case.truth], case.first_measure, case.last_measure, truth_kinds[case.truth]
        )
        if sorted(case.features) != derived:
            raise ReferenceSetError(
                f"{case.id}: el manifiesto dice que cubre {sorted(case.features)} y la verdad de "
                f"los compases {case.first_measure}-{case.last_measure} da {derived}: revisa los "
                "compases de la página"
            )

    runtime: dict[str, Any]
    if engine is None:
        runtime = _homr_runtime(use_gpu)
        from cadenza.omr import HOMREngine, disable_power_throttling

        runtime["power_throttling_disabled"] = disable_power_throttling()
        runtime["engine"] = "HOMREngine"
        engine = HOMREngine(use_gpu=use_gpu)
    else:
        runtime = {"engine": type(engine).__name__}
    transcriptions = transcribe_cases(
        manifest,
        pages_dir,
        results / PREDICTIONS_DIR_NAME,
        engine,
        reuse=reuse_predictions,
        engine_info={key: runtime.get(key) for key in ("engine", "homr_version", "device")},
        log=log,
    )

    pages: list[dict[str, Any]] = []
    for case in manifest.cases:
        truth = truth_scores[case.truth]
        kinds = truth_kinds[case.truth]
        xml_text = (results / PREDICTIONS_DIR_NAME / f"{case.id}.musicxml").read_text(
            encoding="utf-8"
        )
        read = musicxml_to_score_ir(xml_text)
        stage_report: dict[str, Any] | None = None
        if meter_features:
            read, report = recognize_meter(read, meter_features)
            stage_report = report.to_primitive()
        pages.append(
            {
                "id": case.id,
                "truth": case.truth,
                "scan": case.scan,
                "pdf_page": case.pdf_page,
                "measures": [case.first_measure, case.last_measure],
                "features": list(case.features),
                "image_sha256": case.image_sha256,
                "transcription": transcriptions[case.id],
                "comparison": compare_page(
                    truth, read, case.first_measure, case.last_measure, kinds, tolerance
                ),
                "meter_stage": stage_report,
            }
        )
        log(f"[exp_15] {case.id}: comparada")

    heads = headline(pages, primus_summaries)
    head_pages, head_primus = heads["pages"], heads["primus"]
    proportions = {
        f"{prefix}.{name}": (value["cases"], value["n"])
        for group, prefix in (
            (head_pages, "pages"),
            (head_pages["time_segments"], "pages.time_segments"),
            (head_primus, "primus"),
        )
        for name, value in group.items()
        if isinstance(value, dict) and "proportion" in value
    }
    meter_stage = {
        "features": features_label(meter_features),
        "version": METER_STAGE_VERSION if meter_features else None,
        "issue": 237,
    }
    run_info = {
        **get_run_info(EXPERIMENT, manifest_path=manifest_path),
        "issue": 234,
        "simulated": False,
        "tolerance": tolerance,
        "meter_stage": meter_stage,
        "omr": runtime,
        "rasterization": rasterization,
        "data_dir": str(data_dir),
        "workers": workers,
        "reuse_predictions": reuse_predictions,
        "seconds": round(time.perf_counter() - started, 1),
    }
    summary_out = {
        "experiment": EXPERIMENT,
        "issue": 234,
        "simulated": False,
        "tolerance": tolerance,
        "meter_stage": meter_stage,
        "coverage": coverage(manifest, primus_summaries),
        "headline": heads,
        "pages": pages,
        "primus": primus_summaries,
        "sample_size": sample_size_justification(
            "conjunto de referencia (#234)",
            {
                "pages": len(pages),
                "primus_incipits": sum(s["counts"].get("incipits", 0) for s in primus_summaries),
            },
            proportions,
        ),
        "notes": [
            "Las imágenes de PrIMuS son renders de Verovio, no escaneos.",
            "Las páginas son de las ediciones de Breitkopf (IMSLP); la verdad, de OpenScore "
            "Lieder, que puede no coincidir en todo con esa edición (p. ej. dónde imprime el "
            "número de un tresillo).",
            "Alineación proporcional de compases con tolerancia: ver `tolerance` y ADR-0056.",
        ],
        "run_info": run_info,
    }
    (results / SUMMARY_NAME).write_text(
        json.dumps(summary_out, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _write_csv(results / PAGES_CSV_NAME, [_page_row(page) for page in pages])
    _write_csv(results / PRIMUS_CSV_NAME, primus_rows)
    (results / RUN_INFO_NAME).write_text(
        json.dumps(run_info, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log(f"[exp_15] salida en {results} ({run_info['seconds']} s)")
    return summary_out


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="exp_15: HOMR sobre el conjunto de referencia (#234, ADR-0056)"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("pages", "run"):
        command = sub.add_parser(name)
        command.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
        command.add_argument("--data", type=Path, default=DATA_DIR, help="la carpeta data/")
        command.add_argument(
            "--pages-dir", type=Path, default=None, help="por defecto, data/reference/pages"
        )
        command.add_argument("--pdftoppm", default=None, help="ruta de pdftoppm (poppler)")
    sub.choices["pages"].add_argument(
        "--force", action="store_true", help="rasteriza también las que ya están"
    )
    run_parser = sub.choices["run"]
    run_parser.add_argument("--output-dir", type=Path, default=None, help="por defecto, results/")
    run_parser.add_argument("--gpu", action="store_true", help="HOMR en GPU (por defecto, CPU)")
    run_parser.add_argument("--tolerance", type=int, default=DEFAULT_TOLERANCE)
    run_parser.add_argument(
        "--workers",
        type=int,
        default=min(DEFAULT_MAX_WORKERS, max(1, (os.cpu_count() or 2) - 1)),
        help="procesos para leer PrIMuS (por defecto, hasta 8: music21 ocupa mucha memoria)",
    )
    run_parser.add_argument(
        "--meter-features",
        default="none",
        help=(
            "rasgos de la etapa del compás tras HOMR (ADR-0059), separados por comas: "
            "numerator, symbol, implicit_tuplets, 'all' o 'none' (por defecto, HOMR solo)"
        ),
    )
    run_parser.add_argument(
        "--reuse-predictions",
        action="store_true",
        help="reutiliza el MusicXML de HOMR de --output-dir si es de la misma imagen",
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "pages":
            manifest = load_manifest(args.manifest)
            verify_sources(manifest, args.data, primus=False)
            info = prepare_pages(
                manifest,
                args.data,
                args.pages_dir or args.data / "reference" / "pages",
                args.pdftoppm,
                force=args.force,
            )
            print(json.dumps(info, indent=2, ensure_ascii=False))
        else:
            run(
                manifest_path=args.manifest,
                data_dir=args.data,
                pages_dir=args.pages_dir,
                output_dir=args.output_dir,
                use_gpu=args.gpu,
                tolerance=args.tolerance,
                workers=args.workers,
                reuse_predictions=args.reuse_predictions,
                pdftoppm=args.pdftoppm,
                meter_features=parse_meter_features(args.meter_features),
            )
    except ReferenceSetError as exc:
        raise SystemExit(f"[exp_15] {exc}") from None


if __name__ == "__main__":
    main()
