"""Correr el evaluador interno S1 (sin holdout por defecto).

Uso desde la raíz del entregable:

    python scripts/run_evals.py
    python scripts/run_evals.py --ids P01,P05,P10
    python scripts/run_evals.py --holdout   # solo desde S5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Eval suite Analista de datos")
    parser.add_argument(
        "--holdout",
        action="store_true",
        help="Incluir apartadas (usar solo desde S5)",
    )
    parser.add_argument(
        "--ids",
        type=str,
        default="",
        help="Lista separada por comas, ej. P01,P02,P10",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    from src.evals.harness import run_eval_suite

    ids = [x.strip() for x in args.ids.split(",") if x.strip()] or None
    result = run_eval_suite(
        include_holdout=args.holdout,
        ids=ids,
        verbose=not args.quiet,
    )
    printable = {
        "n": result["n"],
        "acierto_respuesta": result["acierto_respuesta"],
        "ids": result["ids"],
        "detalle": {
            k: v.get("score") for k, v in result["casos"].items()
        },
    }
    print(json.dumps(printable, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
