"""Allowlist de tools por agente en código. (Caso1 S4 / aplicada desde S1–S3)"""

from __future__ import annotations

_READ_TOOLS = frozenset(
    {
        "listar_tablas",
        "describir_tabla",
        "listar_medidas",
        "leer_glosario",
        "consultar_medida",
        "ejecutar_sql_readonly",
        "calcular_variacion_interanual",
        "calcular_desvio_presupuesto",
        "calcular_participacion",
    }
)

_CHART_TOOLS = frozenset({"generar_grafico_barras"})

TOOLS_BY_AGENT: dict[str, frozenset[str]] = {
    "analista_simple": _READ_TOOLS | _CHART_TOOLS,
    "analista_conversacional": _READ_TOOLS | _CHART_TOOLS,
    # S3 workers
    "investigador": _READ_TOOLS | _CHART_TOOLS,
    "analista": frozenset(),  # solo síntesis; no tools (blast radius)
    "redactor": _CHART_TOOLS,  # puede pedir gráfico; el PDF lo arma código
}


def assert_tool_allowed(agent: str, tool_name: str) -> None:
    allowed = TOOLS_BY_AGENT.get(agent)
    if allowed is None:
        raise KeyError(f"Agente desconocido: {agent}")
    if tool_name not in allowed:
        raise PermissionError(f"Tool {tool_name!r} no permitida para {agent}")


def tools_for_agent(agent: str) -> list[str]:
    return sorted(TOOLS_BY_AGENT.get(agent, frozenset()))
