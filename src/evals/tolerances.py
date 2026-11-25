"""Tolerancias numéricas del evaluador (Caso1 §5)."""

from __future__ import annotations

MONTO_REL_TOL = 0.005  # ±0,5 %
PCT_ABS_TOL = 0.1  # una décima en % o pp


def montos_ok(actual: float, expected: float) -> bool:
    if expected == 0:
        return abs(actual) <= MONTO_REL_TOL
    return abs(actual - expected) / abs(expected) <= MONTO_REL_TOL


def pct_ok(actual: float, expected: float) -> bool:
    return abs(actual - expected) <= PCT_ABS_TOL


def conteo_ok(actual: int | float, expected: int | float) -> bool:
    return actual == expected


def ranking_ok(actual_set: list | set, expected_set: list | set) -> bool:
    return set(actual_set) == set(expected_set)
