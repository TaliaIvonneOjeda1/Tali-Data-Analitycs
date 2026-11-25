"""Schemas públicos de la API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    pregunta: str = Field(min_length=1)
    verbose: bool = False


class ChatTurnRequest(BaseModel):
    mensaje: str = Field(min_length=1)
    session_id: str | None = None
    verbose: bool = False


class InformeRequest(BaseModel):
    pedido: str | None = None
    informe_id: str | None = Field(default=None, description="I1, I2 o I3")
    session_id: str | None = Field(
        default=None,
        description="Si se pasa, el informe se arma con la evidencia de esa sesión",
    )
    turn_indices: list[int] | None = Field(
        default=None,
        description="Turnos de la sesión a incluir (default: todos)",
    )
    verbose: bool = False


class JobCreateResponse(BaseModel):
    job_id: str
    status: str = "queued"
    kind: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    kind: str
    progress: list[dict[str, Any]] = Field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
