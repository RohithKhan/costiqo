from decimal import Decimal, InvalidOperation
import re


def parse_price(value: str | int | float | Decimal | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"))
    if isinstance(value, (int, float)):
        return Decimal(str(value)).quantize(Decimal("0.01"))

    cleaned = re.sub(r"[^\d.]", "", value)
    if not cleaned:
        return None
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def format_price_inr(value: Decimal | None) -> str:
    if value is None:
        return "N/A"
    return f"₹{value:,.2f}"
