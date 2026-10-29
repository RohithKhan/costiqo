from urllib.parse import quote_plus

from playwright.async_api import Page

from app.scrapers.base import BaseScraper, PriceHistoryEntry, ScrapedListing, ScrapedReview
from app.scrapers.live_utils import fetch_live_results
from app.scrapers.normalizers import listing_matches_query
from app.scrapers.base import SearchContext
from app.utils.number_parser import parse_count_value, parse_rating_value
from app.utils.price_parser import parse_price
from app.utils.product_identity import build_product_key, infer_brand, infer_category, normalize_product_name
from app.utils.time_utils import utc_now
from app.utils.vendor_links import canonicalize_vendor_product_url


AMAZON_EXTRACTION_SCRIPT = """
() => Array.from(document.querySelectorAll('[data-component-type="s-search-result"]'))
  .filter((item) => item.getAttribute('data-asin'))
  .slice(0, 30)
  .map((item) => {
    const titleLink = item.querySelector('a.s-line-clamp-2') || item.querySelector('h2 a');
    return {
      asin: item.getAttribute('data-asin'),
      title:
        item.querySelector('a.s-line-clamp-2 span')?.textContent?.trim() ||
        item.querySelector('h2 span')?.textContent?.trim() ||
        item.querySelector('img.s-image')?.alt?.trim() ||
        '',
      href: titleLink?.href || null,
      image: item.querySelector('img.s-image')?.src || '',
      price: item.querySelector('.a-price .a-offscreen')?.textContent?.trim() || null,
      rating:
        item.querySelector('[aria-label*="out of 5 stars"]')?.getAttribute('aria-label') || null,
      reviews:
        item.querySelector('a[href*="#customerReviews"]')?.textContent?.trim() ||
        item.querySelector('span.a-size-base.s-underline-text')?.textContent?.trim() ||
        null,
    };
  });
"""


class AmazonScraper(BaseScraper):
    vendor_name = "Amazon"
    base_url = "https://www.amazon.in"
    scrape_strategy = "live-playwright"

    async def search(
        self,
        query: str,
        context: SearchContext | None = None,
    ) -> list[ScrapedListing]:
        raw_items = await fetch_live_results(
            url=f"{self.base_url}/s?k={quote_plus(query)}",
            extraction_script=AMAZON_EXTRACTION_SCRIPT,
            result_selectors=['[data-component-type="s-search-result"]'],
            page_setup=self._page_setup(context),
        )
        return self._build_live_listings(query, raw_items)

    async def fetch_reviews(self, product_url: str) -> list[ScrapedReview]:
        return []

    def _page_setup(self, context: SearchContext | None):
        if context is None or not context.pincode:
            return None

        async def apply_pincode(page: Page) -> None:
            location_trigger = page.locator("#nav-global-location-popover-link")
            if not await location_trigger.count():
                return

            await location_trigger.first.click(timeout=10_000)
            zip_input = page.locator("#GLUXZipUpdateInput")
            if not await zip_input.count():
                return

            await zip_input.first.fill(context.pincode)
            submit = page.locator("#GLUXZipUpdate")
            if await submit.count():
                await submit.first.click(timeout=10_000)
            await page.wait_for_timeout(2_500)

            close_button = page.locator("#GLUXConfirmClose")
            if await close_button.count():
                await close_button.first.click(timeout=5_000)

        return apply_pincode

    def _build_live_listings(self, query: str, raw_items: list[dict]) -> list[ScrapedListing]:
        listings: list[ScrapedListing] = []
        seen_urls: set[str] = set()
        now = utc_now()

        for item in raw_items:
            title = normalize_product_name(item.get("title") or "")
            price_value = parse_price(item.get("price"))
            asin = (item.get("asin") or "").strip()
            href = item.get("href") or (f"{self.base_url}/dp/{asin}" if asin else "")
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
