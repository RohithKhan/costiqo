from __future__ import annotations

import asyncio
from decimal import Decimal
import re
from threading import Lock
from typing import Any
from urllib.parse import urljoin

import httpx

from app.scrapers.base import BaseScraper, PriceHistoryEntry, ScrapedListing
from app.services.query_understanding_service import understand_query
from app.services.source_selection import normalize_hardware_query
from app.utils.number_parser import parse_count_value, parse_rating_value
from app.utils.price_parser import parse_price
from app.utils.product_identity import build_product_key, infer_brand, infer_category, normalize_product_name
from app.utils.time_utils import utc_now
from app.utils.vendor_links import canonicalize_vendor_product_url


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

GENERIC_HARDWARE_TERMS = (
    "anchor bolt",
    "asian paints",
    "ball valve",
    "cement based putty",
    "cement board",
    "cpvc elbow",
    "cpvc pipe",
    "cutting wheel",
    "grinding wheel",
    "industrial glove",
    "pipe fitting",
    "safety helmet",
    "safety shoes",
    "wire stripper",
    "clamp meter",
    "digital multimeter",
    "breadboard",
    "servo motor",
    "ultrasonic sensor",
    "dht11 sensor",
    "dht22 sensor",
    "l298n motor driver",
    "buck converter",
    "boost converter",
    "18650 battery",
    "bms module",
    "oled display",
    "lcd display",
    "impact drill",
    "drill machine",
    "soldering iron",
    "soldering station",
    "relay module",
    "jumper wire",
    "raspberry pi",
    "arduino uno",
    "arduino nano",
    "stm32",
    "angle grinder",
    "wall putty",
    "white cement",
    "wedge anchor",
    "waterproofing",
    "tile adhesive",
    "multimeter",
    "adhesive",
    "anchor",
    "bearing",
    "bolt",
    "cement",
    "conduit",
    "coupling",
    "cpvc",
    "elbow",
    "fastener",
    "fitting",
    "gloves",
    "drill",
    "helmet",
    "hinge",
    "ladder",
    "nut",
    "paint",
    "pipe",
    "plywood",
    "primer",
    "putty",
    "rod",
    "safety",
    "screw",
    "sealant",
    "shoes",
    "steel",
    "stripper",
    "soldering",
    "relay",
    "sensor",
    "module",
    "arduino",
    "esp32",
    "esp",
    "capacitor",
    "resistor",
    "mosfet",
    "transistor",
    "breadboard",
    "wire",
    "gpio",
    "led",
    "motor",
    "servo",
    "ultrasonic",
    "lithium",
    "battery",
    "converter",
    "crimper",
    "grinder",
    "tmt",
    "upvc",
    "valve",
    "washer",
    "welding",
)

GENERIC_QUERY_SKIP_TOKENS = {
    "and",
    "for",
    "heavy",
    "industrial",
    "official",
    "with",
}


_shared_clients: dict[asyncio.AbstractEventLoop, httpx.AsyncClient] = {}
_client_lock = Lock()


def get_shared_client() -> httpx.AsyncClient:
    """Return an active AsyncClient for the current event loop, reusing connections with connection pooling."""
    loop = asyncio.get_running_loop()
    with _client_lock:
        # Purge any clients whose event loops are closed
        dead_loops = [l for l in _shared_clients if l.is_closed()]
        for l in dead_loops:
            _shared_clients.pop(l, None)

        client = _shared_clients.get(loop)
        if client is None or client.is_closed:
            limits = httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
                keepalive_expiry=30.0,
            )
            client = httpx.AsyncClient(
                follow_redirects=True,
                limits=limits,
                timeout=httpx.Timeout(20.0, connect=5.0),
            )
            _shared_clients[loop] = client
        return client


async def close_shared_clients() -> None:
    """Close all shared AsyncClient instances and release connection pools."""
    with _client_lock:
        clients = list(_shared_clients.values())
        _shared_clients.clear()
    for client in clients:
        if not client.is_closed:
            try:
                await client.aclose()
            except Exception:
                pass


