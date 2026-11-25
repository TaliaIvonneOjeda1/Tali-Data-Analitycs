"""Demo S4 sin LLM: muestra hooks que frenan.

Uso:
    python scripts/demo_hooks.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agent.hooks import HookBlocked, pre_tool_use, stop_guard


def main() -> None:
    report: dict = {"hooks": []}

    # 1) PreToolUse frena SQL no-SELECT
    try:
        pre_tool_use(
            "ejecutar_sql_readonly",
            {"sql": "DELETE FROM ventas WHERE 1=1"},
        )
        report["hooks"].append({"pre_delete": "NO_BLOQUEO_ERROR"})
    except HookBlocked as exc:
        report["hooks"].append({"pre_delete": "BLOQUEADO", "reason": str(exc)})
        print("OK PreToolUse freno DELETE:", exc)

    # 2) PreToolUse deja pasar SELECT
    try:
        pre_tool_use(
            "ejecutar_sql_readonly",
            {"sql": "SELECT count(*) FROM sucursales"},
        )
        report["hooks"].append({"pre_select": "PERMITIDO"})
        print("OK PreToolUse permite SELECT")
    except HookBlocked as exc:
        report["hooks"].append({"pre_select": "BLOQUEADO_MAL", "reason": str(exc)})

    # 3) Stop frena número sin traza
    try:
        stop_guard(
            {
                "valor": 999999999,
                "consultas": [],
                "cuentas": [],
            },
            trace=[],
        )
        report["hooks"].append({"stop_sin_traza": "NO_BLOQUEO_ERROR"})
    except HookBlocked as exc:
        report["hooks"].append({"stop_sin_traza": "BLOQUEADO", "reason": str(exc)})
        print("OK Stop freno numero sin traza:", exc)

    # 4) Stop deja pasar valor trazado
    try:
        stop_guard(
            {
                "valor": 10,
                "consultas": [
                    {
                        "medida": None,
                        "filtros": {},
                        "sql": "SELECT 10",
                        "valor": 10,
                    }
                ],
                "cuentas": [],
            },
            trace=[{"valor": 10}],
        )
        report["hooks"].append({"stop_con_traza": "PERMITIDO"})
        print("OK Stop permite valor trazado")
    except HookBlocked as exc:
        report["hooks"].append({"stop_con_traza": "BLOQUEADO_MAL", "reason": str(exc)})

    summary = {
        "ok_pre_bloquea_delete": report["hooks"][0].get("pre_delete") == "BLOQUEADO",
        "ok_pre_permite_select": report["hooks"][1].get("pre_select") == "PERMITIDO",
        "ok_stop_bloquea_sin_traza": report["hooks"][2].get("stop_sin_traza")
        == "BLOQUEADO",
        "ok_stop_permite_trazado": report["hooks"][3].get("stop_con_traza")
        == "PERMITIDO",
        "detalle": report["hooks"],
    }
    out = ROOT / "outputs" / "demo_hooks.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    print("Guardado:", out)


if __name__ == "__main__":
    main()
