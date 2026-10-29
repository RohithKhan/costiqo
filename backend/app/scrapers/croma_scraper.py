from __future__ import annotations

import logging
from urllib.parse import quote_plus

from app.scrapers.base import BaseScraper, PriceHistoryEntry, ScrapedListing, ScrapedReview, SearchContext
from app.scrapers.hardware_scraper_utils import availability_from_text, build_listing, coerce_text, fetch_json
from app.scrapers.live_utils import fetch_live_results
from app.scrapers.normalizers import listing_matches_query
from app.utils.number_parser import parse_count_value, parse_rating_value
from app.utils.price_parser import parse_price
from app.utils.product_identity import build_product_key, infer_brand, infer_category, normalize_product_name
from app.utils.time_utils import utc_now
from app.utils.vendor_links import canonicalize_vendor_product_url


logger = logging.getLogger(__name__)


CROMA_EXTRACTION_SCRIPT = """
() => {
  const seen = new Set();
  const cards = Array.from(document.querySelectorAll('.cp-product, .product-item, li.product-item, [data-testid*="product"], [class*="product"]'));
  return cards.map((card) => {
    const link =
      card.querySelector('a[href*="/p/"]') ||
      card.querySelector('a[href*="%2Fp%2F"]') ||
      card.querySelector('a[href*="/l/redirect"]') ||
      card.querySelector('a[href*="/product/"]') ||
      card.querySelector('a[href]');
    const href = link?.href || link?.getAttribute('href') || '';
    if (!href || seen.has(href) || !(href.includes('/p/') || href.includes('%2Fp%2F'))) {
      return null;
    }
    seen.add(href);
    const title =
      card.querySelector('.product-title, .plp-prod-title, .product-name, h3, h2')?.textContent?.trim() ||
      card.querySelector('img')?.getAttribute('alt')?.trim() ||
      '';
    const price =
      card.querySelector('.amount, .new-price, .price, [class*="price"], [class*="Price"]')?.textContent?.trim()?.match(/₹\\s*[\\d,]+(?:\\.\\d+)?/)?.[0] ||
      card.textContent?.match(/₹\\s*[\\d,]+(?:\\.\\d+)?/)?.[0] ||
      null;
    return {
      href,
      title,
      image: card.querySelector('img')?.currentSrc || card.querySelector('img')?.src || '',
      price,
      rating: card.querySelector('[class*="rating"], [aria-label*="rating"]')?.textContent?.trim() || card.querySelector('[aria-label*="rating"]')?.getAttribute('aria-label') || null,
      reviews: card.textContent?.match(/\\(?[\\d,]+\\s*(?:ratings?|reviews?)\\)?/i)?.[0] || null,
      availability: card.textContent?.match(/out of stock|in stock|available/i)?.[0] || null,
    };
  }).filter(Boolean).slice(0, 24);
}
"""


