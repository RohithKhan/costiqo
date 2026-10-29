from __future__ import annotations

import json
import re
from decimal import Decimal
from html import unescape
from typing import Any
from urllib.parse import urlparse

from app.utils.price_parser import parse_price


GOOGLE_HOSTS = {"google.com", "google.co.in"}


def is_probable_product_page_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False

    hostname = (parsed.hostname or "").lower().removeprefix("www.")
    if hostname in GOOGLE_HOSTS or hostname.endswith(".google.com") or hostname.endswith(".google.co.in"):
        return False

    path = parsed.path.strip("/")
    if not path:
        return False

    path_lower = f"/{path.lower()}"
    blocked_segments = (
        "/search",
        "/collections",
        "/collection",
        "/category",
        "/categories",
        "/all-products",
        "/cart",
        "/checkout",
    )
    if any(path_lower == segment or path_lower.startswith(f"{segment}/") for segment in blocked_segments):
        return False

    if parsed.query and re.search(r"(^|&)(q|query|search|search_query|keyword|s)=", parsed.query, re.IGNORECASE):
        if not _has_product_marker(path_lower):
            return False

    if _has_product_marker(path_lower):
        return True

    last_segment = path.rsplit("/", 1)[-1]
    slug_tokens = re.findall(r"[a-z0-9]+", last_segment.lower())
    return len(last_segment) >= 8 and len(slug_tokens) >= 2


def extract_current_product_price(
    text: str,
    *,
    expected_price: float | None = None,
) -> float | None:
    if not text:
        return None

    structured_candidates = _extract_structured_price_candidates(text)
    if expected_price is not None:
        exact = _find_expected_match(structured_candidates, expected_price)
        if exact is not None:
            return exact
    if structured_candidates:
        return structured_candidates[0]

    visible_text = _html_to_visible_text(text)
    rendered_candidates = _extract_visible_price_candidates(visible_text)
    if expected_price is not None:
        exact = _find_expected_match(rendered_candidates[:20], expected_price)
        if exact is not None:
            return exact
    if rendered_candidates:
        return rendered_candidates[0]
    return None


def extract_page_title(html_text: str) -> str | None:
    title_match = re.search(r"<title[^>]*>(?P<title>.*?)</title>", html_text, re.IGNORECASE | re.DOTALL)
    if title_match:
        return _clean_text(title_match.group("title"))

    meta_match = re.search(
        r'<meta[^>]+(?:property|name)=["\']og:title["\'][^>]+content=["\'](?P<title>[^"\']+)["\']',
        html_text,
        re.IGNORECASE,
    )
    if meta_match:
        return _clean_text(meta_match.group("title"))
    return None


def format_inr_price(price: float | Decimal) -> str:
    value = Decimal(str(price)).quantize(Decimal("0.01"))
    if value == value.to_integral_value():
        return f"\u20b9{int(value):,}"
    return f"\u20b9{value:,.2f}"


def _has_product_marker(path_lower: str) -> bool:
    if path_lower.endswith("/p") and path_lower != "/p":
        return True

    return any(
        marker in path_lower
        for marker in (
            "/dp/",
            "/gp/product/",
            "/product/",
            "/products/",
            "/product-page/",
            "/p/",
            "/mp/",
            "/pn/",
            "/itm",
        )
    )


