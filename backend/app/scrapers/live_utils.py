from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence

from playwright.async_api import Browser, Page, Playwright, async_playwright


PageSetupCallback = Callable[[Page], Awaitable[None]]

logger = logging.getLogger(__name__)

_playwright: Playwright | None = None
_browser: Browser | None = None
_browser_lock: asyncio.Lock | None = None
_browser_lock_loop: asyncio.AbstractEventLoop | None = None
_browser_semaphore: asyncio.Semaphore | None = None
_browser_semaphore_loop: asyncio.AbstractEventLoop | None = None
MAX_CONCURRENT_BROWSER_CONTEXTS = 4

BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}
BLOCKED_URL_PARTS = (
    "doubleclick.net",
    "facebook.net",
    "facebook.com/tr",
    "google-analytics.com",
    "googletagmanager.com",
    "hotjar.com",
    "moengage",
    "optimizely",
    "segment.com",
)


def should_block_request(resource_type: str, url: str) -> bool:
    normalized_url = url.lower()
    return resource_type in BLOCKED_RESOURCE_TYPES or any(
        blocked_part in normalized_url
        for blocked_part in BLOCKED_URL_PARTS
    )


def _get_browser_semaphore() -> asyncio.Semaphore:
    global _browser_semaphore, _browser_semaphore_loop

    current_loop = asyncio.get_running_loop()
    if _browser_semaphore is None or _browser_semaphore_loop is not current_loop or current_loop.is_closed():
        _browser_semaphore = asyncio.Semaphore(MAX_CONCURRENT_BROWSER_CONTEXTS)
        _browser_semaphore_loop = current_loop
    return _browser_semaphore


async def fetch_live_results(
    url: str,
    extraction_script: str,
    result_selectors: Sequence[str],
    page_setup: PageSetupCallback | None = None,
    wait_after_load_ms: int = 3000,
    settle_after_result_ms: int = 500,
    navigation_timeout_ms: int = 20_000,
) -> list[dict]:
    sem = _get_browser_semaphore()
    async with sem:
        browser = await _get_browser()
        context = await browser.new_context(
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            viewport={"width": 1440, "height": 1024},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            extra_http_headers={
                "Accept-Language": "en-IN,en;q=0.9",
            },
        )
        try:
            await context.route("**/*", _route_request)
            page = await context.new_page()
            await page.add_init_script(
                """
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                """
            )

            response = await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=navigation_timeout_ms,
            )
            if page_setup is not None:
                await page.wait_for_timeout(min(1_000, wait_after_load_ms))
                await page_setup(page)

            result_ready = await _wait_for_any_result_selector(
                page,
                result_selectors,
                timeout_ms=wait_after_load_ms,
            )
            if result_ready and settle_after_result_ms > 0:
                await page.wait_for_timeout(settle_after_result_ms)

            for selector in result_selectors:
                locator = page.locator(selector)
                if await locator.count():
                    break
            else:
                title = await page.title()
                preview = (await page.content())[:600]
                raise RuntimeError(
                    f"Vendor page returned no parsable results. title={title!r} status={response.status if response else None} preview={preview!r}"
                )

            data = await page.evaluate(extraction_script)
            return data or []
        finally:
            try:
                await asyncio.shield(context.close())
            except Exception:
                pass


async def close_live_browser() -> None:
    global _browser, _browser_lock, _browser_lock_loop, _browser_semaphore, _browser_semaphore_loop, _playwright

    lock = _get_browser_lock()
    async with lock:
        browser = _browser
        playwright = _playwright
        _browser = None
        _playwright = None

        if browser is not None:
            try:
                await browser.close()
            except Exception:
                logger.debug("live_playwright_browser_already_closed", exc_info=True)
        await asyncio.sleep(0)
        if playwright is not None:
            try:
                await playwright.stop()
            except Exception:
                logger.debug("live_playwright_driver_already_closed", exc_info=True)
        _browser_lock = None
        _browser_lock_loop = None
        _browser_semaphore = None
        _browser_semaphore_loop = None


async def _get_browser() -> Browser:
    global _browser, _playwright

    lock = _get_browser_lock()
    async with lock:
        if _browser is not None and _browser.is_connected():
            return _browser

        if _playwright is None:
            _playwright = await async_playwright().start()

        _browser = await _playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-extensions",
            ],
        )
        logger.info("live_playwright_browser_started")
        return _browser


def _get_browser_lock() -> asyncio.Lock:
    global _browser_lock, _browser_lock_loop

    current_loop = asyncio.get_running_loop()
    if _browser_lock is None or _browser_lock_loop is not current_loop or current_loop.is_closed():
        _browser_lock = asyncio.Lock()
        _browser_lock_loop = current_loop
    return _browser_lock


async def _route_request(route) -> None:
    try:
        request = route.request
        if should_block_request(request.resource_type, request.url):
            await route.abort()
            return
        await route.continue_()
    except Exception:
        logger.debug("live_playwright_route_already_closed", exc_info=True)


async def _wait_for_any_result_selector(
    page: Page,
    selectors: Sequence[str],
    *,
    timeout_ms: int,
) -> bool:
    if timeout_ms <= 0:
        return False

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_ms / 1000
    while loop.time() < deadline:
        for selector in selectors:
            if await page.locator(selector).count():
                return True

        remaining_ms = max(int((deadline - loop.time()) * 1000), 0)
        await page.wait_for_timeout(min(150, remaining_ms))

    return False
