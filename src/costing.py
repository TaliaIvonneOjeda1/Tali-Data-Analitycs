"""Estimación de costo a partir de usage de la API.

Precios configurables por env (USD por millón de tokens).
Defaults orientativos para Haiku 5.5 — ajustar si Anthropic publica otra tarifa.
"""

from __future__ import annotations

import os
from typing import Any


def _rate(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


INPUT_USD_PER_MTOK = _rate("ANTHROPIC_INPUT_USD_PER_MTOK", 1.0)
OUTPUT_USD_PER_MTOK = _rate("ANTHROPIC_OUTPUT_USD_PER_MTOK", 5.0)
CACHE_READ_USD_PER_MTOK = _rate("ANTHROPIC_CACHE_READ_USD_PER_MTOK", 0.1)
CACHE_WRITE_USD_PER_MTOK = _rate("ANTHROPIC_CACHE_WRITE_USD_PER_MTOK", 1.25)


def empty_usage() -> dict[str, int]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }


def add_usage(total: dict[str, int], part: dict[str, Any] | None) -> dict[str, int]:
    part = part or {}
    for k in empty_usage():
        total[k] = int(total.get(k, 0)) + int(part.get(k) or 0)
    return total


def estimate_cost_usd(usage: dict[str, Any]) -> dict[str, float]:
    inp = int(usage.get("input_tokens") or 0)
    out = int(usage.get("output_tokens") or 0)
    cache_r = int(usage.get("cache_read_input_tokens") or 0)
    cache_w = int(usage.get("cache_creation_input_tokens") or 0)
    # Los cache tokens suelen reportarse aparte; no doble-contar input si ya vienen restados.
    cost_in = (inp / 1_000_000) * INPUT_USD_PER_MTOK
    cost_out = (out / 1_000_000) * OUTPUT_USD_PER_MTOK
    cost_cr = (cache_r / 1_000_000) * CACHE_READ_USD_PER_MTOK
    cost_cw = (cache_w / 1_000_000) * CACHE_WRITE_USD_PER_MTOK
    total = cost_in + cost_out + cost_cr + cost_cw
    return {
        "input_usd": round(cost_in, 6),
        "output_usd": round(cost_out, 6),
        "cache_read_usd": round(cost_cr, 6),
        "cache_write_usd": round(cost_cw, 6),
        "total_usd": round(total, 6),
        "rates": {
            "input_usd_per_mtok": INPUT_USD_PER_MTOK,
            "output_usd_per_mtok": OUTPUT_USD_PER_MTOK,
            "cache_read_usd_per_mtok": CACHE_READ_USD_PER_MTOK,
            "cache_write_usd_per_mtok": CACHE_WRITE_USD_PER_MTOK,
        },
    }
