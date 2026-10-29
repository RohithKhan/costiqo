from __future__ import annotations

import logging

from fastapi import HTTPException, status

from app.scrapers.base import SearchContext
from app.utils.india_pincode import normalize_indian_pincode, resolve_indian_pincode


logger = logging.getLogger(__name__)


class SearchContextService:
    async def build(
        self,
        *,
        location: str | None = None,
        pincode: str | None = None,
    ) -> SearchContext:
        normalized_location = _normalize_location(location)

        try:
            normalized_pincode = normalize_indian_pincode(pincode)
        except ValueError as exc:
            logger.info(
                "comparison_ignoring_invalid_pincode pincode=%s error=%s",
                pincode,
                exc,
            )
            normalized_pincode = None

        resolved_location = None
        if normalized_pincode:
            try:
                details = await resolve_indian_pincode(normalized_pincode)
            except ValueError as exc:
                if not _is_transient_pincode_lookup_error(str(exc)):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=str(exc),
                    ) from exc
                logger.warning(
                    "pincode_lookup_unavailable pincode=%s location=%s error=%s",
                    normalized_pincode,
                    normalized_location,
                    exc,
                )
            else:
                resolved_location = details.location_label

        return SearchContext(
            location=normalized_location or resolved_location,
            pincode=normalized_pincode,
            resolved_location=resolved_location,
        )

    async def verify_pincode(self, pincode: str) -> dict[str, str | None]:
        try:
            normalized_pincode = normalize_indian_pincode(pincode)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

        if not normalized_pincode:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pincode must be a valid 6-digit Indian PIN code.",
            )

        try:
            details = await resolve_indian_pincode(normalized_pincode)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

        return {
            "pincode": details.pincode,
            "district": details.district,
            "state": details.state,
            "office_name": details.office_name,
            "location": details.location_label,
        }


def _normalize_location(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split()).strip()
    return normalized or None


def _is_transient_pincode_lookup_error(message: str) -> bool:
    normalized = message.strip().lower()
    return (
        normalized.startswith("unable to verify the indian pincode")
        or "verification service returned invalid data" in normalized
        or "verification service returned an unexpected response" in normalized
        or "verification did not return district/state details" in normalized
    )
