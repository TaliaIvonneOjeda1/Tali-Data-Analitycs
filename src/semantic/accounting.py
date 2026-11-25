"""Cuentas derivadas en código (Caso1 S2 / medidas_derivadas).

El LLM NO debe calcular YoY, desvío, LFL ni participación a mano:
usa las tools que llaman a estas funciones.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from src.semantic.db import connect
from src.semantic.measures import get_layer


def variacion_pct(actual: float, anterior: float) -> float:
    if anterior == 0:
        raise ZeroDivisionError("No se puede calcular variación: base anterior = 0")
    return (actual - anterior) / anterior * 100


def desvio_presupuesto_pct(real: float, presupuesto: float) -> float:
    if presupuesto == 0:
        raise ZeroDivisionError("No se puede calcular desvío: presupuesto = 0")
    return (real - presupuesto) / presupuesto * 100


def delta_pp(actual_pct: float, anterior_pct: float) -> float:
    """Variación de margen % en puntos porcentuales."""
    return actual_pct - anterior_pct


def participacion_pct(parte: float, total: float) -> float:
    if total == 0:
        raise ZeroDivisionError("No se puede calcular participación: total = 0")
    return parte / total * 100


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def period_bounds(filters: dict[str, Any]) -> tuple[date, date]:
    """Min/max fecha del período definido por filtros de calendario/fiscal."""
    layer = get_layer()
    # Reusa joins de fechas vía query trivial
    where = ["1=1"]
    for dim, val in filters.items():
        if dim not in {
            "anio_fiscal",
            "trimestre_fiscal",
            "mes_fiscal",
            "anio",
            "mes",
            "fecha",
            "semana",
        }:
            continue
        expr = layer._dim_expr(dim, "ventas")
        if isinstance(val, (int, float)):
            where.append(f"{expr} = {val}")
        else:
            lit = str(val).replace("'", "''")
            where.append(f"{expr} = '{lit}'")
    sql = f"SELECT min(f.fecha) AS dmin, max(f.fecha) AS dmax FROM fechas f WHERE {' AND '.join(where)}"
    con = connect()
    try:
        row = con.execute(sql).fetchone()
    finally:
        con.close()
    if not row or row[0] is None:
        raise ValueError(f"No hay fechas para filtros de período: {filters}")
    return _as_date(row[0]), _as_date(row[1])


def shift_yoy_filters(filters: dict[str, Any]) -> dict[str, Any]:
    """Copia filtros moviendo el período un año atrás (fiscal o calendario)."""
    out = dict(filters)
    if "anio_fiscal" in out:
        out["anio_fiscal"] = int(out["anio_fiscal"]) - 1
    elif "anio" in out:
        out["anio"] = int(out["anio"]) - 1
    else:
        raise ValueError(
            "Para YoY/LFL hace falta anio_fiscal o anio en los filtros del período actual."
        )
    return out


def query_measure_value(
    medida: str,
    filters: dict[str, Any] | None = None,
    *,
    comparables: bool = False,
    lfl_apertura_hasta: str | None = None,
) -> dict[str, Any]:
    """Consulta medida; si comparables=True aplica filtro LFL de apertura."""
    layer = get_layer()
    filters = dict(filters or {})
    extra_where: list[str] = []
    if comparables:
        if not lfl_apertura_hasta:
            # default: primer día del período anterior
            prev = shift_yoy_filters(
                {
                    k: v
                    for k, v in filters.items()
                    if k
                    in {
                        "anio_fiscal",
                        "trimestre_fiscal",
                        "mes_fiscal",
                        "anio",
                        "mes",
                    }
                }
            )
            dmin, _ = period_bounds(prev)
            lfl_apertura_hasta = dmin.isoformat()
        extra_where.append(f"s.fecha_apertura <= DATE '{lfl_apertura_hasta}'")
        # forzar join sucursales
        filters.setdefault("region", filters.get("region"))  # no-op keep
        # hack: ensure branch join by adding a noop dim if missing
        if not any(k in filters for k in ("region", "formato", "sucursal", "nombre_sucursal")):
            # inject via group-less path: use build with temporary region-less join
            pass

    mid, sql, filters_norm = layer.build_sql(medida, filters=filters)
    if extra_where:
        # Asegurar JOIN sucursales
        if "JOIN sucursales" not in sql:
            sql = sql.replace(
                "JOIN fechas f ON v.fecha = f.fecha",
                "JOIN fechas f ON v.fecha = f.fecha JOIN sucursales s ON v.sucursal_id = s.sucursal_id",
            )
            sql = sql.replace(
                "JOIN fechas f ON st.semana = f.fecha",
                "JOIN fechas f ON st.semana = f.fecha JOIN sucursales s ON st.sucursal_id = s.sucursal_id",
            )
            sql = sql.replace(
                "JOIN fechas f ON pz.mes = f.fecha",
                "JOIN fechas f ON pz.mes = f.fecha JOIN sucursales s ON pz.sucursal_id = s.sucursal_id",
            )
        sql = sql + " AND " + " AND ".join(extra_where)

    con = connect()
    try:
        row = con.execute(sql).fetchone()
        valor = row[0] if row else None
    finally:
        con.close()

    m = layer.measures[mid]
    return {
        "medida": mid,
        "nombre": m["nombre"],
        "unidad": m.get("unidad", ""),
        "filtros": filters_norm,
        "comparables": comparables,
        "lfl_apertura_hasta": lfl_apertura_hasta,
        "sql": sql,
        "valor": valor,
    }


def calcular_variacion_interanual(
    medida: str,
    filtros: dict[str, Any],
    *,
    comparables: bool = False,
    margen_en_pp: bool = False,
) -> dict[str, Any]:
    """YoY total o LFL. Si la medida es margen_pct, por defecto informa Δpp."""
    filtros_actual = dict(filtros)
    filtros_anterior = shift_yoy_filters(filtros_actual)

    lfl_cut = None
    if comparables:
        dmin_prev, _ = period_bounds(
            {
                k: v
                for k, v in filtros_anterior.items()
                if k
                in {
                    "anio_fiscal",
                    "trimestre_fiscal",
                    "mes_fiscal",
                    "anio",
                    "mes",
                }
            }
        )
        lfl_cut = dmin_prev.isoformat()

    actual = query_measure_value(
        medida,
        filtros_actual,
        comparables=comparables,
        lfl_apertura_hasta=lfl_cut,
    )
    anterior = query_measure_value(
        medida,
        filtros_anterior,
        comparables=comparables,
        lfl_apertura_hasta=lfl_cut,
    )

    mid = actual["medida"]
    use_pp = margen_en_pp or mid == "margen_pct"
    if actual["valor"] is None or anterior["valor"] is None:
        raise ValueError("Faltan valores para calcular la variación.")

    if use_pp:
        valor = delta_pp(float(actual["valor"]), float(anterior["valor"]))
        unidad = "pp"
        cuenta = (
            f"delta_pp({actual['valor']}, {anterior['valor']}) = {valor}"
        )
    else:
        valor = variacion_pct(float(actual["valor"]), float(anterior["valor"]))
        unidad = "%"
        cuenta = (
            f"variacion_pct({actual['valor']}, {anterior['valor']}) = {valor}"
        )

    return {
        "medida": mid,
        "comparables": comparables,
        "filtros_actual": filtros_actual,
        "filtros_anterior": filtros_anterior,
        "actual": actual,
        "anterior": anterior,
        "valor": valor,
        "unidad": unidad,
        "cuenta": cuenta,
        "consultas": [
            {
                "medida": mid,
                "filtros": actual["filtros"],
                "sql": actual["sql"],
                "valor": actual["valor"],
            },
            {
                "medida": mid,
                "filtros": anterior["filtros"],
                "sql": anterior["sql"],
                "valor": anterior["valor"],
            },
        ],
        "cuentas": [cuenta],
    }


def calcular_desvio(
    filtros: dict[str, Any],
) -> dict[str, Any]:
    """Desvío % = (ventas_netas - presupuesto) / presupuesto * 100."""
    ventas = query_measure_value("ventas_netas", filtros)
    # presupuesto: categoria usa pz.categoria — mismos filtros de período/sucursal/región
    prep_filters = {
        k: v
        for k, v in filtros.items()
        if k
        in {
            "anio_fiscal",
            "trimestre_fiscal",
            "mes_fiscal",
            "anio",
            "mes",
            "region",
            "formato",
            "sucursal",
            "nombre_sucursal",
            "categoria",
        }
    }
    presupuesto = query_measure_value("presupuesto", prep_filters)
    if ventas["valor"] is None or presupuesto["valor"] is None:
        raise ValueError("Faltan ventas o presupuesto para el desvío.")
    valor = desvio_presupuesto_pct(float(ventas["valor"]), float(presupuesto["valor"]))
    cuenta = (
        f"desvio_presupuesto_pct({ventas['valor']}, {presupuesto['valor']}) = {valor}"
    )
    return {
        "medida": "desvio_presupuesto_pct",
        "filtros": filtros,
        "ventas_netas": ventas,
        "presupuesto": presupuesto,
        "valor": valor,
        "unidad": "%",
        "cuenta": cuenta,
        "consultas": [
            {
                "medida": "ventas_netas",
                "filtros": ventas["filtros"],
                "sql": ventas["sql"],
                "valor": ventas["valor"],
            },
            {
                "medida": "presupuesto",
                "filtros": presupuesto["filtros"],
                "sql": presupuesto["sql"],
                "valor": presupuesto["valor"],
            },
        ],
        "cuentas": [cuenta],
    }


def calcular_participacion(
    medida: str,
    filtros_parte: dict[str, Any],
    filtros_total: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Participación % de una parte sobre el total (mismos filtros sin la dimensión parte)."""
    filtros_parte = dict(filtros_parte)
    if filtros_total is None:
        # quitar dimensiones de desagregue típicas
        filtros_total = {
            k: v
            for k, v in filtros_parte.items()
            if k
            not in {
                "categoria",
                "subcategoria",
                "region",
                "formato",
                "proveedor",
                "marca",
                "producto",
                "sucursal",
                "nombre_sucursal",
            }
        }
    parte = query_measure_value(medida, filtros_parte)
    total = query_measure_value(medida, filtros_total)
    if parte["valor"] is None or total["valor"] is None:
        raise ValueError("Faltan valores para participación.")
    valor = participacion_pct(float(parte["valor"]), float(total["valor"]))
    cuenta = f"participacion_pct({parte['valor']}, {total['valor']}) = {valor}"
    return {
        "medida": medida,
        "filtros_parte": filtros_parte,
        "filtros_total": filtros_total,
        "parte": parte,
        "total": total,
        "valor": valor,
        "unidad": "%",
        "cuenta": cuenta,
        "consultas": [
            {
                "medida": parte["medida"],
                "filtros": parte["filtros"],
                "sql": parte["sql"],
                "valor": parte["valor"],
            },
            {
                "medida": total["medida"],
                "filtros": total["filtros"],
                "sql": total["sql"],
                "valor": total["valor"],
            },
        ],
        "cuentas": [cuenta],
    }
