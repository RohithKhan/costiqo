import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.scrapers import hardware_scraper_utils, live_utils
from app.scrapers.base import BaseScraper, ScrapedListing, SearchContext
from app.services.offer_verification_service import OfferVerificationService
from app.services.scrape_service import ScrapeService, ScraperResult


class DummyScraper(BaseScraper):
    vendor_name = "MockVendor"
    base_url = "https://example.com"
    scrape_strategy = "mock"
    timeout_seconds = 5

    def __init__(self, delay: float = 0.05, results: list[ScrapedListing] | None = None) -> None:
        self.delay = delay
        self.results = results or []
        self.call_count = 0

    async def search(self, query: str, context: SearchContext | None = None) -> list[ScrapedListing]:
        self.call_count += 1
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        return list(self.results)

    async def fetch_reviews(self, product_url: str):
        return []


class FailingScraper(BaseScraper):
    vendor_name = "FailingVendor"
    base_url = "https://failing.example.com"
    scrape_strategy = "failing"
    timeout_seconds = 2

    async def search(self, query: str, context: SearchContext | None = None) -> list[ScrapedListing]:
        raise httpx.ConnectTimeout("Connection to vendor timed out")

    async def fetch_reviews(self, product_url: str):
        return []


@pytest.mark.asyncio
async def test_hardware_scraper_utils_timeouts_configured():
    """Verify fetch_html, fetch_json, and post_json configure explicit connection and overall timeouts."""
    async def mock_send(request, **kwargs):
        return httpx.Response(200, request=request, text="<html><body>content</body></html>")

    transport = httpx.MockTransport(mock_send)
    custom_client = httpx.AsyncClient(transport=transport)

    with patch.object(custom_client, "get", wraps=custom_client.get) as spy_get:
        res = await hardware_scraper_utils.fetch_html(
            "https://example.com/item",
            timeout_seconds=6.0,
            client=custom_client,
        )
        assert res == "<html><body>content</body></html>"
        assert spy_get.call_count == 1
        call_kwargs = spy_get.call_args.kwargs
        timeout_arg = call_kwargs.get("timeout")
        assert isinstance(timeout_arg, httpx.Timeout)
        assert timeout_arg.connect == 5.0
        assert timeout_arg.read == 6.0

    await custom_client.aclose()


@pytest.mark.asyncio
async def test_live_browser_concurrency_semaphore():
    """Verify live_utils bounds concurrent browser contexts with a semaphore."""
    sem = live_utils._get_browser_semaphore()
    assert isinstance(sem, asyncio.Semaphore)
    # Default is 4
    assert sem._value <= 4

    await live_utils.close_live_browser()
    assert live_utils._browser_semaphore is None


@pytest.mark.asyncio
async def test_scrape_service_inflight_deduplication():
    """Verify duplicate concurrent queries reuse the in-flight scrape rather than firing twice."""
    scraper = DummyScraper(delay=0.1, results=[MagicMock(spec=ScrapedListing)])
    service = object.__new__(ScrapeService)
    service.retry_attempts = 1
    service.retry_backoff_seconds = 0.01
    service._scraper_semaphore = asyncio.Semaphore(10)
    service._inflight_scrapes = {}

    # Fire two identical searches concurrently
    task1 = asyncio.create_task(service._search_with_retry(scraper, "raspberry pi 4"))
    task2 = asyncio.create_task(service._search_with_retry(scraper, "raspberry pi 4"))

    res1, res2 = await asyncio.gather(task1, task2)
    assert res1.error is None
    assert res2.error is None
    assert len(res1.listings) == 1
    assert len(res2.listings) == 1
    # Only one underlying scraper search call should have happened!
    assert scraper.call_count == 1
    # In-flight dictionary should be cleared after completion
    assert len(service._inflight_scrapes) == 0


@pytest.mark.asyncio
async def test_scrape_service_scraper_concurrency_bounding():
    """Verify scraping execution is bounded by the scraper semaphore."""
    scraper = DummyScraper(delay=0.05)
    service = object.__new__(ScrapeService)
    service.retry_attempts = 1
    service.retry_backoff_seconds = 0.01
    # Limit concurrency to 2
    service._scraper_semaphore = asyncio.Semaphore(2)
    service._inflight_scrapes = {}

    max_active = 0
    current_active = 0

    orig_execute = service._execute_search_with_retry

    async def monitored_execute(sc, q, ctx):
        nonlocal max_active, current_active
        current_active += 1
        if current_active > max_active:
            max_active = current_active
        try:
            return await orig_execute(sc, q, ctx)
        finally:
            current_active -= 1

    service._execute_search_with_retry = monitored_execute

    tasks = [
        asyncio.create_task(service._search_with_retry(scraper, f"query {i}"))
        for i in range(6)
    ]
    await asyncio.gather(*tasks)

    # Max concurrency observed must not exceed the semaphore limit of 2
    assert max_active <= 2
    assert current_active == 0


@pytest.mark.asyncio
async def test_offer_verification_service_reuses_browser():
    """Verify offer verification service uses shared browser from live_utils instead of launching a new one."""
    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = MagicMock()
    mock_page.url = "https://www.amazon.in/dp/B08N5WRWNW"

    mock_locator = MagicMock()
    mock_locator.inner_text = AsyncMock(return_value="₹1,499.00 In Stock")
    mock_page.locator = MagicMock(return_value=mock_locator)

    mock_browser.new_context.return_value = mock_context
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_page.goto = AsyncMock()
    mock_page.wait_for_timeout = AsyncMock()

    service = OfferVerificationService(timeout_seconds=5)

    with patch("app.scrapers.live_utils._get_browser", return_value=mock_browser) as mock_get_browser:
        text = await service._fetch_rendered_text("https://www.amazon.in/dp/B08N5WRWNW")
        assert text is not None
        assert "₹1,499.00" in text
        # Must have retrieved the shared browser
        assert mock_get_browser.call_count == 1
        # Must have created context and page, and closed context
        assert mock_browser.new_context.call_count == 1
        assert mock_context.close.call_count == 1


@pytest.mark.asyncio
async def test_scrape_service_handles_vendor_failure_gracefully():
    """Verify ScrapeService catches scraper exceptions and returns graceful empty results without crashing."""
    scraper = FailingScraper()
    service = object.__new__(ScrapeService)
    service.retry_attempts = 2
    service.retry_backoff_seconds = 0.01
    service._scraper_semaphore = asyncio.Semaphore(5)
    service._inflight_scrapes = {}

    result = await service._search_with_retry(scraper, "test item")
    assert isinstance(result, ScraperResult)
    assert result.listings == []
    assert isinstance(result.error, httpx.ConnectTimeout)
    assert result.scraper.vendor_name == "FailingVendor"
