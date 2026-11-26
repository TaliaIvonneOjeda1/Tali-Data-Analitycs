from pathlib import Path

from src.usage_ledger import backfill_session, record_usage, reset_for_tests, summary


def setup_function(tmp_path_factory=None) -> None:
    # pytest inyecta tmp_path por fixture; fallback a outputs de test aislado
    pass


def test_record_and_summary_by_session(tmp_path: Path):
    reset_for_tests(tmp_path)
    record_usage(
        kind="chat",
        label="ventas AF2025",
        usage={
            "input_tokens": 1000,
            "output_tokens": 200,
            "cache_read_input_tokens": 5000,
        },
        session_id="abc123",
        tiempo_s=1.2,
    )
    record_usage(
        kind="chat_blocked",
        label="quien es messi",
        usage={},
        session_id="abc123",
        tiempo_s=0.0,
    )
    data = summary(session_id="abc123")
    assert data["app"]["consultas"] == 2
    assert data["sesion_actual"]["consultas"] == 2
    assert data["app"]["costo"]["total_usd"] > 0
    assert data["app"]["usage"]["cache_read_input_tokens"] == 5000
    assert data["app"]["ahorro_cache_usd"] > 0
    assert data["sesion_actual"]["total_usd"] == data["app"]["costo"]["total_usd"]


def test_backfill_recovers_session(tmp_path: Path):
    reset_for_tests(tmp_path)
    backfill_session(
        session_id="sess9",
        usage={"input_tokens": 800, "output_tokens": 120},
        turnos=1,
    )
    data = summary(session_id="sess9")
    assert data["app"]["consultas"] == 1
    assert data["sesion_actual"]["total_usd"] > 0
    # idempotente
    backfill_session(
        session_id="sess9",
        usage={"input_tokens": 800, "output_tokens": 120},
        turnos=1,
    )
    assert summary(session_id="sess9")["app"]["consultas"] == 1
