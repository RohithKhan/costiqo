import re


def parse_rating_value(value: str | None) -> float | None:
    if not value:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", value)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def parse_count_value(value: str | None) -> int:
    if not value:
        return 0

    match = re.search(r"(\d+(?:\.\d+)?)\s*([kKmM])?", value.replace(",", ""))
    if not match:
        return 0

    try:
        amount = float(match.group(1))
    except ValueError:
        return 0

    suffix = (match.group(2) or "").lower()
    if suffix == "k":
        amount *= 1_000
    elif suffix == "m":
        amount *= 1_000_000
    return int(amount)
