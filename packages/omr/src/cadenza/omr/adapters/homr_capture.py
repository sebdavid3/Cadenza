"""Lo que HOMR deja de su lectura además del MusicXML (#403, ADR-0067).

Para emparejar más adelante cada pentagrama de la foto con sus compases corregidos hacen falta
tres cosas que HOMR calcula y no devuelve:

- **Las cajas de los pentagramas.** Con `ProcessingConfig(write_staff_positions=True)`, HOMR
  llama a `save_staff_positions(multi_staffs, shape, archivo)` tras leer la página. Aquí se
  envuelve: durante una captura se anota cada pentagrama (`min_x`, `min_y`, `max_x`, `max_y` y
  si es un gran pentagrama de piano) relativo al alto y al ancho de `shape`, que es la imagen
  que vio HOMR, y no se escribe ningún archivo. Es lo mismo que escribiría HOMR, sin pasar por
  el formato de texto.
- **El recorte del papel.** Antes de detectar, HOMR aplica `autocrop`, que recorta la imagen al
  contorno del papel si lo encuentra (una vista de la imagen de entrada, `img[y:y+h, x:x+w]`).
  Las cajas son relativas a lo recortado, así que se anota el rectángulo: el desplazamiento de la
  vista dentro de la imagen de entrada y su tamaño. Si no recortó, nulo.
- **Los sistemas.** El MusicXML de HOMR marca el comienzo de cada sistema con
  `<print new-system="yes">`; la importación lo descarta. `systems_of` da el número del primer
  compás de cada sistema.

Una página de voz y piano se lee dos veces (`homr_piano`, ADR-0060): cada lectura deja sus cajas
con su modo (`paired`, el piano como un gran pentagrama; `alone`, cada pentagrama solo).

HOMR se llama de uno en uno en todo el proceso (`homr._HOMR_LOCK`), así que la captura en curso es
una sola, como la lectura del piano en `homr_grand_staff`. Fuera de una captura, las dos
funciones envueltas hacen lo de siempre.
"""

from __future__ import annotations

import base64
import functools
import hashlib
import math
import xml.etree.ElementTree as ET
import zlib
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from . import homr_grand_staff

CAPTURE_FORMAT_VERSION = 2
"""2: `musicxml` guarda el de cada lectura de HOMR por su modo (en la 1, uno solo)."""

_PATCHED_ATTRIBUTE = "_cadenza_capture"


@dataclass
class ReadingCapture:
    """Las cajas de una lectura de HOMR."""

    mode: str
    """`paired` o `alone` (`homr_grand_staff.PianoReading`)."""
    image_shape: tuple[int, int]
    """Alto y ancho de la imagen que vio HOMR, ya recortada y redimensionada."""
    source_shape: tuple[int, int] | None
    """Alto y ancho de la imagen que recibió HOMR, antes de recortarla."""
    autocrop: tuple[int, int, int, int] | None
    """`[x, y, ancho, alto]` del papel en la imagen recibida, o None si no recortó."""
    staves: list[dict[str, Any]] = field(default_factory=list)

    def to_primitive(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "image_shape": list(self.image_shape),
            "source_shape": None if self.source_shape is None else list(self.source_shape),
            "autocrop": None if self.autocrop is None else list(self.autocrop),
            "staves": [dict(staff) for staff in self.staves],
        }


@dataclass
class Capture:
    """Lo anotado en una transcripción: una entrada por lectura de HOMR."""

    readings: list[ReadingCapture] = field(default_factory=list)
    native_musicxml: dict[str, str] = field(default_factory=dict)
    """El MusicXML que escribió HOMR en cada lectura (`paired`, `alone`), antes de combinarlas."""
    systems: list[str] | None = None
    """El primer compás de cada sistema, del MusicXML de HOMR (`systems_of`)."""
    errors: list[str] = field(default_factory=list)
    """Lo que no se pudo anotar: la captura nunca hace fallar la lectura de HOMR."""
    _pending_crop: tuple[tuple[int, int], tuple[int, int, int, int] | None] | None = None

    def discard(self, mode: str) -> None:
        """Olvida las lecturas de `mode`, sus errores y su MusicXML: la del piano solo, si
        falló y queda la emparejada."""
        self.readings = [reading for reading in self.readings if reading.mode != mode]
        self.errors = [error for error in self.errors if not error.startswith(f"{mode}: ")]
        self.native_musicxml.pop(mode, None)


