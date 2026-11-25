"""Evidencia de sesión → informe (sin Anthropic)."""

from __future__ import annotations

from src.agent.conversation import ConversationSession
from src.multiagent.orchestrator import run_informe


def _seed_session() -> ConversationSession:
    session = ConversationSession(conversation_id="demo-sesion")
    session.turnos = [
        {
            "usuario": "¿Cuánto vendió la cadena en AF2025?",
            "respuesta": {
                "texto": "Ventas netas AF2025 = 9747 M ARS",
                "valor": 9_747_823_869,
                "unidad": "ARS",
                "supuestos": ["Año fiscal mayo-abril"],
                "consultas": [
                    {
                        "medida": "ventas_netas",
                        "filtros": {"anio_fiscal": 2025},
                        "sql": "SELECT SUM(importe_neto) FROM ventas",
                        "valor": 9_747_823_869,
                    }
                ],
                "cuentas": [],
            },
            "meta": {},
            "estado_despues": {
                "medida": "ventas_netas",
                "filtros": {"anio_fiscal": 2025},
            },
        },
        {
            "usuario": "¿Y el margen del T2 AF2026?",
            "respuesta": {
                "texto": "Margen bruto T2 AF2026 = 26.78%",
                "valor": 26.78,
                "unidad": "%",
                "supuestos": [],
                "consultas": [
                    {
                        "medida": "margen_pct",
                        "filtros": {"anio_fiscal": 2026, "trimestre_fiscal": 2},
                        "sql": "SELECT ...",
                        "valor": 26.78,
                    }
                ],
                "cuentas": ["delta_pp(26.78, 27.03) = -0.25"],
            },
            "meta": {},
            "estado_despues": {
                "medida": "margen_pct",
                "filtros": {"anio_fiscal": 2026, "trimestre_fiscal": 2},
            },
        },
    ]
    session.estado = {
        "medida": "margen_pct",
        "filtros": {"anio_fiscal": 2026, "trimestre_fiscal": 2},
        "ultimo_valor": 26.78,
        "unidad": "%",
        "supuestos": ["Año fiscal mayo-abril"],
    }
    return session


def test_evidencia_para_informe_empaqueta_turnos():
    session = _seed_session()
    pack = session.evidencia_para_informe()
    assert pack["origen"] == "sesion_exploracion"
    assert pack["n_turnos"] == 2
    assert len(pack["consultas"]) == 2
    assert any("margen" in (c.get("medida") or "") for c in pack["consultas"])
    assert "delta_pp" in pack["cuentas"][0]
    assert "AF2025" in pack["texto"]


def test_evidencia_filtra_por_indices():
    session = _seed_session()
    pack = session.evidencia_para_informe([1])
    assert pack["n_turnos"] == 1
    assert pack["hallazgos"][0]["pregunta"].startswith("¿Y el margen")
    assert len(pack["consultas"]) == 1


def test_resumen_publico():
    session = _seed_session()
    summary = session.resumen_publico()
    assert summary["turnos_con_evidencia"] == 2
    assert summary["turnos"][0]["index"] == 0
    assert summary["turnos"][0]["tiene_evidencia"] is True


def test_run_informe_desde_sesion_salta_investigador(monkeypatch, tmp_path):
    """Con evidencia de sesión no llama al investigador con tools."""
    session = _seed_session()
    evidencia = session.evidencia_para_informe()
    calls: list[str] = []

    def fake_worker(role, instruction, **kwargs):
        calls.append(role)
        if role == "analista":
            return {
                "texto": "Síntesis de la sesión",
                "consultas": [],
                "cuentas": [],
                "_parsed": {
                    "texto": "Síntesis de la sesión",
                    "conclusiones": ["Ventas AF2025 sólidas", "Margen T2 levemente abajo"],
                },
                "_meta": {"usage": {}},
            }
        if role == "redactor":
            return {
                "texto": '{"titulo":"Informe de sesión","resumen_ejecutivo":"Resumen","indicadores":[{"nombre":"margen_pct","valor":26.78,"unidad":"%"}],"conclusiones":["Seguir el margen"],"consultas":[],"cuentas":[]}',
                "consultas": [],
                "cuentas": [],
                "_parsed": {
                    "titulo": "Informe de sesión",
                    "resumen_ejecutivo": "Resumen",
                    "indicadores": [{"nombre": "margen_pct", "valor": 26.78, "unidad": "%"}],
                    "conclusiones": ["Seguir el margen"],
                },
                "_meta": {"usage": {}},
            }
        raise AssertionError(f"Worker inesperado: {role}")

    monkeypatch.setattr(
        "src.multiagent.orchestrator.run_worker", fake_worker
    )
    monkeypatch.setattr(
        "src.multiagent.orchestrator.build_pdf",
        lambda *a, **k: tmp_path / "out.pdf",
    )
    monkeypatch.setattr(
        "src.multiagent.orchestrator.execute_tool",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no tools")),
    )

    result = run_informe(
        "Informe con hallazgos de la sesión",
        informe_id="sesion_demo",
        verbose=False,
        output_dir=tmp_path,
        evidencia_sesion=evidencia,
    )
    assert "investigador" not in calls
    assert calls == ["analista", "redactor"]
    assert result.get("titulo")
    pasos = result.get("_pasos") or []
    assert pasos[0].get("origen") == "sesion_exploracion"
