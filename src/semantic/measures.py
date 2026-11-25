"""Capa semántica: carga medidas.yaml y arma SQL de medidas base.

Regla Caso1: pedir medida + filtros; no rearmar fórmulas a mano fuera de acá.
Las derivadas (YoY, desvío, LFL, participación) se calculan en accounting.py (S2).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from src.config import DUCKDB_MAX_ROWS, DUCKDB_QUERY_TIMEOUT_S, MEASURES_PATH
from src.security.sql_guard import sql_is_readonly
from src.semantic.db import connect

# Dimensión lógica -> expresión SQL (según medidas.yaml)
DIMENSION_EXPR: dict[str, str] = {
    "fecha": "f.fecha",
    "anio": "f.anio",
    "mes": "f.mes",
    "anio_fiscal": "f.anio_fiscal",
    "trimestre_fiscal": "f.trimestre_fiscal",
    "mes_fiscal": "f.mes_fiscal",
    "semana": "f.semana_inicio",
    "sucursal": "s.sucursal_id",
    "nombre_sucursal": "s.nombre",
    "region": "s.region",
    "formato": "s.formato",
    "categoria": "p.categoria",
    "subcategoria": "p.subcategoria",
    "marca": "p.marca",
    "producto": "p.sku",
    "es_marca_propia": "p.es_marca_propia",
    "proveedor": "pr.nombre",
    # presupuesto: categoría vive en la tabla hecho
    "categoria_presupuesto": "pz.categoria",
}

# Filtros que requieren joins de dimensión
_NEEDS_PRODUCT = {
    "categoria",
    "subcategoria",
    "marca",
    "producto",
    "es_marca_propia",
    "proveedor",
}
_NEEDS_BRANCH = {"sucursal", "nombre_sucursal", "region", "formato"}
_NEEDS_PROVIDER = {"proveedor"}


class SemanticLayer:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or MEASURES_PATH
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        self.meta = raw
        self.fact_tables: dict[str, dict] = raw["tablas_hecho"]
        self.measures: dict[str, dict] = {m["id"]: m for m in raw["medidas"]}
        self.derived: dict[str, dict] = {
            m["id"]: m for m in raw.get("medidas_derivadas", [])
        }
        self._synonym_index: dict[str, str] = {}
        for mid, m in self.measures.items():
            self._synonym_index[mid.lower()] = mid
            self._synonym_index[m["nombre"].lower()] = mid
            for s in m.get("sinonimos") or []:
                self._synonym_index[str(s).lower()] = mid

    def resolve_measure_id(self, nombre_o_sinonimo: str) -> str:
        key = nombre_o_sinonimo.strip().lower()
        if key in self._synonym_index:
            return self._synonym_index[key]
        if nombre_o_sinonimo in self.derived:
            raise ValueError(
                f"'{nombre_o_sinonimo}' es medida derivada: calculala en código "
                f"sobre medidas base (S2). Bases: {sorted(self.measures)}"
            )
        raise KeyError(
            f"Medida desconocida: {nombre_o_sinonimo!r}. "
            f"Ids: {sorted(self.measures)}"
        )

    def list_measures_summary(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in self.meta["medidas"]:
            out.append(
                {
                    "id": m["id"],
                    "nombre": m["nombre"],
                    "unidad": m.get("unidad", ""),
                    "tabla": m["tabla"],
                    "descripcion": m.get("descripcion", m.get("nota", "")),
                    "sinonimos": m.get("sinonimos") or [],
                }
            )
        for m in self.meta.get("medidas_derivadas", []):
            out.append(
                {
                    "id": m["id"],
                    "nombre": m["nombre"],
                    "unidad": "%",
                    "tabla": None,
                    "descripcion": m.get("nota", ""),
                    "derivada": True,
                    "formula": m.get("formula"),
                }
            )
        return out

    def _categoria_expr(self, tabla: str) -> str:
        if tabla == "presupuesto":
            return "pz.categoria"
        return "p.categoria"

    def _dim_expr(self, dim: str, tabla: str) -> str:
        if dim == "categoria":
            return self._categoria_expr(tabla)
        if dim not in DIMENSION_EXPR:
            raise KeyError(f"Dimensión no soportada: {dim}")
        return DIMENSION_EXPR[dim]

    def _join_sql(self, tabla: str, filters: dict[str, Any], group_by: list[str]) -> str:
        needed = set(filters) | set(group_by)
        if tabla == "ventas":
            parts = [
                "ventas v",
                "JOIN fechas f ON v.fecha = f.fecha",
            ]
            if needed & _NEEDS_PRODUCT or needed & _NEEDS_PROVIDER:
                parts.append("JOIN productos p ON v.sku = p.sku")
            if needed & _NEEDS_BRANCH:
                parts.append("JOIN sucursales s ON v.sucursal_id = s.sucursal_id")
            if needed & _NEEDS_PROVIDER:
                parts.append("JOIN proveedores pr ON p.proveedor_id = pr.proveedor_id")
            return " ".join(parts)
        if tabla == "stock_semanal":
            parts = [
                "stock_semanal st",
                "JOIN fechas f ON st.semana = f.fecha",
            ]
            if needed & _NEEDS_PRODUCT or needed & _NEEDS_PROVIDER:
                parts.append("JOIN productos p ON st.sku = p.sku")
            if needed & _NEEDS_BRANCH:
                parts.append("JOIN sucursales s ON st.sucursal_id = s.sucursal_id")
            if needed & _NEEDS_PROVIDER:
                parts.append("JOIN proveedores pr ON p.proveedor_id = pr.proveedor_id")
            return " ".join(parts)
        if tabla == "presupuesto":
            parts = [
                "presupuesto pz",
                "JOIN fechas f ON pz.mes = f.fecha",
            ]
            # presupuesto no joinea productos; categoría en pz
            if needed & (_NEEDS_BRANCH - {"categoria"}):
                parts.append("JOIN sucursales s ON pz.sucursal_id = s.sucursal_id")
            elif "region" in needed or "formato" in needed or "nombre_sucursal" in needed:
                parts.append("JOIN sucursales s ON pz.sucursal_id = s.sucursal_id")
            if "sucursal" in needed or "region" in needed or "formato" in needed:
                if "JOIN sucursales" not in " ".join(parts):
                    parts.append("JOIN sucursales s ON pz.sucursal_id = s.sucursal_id")
            return " ".join(parts)
        raise KeyError(f"Tabla hecho desconocida: {tabla}")

    def build_sql(
        self,
        medida: str,
        filters: dict[str, Any] | None = None,
        group_by: list[str] | None = None,
        order_by_valor_desc: bool = False,
        limit: int | None = None,
    ) -> tuple[str, str, dict[str, Any]]:
        """Devuelve (medida_id, sql, filtros_normalizados)."""
        mid = self.resolve_measure_id(medida)
        m = self.measures[mid]
        tabla = m["tabla"]
        filters = dict(filters or {})
        group_by = list(group_by or [])

        # Normalizar categoría en presupuesto
        where_parts: list[str] = ["1=1"]
        for dim, val in filters.items():
            expr = self._dim_expr(dim, tabla)
            if isinstance(val, bool):
                where_parts.append(f"{expr} = {str(val).upper()}")
            elif isinstance(val, (int, float)):
                where_parts.append(f"{expr} = {val}")
            else:
                lit = str(val).replace("'", "''")
                where_parts.append(f"{expr} = '{lit}'")

        select_dims = []
        for dim in group_by:
            expr = self._dim_expr(dim, tabla)
            select_dims.append(f"{expr} AS {dim}")

        formula = m["formula"]
        select_list = ", ".join([*select_dims, f"{formula} AS valor"])
        join_sql = self._join_sql(tabla, filters, group_by)
        sql = (
            f"SELECT {select_list} FROM {join_sql} "
            f"WHERE {' AND '.join(where_parts)}"
        )
        if group_by:
            group_exprs = ", ".join(self._dim_expr(d, tabla) for d in group_by)
            sql += f" GROUP BY {group_exprs}"
        if order_by_valor_desc:
            sql += " ORDER BY valor DESC"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        return mid, sql, filters

    def query_measure(
        self,
        medida: str,
        filters: dict[str, Any] | None = None,
        group_by: list[str] | None = None,
        order_by_valor_desc: bool = False,
        limit: int | None = None,
    ) -> dict[str, Any]:
        mid, sql, filters_norm = self.build_sql(
            medida,
            filters=filters,
            group_by=group_by,
            order_by_valor_desc=order_by_valor_desc,
            limit=limit,
        )
        m = self.measures[mid]
        con = connect()
        try:
            rows = con.execute(sql).fetchall()
            cols = [c[0] for c in con.description]
        finally:
            con.close()

        records = [dict(zip(cols, row)) for row in rows]
        # Serializar valores no JSON-nativos
        for rec in records:
            for k, v in list(rec.items()):
                if hasattr(v, "isoformat"):
                    rec[k] = v.isoformat()
                elif isinstance(v, (bytes,)):
                    rec[k] = v.decode("utf-8", errors="replace")

        valor: Any = None
        if not group_by:
            valor = records[0]["valor"] if records else None

        return {
            "medida": mid,
            "nombre": m["nombre"],
            "unidad": m.get("unidad", ""),
            "filtros": filters_norm,
            "group_by": group_by or [],
            "sql": sql,
            "valor": valor,
            "filas": records if group_by else [],
        }


_LAYER: SemanticLayer | None = None


def get_layer() -> SemanticLayer:
    global _LAYER
    if _LAYER is None:
        _LAYER = SemanticLayer()
    return _LAYER


def load_measures(path: Path | None = None) -> dict[str, Any]:
    layer = SemanticLayer(path) if path else get_layer()
    return {
        "medidas": layer.list_measures_summary(),
        "reglas": layer.meta.get("reglas", []),
    }


def resolve_measure_id(nombre_o_sinonimo: str) -> str:
    return get_layer().resolve_measure_id(nombre_o_sinonimo)


def run_readonly_sql(sql: str, max_rows: int | None = None) -> dict[str, Any]:
    """Ejecuta solo SELECT/WITH. Usar para huecos que la capa no cubre."""
    from concurrent.futures import ThreadPoolExecutor
    from concurrent.futures import TimeoutError as FuturesTimeout

    cleaned = (sql or "").strip().rstrip(";")
    if not sql_is_readonly(cleaned):
        return {
            "error": "SQL no permitido. Solo SELECT/WITH/DESCRIBE/SHOW.",
            "sql": sql,
            "is_error": True,
        }
    first = cleaned.lstrip().split(None, 1)[0].upper()
    limit = int(max_rows if max_rows is not None else DUCKDB_MAX_ROWS)

    # Envolver SELECT con límite si no trae LIMIT
    exec_sql = cleaned
    if first in {"SELECT", "WITH"} and "limit" not in cleaned.lower():
        exec_sql = f"SELECT * FROM ({cleaned}) AS _q LIMIT {limit}"

    def _run() -> tuple[list[Any], list[str]]:
        con = connect()
        try:
            rows = con.execute(exec_sql).fetchall()
            cols = [c[0] for c in con.description]
            return rows, cols
        finally:
            con.close()

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_run)
            rows, cols = fut.result(timeout=float(DUCKDB_QUERY_TIMEOUT_S))
    except FuturesTimeout:
        return {
            "error": f"Timeout DuckDB ({DUCKDB_QUERY_TIMEOUT_S}s).",
            "sql": sql,
            "is_error": True,
        }
    except Exception as exc:  # noqa: BLE001 — se devuelve al modelo como error
        return {"error": str(exc), "sql": sql, "is_error": True}

    records = []
    for row in rows:
        rec = dict(zip(cols, row))
        for k, v in list(rec.items()):
            if hasattr(v, "isoformat"):
                rec[k] = v.isoformat()
        records.append(rec)
    return {"sql": sql, "filas": records, "n": len(records)}
