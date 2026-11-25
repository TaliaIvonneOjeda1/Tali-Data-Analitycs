"""Ensayo Demo Day (S7): una pregunta + un informe + resumen de traza/costo.

Uso (desde la raiz del entregable):

    set PYTHONIOENCODING=utf-8
    python scripts/demo_day.py
    python scripts/demo_day.py --pregunta P05 --informe I2
    python scripts/demo_day.py --skip-informe   # solo pregunta (ahorra tokens)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agent.loop import run_agent
from src.config import DATA_DIR, OUTPUTS_DIR, QUESTIONS_PATH
from src.multiagent.orchestrator import run_informe, save_result
from src.persist import save_respuesta_json


def _load_pregunta(qid: str) -> str:
    items = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    for item in items:
        if item["id"] == qid:
            return item["texto"]
    raise SystemExit(f"No encontre pregunta {qid}")


def _load_pedido(iid: str) -> str:
    path = DATA_DIR / "preguntas" / "pedidos_de_informe.json"
    items = json.loads(path.read_text(encoding="utf-8"))
    for item in items:
        if item["id"] == iid:
            return item["texto"]
    raise SystemExit(f"No encontre pedido {iid}")


def _print_traza_corta(result: dict) -> None:
    consultas = result.get("consultas") or []
    cuentas = result.get("cuentas") or []
    print("  valor:", result.get("valor"), result.get("unidad") or "")
    print(f"  consultas: {len(consultas)} | cuentas: {len(cuentas)}")
    for i, c in enumerate(consultas[:3], 1):
        medida = c.get("medida")
        filtros = c.get("filtros") or {}
        sql = (c.get("sql") or "").replace("\n", " ")[:120]
        print(f"    [{i}] medida={medida} filtros={filtros}")
        if sql:
            print(f"        sql={sql}...")
    meta = result.get("_meta") or {}
    usage = meta.get("usage") or {}
    print(
        "  meta:",
        json.dumps(
            {
                "cache_read_input_tokens": meta.get("cache_read_input_tokens"),
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "hooks_enabled": meta.get("hooks_enabled"),
            },
            ensure_ascii=True,
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Ensayo Demo Day")
    parser.add_argument("--pregunta", default="P01", help="Id pregunta (default P01)")
    parser.add_argument("--informe", default="I1", help="Id informe (default I1)")
    parser.add_argument("--skip-informe", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    OUTPUTS_DIR.mkdir(exist_ok=True)
    t0 = time.perf_counter()
    summary: dict = {
        "pregunta_id": args.pregunta,
        "informe_id": None if args.skip_informe else args.informe,
    }

    print("=" * 60)
    print("DEMO DAY — Bloque 1: pregunta")
    print("=" * 60)
    texto_q = _load_pregunta(args.pregunta)
    print(f"[{args.pregunta}] {texto_q}\n")
    resp = run_agent(texto_q, verbose=not args.quiet)
    out_q = OUTPUTS_DIR / "demo_day_pregunta.json"
    try:
        save_respuesta_json(resp, out_q)
    except ValueError as exc:
        out_q.write_text(
            json.dumps(resp, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"AVISO validacion pydantic: {exc}")

    print("\n--- Traza (para senalar en vivo) ---")
    _print_traza_corta(resp)
    print(f"JSON: {out_q}")
    summary["ok_pregunta"] = bool(
        (resp.get("texto") or "").strip()
        or resp.get("valor") is not None
        or (resp.get("consultas") or [])
    )
    summary["ok_consultas_pregunta"] = len(resp.get("consultas") or []) > 0
    summary["pregunta_valor"] = resp.get("valor")
    summary["pregunta_unidad"] = resp.get("unidad")

    if not args.skip_informe:
        print("\n" + "=" * 60)
        print("DEMO DAY — Bloque 2: informe")
        print("=" * 60)
        pedido = _load_pedido(args.informe)
        print(f"[{args.informe}] {pedido}\n")
        inf = run_informe(pedido, informe_id=args.informe, verbose=not args.quiet)
        out_i = save_result(inf, OUTPUTS_DIR / "demo_day_informe.json")
        pdf = inf.get("pdf")
        print("\n--- Informe (para senalar en vivo) ---")
        print("  flujo:", (inf.get("agentes") or {}).get("flujo"))
        print(f"  consultas: {len(inf.get('consultas') or [])}")
        print(f"  PDF: {pdf}")
        print("  costo:", json.dumps(inf.get("costo"), ensure_ascii=True))
        print(f"JSON: {out_i}")
        summary["ok_informe_pdf"] = Path(pdf or "").is_file()
        summary["ok_informe_consultas"] = len(inf.get("consultas") or []) > 0
        summary["informe_costo_usd"] = (inf.get("costo") or {}).get("total_usd")
        summary["pdf"] = pdf
        summary["flujo"] = (inf.get("agentes") or {}).get("flujo")

    summary["tiempo_s"] = round(time.perf_counter() - t0, 1)
    summary["ok"] = bool(summary.get("ok_pregunta")) and (
        args.skip_informe or bool(summary.get("ok_informe_pdf"))
    )
    out_s = OUTPUTS_DIR / "demo_day_summary.json"
    out_s.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print("DEMO DAY — SUMMARY")
    print("=" * 60)
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    print(f"\nGuardado: {out_s}")
    print("Guion: docs/S7_DEMO_DAY.md")
    if not summary["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
