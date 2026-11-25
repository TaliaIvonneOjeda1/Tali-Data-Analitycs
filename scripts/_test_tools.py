"""Prueba tools sin LLM (S1 smoke)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tools.registry import execute_tool


def main() -> None:
    print("tablas", execute_tool("listar_tablas")[:200])
    print(
        "P01",
        execute_tool(
            "consultar_medida",
            {"medida": "ventas_netas", "filtros": {"anio_fiscal": 2025}},
        ),
    )
    print(
        "P03",
        execute_tool(
            "consultar_medida",
            {
                "medida": "margen_pct",
                "filtros": {"anio_fiscal": 2026, "categoria": "Perfumería"},
            },
        ),
    )
    print(
        "P02",
        execute_tool(
            "consultar_medida",
            {
                "medida": "unidades",
                "filtros": {"categoria": "Lácteos", "anio": 2026, "mes": 3},
            },
        ),
    )
    print(
        "P05",
        execute_tool(
            "ejecutar_sql_readonly",
            {"sql": "SELECT count(*) AS n FROM sucursales WHERE region = 'Oeste'"},
        ),
    )
    print(
        "P10",
        execute_tool(
            "consultar_medida",
            {
                "medida": "ventas_netas",
                "filtros": {"anio_fiscal": 2026},
                "group_by": ["nombre_sucursal"],
                "ordenar_desc": True,
                "limit": 5,
            },
        )[:500],
    )


if __name__ == "__main__":
    main()
