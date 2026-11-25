"""Rutas y configuración del entregable.

Todo path relativo a la raíz de `Taligent-Analista de datos`.
No depende del workspace Spring Camp / moduloN.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "base" / "almacenes_del_sur.duckdb"
# Copia de trabajo si DBeaver u otro cliente bloquea el .duckdb original (Windows).
DB_PATH_RO = DATA_DIR / "base" / "almacenes_del_sur.ro.duckdb"
MEASURES_PATH = DATA_DIR / "capa_semantica" / "medidas.yaml"
GLOSSARY_PATH = DATA_DIR / "capa_semantica" / "glosario.md"
QUESTIONS_PATH = DATA_DIR / "preguntas" / "preguntas.json"
OUTPUTS_DIR = ROOT / "outputs"

# Cargar .env local del entregable; si no hay key, intentar el .env del workspace padre.
load_dotenv(ROOT / ".env")
if not os.getenv("ANTHROPIC_API_KEY"):
    load_dotenv(ROOT.parent / ".env")

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5")
MAX_ITERATIONS_DEFAULT = int(os.getenv("AGENT_MAX_ITERATIONS", "16"))

# Modo producto: budgets hard (API / front). CLI de evals puede override.
PRODUCT_MAX_WALL_S = float(os.getenv("PRODUCT_MAX_WALL_S", "180"))
PRODUCT_MAX_USD = float(os.getenv("PRODUCT_MAX_USD", "0.75"))
PRODUCT_MAX_ITER = int(os.getenv("PRODUCT_MAX_ITER", "12"))
# Informes multiagente (investigador + analista + redactor) necesitan más iteraciones.
PRODUCT_INFORME_MAX_ITER = int(os.getenv("PRODUCT_INFORME_MAX_ITER", "20"))
# Pedidos compuestos (varios focos fusionados) suman iteraciones extra por foco.
PRODUCT_INFORME_EXTRA_ITER_PER_FOCO = int(
    os.getenv("PRODUCT_INFORME_EXTRA_ITER_PER_FOCO", "8")
)
PRODUCT_INFORME_REDACTOR_RESERVE = int(
    os.getenv("PRODUCT_INFORME_REDACTOR_RESERVE", "4")
)
DUCKDB_QUERY_TIMEOUT_S = float(os.getenv("DUCKDB_QUERY_TIMEOUT_S", "30"))
DUCKDB_MAX_ROWS = int(os.getenv("DUCKDB_MAX_ROWS", "200"))

# API
ANALISTA_API_TOKEN = os.getenv("ANALISTA_API_TOKEN", "dev-token-cambiar")
API_CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "API_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if o.strip()
]
API_RATE_LIMIT_PER_MIN = int(os.getenv("API_RATE_LIMIT_PER_MIN", "30"))
JOBS_DIR = OUTPUTS_DIR / "jobs"
