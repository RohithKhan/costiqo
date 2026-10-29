from datetime import datetime, timezone

from app.utils.product_page_validation import (
    extract_current_product_price,
    is_probable_product_page_url,
)
from app.services.offer_verification_service import OfferVerificationService


def test_build_result_marks_verified_when_store_price_matches():
    service = OfferVerificationService()

    result = service._build_result(
        expected_price=58190.0,
        verified_price=58190.0,
        checked_at=datetime(2026, 4, 28, 12, 0, 0, tzinfo=timezone.utc),
    )

    assert result is not None
    assert result.status == "verified"
    assert result.confidence == 1.0


def test_build_result_marks_mismatch_when_store_price_differs():
    service = OfferVerificationService()

    result = service._build_result(
        expected_price=58190.0,
        verified_price=61999.0,
        checked_at=datetime(2026, 4, 28, 12, 0, 0, tzinfo=timezone.utc),
    )

    assert result is not None
    assert result.status == "mismatch_detected"
    assert result.verified_price == 61999.0


def test_extract_price_candidate_prefers_exact_match_from_rendered_text():
    service = OfferVerificationService()
    text = "Apple iPhone 15\n₹58,190\nMRP ₹59,900\nEMI from ₹2,702"

    result = service._extract_price_candidate(text, expected_price=58190.0)

    assert result == 58190.0


def test_product_page_price_extractor_rejects_emi_before_current_price():
    text = "EMI from ₹2,702 per month\nCurrent price ₹58,190\nMRP ₹59,900"

    result = extract_current_product_price(text, expected_price=58190.0)

    assert result == 58190.0


def test_product_page_price_extractor_accepts_rs_prefix_prices():
    text = "Product price\nRs.54.00\nMRP Rs.99.00\nEMI not available"

    result = extract_current_product_price(text, expected_price=54.0)

    assert result == 54.0


def test_product_page_url_validator_rejects_basic_and_search_urls():
    assert is_probable_product_page_url("https://www.amazon.in/dp/B0ABCDEF12")
    assert is_probable_product_page_url("https://www.electronicscomp.com/1000uf-16v-smd-electrolytic-capacitor")
    assert is_probable_product_page_url(
        "https://www.poorvika.com/samsung-galaxy-s24-5g-cobalt-violet-128gb-8gb-ram/p"
    )
    assert not is_probable_product_page_url("https://www.amazon.in/")
    assert not is_probable_product_page_url("https://example.com/p")
    assert not is_probable_product_page_url("https://www.croma.com/search?q=iphone")
    assert not is_probable_product_page_url("https://www.google.com/shopping/product/123")
