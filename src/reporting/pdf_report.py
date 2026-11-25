"""PDF de informe BI: portada con logo, narrativa, KPIs, evidencia, anexo."""

from __future__ import annotations

import html
import re
from datetime import date
from pathlib import Path
from typing import Any

from src.config import OUTPUTS_DIR
from src.reporting.charts import bar_chart, line_chart

_ASSETS = Path(__file__).resolve().parent / "assets"
_LOGO = _ASSETS / "taligent-logo.png"

# Paleta alineada a la UI TaliAnalytics
_NAVY = "#101a2f"
_ACCENT = "#2457d6"
_META = "#475569"
_CARD_BG = "#f4f6fb"
_CARD_BORDER = "#d7deea"


def _safe(text: Any, limit: int = 2000) -> str:
    s = "" if text is None else str(text)
    return s[:limit]


def _esc(text: Any, limit: int = 2000) -> str:
    return html.escape(_safe(text, limit))


def _fmt_valor(valor: Any, unidad: Any = None) -> str:
    """Valor legible; nunca deja strings enormes sin espacios (rompen el PDF)."""
    if valor is None:
        return "No disponible"
    if isinstance(valor, bool):
        return str(valor)
    if isinstance(valor, (int, float)):
        x = float(valor)
        u = str(unidad or "").lower()
        if "pp" in u:
            return f"{x:.2f}".replace(".", ",")
        if "%" in u or "pct" in u:
            return f"{x:.2f}".replace(".", ",")
        if abs(x) >= 1_000_000:
            return f"{x / 1_000_000:,.2f} M".replace(",", "X").replace(".", ",").replace(
                "X", "."
            )
        if abs(x) >= 1000:
            return f"{x:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
        if abs(x - round(x)) < 1e-9:
            return str(int(round(x)))
        return f"{x:.2f}".replace(".", ",")
    s = re.sub(r"\s+", " ", str(valor).strip())
    if len(s) > 42:
        s = s[:39] + "…"
    return s


def _short_nota(nota: Any, limit: int = 160) -> str:
    s = re.sub(r"\s+", " ", _safe(nota, limit)).strip()
    return s


