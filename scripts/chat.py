"""CLI S2: conversación multi-turno con herencia de contexto.

Uso:

    python scripts/chat.py --id C1
    python scripts/chat.py --id C5
    python scripts/chat.py  # modo interactivo
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agent.conversation import ConversationSession, run_conversation
from src.config import DATA_DIR, OUTPUTS_DIR


def _load_conversation(cid: str) -> list[str]:
    path = DATA_DIR / "preguntas" / "conversaciones.json"
    items = json.loads(path.read_text(encoding="utf-8"))
    for item in items:
        if item["id"] == cid:
            return list(item["turnos"])
    raise SystemExit(f"No encontré conversación {cid}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Conversación Analista de datos")
    parser.add_argument("--id", dest="cid", help="Id C1..C5 de conversaciones.json")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    OUTPUTS_DIR.mkdir(exist_ok=True)

    if args.cid:
        turnos = _load_conversation(args.cid)
        result = run_conversation(
            turnos, conversation_id=args.cid, verbose=not args.quiet
        )
        out = OUTPUTS_DIR / f"conversacion_{args.cid}.json"
        out.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"\nGuardado en {out}")
        for i, t in enumerate(result["turnos"], 1):
            r = t["respuesta"]
            print(f"\n--- Turno {i} ---")
            print("USER:", t["usuario"])
            print("TEXTO:", (r.get("texto") or "")[:500])
            print("VALOR:", r.get("valor"), r.get("unidad"))
            print("ESTADO:", t.get("estado_despues"))
        return

    # Interactivo
    session = ConversationSession(conversation_id="interactive")
    print("Modo interactivo. Escribí 'salir' para terminar.")
    while True:
        try:
            texto = input("\nvos> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not texto or texto.lower() in {"salir", "exit", "quit"}:
            break
        record = session.ask(texto, verbose=not args.quiet)
        r = record["respuesta"]
        print("\nanalista>", r.get("texto"))
        print("valor:", r.get("valor"), r.get("unidad"))
    out = OUTPUTS_DIR / "conversacion_interactive.json"
    out.write_text(
        json.dumps(session.to_dict(), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"Guardado en {out}")


if __name__ == "__main__":
    main()
