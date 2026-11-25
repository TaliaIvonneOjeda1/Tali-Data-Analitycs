"""Orquestación multi-agente S3 — workflow orchestrator-worker (código decide el flujo).

Fases fijas (M4: cuando las fases se conocen, el andamiaje lo escribe el código):

1. investigador  → hechos + consultas
2. analista      → síntesis / diagnóstico (sin tools)
3. redactor      → payload de informe (solo en run_informe) + PDF en código

Documentado en docs/S3_IMPLEMENTACION.md y ADR-014.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Callable

from src.agent.permissions import tools_for_agent
from src.agent.schemas import extract_json_block
from src.budget import Budget, BudgetExceeded
from src.config import (
    OUTPUTS_DIR,
    PRODUCT_INFORME_EXTRA_ITER_PER_FOCO,
    PRODUCT_INFORME_MAX_ITER,
    PRODUCT_INFORME_REDACTOR_RESERVE,
    PRODUCT_MAX_ITER,
)
from src.costing import add_usage, empty_usage, estimate_cost_usd
from src.enrich import enrich_respuesta
from src.multiagent.workers import pack_findings_for_downstream, run_worker
from src.reporting.names import (
    SUFIJO_CONSULTAS,
    SUFIJO_EJECUTIVO,
    informe_pdf_filename,
    informe_stem,
)
from src.reporting.pdf_report import build_pdf
from src.security.paths import safe_output_path
from src.tools.registry import execute_tool


def _normalize_consulta(c: Any) -> dict[str, Any] | None:
    if isinstance(c, dict):
        return c
    if isinstance(c, str) and c.strip():
        return {"medida": None, "filtros": {}, "sql": c.strip()}
    return None


def _merge_consultas(*sources: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for src in sources:
        buckets = list(src.get("consultas") or [])
        parsed = src.get("_parsed") or {}
        buckets.extend(parsed.get("consultas") or [])
        for raw in buckets:
            c = _normalize_consulta(raw)
            if not c:
                continue
            key = json.dumps(c, ensure_ascii=False, sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            out.append(c)
    return out


def _merge_cuentas(*sources: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for src in sources:
        for c in src.get("cuentas") or []:
            if c and c not in out:
                out.append(c)
        for c in (src.get("_parsed") or {}).get("cuentas") or []:
            if c and c not in out:
                out.append(c)
    return out


def _looks_like_informe_json(parsed: dict[str, Any] | None) -> bool:
    if not isinstance(parsed, dict) or not parsed:
        return False
    if parsed.get("indicadores") or parsed.get("conclusiones"):
        return True
    if parsed.get("resumen_ejecutivo") and (
        parsed.get("titulo") or parsed.get("indicadores") is not None
    ):
        return True
    return False


def _title_from_pedido(pedido: str, informe_id: str) -> str:
    clean = re.sub(r"\s+", " ", (pedido or "").strip())
    if len(clean) > 90:
        clean = clean[:87] + "…"
    return clean or f"Informe {informe_id}"


def detect_focos_pedido(pedido: str) -> list[dict[str, str]]:
    """Descompone un pedido exigente en focos investigables (máx. 3).

    Soporta consignas pegadas (I1+I2+I3) o frases del tipo
    «Preparame… Necesito… Armame…».
    """
    text = re.sub(r"\s+", " ", (pedido or "").strip())
    if not text:
        return [{"id": "unico", "titulo": "Pedido principal", "instruccion": ""}]

    catalog = [
        {
            "id": "presupuesto_enero",
            "pattern": r"cumplimiento de presupuesto|presupuesto de enero|enero de 2026.{0,40}categor",
            "titulo": "Cumplimiento de presupuesto · enero 2026",
            "instruccion": (
                "Informe de cumplimiento de presupuesto de enero de 2026 (calendario), "
                "por categoría y por región. Calculá desvíos vs presupuesto y señalá "
                "anomalías de carga si aparecen."
            ),
        },
        {
            "id": "margen_t2",
            "pattern": r"T2 del AF2026|foco en margen|margen.{0,30}AF2026|ejecutivo del T2",
            "titulo": "Margen · T2 AF2026",
            "instruccion": (
                "Informe ejecutivo del T2 del AF2026 con foco en margen bruto, "
                "variación interanual (pp) y cortes útiles por categoría/región."
            ),
        },
        {
            "id": "oeste_af2026",
            "pattern": r"regi[oó]n Oeste|gerente de la regi",
            "titulo": "Región Oeste · AF2026",
            "instruccion": (
                "Informe del AF2026 para el gerente de la región Oeste: ventas, margen, "
                "desvíos y comparables (mismas sucursales) de Oeste cuando sea posible."
            ),
        },
    ]
    focos: list[dict[str, str]] = []
    for item in catalog:
        if re.search(item["pattern"], text, flags=re.IGNORECASE):
            focos.append(
                {
                    "id": item["id"],
                    "titulo": item["titulo"],
                    "instruccion": item["instruccion"],
                }
            )
    if len(focos) >= 2:
        return focos[:3]

    parts = re.split(
        r"(?<=[.!?])\s+(?=(?:Preparame|Necesito|Armame|Quiero|Haceme|Generame)\b)",
        text,
        flags=re.IGNORECASE,
    )
    parts = [p.strip(" .") for p in parts if len(p.strip()) > 25]
    if len(parts) >= 2:
        out: list[dict[str, str]] = []
        for i, part in enumerate(parts[:3], 1):
            out.append(
                {
                    "id": f"foco_{i}",
                    "titulo": (part[:64] + "…") if len(part) > 64 else part,
                    "instruccion": part,
                }
            )
        return out

    if focos:
        return focos[:1]
    return [{"id": "unico", "titulo": "Pedido principal", "instruccion": text}]


def _merge_investigaciones(
    pedido: str, focos: list[dict[str, str]], parts: list[dict[str, Any]]
) -> dict[str, Any]:
    """Fusiona varios pases del investigador en un único paquete para el analista."""
    textos = []
    hallazgos: list[Any] = []
    for foco, part in zip(focos, parts):
        parsed = part.get("_parsed") or {}
        resumen = parsed.get("texto") or part.get("texto") or ""
        textos.append(f"[{foco['titulo']}] {resumen}".strip())
        for h in parsed.get("hallazgos") or []:
            if isinstance(h, dict):
                hallazgos.append({**h, "foco": foco["titulo"]})
            else:
                hallazgos.append({"titulo": str(h), "foco": foco["titulo"]})
    merged = {
        "pregunta": pedido,
        "texto": "\n\n".join(t for t in textos if t),
        "hallazgos": hallazgos,
        "valor": None,
        "unidad": None,
        "supuestos": [],
        "consultas": _merge_consultas(*parts),
        "cuentas": _merge_cuentas(*parts),
        "alertas": [],
        "focos": focos,
        "_parsed": {},
    }
    for part in parts:
        for s in (part.get("_parsed") or {}).get("supuestos") or part.get("supuestos") or []:
            if s and s not in merged["supuestos"]:
                merged["supuestos"].append(s)
        for alerta in (part.get("_parsed") or {}).get("alertas") or part.get("alertas") or []:
            if alerta and alerta not in merged["alertas"]:
                merged["alertas"].append(alerta)
    merged["_parsed"] = {
        "texto": merged["texto"],
        "hallazgos": hallazgos,
        "consultas": merged["consultas"],
        "cuentas": merged["cuentas"],
        "supuestos": merged["supuestos"],
        "alertas": merged["alertas"],
        "focos": focos,
    }
    return merged


def _indicadores_from_evidence(*sources: dict[str, Any]) -> list[dict[str, Any]]:
    """Arma indicadores a partir de consultas/cuentas ya trazadas."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(nombre: str, valor: Any, unidad: Any = None, nota: str = "") -> None:
        key = nombre.strip().lower()
        if not key or key in seen:
            return
        seen.add(key)
        item: dict[str, Any] = {"nombre": nombre.strip(), "valor": valor}
        if unidad:
            item["unidad"] = unidad
        if nota:
            item["nota"] = nota
        out.append(item)

    for src in sources:
        for c in src.get("consultas") or []:
            if not isinstance(c, dict) or c.get("valor") is None:
                continue
            medida = c.get("medida") or "Indicador"
            filtros = c.get("filtros") or {}
            filtro_txt = ", ".join(f"{k}={v}" for k, v in list(filtros.items())[:3])
            nombre = f"{medida}" + (f" ({filtro_txt})" if filtro_txt else "")
            _add(nombre, c.get("valor"), c.get("unidad"), "Derivado de consulta registrada")
        for cuenta in src.get("cuentas") or []:
            text = str(cuenta)
            match = re.search(
                r"([A-Za-zÁÉÍÓÚáéíóúñÑ0-9_ %().]+?)\s*=\s*(-?\d+(?:\.\d+)?)",
                text,
            )
            if not match:
                continue
            nombre = match.group(1).strip()
            try:
                valor = float(match.group(2))
            except ValueError:
                continue
            unidad = None
            lower = text.lower()
            if "pp" in lower:
                unidad = "pp"
            elif "%" in text or "pct" in lower:
                unidad = "%"
            elif "ars" in lower:
                unidad = "ARS"
            _add(nombre[:80], valor, unidad, "Derivado de cuenta registrada")
            if len(out) >= 8:
                return out
    return out[:8]


