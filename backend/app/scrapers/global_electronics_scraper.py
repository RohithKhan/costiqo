from __future__ import annotations

import asyncio
import json
import re
from typing import Any
from urllib.parse import quote_plus

from app.scrapers.base import BaseScraper, ScrapedListing, ScrapedReview, SearchContext
from app.scrapers.hardware_scraper_utils import (
    availability_from_text,
    build_listing,
    coerce_text,
    fetch_html,
    query_variants,
)


class GlobalElectronicsScraper(BaseScraper):
    vendor_name = "Global Electronics"
    base_url = "https://www.globalelectronics.in"
    scrape_strategy = "live-http-wix"
    user_agent = "curl/8.7.1"
    timeout_seconds = 8
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
            f"{self.base_url}/all-products?q={quote_plus(primary_query)}",
            timeout_seconds=self.timeout_seconds,
            user_agent=self.user_agent,
        )
        listings = self._build_live_listings(query, html)
        if listings:
            return listings

        # Fallback variants: run concurrently
        remaining = variants[1:3]
        if remaining:
            tasks = [
                fetch_html(
                    f"{self.base_url}/all-products?q={quote_plus(variant)}",
                    timeout_seconds=self.timeout_seconds,
                    user_agent=self.user_agent,
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
        for product in self._extract_products(html):
            product_path = coerce_text(product.get("urlPart"))
            listing = build_listing(
                self,
                query,
                title=coerce_text(product.get("name")),
                product_url=f"{self.base_url}/product-page/{product_path}" if product_path else "",
                price=product.get("price") or product.get("formattedPrice"),
                raw_price=coerce_text(product.get("formattedPrice")) or None,
                image_url=self._image_url(product),
                brand=self._brand_from_sku(product),
                category=self._category(product),
                model_number=coerce_text(product.get("sku")) or None,
                availability_status=(
                    "in_stock"
                    if product.get("isInStock") is True
                    else availability_from_text(coerce_text(product.get("inventory")))
                ),
                raw_payload=product,
            )
            if listing is None or listing.product_url in seen_urls:
                continue
            seen_urls.add(listing.product_url)
            listings.append(listing)
            if len(listings) >= self.max_results:
                break
        return listings

    def _extract_products(self, html: str) -> list[dict[str, Any]]:
        decoder = json.JSONDecoder()
        products: list[dict[str, Any]] = []
        for match in re.finditer(r'\{"id":"[^"]+".{0,500}?"productType":"physical"', html):
            try:
                value, _ = decoder.raw_decode(html[match.start():])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and value.get("productType") == "physical":
                products.append(value)
        return products

    def _image_url(self, product: dict[str, Any]) -> str:
        media = product.get("media")
        if isinstance(media, list) and media:
            first = media[0]
            if isinstance(first, dict):
                return coerce_text(first.get("fullUrl") or first.get("url"))
        return ""

    def _brand_from_sku(self, product: dict[str, Any]) -> str | None:
        sku = coerce_text(product.get("sku"))
        if not sku:
            return None
        return sku.split()[0]

    def _category(self, product: dict[str, Any]) -> str | None:
        category = product.get("category")
        if isinstance(category, dict):
            return coerce_text(category.get("name")) or None
        return None
