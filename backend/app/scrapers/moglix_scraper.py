from __future__ import annotations

import asyncio
import json
import re
from typing import Any
from urllib.parse import quote_plus

from app.scrapers.base import BaseScraper, ScrapedListing, ScrapedReview, SearchContext
from app.scrapers.hardware_scraper_utils import build_listing, coerce_text, fetch_html, query_variants


class MoglixScraper(BaseScraper):
    vendor_name = "Moglix"
    base_url = "https://www.moglix.com"
    scrape_strategy = "live-http-ssr"
    timeout_seconds = 20
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
            f"{self.base_url}/search?search_query={quote_plus(primary_query)}",
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
                    f"{self.base_url}/search?search_query={quote_plus(variant)}",
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
        for document in self._extract_products(html):
            product_url = coerce_text(document.get("productUrl"))
            if product_url:
                product_url = f"{self.base_url}/{product_url.lstrip('/')}"
            listing = build_listing(
                self,
                query,
                title=coerce_text(document.get("productName") or document.get("variantName")),
                product_url=product_url,
                price=document.get("salesPrice") or document.get("priceWithoutTax") or document.get("mrp"),
                raw_price=(
                    f"₹{document.get('salesPrice'):,.0f}"
                    if isinstance(document.get("salesPrice"), (int, float))
                    else None
                ),
                image_url=self._image_url(document),
                brand=coerce_text(document.get("brandName")) or None,
                category=self._category(document),
                model_number=coerce_text(document.get("moglixPartNumber"))
                or coerce_text(document.get("itemCode"))
                or None,
                rating=document.get("avgRating") or document.get("rating"),
                review_count=document.get("reviewCount") or document.get("ratingCount"),
                delivery_info=coerce_text(document.get("eta")) or None,
                availability_status=(
                    "in_stock"
                    if (document.get("quantityAvailable") or 0) > 0 and document.get("isActive", True)
                    else "out_of_stock"
                ),
                raw_payload=document,
            )
            if listing is None or listing.product_url in seen_urls:
                continue
            seen_urls.add(listing.product_url)
            listings.append(listing)
            if len(listings) >= self.max_results:
                break
        return listings

    def _extract_products(self, html: str) -> list[dict[str, Any]]:
        decoded = (
            html.replace("&q;", '"')
            .replace("&a;", "&")
            .replace("\\u0026", "&")
        )
        decoder = json.JSONDecoder()
        products: list[dict[str, Any]] = []
        for match in re.finditer(r'\{"moglixPartNumber"\s*:', decoded):
            try:
                value, _ = decoder.raw_decode(decoded[match.start():])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                products.append(value)
        return products

    def _category(self, document: dict[str, Any]) -> str | None:
        names = document.get("categoryNames") or document.get("taxonomyName")
        if isinstance(names, list) and names:
            return coerce_text(names[-1]) or None
        return None

    def _image_url(self, document: dict[str, Any]) -> str:
        for key in ("mainImageLink", "mainImageMediumLink", "mainImagePath"):
            value = coerce_text(document.get(key))
            if not value:
                continue
            if value.startswith("http://") or value.startswith("https://"):
                return value
            return f"https://cdn.moglix.com/{value.lstrip('/')}"
        return ""