_current: Capture | None = None


@contextmanager
def recording(capture: Capture | None) -> Iterator[Capture | None]:
    """Anota en `capture`, mientras dura, lo que HOMR calcula al leer (sin captura, nada)."""

    global _current
    previous, _current = _current, capture
    try:
        yield capture
    finally:
        _current = previous


def crop_rectangle(source: Any, cropped: Any) -> tuple[int, int, int, int] | None:
    """`[x, y, ancho, alto]` de `cropped` dentro de `source`, si es una vista recortada de ella.

    `autocrop` devuelve `img[y:y+h, x:x+w]`, una vista que comparte memoria con la imagen: el
    desplazamiento de su primer píxel da `x` e `y`. Si devuelve la misma imagen, no recortó (None).
    """

    if cropped is source or tuple(cropped.shape[:2]) == tuple(source.shape[:2]):
        return None
    source_start = int(source.__array_interface__["data"][0])
    cropped_start = int(cropped.__array_interface__["data"][0])
    offset = cropped_start - source_start
    row, column = int(source.strides[0]), int(source.strides[1])
    if offset < 0 or row <= 0 or column <= 0:
        raise ValueError("el recorte no es una vista de la imagen")
    y, rest = divmod(offset, row)
    x = rest // column
    height, width = int(cropped.shape[0]), int(cropped.shape[1])
    if y + height > source.shape[0] or x + width > source.shape[1]:
        raise ValueError("el recorte se sale de la imagen")
    return (x, y, width, height)


def staff_boxes(multi_staffs: Any, shape: Any) -> list[dict[str, Any]]:
    """Cada pentagrama de HOMR como caja relativa a la imagen (`cx`, `cy`, `w`, `h` en [0, 1])
    y `grand` si es un gran pentagrama de piano, en el orden en que los da HOMR."""

    height, width = int(shape[0]), int(shape[1])
    boxes = []
    for multi_staff in multi_staffs:
        for staff in multi_staff.staffs:
            x0, y0 = float(staff.min_x), float(staff.min_y)
            x1, y1 = float(staff.max_x), float(staff.max_y)
            if not all(math.isfinite(v) for v in (x0, y0, x1, y1)):
                raise ValueError(f"caja de pentagrama no finita: {(x0, y0, x1, y1)}")
            boxes.append(
                {
                    "grand": bool(getattr(staff, "is_grandstaff", False)),
                    "cx": round((x0 + x1) / 2 / width, 6),
                    "cy": round((y0 + y1) / 2 / height, 6),
                    "w": round((x1 - x0) / width, 6),
                    "h": round((y1 - y0) / height, 6),
                }
            )
    return boxes


def _reading_mode() -> str:
    record = homr_grand_staff._current
    return record.mode.value if record is not None else homr_grand_staff.PianoReading.PAIRED.value


def _save_staff_positions(
    original: Callable[..., Any], multi_staffs: Any, shape: Any, file_path: str
) -> None:
    capture = _current
    if capture is None:
        original(multi_staffs, shape, file_path)
        return
    source_shape, crop = capture._pending_crop or (None, None)
    capture._pending_crop = None
    try:
        capture.readings.append(
            ReadingCapture(
                mode=_reading_mode(),
                image_shape=(int(shape[0]), int(shape[1])),
                source_shape=source_shape,
                autocrop=crop,
                staves=staff_boxes(multi_staffs, shape),
            )
        )
    except Exception as exc:  # la captura no debe tumbar la lectura
        capture.errors.append(f"{_reading_mode()}: cajas: {exc!r}")


