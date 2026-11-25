"""Valor agregado post-respuesta (consigna «sube la vara»)."""

from __future__ import annotations

from typing import Any


def explicar_consulta(c: dict[str, Any]) -> str:
    medida = c.get("medida")
    filtros = c.get("filtros") or {}
    parts = []
    if medida:
        parts.append(f"Se consultó la medida «{medida}»")
    else:
        parts.append("Se ejecutó una consulta SQL de apoyo")
    if filtros:
        nice = ", ".join(f"{k}={v}" for k, v in list(filtros.items())[:6])
        parts.append(f"con filtros {nice}")
    valor = c.get("valor")
    if valor is not None:
        unidad = c.get("unidad") or ""
        parts.append(f"y el valor obtenido fue {valor} {unidad}".strip())
    return " ".join(parts) + "."


def sugerir_siguiente_pregunta(data: dict[str, Any]) -> str | None:
    texto = (data.get("texto") or "").lower()
    consultas = data.get("consultas") or []
    filtros: dict[str, Any] = {}
    medida = None
    for c in consultas:
        if isinstance(c, dict):
            if c.get("medida") and not medida:
                medida = c.get("medida")
            filtros.update(c.get("filtros") or {})

    if data.get("valor") is None and (
        "aclar" in texto or "¿" in (data.get("texto") or "") or "supuesto" in texto
    ):
        return "¿Querés que lo tome como año fiscal o calendario?"

    if "sin dato" in texto or "no hay" in texto or "no está" in texto:
        return "¿Querés ver ventas netas o margen del mismo período en su lugar?"

    anio = filtros.get("anio_fiscal") or filtros.get("anio")
    trim = filtros.get("trimestre_fiscal")
    region = filtros.get("region")
    categoria = filtros.get("categoria")

    if medida == "ventas_netas" and anio and not trim:
        return f"¿Cómo se comparan las ventas netas del AF{anio} vs el año anterior?"
    if medida in {"margen_pct", "margen_bruto"} and anio:
        base = f"margen en AF{anio}"
        if trim:
            base = f"margen en T{trim} AF{anio}"
        return f"¿Querés el desglose de {base} por categoría o por región?"
    if "desvio" in str(medida or "") or any(
        "desvio" in str(x).lower() for x in (data.get("cuentas") or [])
    ):
        return "¿En qué categoría o mes se concentra el desvío vs presupuesto?"
    if region and not categoria:
        return f"¿Y el mismo indicador solo en la categoría más relevante de {region}?"
    if categoria and not region:
        return f"¿Cómo se ve {categoria} por región en el mismo período?"
    if anio and trim:
        return f"¿Preparás un informe ejecutivo de T{trim} AF{anio} con foco en margen?"
    if anio:
        return f"¿Querés el ranking de proveedores por margen en AF{anio}?"
    return "¿Querés que profundice con un corte por región o por categoría?"


def detectar_alerta_desvio(data: dict[str, Any]) -> dict[str, Any] | None:
    """Heurística: desvío fuerte o concentración mencionada en cuentas/consultas."""
    valor = data.get("valor")
    try:
        num = float(valor) if valor is not None else None
    except (TypeError, ValueError):
        num = None

    cuentas = " ".join(str(c) for c in (data.get("cuentas") or [])).lower()
    texto = (data.get("texto") or "").lower()
    medida_hit = any(
        (isinstance(c, dict) and "desvio" in str(c.get("medida") or "").lower())
        for c in (data.get("consultas") or [])
    ) or ("desvio" in cuentas)

    if medida_hit and num is not None and abs(num) >= 5.0:
        return {
            "activa": True,
            "motivo": (
                f"Desvío relevante ({num}%). Revisá si se concentra en "
                "una categoría o mes antes de generalizar."
            ),
            "umbral_abs_pct": 5.0,
        }

    # Concentración por group_by en consultas con filas
    for c in data.get("consultas") or []:
        if not isinstance(c, dict):
            continue
        filas = c.get("filas") or []
        if len(filas) < 2:
            continue
        vals = []
        for row in filas:
            if isinstance(row, dict) and row.get("valor") is not None:
                try:
                    vals.append(abs(float(row["valor"])))
                except (TypeError, ValueError):
                    pass
        if not vals:
            continue
        total = sum(vals)
        if total <= 0:
            continue
        top = max(vals) / total
        if top >= 0.45 and ("desvio" in str(c.get("medida") or "").lower() or medida_hit):
            return {
                "activa": True,
                "motivo": (
                    "El corte muestra concentración (≥45% en un solo segmento). "
                    "El desvío puede no ser homogéneo."
                ),
                "concentracion_top": round(top, 3),
            }

    if "concentra" in texto or "explica la mayor parte" in texto:
        return {
            "activa": True,
            "motivo": "El texto señala concentración del desvío en un segmento.",
        }
    return None


def enrich_respuesta(data: dict[str, Any]) -> dict[str, Any]:
    """Agrega explicaciones, sugerencia y alerta sin romper el registro base."""
    out = dict(data)
    consultas = []
    for raw in out.get("consultas") or []:
        if isinstance(raw, dict):
            c = dict(raw)
            if not c.get("explicacion_consulta"):
                c["explicacion_consulta"] = explicar_consulta(c)
            consultas.append(c)
        else:
            consultas.append(raw)
    out["consultas"] = consultas
    if not out.get("siguiente_pregunta_sugerida"):
        out["siguiente_pregunta_sugerida"] = sugerir_siguiente_pregunta(out)
    alerta = detectar_alerta_desvio(out)
    if alerta:
        out["alerta_desvio"] = alerta
    elif "alerta_desvio" not in out:
        out["alerta_desvio"] = None
    return out