def _dedupe_indicadores(indicadores: list[Any]) -> list[dict[str, Any]]:
    """Evita listas enormes/duplicadas que ensucian el PDF."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in indicadores:
        if not isinstance(raw, dict):
            continue
        nombre = str(raw.get("nombre") or "").strip()
        if not nombre:
            continue
        key = nombre.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(raw)
        if len(out) >= 12:
            break
    return out


def _list_items(payload: dict[str, Any], *keys: str) -> list[str]:
    items: list[str] = []
    for key in keys:
        raw = payload.get(key) or []
        if isinstance(raw, str) and raw.strip():
            items.append(raw.strip())
            continue
        if not isinstance(raw, list):
            continue
        for x in raw:
            s = str(x).strip()
            if s and s not in items:
                items.append(s)
    return items


def _labels_look_temporal(labels: list[Any]) -> bool:
    """True si las etiquetas parecen una serie temporal (meses, T1–T4, AF, años)."""
    if len(labels) < 2:
        return False
    joined = " ".join(str(x).lower() for x in labels)
    markers = (
        "t1",
        "t2",
        "t3",
        "t4",
        "af20",
        "ene",
        "feb",
        "mar",
        "abr",
        "may",
        "jun",
        "jul",
        "ago",
        "sep",
        "oct",
        "nov",
        "dic",
        "2024",
        "2025",
        "2026",
        "q1",
        "q2",
        "q3",
        "q4",
    )
    hits = sum(1 for m in markers if m in joined)
    # Varios períodos distintos o varias etiquetas con año/trimestre
    return hits >= 2 or (hits >= 1 and len(labels) >= 3)


def _resolve_chart(payload: dict[str, Any]) -> Path | None:
    grafico = payload.get("grafico")
    if isinstance(grafico, dict) and grafico.get("etiquetas") and grafico.get("valores"):
        nombre = grafico.get("nombre_archivo") or "informe_chart.png"
        dest = OUTPUTS_DIR / Path(str(nombre)).name
        tipo = str(grafico.get("tipo") or "").lower().strip()
        title = grafico.get("titulo") or ""
        ylabel = grafico.get("ylabel") or ""
        labels = list(grafico["etiquetas"])
        # Heurística: si el tipo no viene o dice barras pero las etiquetas
        # parecen tiempo (mes/trimestre/año), preferir líneas.
        if not tipo:
            tipo = "lineas" if _labels_look_temporal(labels) else "barras"
        elif tipo.startswith("bar") and _labels_look_temporal(labels):
            tipo = "lineas"
        if tipo.startswith("lin"):
            return line_chart(
                labels,
                grafico["valores"],
                dest,
                title=title,
                ylabel=ylabel,
            )
        return bar_chart(
            labels,
            grafico["valores"],
            dest,
            title=title,
            ylabel=ylabel,
        )
    if payload.get("chart_path"):
        p = Path(payload["chart_path"])
        if not p.is_file():
            p = OUTPUTS_DIR / Path(str(payload["chart_path"])).name
        if p.is_file():
            return p
    return None


def build_pdf(pedido: str, payload: dict[str, Any], dest: Path | None = None) -> Path:
    """Escribe el PDF BI con portada, narrativa y branding TaliAnalytics."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Image,
        KeepTogether,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    OUTPUTS_DIR.mkdir(exist_ok=True)
    dest = Path(dest) if dest else (OUTPUTS_DIR / "informe.pdf")

    chart_path = _resolve_chart(payload)

    navy = colors.HexColor(_NAVY)
    accent = colors.HexColor(_ACCENT)
    meta_c = colors.HexColor(_META)
    card_bg = colors.HexColor(_CARD_BG)
    card_bd = colors.HexColor(_CARD_BORDER)

    styles = getSampleStyleSheet()
    brand = ParagraphStyle(
        "BrandES",
        parent=styles["BodyText"],
        fontSize=11,
        leading=14,
        fontName="Helvetica-Bold",
        textColor=navy,
    )
    title_style = ParagraphStyle(
        "TitleES",
        parent=styles["Heading1"],
        fontSize=18,
        spaceAfter=8,
        leading=22,
        textColor=navy,
        fontName="Helvetica-Bold",
    )
    meta_style = ParagraphStyle(
        "MetaES",
        parent=styles["BodyText"],
        fontSize=9,
        leading=12,
        textColor=meta_c,
    )
    h2 = ParagraphStyle(
        "H2ES",
        parent=styles["Heading2"],
        fontSize=12,
        spaceBefore=14,
        spaceAfter=6,
        textColor=accent,
        fontName="Helvetica-Bold",
    )
    body = ParagraphStyle(
        "BodyES", parent=styles["BodyText"], fontSize=10, leading=14, textColor=navy
    )
    small = ParagraphStyle(
        "SmallES", parent=styles["BodyText"], fontSize=8, leading=11, textColor=meta_c
    )
    ind_name = ParagraphStyle(
        "IndName",
        parent=styles["BodyText"],
        fontSize=9,
        leading=11,
        fontName="Helvetica-Bold",
        textColor=navy,
    )
    ind_val = ParagraphStyle(
        "IndVal",
        parent=styles["BodyText"],
        fontSize=12,
        leading=14,
        fontName="Helvetica-Bold",
        textColor=accent,
    )
    ind_meta = ParagraphStyle(
        "IndMeta",
        parent=styles["BodyText"],
        fontSize=8,
        leading=10,
        textColor=meta_c,
    )

    page_w, _ = A4
    left_m = 1.7 * cm
    right_m = 1.7 * cm
    usable = page_w - left_m - right_m

    def _header_footer(canvas: Any, doc_obj: Any) -> None:
        canvas.saveState()
        canvas.setStrokeColor(card_bd)
        canvas.setLineWidth(0.4)
        canvas.line(left_m, A4[1] - 1.15 * cm, page_w - right_m, A4[1] - 1.15 * cm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(meta_c)
        canvas.drawString(left_m, A4[1] - 1.0 * cm, "TaliAnalytics")
        canvas.drawRightString(
            page_w - right_m,
            1.0 * cm,
            f"Confidencial — uso interno  ·  {doc_obj.page}",
        )
        canvas.line(left_m, 1.25 * cm, page_w - right_m, 1.25 * cm)
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(dest),
        pagesize=A4,
        leftMargin=left_m,
        rightMargin=right_m,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        title=_safe(payload.get("titulo") or "Informe TaliAnalytics", 120),
        author="TaliAnalytics",
    )
    story: list[Any] = []

    # —— Portada / encabezado ——
    titulo = payload.get("titulo") or "Informe ejecutivo — Almacenes del Sur"
    periodo = _safe(payload.get("periodo") or "", 80)
    audiencia = _safe(payload.get("audiencia") or "", 80)
    fecha = date.today().strftime("%d/%m/%Y")

    header_cells: list[Any] = []
    if _LOGO.is_file():
        header_cells.append(Image(str(_LOGO), width=2.6 * cm, height=2.6 * cm))
    else:
        header_cells.append(Paragraph("TaliAnalytics", brand))
    header_cells.append(
        [
            Paragraph("TaliAnalytics", brand),
            Paragraph("Informe de Business Intelligence", meta_style),
            Paragraph(f"Fecha: {fecha}", meta_style),
        ]
    )
    header = Table([header_cells], colWidths=[3.0 * cm, usable - 3.0 * cm])
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(header)
    story.append(Spacer(1, 0.35 * cm))
    story.append(Paragraph(_esc(titulo), title_style))
    story.append(Paragraph(f"<b>Pedido:</b> {_esc(pedido)}", body))
    meta_bits = []
    if periodo:
        meta_bits.append(f"<b>Período:</b> {_esc(periodo)}")
    if audiencia:
        meta_bits.append(f"<b>Audiencia:</b> {_esc(audiencia)}")
    if meta_bits:
        story.append(Paragraph("  ·  ".join(meta_bits), meta_style))
    story.append(Spacer(1, 0.2 * cm))

    # —— 1. Pregunta y contexto ——
    story.append(Paragraph("1. Pregunta y contexto", h2))
    pregunta = payload.get("pregunta_negocio") or pedido
    story.append(Paragraph(_esc(pregunta), body))
    if audiencia and not payload.get("pregunta_negocio"):
        story.append(
            Paragraph(
                "Informe orientado a decisión de negocio con evidencia trazable.",
                meta_style,
            )
        )

    # —— 2. Resumen ejecutivo ——
    story.append(Paragraph("2. Resumen ejecutivo", h2))
    story.append(
        Paragraph(
            _esc(payload.get("resumen_ejecutivo") or payload.get("texto") or "—"),
            body,
        )
    )

    # —— 3. KPIs ——
    story.append(Paragraph("3. Indicadores clave (KPIs)", h2))
    indicadores = _dedupe_indicadores(list(payload.get("indicadores") or []))
    if indicadores:
        for ind in indicadores:
            nombre = _esc(ind.get("nombre"), 90)
            unidad = ind.get("unidad") or ""
            valor = _esc(_fmt_valor(ind.get("valor"), unidad))
            contexto = _esc(
                _short_nota(ind.get("contexto") or ind.get("comparacion") or ""),
                180,
            )
            nota = _esc(_short_nota(ind.get("nota")), 180)
            unidad_txt = _esc(unidad, 24) if unidad else ""
            left_bits = [Paragraph(nombre, ind_name)]
            if contexto:
                left_bits.append(Paragraph(contexto, ind_meta))
            if nota:
                left_bits.append(Paragraph(nota, ind_meta))
            right = [
                Paragraph(valor, ind_val),
                Paragraph(unidad_txt or " ", ind_meta),
            ]
            row = Table(
                [[left_bits, right]],
                colWidths=[usable * 0.72, usable * 0.28],
            )
            row.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("BACKGROUND", (0, 0), (-1, -1), card_bg),
                        ("BOX", (0, 0), (-1, -1), 0.3, card_bd),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                        ("TOPPADDING", (0, 0), (-1, -1), 7),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ]
                )
            )
            story.append(KeepTogether([row, Spacer(1, 0.22 * cm)]))
    else:
        story.append(Paragraph("Sin indicadores estructurados.", body))

    # —— 4. Evidencia visual ——
    story.append(Paragraph("4. Evidencia visual", h2))
    if chart_path and chart_path.is_file():
        grafico = payload.get("grafico") if isinstance(payload.get("grafico"), dict) else {}
        chart_title = _safe((grafico or {}).get("titulo") or "", 140)
        if chart_title:
            story.append(Paragraph(_esc(chart_title), meta_style))
        story.append(Image(str(chart_path), width=usable, height=usable * 0.48))
    else:
        story.append(
            Paragraph(
                "Sin gráfico en este informe: los hallazgos se sostienen en KPIs y anexo.",
                body,
            )
        )

    # —— 5. Hallazgos ——
    story.append(Paragraph("5. Hallazgos e interpretación", h2))
    hallazgos = _list_items(payload, "hallazgos")
    if not hallazgos:
        # Fallback: primeras conclusiones como hallazgos si no vinieron tipados
        hallazgos = _list_items(payload, "conclusiones")[:3]
    if hallazgos:
        for h in hallazgos:
            story.append(Paragraph(f"• {_esc(h)}", body))
    else:
        story.append(Paragraph("—", body))

    # —— 6. Conclusiones y próximos pasos ——
    story.append(Paragraph("6. Conclusiones y próximos pasos", h2))
    conclusiones = _list_items(payload, "conclusiones")
    if conclusiones:
        story.append(Paragraph("<b>Conclusiones</b>", body))
        for c in conclusiones:
            story.append(Paragraph(f"• {_esc(c)}", body))
    else:
        story.append(Paragraph("Sin conclusiones estructuradas.", body))

    proximos = _list_items(payload, "proximos_pasos")
    if proximos:
        story.append(Spacer(1, 0.15 * cm))
        story.append(Paragraph("<b>Próximos pasos</b>", body))
        for p in proximos:
            story.append(Paragraph(f"• {_esc(p)}", body))

    # —— 7. Limitaciones ——
    story.append(Paragraph("7. Limitaciones y supuestos", h2))
    limitaciones = _list_items(payload, "limitaciones", "supuestos")
    if limitaciones:
        for s in limitaciones:
            story.append(Paragraph(f"• {_esc(s)}", body))
    else:
        story.append(
            Paragraph(
                "Sin limitaciones adicionales declaradas. Toda cifra del cuerpo "
                "debe contrastarse con el anexo de consultas.",
                body,
            )
        )

    # —— 8. Glosario ——
    story.append(Paragraph("8. Glosario", h2))
    glosario = payload.get("glosario") or []
    gloss_items: list[tuple[str, str]] = []
    if isinstance(glosario, list):
        for g in glosario:
            if isinstance(g, dict):
                term = str(g.get("termino") or g.get("término") or "").strip()
                defin = str(g.get("definicion") or g.get("definición") or "").strip()
                if term and defin:
                    gloss_items.append((term, defin))
            elif isinstance(g, str) and ":" in g:
                term, defin = g.split(":", 1)
                gloss_items.append((term.strip(), defin.strip()))
    if not gloss_items:
        # Fallback mínimo para términos habituales del dominio
        gloss_items = [
            ("AF", "Año fiscal (empieza el 1 de mayo; AF2026 = mayo 2025–abril 2026)."),
            ("T2", "Segundo trimestre fiscal (agosto–octubre)."),
            (
                "Variación interanual",
                "Comparación contra el mismo período del año anterior.",
            ),
            (
                "Comparables",
                "Misma base de sucursales abiertas en ambos períodos (sin aperturas nuevas).",
            ),
            ("pp", "Puntos porcentuales (diferencia entre porcentajes, no variación relativa)."),
        ]
    for term, defin in gloss_items[:10]:
        story.append(Paragraph(f"<b>{_esc(term, 40)}</b> — {_esc(defin, 220)}", body))

    # —— 9. Anexo ——
    story.append(Paragraph("9. Anexo — consultas y cuentas", h2))
    consultas = payload.get("consultas") or []
    sql_consultas: list[Any] = []
    notas_consultas: list[Any] = []
    for c in consultas:
        if not isinstance(c, dict):
            notas_consultas.append(c)
            continue
        sql = str(c.get("sql") or "").strip()
        if sql.upper().startswith(("SELECT", "WITH", "DESCRIBE", "SHOW")):
            sql_consultas.append(c)
        else:
            notas_consultas.append(c)

    if sql_consultas:
        story.append(
            Paragraph(
                "SQL ejecutable: cada bloque es una consulta completa e independiente. "
                "En DBeaver abrí un editor SQL nuevo y pegá solo ese bloque.",
                small,
            )
        )
        for i, c in enumerate(sql_consultas, 1):
            story.append(
                Paragraph(
                    f"<b>Consulta {i}</b> — medida={_esc(c.get('medida'))} "
                    f"filtros={_esc(c.get('filtros'), 180)}",
                    small,
                )
            )
            story.append(
                Paragraph(f"<b>SQL (copiar completo):</b> {_esc(c.get('sql'), 1500)}", small)
            )
            if c.get("valor") is not None:
                story.append(Paragraph(f"Valor: {_esc(c.get('valor'))}", small))
            story.append(Spacer(1, 0.12 * cm))
    else:
        story.append(Paragraph("Sin consultas SQL ejecutables registradas.", small))

    if notas_consultas:
        story.append(Paragraph("<b>Notas / tools de código</b> (no son SQL ejecutable)", small))
        for i, c in enumerate(notas_consultas, 1):
            if not isinstance(c, dict):
                story.append(Paragraph(f"• {_esc(c, 400)}", small))
                continue
            medida = c.get("medida") or "sin medida"
            detalle = c.get("sql") or c.get("explicacion_consulta") or ""
            story.append(
                Paragraph(
                    f"• {i}. {_esc(medida, 80)}"
                    + (f" — {_esc(detalle, 280)}" if detalle else ""),
                    small,
                )
            )

    cuentas = payload.get("cuentas") or []
    if cuentas:
        story.append(Paragraph("<b>Cuentas de código</b>", small))
        for c in cuentas:
            story.append(Paragraph(f"• {_esc(c)}", small))

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return dest
