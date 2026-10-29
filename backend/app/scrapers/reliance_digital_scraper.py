from urllib.parse import quote_plus

from app.scrapers.base import BaseScraper, PriceHistoryEntry, ScrapedListing, ScrapedReview, SearchContext
from app.scrapers.live_utils import fetch_live_results
from app.scrapers.normalizers import listing_matches_query
from app.utils.number_parser import parse_count_value
from app.utils.price_parser import parse_price
from app.utils.product_identity import build_product_key, infer_brand, infer_category, normalize_product_name
from app.utils.time_utils import utc_now
from app.utils.vendor_links import canonicalize_vendor_product_url


RELIANCE_DIGITAL_EXTRACTION_SCRIPT = """
() => Array.from(document.querySelectorAll('a.details-container'))
  .slice(0, 24)
  .map((link) => {
    const card = link.closest('.product-card-details')?.parentElement;
    return {
      href: link.getAttribute('href'),
      title: link.querySelector('.product-card-title')?.textContent?.trim() || '',
      image: card?.querySelector('img')?.src || '',
      price: link.querySelector('.price')?.textContent?.trim() || null,
      reviews: card?.querySelector('.product-card-rating')?.textContent?.trim() || null,
      delivery:
        card?.querySelector('.delivery-fulfilment-plp')?.textContent?.trim().replace(/\\s+/g, ' ') ||
        null,
      starCount: card?.querySelectorAll('.rating-star-list svg').length || 0,
    };
  });
"""


class RelianceDigitalScraper(BaseScraper):
    vendor_name = "Reliance Digital"
    base_url = "https://www.reliancedigital.in"
    scrape_strategy = "live-playwright"

    async def search(
        self,
        query: str,
        context: SearchContext | None = None,
    ) -> list[ScrapedListing]:
        raw_items = await fetch_live_results(
            url=f"{self.base_url}/products?q={quote_plus(query)}",
            extraction_script=RELIANCE_DIGITAL_EXTRACTION_SCRIPT,
            result_selectors=["a.details-container"],
            wait_after_load_ms=5_000,
        )
        return self._build_live_listings(query, raw_items)

    async def fetch_reviews(self, product_url: str) -> list[ScrapedReview]:
        return []

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

            product_url = canonicalize_vendor_product_url(
                self.vendor_name,
                href,
                self.base_url,
            )
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
                    rating=float(item.get("starCount") or 0) or None,
                    review_count=parse_count_value(item.get("reviews")),
                    delivery_info=item.get("delivery"),
                    price_history=[
                        PriceHistoryEntry(
                            scraped_at=now,
                            price=price_value,
                        )
                    ],
                    raw_payload=item,
                )
            )

        return listings
