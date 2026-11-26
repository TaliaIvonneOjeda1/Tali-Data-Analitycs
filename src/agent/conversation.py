"""Conversaciones multi-turno con herencia de período / filtros / medida. (Caso1 S2)

Cada turno hereda el contexto del anterior salvo lo que el propio turno cambia.
El historial LLM se conserva; además mantenemos un estado estructurado.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import anthropic

from src.agent.loop import run_agent
from src.agent.prompts import system_prompt_for
from src.config import MODEL
from src.costing import estimate_cost_usd
from src.security.multi_question import (
    is_multi_question_message,
    multi_question_payload,
)
from src.security.scope import is_out_of_scope, refusal_payload
from src.usage_ledger import record_usage


def _infer_state_from_respuesta(respuesta: dict[str, Any]) -> dict[str, Any]:
    """Extrae medida/filtros de la última consulta útil."""
    estado: dict[str, Any] = {
        "medida": None,
        "filtros": {},
        "ultimo_valor": respuesta.get("valor"),
        "unidad": respuesta.get("unidad"),
        "supuestos": list(respuesta.get("supuestos") or []),
    }
    for c in respuesta.get("consultas") or []:
        if c.get("medida"):
            estado["medida"] = c.get("medida")
        filtros = c.get("filtros") or {}
        if filtros:
            estado["filtros"] = {**estado["filtros"], **filtros}
    return estado


@dataclass
class ConversationSession:
    conversation_id: str = "adhoc"
    estado: dict[str, Any] = field(
        default_factory=lambda: {
            "medida": None,
            "filtros": {},
            "ultimo_valor": None,
            "unidad": None,
            "supuestos": [],
        }
    )
    turnos: list[dict[str, Any]] = field(default_factory=list)
    usage_total: dict[str, int] = field(
        default_factory=lambda: {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        }
    )

    def _wrap_turn(self, texto_usuario: str) -> str:
        ctx = {
            "medida_heredada": self.estado.get("medida"),
            "filtros_heredados": self.estado.get("filtros") or {},
            "supuestos_previos": self.estado.get("supuestos") or [],
        }
        return (
            "<contexto_conversacion>\n"
            "Heredá período, filtros y medida del estado siguiente, "
            "salvo lo que este turno cambie explícitamente.\n"
            f"{json.dumps(ctx, ensure_ascii=False, indent=2)}\n"
            "</contexto_conversacion>\n\n"
            f"Turno del usuario: {texto_usuario}"
        )

    def ask(
        self,
        texto_usuario: str,
        *,
        verbose: bool = True,
        client: anthropic.Anthropic | None = None,
    ) -> dict[str, Any]:
        if is_out_of_scope(texto_usuario):
            respuesta = refusal_payload(texto_usuario)
            meta = dict(respuesta.get("_meta") or {})
            record_usage(
                kind="chat_blocked",
                label=texto_usuario,
                usage=meta.get("usage"),
                session_id=self.conversation_id,
                tiempo_s=0.0,
            )
            record = {
                "usuario": texto_usuario,
                "respuesta": {
                    k: v for k, v in respuesta.items() if not k.startswith("_")
                },
                "meta": meta,
                "estado_despues": dict(self.estado),
            }
            self.turnos.append(record)
            return record

        if is_multi_question_message(texto_usuario):
            respuesta = multi_question_payload(texto_usuario)
            meta = dict(respuesta.get("_meta") or {})
            record_usage(
                kind="chat_clarify",
                label=texto_usuario,
                usage=meta.get("usage"),
                session_id=self.conversation_id,
                tiempo_s=0.0,
            )
            # Etiqueta corta en sesión: no guardar el catálogo entero como "pregunta".
            label = "Varias preguntas (pedir una)"
            record = {
                "usuario": label,
                "respuesta": {
                    k: v for k, v in respuesta.items() if not k.startswith("_")
                },
                "meta": meta,
                "estado_despues": dict(self.estado),
            }
            self.turnos.append(record)
            return record

        pregunta = self._wrap_turn(texto_usuario)
        # run_agent es single-shot; para herencia fuerte además del prompt,
        # concatenamos resumen de turnos previos en el mensaje.
        if self.turnos:
            historial = []
            for i, t in enumerate(self.turnos, 1):
                historial.append(
                    {
                        "turno": i,
                        "usuario": t["usuario"],
                        "texto": (t["respuesta"].get("texto") or "")[:500],
                        "valor": t["respuesta"].get("valor"),
                        "estado": t.get("estado_despues"),
                    }
                )
            pregunta = (
                "<historial_resumido>\n"
                f"{json.dumps(historial, ensure_ascii=False, indent=2, default=str)}\n"
                "</historial_resumido>\n\n"
                + pregunta
            )

        respuesta = run_agent(
            pregunta,
            agent_role="analista_conversacional",
            verbose=verbose,
            client=client,
        )
        meta = respuesta.get("_meta") or {}
        usage = meta.get("usage") or {}
        for k in self.usage_total:
            self.usage_total[k] += int(usage.get(k) or 0)
        record_usage(
            kind="chat",
            label=texto_usuario,
            usage=usage,
            session_id=self.conversation_id,
            tiempo_s=meta.get("tiempo_s"),
        )

        nuevo_estado = _infer_state_from_respuesta(respuesta)
        # merge: lo nuevo pisa; lo no tocado se conserva
        merged_filtros = {
            **(self.estado.get("filtros") or {}),
            **(nuevo_estado.get("filtros") or {}),
        }
        self.estado = {
            "medida": nuevo_estado.get("medida") or self.estado.get("medida"),
            "filtros": merged_filtros,
            "ultimo_valor": (
                nuevo_estado.get("ultimo_valor")
                if nuevo_estado.get("ultimo_valor") is not None
                else self.estado.get("ultimo_valor")
            ),
            "unidad": nuevo_estado.get("unidad") or self.estado.get("unidad"),
            "supuestos": nuevo_estado.get("supuestos")
            or self.estado.get("supuestos")
            or [],
        }
        record = {
            "usuario": texto_usuario,
            "respuesta": {k: v for k, v in respuesta.items() if not k.startswith("_")},
            "meta": meta,
            "estado_despues": dict(self.estado),
        }
        self.turnos.append(record)
        return record

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.conversation_id,
            "estado": self.estado,
            "usage_total": self.usage_total,
            "model": MODEL,
            "system_role": "analista_conversacional",
            "turnos": self.turnos,
        }

    def resumen_publico(self) -> dict[str, Any]:
        """Vista liviana para la UI (sin metas internas pesadas)."""
        turnos_pub: list[dict[str, Any]] = []
        for i, t in enumerate(self.turnos):
            resp = t.get("respuesta") or {}
            turnos_pub.append(
                {
                    "index": i,
                    "usuario": t.get("usuario"),
                    "texto": resp.get("texto"),
                    "valor": resp.get("valor"),
                    "unidad": resp.get("unidad"),
                    "supuestos": list(resp.get("supuestos") or []),
                    "consultas": list(resp.get("consultas") or []),
                    "cuentas": list(resp.get("cuentas") or []),
                    "tiene_evidencia": bool(
                        resp.get("consultas")
                        or resp.get("cuentas")
                        or resp.get("valor") is not None
                    ),
                }
            )
        costo = estimate_cost_usd(self.usage_total)
        return {
            "session_id": self.conversation_id,
            "estado": dict(self.estado),
            "turnos": turnos_pub,
            "turnos_con_evidencia": sum(1 for t in turnos_pub if t["tiene_evidencia"]),
            "usage_total": dict(self.usage_total),
            "costo_usd": costo.get("total_usd"),
            "costo": {
                "input_usd": costo.get("input_usd"),
                "output_usd": costo.get("output_usd"),
                "cache_read_usd": costo.get("cache_read_usd"),
                "cache_write_usd": costo.get("cache_write_usd"),
                "total_usd": costo.get("total_usd"),
            },
        }

    def evidencia_para_informe(
        self,
        turn_indices: list[int] | None = None,
    ) -> dict[str, Any]:
        """Empaqueta hallazgos de la sesión como evidencia para el multiagente.

        Si se pasan índices, solo incluye esos turnos; si no, todos los que
        tengan valor, consultas o cuentas.
        """
        if not self.turnos:
            raise ValueError("La sesión no tiene turnos para armar un informe.")

        if turn_indices is None:
            selected = list(enumerate(self.turnos))
        else:
            selected = []
            for idx in turn_indices:
                if idx < 0 or idx >= len(self.turnos):
                    raise ValueError(f"Índice de turno inválido: {idx}")
                selected.append((idx, self.turnos[idx]))

        hallazgos: list[dict[str, Any]] = []
        consultas: list[dict[str, Any]] = []
        cuentas: list[str] = []
        supuestos: list[str] = []
        seen_sql: set[str] = set()

        for idx, turno in selected:
            resp = turno.get("respuesta") or {}
            hallazgos.append(
                {
                    "turno": idx + 1,
                    "pregunta": turno.get("usuario"),
                    "texto": resp.get("texto"),
                    "valor": resp.get("valor"),
                    "unidad": resp.get("unidad"),
                    "supuestos": list(resp.get("supuestos") or []),
                }
            )
            for c in resp.get("consultas") or []:
                if not isinstance(c, dict):
                    continue
                key = json.dumps(c, ensure_ascii=False, sort_keys=True, default=str)
                if key in seen_sql:
                    continue
                seen_sql.add(key)
                consultas.append(c)
            for cuenta in resp.get("cuentas") or []:
                if cuenta and cuenta not in cuentas:
                    cuentas.append(cuenta)
            for s in resp.get("supuestos") or []:
                if s and s not in supuestos:
                    supuestos.append(s)

        if not hallazgos:
            raise ValueError("No hay hallazgos seleccionados para el informe.")

        lineas = [
            "Hallazgos reunidos durante la sesión de exploración del usuario:",
        ]
        for h in hallazgos:
            valor = h.get("valor")
            unidad = h.get("unidad") or ""
            valor_txt = (
                f" → {valor} {unidad}".rstrip()
                if valor is not None
                else ""
            )
            lineas.append(f"- P{h['turno']}: {h.get('pregunta')}{valor_txt}")
            if h.get("texto"):
                lineas.append(f"  Lectura: {str(h['texto'])[:400]}")

        texto = "\n".join(lineas)
        return {
            "texto": texto,
            "consultas": consultas,
            "cuentas": cuentas,
            "supuestos": supuestos,
            "hallazgos": hallazgos,
            "estado_sesion": dict(self.estado),
            "origen": "sesion_exploracion",
            "n_turnos": len(hallazgos),
            "_parsed": {
                "texto": texto,
                "hallazgos": hallazgos,
                "consultas": consultas,
                "cuentas": cuentas,
                "supuestos": supuestos,
            },
        }


def run_conversation(
    turnos: list[str],
    *,
    conversation_id: str = "adhoc",
    verbose: bool = True,
) -> dict[str, Any]:
    session = ConversationSession(conversation_id=conversation_id)
    for texto in turnos:
        if verbose:
            print(f"\n######## TURNO: {texto}")
        session.ask(texto, verbose=verbose)
    return session.to_dict()


# Evitar import circular unused warning en type checkers
_ = system_prompt_for
