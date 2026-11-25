"""S5: abrir las 5 apartadas UNA vez (en paralelo por defecto).

Uso:
    python scripts/run_holdout.py
    python scripts/run_holdout.py --sequential
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import OUTPUTS_DIR
from src.evals.holdout import run_holdout, write_holdout_report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sequential", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    summary = run_holdout(
        parallel=not args.sequential,
        verbose=args.verbose,
    )
    report = write_holdout_report(summary, ROOT / "docs" / "HOLDOUT_RESULTADO.md")
    printable = {
        "aciertos": summary["aciertos"],
        "n": summary["n"],
        "cache_read_input_tokens_total": summary["cache_read_input_tokens_total"],
        "cache_creation_input_tokens_total": summary[
            "cache_creation_input_tokens_total"
        ],
        "detalle": {
            k: v["score"] for k, v in summary["casos"].items()
        },
        "report": str(report),
        "bundle": str(OUTPUTS_DIR / "holdout_s5.json"),
    }
    print(json.dumps(printable, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
