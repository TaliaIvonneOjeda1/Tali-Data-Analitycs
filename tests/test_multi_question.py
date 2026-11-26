from src.security.multi_question import (
    extract_candidate_questions,
    is_multi_question_message,
    multi_question_payload,
)


CATALOG = """
P01 — ¿Cuánto vendió la cadena en el AF2025?
Comparativas
P06–P09
P06 — crecimiento Bebidas T3 AF2026 vs año anterior
Rankings
P10–P12
P10 — top 5 sucursales AF2026
Diagnósticos
P13–P16
P13 — ¿Por qué bajó el margen de Almacén en T2 AF2026?
Ambiguas
P17–P18
P17 — ¿Cuánto vendimos en el último trimestre?
Sin información
P19–P20
P19 — ¿Cuál es el ticket promedio?
"""


def test_catalog_is_multi_question():
    assert is_multi_question_message(CATALOG)
    found = extract_candidate_questions(CATALOG)
    assert len(found) >= 4
    assert any("AF2025" in f or "vendió" in f for f in found)


def test_single_question_ok():
    assert not is_multi_question_message(
        "¿Cuánto vendió la cadena en el año fiscal 2025?"
    )


def test_payload_asks_to_choose():
    payload = multi_question_payload(CATALOG)
    assert payload["valor"] is None
    assert "varias preguntas" in payload["texto"].lower()
    assert payload["_meta"]["multi_question"] is True