def _autocrop(original: Callable[[Any], Any], image: Any) -> Any:
    result = original(image)
    capture = _current
    if capture is not None:
        try:
            capture._pending_crop = (
                (int(image.shape[0]), int(image.shape[1])),
                crop_rectangle(image, result),
            )
        except Exception as exc:  # la captura no debe tumbar la lectura
            capture._pending_crop = None
            capture.errors.append(f"{_reading_mode()}: recorte del papel: {exc!r}")
    return result


def install(homr_main: Any) -> None:
    """Envuelve `save_staff_positions` y `autocrop` de `homr.main` (una sola vez). Un `homr.main`
    sin ellas (un doble de pruebas) queda como está: no se captura nada."""

    for name, wrapper in (("save_staff_positions", _save_staff_positions), ("autocrop", _autocrop)):
        current = getattr(homr_main, name, None)
        if current is None or getattr(current, _PATCHED_ATTRIBUTE, False):
            continue
        patched = functools.partial(wrapper, current)
        setattr(patched, _PATCHED_ATTRIBUTE, True)
        setattr(homr_main, name, patched)


def systems_of(musicxml: str) -> list[str]:
    """El número del primer compás de cada sistema, según los `<print new-system="yes">` de la
    primera parte del MusicXML de HOMR (el primer sistema empieza en su primer compás)."""

    root = ET.fromstring(musicxml)
    part = root.find("part")
    if part is None:
        return []
    starts: list[str] = []
    for index, measure in enumerate(part.findall("measure")):
        number = measure.get("number", str(index + 1))
        printed = measure.find("print")
        new_system = printed is not None and printed.get("new-system") == "yes"
        if index == 0 or new_system:
            starts.append(number)
    return starts


def systems_or_empty(musicxml: str, capture: Capture | None = None) -> list[str]:
    """`systems_of`, o ningún sistema (anotado en `capture.errors`) si no se puede leer: la
    captura nunca hace fallar la lectura."""

    try:
        return systems_of(musicxml)
    except Exception as exc:
        if capture is not None:
            capture.errors.append(f"{_reading_mode()}: sistemas: {exc!r}")
        return []


def capture_primitive(
    capture: Capture,
    musicxml: str,
    *,
    homr_version: str | None,
    preprocessed: bool,
) -> dict[str, Any]:
    """La captura como objeto JSON para `ScoreDocument.omr_capture` (ADR-0067).

    `musicxml` guarda, comprimido (zlib y base64) y con su sha256, el MusicXML que escribió HOMR
    en cada lectura (`paired` y, en una página de voz y piano, `alone`): conserva lo que la
    importación descarta (los sistemas, los trinos, las repeticiones). La combinación de las dos
    lecturas del piano la escribe Cadenza desde el `ScoreIR` y no se guarda. Sin lecturas
    anotadas (un doble de pruebas), se guarda el MusicXML importado, como `importado`.
    """

    systems = capture.systems if capture.systems is not None else systems_or_empty(musicxml)
    return {
        "format_version": CAPTURE_FORMAT_VERSION,
        "engine": "homr",
        "homr_version": homr_version,
        "preprocessed": preprocessed,
        "readings": [reading.to_primitive() for reading in capture.readings],
        "systems": systems,
        "errors": list(capture.errors),
        "musicxml": {
            mode: _compressed(text)
            for mode, text in (capture.native_musicxml or {"importado": musicxml}).items()
        },
    }


def _compressed(text: str) -> dict[str, str]:
    raw = text.encode("utf-8")
    return {
        "encoding": "zlib+base64",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "data": base64.b64encode(zlib.compress(raw, 9)).decode("ascii"),
    }


def raw_musicxml(capture: Mapping[str, Any], mode: str | None = None) -> str:
    """El MusicXML de HOMR de una lectura de la captura (`capture_primitive`): `mode`, o la
    emparejada (`paired`) si no se dice, o la única que haya."""

    stored = capture["musicxml"]
    key = mode or ("paired" if "paired" in stored else next(iter(stored)))
    entry = stored[key]
    if entry.get("encoding") != "zlib+base64":
        raise ValueError(f"codificación desconocida: {entry.get('encoding')!r}")
    return zlib.decompress(base64.b64decode(entry["data"])).decode("utf-8")
