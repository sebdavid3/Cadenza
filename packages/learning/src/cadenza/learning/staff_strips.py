"""Cada pentagrama de la foto con sus compases (#403, ADR-0067).

Con la captura de HOMR de una sesión (`ScoreDocument.omr_capture`: las cajas de los pentagramas de
cada lectura, el recorte del papel y el primer compás de cada sistema) y su partitura, da una
**tira** por caja: el rectángulo de la foto que ocupa ese pentagrama (o el gran pentagrama del
piano) y los compases y pentagramas del `ScoreIR` que le corresponden. Con la tira y el estado
final de la sesión se forma el par con el que se entrena un lector como HOMR (una imagen de
pentagrama y su secuencia correcta).

El emparejamiento:

1. **Los sistemas.** El sistema k va del compás con que empieza hasta el anterior al siguiente,
   en el orden de los compases del primer pentagrama.
2. **Las cajas, de arriba abajo.** En cada sistema van en el orden de las partes y sus
   pentagramas; un gran pentagrama de piano (`grand`) ocupa dos pentagramas seguidos de una
   misma parte. Se prueba primero la lectura de cada pentagrama solo (`alone`) y después la
   emparejada (`paired`); vale la primera cuyas cajas casan exactamente con los sistemas.
3. **De la imagen de HOMR a la foto.** Las cajas son relativas a la imagen que vio HOMR, ya
   recortada al papel: se suman el desplazamiento del recorte y se escala a la foto.
4. **El alto de la tira**, como en HOMR: hasta la mitad del hueco con el pentagrama vecino, para
   que entren las líneas adicionales, las plicas y las ligaduras.

Desde la vista no se insertan ni se borran compases, así que el compás N leído es el compás N
final y la tira vale para los dos estados.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from cadenza.domain import Event, EventKind, ScoreIR

READING_ORDER = ("alone", "paired")
"""Las lecturas que se prueban, en este orden: un pentagrama por caja antes que el piano junto."""

_SIDE_MARGIN = 0.005
"""Margen a cada lado de la caja, en fracción del ancho de la foto."""


class StripError(ValueError):
    """Por qué las cajas de una sesión no se pueden emparejar con su partitura."""


@dataclass(frozen=True)
class Strip:
    """Un pentagrama (o el gran pentagrama del piano) de un sistema en la foto."""

    system: int
    """Número del sistema, desde 1."""
    measures: tuple[int, ...]
    """Los números de compás del sistema."""
    staves: tuple[tuple[int, int], ...]
    """`(parte, pentagrama)` del `ScoreIR`: uno, o dos en un gran pentagrama."""
    box: tuple[int, int, int, int]
    """`(x0, y0, x1, y1)` en píxeles de la foto."""
    reading: str
    """La lectura de HOMR de la que sale la caja (`alone` o `paired`)."""


def _systems(capture: Mapping[str, Any], score: ScoreIR) -> list[tuple[int, ...]]:
    if not score.parts or not score.parts[0].staves:
        raise StripError("la partitura no tiene pentagramas")
    numbers = [measure.number for measure in score.parts[0].staves[0].measures]
    if not numbers:
        raise StripError("la partitura no tiene compases")
    starts = [str(start) for start in capture.get("systems") or ()] or [str(numbers[0])]
    positions = []
    for start in starts:
        try:
            positions.append(numbers.index(int(start)))
        except ValueError as exc:
            raise StripError(f"un sistema empieza en el compás {start}, que no existe") from exc
    if positions != sorted(set(positions)) or positions[0] != 0:
        raise StripError(f"los sistemas no van en orden desde el primer compás: {starts}")
    ends = [*positions[1:], len(numbers)]
    return [tuple(numbers[a:b]) for a, b in zip(positions, ends, strict=True)]


def _assign(
    boxes: Sequence[Mapping[str, Any]],
    staves: Sequence[tuple[int, int]],
    systems: int,
) -> list[tuple[int, tuple[tuple[int, int], ...]]] | None:
    """El sistema y los pentagramas de cada caja (ya ordenadas de arriba abajo), o None."""

    assigned: list[tuple[int, tuple[tuple[int, int], ...]]] = []
    position = 0
    for system in range(1, systems + 1):
        index = 0
        while index < len(staves):
            if position >= len(boxes):
                return None
            grand = bool(boxes[position].get("grand"))
            if grand:
                if index + 1 >= len(staves) or staves[index][0] != staves[index + 1][0]:
                    return None
                assigned.append((system, (staves[index], staves[index + 1])))
                index += 2
            else:
                assigned.append((system, (staves[index],)))
                index += 1
            position += 1
    return assigned if position == len(boxes) else None


_ASPECT_TOLERANCE = 0.02
"""Cuánto puede diferir la proporción de la foto de la de la imagen que recibió HOMR."""


def _pixel_boxes(
    reading: Mapping[str, Any], boxes: Sequence[Mapping[str, Any]], photo: tuple[int, int]
) -> list[tuple[int, int, int, int]]:
    photo_width, photo_height = photo
    source = reading.get("source_shape")
    if not source:
        raise StripError("la lectura no dice qué imagen recibió HOMR (source_shape)")
    source_height, source_width = int(source[0]), int(source[1])
    if abs(photo_width / photo_height - source_width / source_height) > _ASPECT_TOLERANCE * (
        source_width / source_height
    ):
        # Otra foto, o la misma girada (la orientación EXIF que OpenCV aplica y PIL no).
        raise StripError(
            f"la foto ({photo_width} x {photo_height}) no tiene la proporción de la imagen que "
            f"leyó HOMR ({source_width} x {source_height})"
        )
    crop = reading.get("autocrop")
    left, top, width, height = (
        (0, 0, source_width, source_height) if crop is None else (int(v) for v in crop)
    )
    scale_x, scale_y = photo_width / source_width, photo_height / source_height

    def to_photo(cx: float, cy: float) -> tuple[float, float]:
        return (left + cx * width) * scale_x, (top + cy * height) * scale_y

    centers = [to_photo(float(b["cx"]), float(b["cy"])) for b in boxes]
    halves = [
        (float(b["w"]) * width * scale_x / 2, float(b["h"]) * height * scale_y / 2) for b in boxes
    ]
    margin = _SIDE_MARGIN * photo_width
    result = []
    for index, ((x, y), (half_w, half_h)) in enumerate(zip(centers, halves, strict=True)):
        up = (y - centers[index - 1][1]) / 2 if index > 0 else None
        down = (centers[index + 1][1] - y) / 2 if index + 1 < len(centers) else None
        up = up if up is not None else (down if down is not None else 1.5 * half_h)
        down = down if down is not None else up
        result.append(
            (
                max(0, round(x - half_w - margin)),
                max(0, round(y - max(up, half_h))),
                min(photo_width, round(x + half_w + margin)),
                min(photo_height, round(y + max(down, half_h))),
            )
        )
    return result


def plan_strips(
    capture: Mapping[str, Any], score: ScoreIR, photo_size: tuple[int, int]
) -> list[Strip]:
    """Las tiras de la foto (`photo_size`: ancho y alto en píxeles), una por caja de HOMR.

    Falla con `StripError` si la imagen se preprocesó (las cajas no serían de la foto) o si las
    cajas de ninguna lectura casan con los sistemas y los pentagramas de la partitura.
    """

    if capture.get("preprocessed"):
        raise StripError("HOMR leyó la imagen preprocesada: sus cajas no son de la foto")
    if capture.get("errors"):
        # Sin el recorte del papel o con cajas a medias, las tiras saldrían en otro sitio.
        raise StripError(f"la captura tuvo errores: {'; '.join(map(str, capture['errors']))}")
    systems = _systems(capture, score)
    staves = [(p, s) for p, part in enumerate(score.parts) for s, _ in enumerate(part.staves)]
    readings = {str(r.get("mode")): r for r in capture.get("readings") or ()}
    tried = []
    for mode in READING_ORDER:
        reading = readings.get(mode)
        if reading is None:
            continue
        boxes = sorted(reading.get("staves") or (), key=lambda b: float(b["cy"]))
        tried.append(f"{mode}: {len(boxes)} cajas")
        assigned = _assign(boxes, staves, len(systems))
        if assigned is None:
            continue
        pixels = _pixel_boxes(reading, boxes, photo_size)
        return [
            Strip(
                system=system,
                measures=systems[system - 1],
                staves=covered,
                box=pixels[index],
                reading=mode,
            )
            for index, (system, covered) in enumerate(assigned)
        ]
    detail = "; ".join(tried) or "ninguna lectura con cajas"
    raise StripError(
        f"las cajas no casan con {len(systems)} sistemas de {len(staves)} pentagramas ({detail})"
    )


# --- La transcripción de una tira, como texto -------------------------------------------------


def _beats(value: Fraction | None) -> str:
    if value is None:
        return "?"
    return (
        str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"
    )


def event_token(event: Event) -> str:
    """Un evento en una palabra: `F4:3/4`, `r:1` (silencio), `_:1` (hueco de la voz), `A4:0` (nota
    de adorno); `+` delante si es una nota más del acorde y `~` detrás si se liga."""

    duration = _beats(event.duration_beats)
    if event.kind is EventKind.REST:
        return f"{'_' if event.hidden else 'r'}:{duration}"
    token = f"{event.pitch or '?'}:{duration}"
    if event.is_chord:
        token = f"+{token}"
    if event.tie is not None and event.tie.value in ("start", "continue"):
        token = f"{token}~"
    return token


def strip_sequence(score: ScoreIR, strip: Strip) -> str:
    """Los compases de la tira en `score`, compás a compás («c4: …»), con las voces separadas
    por `/` y los dos pentagramas de un gran pentagrama por `||`."""

    staves_text = []
    for part, staff in strip.staves:
        measures = {m.number: m for m in score.parts[part].staves[staff].measures}
        bars = []
        for number in strip.measures:
            measure = measures.get(number)
            if measure is None:
                bars.append(f"c{number}: ?")
                continue
            voices: dict[int, list[str]] = {}
            for event in measure.events:
                voices.setdefault(event.voice, []).append(event_token(event))
            content = " / ".join(" ".join(tokens) for _, tokens in sorted(voices.items()))
            bars.append(f"c{number}: {content}")
        staves_text.append(" | ".join(bars))
    return " || ".join(staves_text)
