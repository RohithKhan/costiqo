from __future__ import annotations

import json
import logging
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote_plus

from app.scrapers.base import BaseScraper, ScrapedListing, ScrapedReview, SearchContext
from app.scrapers.hardware_scraper_utils import build_listing, coerce_text, fetch_json, query_variants
from app.scrapers.live_utils import fetch_live_results
from app.utils.price_parser import parse_price


logger = logging.getLogger(__name__)


ROBU_RELATED_SEARCH_QUERY = """
query RelatedProductSearch($search: String!) {
  productSearch(search: $search) {
    data {
      categories {
        products {
          id
          name
          slug
          sku
          price
          sale_price
          moq_price
          image_url
          in_stock
          is_backorder
          special_price_from
          special_price_to
          reviews_count
          __typename
        }
        __typename
      }
      brands {
        products {
          id
          name
          slug
          sku
          price
          sale_price
          moq_price
          image_url
          in_stock
          is_backorder
          special_price_from
          special_price_to
          reviews_count
          __typename
        }
        __typename
      }
      tags {
        products {
          id
          name
          slug
          sku
          price
          sale_price
          moq_price
          image_url
          in_stock
          is_backorder
          special_price_from
          special_price_to
          reviews_count
          __typename
        }
        __typename
      }
      products {
        id
        name
        slug
        sku
        price
        sale_price
        moq_price
        image_url
        in_stock
        is_backorder
        special_price_from
        special_price_to
        reviews_count
        __typename
      }
      __typename
    }
    __typename
  }
}
"""


def build_robu_graphql_extraction_script(search_query: str) -> str:
    search_json = json.dumps(search_query)
    query_json = json.dumps(ROBU_RELATED_SEARCH_QUERY)
    return f"""
async () => {{
  const body = {{
    operationName: "RelatedProductSearch",
    variables: {{ search: {search_json} }},
    query: {query_json},
  }};
  const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
  const startedAt = Date.now();
  while (Date.now() - startedAt < 5500) {{
    try {{
      const response = await fetch("/api/proxy/graphql/", {{
        method: "POST",
        headers: {{ "content-type": "application/json" }},
        body: JSON.stringify(body),
      }});
      if (!response.ok) {{
        await sleep(450);
        continue;
      }}
      const payload = await response.json();
      const data = payload?.data?.productSearch?.data || {{}};
      const productGroups = [
        data.products || [],
        ...(data.categories || []).map((group) => group?.products || []),
        ...(data.brands || []).map((group) => group?.products || []),
        ...(data.tags || []).map((group) => group?.products || []),
      ];
      const seen = new Set();
      const items = [];
      for (const group of productGroups) {{
        for (const product of group || []) {{
          const slug = product?.slug || "";
          const title = (product?.name || "").replace(/\\s+/g, " ").trim();
          const priceValue = product?.sale_price ?? product?.moq_price ?? product?.price;
          const key = slug || product?.id || title;
          if (!key || seen.has(key) || !slug || !title || priceValue == null) {{
            continue;
          }}
          seen.add(key);
          const numericPrice = Number(priceValue);
          const rawPrice = Number.isFinite(numericPrice)
            ? `₹${{numericPrice.toLocaleString("en-IN")}}`
            : String(priceValue);
          items.push({{
            href: `https://robu.in/product/${{slug}}/`,
            title,
            price: rawPrice,
            image: product?.image_url || "",
            sku: product?.sku || null,
            reviews: product?.reviews_count ?? null,
            availability: product?.is_backorder
              ? "backorder"
              : product?.in_stock === false
                ? "out of stock"
                : "add to cart",
            rawPayload: product,
          }});
          if (items.length >= 24) {{
            return items;
          }}
        }}
      }}
      if (items.length) {{
        return items;
      }}
    }} catch (error) {{
      // Cloudflare occasionally completes the page before its fetch cookie is ready.
    }}
    await sleep(450);
  }}
  return [];
}}
"""


