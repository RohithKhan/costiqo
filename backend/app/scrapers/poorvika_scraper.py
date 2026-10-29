from __future__ import annotations

from decimal import Decimal
from typing import Any
from urllib.parse import urljoin

import httpx

from app.scrapers.base import BaseScraper, PriceHistoryEntry, ScrapedListing, ScrapedReview, SearchContext
from app.scrapers.hardware_scraper_utils import post_json
from app.scrapers.normalizers import listing_matches_query
from app.utils.number_parser import parse_count_value, parse_rating_value
from app.utils.price_parser import parse_price
from app.utils.product_identity import build_product_key, infer_brand, infer_category, normalize_product_name
from app.utils.time_utils import utc_now
from app.utils.vendor_links import canonicalize_vendor_product_url


class PoorvikaScraper(BaseScraper):
    vendor_name = "Poorvika"
    base_url = "https://www.poorvika.com"
    scrape_strategy = "live-typesense"
    search_endpoint = "https://3hskuwtianmdbqoep.a1.typesense.net/multi_search"
    typesense_api_key = "YsItgfKl6Oi2Mj3TtiAZPqoTckK2tiHn"
    timeout_seconds = 12
    max_results = 24

    async def search(
        self,
        query: str,
        context: SearchContext | None = None,
    ) -> list[ScrapedListing]:
        payload = await self._fetch_search_payload(query)
        return self._build_live_listings(query, payload)

    async def fetch_reviews(self, product_url: str) -> list[ScrapedReview]:
        return []

    async def _fetch_search_payload(self, query: str) -> dict[str, Any]:
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "origin": self.base_url,
            "referer": f"{self.base_url}/",
            "user-agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "x-typesense-api-key": self.typesense_api_key,
        }
        payload = await post_json(
            self.search_endpoint,
            payload={"searches": self._build_searches(query)},
            timeout_seconds=self.timeout_seconds,
            extra_headers=headers,
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Poorvika search response was not a JSON object.")
        return payload

    def _build_searches(self, query: str) -> list[dict[str, Any]]:
        base_search = {
            "collection": "productsnew",
            "q": query,
            "num_typos": 3,
            "query_by": "name,categories,item_code,sku",
            "query_by_weights": "4,3,2,1",
            "sort_by": "rating:desc,_text_match:desc",
            "page": 1,
            "filter_by": "sellable:=1 && variant_status:=1 && special_price:>-1",
        }
        return [
            {
                **base_search,
                "per_page": min(self.max_results, 8),
                "group_by": "model_code",
                "group_limit": 1,
            },
            {
                **base_search,
                "per_page": self.max_results,
            },
        ]

    def _build_live_listings(self, query: str, payload: dict[str, Any]) -> list[ScrapedListing]:
        listings: list[ScrapedListing] = []
        seen_urls: set[str] = set()
        now = utc_now()

        for document in self._extract_documents(payload):
            title = normalize_product_name(
                self._coerce_text(document.get("name"))
                or self._coerce_text(document.get("model"))
                or ""
            )
            price_value = parse_price(document.get("special_price")) or parse_price(
                document.get("price")
            )
            product_url = self._build_product_url(document)
            if not title or price_value is None or not product_url:
                continue
            if not listing_matches_query(
                query,
                title,
                self._coerce_text(document.get("model")),
                self._coerce_text(document.get("sku")),
            ):
                continue
            if product_url in seen_urls:
                continue
            seen_urls.add(product_url)

            listings.append(
                ScrapedListing(
                    vendor=self.vendor_name,
                    base_url=self.base_url,
                    scrape_strategy=self.scrape_strategy,
                    canonical_name=title,
                    brand=self._coerce_text(document.get("brand_name"))
                    or infer_brand(title, query),
                    category=infer_category(title, query),
                    model_number=self._coerce_text(document.get("model_code"))
                    or build_product_key(title, query),
                    image_url=self._build_image_url(document),
                    vendor_product_name=title,
                    product_url=product_url,
                    price=price_value,
                    raw_price=self._raw_price(document, price_value),
                    rating=parse_rating_value(self._coerce_text(document.get("rating"))),
                    review_count=parse_count_value(self._coerce_text(document.get("review_count"))),
                    delivery_info=self._coerce_text(document.get("stock_status")),
                    availability_status=self._availability_status(document),
                    price_history=[
                        PriceHistoryEntry(
                            scraped_at=now,
                            price=price_value,
                        )
                    ],
                    raw_payload=document,
                )
            )

        return listings

    def _extract_documents(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        extracted: list[dict[str, Any]] = []
        for result in payload.get("results", []):
            if not isinstance(result, dict):
                continue
            grouped_hits = result.get("grouped_hits")
            if isinstance(grouped_hits, list):
                for group in grouped_hits:
                    if not isinstance(group, dict):
                        continue
                    extracted.extend(self._extract_hit_documents(group.get("hits")))
            extracted.extend(self._extract_hit_documents(result.get("hits")))
        return extracted

    def _extract_hit_documents(self, hits: Any) -> list[dict[str, Any]]:
        if not isinstance(hits, list):
            return []
        documents: list[dict[str, Any]] = []
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            document = hit.get("document") if isinstance(hit.get("document"), dict) else hit
            if isinstance(document, dict):
                documents.append(document)
        return documents

    def _build_product_url(self, document: dict[str, Any]) -> str:
        slug = self._coerce_text(document.get("slug"))
        if slug:
            return canonicalize_vendor_product_url(
                self.vendor_name,
                f"{self.base_url}/{slug}/p",
                self.base_url,
            )

        products_slug = document.get("products_slug")
        if isinstance(products_slug, list):
            for candidate in products_slug:
                candidate_slug = self._coerce_text(candidate)
                if candidate_slug:
                    return canonicalize_vendor_product_url(
                        self.vendor_name,
                        f"{self.base_url}/{candidate_slug}/s",
                        self.base_url,
                    )
        return ""

    def _build_image_url(self, document: dict[str, Any]) -> str:
        image = self._coerce_text(document.get("image"))
        if not image:
            return ""
        if image.startswith("http://") or image.startswith("https://"):
            return image
        return urljoin(f"{self.base_url}/", image.lstrip("/"))

    def _availability_status(self, document: dict[str, Any]) -> str:
        if not self._truthy(document.get("sellable")) or not self._truthy(document.get("variant_status")):
            return "unavailable"

        stock_status = self._coerce_text(document.get("stock_status")).lower()
        if "out of stock" in stock_status or "sold out" in stock_status:
            return "out_of_stock"
        if "pre" in stock_status and "order" in stock_status:
            return "preorder"
        if "coming" in stock_status:
            return "coming_soon"
        return "in_stock"

    def _raw_price(self, document: dict[str, Any], price_value: Decimal) -> str:
        raw_price = self._coerce_text(document.get("display_special_price"))
        if raw_price:
            return raw_price
        raw_numeric = document.get("special_price")
        if raw_numeric is not None:
            return f"₹{Decimal(str(raw_numeric)):,.0f}"
        return f"₹{price_value:,.0f}"

    def _coerce_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()

    def _truthy(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        if isinstance(value, (int, float)):
            return value != 0
        return self._coerce_text(value).lower() not in {"", "0", "false", "no"}