async def fetch_html(
    url: str,
    *,
    timeout_seconds: int | float | httpx.Timeout = 20,
    user_agent: str = USER_AGENT,
    client: httpx.AsyncClient | None = None,
) -> str:
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": "en-IN,en;q=0.9",
        "user-agent": user_agent,
    }
    http_client = client or get_shared_client()
    timeout = (
        timeout_seconds
        if isinstance(timeout_seconds, httpx.Timeout)
        else httpx.Timeout(float(timeout_seconds), connect=min(5.0, float(timeout_seconds)))
    )
    response = await http_client.get(
        url,
        headers=headers,
        timeout=timeout,
    )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"Vendor page failed with status {exc.response.status_code}: {exc.response.text[:300]}"
        ) from exc
    return response.text


async def fetch_json(
    url: str,
    *,
    timeout_seconds: int | float | httpx.Timeout = 20,
    user_agent: str = USER_AGENT,
    extra_headers: dict[str, str] | None = None,
    client: httpx.AsyncClient | None = None,
) -> Any:
    headers = {
        "accept": "application/json,text/plain,*/*",
        "accept-language": "en-IN,en;q=0.9",
        "user-agent": user_agent,
    }
    if extra_headers:
        headers.update(extra_headers)
    http_client = client or get_shared_client()
    timeout = (
        timeout_seconds
        if isinstance(timeout_seconds, httpx.Timeout)
        else httpx.Timeout(float(timeout_seconds), connect=min(5.0, float(timeout_seconds)))
    )
    response = await http_client.get(
        url,
        headers=headers,
        timeout=timeout,
    )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"Vendor API failed with status {exc.response.status_code}: {exc.response.text[:300]}"
        ) from exc
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError("Vendor API response was not valid JSON.") from exc


async def post_json(
    url: str,
    *,
    payload: dict[str, Any],
    timeout_seconds: int | float | httpx.Timeout = 20,
    user_agent: str = USER_AGENT,
    extra_headers: dict[str, str] | None = None,
    client: httpx.AsyncClient | None = None,
) -> Any:
    headers = {
        "accept": "application/json,text/plain,*/*",
        "accept-language": "en-IN,en;q=0.9",
        "content-type": "application/json",
        "user-agent": user_agent,
    }
    if extra_headers:
        headers.update(extra_headers)
    http_client = client or get_shared_client()
    timeout = (
        timeout_seconds
        if isinstance(timeout_seconds, httpx.Timeout)
        else httpx.Timeout(float(timeout_seconds), connect=min(5.0, float(timeout_seconds)))
    )
    response = await http_client.post(
        url,
        json=payload,
        headers=headers,
        timeout=timeout,
    )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"Vendor API failed with status {exc.response.status_code}: {exc.response.text[:300]}"
        ) from exc
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError("Vendor API response was not valid JSON.") from exc


def build_listing(
    scraper: BaseScraper,
    query: str,
    *,
    title: str,
    product_url: str,
    price: Decimal | int | float | str | None,
    raw_price: str | None = None,
    image_url: str | None = None,
    brand: str | None = None,
    category: str | None = None,
    model_number: str | None = None,
    rating: float | str | None = None,
    review_count: int | str | None = None,
    delivery_info: str | None = None,
    availability_status: str = "in_stock",
    raw_payload: dict[str, Any] | None = None,
) -> ScrapedListing | None:
    normalized_title = normalize_product_name(title)
    price_value = parse_price(price)
    if not normalized_title or price_value is None or not product_url:
        return None

    resolved_url = canonicalize_vendor_product_url(
        scraper.vendor_name,
        product_url,
        scraper.base_url,
    )
    now = utc_now()
    return ScrapedListing(
        vendor=scraper.vendor_name,
        base_url=scraper.base_url,
        scrape_strategy=scraper.scrape_strategy,
        canonical_name=normalized_title,
        brand=brand or infer_brand(normalized_title, query),
        category=category or infer_category(normalized_title, query),
        model_number=model_number or build_product_key(normalized_title, query),
        image_url=normalize_url(image_url or "", scraper.base_url),
        vendor_product_name=normalized_title,
        product_url=resolved_url,
        price=price_value,
        raw_price=raw_price or f"₹{price_value:,.0f}",
        rating=rating if isinstance(rating, float) else parse_rating_value(str(rating) if rating else None),
        review_count=(
            review_count
            if isinstance(review_count, int)
            else parse_count_value(str(review_count) if review_count else None)
        ),
        delivery_info=delivery_info,
        availability_status=availability_status,
        price_history=[
            PriceHistoryEntry(
                scraped_at=now,
                price=price_value,
            )
        ],
        raw_payload=raw_payload or {},
    )


