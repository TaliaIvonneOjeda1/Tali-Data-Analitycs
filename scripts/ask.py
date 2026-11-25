"""CLI S1: una pregunta → respuesta trazable JSON.

Uso (desde la raíz del entregable, con el venv del workspace o uno local):

    python scripts/ask.py "¿Cuánto vendió la cadena en el año fiscal 2025?"
    python scripts/ask.py --id P01
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import OUTPUTS_DIR, QUESTIONS_PATH
from src.agent.loop import run_agent


def _load_question(qid: str) -> str:
    items = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    for item in items:
        if item["id"] == qid:
            return item["texto"]
    raise SystemExit(f"No encontré pregunta {qid}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analista de datos — una pregunta")
    parser.add_argument("pregunta", nargs="?", help="Texto de la pregunta")
    parser.add_argument("--id", dest="qid", help="Id de preguntas.json (P01...)")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if args.qid:
        pregunta = _load_question(args.qid)
    elif args.pregunta:
        pregunta = args.pregunta
    else:
        parser.error("Pasá una pregunta o --id P01")

    result = run_agent(pregunta, verbose=not args.quiet)
    OUTPUTS_DIR.mkdir(exist_ok=True)
    out = OUTPUTS_DIR / "last_respuesta.json"
    from src.persist import save_respuesta_json

    try:
        save_respuesta_json(result, out)
    except ValueError as exc:
        # Igual guardamos crudo para debug, pero avisamos
        out.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"AVISO validacion pydantic: {exc}")
    print("\n=== RESPUESTA ===")
    printable = {k: v for k, v in result.items() if not k.startswith("_")}
    print(json.dumps(printable, ensure_ascii=False, indent=2, default=str))
    print(f"\nGuardado en {out}")
    meta = result.get("_meta") or {}
    print(
        "meta:",
        json.dumps(
            {
                "structured_output_ok": meta.get("structured_output_ok"),
                "cache_read_input_tokens": meta.get("cache_read_input_tokens"),
                "cache_creation_input_tokens": meta.get(
                    "cache_creation_input_tokens"
                ),
                "hooks_enabled": meta.get("hooks_enabled"),
                "usage": meta.get("usage"),
            },
            ensure_ascii=False,
        ),
    )


if __name__ == "__main__":
    main()
