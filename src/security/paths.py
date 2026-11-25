"""Sanitización de paths bajo outputs/ (anti path traversal)."""

from __future__ import annotations

import re
from pathlib import Path

from src.config import OUTPUTS_DIR

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(nombre: str, *, default: str = "chart_barras.png") -> str:
    """Solo el basename, caracteres seguros. Rechaza '..' y separadores."""
    raw = (nombre or "").strip() or default
    base = Path(raw.replace("\\", "/")).name
    if not base or base in {".", ".."}:
        base = default
    cleaned = _SAFE_NAME.sub("_", base).strip("._")
    if not cleaned:
        cleaned = default
    if "." not in cleaned:
        cleaned = f"{cleaned}.png"
    return cleaned


def safe_output_path(
    nombre_archivo: str,
    *,
    base_dir: Path | None = None,
    default: str = "chart_barras.png",
) -> Path:
    """Resuelve un path garantizado dentro de base_dir (default OUTPUTS_DIR)."""
    root = (base_dir or OUTPUTS_DIR).resolve()
    root.mkdir(parents=True, exist_ok=True)
    name = sanitize_filename(nombre_archivo, default=default)
    dest = (root / name).resolve()
    if not str(dest).startswith(str(root)):
        dest = (root / default).resolve()
    return dest
