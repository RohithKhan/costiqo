from __future__ import annotations

import re

from app.utils.price_parser import parse_price


def infer_delivery_days(delivery_info: str | None) -> int | None:
    if not delivery_info:
        return None

    normalized = delivery_info.lower()
    if "same day" in normalized or "same-day" in normalized:
        return 0
    if "tomorrow" in normalized:
        return 1
    if "next day" in normalized or "next-day" in normalized:
        return 1
    if "today" in normalized:
        return 0

    day_match = re.search(r"(\d+)\s*day", normalized)
    if day_match:
        return int(day_match.group(1))

    return None


def infer_shipping_cost(delivery_info: str | None) -> float | None:
    if not delivery_info:
        return None

    normalized = delivery_info.lower()
    if "free delivery" in normalized or "free shipping" in normalized:
        return 0.0

    currency_match = re.search(
        r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d{1,2})?)|([\d,]+(?:\.\d{1,2})?)\s*(?:₹|rs\.?|inr)",
        normalized,
    )
    if currency_match is None:
        return None

    raw_amount = currency_match.group(1) or currency_match.group(2)
    parsed = parse_price(raw_amount)
    return float(parsed) if parsed is not None else None
