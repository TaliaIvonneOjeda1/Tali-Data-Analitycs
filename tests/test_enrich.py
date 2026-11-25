from src.enrich import enrich_respuesta, explicar_consulta


def test_explicacion_y_sugerencia():
    data = {
        "pregunta": "¿Cuánto vendió?",
        "texto": "Vendió 100.",
        "valor": 100,
        "unidad": "ARS",
        "consultas": [
            {
                "medida": "ventas_netas",
                "filtros": {"anio_fiscal": 2025},
                "sql": "SELECT 1",
                "valor": 100,
                "unidad": "ARS",
            }
        ],
        "cuentas": [],
    }
    out = enrich_respuesta(data)
    assert out["consultas"][0]["explicacion_consulta"]
    assert "ventas" in out["consultas"][0]["explicacion_consulta"].lower()
    assert out["siguiente_pregunta_sugerida"]


def test_alerta_desvio():
    out = enrich_respuesta(
        {
            "pregunta": "desvio",
            "texto": "Desvío de presupuesto.",
            "valor": -8.5,
            "unidad": "%",
            "consultas": [
                {"medida": "desvio_presupuesto_pct", "filtros": {}, "sql": None}
            ],
            "cuentas": ["desvio_presupuesto_pct(...) = -8.5"],
        }
    )
    assert out["alerta_desvio"] and out["alerta_desvio"]["activa"]


def test_explicar_consulta_unit():
    s = explicar_consulta({"medida": "margen_pct", "filtros": {"trimestre_fiscal": 2}})
    assert "margen_pct" in s
