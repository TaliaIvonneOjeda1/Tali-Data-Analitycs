"""Backend FastAPI — nunca expone ANTHROPIC_API_KEY al cliente."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from src.agent.conversation import ConversationSession
from src.agent.loop import run_agent
from src.api.auth import rate_limit, require_token
from src.api.jobs import (
    append_progress,
    artifact_path,
    create_job,
    get_job,
    set_error,
    set_result,
    submit,
)
from src.api.schemas import (
    AskRequest,
    ChatTurnRequest,
    InformeRequest,
    JobCreateResponse,
    JobStatusResponse,
)
from src.budget import Budget
from src.config import (
    API_CORS_ORIGINS,
    DATA_DIR,
    DB_PATH,
    DB_PATH_RO,
    JOBS_DIR,
    OUTPUTS_DIR,
)
from src.logging_util import setup_logging
from src.multiagent.orchestrator import run_informe, save_result
from src.security.public import to_public_informe, to_public_respuesta
from src.security.multi_question import (
    is_multi_question_message,
    multi_question_payload,
)
from src.security.scope import is_out_of_scope, refusal_payload
from src.usage_ledger import (
    backfill_session,
    record_usage,
    summary as usage_summary,
)

setup_logging()

app = FastAPI(
    title="TaliAnalytics · Analista de datos",
    version="1.0.0",
    description="API del analista trazable (Haiku 5.5 + capa semántica). Frontend oficial en React.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=API_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Cabeceras al estilo dual-source-agent (OWASP LLM / demo local)."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


# Sesiones de chat en memoria (demo interno)
_sessions: dict[str, ConversationSession] = {}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, Any]:
    """Chequeo de demo (como /ready del dual-source-agent)."""
    db_ok = DB_PATH.is_file() or DB_PATH_RO.is_file()
    return {
        "agent": True,
        "db": db_ok,
        "anthropic_key": bool(os.getenv("ANTHROPIC_API_KEY")),
    }


@app.post("/ask", dependencies=[Depends(rate_limit)])
def ask(body: AskRequest) -> dict[str, Any]:
    if is_out_of_scope(body.pregunta):
        blocked = refusal_payload(body.pregunta)
        record_usage(
            kind="ask_blocked",
            label=body.pregunta,
            usage=(blocked.get("_meta") or {}).get("usage"),
            tiempo_s=0.0,
        )
        return to_public_respuesta(blocked)

    if is_multi_question_message(body.pregunta):
        clarified = multi_question_payload(body.pregunta)
        record_usage(
            kind="ask_clarify",
            label=body.pregunta,
            usage=(clarified.get("_meta") or {}).get("usage"),
            tiempo_s=0.0,
        )
        return to_public_respuesta(clarified)

    budget = Budget()
    result = run_agent(
        body.pregunta,
        verbose=body.verbose,
        enable_budget=True,
        budget=budget,
        enrich=True,
    )
    meta = result.get("_meta") or {}
    record_usage(
        kind="ask",
        label=body.pregunta,
        usage=meta.get("usage"),
        tiempo_s=meta.get("tiempo_s"),
    )
    return to_public_respuesta(result)


@app.post("/chat", dependencies=[Depends(rate_limit)])
def chat(body: ChatTurnRequest) -> dict[str, Any]:
    import uuid

    sid = body.session_id or uuid.uuid4().hex[:10]
    session = _sessions.get(sid)
    if session is None:
        session = ConversationSession(conversation_id=sid)
        _sessions[sid] = session
    turn = session.ask(body.mensaje, verbose=body.verbose)
    # ConversationSession.ask() devuelve un record {usuario, respuesta, meta, ...}
    # y no el payload plano que espera to_public_respuesta.
    from src.enrich import enrich_respuesta

    payload = dict(turn.get("respuesta") or {})
    if turn.get("meta"):
        payload["_meta"] = turn["meta"]
    payload = enrich_respuesta(payload)
    pub = to_public_respuesta(payload)
    pub["session_id"] = sid
    pub["turno_index"] = len(session.turnos) - 1
    pub["turnos_en_sesion"] = len(session.turnos)
    return pub


@app.get("/sessions/{session_id}", dependencies=[Depends(require_token)])
def get_session(session_id: str) -> dict[str, Any]:
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(404, f"Sesión no encontrada: {session_id}")
    summary = session.resumen_publico()
    summary["session_id"] = session_id
    return summary


@app.get("/usage", dependencies=[Depends(require_token)])
def get_usage(session_id: str | None = None) -> dict[str, Any]:
    """Consumo acumulado de tokens/USD (app + sesión opcional)."""
    # Recupera consumos de sesiones vivas si el ledger se perdió por reload.
    for sid, session in list(_sessions.items()):
        backfill_session(
            session_id=sid,
            usage=session.usage_total,
            label=f"Sesión {sid} ({len(session.turnos)} turnos)",
            turnos=len(session.turnos),
        )
    return usage_summary(session_id=session_id)


@app.post("/informe", response_model=JobCreateResponse, dependencies=[Depends(rate_limit)])
def informe_async(body: InformeRequest) -> JobCreateResponse:
    pedido = body.pedido
    iid = body.informe_id or "adhoc"
    evidencia_sesion: dict[str, Any] | None = None

    if body.session_id:
        session = _sessions.get(body.session_id)
        if session is None:
            raise HTTPException(404, f"Sesión no encontrada: {body.session_id}")
        try:
            evidencia_sesion = session.evidencia_para_informe(body.turn_indices)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if not pedido:
            n = evidencia_sesion.get("n_turnos") or len(session.turnos)
            pedido = (
                f"Preparame un informe ejecutivo con los {n} hallazgos "
                "reunidos en esta sesión de análisis."
            )
        if iid == "adhoc":
            iid = f"sesion_{body.session_id}"

    if body.informe_id and not pedido:
        path = DATA_DIR / "preguntas" / "pedidos_de_informe.json"
        items = json.loads(path.read_text(encoding="utf-8"))
        pedido = next(i["texto"] for i in items if i["id"] == body.informe_id)
    if not pedido:
        raise HTTPException(
            400,
            "Pasá pedido, informe_id (I1/I2/I3) o session_id con turnos",
        )

    job_id = create_job("informe")
    job_dir = JOBS_DIR / job_id

    def _run() -> None:
        def on_progress(ev: dict[str, Any]) -> None:
            append_progress(job_id, ev)

        try:
            result = run_informe(
                pedido,
                informe_id=iid,
                verbose=body.verbose,
                enable_budget=True,
                budget=Budget(),
                request_id=job_id,
                on_progress=on_progress,
                output_dir=job_dir,
                evidencia_sesion=evidencia_sesion,
            )
            # Copiar PDF al job dir si quedó en outputs/
            pdf = result.get("pdf")
            if pdf:
                src = Path(pdf)
                if src.is_file():
                    dest = job_dir / src.name
                    if src.resolve() != dest.resolve():
                        dest.write_bytes(src.read_bytes())
                    result["pdf"] = dest.name
                    result["job_id"] = job_id
            save_result(result, job_dir / "informe.json")
            costo = result.get("costo") or {}
            record_usage(
                kind="informe",
                label=pedido or iid,
                usage=costo.get("usage"),
                session_id=body.session_id,
                tiempo_s=result.get("tiempo_s") or costo.get("tiempo_s"),
                extra={"informe_id": iid, "job_id": job_id},
            )
            set_result(job_id, to_public_informe(result))
        except Exception as exc:  # noqa: BLE001
            set_error(job_id, str(exc))

    submit(job_id, _run)
    return JobCreateResponse(job_id=job_id, status="queued", kind="informe")


@app.get("/jobs/{job_id}", response_model=JobStatusResponse, dependencies=[Depends(require_token)])
def job_status(job_id: str) -> JobStatusResponse:
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job no encontrado")
    return JobStatusResponse(**job)


@app.get("/jobs/{job_id}/events", dependencies=[Depends(require_token)])
async def job_events(job_id: str) -> StreamingResponse:
    if not get_job(job_id):
        raise HTTPException(404, "Job no encontrado")

    async def event_stream():
        last_n = 0
        for _ in range(600):  # ~5 min a 0.5s
            job = get_job(job_id)
            if not job:
                break
            progress = job.get("progress") or []
            while last_n < len(progress):
                payload = json.dumps(progress[last_n], ensure_ascii=False)
                yield f"data: {payload}\n\n"
                last_n += 1
            if job.get("status") in {"done", "error"}:
                final = {
                    "phase": "final",
                    "status": job["status"],
                    "result": job.get("result"),
                    "error": job.get("error"),
                }
                yield f"data: {json.dumps(final, ensure_ascii=False)}\n\n"
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/artifacts/{job_id}/{name}", dependencies=[Depends(require_token)])
def get_artifact(job_id: str, name: str) -> FileResponse:
    path = artifact_path(job_id, name)
    if path is None:
        # fallback outputs raíz
        candidate = OUTPUTS_DIR / Path(name).name
        if candidate.is_file():
            path = candidate
    if path is None or not path.is_file():
        raise HTTPException(404, "Artefacto no encontrado")
    media = "application/pdf" if path.suffix.lower() == ".pdf" else "application/octet-stream"
    if path.suffix.lower() == ".png":
        media = "image/png"
    return FileResponse(path, media_type=media, filename=path.name)


@app.get("/demo/presets", dependencies=[Depends(require_token)])
def demo_presets() -> dict[str, Any]:
    """Atajos Demo Day."""
    questions = json.loads(
        (DATA_DIR / "preguntas" / "preguntas.json").read_text(encoding="utf-8")
    )
    informes = json.loads(
        (DATA_DIR / "preguntas" / "pedidos_de_informe.json").read_text(encoding="utf-8")
    )
    by_q = {q["id"]: q["texto"] for q in questions}
    by_i = {i["id"]: i["texto"] for i in informes}
    return {
        "pregunta_demo": {"id": "P01", "texto": by_q.get("P01")},
        "informe_demo": {"id": "I1", "texto": by_i.get("I1")},
        "preguntas": [{"id": k, "texto": by_q[k]} for k in ("P01", "P05", "P17", "P19") if k in by_q],
        "informes": [{"id": k, "texto": by_i[k]} for k in ("I1", "I2", "I3") if k in by_i],
    }
