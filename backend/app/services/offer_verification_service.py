from __future__ import annotations

import asyncio
from collections.abc import Sequence
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urljoin

import httpx

from app.core.config import TRUSTED_VENDOR_DOMAINS
from app.schemas.product import VendorListingSummary
from app.utils.product_page_validation import extract_current_product_price
from app.utils.time_utils import utc_now
from app.utils.url_safety import is_safe_url, validate_safe_url


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class OfferVerificationResult:
    status: str
    confidence: float
    verified_price: float | None
    checked_at: datetime


@dataclass(slots=True)
class _CachedVerification:
    result: OfferVerificationResult | None
    expires_at: datetime


class OfferVerificationService:
    STRUCTURED_PRICE_PATTERNS = (
        re.compile(r'"price"\s*:\s*"?(?P<amount>\d[\d,]*(?:\.\d+)?)', re.IGNORECASE),
        re.compile(r'product:price:amount"\s+content="(?P<amount>\d[\d,]*(?:\.\d+)?)', re.IGNORECASE),
        re.compile(r'sellingPrice[^0-9]{0,80}(?P<amount>\d[\d,]*(?:\.\d+)?)', re.IGNORECASE),
        re.compile(r'finalPrice[^0-9]{0,80}(?P<amount>\d[\d,]*(?:\.\d+)?)', re.IGNORECASE),
        re.compile(r'currentPrice[^0-9]{0,80}(?P<amount>\d[\d,]*(?:\.\d+)?)', re.IGNORECASE),
    )
    RENDERED_PRICE_PATTERN = re.compile(r"₹\s*(\d[\d,]*(?:\.\d+)?)")
    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
    MAX_REDIRECTS = 3
    MAX_RESPONSE_BYTES = 2 * 1024 * 1024

    def __init__(
        self,
        *,
        enabled: bool = True,
        timeout_seconds: int = 8,
        cache_ttl_seconds: int = 900,
        max_offers: int = 2,
        trusted_vendor_domains: Sequence[str] | None = None,
    ) -> None:
        self.enabled = enabled
        self.timeout_seconds = timeout_seconds
        self.cache_ttl_seconds = cache_ttl_seconds
        self.max_offers = max_offers
        self.trusted_vendor_domains: tuple[str, ...] = (
            tuple(trusted_vendor_domains)
            if trusted_vendor_domains is not None
            else TRUSTED_VENDOR_DOMAINS
        )
        self._cache: dict[str, _CachedVerification] = {}

    def configure(
        self,
        *,
        enabled: bool | None = None,
        timeout_seconds: int | None = None,
        cache_ttl_seconds: int | None = None,
        max_offers: int | None = None,
        trusted_vendor_domains: Sequence[str] | None = None,
    ) -> None:
        if enabled is not None:
            self.enabled = enabled
        if timeout_seconds is not None:
            self.timeout_seconds = timeout_seconds
        if cache_ttl_seconds is not None:
            self.cache_ttl_seconds = cache_ttl_seconds
        if max_offers is not None:
            self.max_offers = max_offers
        if trusted_vendor_domains is not None:
            self.trusted_vendor_domains = tuple(trusted_vendor_domains)


    async def verify_vendor_summaries(
        self,
        listings: list[VendorListingSummary],
    ) -> dict[int, OfferVerificationResult]:
        if not self.enabled:
            return {}

        candidates = sorted(
            [
                listing
                for listing in listings
                if listing.product_url and not listing.product_url.startswith("#")
            ],
            key=lambda listing: listing.current_price,
        )[: self.max_offers]
        if not candidates:
            return {}

        results = await asyncio.gather(
            *(self._verify_listing(listing) for listing in candidates)
        )
        return {
            listing.id: result
            for listing, result in zip(candidates, results)
            if result is not None
        }

    async def _verify_listing(
        self,
        listing: VendorListingSummary,
    ) -> OfferVerificationResult | None:
        cached = self._cache.get(listing.product_url)
        now = utc_now()
        if cached is not None and cached.expires_at > now:
            return cached.result

        verified_price = await self._fetch_verified_price(
            listing.product_url,
            expected_price=listing.current_price,
        )
        result = self._build_result(
            expected_price=listing.current_price,
            verified_price=verified_price,
            checked_at=now,
        )
        self._cache[listing.product_url] = _CachedVerification(
            result=result,
            expires_at=now + timedelta(seconds=self.cache_ttl_seconds),
        )
        return result

    def _build_result(
        self,
        *,
        expected_price: float,
        verified_price: float | None,
        checked_at: datetime,
    ) -> OfferVerificationResult | None:
        if verified_price is None:
            return None
        if abs(verified_price - expected_price) <= 1.0:
            logger.info(
                "verification_match expected_price=%.2f verified_price=%.2f",
                expected_price,
                verified_price,
            )
            return OfferVerificationResult(
                status="verified",
                confidence=1.0,
                verified_price=verified_price,
                checked_at=checked_at,
            )
        logger.warning(
            "verification_mismatch expected_price=%.2f verified_price=%.2f",
            expected_price,
            verified_price,
        )
        return OfferVerificationResult(
            status="mismatch_detected",
            confidence=0.0,
            verified_price=verified_price,
            checked_at=checked_at,
        )

    async def _fetch_verified_price(
        self,
        url: str,
        *,
        expected_price: float,
    ) -> float | None:
        html = await self._fetch_page_html(url)
        candidate = self._extract_price_candidate(html or "", expected_price=expected_price)
        if candidate is not None:
            return candidate

        rendered_text = await self._fetch_rendered_text(url)
        return self._extract_price_candidate(
            rendered_text or "",
            expected_price=expected_price,
        )

    async def _fetch_page_html(self, url: str) -> str | None:
        is_safe, reason = validate_safe_url(url, allowed_domains=self.trusted_vendor_domains)
        if not is_safe:
            logger.warning("verification_fetch_blocked reason=%s", reason)
            return None

        headers = {
            "user-agent": self.USER_AGENT,
            "accept-language": "en-IN,en;q=0.9",
        }

        current_url = url
        timeout = httpx.Timeout(float(self.timeout_seconds), connect=min(4.0, float(self.timeout_seconds)))
        try:
            async with httpx.AsyncClient(
                follow_redirects=False,
                headers=headers,
                timeout=timeout,
            ) as client:
                for _ in range(self.MAX_REDIRECTS + 1):
                    is_safe, reason = validate_safe_url(
                        current_url,
                        allowed_domains=self.trusted_vendor_domains,
                    )
                    if not is_safe:
                        logger.warning("verification_redirect_blocked reason=%s", reason)
                        return None

                    response = await client.get(current_url)

                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            logger.warning("verification_redirect_missing_location")
                            return None
                        current_url = urljoin(current_url, location)
                        continue

                    if response.status_code >= 400:
                        logger.warning(
                            "verification_fetch_status_failure status_code=%s",
                            response.status_code,
                        )
                        return None

                    content_length = response.headers.get("content-length")
                    if content_length and int(content_length) > self.MAX_RESPONSE_BYTES:
                        logger.warning("verification_response_exceeds_size_limit")
                        return None

                    text = response.text
                    if len(text.encode("utf-8", errors="ignore")) > self.MAX_RESPONSE_BYTES:
                        text = text[: self.MAX_RESPONSE_BYTES]
                    return text

                logger.warning("verification_max_redirects_exceeded")
                return None
        except httpx.HTTPError as exc:
            logger.warning("verification_fetch_failed error_type=%s", type(exc).__name__)
            return None
        except Exception:
            logger.warning("verification_fetch_unexpected_error")
            return None

    async def _fetch_rendered_text(self, url: str) -> str | None:
        is_safe, reason = validate_safe_url(url, allowed_domains=self.trusted_vendor_domains)
        if not is_safe:
            logger.warning("verification_render_blocked reason=%s", reason)
            return None

        try:
            from playwright.async_api import Error as PlaywrightError
            from app.scrapers.live_utils import _get_browser
        except Exception:
            return None

        try:
            browser = await _get_browser()
            context = await browser.new_context(
                user_agent=self.USER_AGENT,
                locale="en-IN",
            )
            try:
                async def _route_guard(route):
                    try:
                        request = route.request
                        if request.resource_type in {"image", "media", "font"}:
                            await route.abort()
                            return

                        req_url = request.url
                        if request.is_navigation_request():
                            req_safe, _ = validate_safe_url(
                                req_url,
                                allowed_domains=self.trusted_vendor_domains,
                            )
                            if not req_safe:
                                logger.warning("playwright_navigation_blocked")
                                await route.abort()
                                return
                        else:
                            req_safe, _ = validate_safe_url(
                                req_url,
                                allowed_domains=None,
                            )
                            if not req_safe:
                                logger.warning("playwright_subresource_blocked")
                                await route.abort()
                                return

                        await route.continue_()
                    except Exception:
                        await route.abort()

                await context.route("**/*", _route_guard)
                page = await context.new_page()
                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=self.timeout_seconds * 1000,
                )
                await page.wait_for_timeout(1200)

                if not is_safe_url(page.url, allowed_domains=self.trusted_vendor_domains):
                    logger.warning("playwright_final_url_untrusted")
                    return None

                return await page.locator("body").inner_text()
            finally:
                try:
                    await asyncio.shield(context.close())
                except Exception:
                    pass
        except (PlaywrightError, TimeoutError, Exception):
            return None
            logger.warning("verification_render_failed reason=playwright_timeout_or_error")
            return None
        except Exception:
            logger.warning("verification_render_failed reason=unexpected_error")
            return None


    def _extract_price_candidate(
        self,
        text: str,
        *,
        expected_price: float,
    ) -> float | None:
        return extract_current_product_price(text, expected_price=expected_price)

    def _extract_structured_candidates(self, text: str) -> list[float]:
        candidates: list[float] = []
        seen: set[float] = set()
        for pattern in self.STRUCTURED_PRICE_PATTERNS:
            for match in pattern.finditer(text):
                amount = self._parse_amount(match.group("amount"))
                if amount is None or amount in seen:
                    continue
                seen.add(amount)
                candidates.append(amount)
        return candidates

    def _extract_rendered_candidates(self, text: str) -> list[float]:
        candidates: list[float] = []
        seen: set[float] = set()
        for match in self.RENDERED_PRICE_PATTERN.finditer(text[:12000]):
            amount = self._parse_amount(match.group(1))
            if amount is None or amount in seen:
                continue
            seen.add(amount)
            candidates.append(amount)
        return candidates

    def _find_expected_match(
        self,
        candidates: list[float],
        expected_price: float,
    ) -> float | None:
        for candidate in candidates:
            if abs(candidate - expected_price) <= 1.0:
                return candidate
        return None

    def _parse_amount(self, raw_amount: str | None) -> float | None:
        if not raw_amount:
            return None
        try:
            amount = float(raw_amount.replace(",", "").strip())
        except ValueError:
            return None
        if amount <= 0:
            return None
        if amount < 100:
            return None
        return amount
