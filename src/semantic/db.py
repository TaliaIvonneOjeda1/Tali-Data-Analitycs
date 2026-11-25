"""Conexión DuckDB en solo lectura.

En Windows, si DBeaver (u otro) tiene abierto `almacenes_del_sur.duckdb`,
DuckDB no permite ni lectura concurrente. Usamos entonces la copia
`almacenes_del_sur.ro.duckdb` (ver docs/S1_IMPLEMENTACION.md).
"""

from __future__ import annotations

import duckdb

from src.config import DB_PATH, DB_PATH_RO


def connect() -> duckdb.DuckDBPyConnection:
    errors: list[str] = []
    for path in (DB_PATH, DB_PATH_RO):
        if not path.is_file():
            errors.append(f"no existe: {path}")
            continue
        try:
            return duckdb.connect(str(path), read_only=True)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{path.name}: {exc}")
    raise RuntimeError(
        "No pude abrir la base en solo lectura. Cerrá DBeaver o regenerá "
        f"la copia .ro.duckdb. Detalle: {errors}"
    )