ROBU_EXTRACTION_SCRIPT = """
() => {
  const seen = new Set();
  const links = Array.from(document.querySelectorAll('.product-details a[href*="/product/"], a[href*="/product/"]'));
  return links.map((link) => {
    const href = link.href || link.getAttribute('href') || '';
    if (!href || seen.has(href)) {
      return null;
    }
    const details = link.closest('.product-details') || link.parentElement;
    const card = details?.parentElement || link.closest('[class*="product"], li, article, div') || link;
    const detailText = (details?.textContent || card?.textContent || '').replace(/\\s+/g, ' ').trim();
    const title = (link.textContent || '').replace(/\\s+/g, ' ').trim();
    const price = detailText.match(/₹\\s*[\\d,]+(?:\\.\\d+)?/)?.[0] || null;
    if (!title || !price) {
      return null;
    }
    seen.add(href);
    return {
      href,
      title,
      price,
      image: card?.querySelector('img')?.currentSrc || card?.querySelector('img')?.src || '',
      sku: detailText.match(/SKU:\\s*([^\\s()]+)/i)?.[1] || null,
      reviews: detailText.match(/\\(([\\d,]+)\\)/)?.[1] || null,
      availability: detailText.match(/out of stock|backorder|add to cart/i)?.[0] || null,
      rawText: detailText,
    };
  }).filter(Boolean).slice(0, 24);
}
"""


