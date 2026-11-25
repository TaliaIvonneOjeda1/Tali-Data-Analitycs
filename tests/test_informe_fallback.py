"""Fallback estructurado de informes (sin Anthropic)."""

from __future__ import annotations

from src.multiagent.orchestrator import (
    _build_informe_fallback,
    _conclusiones_from_analista,
    _indicadores_from_evidence,
    _looks_like_informe_json,
    _merge_investigaciones,
    detect_focos_pedido,
)
from src.reporting.pdf_report import build_pdf


def test_looks_like_informe_json():
    assert _looks_like_informe_json({"indicadores": [{"nombre": "x", "valor": 1}]})
    assert _looks_like_informe_json(
        {"titulo": "T", "resumen_ejecutivo": "Resumen"}
    )
    assert not _looks_like_informe_json({})
    assert not _looks_like_informe_json({"texto": "Se detuvo por presupuesto"})


def test_indicadores_from_evidence_and_fallback(tmp_path):
    inv = {
        "texto": "Hallazgos",
        "consultas": [
            {
                "medida": "margen_pct",
                "filtros": {"anio_fiscal": 2026, "trimestre_fiscal": 2},
                "sql": "SELECT 1",
                "valor": 26.78,
                "unidad": "%",
            }
        ],
        "cuentas": ["delta_pp(26.78, 27.03) = -0.25"],
    }
    an = {
        "texto": "1) El margen cayó levemente.\n2) Hay que validar cortes por región.",
        "_parsed": {
            "texto": "1) El margen cayó levemente.\n2) Hay que validar cortes por región.",
            "conclusiones": ["Margen T2 en 26,78%", "Validar Oeste con LFL"],
        },
    }
    inds = _indicadores_from_evidence(inv, an)
    assert any(i["nombre"].startswith("margen_pct") for i in inds)
    assert _conclusiones_from_analista(an)

    payload = _build_informe_fallback(
        "Preparame un informe ejecutivo del T2 del AF2026 con foco en margen.",
        "I1",
        inv,
        an,
        motivo="redactor sin JSON",
    )
    assert payload["indicadores"]
    assert payload["conclusiones"]
    assert payload["supuestos"]
    assert payload.get("grafico") is None or payload["grafico"].get("valores")

    pdf = build_pdf(payload["pedido"], payload, tmp_path / "informe_test.pdf")
    assert pdf.is_file()
    assert pdf.stat().st_size > 500


def test_detect_focos_pedido_compuesto():
    pedido = (
        "Necesito un informe de cumplimiento de presupuesto de enero de 2026, "
        "por categoría y por región.Preparame un informe ejecutivo del T2 del AF2026 "
        "con foco en margen. Armame un informe del AF2026 para el gerente de la región Oeste. "
        "debe ser un informe que abarque todo lo solicitado."
    )
    focos = detect_focos_pedido(pedido)
    assert len(focos) == 3
    ids = {f["id"] for f in focos}
    assert ids == {"presupuesto_enero", "margen_t2", "oeste_af2026"}


def test_merge_investigaciones_fusiona_evidencia():
    focos = detect_focos_pedido(
        "Necesito un informe de cumplimiento de presupuesto de enero de 2026, "
        "por categoría y por región. Preparame un informe ejecutivo del T2 del AF2026 "
        "con foco en margen. Armame un informe del AF2026 para el gerente de la región Oeste."
    )
    parts = [
        {
            "texto": "Desvío enero -23%",
            "consultas": [{"medida": "desvio_presupuesto_pct", "filtros": {"mes": 1}, "sql": "SELECT 1", "valor": -23.7}],
            "cuentas": ["desvio_presupuesto_pct(1,2) = -23.7"],
            "_parsed": {"texto": "Desvío enero -23%", "hallazgos": [{"titulo": "Desvío", "valor": -23.7}]},
        },
        {
            "texto": "Margen T2 26.78%",
            "consultas": [{"medida": "margen_pct", "filtros": {"trimestre_fiscal": 2}, "sql": "SELECT 2", "valor": 26.78}],
            "cuentas": ["margen_pct = 26.78"],
            "_parsed": {"texto": "Margen T2 26.78%", "hallazgos": [{"titulo": "Margen", "valor": 26.78}]},
        },
        {
            "texto": "Oeste LFL -0.28 pp",
            "consultas": [{"medida": "margen_pct", "filtros": {"region": "Oeste"}, "sql": "SELECT 3", "valor": 26.64}],
            "cuentas": ["delta_pp = -0.28"],
            "_parsed": {"texto": "Oeste LFL -0.28 pp", "hallazgos": [{"titulo": "Oeste", "valor": 26.64}]},
        },
    ]
    merged = _merge_investigaciones("pedido compuesto", focos, parts)
    assert len(merged["consultas"]) == 3
    assert len(merged["hallazgos"]) == 3
    assert "Cumplimiento" in merged["texto"] or "Desvío" in merged["texto"]
    fb = _build_informe_fallback(
        "pedido compuesto",
        "adhoc",
        merged,
        {"texto": "1) Presupuesto. 2) Margen. 3) Oeste.", "_parsed": {"conclusiones": ["A", "B", "C"]}},
        motivo="test",
        focos=focos,
    )
    assert "fusionado" in fb["titulo"].lower() or "·" in fb["titulo"]
    assert len(fb["indicadores"]) >= 2
    assert len(fb["conclusiones"]) >= 2
