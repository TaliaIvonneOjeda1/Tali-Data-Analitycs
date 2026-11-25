"""Demo S3: 1 diagnostico (P13) + 1 informe (I1) con PDF y costo.

Uso:
    set PYTHONIOENCODING=utf-8
    python scripts/demo_s3.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import OUTPUTS_DIR, QUESTIONS_PATH
from src.multiagent.orchestrator import run_diagnostico, run_informe, save_result


def main() -> None:
    OUTPUTS_DIR.mkdir(exist_ok=True)
    questions = {q["id"]: q["texto"] for q in json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))}

    print("=== Diagnostico P13 ===")
    diag = run_diagnostico(questions["P13"], verbose=True)
    save_result(diag, OUTPUTS_DIR / "diagnostico_P13.json")

    print("\n=== Informe I1 ===")
    inf = run_informe(
        "Preparame un informe ejecutivo del T2 del AF2026 con foco en margen.",
        informe_id="I1",
        verbose=True,
    )
    save_result(inf, OUTPUTS_DIR / "informe_I1.json")

    summary = {
        "ok_diagnostico_texto": bool((diag.get("texto") or "").strip()),
        "ok_diagnostico_consultas": len(diag.get("consultas") or []) > 0,
        "ok_diagnostico_costo": (diag.get("costo") or {}).get("total_usd") is not None,
        "ok_informe_pdf": Path(inf.get("pdf") or "").is_file(),
        "ok_informe_consultas": len(inf.get("consultas") or []) > 0,
        "ok_informe_costo": (inf.get("costo") or {}).get("total_usd") is not None,
        "costo_diagnostico_usd": (diag.get("costo") or {}).get("total_usd"),
        "costo_informe_usd": (inf.get("costo") or {}).get("total_usd"),
        "pdf": inf.get("pdf"),
        "agentes_informe": (inf.get("agentes") or {}).get("flujo"),
    }
    (OUTPUTS_DIR / "demo_s3_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
