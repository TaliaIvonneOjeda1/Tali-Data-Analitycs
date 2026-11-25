"""CLI S3: diagnóstico multi-agente.

Uso:
    python scripts/diagnostico.py --id P13
    python scripts/diagnostico.py "¿Por qué bajó el margen de Almacén en el T2 del AF2026?"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import OUTPUTS_DIR, QUESTIONS_PATH
from src.multiagent.orchestrator import run_diagnostico, save_result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pregunta", nargs="?")
    parser.add_argument("--id", dest="qid")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if args.qid:
        items = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
        pregunta = next(i["texto"] for i in items if i["id"] == args.qid)
        out_name = f"diagnostico_{args.qid}.json"
    elif args.pregunta:
        pregunta = args.pregunta
        out_name = "diagnostico_adhoc.json"
    else:
        parser.error("Pasá pregunta o --id P13")

    result = run_diagnostico(pregunta, verbose=not args.quiet)
    path = save_result(result, OUTPUTS_DIR / out_name)
    printable = {k: v for k, v in result.items() if not k.startswith("_")}
    print("\n=== DIAGNOSTICO ===")
    print(json.dumps(printable, ensure_ascii=False, indent=2, default=str)[:4000])
    print(f"\nGuardado: {path}")
    print("Costo:", json.dumps(result.get("costo"), ensure_ascii=False))


if __name__ == "__main__":
    main()
