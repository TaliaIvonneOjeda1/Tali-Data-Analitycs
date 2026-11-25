"""Harness S1: acierto de respuesta (+ check de medida en consultas cuando hay).

Por defecto excluye holdout (P09, P11, P14, P18, P20).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.agent.loop import run_agent
from src.config import OUTPUTS_DIR, QUESTIONS_PATH, ROOT
from src.evals.tolerances import conteo_ok, montos_ok, pct_ok, ranking_ok
from src.tools.registry import execute_tool

HOLDOUT_IDS = frozenset({"P09", "P11", "P14", "P18", "P20"})
GOLD_PATH = Path(__file__).with_name("gold_s1.json")

# Medidas derivadas: no se re-ejecutan con consultar_medida.
DERIVED_MEASURE_TOOLS: dict[str, str] = {
    "desvio_presupuesto_pct": "calcular_desvio_presupuesto",
    "variacion_interanual_pct": "calcular_variacion_interanual",
    "participacion_pct": "calcular_participacion",
}
DERIVED_CHILD_HINTS: dict[str, frozenset[str]] = {
    "desvio_presupuesto_pct": frozenset({"ventas_netas", "presupuesto"}),
}


def _load_questions() -> dict[str, str]:
    items = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    return {i["id"]: i["texto"] for i in items}


def _load_gold() -> dict[str, Any]:
    return json.loads(GOLD_PATH.read_text(encoding="utf-8"))


def _extract_number(text: str) -> float | None:
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    # buscar número con posibles separadores
    matches = re.findall(r"-?\d+(?:[.,]\d+)?", str(text).replace(" ", ""))
    if not matches:
        return None
    # preferir el más largo (monto completo)
    raw = max(matches, key=len).replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _valor_respuesta(actual: dict[str, Any]) -> float | None:
    if actual.get("valor") is not None:
        try:
            return float(actual["valor"])
        except (TypeError, ValueError):
            pass
    return _extract_number(actual.get("texto") or "")


def _medida_en_consultas(actual: dict[str, Any], expected_medida: str | None) -> bool | None:
    if not expected_medida:
        return None
    consultas = actual.get("consultas") or []
    cuentas = " ".join(str(c) for c in (actual.get("cuentas") or []))
    ids = {c.get("medida") for c in consultas if isinstance(c, dict) and c.get("medida")}
    if expected_medida in ids:
        return True
    if expected_medida in cuentas:
        return True
    # Derivada: aceptar traza con consultas hijas típicas
    children = DERIVED_CHILD_HINTS.get(expected_medida)
    if children and children.issubset(ids):
        return True
    if not consultas and not cuentas:
        return False
    return False


def _compare_tol(got: float, exp: float, tol: str | None) -> bool:
    if tol == "monto":
        return montos_ok(got, exp)
    if tol in {"pct", "pp"}:
        return pct_ok(got, exp)
    if tol == "conteo":
        return conteo_ok(got, exp)
    return montos_ok(got, exp)


def _reexec_ok(actual: dict[str, Any], expected: dict[str, Any]) -> bool | None:
    """Re-ejecuta la consulta esperada; soporta medidas derivadas."""
    expected_medida = expected.get("medida")
    tol = expected.get("tol")
    reported = actual.get("valor")
    consultas = actual.get("consultas") or []

    # Preferir re-exec de la medida gold (derivada o base)
    if expected_medida in DERIVED_MEASURE_TOOLS:
        filtros = {}
        for c in consultas:
            if isinstance(c, dict) and (c.get("filtros") or {}):
                filtros = dict(c.get("filtros") or {})
                break
        tool = DERIVED_MEASURE_TOOLS[expected_medida]
        if tool == "calcular_desvio_presupuesto":
            payload = json.loads(execute_tool(tool, {"filtros": filtros}))
        elif tool == "calcular_variacion_interanual":
            payload = json.loads(
                execute_tool(
                    tool,
                    {"medida": "ventas_netas", "filtros": filtros},
                )
            )
        else:
            payload = json.loads(
                execute_tool(
                    tool,
                    {
                        "medida": "ventas_netas",
                        "filtros_parte": filtros,
                        "filtros_total": {
                            k: v
                            for k, v in filtros.items()
                            if k in {"anio_fiscal", "trimestre_fiscal", "mes_fiscal"}
                        },
                    },
                )
            )
        if payload.get("error"):
            return False
        if reported is None or payload.get("valor") is None:
            return False
        return _compare_tol(float(payload["valor"]), float(reported), tol)

    for c in consultas:
        medida = c.get("medida") if isinstance(c, dict) else None
        if not medida:
            continue
        if medida in DERIVED_MEASURE_TOOLS:
            continue
        filtros = c.get("filtros") or {}
        payload = json.loads(
            execute_tool("consultar_medida", {"medida": medida, "filtros": filtros})
        )
        if payload.get("error"):
            return False
        if reported is None:
            reported = payload.get("valor")
        if reported is None or payload.get("valor") is None:
            return False
        return _compare_tol(float(payload["valor"]), float(reported), tol)
    return None


def score_respuesta(actual: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    tipo = expected.get("tipo")
    tol = expected.get("tol")
    result: dict[str, Any] = {
        "tipo": tipo,
        "acierto_respuesta": False,
        "acierto_consulta": None,
        "detalle": {},
    }

    if tipo == "ranking":
        texto = (actual.get("texto") or "") + " " + json.dumps(actual, ensure_ascii=False)
        expected_set = expected.get("conjunto") or []
        found = [name for name in expected_set if name in texto]
        # también mirar filas en consultas
        for c in actual.get("consultas") or []:
            for row in c.get("filas") or []:
                for v in row.values():
                    if v in expected_set and v not in found:
                        found.append(v)
        ok = ranking_ok(found, expected_set) if found else False
        # si encontró todos los nombres en el texto
        if set(expected_set).issubset(set(found)):
            ok = True
        result["acierto_respuesta"] = ok
        result["detalle"]["encontrados"] = found
        result["detalle"]["esperados"] = expected_set
        med = _medida_en_consultas(actual, expected.get("medida"))
        result["acierto_consulta"] = med
        return result

    valor = _valor_respuesta(actual)
    expected_valor = float(expected["valor"])
    result["detalle"]["valor_actual"] = valor
    result["detalle"]["valor_esperado"] = expected_valor

    if valor is None:
        result["acierto_respuesta"] = False
    elif tol == "monto":
        result["acierto_respuesta"] = montos_ok(valor, expected_valor)
    elif tol in {"pct", "pp"}:
        result["acierto_respuesta"] = pct_ok(valor, expected_valor)
    elif tol == "conteo":
        result["acierto_respuesta"] = conteo_ok(valor, expected_valor)
    else:
        result["acierto_respuesta"] = montos_ok(valor, expected_valor)

    med_ok = _medida_en_consultas(actual, expected.get("medida"))
    reexec = _reexec_ok(actual, expected)
    if med_ok is False:
        result["acierto_consulta"] = False
    elif reexec is not None:
        result["acierto_consulta"] = bool(med_ok is not False and reexec)
    else:
        result["acierto_consulta"] = med_ok
    return result


def run_eval_suite(
    cases_path: Path | None = None,
    *,
    include_holdout: bool = False,
    ids: list[str] | None = None,
    verbose: bool = True,
) -> dict[str, Any]:
    """Corre gold S1 (o subset). `cases_path` se ignora si hay gold_s1; se mantiene por firma."""
    _ = cases_path  # compat scripts/run_evals.py
    questions = _load_questions()
    gold = _load_gold()
    selected = list(ids) if ids else list(gold.keys())
    if not include_holdout:
        selected = [i for i in selected if i not in HOLDOUT_IDS]

    results: dict[str, Any] = {}
    for qid in selected:
        if qid not in gold:
            results[qid] = {"error": "sin gold"}
            continue
        pregunta = questions[qid]
        if verbose:
            print(f"\n===== {qid}: {pregunta} =====")
        actual = run_agent(pregunta, verbose=verbose)
        scored = score_respuesta(actual, gold[qid])
        results[qid] = {
            "pregunta": pregunta,
            "score": scored,
            "respuesta": {k: v for k, v in actual.items() if not k.startswith("_")},
            "meta": actual.get("_meta"),
        }
        if verbose:
            print(f"SCORE {qid}: {scored}")

    n = len(results)
    n_ok = sum(1 for r in results.values() if r.get("score", {}).get("acierto_respuesta"))
    summary = {
        "n": n,
        "acierto_respuesta": n_ok,
        "include_holdout": include_holdout,
        "ids": selected,
        "casos": results,
    }
    OUTPUTS_DIR.mkdir(exist_ok=True)
    out = OUTPUTS_DIR / "eval_s1.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    if verbose:
        print(f"\nResumen: {n_ok}/{n} acierto_respuesta → {out}")
    return summary
