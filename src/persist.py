"""Persistencia con validación Pydantic (S5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.agent.models import validate_informe, validate_respuesta


def save_respuesta_json(data: dict[str, Any], path: Path) -> dict[str, Any]:
    validated, errors = validate_respuesta(data)
    if validated is None:
        raise ValueError(f"Respuesta inválida, no se persiste: {errors}")
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = json.loads(json.dumps(validated, ensure_ascii=False, default=str))
    path.write_text(
        json.dumps(serializable, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return validated


def save_informe_json(data: dict[str, Any], path: Path) -> dict[str, Any]:
    validated, errors = validate_informe(data)
    if validated is None:
        raise ValueError(f"Informe inválido, no se persiste: {errors}")
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = json.loads(json.dumps(validated, ensure_ascii=False, default=str))
    path.write_text(
        json.dumps(serializable, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return validated
