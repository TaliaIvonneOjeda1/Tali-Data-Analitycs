"""Ledger de consumo (tokens / USD), con persistencia en disco para sobrevivir reload."""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from src.config import OUTPUTS_DIR
from src.costing import add_usage, empty_usage, estimate_cost_usd

_lock = threading.Lock()
_events: list[dict[str, Any]] = []
_started_at = time.time()
_LEDGER_PATH = OUTPUTS_DIR / "usage_ledger.json"
_seen_ids: set[str] = set()


def _ensure_loaded() -> None:
    global _started_at
    if _events or not _LEDGER_PATH.is_file():
        return
    try:
        raw = json.loads(_LEDGER_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return
    events = raw.get("events") if isinstance(raw, dict) else None
    if not isinstance(events, list):
        return
    for ev in events:
        if not isinstance(ev, dict):
            continue
        eid = str(ev.get("id") or "")
        if eid and eid in _seen_ids:
            continue
        if eid:
            _seen_ids.add(eid)
        _events.append(ev)
    if isinstance(raw, dict) and raw.get("started_at"):
        try:
            _started_at = float(raw["started_at"])
        except (TypeError, ValueError):
            pass


def _persist_unlocked() -> None:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "started_at": _started_at,
        "updated_at": time.time(),
        "events": _events[-500:],
    }
    tmp = _LEDGER_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_LEDGER_PATH)


def record_usage(
    *,
    kind: str,
    label: str,
    usage: dict[str, Any] | None = None,
    session_id: str | None = None,
    tiempo_s: float | None = None,
    extra: dict[str, Any] | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    usage_clean = empty_usage()
    add_usage(usage_clean, usage)
    costo = estimate_cost_usd(usage_clean)
    event = {
        "id": event_id or uuid.uuid4().hex[:10],
        "ts": time.time(),
        "kind": kind,
        "label": (label or "")[:180],
        "session_id": session_id,
        "usage": usage_clean,
        "costo": {
            "input_usd": costo.get("input_usd"),
            "output_usd": costo.get("output_usd"),
            "cache_read_usd": costo.get("cache_read_usd"),
            "cache_write_usd": costo.get("cache_write_usd"),
            "total_usd": costo.get("total_usd"),
        },
        "tiempo_s": tiempo_s,
        "extra": extra or {},
    }
    with _lock:
        _ensure_loaded()
        if event["id"] in _seen_ids:
            return event
        _seen_ids.add(event["id"])
        _events.append(event)
        _persist_unlocked()
    return event


def backfill_session(
    *,
    session_id: str,
    usage: dict[str, Any] | None,
    label: str = "consumo recuperado de sesión",
    turnos: int | None = None,
) -> None:
    """Si la sesión tiene usage pero el ledger no, registra un evento agregado."""
    usage_clean = empty_usage()
    add_usage(usage_clean, usage)
    if sum(usage_clean.values()) <= 0:
        return
    with _lock:
        _ensure_loaded()
        already = any(
            (e.get("session_id") == session_id and sum((e.get("usage") or {}).values()) > 0)
            for e in _events
        )
        if already:
            return
    record_usage(
        kind="session_backfill",
        label=label,
        usage=usage_clean,
        session_id=session_id,
        extra={"turnos": turnos, "recuperado": True},
        event_id=f"bf-{session_id}",
    )


def _sum_usage(events: list[dict[str, Any]]) -> dict[str, int]:
    total = empty_usage()
    for ev in events:
        add_usage(total, ev.get("usage"))
    return total


def _sum_usd(events: list[dict[str, Any]]) -> float:
    return round(
        sum(float((ev.get("costo") or {}).get("total_usd") or 0.0) for ev in events),
        6,
    )


def _cache_savings_usd(usage: dict[str, int], rates: dict[str, float]) -> float:
    """Cuánto se ahorró por leer de cache vs pagar input pleno."""
    cache_r = int(usage.get("cache_read_input_tokens") or 0)
    if cache_r <= 0:
        return 0.0
    full = (cache_r / 1_000_000) * float(rates.get("input_usd_per_mtok") or 0)
    paid = (cache_r / 1_000_000) * float(rates.get("cache_read_usd_per_mtok") or 0)
    return round(max(full - paid, 0.0), 6)


def summary(*, session_id: str | None = None, limit: int = 40) -> dict[str, Any]:
    with _lock:
        _ensure_loaded()
        events = list(_events)

    by_session: dict[str, list[dict[str, Any]]] = {}
    for ev in events:
        sid = ev.get("session_id") or "sin_sesion"
        by_session.setdefault(sid, []).append(ev)

    sessions = []
    for sid, items in by_session.items():
        usage = _sum_usage(items)
        sessions.append(
            {
                "session_id": sid,
                "consultas": len(items),
                "usage": usage,
                "total_usd": _sum_usd(items),
                "ultimo_ts": items[-1]["ts"] if items else None,
            }
        )
    sessions.sort(key=lambda s: s.get("ultimo_ts") or 0, reverse=True)

    app_usage = _sum_usage(events)
    app_cost = estimate_cost_usd(app_usage)
    rates = app_cost.get("rates") or {}
    session_block = None
    if session_id:
        sess_events = [e for e in events if e.get("session_id") == session_id]
        sess_usage = _sum_usage(sess_events)
        session_block = {
            "session_id": session_id,
            "consultas": len(sess_events),
            "usage": sess_usage,
            "total_usd": _sum_usd(sess_events),
            "ahorro_cache_usd": _cache_savings_usd(sess_usage, rates),
            "eventos": list(reversed(sess_events[-limit:])),
        }

    return {
        "started_at": _started_at,
        "now": time.time(),
        "ledger_path": str(_LEDGER_PATH),
        "app": {
            "consultas": len(events),
            "usage": app_usage,
            "costo": {
                "input_usd": app_cost.get("input_usd"),
                "output_usd": app_cost.get("output_usd"),
                "cache_read_usd": app_cost.get("cache_read_usd"),
                "cache_write_usd": app_cost.get("cache_write_usd"),
                "total_usd": app_cost.get("total_usd"),
            },
            "ahorro_cache_usd": _cache_savings_usd(app_usage, rates),
            "rates": rates,
            "nota_cache": (
                "El prompt cache reutiliza el system prompt: los tokens de "
                "cache_read cuestan menos que input pleno y bajan el USD total."
            ),
        },
        "sesion_actual": session_block,
        "sesiones": sessions[:20],
        "eventos_recientes": list(reversed(events[-limit:])),
    }


def reset_for_tests(tmp_path: Path | None = None) -> None:
    global _LEDGER_PATH, _started_at
    with _lock:
        _events.clear()
        _seen_ids.clear()
        _started_at = time.time()
        if tmp_path is not None:
            _LEDGER_PATH = Path(tmp_path) / "usage_ledger.json"
        if _LEDGER_PATH.is_file():
            _LEDGER_PATH.unlink()
