"""Logging estructurado liviano (request_id, rol, tokens, usd)."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

_configured = False


def setup_logging(level: str = "INFO") -> None:
    global _configured
    if _configured:
        return
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
    _configured = True


def get_logger(name: str = "analista") -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    request_id: str | None = None,
    **fields: Any,
) -> None:
    payload = {"event": event, "request_id": request_id, **fields}
    logger.info(json.dumps(payload, ensure_ascii=False, default=str))
