from __future__ import annotations

import asyncio
import json
import ssl
from dataclasses import dataclass
from json import JSONDecodeError
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import certifi


PINCODE_API_URL = "https://api.postalpincode.in/pincode"
PINCODE_CACHE_TTL_SECONDS = 60 * 60 * 12
LOCATION_ALIASES = {
    "bangalore": "Bengaluru",
    "bombay": "Mumbai",
    "calcutta": "Kolkata",
    "gurgaon": "Gurugram",
}


@dataclass(slots=True, frozen=True)
class PincodeDetails:
    pincode: str
    district: str
    state: str
    office_name: str | None = None
    country: str = "India"

    @property
    def location_label(self) -> str:
        parts = [_normalize_location_name(self.district), self.state, self.country]
        return ", ".join(part for part in parts if part)


_pincode_cache: dict[str, tuple[float, PincodeDetails]] = {}


def normalize_indian_pincode(value: str | None) -> str | None:
    if value is None:
        return None
    digits_only = "".join(character for character in value if character.isdigit())
    if not digits_only:
        return None
    if len(digits_only) != 6 or digits_only.startswith("0"):
        raise ValueError("Pincode must be a valid 6-digit Indian PIN code.")
    return digits_only


async def resolve_indian_pincode(pincode: str) -> PincodeDetails:
    cached = _pincode_cache.get(pincode)
    if cached and monotonic() - cached[0] < PINCODE_CACHE_TTL_SECONDS:
        return cached[1]

    details = await asyncio.to_thread(_fetch_pincode_details, pincode)
    _pincode_cache[pincode] = (monotonic(), details)
    return details


def _fetch_pincode_details(pincode: str) -> PincodeDetails:
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    try:
        with urlopen(f"{PINCODE_API_URL}/{pincode}", timeout=20, context=ssl_context) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise ValueError("Unable to verify the Indian pincode right now.") from exc
    except URLError as exc:
        raise ValueError(f"Unable to verify the Indian pincode: {exc.reason}") from exc
    except JSONDecodeError as exc:
        raise ValueError("Pincode verification service returned invalid data.") from exc

    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        raise ValueError("Pincode verification service returned an unexpected response.")

    result = payload[0]
    if str(result.get("Status")).lower() != "success":
        raise ValueError("Pincode was not recognized as a valid Indian delivery area.")

    office_rows = result.get("PostOffice")
    if not isinstance(office_rows, list) or not office_rows:
        raise ValueError("Pincode was not recognized as a valid Indian delivery area.")

    office = next((row for row in office_rows if isinstance(row, dict)), None)
    if office is None:
        raise ValueError("Pincode was not recognized as a valid Indian delivery area.")

    district = _coerce_text(office.get("District"))
    state = _coerce_text(office.get("State"))
    office_name = _coerce_text(office.get("Name"))
    if not district or not state:
        raise ValueError("Pincode verification did not return district/state details.")

    return PincodeDetails(
        pincode=pincode,
        district=district,
        state=state,
        office_name=office_name,
    )


def _coerce_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_location_name(value: str) -> str:
    return LOCATION_ALIASES.get(value.strip().lower(), value)
