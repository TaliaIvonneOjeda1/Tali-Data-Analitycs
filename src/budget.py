"""Budgets hard por request (wall-clock, USD, iteraciones)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from src.config import (
    PRODUCT_MAX_ITER,
    PRODUCT_MAX_USD,
    PRODUCT_MAX_WALL_S,
)
from src.costing import estimate_cost_usd


class BudgetExceeded(Exception):
    """Se agotó el presupuesto de la corrida."""


@dataclass
class Budget:
    max_wall_s: float = field(default_factory=lambda: float(PRODUCT_MAX_WALL_S))
    max_usd: float = field(default_factory=lambda: float(PRODUCT_MAX_USD))
    max_iter: int = field(default_factory=lambda: int(PRODUCT_MAX_ITER))
    started: float = field(default_factory=time.perf_counter)
    usage: dict[str, int] = field(
        default_factory=lambda: {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        }
    )
    iterations: int = 0

    def elapsed_s(self) -> float:
        return time.perf_counter() - self.started

    def cost_usd(self) -> float:
        return float(estimate_cost_usd(self.usage).get("total_usd") or 0.0)

    def add_usage(self, part: dict[str, Any] | None) -> None:
        part = part or {}
        for k in self.usage:
            self.usage[k] = int(self.usage.get(k, 0)) + int(part.get(k) or 0)

    def tick_iteration(self) -> None:
        self.iterations += 1
        self.check()

    def remaining_iterations(self) -> int:
        return max(0, int(self.max_iter) - int(self.iterations))

    def check(self) -> None:
        if self.elapsed_s() > self.max_wall_s:
            raise BudgetExceeded(
                f"Budget wall-clock: {self.elapsed_s():.1f}s > {self.max_wall_s}s"
            )
        if self.cost_usd() > self.max_usd:
            raise BudgetExceeded(
                f"Budget USD: {self.cost_usd():.4f} > {self.max_usd}"
            )
        if self.iterations > self.max_iter:
            raise BudgetExceeded(
                f"Budget iteraciones: {self.iterations} > {self.max_iter}"
            )

    def snapshot(self) -> dict[str, Any]:
        return {
            "elapsed_s": round(self.elapsed_s(), 2),
            "cost_usd": round(self.cost_usd(), 6),
            "iterations": self.iterations,
            "limits": {
                "max_wall_s": self.max_wall_s,
                "max_usd": self.max_usd,
                "max_iter": self.max_iter,
            },
        }