def _extract_structured_price_candidates(text: str) -> list[float]:
    candidates: list[float] = []
    seen: set[float] = set()

    for value in _json_ld_prices(text):
        _append_price_candidate(candidates, seen, value)

    priority_patterns = (
        r'"(?:salePrice|sellingPrice|finalPrice|currentPrice|offerPrice)"\s*:\s*"?(?P<amount>\d[\d,]*(?:\.\d+)?)',
        r'(?:salePrice|sellingPrice|finalPrice|currentPrice|offerPrice)[^0-9]{0,80}(?P<amount>\d[\d,]*(?:\.\d+)?)',
        r'(?:itemprop|property|name)=["\'](?:price|product:price:amount|og:price:amount)["\'][^>]+content=["\'](?P<amount>\d[\d,]*(?:\.\d+)?)',
        r'content=["\'](?P<amount>\d[\d,]*(?:\.\d+)?)["\'][^>]+(?:itemprop|property|name)=["\'](?:price|product:price:amount|og:price:amount)["\']',
        r'"price"\s*:\s*"?(?P<amount>\d[\d,]*(?:\.\d+)?)',
    )
    for pattern in priority_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            context = text[max(0, match.start() - 80): match.start()]
            if _price_context_is_suspicious(context):
                continue
            _append_price_candidate(candidates, seen, match.group("amount"))
    return candidates


def _json_ld_prices(text: str) -> list[Any]:
    prices: list[Any] = []
    for match in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(?P<payload>.*?)</script>',
        text,
        re.IGNORECASE | re.DOTALL,
    ):
        payload = unescape(match.group("payload")).strip()
        if not payload:
            continue
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            continue
        _collect_json_ld_prices(parsed, prices)
    return prices


def _collect_json_ld_prices(value: Any, prices: list[Any]) -> None:
    if isinstance(value, list):
        for item in value:
            _collect_json_ld_prices(item, prices)
        return
    if not isinstance(value, dict):
        return

    raw_type = value.get("@type")
    types = raw_type if isinstance(raw_type, list) else [raw_type]
    normalized_types = {str(item).lower() for item in types if item is not None}
    if normalized_types & {"offer", "aggregateoffer"}:
        for key in ("price", "salePrice", "lowPrice"):
            if value.get(key) is not None:
                prices.append(value.get(key))

    for child in value.values():
        _collect_json_ld_prices(child, prices)


def _extract_visible_price_candidates(text: str) -> list[float]:
    candidates: list[float] = []
    seen: set[float] = set()
    price_pattern = r"(?:\u20b9|rs\.?|inr)\s*(?P<amount>\d[\d,]*(?:\.\d+)?)"
    for match in re.finditer(price_pattern, text[:20000], re.IGNORECASE):
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.end())
        if line_end == -1:
            line_end = min(len(text), match.end() + 80)
        context = text[line_start:match.start()]
        if _price_context_is_suspicious(context):
            continue
        _append_price_candidate(candidates, seen, match.group("amount"))
    return candidates


def _append_price_candidate(candidates: list[float], seen: set[float], value: Any) -> None:
    amount = _parse_amount(value)
    if amount is None or amount in seen:
        return
    seen.add(amount)
    candidates.append(amount)


def _parse_amount(value: Any) -> float | None:
    price = parse_price(value)
    if price is None:
        return None
    amount = float(price)
    if amount <= 0:
        return None
    return amount


def _find_expected_match(candidates: list[float], expected_price: float) -> float | None:
    for candidate in candidates:
        if abs(candidate - expected_price) <= 1.0:
            return candidate
    return None


def _price_context_is_suspicious(context: str) -> bool:
    normalized = _clean_text(context).lower()
    suspicious_terms = (
        "emi",
        "month",
        "monthly",
        "/mo",
        "per month",
        "cashback",
        "coupon",
        "bank offer",
        "exchange",
        "save ",
        "discount",
        "mrp",
        "list price",
        "was \u20b9",
        "delivery",
        "shipping",
        "fee",
    )
    return any(term in normalized for term in suspicious_terms)


def _html_to_visible_text(text: str) -> str:
    without_scripts = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    without_styles = re.sub(r"<style\b[^>]*>.*?</style>", " ", without_scripts, flags=re.IGNORECASE | re.DOTALL)
    without_tags = re.sub(r"<[^>]+>", "\n", without_styles)
    lines = [
        _clean_text(line)
        for line in unescape(without_tags).splitlines()
    ]
    return "\n".join(line for line in lines if line)


def _clean_text(value: str) -> str:
    return " ".join(unescape(value).split()).strip()
