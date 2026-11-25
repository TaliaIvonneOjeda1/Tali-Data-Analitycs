"""Levanta la API FastAPI (uvicorn).

Uso:
    set ANALISTA_API_TOKEN=dev-token-cambiar
    python scripts/serve_api.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import uvicorn


def main() -> None:
    uvicorn.run(
        "src.api.app:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
