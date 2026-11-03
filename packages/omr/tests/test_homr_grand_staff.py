"""El piano de un sistema de voz y piano son los dos pentagramas de abajo (#239, ADR-0060).

Las medidas de los sistemas son las que HOMR da en las páginas del banco del estudio (TS-02 y
TS-04) y de *Mondnacht*: el alto de cada pentagrama y el centro y el tamaño de los elementos altos
de la izquierda del sistema (la barra que une los tres pentagramas y la llave del piano).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import pytest
from cadenza.omr.adapters import homr_grand_staff
from cadenza.omr.adapters.homr_grand_staff import (
    covers_every_staff,
    install,
    select_grandstaffs_voice_above_piano,
)

# Sistemas de tres pentagramas: (min_y, max_y) de cada uno, de arriba abajo.
TS02 = [(35, 99), (202, 261), (335, 402)]
TS04 = [(60, 125), (214, 277), (373, 436)]
# La barra del sistema (fundida con la llave en TS-02) y la llave del piano: (centro, tamaño).
TS02_SYSTEM_LINE = ((152, 218), (21, 383))
TS04_SYSTEM_LINE = ((142, 249), (7, 396))
TS04_BRACE = ((128, 324), (14, 245))


@dataclass
class _Staff:
    min_y: float
    max_y: float
    min_x: float = 150


@dataclass
class _Symbol:
    center: tuple[float, float]
    size: tuple[float, float]


class _Pair:
    def __init__(self, pair_index: list[int], score: float) -> None:
        self.pair_index = pair_index
        self.score = score

    def get_index(self) -> list[int]:
        return self.pair_index

    def get_score(self) -> float:
        return self.score


class _MultiStaff:
    """Lo que hace HOMR 0.7 en `MultiStaff._select_grandstaffs`, con su misma puntuación."""

    def __init__(self, staffs: Sequence[tuple[float, float]]) -> None:
        self.staffs = [_Staff(*bounds) for bounds in staffs]

    def _score(self, symbol: _Symbol, upper: _Staff, lower: _Staff) -> float:
        unit_size = (upper.max_y - upper.min_y) / 4
        x_distance = abs(min(upper.min_x, lower.min_x) - symbol.center[0])
        top = symbol.center[1] - symbol.size[1] / 2
        bottom = symbol.center[1] + symbol.size[1] / 2
        y_overlap = min(bottom, lower.max_y) - max(top, upper.min_y)
        if x_distance < 5 * unit_size and y_overlap > 0.5 * symbol.size[1]:
            return y_overlap - x_distance
        return 0

    def _select_grandstaffs(self, brace_dot: list[_Symbol]) -> list[_Pair]:
        scored = []
        for i in range(len(self.staffs) - 1):
            best = max(self._score(s, self.staffs[i], self.staffs[i + 1]) for s in brace_dot)
            if best > 0:
                scored.append(_Pair([i, i + 1], best))
        chosen: list[_Pair] = []
        used: set[int] = set()
        for pair in sorted(scored, key=lambda p: p.get_score(), reverse=True):
            if any(index in used for index in pair.get_index()):
                continue
            chosen.append(pair)
            used.update(pair.get_index())
        return chosen


def _original(multi_staff: Any, brace_dot: list[Any]) -> list[Any]:
    return list(_MultiStaff._select_grandstaffs(multi_staff, brace_dot))


def _symbol(spec: tuple[tuple[float, float], tuple[float, float]]) -> _Symbol:
    return _Symbol(center=spec[0], size=spec[1])


def _chosen(staffs: Sequence[tuple[float, float]], *symbols: _Symbol) -> list[list[int]]:
    multi = _MultiStaff(staffs)
    chosen = select_grandstaffs_voice_above_piano(_original, multi, [*symbols])
    return [pair.get_index() for pair in chosen]


def test_homr_alone_pairs_the_voice_with_the_right_hand() -> None:
    # Lo que pasaba: la barra del sistema abarca los dos pares y gana el de arriba.
    multi = _MultiStaff(TS02)
    assert [p.get_index() for p in multi._select_grandstaffs([_symbol(TS02_SYSTEM_LINE)])] == [
        [0, 1]
    ]


def test_a_line_over_the_whole_system_makes_the_two_lower_staves_the_piano() -> None:
    assert _chosen(TS02, _symbol(TS02_SYSTEM_LINE)) == [[1, 2]]


def test_the_brace_decides_and_the_system_line_does_not_count() -> None:
    assert _chosen(TS04, _symbol(TS04_SYSTEM_LINE), _symbol(TS04_BRACE)) == [[1, 2]]


def test_a_brace_of_the_two_upper_staves_is_kept() -> None:
    # Un piano por encima de otro pentagrama: su llave no abarca el de abajo y decide.
    brace = _Symbol(center=(140, 150), size=(14, 240))
    assert _chosen(TS04, _symbol(TS04_SYSTEM_LINE), brace) == [[0, 1]]


def test_without_tall_elements_there_is_no_piano() -> None:
    assert _chosen(TS02) == []


def test_elements_that_join_no_pair_leave_the_staves_apart() -> None:
    far = _Symbol(center=(1500, 218), size=(10, 383))
    assert _chosen(TS02, far) == []


def test_systems_of_two_or_four_staves_are_left_to_homr() -> None:
    piano = [(202, 261), (335, 402)]
    line = _Symbol(center=(152, 300), size=(15, 220))
    assert _chosen(piano, line) == [[0, 1]]

    four = [*TS02, (500, 560)]
    long_line = _Symbol(center=(152, 300), size=(21, 560))
    multi = _MultiStaff(four)
    expected = [p.get_index() for p in multi._select_grandstaffs([long_line])]
    assert _chosen(four, long_line) == expected


def test_covers_every_staff_needs_half_of_each_staff() -> None:
    staffs = [_Staff(*bounds) for bounds in TS02]
    assert covers_every_staff(_symbol(TS02_SYSTEM_LINE), staffs)
    assert not covers_every_staff(_symbol(TS04_BRACE), [_Staff(*b) for b in TS04])
    # Llega a algo más de un tercio del pentagrama de arriba.
    assert not covers_every_staff(_Symbol(center=(150, 250), size=(10, 350)), staffs)


def test_install_is_idempotent_and_keeps_homr_scoring() -> None:
    class Patched(_MultiStaff):
        pass

    install(Patched)
    first = Patched._select_grandstaffs
    install(Patched)
    assert Patched._select_grandstaffs is first

    system = Patched(TS02)
    assert [p.get_index() for p in system._select_grandstaffs([_symbol(TS02_SYSTEM_LINE)])] == [
        [1, 2]
    ]
    # La clase original de HOMR sigue igual.
    assert _MultiStaff._select_grandstaffs is not Patched._select_grandstaffs


def test_install_fails_without_the_homr_method() -> None:
    class Other:
        pass

    with pytest.raises(RuntimeError, match="_select_grandstaffs"):
        install(Other)


def _homr_installed() -> bool:
    try:
        from homr import model  # noqa: F401

        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _homr_installed(), reason="requiere el extra opcional 'homr'")
def test_real_homr_multistaff_takes_the_two_lower_staves() -> None:
    import numpy as np
    from cadenza.omr.adapters.homr import _import_homr
    from homr.bounding_boxes import RotatedBoundingBox
    from homr.model import MultiStaff, Staff, StaffPoint

    _import_homr()

    def staff(min_y: float, max_y: float) -> Any:
        step = (max_y - min_y) / 4
        return Staff(
            [StaffPoint(x, [min_y + i * step for i in range(5)], 0.0) for x in range(150, 1800, 10)]
        )

    system = MultiStaff([staff(*bounds) for bounds in TS02], [])
    (cx, cy), (w, h) = TS02_SYSTEM_LINE
    line = RotatedBoundingBox(((cx, cy), (w, h), 0.0), np.zeros((0, 1, 2), dtype=np.int32))

    merged = system.create_grandstaffs([line])

    assert [s.is_grandstaff for s in merged.staffs] == [False, True]
    assert merged.staffs[0].min_y == pytest.approx(35)
    assert len(system.staffs) == homr_grand_staff.SYSTEM_STAFFS
