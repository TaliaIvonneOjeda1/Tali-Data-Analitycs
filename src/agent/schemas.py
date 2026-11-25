"""Schema de respuesta trazable (Caso1 §4). Validación liviana en S1; pydantic estricto en S5."""

from __future__ import annotations

import json
import re
from typing import Any


def empty_respuesta(pregunta: str) -> dict[str, Any]:
    return {
        "pregunta": pregunta,
        "texto": "",
        "valor": None,
        "unidad": None,
        "supuestos": [],
        "consultas": [],
        "cuentas": [],
    }


def extract_json_block(text: str) -> dict[str, Any] | None:
    """Intenta parsear un objeto JSON de la respuesta del modelo."""
    text = text.strip()
    if not text:
        return None
    # bloque ```json
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass
    # primer {...} balanceado simple
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def merge_trace_into_respuesta(
    pregunta: str,
    texto_final: str,
    trace_consultas: list[dict[str, Any]],
) -> dict[str, Any]:
    """Arma el registro: prefiere JSON del modelo; completa consultas desde la traza."""
    parsed = extract_json_block(texto_final) or {}
    out = empty_respuesta(pregunta)
    out["texto"] = parsed.get("texto") or texto_final
    if "valor" in parsed:
        out["valor"] = parsed.get("valor")
    if "unidad" in parsed:
        out["unidad"] = parsed.get("unidad")
    out["supuestos"] = list(parsed.get("supuestos") or [])
    cuentas = list(parsed.get("cuentas") or [])
    for t in trace_consultas:
        for c in t.get("cuentas") or []:
            if c and c not in cuentas:
                cuentas.append(c)
    out["cuentas"] = cuentas

    consultas = list(parsed.get("consultas") or [])
    if not consultas and trace_consultas:
        # aplanar consultas hijas de tools de accounting
        flattened: list[dict[str, Any]] = []
        for t in trace_consultas:
            hijas = t.get("consultas_hijas") or []
            if hijas:
                flattened.extend(hijas)
            elif t.get("sql") is not None or t.get("medida") is not None:
                flattened.append(
                    {
                        "medida": t.get("medida"),
                        "filtros": t.get("filtros") or {},
                        "sql": t.get("sql"),
                        "valor": t.get("valor"),
                        "filas": t.get("filas") or [],
                    }
                )
        consultas = flattened
    out["consultas"] = consultas

    # Si no hay valor pero la última consulta escalar lo tiene, rellenar
    if out["valor"] is None:
        for c in reversed(trace_consultas):
            if c.get("valor") is not None and not c.get("group_by"):
                out["valor"] = c["valor"]
                out["unidad"] = c.get("unidad") or out["unidad"]
                break
    return out