class CromaScraper(BaseScraper):
    vendor_name = "Croma"
    base_url = "https://www.croma.com"
    api_base_url = "https://api.croma.com"
    scrape_strategy = "live-http-search-api"
    timeout_seconds = 12
    max_results = 24
    default_pincode = "400049"

    async def search(
        self,
        query: str,
        context: SearchContext | None = None,
    ) -> list[ScrapedListing]:
        pincode = (context.pincode if context else None) or self.default_pincode
        try:
            payload = await fetch_json(
                self._search_api_url(query, pincode),
                timeout_seconds=self.timeout_seconds,
                extra_headers={
                    "origin": self.base_url,
                    "referer": f"{self.base_url}/searchB?q={quote_plus(query)}%3Arelevance&text={quote_plus(query)}",
                },
            )
            listings = self._build_api_listings(query, payload)
            if listings:
                return listings
        except RuntimeError as exc:
            message = str(exc)
            if self._is_blocked_or_unavailable(message):
                logger.warning("croma_api_search_blocked query=%s error=%s", query, message)
            else:
                logger.warning("croma_api_search_failed query=%s error=%s", query, message)

        try:
            raw_items = await fetch_live_results(
                url=f"{self.base_url}/searchB?q={quote_plus(query)}%3Arelevance&text={quote_plus(query)}",
                extraction_script=CROMA_EXTRACTION_SCRIPT,
                result_selectors=[
                    ".cp-product",
                    ".product-item",
                    "li.product-item",
                    "a[href*='/p/']",
                    "a[href*='/l/redirect']",
                    "[class*='product']",
                ],
                wait_after_load_ms=8_000,
            )
        except RuntimeError as exc:
            message = str(exc)
            if self._is_blocked_or_unavailable(message):
                logger.warning("croma_search_blocked query=%s error=%s", query, message)
                return []
            raise
        return self._build_live_listings(query, raw_items)

    async def fetch_reviews(self, product_url: str) -> list[ScrapedReview]:
        return []

    def _is_blocked_or_unavailable(self, message: str) -> bool:
        normalized = message.lower()
        return any(
            marker in normalized
            for marker in (
                "status=403",
                "status 403",
                "access denied",
                "akamaighost",
                "edgesuite",
                "permission to access",
                "captcha",
                "challenge",
            )
        )

    def _search_api_url(self, query: str, pincode: str) -> str:
        return (
            f"{self.api_base_url}/searchservices/v1/search"
            f"?currentPage=0&query={quote_plus(f'{query}:relevance')}"
            f"&fields=FULL&channel=WEB&channelCode={quote_plus(pincode)}&spellOpt=DEFAULT"
        )

    def _build_api_listings(self, query: str, payload: object) -> list[ScrapedListing]:
        if not isinstance(payload, dict) or not isinstance(payload.get("products"), list):
            return []

        listings: list[ScrapedListing] = []
        seen_urls: set[str] = set()
        for product in payload["products"]:
            if not isinstance(product, dict):
                continue
            listing = build_listing(
                self,
                query,
                title=coerce_text(product.get("name") or product.get("summary")),
                product_url=coerce_text(product.get("url")),
                price=self._api_price(product),
                raw_price=self._api_raw_price(product),
                image_url=coerce_text(product.get("plpImage")),
                brand=coerce_text(product.get("manufacturer")) or None,
                model_number=coerce_text(product.get("code")) or None,
                rating=product.get("finalReviewRating") or product.get("averageRating"),
                review_count=(
                    product.get("numberOfRatings")
                    or product.get("finalReviewRatingCount")
                    or product.get("numberOfReviews")
                ),
                delivery_info=coerce_text(product.get("productMessage")) or None,
                availability_status=self._api_availability(product),
                raw_payload=self._compact_api_payload(product),
            )
            if listing is None or listing.product_url in seen_urls:
                continue
            if not listing_matches_query(query, listing.vendor_product_name):
                continue
            seen_urls.add(listing.product_url)
            listings.append(listing)
            if len(listings) >= self.max_results:
                break
        return listings

    def _api_price(self, product: dict) -> object:
        for key in ("pincodePrice", "price", "mrp"):
            value = product.get(key)
            if isinstance(value, dict):
                return value.get("value") or value.get("formattedValue")
        return None

    def _api_raw_price(self, product: dict) -> str | None:
        for key in ("pincodePrice", "price", "mrp"):
            value = product.get(key)
            if isinstance(value, dict):
                raw_price = coerce_text(value.get("formattedValue"))
                if raw_price:
                    return raw_price
        return None

    def _api_availability(self, product: dict) -> str:
        for key in ("outOfStock", "isOutOfStock", "stockOut"):
            if product.get(key) is True:
                return "out_of_stock"
        stock_flags = product.get("stockFlag")
        if isinstance(stock_flags, list) and not stock_flags:
            return "out_of_stock"
        return "in_stock"

    def _compact_api_payload(self, product: dict) -> dict:
        return {
            "code": product.get("code"),
            "name": product.get("name"),
            "manufacturer": product.get("manufacturer"),
            "url": product.get("url"),
            "price": product.get("price"),
            "pincodePrice": product.get("pincodePrice"),
            "mrp": product.get("mrp"),
            "averageRating": product.get("averageRating"),
            "finalReviewRating": product.get("finalReviewRating"),
            "numberOfRatings": product.get("numberOfRatings"),
            "numberOfReviews": product.get("numberOfReviews"),
            "productMessage": product.get("productMessage"),
        }

    def _build_live_listings(self, query: str, raw_items: list[dict]) -> list[ScrapedListing]:
        listings: list[ScrapedListing] = []
        seen_urls: set[str] = set()
        now = utc_now()
        for item in raw_items:
            title = normalize_product_name(item.get("title") or "")
            price_value = parse_price(item.get("price"))
            href = item.get("href") or ""
            if not title or price_value is None or not href:
                continue
            if not listing_matches_query(query, title):
                continue
            product_url = canonicalize_vendor_product_url(self.vendor_name, href, self.base_url)
            if product_url in seen_urls:
                continue
            seen_urls.add(product_url)
            listings.append(
                ScrapedListing(
                    vendor=self.vendor_name,
                    base_url=self.base_url,
                    scrape_strategy=self.scrape_strategy,
                    canonical_name=title,
                    brand=infer_brand(title, query),
                    category=infer_category(title, query),
                    model_number=build_product_key(title, query),
                    image_url=item.get("image") or "",
                    vendor_product_name=title,
                    product_url=product_url,
                    price=price_value,
                    raw_price=item.get("price") or "",
                    rating=parse_rating_value(item.get("rating")),
                    review_count=parse_count_value(item.get("reviews")),
                    availability_status=availability_from_text(item.get("availability")),
                    price_history=[PriceHistoryEntry(scraped_at=now, price=price_value)],
                    raw_payload=item,
                )
            )
        return listings
