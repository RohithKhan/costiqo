from __future__ import annotations

from difflib import SequenceMatcher
import re


HARDWARE_QUERY_TERM_ALIASES = {
    "capactior": "capacitor",
    "capacitior": "capacitor",
}

HARDWARE_QUERY_TERMS = (
    "abrasive",
    "adhesive",
    "access point",
    "anchor",
    "arduino",
    "bearing",
    "battery",
    "bms",
    "bolt",
    "breadboard",
    "bosch",
    "brick",
    "buck",
    "capacitor",
    "capactior",
    "capacitior",
    "cement",
    "channel",
    "chemical",
    "component",
    "concrete",
    "conduit",
    "connector",
    "converter",
    "construction",
    "coupling",
    "cpvc",
    "crimp",
    "cutting",
    "drill",
    "electrode",
    "elbow",
    "electronicscomp",
    "ethernet",
    "esp",
    "esp32",
    "esp8266",
    "fastener",
    "ferrule",
    "fitting",
    "gpio",
    "glove",
    "gloves",
    "grinder",
    "grout",
    "hardware",
    "helmet",
    "hinge",
    "industrial",
    "jumper",
    "kit",
    "ladder",
    "lcr",
    "lcd",
    "led",
    "lipo",
    "lithium",
    "mcu",
    "microcontroller",
    "module",
    "modem",
    "mosfet",
    "motor",
    "mro",
    "multimeter",
    "nano",
    "network",
    "networking",
    "nodemcu",
    "nut",
    "paint",
    "pcb",
    "photodiode",
    "pipe",
    "plumbing",
    "plywood",
    "ppe",
    "primer",
    "putty",
    "raspberry",
    "relay",
    "resistor",
    "robot",
    "robotics",
    "rod",
    "router",
    "safety",
    "sanitary",
    "screw",
    "sealant",
    "servo",
    "sensor",
    "shoes",
    "solder",
    "soldering",
    "staple",
    "stm32",
    "steel",
    "stripper",
    "switch",
    "tmt",
    "tool",
    "transistor",
    "ultrasonic",
    "upvc",
    "valve",
    "washer",
    "waterproofing",
    "welding",
    "wifi",
    "wroom",
    "wire",
)

HARDWARE_PRIMARY_SOURCE_ORDER = (
    "moglix",
    "robu",
    "electronicscomp",
    "ibo",
    "global-electronics",
    "amazon",
)

CONSUMER_PRIMARY_SOURCE_ORDER = (
    "flipkart",
    "poorvika",
    "reliance-digital",
    "amazon",
    "croma",
)


def query_looks_like_hardware(query: str) -> bool:
    normalized_query = query.lower()
    compact_query = _compact_query(query)
    tokens = _query_tokens(normalized_query)
    if any(
        _query_contains_hardware_term(normalized_query, compact_query, tokens, term)
        for term in HARDWARE_QUERY_TERMS
    ):
        return True
    return any(
        _token_matches_hardware_term(token, term)
        for token in tokens
        for term in HARDWARE_QUERY_TERMS
    )


def normalize_hardware_query(query: str) -> str:
    return re.sub(
        r"[A-Za-z0-9]+",
        lambda match: _normalize_hardware_query_token(match.group(0)),
        query,
    )


def select_query_primary_sources(
    configured_sources: list[str],
    query: str,
) -> list[str] | None:
    if not configured_sources:
        return None
    return list(dict.fromkeys(configured_sources))


def select_query_suggestion_sources(
    configured_sources: list[str],
    query: str,
    *,
    limit: int,
) -> list[str]:
    if not configured_sources:
        return []

    ordered_sources = select_query_primary_sources(configured_sources, query) or configured_sources
    return ordered_sources[:limit]


def _compact_query(query: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", query.lower())


def _query_tokens(query: str) -> set[str]:
    tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
    tokens.update(
        token[:-1]
        for token in list(tokens)
        if len(token) > 4 and token.endswith("s")
    )
    return tokens


def _query_contains_hardware_term(
    normalized_query: str,
    compact_query: str,
    tokens: set[str],
    term: str,
) -> bool:
    normalized_term = term.lower()
    term_tokens = re.findall(r"[a-z0-9]+", normalized_term)
    if not term_tokens:
        return False
    if len(term_tokens) == 1:
        compact_term = _compact_query(normalized_term)
        return normalized_term in tokens or (
            any(character.isdigit() for character in compact_term)
            and compact_term in compact_query
        )

    phrase_pattern = r"\b" + r"\s+".join(re.escape(token) for token in term_tokens) + r"\b"
    if re.search(phrase_pattern, normalized_query):
        return True

    compact_term = _compact_query(normalized_term)
    return any(character.isdigit() for character in compact_term) and compact_term in compact_query


def _normalize_hardware_query_token(token: str) -> str:
    normalized_token = token.lower()
    alias = HARDWARE_QUERY_TERM_ALIASES.get(normalized_token)
    if alias is not None:
        return _match_case(token, alias)
    for term in HARDWARE_QUERY_TERMS:
        if _token_matches_hardware_term(normalized_token, term):
            return _match_case(token, term)
    return token


def _token_matches_hardware_term(token: str, term: str) -> bool:
    normalized_term = term.lower()
    if token == normalized_term:
        return True
    if len(token) < 6 or len(normalized_term) < 6:
        return False
    if token[0] != normalized_term[0]:
        return False
    return SequenceMatcher(None, token, normalized_term).ratio() >= 0.88


def _match_case(original: str, replacement: str) -> str:
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper():
        return replacement.capitalize()
    return replacement