class RobuScraper(BaseScraper):
    vendor_name = "Robu"
    base_url = "https://robu.in"
    api_base_url = "https://oldwp.robu.in"
    scrape_strategy = "live-http-wc-store-api"
    timeout_seconds = 12
    max_results = 24

    async def search(
        self,
        query: str,
        context: SearchContext | None = None,
    ) -> list[ScrapedListing]:
        for search_query in query_variants(query):
            try:
                raw_items = await fetch_live_results(
                    url=f"{self.base_url}/?s={quote_plus(search_query)}&post_type=product",
                    extraction_script=build_robu_graphql_extraction_script(search_query),
                    result_selectors=["body"],
                    wait_after_load_ms=1_000,
                    settle_after_result_ms=500,
                    navigation_timeout_ms=12_000,
                )
            except RuntimeError as exc:
                message = str(exc)
                if self._is_blocked_or_unavailable(message):
                    logger.warning("robu_graphql_search_blocked query=%s error=%s", search_query, message)
                    break
                if "no parsable results" not in message.lower():
                    raise
                continue
            listings = self._build_live_listings(query, raw_items)
            if listings:
                return listings

        for search_query in query_variants(query):
            try:
                payload = await fetch_json(
                    f"{self.api_base_url}/wp-json/wc/store/v1/products"
                    f"?search={quote_plus(search_query)}&per_page={self.max_results}",
                    timeout_seconds=self.timeout_seconds,
                )
            except RuntimeError as exc:
                message = str(exc)
                if self._is_blocked_or_unavailable(message):
                    logger.warning("robu_search_blocked query=%s error=%s", search_query, message)
                    break
                raise
            listings = self._build_api_listings(query, payload)
            if listings:
                return listings

        for search_query in query_variants(query):
            try:
                raw_items = await fetch_live_results(
                    url=f"{self.base_url}/?s={quote_plus(search_query)}&post_type=product",
                    extraction_script=ROBU_EXTRACTION_SCRIPT,
                    result_selectors=[
                        ".product-details a[href*='/product/']",
                        "a[href*='/product/']",
                    ],
                    wait_after_load_ms=12_000,
                    settle_after_result_ms=1_000,
                    navigation_timeout_ms=30_000,
                )
            except RuntimeError as exc:
                message = str(exc)
                if self._is_blocked_or_unavailable(message):
                    logger.warning("robu_live_search_blocked query=%s error=%s", search_query, message)
                    return []
                raise
            listings = self._build_live_listings(query, raw_items)
            if listings:
                return listings
        return []

    async def fetch_reviews(self, product_url: str) -> list[ScrapedReview]:
        return []

    def _is_blocked_or_unavailable(self, message: str) -> bool:
        normalized = message.lower()
        return any(
            marker in normalized
            for marker in (
                "status 403",
                "status 503",
                "access denied",
                "service temporarily unavailable",
                "cf-mitigated",
                "cloudflare",
                "challenge",
                "just a moment",
                "security verification",
                "attention required",
            )
        )

    def _build_api_listings(self, query: str, payload: Any) -> list[ScrapedListing]:
        if not isinstance(payload, list):
            return []

        listings: list[ScrapedListing] = []
        seen_urls: set[str] = set()
        for product in payload:
            if not isinstance(product, dict):
                continue
            category = self._category(product)
            listing = build_listing(
                self,
                query,
                title=coerce_text(product.get("name")),
                product_url=self._product_url(product),
                price=self._price(product),
                raw_price=self._raw_price(product),
                image_url=self._image_url(product),
                model_number=coerce_text(product.get("sku")) or None,
                rating=product.get("average_rating"),
                review_count=product.get("review_count"),
                availability_status="in_stock" if product.get("is_in_stock") else "out_of_stock",
                raw_payload=self._compact_payload(product),
            )
            if listing is None or listing.product_url in seen_urls:
                continue
            if category:
                listing.category = category
            seen_urls.add(listing.product_url)
            listings.append(listing)
        return listings

    def _product_url(self, product: dict[str, Any]) -> str:
        slug = coerce_text(product.get("slug"))
        if slug:
            return f"{self.base_url}/product/{slug}/"
        permalink = coerce_text(product.get("permalink"))
        if permalink:
            return permalink.replace(self.api_base_url, self.base_url)
        return ""

    def _price(self, product: dict[str, Any]) -> Decimal | None:
        prices = product.get("prices")
        if not isinstance(prices, dict):
            return parse_price(coerce_text(product.get("price_html")))
        raw_price = coerce_text(prices.get("price") or prices.get("sale_price") or prices.get("regular_price"))
        if not raw_price:
            return parse_price(coerce_text(product.get("price_html")))
        try:
            minor_unit = int(prices.get("currency_minor_unit") or 2)
            divisor = Decimal(10) ** minor_unit
            return (Decimal(raw_price) / divisor).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            return parse_price(coerce_text(product.get("price_html")))

    def _raw_price(self, product: dict[str, Any]) -> str | None:
        price = self._price(product)
        return f"₹{price:,.2f}" if price is not None else None

    def _image_url(self, product: dict[str, Any]) -> str:
        images = product.get("images")
        if isinstance(images, list) and images:
            first = images[0]
            if isinstance(first, dict):
                return coerce_text(first.get("src") or first.get("thumbnail"))
        return ""

    def _category(self, product: dict[str, Any]) -> str | None:
        categories = product.get("categories")
        if isinstance(categories, list) and categories:
            first = categories[0]
            if isinstance(first, dict):
                return coerce_text(first.get("name")) or None
        return None

    def _compact_payload(self, product: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": product.get("id"),
            "name": product.get("name"),
            "slug": product.get("slug"),
            "sku": product.get("sku"),
            "permalink": product.get("permalink"),
            "prices": product.get("prices"),
            "average_rating": product.get("average_rating"),
            "review_count": product.get("review_count"),
            "is_in_stock": product.get("is_in_stock"),
            "categories": product.get("categories"),
        }

    def _build_live_listings(self, query: str, raw_items: list[dict]) -> list[ScrapedListing]:
        listings: list[ScrapedListing] = []
        seen_urls: set[str] = set()
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            listing = build_listing(
                self,
                query,
                title=coerce_text(item.get("title")),
                product_url=coerce_text(item.get("href")),
                price=item.get("price"),
                raw_price=coerce_text(item.get("price")) or None,
                image_url=coerce_text(item.get("image")),
                model_number=coerce_text(item.get("sku")) or None,
                review_count=item.get("reviews"),
                availability_status=self._live_availability(item),
                raw_payload=item,
            )
            if listing is None or listing.product_url in seen_urls:
                continue
            seen_urls.add(listing.product_url)
            listings.append(listing)
            if len(listings) >= self.max_results:
                break
        return listings

    def _live_availability(self, item: dict) -> str:
        availability = coerce_text(item.get("availability")).lower()
        if "out of stock" in availability:
            return "out_of_stock"
        if "backorder" in availability:
            return "backorder"
        return "in_stock"
