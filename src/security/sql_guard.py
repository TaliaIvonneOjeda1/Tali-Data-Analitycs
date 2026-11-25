"""Única fuente de verdad: qué SQL de lectura está permitido."""

from __future__ import annotations

import re

_SQL_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|attach|copy|create|grant|pragma|call|"
    r"truncate|replace|merge|vacuum|export|import|install|load|checkpoint)\b",
    re.IGNORECASE,
)

_ALLOWED_FIRST = frozenset({"SELECT", "WITH", "DESCRIBE", "SHOW", "EXPLAIN"})


def sql_is_readonly(sql: str) -> bool:
    """True si el statement es de solo lectura (SELECT/WITH/DESCRIBE/SHOW/EXPLAIN)."""
    cleaned = (sql or "").strip().rstrip(";")
    if not cleaned:
        return False
    if _SQL_FORBIDDEN.search(cleaned):
        return False
    first = cleaned.lstrip().split(None, 1)[0].upper()
    return first in _ALLOWED_FIRST
