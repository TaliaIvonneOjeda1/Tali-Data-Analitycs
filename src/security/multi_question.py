"""Detecta varios pedidos de consulta en un mismo mensaje."""

from __future__ import annotations

import re
from typing import Any


_P_LINE = re.compile(
    r"(?im)^\s*(?:P\d+\s*[—\-–:.]?\s*)?(.+?\?|top\s+\d+\s+.+|crecimiento\s+.+|"
    r"margen\s+.+|ticket\s+.+|ventas?\s+.+|desvío\s+.+|desvio\s+.+)\s*$"
)
_QUESTION_MARK = re.compile(r"[¿?]")
_CODED_LINE = re.compile(
    r"(?i)^\s*P(\d+)\s*[—\-–:.]\s*(.+?)\s*$"
)
_RANGE_ONLY = re.compile(r"(?i)^\s*P\d+\s*[–—\-]\s*P\d+\s*$")


def extract_candidate_questions(text: str, *, limit: int = 8) -> list[str]:
    """Extrae preguntas/pedidos distintos de un pegado tipo catálogo."""
    raw = (text or "").strip()
    if not raw:
        return []

    found: list[str] = []
    seen: set[str] = set()

    def _add(item: str) -> None:
        cleaned = re.sub(r"\s+", " ", item).strip(" -—–:\t")
        cleaned = re.sub(
            r"^(Comparativas|Rankings|Diagnósticos|Ambiguas|Sin información|"
            r"Puntuales)\b[:\s]*",
            "",
            cleaned,
            flags=re.I,
        )
        if len(cleaned) < 8:
            return
        key = cleaned.casefold()
        if key in seen:
            return
        # Filtra encabezados de tabla / ruido
        if re.fullmatch(
            r"(?i)(comparativas|rankings|diagn[oó]sticos|ambiguas|sin informaci[oó]n|"
            r"puntuales|p\d+\s*[–—\-]\s*p\d+)",
            cleaned,
        ):
            return
        seen.add(key)
        found.append(cleaned[:160])

    # Preferir línea por línea (mantiene orden del catálogo).
    for line in raw.splitlines():
        line = line.strip()
        if not line or _RANGE_ONLY.match(line):
            continue
        m = _CODED_LINE.match(line)
        if m:
            _add(m.group(2))
            continue
        m = _P_LINE.match(line)
        if m:
            _add(m.group(1))
        elif _QUESTION_MARK.search(line) and len(line) > 12:
            _add(line)

    # Fallback: oraciones con signo de pregunta
    if len(found) < 2:
        for chunk in re.split(r"(?<=[?¿])\s+", raw):
            if _QUESTION_MARK.search(chunk):
                _add(chunk)

    return found[:limit]


def is_multi_question_message(text: str) -> bool:
    return len(extract_candidate_questions(text)) >= 2


def multi_question_payload(text: str) -> dict[str, Any]:
    candidates = extract_candidate_questions(text)
    bullets = "\n".join(f"- {c}" for c in candidates[:6])
    more = "" if len(candidates) <= 6 else f"\n(+{len(candidates) - 6} más)"
    cuerpo = (
        "Detecté varias preguntas en el mismo mensaje. "
        "Para que cada respuesta quede trazable en la sesión, "
        "elegí una sola y volvé a consultar (podés pegar solo esa línea).\n\n"
        f"Encontré:\n{bullets}{more}"
    )
    return {
        "pregunta": text[:240],
        "texto": cuerpo,
        "valor": None,
        "unidad": None,
        "supuestos": [
            "El mensaje contenía múltiples pedidos; se pidió aclaración "
            "antes de consultar la base."
        ],
        "consultas": [],
        "cuentas": [],
        "siguiente_pregunta_sugerida": candidates[0] if candidates else None,
        "alerta_desvio": None,
        "_meta": {
            "tiempo_s": 0.0,
            "costo_usd": 0.0,
            "usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
            "multi_question": True,
            "candidatos": candidates,
        },
    }
