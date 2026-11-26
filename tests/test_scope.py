from src.security.scope import REFUSAL_TEXT, is_out_of_scope, refusal_payload


def test_messi_out_of_scope():
    assert is_out_of_scope("quien es messi ?")
    assert is_out_of_scope("¿Quién es Messi?")


def test_business_in_scope():
    assert not is_out_of_scope("¿Cuánto vendió la cadena en el año fiscal 2025?")
    assert not is_out_of_scope("¿Y en la región Sur?")
    assert not is_out_of_scope("margen de Almacén T2 AF2026")


def test_refusal_payload():
    payload = refusal_payload("quien es messi")
    assert payload["texto"] == REFUSAL_TEXT
    assert payload["valor"] is None
    assert payload["_meta"]["scope_blocked"] is True