def _conclusiones_from_analista(an: dict[str, Any]) -> list[str]:
    parsed = an.get("_parsed") or {}
    conc = parsed.get("conclusiones") or an.get("conclusiones") or []
    if isinstance(conc, list) and conc:
        return [str(c).strip() for c in conc if str(c).strip()][:5]
    texto = str(parsed.get("texto") or an.get("texto") or "").strip()
    if not texto or texto.lower().startswith("se detuvo por presupuesto"):
        return [
            "La evidencia reunida alcanza para una lectura parcial del pedido.",
            "Conviene reconsultar los cortes sin filas antes de cerrar decisiones.",
            "Priorizar un único foco de informe mejora la calidad del PDF.",
        ]
    bullets: list[str] = []
    for raw in re.split(r"\n+", texto):
        line = re.sub(r"^\s*\d+\)\s*", "", raw).strip(" -•\t")
        if len(line) < 40:
            continue
        bullets.append(line[:280])
        if len(bullets) >= 4:
            break
    if bullets:
        return bullets
    return [texto[:280]]


def _grafico_from_indicadores(
    indicadores: list[dict[str, Any]],
    informe_id: str,
    *,
    from_session: bool = False,
) -> dict[str, Any] | None:
    numeric: list[dict[str, Any]] = []
    for ind in indicadores:
        valor = ind.get("valor")
        if isinstance(valor, bool):
            continue
        if isinstance(valor, (int, float)):
            numeric.append(ind)
        elif isinstance(valor, str):
            try:
                numeric.append({**ind, "valor": float(valor.replace(",", "."))})
            except ValueError:
                continue
    if len(numeric) < 2:
        return None
    # Preferir indicadores con misma unidad aproximada
    picked = numeric[:4]
    stem = informe_stem(informe_id, from_session=from_session)
    return {
        "etiquetas": [str(i.get("nombre") or f"Ind {n+1}")[:28] for n, i in enumerate(picked)],
        "valores": [float(i["valor"]) for i in picked],
        "titulo": "Indicadores del informe",
        "ylabel": str(picked[0].get("unidad") or ""),
        "nombre_archivo": f"{stem}_chart.png",
    }


