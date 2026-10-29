from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.utils.product_identity import (
    ACCESSORY_TOKENS,
    COLOR_TOKENS,
    NOISE_TOKENS,
    RESTRICTED_LISTING_PHRASES,
    RESTRICTED_LISTING_TOKENS,
    SPEC_TOKENS,
    VARIANT_TOKENS,
)
from app.utils.text_cleaner import compact_whitespace, tokenize


MATCHING_TOKEN_ALIASES = {
    "development": ("dev",),
    "devkit": ("dev", "devkit"),
    "devkitc": ("dev", "devkitc"),
    "dt830d": ("dt", "830d"),
    "esp32": ("esp", "32"),
    "esp8266": ("esp", "8266"),
    "capactior": ("capacitor",),
    "capacitior": ("capacitor",),
    "iphone15": ("iphone", "15"),
    "nodemcu32": ("nodemcu", "32"),
    "ps4": ("playstation", "4"),
    "ps5": ("playstation", "5"),
    "s25": ("s", "25"),
    "wroom32": ("wroom", "32"),
}
OPTIONAL_BRAND_CONTEXT_TOKENS = {
    "apple": {"airpods", "ipad", "iphone", "macbook", "watch"},
    "samsung": {"galaxy"},
    "xiaomi": {"mi", "redmi"},
}
GENERIC_SIZE_CONTEXT_TOKENS = {
    "display",
    "laptop",
    "monitor",
    "notebook",
    "screen",
    "television",
    "tv",
}
PACKAGE_CONTEXT_TOKENS = {
    "pack",
    "package",
    "pc",
    "pcs",
    "piece",
    "pieces",
    "set",
}
PACKAGE_TOKEN_ALIASES = {
    "packs": "pack",
    "package": "pack",
    "packages": "pack",
    "pc": "pcs",
    "piece": "pcs",
    "pieces": "pcs",
    "sets": "set",
}
PLURAL_TOKEN_ALIASES = {
    "capacitors": "capacitor",
    "cables": "cable",
    "connectors": "connector",
    "modules": "module",
    "resistors": "resistor",
    "sensors": "sensor",
    "wires": "wire",
}


def normalize_text(value: str) -> str:
    return compact_whitespace(value.lower())


def match_score(query: str, *candidates: str | None) -> float:
    query_tokens = set(_matching_sequence(query))
    if not query_tokens:
        return 1.0

    candidate_text = " ".join(filter(None, candidates))
    candidate_tokens = set(_matching_sequence(candidate_text))
    if not candidate_tokens:
        return 0.0

    overlap = len(query_tokens & candidate_tokens) / len(query_tokens)
    ratio = SequenceMatcher(
        None,
        " ".join(sorted(query_tokens)),
        " ".join(sorted(candidate_tokens)),
    ).ratio()
    return round((overlap * 0.7) + (ratio * 0.3), 4)


def has_identifier_conflict(query: str, *candidates: str | None) -> bool:
    query_tokens = _matching_sequence(query)
    candidate_text = " ".join(filter(None, candidates))
    candidate_sequence = _matching_sequence(candidate_text)
    candidate_tokens = set(candidate_sequence)
    if not query_tokens or not candidate_tokens:
        return False

    if _has_variant_conflict(query_tokens, candidate_sequence):
        return True

    query_numeric_model_tokens = {
        token
        for index, token in enumerate(query_tokens)
        if (
            any(character.isdigit() for character in token)
            and token not in SPEC_TOKENS
            and not _is_context_bound_digit(query_tokens, index)
        )
    }
    candidate_numeric_model_tokens = {
        token
        for index, token in enumerate(candidate_sequence)
        if (
            any(character.isdigit() for character in token)
            and token not in SPEC_TOKENS
            and not _is_context_bound_digit(candidate_sequence, index)
        )
    }
    if (
        query_numeric_model_tokens
        and candidate_numeric_model_tokens
        and not (query_numeric_model_tokens & candidate_numeric_model_tokens)
    ):
        return True

    return False


