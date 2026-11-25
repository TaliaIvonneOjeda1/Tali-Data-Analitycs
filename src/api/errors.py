"""Traduce errores de Anthropic / runtime a mensajes claros para la UI."""

from __future__ import annotations

from fastapi import HTTPException

try:
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None  # type: ignore


def http_from_exception(exc: Exception) -> HTTPException:
    """Mapea excepciones conocidas a HTTPException con detalle usable."""
    if anthropic is not None:
        if isinstance(exc, anthropic.AuthenticationError):
            return HTTPException(
                status_code=503,
                detail=(
                    "La clave ANTHROPIC_API_KEY no es válida o expiró. "
                    "Actualizala en el archivo .env del workspace "
                    "(carpeta Taligent) y reiniciá la API."
                ),
            )
        if isinstance(exc, anthropic.RateLimitError):
            return HTTPException(
                status_code=429,
                detail="Límite de la API de Anthropic alcanzado. Probá en unos minutos.",
            )
        if isinstance(exc, anthropic.APIStatusError):
            return HTTPException(
                status_code=502,
                detail=f"Error de Anthropic ({exc.status_code}): {exc.message}",
            )
        if isinstance(exc, anthropic.APIConnectionError):
            return HTTPException(
                status_code=503,
                detail="No se pudo conectar con Anthropic. Revisá la red e intentá de nuevo.",
            )
    return HTTPException(status_code=500, detail=str(exc) or "Error interno")
