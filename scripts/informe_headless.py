"""S4: generar un informe sin intervencion (headless).

Equivale a scripts/informe.py --quiet, pensado para corridas autonomas / Demo Day prep.

Uso:
    python scripts/informe_headless.py --id I1
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
    parser = argparse.ArgumentParser(description="Informe headless S4")
    parser.add_argument("--id", dest="iid", default="I1")
    args = parser.parse_args()

    path = DATA_DIR / "preguntas" / "pedidos_de_informe.json"
    items = json.loads(path.read_text(encoding="utf-8"))
    pedido = next(i["texto"] for i in items if i["id"] == args.iid)

    print(f"[headless] Generando informe {args.iid} ...")
    result = run_informe(pedido, informe_id=args.iid, verbose=False)
    out = save_result(result, OUTPUTS_DIR / f"informe_headless_{args.iid}.json")
    print(
        json.dumps(
            {
                "id": args.iid,
                "pdf": result.get("pdf"),
                "consultas_n": len(result.get("consultas") or []),
                "costo": result.get("costo"),
                "json": str(out),
                "agentes": (result.get("agentes") or {}).get("flujo"),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
