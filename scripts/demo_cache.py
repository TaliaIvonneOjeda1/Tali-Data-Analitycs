"""S5: demostrar prompt cache con dos llamadas seguidas al mismo system.

Uso:
    python scripts/demo_cache.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agent.loop import run_agent
from src.config import OUTPUTS_DIR


def main() -> None:
    OUTPUTS_DIR.mkdir(exist_ok=True)
    # Dos preguntas cortas con el mismo system cacheado
    r1 = run_agent(
        "¿Cuántas sucursales tiene la región Oeste?",
        verbose=False,
        enable_prompt_cache=True,
    )
    r2 = run_agent(
        "¿Cuántas sucursales tiene la región Sur?",
        verbose=False,
        enable_prompt_cache=True,
    )
    m1 = r1.get("_meta") or {}
    m2 = r2.get("_meta") or {}
    summary = {
        "call_1": {
            "cache_creation": m1.get("cache_creation_input_tokens"),
            "cache_read": m1.get("cache_read_input_tokens"),
            "structured_ok": m1.get("structured_output_ok"),
            "valor": r1.get("valor"),
        },
        "call_2": {
            "cache_creation": m2.get("cache_creation_input_tokens"),
            "cache_read": m2.get("cache_read_input_tokens"),
            "structured_ok": m2.get("structured_output_ok"),
            "valor": r2.get("valor"),
        },
        "ok_structured": bool(m1.get("structured_output_ok") and m2.get("structured_output_ok")),
        "ok_cache_signal": (
            int(m1.get("cache_creation_input_tokens") or 0) > 0
            or int(m2.get("cache_read_input_tokens") or 0) > 0
            or int(m1.get("cache_read_input_tokens") or 0) > 0
        ),
        "nota": (
            "Si cache_read de la 2da llamada > 0, el prefijo estable se está reutilizando. "
            "Algunos modelos/cuentas reportan cache_creation en la 1ra y read después."
        ),
    }
    out = OUTPUTS_DIR / "demo_cache.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("Guardado:", out)


if __name__ == "__main__":
    main()
