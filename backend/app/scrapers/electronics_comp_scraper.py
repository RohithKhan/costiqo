from __future__ import annotations

import asyncio
from html import unescape
import re
from urllib.parse import quote_plus

from app.scrapers.base import BaseScraper, ScrapedListing, ScrapedReview, SearchContext
from app.scrapers.hardware_scraper_utils import availability_from_text, build_listing, coerce_text, fetch_html, query_variants


class ElectronicsCompScraper(BaseScraper):
    vendor_name = "ElectronicsComp"
    base_url = "https://www.electronicscomp.com"
    scrape_strategy = "live-http-opencart"
    timeout_seconds = 12
    max_results = 24

    async def search(
        self,
        query: str,
        context: SearchContext | None = None,
    ) -> list[ScrapedListing]:
        variants = query_variants(query)
        if not variants:
            return []

        # Primary query fast path
        primary_query = variants[0]
        html = await fetch_html(
            f"{self.base_url}/index.php?route=product/search&search={quote_plus(primary_query)}",
            timeout_seconds=self.timeout_seconds,
        )
        listings = self._build_live_listings(query, html)
        if listings:
            return listings

        # Fallback variants: run concurrently
        remaining = variants[1:3]
        if remaining:
            tasks = [
                fetch_html(
                    f"{self.base_url}/index.php?route=product/search&search={quote_plus(variant)}",
                    timeout_seconds=self.timeout_seconds,
                )
                for variant in remaining
            ]
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            for resp in responses:
                if isinstance(resp, str):
                    listings = self._build_live_listings(query, resp)
                    if listings:
                        return listings
        return []

    async def fetch_reviews(self, product_url: str) -> list[ScrapedReview]:
        return []

    def _build_live_listings(self, query: str, html: str) -> list[ScrapedListing]:
        listings: list[ScrapedListing] = []
        seen_urls: set[str] = set()

        for block in re.split(r'<div class="product-layout product-list col-xs-12">', html)[1:]:
            title_match = re.search(
                r"<h4>\s*<a\s+href=\"(?P<url>[^\"]+)\">(?P<title>.*?)</a>\s*</h4>",
                block,
                re.DOTALL | re.IGNORECASE,
            )
            if title_match is None:
                continue

            image_match = re.search(r"<img\s+src=\"(?P<src>[^\"]+)\"", block, re.IGNORECASE)
            price_match = re.search(
                r'<p\s+class="price">\s*(?P<price>.*?)\s*</p>',
                block,
                re.DOTALL | re.IGNORECASE,
            )

            raw_price = _clean_price(price_match.group("price")) if price_match else ""
            listing = build_listing(
                self,
                query,
                title=_clean_html(title_match.group("title")),
                product_url=title_match.group("url"),
                price=raw_price,
                raw_price=raw_price or None,
                image_url=image_match.group("src") if image_match else None,
                availability_status=availability_from_text(block),
            )
            if listing is None or listing.product_url in seen_urls:
                continue
            seen_urls.add(listing.product_url)
            listings.append(listing)
            if len(listings) >= self.max_results:
                break

        return listings


def _clean_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    return coerce_text(unescape(text))


def _clean_price(value: str) -> str:
    return re.sub(r"\bRs\.\s*", "Rs ", _clean_html(value), flags=re.IGNORECASE)