def listing_matches_query(query: str, *candidates: str | None) -> bool:
    query_tokens = _matching_sequence(query)
    candidate_text = " ".join(filter(None, candidates))
    normalized_candidate_text = normalize_text(candidate_text)
    candidate_sequence = _matching_sequence(candidate_text)
    candidate_tokens = set(candidate_sequence)
    compact_query = _compact_text(query)
    compact_candidate = _compact_text(candidate_text)
    compact_query_match = len(compact_query) >= 5 and compact_query in compact_candidate

    query_has_package_intent = bool(set(query_tokens) & PACKAGE_CONTEXT_TOKENS)
    if _contains_restricted_listing_terms(
        normalized_candidate_text,
        candidate_tokens,
        query_has_package_intent=query_has_package_intent,
    ):
        return False

    if has_identifier_conflict(query, *candidates):
        return False

    query_has_accessory_intent = any(token in ACCESSORY_TOKENS for token in query_tokens)
    candidate_accessory_tokens = candidate_tokens & ACCESSORY_TOKENS
    if "wire" in query_tokens or "jumper" in query_tokens:
        candidate_accessory_tokens -= {"cable"}
    if candidate_accessory_tokens and not query_has_accessory_intent:
        return False

    if compact_query_match:
        return True

    required_query_tokens = _required_query_tokens(query_tokens)
    missing_required_tokens = required_query_tokens - candidate_tokens
    if missing_required_tokens and not _missing_required_tokens_allowed(
        missing_required_tokens,
        candidate_tokens,
    ):
        return False

    if _has_variant_conflict(query_tokens, candidate_sequence):
        return False

    alpha_query_tokens = {token for token in query_tokens if not token.isdigit()}
    numeric_query_tokens = {token for token in query_tokens if token.isdigit()}
    if alpha_query_tokens and not (alpha_query_tokens & candidate_tokens):
        return False

    query_numeric_bigrams = {
        (left, right)
        for index, (left, right) in enumerate(zip(query_tokens, query_tokens[1:]))
        if (
            left.isdigit()
            and not _is_context_bound_digit(query_tokens, index)
        )
        or (
            right.isdigit()
            and not _is_context_bound_digit(query_tokens, index + 1)
        )
    }
    query_informative_mixed_bigrams = {
        (left, right)
        for index, (left, right) in enumerate(zip(query_tokens, query_tokens[1:]))
        if (
            right.isdigit()
            and not left.isdigit()
            and left not in SPEC_TOKENS
            and not _is_context_bound_digit(query_tokens, index + 1)
        )
        or (
            left.isdigit()
            and not right.isdigit()
            and right not in SPEC_TOKENS
            and not _is_context_bound_digit(query_tokens, index)
        )
    }
    candidate_bigrams = set(zip(candidate_sequence, candidate_sequence[1:]))
    if query_informative_mixed_bigrams:
        if not (query_informative_mixed_bigrams & candidate_bigrams):
            fallback_tokens = {
                token
                for bigram in query_informative_mixed_bigrams
                for token in bigram
            }
            if not fallback_tokens <= candidate_tokens or match_score(query, *candidates) < 0.6:
                return False
    elif query_numeric_bigrams:
        if not (query_numeric_bigrams & candidate_bigrams):
            fallback_tokens = {
                token
                for bigram in query_numeric_bigrams
                for token in bigram
            }
            if not fallback_tokens <= candidate_tokens or match_score(query, *candidates) < 0.6:
                return False
    elif numeric_query_tokens and not (numeric_query_tokens & candidate_tokens):
        return False

    score = match_score(query, *candidates)
    if score >= 0.35:
        return True

    return False


def _contains_restricted_listing_terms(
    candidate_text: str,
    candidate_tokens: set[str],
    *,
    query_has_package_intent: bool,
) -> bool:
    restricted_tokens = candidate_tokens & RESTRICTED_LISTING_TOKENS
    if query_has_package_intent:
        restricted_tokens -= {"kit", "pack"}
    if restricted_tokens:
        return True
    return any(phrase in candidate_text for phrase in RESTRICTED_LISTING_PHRASES)


