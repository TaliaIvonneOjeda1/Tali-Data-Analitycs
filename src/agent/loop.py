"""Agent loop ReAct-style con tools del MCP + hooks S4.

Modelo: claude-haiku-5-5 (Caso1). Guarda response.content completo.
Hooks: PreToolUse / PostToolUse / Stop (Caso1 S4).
Budgets / dedupe / enrich: modo producto.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable

import anthropic

from src.agent.hooks import HookBlocked, post_tool_use, pre_tool_use, stop_guard
from src.agent.permissions import TOOLS_BY_AGENT, assert_tool_allowed
from src.agent.prompts import system_prompt_for
from src.agent.schemas import merge_trace_into_respuesta
from src.budget import Budget, BudgetExceeded
from src.config import MAX_ITERATIONS_DEFAULT, MODEL, PRODUCT_MAX_ITER
from src.costing import estimate_cost_usd
from src.enrich import enrich_respuesta
from src.logging_util import get_logger, log_event
from src.tools.registry import execute_tool, list_tool_schemas

logger = get_logger("analista.loop")


def _text_from_content(content: list[Any]) -> str:
    parts: list[str] = []
    for block in content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "\n".join(parts).strip()


def _tool_call_key(name: str, args: dict[str, Any]) -> str:
    return f"{name}:{json.dumps(args or {}, ensure_ascii=False, sort_keys=True, default=str)}"


def _trace_from_tool_payload(name: str, payload: str) -> dict[str, Any] | None:
    traced_tools = {
        "consultar_medida",
        "ejecutar_sql_readonly",
        "calcular_variacion_interanual",
        "calcular_desvio_presupuesto",
        "calcular_participacion",
        "generar_grafico_barras",
    }
    if name not in traced_tools:
        return None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if data.get("is_error") or data.get("error"):
        return None
    if name == "consultar_medida":
        return {
            "medida": data.get("medida"),
            "filtros": data.get("filtros") or {},
            "sql": data.get("sql"),
            "valor": data.get("valor"),
            "unidad": data.get("unidad"),
            "group_by": data.get("group_by") or [],
            "filas": data.get("filas") or [],
        }
    if name in {
        "calcular_variacion_interanual",
        "calcular_desvio_presupuesto",
        "calcular_participacion",
    }:
        return {
            "medida": data.get("medida"),
            "filtros": data.get("filtros")
            or data.get("filtros_actual")
            or data.get("filtros_parte")
            or {},
            "sql": None,
            "valor": data.get("valor"),
            "unidad": data.get("unidad"),
            "cuentas": data.get("cuentas") or [],
            "consultas_hijas": data.get("consultas") or [],
            "filas": [],
        }
    if name == "generar_grafico_barras":
        return {
            "medida": None,
            "filtros": {},
            "sql": None,
            "valor": None,
            "unidad": None,
            "cuentas": [data.get("cuenta")] if data.get("cuenta") else [],
            "path": data.get("path"),
            "filas": [],
        }
    return {
        "medida": None,
        "filtros": {},
        "sql": data.get("sql"),
        "valor": None,
        "unidad": None,
        "filas": data.get("filas") or [],
    }


def run_agent(
    pregunta: str,
    *,
    max_iteraciones: int | None = None,
    agent_role: str = "analista_simple",
    verbose: bool = True,
    client: anthropic.Anthropic | None = None,
    enable_hooks: bool = True,
    enable_prompt_cache: bool = True,
    enable_budget: bool = False,
    budget: Budget | None = None,
    enrich: bool = True,
    request_id: str | None = None,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Ejecuta el loop y devuelve registro Respuesta + meta (usage, hooks, cache)."""
    started = time.perf_counter()
    if enable_budget and budget is None:
        budget = Budget(max_iter=max_iteraciones or PRODUCT_MAX_ITER)
    max_iter = max_iteraciones or (
        budget.max_iter if budget else MAX_ITERATIONS_DEFAULT
    )
    client = client or anthropic.Anthropic()
    allowed = TOOLS_BY_AGENT.get(agent_role)
    if allowed is None:
        raise KeyError(f"Agente desconocido: {agent_role}")
    tools = [t for t in list_tool_schemas() if t["name"] in allowed]
    system_text = system_prompt_for(agent_role)
    # S5: prefijo estable con cache_control (Caso1 S5 / M6)
    if enable_prompt_cache:
        system: str | list[dict[str, Any]] = [
            {
                "type": "text",
                "text": system_text,
                "cache_control": {"type": "ephemeral"},
            }
        ]
    else:
        system = system_text
    messages: list[dict[str, Any]] = [{"role": "user", "content": pregunta}]
    trace_consultas: list[dict[str, Any]] = []
    hook_events: list[dict[str, Any]] = []
    seen_tool_calls: dict[str, str] = {}
    usage_total = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }
    stop_reason = None
    final_text = ""
    respuesta: dict[str, Any] = {}
    budget_error: str | None = None

    step = 0
    try:
        for step in range(1, max_iter + 1):
            if budget is not None:
                budget.tick_iteration()
            if verbose:
                print(f"\n--- Iteración {step} [{agent_role}] ---")
            if on_progress:
                on_progress(
                    {
                        "phase": "iteration",
                        "role": agent_role,
                        "iteration": step,
                        "request_id": request_id,
                    }
                )
            create_kwargs: dict[str, Any] = {
                "model": MODEL,
                "max_tokens": 8192,
                "system": system,
                "messages": messages,
            }
            if tools:
                create_kwargs["tools"] = tools
            response = client.messages.create(**create_kwargs)
            stop_reason = response.stop_reason
            if verbose:
                print(f"stop_reason: {stop_reason}")

            if response.usage:
                part = {
                    "input_tokens": getattr(response.usage, "input_tokens", 0) or 0,
                    "output_tokens": getattr(response.usage, "output_tokens", 0) or 0,
                    "cache_read_input_tokens": getattr(
                        response.usage, "cache_read_input_tokens", 0
                    )
                    or 0,
                    "cache_creation_input_tokens": getattr(
                        response.usage, "cache_creation_input_tokens", 0
                    )
                    or 0,
                }
                for k, v in part.items():
                    usage_total[k] += v
                if budget is not None:
                    budget.add_usage(part)
                    budget.check()

            messages.append({"role": "assistant", "content": response.content})

            if stop_reason == "end_turn" or (
                stop_reason != "tool_use" and stop_reason is not None
            ):
                final_text = _text_from_content(response.content)
                if stop_reason != "end_turn" and not final_text:
                    final_text = f"stop_reason inesperado: {stop_reason}"
                if verbose and final_text:
                    print(final_text[:2000])

                respuesta = merge_trace_into_respuesta(
                    pregunta, final_text, trace_consultas
                )
                if enable_hooks:
                    try:
                        stop_guard(respuesta, trace_consultas)
                    except HookBlocked as exc:
                        hook_events.append(
                            {
                                "hook": "stop_guard",
                                "blocked": True,
                                "reason": str(exc),
                            }
                        )
                        if verbose:
                            print(f"  [HOOK STOP] {exc}")
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    f"Error del harness (Hook Stop): {exc}\n"
                                    "Corregí la respuesta: consultá de nuevo o registrá "
                                    "la cuenta. No inventes el número."
                                ),
                            }
                        )
                        continue
                break

            if stop_reason != "tool_use":
                final_text = _text_from_content(response.content) or (
                    f"stop_reason inesperado: {stop_reason}"
                )
                respuesta = merge_trace_into_respuesta(
                    pregunta, final_text, trace_consultas
                )
                break

            tool_results: list[dict[str, Any]] = []
            for block in response.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                name = block.name
                args = block.input or {}
                if verbose:
                    print(
                        f"  [tool] {name}({json.dumps(args, ensure_ascii=False)[:300]})"
                    )

                is_error = False
                payload: str
                call_key = _tool_call_key(name, args)
                if call_key in seen_tool_calls:
                    payload = seen_tool_calls[call_key]
                    if verbose:
                        print("  [dedupe] reusando resultado idéntico")
                else:
                    try:
                        assert_tool_allowed(agent_role, name)
                        if enable_hooks:
                            pre_tool_use(name, args)
                        payload = execute_tool(name, args)
                        seen_tool_calls[call_key] = payload
                    except (PermissionError, HookBlocked) as exc:
                        payload = json.dumps(
                            {
                                "error": str(exc),
                                "is_error": True,
                                "hook": "pre_tool_use",
                            },
                            ensure_ascii=False,
                        )
                        is_error = True
                        hook_events.append(
                            {
                                "hook": "pre_tool_use",
                                "blocked": True,
                                "tool": name,
                                "reason": str(exc),
                            }
                        )
                        if verbose:
                            print(f"  [HOOK PRE] {exc}")

                if verbose:
                    print(f"  [result] {payload[:400]}")

                traced = None if is_error else _trace_from_tool_payload(name, payload)
                if enable_hooks:
                    post_tool_use(
                        name, payload, trace_consultas, traced_entry=traced
                    )
                elif traced:
                    trace_consultas.append(traced)

                try:
                    parsed = json.loads(payload)
                    is_error = (
                        bool(parsed.get("is_error") or parsed.get("error")) or is_error
                    )
                except json.JSONDecodeError:
                    pass

                item: dict[str, Any] = {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": payload,
                }
                if is_error:
                    item["is_error"] = True
                tool_results.append(item)
            messages.append({"role": "user", "content": tool_results})
            if budget is not None:
                budget.check()
        else:
            final_text = "Límite de iteraciones alcanzado sin end_turn."
            respuesta = merge_trace_into_respuesta(
                pregunta, final_text, trace_consultas
            )
    except BudgetExceeded as exc:
        budget_error = str(exc)
        log_event(
            logger,
            "budget_exceeded",
            request_id=request_id,
            role=agent_role,
            reason=budget_error,
        )
        if not respuesta:
            respuesta = merge_trace_into_respuesta(
                pregunta,
                f"Se detuvo por presupuesto: {exc}",
                trace_consultas,
            )
            respuesta["texto"] = (
                respuesta.get("texto")
                or f"No pude completar la respuesta a tiempo/presupuesto: {exc}"
            )

    if not respuesta:
        respuesta = merge_trace_into_respuesta(pregunta, final_text, trace_consultas)

    if enrich:
        respuesta = enrich_respuesta(respuesta)

    # S5: validar structured output antes de devolver/persistir
    from src.agent.models import validate_respuesta

    validated, errors = validate_respuesta(respuesta)
    if validated is not None:
        # preserve enrich fields that pydantic may keep via extra=allow
        respuesta = validated

    costo = estimate_cost_usd(usage_total)
    tiempo_s = round(time.perf_counter() - started, 2)
    respuesta["_meta"] = {
        "model": MODEL,
        "stop_reason": stop_reason,
        "iteraciones": step,
        "usage": usage_total,
        "trace_consultas_n": len(trace_consultas),
        "hooks_enabled": enable_hooks,
        "hook_events": hook_events,
        "prompt_cache": enable_prompt_cache,
        "cache_read_input_tokens": usage_total.get("cache_read_input_tokens", 0),
        "cache_creation_input_tokens": usage_total.get(
            "cache_creation_input_tokens", 0
        ),
        "structured_output_ok": validated is not None,
        "structured_output_errors": errors,
        "tiempo_s": tiempo_s,
        "costo_usd": costo.get("total_usd"),
        "budget": budget.snapshot() if budget else None,
        "budget_error": budget_error,
        "request_id": request_id,
        "agent_role": agent_role,
    }
    log_event(
        logger,
        "agent_done",
        request_id=request_id,
        role=agent_role,
        iteraciones=step,
        tokens=usage_total.get("input_tokens"),
        usd=costo.get("total_usd"),
        tiempo_s=tiempo_s,
    )
    return respuesta
