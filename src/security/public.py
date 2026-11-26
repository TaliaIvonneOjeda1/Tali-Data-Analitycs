"""Filtro de payloads públicos (API / front): sin internos ni paths absolutos."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _rel_or_name(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    # Paths Windows/Unix absolutos → solo nombre de archivo
    if ":\\" in value or value.startswith("/") or "\\" in value:
        try:
            return Path(value).name
        except Exception:  # noqa: BLE001
            return value.split("/" if "/" in value else "\\")[-1]
    return value


def _clean_consulta(c: Any) -> dict[str, Any] | None:
    if isinstance(c, str) and c.strip():
        return {"medida": None, "filtros": {}, "sql": c.strip()}
    if not isinstance(c, dict):
        return None
    return {
        "medida": c.get("medida"),
        "filtros": c.get("filtros") or {},
        "sql": c.get("sql"),
        "valor": c.get("valor"),
        "unidad": c.get("unidad"),
        "explicacion_consulta": c.get("explicacion_consulta"),
    }


def to_public_respuesta(data: dict[str, Any]) -> dict[str, Any]:
    """Respuesta segura para el cliente."""
    consultas = []
    for raw in data.get("consultas") or []:
        c = _clean_consulta(raw)
        if c:
            consultas.append(c)
    meta_in = data.get("_meta") or {}
    usage = meta_in.get("usage") or {}
    public_meta = {
        "model": meta_in.get("model"),
        "iteraciones": meta_in.get("iteraciones"),
        "tiempo_s": meta_in.get("tiempo_s"),
        "costo_usd": meta_in.get("costo_usd"),
        "usage": {
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
            "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
        },
        "budget": meta_in.get("budget"),
        "hooks_enabled": meta_in.get("hooks_enabled"),
        "structured_output_ok": meta_in.get("structured_output_ok"),
        "scope_blocked": meta_in.get("scope_blocked"),
        "multi_question": meta_in.get("multi_question"),
    }
    return {
        "pregunta": data.get("pregunta"),
        "texto": data.get("texto") or "",
        "valor": data.get("valor"),
        "unidad": data.get("unidad"),
        "supuestos": list(data.get("supuestos") or []),
        "consultas": consultas,
        "cuentas": list(data.get("cuentas") or []),
        "siguiente_pregunta_sugerida": data.get("siguiente_pregunta_sugerida"),
        "alerta_desvio": data.get("alerta_desvio"),
        "meta": public_meta,
    }


def to_public_informe(data: dict[str, Any]) -> dict[str, Any]:
    """Informe seguro para el cliente."""
    consultas = []
    for raw in data.get("consultas") or []:
        c = _clean_consulta(raw)
        if c:
            consultas.append(c)
    pdf = data.get("pdf")
    costo = data.get("costo") or {}
    agentes = data.get("agentes") or {}
    return {
        "pedido": data.get("pedido"),
        "informe_id": data.get("informe_id") or data.get("id"),
        "nombre_archivo": data.get("nombre_archivo") or (_rel_or_name(pdf) if pdf else None),
        "tipo_informe": data.get("tipo_informe"),
        "titulo": data.get("titulo"),
        "resumen_ejecutivo": data.get("resumen_ejecutivo"),
        "indicadores": data.get("indicadores") or [],
        "conclusiones": data.get("conclusiones") or [],
        "consultas": consultas,
        "cuentas": list(data.get("cuentas") or []),
        "pdf": _rel_or_name(pdf) if pdf else None,
        "job_id": data.get("job_id"),
        "flujo": agentes.get("flujo"),
        "costo": {
            "total_usd": costo.get("total_usd"),
            "tiempo_s": data.get("tiempo_s") or costo.get("tiempo_s"),
        },
        "siguiente_pregunta_sugerida": data.get("siguiente_pregunta_sugerida"),
        "alerta_desvio": data.get("alerta_desvio"),
    }