def _build_informe_fallback(
    pedido: str,
    informe_id: str,
    inv: dict[str, Any],
    an: dict[str, Any],
    *,
    motivo: str,
    focos: list[dict[str, str]] | None = None,
    from_session: bool = False,
) -> dict[str, Any]:
    """Payload mínimo viable cuando el redactor no entrega JSON usable."""
    indicadores = _indicadores_from_evidence(inv, an)
    conclusiones = _conclusiones_from_analista(an)
    resumen = (
        (an.get("_parsed") or {}).get("texto")
        or an.get("texto")
        or (inv.get("_parsed") or {}).get("texto")
        or inv.get("texto")
        or "Informe armado con evidencia parcial."
    )
    if isinstance(resumen, str) and resumen.lower().startswith("se detuvo por presupuesto"):
        resumen = (
            (inv.get("_parsed") or {}).get("texto")
            or inv.get("texto")
            or "Informe armado con evidencia parcial del investigador."
        )
    focos = focos or list((inv.get("_parsed") or {}).get("focos") or inv.get("focos") or [])
    if len(focos) > 1:
        titulo = "Informe ejecutivo fusionado · " + " · ".join(
            f["titulo"] for f in focos[:3]
        )
        if len(titulo) > 110:
            titulo = titulo[:107] + "…"
    else:
        titulo = _title_from_pedido(pedido, informe_id)
    supuestos = [f"Informe armado por fallback: {motivo}"]
    if len(focos) > 1:
        supuestos.append(
            "Pedido compuesto: se investigaron varios focos y se fusionaron en un solo PDF."
        )
    an_parsed = an.get("_parsed") or {}
    return {
        "pedido": pedido,
        "titulo": titulo,
        "periodo": "",
        "audiencia": "dirección",
        "pregunta_negocio": pedido,
        "resumen_ejecutivo": str(resumen)[:2500],
        "indicadores": indicadores,
        "grafico": _grafico_from_indicadores(
            indicadores, informe_id, from_session=from_session
        ),
        "hallazgos": [],
        "conclusiones": conclusiones,
        "proximos_pasos": list(an_parsed.get("proximos_pasos") or []),
        "supuestos": supuestos,
        "limitaciones": [],
        "consultas": _merge_consultas(inv, an),
        "cuentas": _merge_cuentas(inv, an),
        "_fallback": True,
        "focos": focos,
    }


