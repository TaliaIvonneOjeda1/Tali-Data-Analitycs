"""Corrida completa S6: 20 preguntas + 5 conversaciones + 3 informes.

Un solo comando. Reporta costo y tiempo.

Uso:
    python scripts/run_all.py                 # corrida completa (gasta bastante API)
    python scripts/run_all.py --smoke         # subset barato para validar el harness
    python scripts/run_all.py --smoke --skip-informes
    python scripts/run_all.py --workers 4
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Corrida completa Analista de datos")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Subset: P01,P05,P19 + C5 (+ I1 salvo --skip-informes)",
    )
    parser.add_argument(
        "--skip-informes",
        action="store_true",
        help="No generar PDFs multi-agente (ahorra mucho costo)",
    )
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    from src.evals.run_all_suite import run_all

    summary = run_all(
        smoke=args.smoke,
        skip_informes=args.skip_informes,
        max_workers=args.workers,
        verbose=args.verbose,
    )
    printable = {
        "smoke": summary["smoke"],
        "tiempo_s": summary["tiempo_s"],
        "costo_usd": (summary.get("costo") or {}).get("total_usd"),
        "usage": summary.get("usage"),
        "resumen": summary.get("resumen"),
        "report_md": summary.get("report_md"),
        "bundle": summary.get("bundle"),
    }
    print(json.dumps(printable, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
