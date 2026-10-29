import pytest

from app.scrapers import live_utils


class _ClosedBrowser:
    async def close(self) -> None:
        raise RuntimeError("browser transport already closed")


class _ClosedPlaywright:
    def __init__(self) -> None:
        self.stop_called = False

    async def stop(self) -> None:
        self.stop_called = True
        raise RuntimeError("driver transport already closed")


class _ClosedRoute:
    class _Request:
        resource_type = "document"
        url = "https://example.com/product"

    request = _Request()

    async def continue_(self) -> None:
        raise RuntimeError("page already closed")


@pytest.mark.asyncio
async def test_close_live_browser_tolerates_already_closed_transport(monkeypatch):
    playwright = _ClosedPlaywright()
    monkeypatch.setattr(live_utils, "_browser", _ClosedBrowser())
    monkeypatch.setattr(live_utils, "_playwright", playwright)
    monkeypatch.setattr(live_utils, "_browser_lock", None)

    await live_utils.close_live_browser()

    assert playwright.stop_called
    assert live_utils._browser is None
    assert live_utils._playwright is None
    assert live_utils._browser_lock is None


@pytest.mark.asyncio
async def test_route_request_tolerates_already_closed_page():
    await live_utils._route_request(_ClosedRoute())