def _compact_text(value: str) -> str:
    return "".join(_matching_sequence(value))


def _required_query_tokens(query_tokens: list[str]) -> set[str]:
    required: set[str] = set()
    for token in query_tokens:
        if token in ACCESSORY_TOKENS or token in COLOR_TOKENS or token in NOISE_TOKENS:
            continue
        if token in PACKAGE_CONTEXT_TOKENS:
            continue
        if token in SPEC_TOKENS:
            continue
        if token in VARIANT_TOKENS or any(character.isdigit() for character in token) or len(token) >= 3:
            required.add(token)
    return required


def _missing_required_tokens_allowed(
    missing_tokens: set[str],
    candidate_tokens: set[str],
) -> bool:
    for token in missing_tokens:
        if token in PACKAGE_CONTEXT_TOKENS and candidate_tokens & PACKAGE_CONTEXT_TOKENS:
            continue
        context_tokens = OPTIONAL_BRAND_CONTEXT_TOKENS.get(token)
        if not context_tokens or not (context_tokens & candidate_tokens):
            return False
    return True


def _is_spec_bound_digit(tokens: list[str], index: int) -> bool:
    token = tokens[index]
    if not any(character.isdigit() for character in token):
        return False
    previous_token = tokens[index - 1] if index > 0 else None
    next_token = tokens[index + 1] if index + 1 < len(tokens) else None
    return previous_token in SPEC_TOKENS or next_token in SPEC_TOKENS


def _is_context_bound_digit(tokens: list[str], index: int) -> bool:
    if _is_spec_bound_digit(tokens, index):
        return True
    token = tokens[index]
    if not any(character.isdigit() for character in token):
        return False
    previous_token = tokens[index - 1] if index > 0 else None
    next_token = tokens[index + 1] if index + 1 < len(tokens) else None
    return (
        previous_token in GENERIC_SIZE_CONTEXT_TOKENS
        or next_token in GENERIC_SIZE_CONTEXT_TOKENS
        or previous_token in PACKAGE_CONTEXT_TOKENS
        or next_token in PACKAGE_CONTEXT_TOKENS
    )


def _has_variant_conflict(query_tokens: list[str], candidate_sequence: list[str]) -> bool:
    query_variants = _extract_variant_tokens(query_tokens)
    candidate_variants = _extract_variant_tokens(candidate_sequence)
    if not query_variants:
        return False
    return not query_variants <= candidate_variants or bool(candidate_variants - query_variants)


def _extract_variant_tokens(tokens: list[str]) -> set[str]:
    variants: set[str] = set()
    for index, token in enumerate(tokens):
        if token not in VARIANT_TOKENS:
            continue
        next_token = tokens[index + 1] if index + 1 < len(tokens) else None
        if token == "mini" and next_token in {"led", "display"}:
            continue
        if token == "ultra" and next_token == "hd":
            continue
        variants.add(token)
    return variants


def _matching_sequence(value: str) -> list[str]:
    tokens: list[str] = []
    for token in tokenize(value):
        for expanded_token in _expand_quantity_token(token):
            normalized_token = _normalize_matching_token(expanded_token)
            alias_tokens = MATCHING_TOKEN_ALIASES.get(normalized_token)
            if alias_tokens:
                tokens.extend(alias_tokens)
                continue
            tokens.append(normalized_token)
    return tokens


def _normalize_matching_token(token: str) -> str:
    ordinal_match = re.fullmatch(r"(\d+)(?:st|nd|rd|th)", token)
    if ordinal_match:
        return ordinal_match.group(1)
    package_alias = PACKAGE_TOKEN_ALIASES.get(token)
    if package_alias is not None:
        return package_alias
    plural_alias = PLURAL_TOKEN_ALIASES.get(token)
    if plural_alias is not None:
        return plural_alias
    return token


def _expand_quantity_token(token: str) -> list[str]:
    match = re.fullmatch(r"(\d+)(pcs?|pieces?|packs?|sets?)", token)
    if match:
        return [match.group(1), match.group(2)]
    return [token]
