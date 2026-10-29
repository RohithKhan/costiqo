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
    extract_first_price,
    fetch_html,
    query_variants,
)


class IboScraper(BaseScraper):
    vendor_name = "IBO"
    base_url = "https://www.ibo.com"
    scrape_strategy = "live-http-next"
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
            f"{self.base_url}/search?search_term={quote_plus(primary_query)}",
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
                    f"{self.base_url}/search?search_term={quote_plus(variant)}",
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
        for product in self._extract_products(html):
            product_path = coerce_text(product.get("product_url"))
            listing = build_listing(
                self,
                query,
                title=coerce_text(product.get("display_name") or product.get("name")),
                product_url=f"{self.base_url}/{product_path.lstrip('/')}" if product_path else "",
                price=extract_first_price(product.get("prices")),
                image_url=(product.get("media") or {}).get("primary_image_url")
                if isinstance(product.get("media"), dict)
                else None,
                brand=self._facet_value(product, "brand") or None,
                category=self._facet_value(product, "category") or None,
                model_number=coerce_text(product.get("esin") or product.get("sku")) or None,
                delivery_info=coerce_text((product.get("earliest_delivery_date") or {}).get("label"))
                if isinstance(product.get("earliest_delivery_date"), dict)
                else None,
                availability_status=availability_from_text(coerce_text(product.get("stock_status"))),
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
        match = re.search(
            r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )
        if match is None:
            return []
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            return []
        props = payload.get("props") if isinstance(payload.get("props"), dict) else {}
        first_page_props = props.get("pageProps") if isinstance(props.get("pageProps"), dict) else {}
        second_page_props = (
            first_page_props.get("pageProps")
            if isinstance(first_page_props.get("pageProps"), dict)
            else {}
        )
        data = second_page_props.get("data") if isinstance(second_page_props.get("data"), dict) else {}
        search_results = data.get("searchResults") if isinstance(data.get("searchResults"), dict) else {}
        products = search_results.get("products", [])
        return [item for item in products if isinstance(item, dict)]

    def _facet_value(self, product: dict[str, Any], key_fragment: str) -> str:
        for attribute in product.get("attributes") or []:
            if not isinstance(attribute, dict):
                continue
            code = coerce_text(attribute.get("attribute_code") or attribute.get("name")).lower()
            if key_fragment not in code:
                continue
            value = attribute.get("value") or attribute.get("label")
            return coerce_text(value)
        return ""
