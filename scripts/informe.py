"""CLI S3: informe multi-agente + PDF.

Uso:
    python scripts/informe.py --id I1
    python scripts/informe.py "Preparame un informe del T2 AF2026 con foco en margen"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import DATA_DIR, OUTPUTS_DIR
from src.multiagent.orchestrator import run_informe, save_result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pedido", nargs="?")
    parser.add_argument("--id", dest="iid", help="I1, I2 o I3")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if args.iid:
        path = DATA_DIR / "preguntas" / "pedidos_de_informe.json"
        items = json.loads(path.read_text(encoding="utf-8"))
        pedido = next(i["texto"] for i in items if i["id"] == args.iid)
        iid = args.iid
    elif args.pedido:
        pedido = args.pedido
        iid = "adhoc"
    else:
        parser.error("Pasá pedido o --id I1")

    result = run_informe(pedido, informe_id=iid, verbose=not args.quiet)
    out = save_result(result, OUTPUTS_DIR / f"informe_{iid}.json")
    printable = {k: v for k, v in result.items() if not k.startswith("_")}
    print("\n=== INFORME ===")
    print(json.dumps(printable, ensure_ascii=False, indent=2, default=str)[:3500])
    print(f"\nJSON: {out}")
    print(f"PDF:  {result.get('pdf')}")
    print("Costo:", json.dumps(result.get("costo"), ensure_ascii=False))


if __name__ == "__main__":
    main()
