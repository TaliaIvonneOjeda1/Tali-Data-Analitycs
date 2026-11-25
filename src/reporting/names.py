"""Nombres de archivo de informes PDF (convención TaliAnalytics)."""

from __future__ import annotations

from datetime import date

# Sufijos de archivo (tal cual los pide producto).
SUFIJO_CONSULTAS = "Consultas"
SUFIJO_EJECUTIVO = "ejecutivo"

_PREDEFINIDOS = frozenset({"I1", "I2", "I3"})


def informe_stem(
    informe_id: str | None = None,
    *,
    from_session: bool = False,
    when: date | None = None,
) -> str:
    """Stem del PDF: InformeYYYYMMDD-Consultas | InformeYYYYMMDD-ejecutivo.

    - Consultas: informe desde sesión de preguntas libres, o pedido adhoc sin I1–I3.
    - ejecutivo: pedidos predefinidos I1 / I2 / I3.
    """
    day = (when or date.today()).strftime("%Y%m%d")
    iid = (informe_id or "adhoc").strip()
    if from_session or iid.startswith("sesion_") or iid not in _PREDEFINIDOS:
        sufijo = SUFIJO_CONSULTAS
    else:
        sufijo = SUFIJO_EJECUTIVO
    return f"Informe{day}-{sufijo}"


def informe_pdf_filename(
    informe_id: str | None = None,
    *,
    from_session: bool = False,
    when: date | None = None,
) -> str:
    return f"{informe_stem(informe_id, from_session=from_session, when=when)}.pdf"
