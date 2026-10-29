from decimal import Decimal

import pytest

from app.scrapers.base import ScrapedListing
from app.services.candidate_validation_service import CandidateValidationService


def _listing(name: str, *, price: str = "999") -> ScrapedListing:
    return ScrapedListing(
        vendor="TestVendor",
        base_url="https://example.com",
        scrape_strategy="test",
        canonical_name=name,
        brand="",
        category="Networking",
        model_number="",
        image_url="",
        vendor_product_name=name,
        product_url=f"https://example.com/{name.lower().replace(' ', '-')}",
        price=Decimal(price),
        raw_price=f"₹{price}",
    )


def test_candidate_validation_parses_compact_openrouter_rows():
    service = CandidateValidationService(enabled=False)
    listing = _listing("Apple iPhone 15 (Black, 128 GB)")

    rows = service._validation_rows({"c": [[0, True, "exact_match", 0.95]]})
    assert rows == [[0, True, "exact_match", 0.95]]

    result = service._coerce_result(rows[0], {0: listing})

    assert result is not None
    assert result.index == 0
    assert result.is_match is True
    assert result.relation == "exact_match"
    assert result.accepted
    assert result.confidence == 0.95
    assert result.canonical_product == "Apple iPhone 15 (Black, 128 GB)"
    assert result.source == "openrouter"


def test_candidate_validation_still_parses_legacy_compact_openrouter_rows():
    service = CandidateValidationService(enabled=False)
    listing = _listing("Apple iPhone 15 (Black, 128 GB)")

    rows = service._validation_rows({"c": [[0, "exact_match", 0.95]]})
    assert rows == [[0, "exact_match", 0.95]]

    result = service._coerce_result(rows[0], {0: listing})

    assert result is not None
    assert result.index == 0
    assert result.is_match is None
    assert result.relation == "exact_match"
    assert result.accepted


def test_candidate_validation_still_parses_verbose_openrouter_rows():
    service = CandidateValidationService(enabled=False)

    rows = service._validation_rows(
        {
            "candidates": [
                {
                    "index": 1,
                    "is_match": False,
                    "relation": "unrelated",
                    "confidence": 0.88,
                    "canonical_product": "Cabinet hinge",
                    "reason": "Not a phone",
                }
            ]
        }
    )
    assert rows is not None

    result = service._coerce_result(rows[0])

    assert result is not None
    assert result.index == 1
    assert result.is_match is False
    assert result.relation == "unrelated"
    assert not result.accepted
    assert result.reason == "Not a phone"


@pytest.mark.asyncio
async def test_candidate_validation_fallback_treats_requested_adapter_as_product():
    service = CandidateValidationService(enabled=False)

    results = await service.validate(
        "wifi adapter",
        [
            _listing("TP-Link USB WiFi Adapter"),
            _listing("TP-Link WiFi Router"),
        ],
    )

    assert results[0].relation == "exact_match"
    assert results[0].accepted
    assert results[0].canonical_product == "TP-Link USB WiFi Adapter"
    assert results[1].accepted


@pytest.mark.asyncio
async def test_candidate_validation_fallback_excludes_unrelated_candidates():
    service = CandidateValidationService(enabled=False)

    results = await service.validate(
        "daikin ac",
        [
            _listing("TP-Link USB WiFi Adapter"),
        ],
    )

    assert results[0].relation == "unrelated"
    assert not results[0].accepted


@pytest.mark.asyncio
async def test_candidate_validation_fallback_classifies_unrequested_related_item():
    service = CandidateValidationService(enabled=False)

    results = await service.validate(
        "daikin ac",
        [
            _listing(
                "7SEVEN Compatible Daikin AC Remote Original ARC470A25 "
                "Suitable for Split and Window Air Conditioner"
            ),
        ],
    )

    assert results[0].relation == "compatible_accessory_or_part"
    assert results[0].accepted


@pytest.mark.asyncio
async def test_candidate_validation_rejects_numeric_only_overlap():
    service = CandidateValidationService(enabled=False)

    results = await service.validate(
        "iphone 15",
        [
            _listing("Godrej 7215 Inset / 15 Crank Regular Close Cabinet Hinge", price="63"),
            _listing("Traveler Multifunction Knife 15 in 1", price="199"),
        ],
    )

    assert results[0].relation == "unrelated"
    assert not results[0].accepted
    assert results[1].relation == "unrelated"
    assert not results[1].accepted


@pytest.mark.asyncio
async def test_candidate_validation_rejects_category_alternative_for_precise_model_query():
    service = CandidateValidationService(enabled=False)

    results = await service.validate(
        "iphone 15",
        [
            _listing("Apple iPhone 11 64GB Black Smartphone", price="29999"),
            _listing("Apple iPhone 15 128GB Black Smartphone", price="58990"),
        ],
    )

    assert results[0].relation == "unrelated"
    assert not results[0].accepted
    assert results[1].accepted


@pytest.mark.asyncio
async def test_candidate_validation_accepts_brand_family_model_titles():
    service = CandidateValidationService(enabled=False)

    results = await service.validate(
        "samsung s25",
        [
            _listing("Samsung Galaxy S25 5G 128 GB Mobile Phone", price="56999"),
            _listing("Samsung Galaxy S25 Ultra 5G 256 GB Mobile Phone", price="94999"),
            _listing("Samsung Galaxy S24 5G 128 GB Mobile Phone", price="44999"),
        ],
    )

    assert results[0].accepted
    assert results[1].accepted
    assert results[2].relation == "unrelated"
    assert not results[2].accepted
