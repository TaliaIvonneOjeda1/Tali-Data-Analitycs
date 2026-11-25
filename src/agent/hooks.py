"""Hooks del loop (Caso1 S4 / M5).

- PreToolUse: frena lo que no sea SELECT (u operación allowlisteada)
- PostToolUse: registra en la traza
- Stop: no deja salir un número que no esté en consultas/cuentas

El motivo del freno vuelve al modelo como error accionable.
"""

from __future__ import annotations

import json
import re
from typing import Any

from src.security.sql_guard import sql_is_readonly


class HookBlocked(Exception):
    """Freno determinista del harness. El mensaje va al modelo."""


# Tools que no ejecutan SQL arbitrario del usuario/modelo
_SAFE_TOOLS = frozenset(
    {
        "listar_tablas",
        "describir_tabla",
        "listar_medidas",
        "leer_glosario",
        "consultar_medida",
        "calcular_variacion_interanual",
        "calcular_desvio_presupuesto",
        "calcular_participacion",
        "generar_grafico_barras",
    }
)


def pre_tool_use(tool_name: str, arguments: dict[str, Any] | None = None) -> None:
    """PreToolUse: validar tool/args. Raisa HookBlocked si no corresponde."""
    args = arguments or {}
    if tool_name in _SAFE_TOOLS:
        return
    if tool_name == "ejecutar_sql_readonly":
        sql = str(args.get("sql") or "")
        if not sql_is_readonly(sql):
            raise HookBlocked(
                "Hook PreToolUse: solo se permiten SELECT/WITH/DESCRIBE/SHOW. "
                f"SQL rechazado: {sql[:200]}"
            )
        return
    raise HookBlocked(
        f"Hook PreToolUse: tool '{tool_name}' no está en la allowlist de ejecución."
    )


def post_tool_use(
    tool_name: str,
    result: str | dict[str, Any],
    trace: list[dict[str, Any]],
    *,
    traced_entry: dict[str, Any] | None = None,
) -> None:
    """PostToolUse: append a la traza (entry ya parseada o raw)."""
    if traced_entry is not None:
        entry = dict(traced_entry)
        entry["tool"] = tool_name
        entry["hook"] = "post_tool_use"
        trace.append(entry)
        return
    payload: Any = result
    if isinstance(result, str):
        try:
            payload = json.loads(result)
        except json.JSONDecodeError:
            payload = {"raw": result[:500]}
    trace.append(
        {
            "tool": tool_name,
            "hook": "post_tool_use",
            "payload_preview": payload
            if not isinstance(payload, dict)
            else {
                k: payload.get(k)
                for k in ("medida", "valor", "sql", "unidad", "error", "is_error")
                if k in payload
            },
        }
    )


def _numbers_from_trace(trace: list[dict[str, Any]], respuesta: dict[str, Any]) -> list[float]:
    nums: list[float] = []
    for c in respuesta.get("consultas") or []:
        if isinstance(c, dict) and c.get("valor") is not None:
            try:
                nums.append(float(c["valor"]))
            except (TypeError, ValueError):
                pass
        if isinstance(c, dict):
            for row in c.get("filas") or []:
                if isinstance(row, dict) and row.get("valor") is not None:
                    try:
                        nums.append(float(row["valor"]))
                    except (TypeError, ValueError):
                        pass
    for t in trace:
        if t.get("valor") is not None:
            try:
                nums.append(float(t["valor"]))
            except (TypeError, ValueError):
                pass
        for hija in t.get("consultas_hijas") or []:
            if isinstance(hija, dict) and hija.get("valor") is not None:
                try:
                    nums.append(float(hija["valor"]))
                except (TypeError, ValueError):
                    pass
    # cuentas tipo "... = 12.3"
    for cuenta in respuesta.get("cuentas") or []:
        matches = re.findall(r"=\s*(-?\d+(?:\.\d+)?)", str(cuenta))
        for m in matches:
            nums.append(float(m))
    return nums


def _approx_in(value: float, candidates: list[float], rel_tol: float = 0.005, abs_tol: float = 0.15) -> bool:
    for c in candidates:
        if abs(value - c) <= abs_tol:
            return True
        if c != 0 and abs(value - c) / abs(c) <= rel_tol:
            return True
    return False


def stop_guard(respuesta: dict[str, Any], trace: list[dict[str, Any]]) -> None:
    """Stop: si hay valor numérico, debe estar respaldado por traza/consultas/cuentas.

    Excepciones permitidas:
    - valor is None (aclaración, sin dato, ranking solo texto)
    - texto pide aclaración / declara sin dato
    """
    valor = respuesta.get("valor")
    if valor is None:
        return
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return

    candidates = _numbers_from_trace(trace, respuesta)
    if candidates and _approx_in(numero, candidates):
        return

    # Si no hay candidatos pero hay consultas con SQL, igual bloqueamos:
    # el número no aparece como valor registrado.
    raise HookBlocked(
        "Hook Stop: el valor reportado no aparece en consultas/cuentas/traza. "
        f"valor={numero}. Volvé a consultar o registrá la cuenta en 'cuentas'."
    )


def describe_hooks() -> dict[str, str]:
    return {
        "pre_tool_use": "Solo SELECT/WITH/DESCRIBE/SHOW (o tools de capa semántica allowlisteadas).",
        "post_tool_use": "Registra cada tool en la traza del loop.",
        "stop_guard": "Bloquea salida con número no respaldado por consultas/cuentas.",
    }
