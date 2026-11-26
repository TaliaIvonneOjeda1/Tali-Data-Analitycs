"""Alcance del analista: solo datos comerciales de Almacenes del Sur."""

from __future__ import annotations

import re
import unicodedata

REFUSAL_TEXT = (
    "Lo siento, no cuento con la información o los permisos "
    "para darte esta respuesta."
)

_BUSINESS_HINTS = (
    "almacen",
    "almacenes",
    "sur",
    "venta",
    "ventas",
    "margen",
    "presupuesto",
    "stock",
    "quiebre",
    "promocion",
    "promo",
    "sucursal",
    "region",
    "norte",
    "oeste",
    "centro",
    "categoria",
    "subcategoria",
    "proveedor",
    "producto",
    "sku",
    "marca",
    "del sur",
    "fiscal",
    "af20",
    "trimestre",
    "lfl",
    "comparable",
    "like for like",
    "desvio",
    "unidad",
    "unidades",
    "importe",
    "costo",
    "precio",
    "lacteo",
    "bebida",
    "limpieza",
    "perfumeria",
    "fresco",
    "informe",
    "kpi",
    "ranking",
    "top ",
    "yoy",
    "interanual",
    "ticket",  # para poder decir "no está" con trazabilidad
    "cliente",
    "online",
)

_OFFTOPIC_HINTS = (
    "messi",
    "ronaldo",
    "boca",
    "river",
    "futbol",
    "football",
    "celebridad",
    "famoso",
    "famosa",
    "presidente",
    "politica",
    "eleccion",
    "clima",
    "pronostico",
    "receta",
    "chiste",
    "poema",
    "cancion",
    "pelicula",
    "serie",
    "netflix",
    "wikipedia",
    "chatgpt",
    "quien gano",
    "quien es",
    "que es el amor",
    "capital de",
    "traducime",
    "traducir",
    "escribe un",
    "escribime un",
)


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_txt = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return ascii_txt.lower().strip()


def is_out_of_scope(text: str) -> bool:
    """Heurística conservadora: solo bloquea fuera de alcance evidente."""
    folded = _fold(text)
    if len(folded) < 2:
        return False
    # Seguimientos cortos típicos de la sesión comercial.
    if len(folded) <= 40 and re.fullmatch(
        r"(y\s+)?(en|para|por|del?|la|el|los|las)?\s*"
        r"(norte|sur|oeste|centro|af\d{4}|t[1-4]|mayo|junio|julio|"
        r"agosto|septiembre|octubre|noviembre|diciembre|"
        r"margen|ventas?|presupuesto|stock|lfl|comparables?).*\??",
        folded,
    ):
        return False

    has_business = any(hint in folded for hint in _BUSINESS_HINTS)
    has_offtopic = any(hint in folded for hint in _OFFTOPIC_HINTS)
    if has_offtopic and not has_business:
        return True
    # Preguntas de cultura general sin ancla comercial.
    if re.search(r"\b(quien|quién|que|qué)\s+es\b", folded) and not has_business:
        return True
    return False


def refusal_payload(pregunta: str) -> dict:
    return {
        "pregunta": pregunta,
        "texto": REFUSAL_TEXT,
        "valor": None,
        "unidad": None,
        "supuestos": [
            "La consulta está fuera del alcance de los datos comerciales "
            "de Almacenes del Sur."
        ],
        "consultas": [],
        "cuentas": [],
        "siguiente_pregunta_sugerida": None,
        "alerta_desvio": None,
        "_meta": {
            "tiempo_s": 0.0,
            "costo_usd": 0.0,
            "usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
            "scope_blocked": True,
        },
    }
