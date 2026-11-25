"""Apertura del holdout (S5): una sola corrida, documentar qué falla y por qué."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from src.agent.loop import run_agent
from src.config import OUTPUTS_DIR, QUESTIONS_PATH
from src.evals.harness import HOLDOUT_IDS, score_respuesta
from src.persist import save_respuesta_json

GOLD_HOLDOUT_PATH = Path(__file__).with_name("gold_holdout.json")


def _load_questions() -> dict[str, str]:
    items = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    return {i["id"]: i["texto"] for i in items}


def _load_gold() -> dict[str, Any]:
    return json.loads(GOLD_HOLDOUT_PATH.read_text(encoding="utf-8"))


def _score_holdout_case(qid: str, actual: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    tipo = expected.get("tipo")
    texto = (actual.get("texto") or "").lower()

    if tipo == "comparativa":
        scored = score_respuesta(actual, expected)
        return {
            "tipo": tipo,
            "acierto": bool(scored.get("acierto_respuesta")),
            "acierto_consulta": scored.get("acierto_consulta"),
            "detalle": scored.get("detalle"),
            "por_que": None
            if scored.get("acierto_respuesta")
            else "Valor fuera de tolerancia o no reportado vs gold de desvío T4 AF2026",
        }

    if tipo == "ranking":
        scored = score_respuesta(actual, expected)
        return {
            "tipo": tipo,
            "acierto": bool(scored.get("acierto_respuesta")),
            "acierto_consulta": scored.get("acierto_consulta"),
            "detalle": scored.get("detalle"),
            "por_que": None
            if scored.get("acierto_respuesta")
            else "Conjunto de proveedores distinto al gold (margen_bruto AF2026)",
        }

    if tipo == "ambigua":
        ok = (
            actual.get("valor") is None
            or bool(actual.get("supuestos"))
            or "fiscal" in texto
            or "calendario" in texto
            or "?" in (actual.get("texto") or "")
        )
        # fallar si dio número cerrado sin supuestos
        if actual.get("valor") is not None and not actual.get("supuestos"):
            ok = False
        return {
            "tipo": tipo,
            "acierto": ok,
            "por_que": None
            if ok
            else "Respondió un número sin preguntar ni declarar supuesto fiscal/calendario",
        }

    if tipo == "sin_dato":
        ok = actual.get("valor") is None and (
            "no" in texto
            or "cliente" in texto
            or "dato" in texto
            or "base" in texto
        )
        return {
            "tipo": tipo,
            "acierto": ok,
            "por_que": None
            if ok
            else "No declaró ausencia de clientes / inventó un valor",
        }

    if tipo == "diagnostico":
        consultas = actual.get("consultas") or []
        ok = bool((actual.get("texto") or "").strip()) and len(consultas) >= 1
        # no debería inventar clientes
        bad = "cliente nuevo" in texto and actual.get("valor") is not None
        if bad:
            ok = False
        return {
            "tipo": tipo,
            "acierto": ok,
            "consultas_n": len(consultas),
            "por_que": None
            if ok
            else "Faltó texto o consultas trazables en el diagnóstico",
        }

    return {"tipo": tipo, "acierto": False, "por_que": "tipo no soportado"}


def _run_one(qid: str, pregunta: str, verbose: bool) -> dict[str, Any]:
    actual = run_agent(pregunta, verbose=verbose, enable_prompt_cache=True)
    meta = actual.get("_meta") or {}
    path = OUTPUTS_DIR / f"holdout_{qid}.json"
    try:
        save_respuesta_json(actual, path)
        persisted = True
        persist_error = None
    except ValueError as exc:
        persisted = False
        persist_error = str(exc)
        path.write_text(
            json.dumps(actual, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    return {
        "id": qid,
        "pregunta": pregunta,
        "respuesta": {k: v for k, v in actual.items() if not k.startswith("_")},
        "meta": meta,
        "persisted_ok": persisted,
        "persist_error": persist_error,
        "path": str(path),
    }


def run_holdout(
    *,
    parallel: bool = True,
    max_workers: int = 5,
    verbose: bool = False,
) -> dict[str, Any]:
    """Corre las 5 apartadas UNA vez. No usar para tunear."""
    questions = _load_questions()
    gold = _load_gold()
    ids = [i for i in ("P09", "P11", "P14", "P18", "P20") if i in HOLDOUT_IDS]
    OUTPUTS_DIR.mkdir(exist_ok=True)

    raw_results: dict[str, Any] = {}
    if parallel:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futs = {
                pool.submit(_run_one, qid, questions[qid], verbose): qid for qid in ids
            }
            for fut in as_completed(futs):
                qid = futs[fut]
                raw_results[qid] = fut.result()
    else:
        for qid in ids:
            raw_results[qid] = _run_one(qid, questions[qid], verbose)

    scored: dict[str, Any] = {}
    for qid in ids:
        item = raw_results[qid]
        score = _score_holdout_case(qid, item["respuesta"], gold[qid])
        scored[qid] = {
            **item,
            "gold": gold[qid],
            "score": score,
        }

    n_ok = sum(1 for v in scored.values() if v["score"].get("acierto"))
    cache_reads = sum(
        int((v.get("meta") or {}).get("cache_read_input_tokens") or 0)
        for v in scored.values()
    )
    cache_writes = sum(
        int((v.get("meta") or {}).get("cache_creation_input_tokens") or 0)
        for v in scored.values()
    )
    summary = {
        "n": len(ids),
        "aciertos": n_ok,
        "ids": ids,
        "parallel": parallel,
        "cache_read_input_tokens_total": cache_reads,
        "cache_creation_input_tokens_total": cache_writes,
        "casos": scored,
    }
    out = OUTPUTS_DIR / "holdout_s5.json"
    out.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return summary


def write_holdout_report(summary: dict[str, Any], path: Path) -> Path:
    lines = [
        "# Holdout S5 — resultado (una sola corrida)",
        "",
        "Sistema congelado al abrir las apartadas. Lo que importa: **qué falló y por qué**.",
        "",
        f"- Aciertos: **{summary['aciertos']}/{summary['n']}**",
        f"- Paralelo: `{summary.get('parallel')}`",
        f"- `cache_read_input_tokens` total: `{summary.get('cache_read_input_tokens_total')}`",
        f"- `cache_creation_input_tokens` total: `{summary.get('cache_creation_input_tokens_total')}`",
        "",
        "| ID | Tipo | Acierto | Por qué / detalle |",
        "|----|------|---------|-------------------|",
    ]
    for qid in summary["ids"]:
        caso = summary["casos"][qid]
        score = caso["score"]
        por_que = score.get("por_que") or "OK"
        detalle = score.get("detalle") or {}
        extra = ""
        if detalle:
            extra = f" `{json.dumps(detalle, ensure_ascii=False)[:120]}`"
        lines.append(
            f"| {qid} | {score.get('tipo')} | {'sí' if score.get('acierto') else 'no'} | {por_que}{extra} |"
        )
    lines.extend(
        [
            "",
            "## Notas",
            "",
            "- No retuning con este resultado (Caso1 §5).",
            "- Artefactos por caso: `outputs/holdout_Pxx.json`.",
            "- Bundle: `outputs/holdout_s5.json`.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
