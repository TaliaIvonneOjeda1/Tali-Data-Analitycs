from src.security.public import to_public_informe, to_public_respuesta


def test_public_respuesta_strips_internals():
    raw = {
        "pregunta": "P",
        "texto": "ok",
        "valor": 1,
        "unidad": "ARS",
        "supuestos": [],
        "consultas": [{"medida": "ventas_netas", "filtros": {"anio_fiscal": 2025}, "sql": "SELECT 1"}],
        "cuentas": [],
        "siguiente_pregunta_sugerida": "¿YoY?",
        "_pasos": [{"secret": True}],
        "_meta": {
            "usage": {"input_tokens": 10, "output_tokens": 2},
            "hook_events": [{"blocked": True}],
            "costo_usd": 0.01,
            "tiempo_s": 1.2,
        },
    }
    pub = to_public_respuesta(raw)
    assert "_pasos" not in pub
    assert "hook_events" not in (pub.get("meta") or {})
    assert pub["siguiente_pregunta_sugerida"] == "¿YoY?"
    assert pub["meta"]["usage"]["input_tokens"] == 10


def test_public_informe_pdf_name_only():
    pub = to_public_informe(
        {
            "pedido": "I1",
            "pdf": r"C:\Users\talia\Documents\Taligent\outputs\informe_I1.pdf",
            "consultas": [],
            "cuentas": [],
            "costo": {"total_usd": 0.2},
            "agentes": {"flujo": ["investigador", "analista"]},
            "_pasos": [1, 2],
        }
    )
    assert pub["pdf"] == "informe_I1.pdf"
    assert "_pasos" not in pub
