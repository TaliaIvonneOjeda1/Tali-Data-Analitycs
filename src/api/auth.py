"""Auth Bearer + rate limit en memoria."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.config import ANALISTA_API_TOKEN, API_RATE_LIMIT_PER_MIN

_security = HTTPBearer(auto_error=False)
_hits: dict[str, deque[float]] = defaultdict(deque)


def require_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
) -> str:
    token = (credentials.credentials if credentials else "") or ""
    if not token:
        token = request.query_params.get("token") or ""
    if not ANALISTA_API_TOKEN or token != ANALISTA_API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido. Usá Authorization: Bearer <ANALISTA_API_TOKEN>",
        )
    return token


def rate_limit(request: Request, _: str = Depends(require_token)) -> None:
    key = request.client.host if request.client else "unknown"
    now = time.time()
    window = _hits[key]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= API_RATE_LIMIT_PER_MIN:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit: demasiados requests por minuto",
        )
    window.append(now)
