"""Probe rápido de la base (dev). No forma parte del entregable de Demo Day."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb

from src.config import DB_PATH


def main() -> None:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    print("tables", con.execute("show tables").fetchall())
    print(
        "AF",
        con.execute(
            "select anio_fiscal, min(fecha), max(fecha), count(*) "
            "from fechas group by 1 order by 1"
        ).fetchall(),
    )
    print(
        "P01",
        con.execute(
            """
            select sum(v.importe_neto)
            from ventas v join fechas f on v.fecha = f.fecha
            where f.anio_fiscal = 2025
            """
        ).fetchone(),
    )
    print(
        "P05",
        con.execute(
            "select count(*) from sucursales where region = 'Oeste'"
        ).fetchone(),
    )
    print(
        "P03",
        con.execute(
            """
            select (sum(v.importe_neto) - sum(v.costo))
                   / nullif(sum(v.importe_neto), 0) * 100
            from ventas v
            join fechas f on v.fecha = f.fecha
            join productos p on v.sku = p.sku
            where f.anio_fiscal = 2026 and p.categoria = 'Perfumería'
            """
        ).fetchone(),
    )
    print(
        "P02",
        con.execute(
            """
            select sum(v.unidades)
            from ventas v
            join fechas f on v.fecha = f.fecha
            join productos p on v.sku = p.sku
            where p.categoria = 'Lácteos' and f.anio = 2026 and f.mes = 3
            """
        ).fetchone(),
    )
    print(
        "P10",
        con.execute(
            """
            select s.nombre, sum(v.importe_neto) as ventas
            from ventas v
            join fechas f on v.fecha = f.fecha
            join sucursales s on v.sucursal_id = s.sucursal_id
            where f.anio_fiscal = 2026
            group by 1
            order by 2 desc
            limit 5
            """
        ).fetchall(),
    )


if __name__ == "__main__":
    main()