def run_diagnostico(
    pregunta: str,
    *,
    verbose: bool = True,
    enable_budget: bool = False,
    budget: Budget | None = None,
    request_id: str | None = None,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Diagnóstico multi-agente: investigador → analista."""
    started = time.perf_counter()
    usage = empty_usage()
    pasos: list[dict[str, Any]] = []
    if enable_budget and budget is None:
        budget = Budget()
    inv_iters = min(10, PRODUCT_MAX_ITER) if enable_budget else 14

    instr_inv = (
        f"Investigá con tools esta pregunta de diagnóstico:\n{pregunta}\n\n"
        "Reuní margen/ventas del período, variación vs año anterior (en pp si es margen), "
        "y al menos un corte (proveedor, subcategoría o región) que ayude a explicar el cambio. "
        "Registrá todas las consultas. trimestre_fiscal es int (1-4)."
    )
    inv = run_worker(
        "investigador",
        instr_inv,
        max_iteraciones=inv_iters,
        verbose=verbose,
        enable_budget=enable_budget,
        budget=budget,
        request_id=request_id,
        on_progress=on_progress,
    )
    add_usage(usage, (inv.get("_meta") or {}).get("usage"))
    pasos.append({"rol": "investigador", "meta": inv.get("_meta"), "respuesta": {k: v for k, v in inv.items() if not k.startswith("_")}})

    pack = pack_findings_for_downstream(inv)
    instr_an = (
        f"Pregunta original:\n{pregunta}\n\n"
        f"{pack}\n\n"
        "Redactá el diagnóstico: qué pasó, qué lo explica con los números dados, "
        "qué queda como hipótesis y qué no se puede afirmar."
    )
    an = run_worker(
        "analista",
        instr_an,
        max_iteraciones=4,
        verbose=verbose,
        enable_budget=enable_budget,
        budget=budget,
        request_id=request_id,
        on_progress=on_progress,
    )
    add_usage(usage, (an.get("_meta") or {}).get("usage"))
    pasos.append({"rol": "analista", "meta": an.get("_meta"), "respuesta": {k: v for k, v in an.items() if not k.startswith("_")}})

    parsed_an = an.get("_parsed") or {}
    respuesta = {
        "pregunta": pregunta,
        "texto": parsed_an.get("texto") or an.get("texto"),
        "valor": None,
        "unidad": None,
        "supuestos": parsed_an.get("supuestos") or an.get("supuestos") or [],
        "consultas": _merge_consultas(inv, an),
        "cuentas": _merge_cuentas(inv, an),
        "conclusiones": parsed_an.get("conclusiones") or [],
        "proximos_pasos": parsed_an.get("proximos_pasos") or [],
        "agentes": {
            "patron": "orchestrator-worker",
            "flujo": ["investigador", "analista"],
            "tools_por_agente": {
                "investigador": tools_for_agent("investigador"),
                "analista": tools_for_agent("analista"),
            },
        },
        "costo": {
            "usage": usage,
            **estimate_cost_usd(usage),
            "tiempo_s": round(time.perf_counter() - started, 2),
        },
        "_pasos": pasos,
    }
    return respuesta


def run_informe(
    pedido: str,
    *,
    informe_id: str = "adhoc",
    verbose: bool = True,
    enable_budget: bool = False,
    budget: Budget | None = None,
    request_id: str | None = None,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
    output_dir: Path | None = None,
    evidencia_sesion: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Informe multi-agente: investigador → analista → redactor → PDF código.

    Si el pedido exige varios focos, investiga cada uno y fusiona la evidencia
    en un único informe ejecutivo.

    Si `evidencia_sesion` viene de una ConversationSession, se saltea el
    investigador y se sintetiza sobre hallazgos ya validados por el usuario.
    """
    started = time.perf_counter()
    usage = empty_usage()
    pasos: list[dict[str, Any]] = []
    out_dir = output_dir or OUTPUTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    from_session = bool(evidencia_sesion)
    focos = [] if from_session else detect_focos_pedido(pedido)
    multi = len(focos) > 1
    reserve = max(2, PRODUCT_INFORME_REDACTOR_RESERVE)
    if enable_budget and budget is None:
        # Desde sesión: sin investigador → menos iteraciones
        max_iter = 10 if from_session else PRODUCT_INFORME_MAX_ITER
        if multi:
            max_iter += PRODUCT_INFORME_EXTRA_ITER_PER_FOCO * (len(focos) - 1)
        budget = Budget(max_iter=max_iter)
    elif enable_budget and budget is not None and multi:
        budget.max_iter = max(
            budget.max_iter,
            PRODUCT_INFORME_MAX_ITER
            + PRODUCT_INFORME_EXTRA_ITER_PER_FOCO * (len(focos) - 1),
        )

    inv_parts: list[dict[str, Any]] = []
    if from_session:
        assert evidencia_sesion is not None
        if on_progress:
            on_progress(
                {
                    "phase": "worker_start",
                    "role": "investigador",
                    "foco": "sesion",
                    "request_id": request_id,
                    "skipped": True,
                    "reason": "evidencia_sesion",
                }
            )
        inv = dict(evidencia_sesion)
        if "_parsed" not in inv:
            inv["_parsed"] = {
                k: inv.get(k)
                for k in ("texto", "hallazgos", "consultas", "cuentas", "supuestos")
                if k in inv
            }
        inv["_meta"] = {
            "origen": "sesion_exploracion",
            "n_turnos": inv.get("n_turnos"),
            "skipped_tools": True,
        }
        pasos.append(
            {
                "rol": "investigador",
                "origen": "sesion_exploracion",
                "meta": inv.get("_meta"),
                "respuesta": {k: v for k, v in inv.items() if not k.startswith("_")},
            }
        )
    elif multi:
        # Reparte iteraciones de investigación entre focos, reservando analista+redactor.
        if enable_budget and budget is not None:
            inv_pool = max(6, budget.max_iter - reserve - 3)
            per_foco = max(4, inv_pool // len(focos))
        else:
            per_foco = 8
        for foco in focos:
            if on_progress:
                on_progress(
                    {
                        "phase": "worker_start",
                        "role": "investigador",
                        "foco": foco["id"],
                        "request_id": request_id,
                    }
                )
            instr_inv = (
                f"Pedido completo del usuario:\n{pedido}\n\n"
                f"FOCO A INVESTIGAR AHORA ({foco['titulo']}):\n{foco['instruccion']}\n\n"
                "Reuní indicadores clave de ESTE foco con tools. "
                "Devolvé hallazgos con valores y consultas. "
                "trimestre_fiscal es INTEGER (1-4), nunca 'T2'. "
                "No intentes cubrir los otros focos en este pase."
            )
            part = run_worker(
                "investigador",
                instr_inv,
                max_iteraciones=per_foco,
                verbose=verbose,
                enable_budget=enable_budget,
                budget=budget,
                request_id=request_id,
                on_progress=on_progress,
            )
            add_usage(usage, (part.get("_meta") or {}).get("usage"))
            inv_parts.append(part)
            pasos.append(
                {
                    "rol": "investigador",
                    "foco": foco,
                    "meta": part.get("_meta"),
                    "respuesta": {k: v for k, v in part.items() if not k.startswith("_")},
                }
            )
        inv = _merge_investigaciones(pedido, focos, inv_parts)
    else:
        if enable_budget and budget is not None:
            inv_cap = max(4, budget.max_iter - reserve - 2)
            inv_iters = min(10, inv_cap)
        else:
            inv_iters = 12
        instr_inv = (
            f"Pedido de informe:\n{pedido}\n\n"
            "Reuní indicadores clave del período pedido (ventas netas, margen %, "
            "variaciones relevantes, rankings útiles). "
            "Si el foco es margen, priorizá margen_pct y la variación en puntos "
            "porcentuales vs el mismo trimestre del año anterior, más cortes por "
            "categoría/región. Preferí variación interanual total primero; "
            "comparables (mismas sucursales) solo si el presupuesto de tools alcanza. "
            "Devolvé hallazgos con valores y consultas. "
            "trimestre_fiscal es INTEGER (1-4), nunca el texto 'T2' como filtro."
        )
        inv = run_worker(
            "investigador",
            instr_inv,
            max_iteraciones=inv_iters,
            verbose=verbose,
            enable_budget=enable_budget,
            budget=budget,
            request_id=request_id,
            on_progress=on_progress,
        )
        add_usage(usage, (inv.get("_meta") or {}).get("usage"))
        pasos.append(
            {
                "rol": "investigador",
                "meta": inv.get("_meta"),
                "respuesta": {k: v for k, v in inv.items() if not k.startswith("_")},
            }
        )

    pack = pack_findings_for_downstream(inv)
    if from_session:
        instr_an = (
            f"Pedido de informe:\n{pedido}\n\n"
            "La evidencia ya fue reunida por el usuario en una sesión de exploración "
            "(preguntas sucesivas con traza). NO inventes cifras fuera de este bloque.\n\n"
            f"{pack}\n\n"
            "Escribí una síntesis ejecutiva que una esos hallazgos: qué importó, "
            "riesgos y 3-5 conclusiones accionables alineadas a los intereses del usuario. "
            "Si algún corte falta, declaralo como limitación; no lo completes de memoria."
        )
    elif multi:
        focos_txt = "\n".join(f"- {f['titulo']}: {f['instruccion']}" for f in focos)
        instr_an = (
            f"Pedido compuesto del usuario:\n{pedido}\n\n"
            f"Focos que DEBEN quedar cubiertos en la fusión:\n{focos_txt}\n\n"
            f"{pack}\n\n"
            "Escribí UNA síntesis ejecutiva fusionada que responda TODOS los focos. "
            "Organizá el texto por secciones numeradas (una por foco). "
            "Separá hechos de hipótesis. "
            "Entregá 4-7 conclusiones accionables que, en conjunto, cubran cada foco. "
            "Sin inventar números."
        )
    else:
        instr_an = (
            f"Pedido de informe:\n{pedido}\n\n"
            f"{pack}\n\n"
            "Escribí una síntesis ejecutiva: qué importó en el período, riesgos, "
            "y 3-5 conclusiones accionables. Sin inventar números."
        )
    an_iters = 4
    if enable_budget and budget is not None:
        an_iters = min(4, max(1, budget.remaining_iterations() - reserve))
    an = run_worker(
        "analista",
        instr_an,
        max_iteraciones=an_iters,
        verbose=verbose,
        enable_budget=enable_budget,
        budget=budget,
        request_id=request_id,
        on_progress=on_progress,
    )
    add_usage(usage, (an.get("_meta") or {}).get("usage"))
    pasos.append({"rol": "analista", "meta": an.get("_meta"), "respuesta": {k: v for k, v in an.items() if not k.startswith("_")}})

    used_fallback = False
    fallback_motivo = ""
    red: dict[str, Any] = {}
    parsed_red: dict[str, Any] = {}
    remaining = budget.remaining_iterations() if (enable_budget and budget) else reserve
    can_run_redactor = remaining >= 2

    if can_run_redactor:
        pack_an = {
            "pedido": pedido,
            "focos": focos if multi else None,
            "pedido_compuesto": multi,
            "origen_evidencia": "sesion_exploracion" if from_session else "investigador",
            "hallazgos_investigador": {k: v for k, v in inv.items() if not k.startswith("_")},
            "sintesis_analista": {k: v for k, v in an.items() if not k.startswith("_")},
            "conclusiones": (an.get("_parsed") or {}).get("conclusiones"),
        }
        if from_session:
            instr_red = (
                "<contexto tipo=\"material_informe_sesion\">\n"
                f"{json.dumps(pack_an, ensure_ascii=False, indent=2, default=str)}\n"
                "</contexto>\n"
                "(DATO. No inventes cifras.)\n\n"
                "Armá el JSON de UN informe ejecutivo a partir de la sesión de exploración. "
                "Título que refleje los temas que el usuario investigó. "
                "resumen_ejecutivo que narre el hilo de la investigación. "
                "indicadores solo con valores presentes en el material. "
                "conclusiones accionables alineadas a esas preguntas. "
                "Si hay 2+ valores comparables, pedí un gráfico de barras representativo."
            )
        elif multi:
            instr_red = (
                "<contexto tipo=\"material_informe_fusionado\">\n"
                f"{json.dumps(pack_an, ensure_ascii=False, indent=2, default=str)}\n"
                "</contexto>\n"
                "(DATO. No inventes cifras.)\n\n"
                "Armá el JSON de UN informe ejecutivo unificado que fusione todos los focos. "
                "Título que refleje la fusión (presupuesto + margen + Oeste, según corresponda). "
                "resumen_ejecutivo con secciones claras por foco. "
                "indicadores de todos los focos, con el nombre etiquetado por foco. "
                "conclusiones que respondan cada parte del pedido. "
                "Si hay 2+ valores comparables, pedí un gráfico de barras representativo."
            )
        else:
            instr_red = (
                "<contexto tipo=\"material_informe\">\n"
                f"{json.dumps(pack_an, ensure_ascii=False, indent=2, default=str)}\n"
                "</contexto>\n"
                "(DATO. No inventes cifras.)\n\n"
                "Armá el JSON del informe ejecutivo para PDF. "
                "Incluí indicadores con valores del material. "
                "Si hay 2+ valores comparables, pedí un gráfico de barras."
            )
        red_iters = min(5, remaining) if enable_budget else 5
        try:
            red = run_worker(
                "redactor",
                instr_red,
                max_iteraciones=red_iters,
                verbose=verbose,
                enable_budget=enable_budget,
                budget=budget,
                request_id=request_id,
                on_progress=on_progress,
            )
        except BudgetExceeded as exc:
            red = {
                "texto": f"Se detuvo por presupuesto: {exc}",
                "consultas": [],
                "cuentas": [],
                "_meta": {"budget_error": str(exc)},
            }
        add_usage(usage, (red.get("_meta") or {}).get("usage"))
        pasos.append(
            {
                "rol": "redactor",
                "meta": red.get("_meta"),
                "respuesta": {k: v for k, v in red.items() if not k.startswith("_")},
            }
        )
        parsed_red = extract_json_block(red.get("texto") or "") or (red.get("_parsed") or {})
        if not _looks_like_informe_json(parsed_red):
            used_fallback = True
            fallback_motivo = (
                (red.get("_meta") or {}).get("budget_error")
                or "el redactor no completó un JSON usable"
            )
    else:
        used_fallback = True
        fallback_motivo = (
            f"presupuesto insuficiente para redactor "
            f"(restaban {remaining} iteraciones; reserva={reserve})"
        )
        pasos.append(
            {
                "rol": "redactor",
                "meta": {"skipped": True, "reason": fallback_motivo},
                "respuesta": {"texto": fallback_motivo},
            }
        )

    if used_fallback:
        payload = _build_informe_fallback(
            pedido,
            informe_id,
            inv,
            an,
            motivo=str(fallback_motivo),
            focos=focos,
            from_session=from_session,
        )
        consultas = list(payload.get("consultas") or [])
        cuentas = list(payload.get("cuentas") or [])
    else:
        consultas = _merge_consultas(inv, an, red)
        if parsed_red.get("consultas"):
            consultas = _merge_consultas(
                {"consultas": consultas}, {"consultas": parsed_red["consultas"]}
            )
        cuentas = _merge_cuentas(inv, an, red)
        if parsed_red.get("cuentas"):
            for c in parsed_red["cuentas"]:
                if c not in cuentas:
                    cuentas.append(c)
        an_parsed = an.get("_parsed") or {}
        proximos = list(
            parsed_red.get("proximos_pasos")
            or an_parsed.get("proximos_pasos")
            or []
        )
        payload = {
            "pedido": pedido,
            "titulo": parsed_red.get("titulo") or f"Informe {informe_id}",
            "periodo": parsed_red.get("periodo") or "",
            "audiencia": parsed_red.get("audiencia") or "",
            "pregunta_negocio": parsed_red.get("pregunta_negocio") or pedido,
            "resumen_ejecutivo": parsed_red.get("resumen_ejecutivo")
            or an_parsed.get("texto")
            or an.get("texto"),
            "indicadores": parsed_red.get("indicadores") or [],
            "grafico": parsed_red.get("grafico"),
            "hallazgos": list(parsed_red.get("hallazgos") or []),
            "conclusiones": parsed_red.get("conclusiones")
            or an_parsed.get("conclusiones")
            or [],
            "proximos_pasos": proximos,
            "supuestos": list(parsed_red.get("supuestos") or []),
            "limitaciones": list(parsed_red.get("limitaciones") or [])[:5],
            "glosario": list(parsed_red.get("glosario") or []),
            "consultas": consultas,
            "cuentas": cuentas,
        }
        # Si el redactor entregó JSON pero sin estructura útil, completar con fallback parcial
        if not payload["indicadores"] and not payload["conclusiones"]:
            fb = _build_informe_fallback(
                pedido,
                informe_id,
                inv,
                an,
                motivo="JSON del redactor sin indicadores/conclusiones",
                focos=focos,
                from_session=from_session,
            )
            payload["indicadores"] = fb["indicadores"]
            payload["conclusiones"] = fb["conclusiones"]
            if not payload.get("grafico"):
                payload["grafico"] = fb.get("grafico")
            payload["supuestos"] = list(payload.get("supuestos") or []) + list(
                fb.get("supuestos") or []
            )
            used_fallback = True
        if multi:
            payload["supuestos"] = list(payload.get("supuestos") or [])
            note = "Pedido compuesto: el PDF fusiona todos los focos solicitados."
            if note not in payload["supuestos"]:
                payload["supuestos"].append(note)

    file_stem = informe_stem(informe_id, from_session=from_session)
    pdf_name = informe_pdf_filename(informe_id, from_session=from_session)

    # Si el redactor pidió gráfico pero no lo ejecutó como tool, generarlo acá
    chart_path = None
    grafico = payload.get("grafico")
    if isinstance(grafico, dict) and grafico.get("etiquetas") and grafico.get("valores"):
        chart_json = execute_tool(
            "generar_grafico_barras",
            {
                "etiquetas": grafico["etiquetas"],
                "valores": grafico["valores"],
                "titulo": grafico.get("titulo") or "",
                "ylabel": grafico.get("ylabel") or "",
                "nombre_archivo": grafico.get("nombre_archivo")
                or f"{file_stem}_chart.png",
                "tipo": grafico.get("tipo")
                or (
                    "lineas"
                    if any(
                        any(
                            m in str(e).lower()
                            for m in (
                                "t1",
                                "t2",
                                "t3",
                                "t4",
                                "af",
                                "2024",
                                "2025",
                                "2026",
                                "ene",
                                "feb",
                                "mar",
                                "abr",
                                "may",
                                "jun",
                                "jul",
                                "ago",
                                "sep",
                                "oct",
                                "nov",
                                "dic",
                            )
                        )
                        for e in (grafico.get("etiquetas") or [])
                    )
                    else "barras"
                ),
            },
        )
        chart_info = json.loads(chart_json)
        if chart_info.get("ok"):
            chart_name = Path(str(chart_info.get("path") or "")).name
            resolved = OUTPUTS_DIR / chart_name
            chart_path = str(resolved if resolved.is_file() else chart_name)
            payload["chart_path"] = chart_path
            cuenta = chart_info.get("cuenta")
            if cuenta and cuenta not in payload["cuentas"]:
                payload["cuentas"].append(cuenta)

    pdf_path = safe_output_path(pdf_name, base_dir=out_dir, default="Informe-Consultas.pdf")
    # build_pdf espera Path completo; safe_output_path ya está bajo out_dir
    build_pdf(pedido, payload, pdf_path)

    costo = {
        "usage": usage,
        **estimate_cost_usd(usage),
        "tiempo_s": round(time.perf_counter() - started, 2),
    }

    if from_session:
        flujo = ["evidencia_sesion", "analista", "redactor", "pdf_codigo"]
    elif multi:
        flujo = ["investigador_por_foco", "fusion", "analista", "redactor", "pdf_codigo"]
    else:
        flujo = ["investigador", "analista", "redactor", "pdf_codigo"]
    if used_fallback:
        flujo = [step for step in flujo if step != "redactor"] + [
            "fallback_estructura",
            "pdf_codigo",
        ]
        # evitar pdf_codigo duplicado
        dedup: list[str] = []
        for step in flujo:
            if step not in dedup:
                dedup.append(step)
        flujo = dedup

    informe = {
        "pedido": pedido,
        "informe_id": informe_id,
        "nombre_archivo": pdf_name,
        "tipo_informe": (
            SUFIJO_CONSULTAS
            if file_stem.endswith(f"-{SUFIJO_CONSULTAS}")
            else SUFIJO_EJECUTIVO
        ),
        "pdf": str(pdf_path),
        "consultas": consultas,
        "cuentas": payload["cuentas"],
        "titulo": payload["titulo"],
        "resumen_ejecutivo": payload["resumen_ejecutivo"],
        "indicadores": payload["indicadores"],
        "conclusiones": payload["conclusiones"],
        "chart_path": chart_path,
        "fallback_estructura": used_fallback,
        "pedido_compuesto": multi,
        "origen_evidencia": "sesion_exploracion" if from_session else "investigador",
        "focos": focos,
        "agentes": {
            "patron": "orchestrator-worker",
            "flujo": flujo,
            "tools_por_agente": {
                "investigador": tools_for_agent("investigador"),
                "analista": tools_for_agent("analista"),
                "redactor": tools_for_agent("redactor"),
            },
            "por_que": (
                "Diagnóstico/informe piden descomponer, consultar varias dimensiones "
                "y redactar: un agente simple no alcanza (Caso1 S3 / M4)."
                + (
                    " Pedido compuesto: se investigó por foco y se fusionó en un PDF."
                    if multi
                    else ""
                )
            ),
        },
        "costo": costo,
        "tiempo_s": costo["tiempo_s"],
        "_pasos": pasos,
    }
    enriched = enrich_respuesta(
        {
            "pregunta": pedido,
            "texto": informe.get("resumen_ejecutivo") or "",
            "valor": None,
            "consultas": consultas,
            "cuentas": informe["cuentas"],
        }
    )
    informe["siguiente_pregunta_sugerida"] = enriched.get(
        "siguiente_pregunta_sugerida"
    )
    informe["alerta_desvio"] = enriched.get("alerta_desvio")
    return informe


def save_result(result: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from src.persist import save_informe_json

        if "pedido" in result and ("pdf" in result or "consultas" in result):
            save_informe_json(result, path)
            return path
    except Exception:  # noqa: BLE001
        pass
    serializable = json.loads(json.dumps(result, ensure_ascii=False, default=str))
    path.write_text(
        json.dumps(serializable, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
