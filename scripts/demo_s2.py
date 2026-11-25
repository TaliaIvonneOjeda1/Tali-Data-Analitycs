"""Demo S2: 1 ambigua + 1 sin dato + 1 conversación + smoke de cuentas/gráfico.

Uso:

    python scripts/demo_s2.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agent.conversation import run_conversation
from src.agent.loop import run_agent
from src.config import OUTPUTS_DIR
from src.tools.registry import execute_tool


def main() -> None:
    OUTPUTS_DIR.mkdir(exist_ok=True)
    report: dict = {"demos": {}}

    print("\n=== SMOKE accounting (sin LLM) ===")
    yoy = json.loads(
        execute_tool(
            "calcular_variacion_interanual",
            {
                "medida": "ventas_netas",
                "filtros": {
                    "anio_fiscal": 2026,
                    "trimestre_fiscal": 3,
                    "categoria": "Bebidas",
                },
            },
        )
    )
    print("YoY Bebidas T3:", yoy.get("valor"), yoy.get("unidad"), yoy.get("cuenta"))
    chart = json.loads(
        execute_tool(
            "generar_grafico_barras",
            {
                "etiquetas": ["actual", "anterior"],
                "valores": [
                    yoy["actual"]["valor"],
                    yoy["anterior"]["valor"],
                ],
                "titulo": "Bebidas T3 AF2026 vs AF2025",
                "nombre_archivo": "demo_s2_bebidas.png",
            },
        )
    )
    print("Gráfico:", chart)

    print("\n=== P17 ambigua (debe preguntar o declarar supuesto) ===")
    ambigua = run_agent(
        "¿Cuánto vendimos en el último trimestre?",
        verbose=True,
    )
    report["demos"]["ambigua_P17"] = {
        k: v for k, v in ambigua.items() if not k.startswith("_")
    }
    report["demos"]["ambigua_P17"]["_meta"] = ambigua.get("_meta")

    print("\n=== P19 sin dato (ticket promedio) ===")
    sindato = run_agent(
        "¿Cuál es el ticket promedio de la cadena?",
        verbose=True,
    )
    report["demos"]["sin_dato_P19"] = {
        k: v for k, v in sindato.items() if not k.startswith("_")
    }
    report["demos"]["sin_dato_P19"]["_meta"] = sindato.get("_meta")

    print("\n=== Conversacion C5 (ambiguedad -> aclara fiscal -> margen) ===")
    conv = run_conversation(
        [
            "¿Cuánto vendimos el último trimestre?",
            "El fiscal.",
            "¿Y con qué margen?",
        ],
        conversation_id="C5",
        verbose=True,
    )
    report["demos"]["conversacion_C5"] = conv

    out = OUTPUTS_DIR / "demo_s2.json"
    out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"\n=== Demo S2 guardada en {out} ===")

    # Criterios rapidos de aceptacion
    texto_a = (ambigua.get("texto") or "").lower()
    ok_ambigua = (
        ambigua.get("valor") is None
        or bool(ambigua.get("supuestos"))
        or "fiscal" in texto_a
        or "calendario" in texto_a
        or "?" in (ambigua.get("texto") or "")
    )
    texto_s = (sindato.get("texto") or "").lower()
    ok_sindato = (
        sindato.get("valor") is None
        and (
            "no" in texto_s
            or "ticket" in texto_s
            or "clientes" in texto_s
            or "dato" in texto_s
        )
    )
    ok_conv = len(conv.get("turnos") or []) == 3
    summary = {
        "ok_ambigua": ok_ambigua,
        "ok_sindato": ok_sindato,
        "ok_conversacion_3_turnos": ok_conv,
        "ok_grafico": bool(chart.get("ok")),
    }
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    (OUTPUTS_DIR / "demo_s2_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
