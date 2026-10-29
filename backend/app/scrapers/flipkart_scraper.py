from urllib.parse import quote_plus

from app.scrapers.base import BaseScraper, PriceHistoryEntry, ScrapedListing, ScrapedReview, SearchContext
from app.scrapers.live_utils import fetch_live_results
from app.scrapers.normalizers import listing_matches_query
from app.utils.number_parser import parse_count_value, parse_rating_value
from app.utils.price_parser import parse_price
from app.utils.product_identity import build_product_key, infer_brand, infer_category, normalize_product_name
from app.utils.time_utils import utc_now
from app.utils.vendor_links import canonicalize_vendor_product_url


FLIPKART_EXTRACTION_SCRIPT = """
() => {
  const seen = new Set();
  return Array.from(document.querySelectorAll('a[href*="/p/"]'))
    .map((link) => {
      const href = link.getAttribute('href');
      if (!href || seen.has(href)) {
        return null;
      }
      seen.add(href);
      return {
        href,
        title:
          link.querySelector('.RG5Slk')?.textContent?.trim() ||
          link.querySelector('img')?.getAttribute('alt')?.trim() ||
          '',
        image: link.querySelector('img')?.src || '',
        price:
          link.querySelector('.hZ3P6w')?.textContent?.trim() ||
          link.textContent?.match(/₹[\\d,]+/)?.[0] ||
          null,
        rating: link.querySelector('.MKiFS6')?.textContent?.trim() || null,
        reviews: link.querySelector('.PvbNMB')?.textContent?.trim() || null,
      };
    })
    .filter(Boolean)
    .slice(0, 20);
}
"""


class FlipkartScraper(BaseScraper):
    vendor_name = "Flipkart"
    base_url = "https://www.flipkart.com"
    scrape_strategy = "live-playwright"

    async def search(
        self,
        query: str,
        context: SearchContext | None = None,
    ) -> list[ScrapedListing]:
        raw_items = await fetch_live_results(
            url=f"{self.base_url}/search?q={quote_plus(query)}",
            extraction_script=FLIPKART_EXTRACTION_SCRIPT,
            result_selectors=['a[href*="/p/"]'],
            wait_after_load_ms=4_000,
        )
        return self._build_live_listings(query, raw_items)

    async def fetch_reviews(self, product_url: str) -> list[ScrapedReview]:
        return []

    def _build_live_listings(self, query: str, raw_items: list[dict]) -> list[ScrapedListing]:
        listings: list[ScrapedListing] = []
        now = utc_now()

        for item in raw_items:
            title = normalize_product_name(item.get("title") or "")
            price_value = parse_price(item.get("price"))
            href = item.get("href") or ""
            if not title or price_value is None or not href:
                continue
            if not listing_matches_query(query, title):
                continue

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
                    product_url=canonicalize_vendor_product_url(
                        self.vendor_name,
                        href,
                        self.base_url,
                    ),
                    price=price_value,
                    raw_price=item.get("price") or "",
                    rating=parse_rating_value(item.get("rating")),
                    review_count=parse_count_value(item.get("reviews")),
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
