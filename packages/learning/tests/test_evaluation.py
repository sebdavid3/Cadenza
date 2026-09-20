"""Pruebas de las métricas de evaluación simbólica."""

from __future__ import annotations

from cadenza.learning import normalized_edit_distance, symbol_error_rate


def test_symbol_error_rate() -> None:
    assert symbol_error_rate(["a", "b"], ["a", "b"]) == 0.0
    assert symbol_error_rate(["a", "b"], ["a", "c"]) == 0.5
    assert symbol_error_rate(["a"], ["a", "b", "c"]) == 1.0
    assert symbol_error_rate([], []) == 0.0
    assert symbol_error_rate([], ["a"]) == 1.0


def test_normalized_edit_distance() -> None:
    assert normalized_edit_distance(["a", "b"], ["a", "c"]) == 0.5
    assert normalized_edit_distance(["a"], ["a", "b"]) == 0.5
    assert normalized_edit_distance([], []) == 0.0
