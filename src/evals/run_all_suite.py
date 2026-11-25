"""Corrida completa S6: 20 preguntas + 5 conversaciones + 3 informes."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from src.agent.conversation import run_conversation
from src.agent.loop import run_agent
from src.config import DATA_DIR, OUTPUTS_DIR
from src.costing import add_usage, empty_usage, estimate_cost_usd
from src.multiagent.orchestrator import run_informe, save_result
from src.persist import save_respuesta_json


def _load_json(name: str) -> Any:
    return json.loads((DATA_DIR / "preguntas" / name).read_text(encoding="utf-8"))


def _usage_from_meta(meta: dict[str, Any] | None) -> dict[str, int]:
    return dict((meta or {}).get("usage") or empty_usage())


def _run_question(item: dict[str, str], verbose: bool) -> dict[str, Any]:
    qid = item["id"]
    started = time.perf_counter()
    result = run_agent(item["texto"], verbose=verbose, enable_prompt_cache=True)
    path = OUTPUTS_DIR / "run_all" / "preguntas" / f"{qid}.json"
    try:
        save_respuesta_json(result, path)
    except ValueError:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    meta = result.get("_meta") or {}
    return {
        "id": qid,
        "tipo": "pregunta",
        "ok": bool((result.get("texto") or "").strip()),
        "valor": result.get("valor"),
        "path": str(path),
        "usage": _usage_from_meta(meta),
        "tiempo_s": round(time.perf_counter() - started, 2),
        "structured_ok": meta.get("structured_output_ok"),
        "cache_read": meta.get("cache_read_input_tokens"),
    }


def _run_conversation(item: dict[str, Any], verbose: bool) -> dict[str, Any]:
    cid = item["id"]
    started = time.perf_counter()
    result = run_conversation(
        list(item["turnos"]), conversation_id=cid, verbose=verbose
    )
    path = OUTPUTS_DIR / "run_all" / "conversaciones" / f"{cid}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    usage = dict(result.get("usage_total") or empty_usage())
    return {
        "id": cid,
        "tipo": "conversacion",
        "ok": len(result.get("turnos") or []) == len(item["turnos"]),
        "turnos": len(result.get("turnos") or []),
        "path": str(path),
        "usage": usage,
        "tiempo_s": round(time.perf_counter() - started, 2),
    }


def _run_informe(item: dict[str, str], verbose: bool) -> dict[str, Any]:
    iid = item["id"]
    started = time.perf_counter()
    result = run_informe(item["texto"], informe_id=iid, verbose=verbose)
    path = save_result(result, OUTPUTS_DIR / "run_all" / "informes" / f"{iid}.json")
    costo = result.get("costo") or {}
    usage = dict(costo.get("usage") or empty_usage())
    return {
        "id": iid,
        "tipo": "informe",
        "ok": Path(result.get("pdf") or "").is_file(),
        "pdf": result.get("pdf"),
        "path": str(path),
        "usage": usage,
        "costo_usd": costo.get("total_usd"),
        "tiempo_s": round(time.perf_counter() - started, 2),
    }


def _parallel_map(
    items: list[Any],
    fn: Callable[[Any], dict[str, Any]],
    *,
    max_workers: int,
) -> list[dict[str, Any]]:
    if not items:
        return []
    out: list[dict[str, Any]] = []
    workers = max(1, min(max_workers, len(items)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(fn, item): item for item in items}
        for fut in as_completed(futs):
            out.append(fut.result())
    # orden estable por id
    out.sort(key=lambda x: x.get("id") or "")
    return out


def run_all(
    *,
    smoke: bool = False,
    skip_informes: bool = False,
    max_workers: int = 5,
    verbose: bool = False,
) -> dict[str, Any]:
    """Un comando: preguntas + conversaciones + informes, con costo y tiempo."""
    started = time.perf_counter()
    OUTPUTS_DIR.mkdir(exist_ok=True)
    (OUTPUTS_DIR / "run_all").mkdir(exist_ok=True)

    preguntas = _load_json("preguntas.json")
    conversaciones = _load_json("conversaciones.json")
    informes = _load_json("pedidos_de_informe.json")

    if smoke:
        # Subset barato para validar el harness
        preguntas = [p for p in preguntas if p["id"] in {"P01", "P05", "P19"}]
        conversaciones = [c for c in conversaciones if c["id"] == "C5"]
        informes = [] if skip_informes else [i for i in informes if i["id"] == "I1"][:1]

    usage_total = empty_usage()
    resultados: dict[str, list[dict[str, Any]]] = {
        "preguntas": [],
        "conversaciones": [],
        "informes": [],
    }

    resultados["preguntas"] = _parallel_map(
        preguntas,
        lambda p: _run_question(p, verbose),
        max_workers=max_workers,
    )
    for r in resultados["preguntas"]:
        add_usage(usage_total, r.get("usage"))

    resultados["conversaciones"] = _parallel_map(
        conversaciones,
        lambda c: _run_conversation(c, verbose),
        max_workers=min(3, max_workers),
    )
    for r in resultados["conversaciones"]:
        add_usage(usage_total, r.get("usage"))

    if not skip_informes:
        # Informes: más caros; paralelismo acotado
        resultados["informes"] = _parallel_map(
            informes,
            lambda i: _run_informe(i, verbose),
            max_workers=min(2, max_workers),
        )
        for r in resultados["informes"]:
            add_usage(usage_total, r.get("usage"))

    elapsed = round(time.perf_counter() - started, 2)
    costo = estimate_cost_usd(usage_total)

    def _ok_rate(rows: list[dict[str, Any]]) -> dict[str, int]:
        return {"ok": sum(1 for r in rows if r.get("ok")), "n": len(rows)}

    summary = {
        "smoke": smoke,
        "skip_informes": skip_informes,
        "tiempo_s": elapsed,
        "usage": usage_total,
        "costo": costo,
        "resumen": {
            "preguntas": _ok_rate(resultados["preguntas"]),
            "conversaciones": _ok_rate(resultados["conversaciones"]),
            "informes": _ok_rate(resultados["informes"]),
        },
        "resultados": resultados,
    }

    bundle = OUTPUTS_DIR / "run_all_summary.json"
    bundle.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    report = OUTPUTS_DIR / "run_all_REPORT.md"
    lines = [
        "# Corrida completa S6",
        "",
        f"- Smoke: `{smoke}`",
        f"- Tiempo total: **{elapsed} s**",
        f"- Costo estimado: **USD {costo.get('total_usd')}**",
        f"- Usage: `{json.dumps(usage_total)}`",
        "",
        "## Resumen",
        "",
        f"- Preguntas: {summary['resumen']['preguntas']}",
        f"- Conversaciones: {summary['resumen']['conversaciones']}",
        f"- Informes: {summary['resumen']['informes']}",
        "",
        "## Detalle IDs OK",
        "",
    ]
    for section in ("preguntas", "conversaciones", "informes"):
        lines.append(f"### {section}")
        for r in resultados[section]:
            flag = "OK" if r.get("ok") else "FAIL"
            lines.append(
                f"- {r.get('id')}: {flag} · {r.get('tiempo_s')}s · path `{r.get('path')}`"
            )
        lines.append("")
    report.write_text("\n".join(lines), encoding="utf-8")
    summary["report_md"] = str(report)
    summary["bundle"] = str(bundle)
    return summary
