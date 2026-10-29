from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from app.services.source_selection import normalize_hardware_query, query_looks_like_hardware
from app.utils.product_identity import ACCESSORY_TOKENS, BRAND_MAP, COLOR_TOKENS


QueryIntent = Literal[
    "hardware_component",
    "tool_mro",
    "consumer_electronics",
    "general_unknown",
]


HARDWARE_SYNONYMS: dict[str, tuple[str, ...]] = {
    "ultrasonic module": ("HC-SR04 ultrasonic sensor",),
    "ultrasonic sensor": ("HC-SR04 ultrasonic sensor",),
    "wifi dev board": ("ESP32 development board",),
    "wifi development board": ("ESP32 development board",),
    "uno board": ("Arduino Uno R3",),
    "arduino board": ("Arduino Uno R3",),
    "motor driver": ("L298N motor driver",),
    "lcd module": ("16x2 LCD display module",),
}
CONSUMER_ELECTRONICS_TERMS = {
    "airpods",
    "appliance",
    "camera",
    "earbuds",
    "ethernet",
    "galaxy",
    "headphones",
    "iphone",
    "laptop",
    "macbook",
    "mobile",
    "modem",
    "monitor",
    "network",
    "networking",
    "phone",
    "printer",
    "refrigerator",
    "router",
    "smartphone",
    "switch",
    "tablet",
    "tv",
    "washing",
    "wifi",
}
TOOL_MRO_TERMS = {
    "abrasive",
    "adhesive",
    "bearing",
    "cement",
    "cutting",
    "drill",
    "grinder",
    "helmet",
    "ladder",
    "pipe",
    "ppe",
    "safety",
    "screw",
    "sealant",
    "shoes",
    "tool",
    "welding",
}
MODEL_PATTERN = re.compile(
    r"\b(?:HC-SR04|L298N|ESP32|ESP8266|DT-?830D|STM32|DHT11|DHT22|[A-Z]{1,4}\d{2,}[A-Z0-9-]*)\b",
    re.IGNORECASE,
)
QUANTITY_PATTERN = re.compile(
    r"\b(?:pack\s+of\s+\d+|\d+\s*(?:pcs?|pieces?|pack|uF|v|w|mah|gb|tb|point|x\d+))\b",
    re.IGNORECASE,
)


@dataclass(slots=True, frozen=True)
class QueryUnderstanding:
    original_query: str
    corrected_query: str
    expanded_query: str
    intent: QueryIntent
    synonyms: tuple[str, ...] = field(default_factory=tuple)
    model_tokens: tuple[str, ...] = field(default_factory=tuple)
    quantity_pack: tuple[str, ...] = field(default_factory=tuple)
    accessory_intent: bool = False
    confidence: float = 0.5


@dataclass(slots=True, frozen=True)
class QueryClarity:
    is_clear: bool
    reason: str | None = None
    detail: str | None = None


QUERY_MODIFIER_TOKENS = {
    "above",
    "best",
    "better",
    "below",
    "budget",
    "buy",
    "cheap",
    "cheapest",
    "compare",
    "cost",
    "deal",
    "deals",
    "discount",
    "expensive",
    "for",
    "free",
    "good",
    "india",
    "latest",
    "low",
    "lowest",
    "near",
    "new",
    "offer",
    "offers",
    "online",
    "price",
    "prices",
    "sale",
    "than",
    "under",
    "upto",
    "with",
}
PRICE_ONLY_PATTERN = re.compile(
    r"^\s*(?:under|below|above|upto|less\s+than|more\s+than)?\s*(?:rs\.?|inr|₹)?\s*\d+[\d,]*\s*$",
    re.IGNORECASE,
)