def normalize_url(value: str, base_url: str) -> str:
    value = coerce_text(value)
    if not value:
        return ""
    return urljoin(f"{base_url}/", value)


def coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split()).strip()
    return str(value).strip()


def query_variants(query: str) -> list[str]:
    original = coerce_text(query)
    if not original:
        return []

    variants = [original]
    corrected_query = coerce_text(normalize_hardware_query(original))
    if corrected_query and corrected_query.lower() != original.lower():
        variants.append(corrected_query)
    understanding = understand_query(original)
    variants.extend(understanding.synonyms)
    if understanding.expanded_query.lower() != original.lower():
        variants.append(understanding.expanded_query)
    tokens = re.findall(r"[A-Za-z0-9]+", original)
    if not tokens:
        return variants

    for index, token in enumerate(tokens[:-1]):
        next_token = tokens[index + 1]
        if token.isalpha() and any(character.isdigit() for character in next_token):
            combined_tokens = [*tokens[:index], f"{token}{next_token}", *tokens[index + 2:]]
            variants.append(" ".join(combined_tokens))

    if any(any(character.isdigit() for character in token) for token in tokens) and len(tokens) <= 3:
        variants.append("".join(tokens))

    variants.extend(_generic_hardware_query_variants(original, tokens))

    unique_variants: list[str] = []
    for variant in variants:
        normalized_variant = coerce_text(variant)
        if normalized_variant and normalized_variant.lower() not in {
            item.lower() for item in unique_variants
        }:
            unique_variants.append(normalized_variant)
    return unique_variants


def _generic_hardware_query_variants(query: str, tokens: list[str]) -> list[str]:
    normalized_query = coerce_text(query).lower()
    generic_variants: list[str] = []
    first_informative_token = next(
        (
            token
            for token in tokens
            if token.lower() not in GENERIC_QUERY_SKIP_TOKENS
            and token.isalpha()
            and len(token) >= 3
        ),
        "",
    )

    for term in GENERIC_HARDWARE_TERMS:
        if term not in normalized_query:
            continue
        generic_variants.append(term)
        if first_informative_token and first_informative_token.lower() not in term:
            generic_variants.append(f"{first_informative_token} {term}")

    return generic_variants


def price_from_money_payload(value: Any) -> Decimal | None:
    if not isinstance(value, dict):
        return parse_price(value)
    amount = value.get("cent_amount")
    fraction = value.get("fraction") or 100
    if amount is None:
        return None
    try:
        return (Decimal(str(amount)) / Decimal(str(fraction))).quantize(Decimal("0.01"))
    except Exception:
        return None


def extract_first_price(prices: Any) -> Decimal | None:
    if not isinstance(prices, list):
        return None
    preferred = [
        row for row in prices
        if isinstance(row, dict) and row.get("type") in {"PRICE_INCL_TAX", "SPECIAL_PRICE", "SELLING_PRICE"}
    ]
    for row in [*preferred, *prices]:
        if not isinstance(row, dict):
            continue
        price = price_from_money_payload(row.get("price"))
        if price is not None:
            return price
    return None


def availability_from_text(*parts: str | None) -> str:
    text = " ".join(part or "" for part in parts).lower()
    if "out of stock" in text or "unavailable" in text or "sold out" in text:
        return "out_of_stock"
    if "preorder" in text or "pre-order" in text:
        return "preorder"
    return "in_stock"
