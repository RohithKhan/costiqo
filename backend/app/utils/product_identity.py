import re

from app.utils.text_cleaner import compact_whitespace, tokenize


BRAND_MAP = {
    "apple": "Apple",
    "boat": "boAt",
    "daikin": "Daikin",
    "dell": "Dell",
    "hp": "HP",
    "iphone": "Apple",
    "lenovo": "Lenovo",
    "lg": "LG",
    "mi": "Xiaomi",
    "nothing": "Nothing",
    "oneplus": "OnePlus",
    "oppo": "OPPO",
    "realme": "Realme",
    "redmi": "Xiaomi",
    "samsung": "Samsung",
    "vivo": "Vivo",
    "xiaomi": "Xiaomi",
}

COLOR_TOKENS = {
    "beige",
    "black",
    "blue",
    "coral",
    "cosmic",
    "deep",
    "gold",
    "gray",
    "green",
    "grey",
    "lavender",
    "mist",
    "midnight",
    "navy",
    "onyx",
    "orange",
    "peacock",
    "pink",
    "purple",
    "red",
    "sage",
    "silver",
    "soft",
    "sprouting",
    "starlight",
    "white",
    "yellow",
}

NOISE_TOKENS = {
    "add",
    "all",
    "and",
    "base",
    "best",
    "bestseller",
    "buy",
    "camera",
    "compare",
    "delivery",
    "display",
    "edition",
    "fast",
    "free",
    "front",
    "included",
    "latest",
    "mobile",
    "more",
    "new",
    "off",
    "offer",
    "offers",
    "only",
    "phone",
    "processor",
    "product",
    "protection",
    "ratings",
    "reviews",
    "sale",
    "smartphone",
    "supplier",
    "upto",
    "wall",
    "warranty",
    "with",
}

ACCESSORY_TOKENS = {
    "adapter",
    "accessories",
    "accessory",
    "backcover",
    "bracket",
    "cable",
    "case",
    "cases",
    "charger",
    "charging",
    "cover",
    "covers",
    "guard",
    "holder",
    "magsafe",
    "mount",
    "mounting",
    "part",
    "parts",
    "protector",
    "remote",
    "remotes",
    "skin",
    "spare",
    "spares",
    "stand",
    "tempered",
}

SPEC_TOKENS = {"4g", "5g", "gb", "inch", "mah", "mp", "ram", "rom", "tb"}

VARIANT_TOKENS = {
    "air",
    "fe",
    "lite",
    "max",
    "mini",
    "neo",
    "note",
    "plus",
    "pro",
    "ultra",
}

RESTRICTED_LISTING_TOKENS = {
    "accessories",
    "bundle",
    "bundled",
    "case",
    "combo",
    "kit",
    "openbox",
    "owned",
    "pack",
    "preowned",
    "refurbished",
    "renewed",
    "secondhand",
    "used",
}

RESTRICTED_LISTING_PHRASES = {
    "open box",
    "pre owned",
    "pre-owned",
    "with case",
    "with charger",
    "with cover",
}


def normalize_product_name(value: str) -> str:
    return compact_whitespace(value)


def infer_brand(title: str, query: str) -> str:
    for token in tokenize(f"{title} {query}"):
        if token in BRAND_MAP:
            return BRAND_MAP[token]

    words = normalize_product_name(title).split()
    return words[0] if words else "Unknown"


def infer_category(title: str, query: str) -> str:
    haystack = f"{title} {query}".lower()
    if any(term in haystack for term in ACCESSORY_TOKENS):
        return "Accessories"
    if any(term in haystack for term in ("iphone", "galaxy", "redmi", "oneplus", "smartphone", "mobile")):
        return "Smartphones"
    if any(term in haystack for term in ("laptop", "notebook", "inspiron", "macbook", "thinkpad")):
        return "Laptops"
    if any(term in haystack for term in ("headphone", "headset", "earbud", "earphone", "rockerz")):
        return "Audio"
    if any(term in haystack for term in ("watch", "smartwatch", "band")):
        return "Wearables"
    if any(term in haystack for term in ("appliance", "refrigerator", "washing machine", "geyser", "cooler", "chimney", "mixer grinder", "kettle", "fan")):
        return "Appliances"
    if any(term in haystack for term in ("multimeter", "clamp meter", "tester", "meter", "sensor", "soldering", "arduino", "raspberry pi", "module", "relay", "battery", "capacitor", "resistor", "cable", "wire")):
        return "Electronics"
    if any(term in haystack for term in ("drill", "grinder", "saw", "cutter", "plier", "spanner", "wrench", "screwdriver", "hammer", "fastener", "hinge", "lock", "drawer", "handle", "hardware", "tool")):
        return "Hardware"
    return "Electronics"


def build_product_key(title: str, query: str) -> str:
    filtered_tokens = _filtered_tokens(title)
    query_tokens = tokenize(query)

    shared_tokens = [token for token in filtered_tokens if token in query_tokens]
    spec_tokens = [token for token in filtered_tokens if _is_spec_token(token)]
    extra_tokens = [
        token
        for token in filtered_tokens
        if token not in shared_tokens and token not in spec_tokens
    ]
    extra_tokens_without_brand = [token for token in extra_tokens if token not in BRAND_MAP]

    if len(shared_tokens) >= 2:
        key_tokens = shared_tokens + spec_tokens + extra_tokens_without_brand
    elif shared_tokens:
        key_tokens = shared_tokens + extra_tokens + spec_tokens
    else:
        key_tokens = filtered_tokens

    if len(key_tokens) < 3:
        key_tokens.extend(query_tokens)

    unique_tokens: list[str] = []
    for token in key_tokens:
        if token not in unique_tokens:
            unique_tokens.append(token)

    final_tokens = unique_tokens[:6]
    if not final_tokens:
        fallback = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        return fallback or "unknown-product"
    return "-".join(final_tokens)


def are_model_keys_compatible(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return True
    return _normalized_model_key_tokens(left) == _normalized_model_key_tokens(right)


def _filtered_tokens(value: str) -> list[str]:
    return [
        token
        for token in tokenize(value)
        if token not in COLOR_TOKENS and token not in NOISE_TOKENS
    ]


def _is_spec_token(token: str) -> bool:
    if token in SPEC_TOKENS:
        return True
    return bool(re.fullmatch(r"\d+(?:gb|tb|mp|mah)?", token))


def _normalized_model_key_tokens(value: str) -> list[str]:
    tokens = tokenize(value)
    if tokens and tokens[0] in BRAND_MAP and tokens[0] != "iphone":
        tokens.pop(0)
    while tokens and tokens[-1] in COLOR_TOKENS:
        tokens.pop()
    return tokens