def understand_query(query: str) -> QueryUnderstanding:
    original_query = " ".join(query.split()).strip()
    corrected_query = normalize_hardware_query(original_query)
    normalized_query = corrected_query.lower()
    synonyms = _synonyms_for_query(normalized_query)
    expanded_query = corrected_query
    if synonyms and not any(synonym.lower() in normalized_query for synonym in synonyms):
        expanded_query = f"{corrected_query} {synonyms[0]}"

    intent = _classify_intent(corrected_query)
    model_tokens = tuple(dict.fromkeys(match.group(0).upper() for match in MODEL_PATTERN.finditer(corrected_query)))
    quantity_pack = tuple(dict.fromkeys(match.group(0) for match in QUANTITY_PATTERN.finditer(corrected_query)))
    accessory_intent = any(token in ACCESSORY_TOKENS for token in re.findall(r"[a-z0-9]+", normalized_query))
    confidence = _confidence(original_query, corrected_query, intent, synonyms, model_tokens)
    return QueryUnderstanding(
        original_query=original_query,
        corrected_query=corrected_query,
        expanded_query=expanded_query,
        intent=intent,
        synonyms=synonyms,
        model_tokens=model_tokens,
        quantity_pack=quantity_pack,
        accessory_intent=accessory_intent,
        confidence=confidence,
    )


def assess_query_clarity(
    query: str,
    understanding: QueryUnderstanding | None = None,
) -> QueryClarity:
    understanding = understanding or understand_query(query)
    normalized_query = understanding.corrected_query.strip()
    tokens = re.findall(r"[a-z0-9]+", normalized_query.lower())
    if not tokens:
        return QueryClarity(
            is_clear=False,
            reason="empty_query",
            detail="Enter a product name, product category, brand plus model, or part number.",
        )

    if PRICE_ONLY_PATTERN.fullmatch(normalized_query):
        return QueryClarity(
            is_clear=False,
            reason="budget_without_product",
            detail="Add the product you want to search for, for example `laptop under 50000`.",
        )

    token_set = set(tokens)
    product_signal_tokens = (
        set(BRAND_MAP)
        | ACCESSORY_TOKENS
        | CONSUMER_ELECTRONICS_TERMS
        | TOOL_MRO_TERMS
    )
    has_alphanumeric_model_token = any(
        len(token) >= 3
        and any(character.isalpha() for character in token)
        and any(character.isdigit() for character in token)
        for token in tokens
    )
    has_product_signal = (
        understanding.intent != "general_unknown"
        or bool(understanding.model_tokens)
        or has_alphanumeric_model_token
        or bool(token_set & product_signal_tokens)
    )
    informative_tokens = [
        token
        for token in tokens
        if token not in QUERY_MODIFIER_TOKENS
        and token not in COLOR_TOKENS
        and not token.isdigit()
    ]

    if has_product_signal:
        return QueryClarity(is_clear=True)

    if not informative_tokens:
        return QueryClarity(
            is_clear=False,
            reason="modifier_without_product",
            detail="The search only contains budget, color, or shopping words. Add a product name or category.",
        )

    if len(informative_tokens) == 1 and len(informative_tokens[0]) < 4:
        return QueryClarity(
            is_clear=False,
            reason="too_short",
            detail="Enter a more specific product name, category, or model number.",
        )

    return QueryClarity(is_clear=True)


def _classify_intent(query: str) -> QueryIntent:
    normalized_query = query.lower()
    tokens = set(re.findall(r"[a-z0-9]+", normalized_query))
    if query_looks_like_hardware(query):
        if tokens & TOOL_MRO_TERMS:
            return "tool_mro"
        return "hardware_component"
    if tokens & CONSUMER_ELECTRONICS_TERMS:
        return "consumer_electronics"
    return "general_unknown"


def _synonyms_for_query(normalized_query: str) -> tuple[str, ...]:
    synonyms: list[str] = []
    for phrase, phrase_synonyms in HARDWARE_SYNONYMS.items():
        if phrase in normalized_query:
            synonyms.extend(phrase_synonyms)
    return tuple(dict.fromkeys(synonyms))


def _confidence(
    original_query: str,
    corrected_query: str,
    intent: QueryIntent,
    synonyms: tuple[str, ...],
    model_tokens: tuple[str, ...],
) -> float:
    score = 0.45
    if intent != "general_unknown":
        score += 0.25
    if synonyms:
        score += 0.1
    if model_tokens:
        score += 0.15
    if corrected_query.lower() != original_query.lower():
        score += 0.05
    return min(score, 1.0)
