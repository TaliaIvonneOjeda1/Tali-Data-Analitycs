"""Schemas Pydantic S5 — validar antes de persistir (Caso1 S5 / M6)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class ConsultaModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    medida: str | None = None
    filtros: dict[str, Any] = Field(default_factory=dict)
    sql: str | None = None
    valor: float | int | None = None
    filas: list[Any] = Field(default_factory=list)

    @field_validator("filtros", mode="before")
    @classmethod
    def _filtros_dict(cls, v: Any) -> dict[str, Any]:
        if v is None:
            return {}
        if isinstance(v, dict):
            return v
        return {"raw": v}


class RespuestaModel(BaseModel):
    """Registro trazable de una respuesta (Caso1 §4)."""

    model_config = ConfigDict(extra="allow")

    pregunta: str
    texto: str = ""
    valor: float | int | str | None = None
    unidad: str | None = None
    supuestos: list[str] = Field(default_factory=list)
    consultas: list[ConsultaModel] = Field(default_factory=list)
    cuentas: list[str] = Field(default_factory=list)

    @field_validator("supuestos", "cuentas", mode="before")
    @classmethod
    def _list_str(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, list):
            return [str(x) for x in v]
        return [str(v)]

    @field_validator("consultas", mode="before")
    @classmethod
    def _consultas_list(cls, v: Any) -> list[Any]:
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        out = []
        for item in v:
            if isinstance(item, str):
                out.append({"medida": None, "filtros": {}, "sql": item})
            else:
                out.append(item)
        return out


class InformeModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    pedido: str
    pdf: str | None = None
    consultas: list[ConsultaModel] = Field(default_factory=list)
    cuentas: list[str] = Field(default_factory=list)
    titulo: str | None = None
    resumen_ejecutivo: str | None = None
    indicadores: list[dict[str, Any]] = Field(default_factory=list)
    conclusiones: list[str] = Field(default_factory=list)


def validate_respuesta(data: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    """Valida y devuelve dict limpio + lista de errores (vacía si OK)."""
    try:
        # sacar meta interna antes de validar
        clean = {k: v for k, v in data.items() if not str(k).startswith("_")}
        model = RespuestaModel.model_validate(clean)
        dumped = model.model_dump()
        # reinyectar meta si venía
        for k, v in data.items():
            if str(k).startswith("_"):
                dumped[k] = v
        return dumped, []
    except ValidationError as exc:
        return None, [e["msg"] for e in exc.errors()]


def validate_informe(data: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        clean = {k: v for k, v in data.items() if not str(k).startswith("_")}
        model = InformeModel.model_validate(clean)
        dumped = model.model_dump()
        for k, v in data.items():
            if str(k).startswith("_"):
                dumped[k] = v
        return dumped, []
    except ValidationError as exc:
        return None, [e["msg"] for e in exc.errors()]
