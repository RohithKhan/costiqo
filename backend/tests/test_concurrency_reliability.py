import asyncio
from concurrent.futures import ThreadPoolExecutor
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI, Request
from starlette.responses import JSONResponse, Response
from starlette.testclient import TestClient

from app.core.http_middleware import RateLimitMiddleware
from app.scrapers.hardware_scraper_utils import (
    close_shared_clients,
    fetch_html,
    fetch_json,
    get_shared_client,
    post_json,
)
from app.scrapers.live_utils import (
    _get_browser_lock,
    close_live_browser,
)
from app.services.search_progress_service import SearchProgress, SearchProgressService
from app.services.scrape_service import ScrapeService, ScraperResult


# =========================================================================
# TASK 1: RATE LIMITER TESTS
# =========================================================================

def test_rate_limiter_normal_and_429_behavior():
    app = FastAPI()

    @app.get("/test")
    def endpoint():
        return {"ok": True}

    # Limit = 2 requests per 60 seconds
    app.add_middleware(RateLimitMiddleware, request_limit=2, window_seconds=60)

    with TestClient(app) as client:
        # Request 1: allowed
        r1 = client.get("/test", headers={"Authorization": "Bearer test-client-token-1"})
        assert r1.status_code == 200
        assert r1.headers["X-RateLimit-Limit"] == "2"
        assert r1.headers["X-RateLimit-Remaining"] == "1"

        # Request 2: allowed
        r2 = client.get("/test", headers={"Authorization": "Bearer test-client-token-1"})
        assert r2.status_code == 200
        assert r2.headers["X-RateLimit-Remaining"] == "0"

        # Request 3: rate limited (429)
        r3 = client.get("/test", headers={"Authorization": "Bearer test-client-token-1"})
        assert r3.status_code == 429
        assert "Retry-After" in r3.headers
        assert r3.json()["detail"] == "Too many requests. Please try again shortly."

        # Request from another client is unaffected
        r_other = client.get("/test", headers={"Authorization": "Bearer test-client-token-2"})
        assert r_other.status_code == 200


def test_rate_limiter_bucket_eviction_and_empty_removal():
    from collections import deque
    app = FastAPI()
    middleware = RateLimitMiddleware(
        app,
        request_limit=5,
        window_seconds=10,
        cleanup_interval_seconds=100.0,
    )

    now = 1000.0
    # Add requests for 3 clients
    with middleware._lock:
        middleware._requests["client1"] = deque([991.0, 995.0]) # still active at now=1000 (window 10s -> min 990)
        middleware._requests["client2"] = deque([980.0, 985.0]) # fully expired (< 990)
        middleware._requests["client3"] = deque([988.0])        # fully expired (< 990)

    assert middleware.tracked_client_count == 3

    # Run cleanup at now = 1000.0
    evicted = middleware.cleanup(now=1000.0)

    # client2 and client3 had all timestamps expired, so their buckets became empty and were removed
    assert evicted == 2
    assert middleware.tracked_client_count == 1
    assert "client1" in middleware._requests
    assert "client2" not in middleware._requests
    assert "client3" not in middleware._requests


def test_rate_limiter_capacity_eviction():
    from collections import deque
    app = FastAPI()
    # Max tracked clients = 3
    middleware = RateLimitMiddleware(
        app,
        request_limit=10,
        window_seconds=60,
        max_tracked_clients=3,
        cleanup_interval_seconds=30.0,
    )

    now = 1000.0
    with middleware._lock:
        middleware._requests["c1"] = deque([990.0])
        middleware._requests["c2"] = deque([992.0])
        middleware._requests["c3"] = deque([995.0])

    assert middleware.tracked_client_count == 3

    # Add a 4th client and enforce capacity
    with middleware._lock:
        middleware._enforce_capacity_locked(now=now)
        middleware._requests["c4"] = deque([now])

    # Should remain bounded at max_tracked_clients
    assert middleware.tracked_client_count <= 3
    # The oldest idle client (c1) was evicted
    assert "c1" not in middleware._requests
    assert "c4" in middleware._requests


def test_rate_limiter_concurrent_access_safety():
    from collections import deque
    app = FastAPI()
    middleware = RateLimitMiddleware(
        app,
        request_limit=100,
        window_seconds=60,
        max_tracked_clients=1000,
    )

    def record_request(client_id: int):
        now = time.monotonic()
        key = f"client_{client_id % 10}"
        with middleware._lock:
            bucket = middleware._requests.get(key)
            if bucket is None:
                bucket = deque()
                middleware._requests[key] = bucket
            bucket.append(now)

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(record_request, i) for i in range(200)]
        for f in futures:
            f.result()

    assert middleware.tracked_client_count <= 10


# =========================================================================
# TASK 2: SEARCH PROGRESS TESTS
# =========================================================================

def test_search_progress_lifecycle():
    service = SearchProgressService(ttl_seconds=10.0, completed_ttl_seconds=2.0)

    # 1. Start
    p1 = service.start("prog_1")
    assert p1.progress_id == "prog_1"
    assert p1.status == "running"
    assert p1.offer_count == 0

    # 2. Update
    p2 = service.update("prog_1", offer_count=5)
    assert p2.offer_count == 5
    assert p2.status == "running"

    # Monotonic offer count
    service.update("prog_1", offer_count=3)
    assert service.get("prog_1").offer_count == 5

    # 3. Complete
    p3 = service.complete("prog_1", offer_count=12)
    assert p3.status == "complete"
    assert p3.offer_count == 12

    # 4. Unknown id
    p_unk = service.get("nonexistent")
    assert p_unk.status == "missing"


def test_search_progress_expiration_and_capacity():
    service = SearchProgressService(
        ttl_seconds=10.0,
        completed_ttl_seconds=2.0,
        max_items=3,
    )

    now = time.monotonic()
    with service._lock:
        service._items["active"] = SearchProgress("active", offer_count=2, status="running", updated_at=now - 2.0)
        service._items["old_completed"] = SearchProgress("old_completed", offer_count=5, status="complete", updated_at=now - 5.0)
        service._items["abandoned"] = SearchProgress("abandoned", offer_count=1, status="running", updated_at=now - 20.0)

    # Retrieve 'active' -> triggers cleanup
    res = service.get("active")
    assert res.status == "running"

    with service._lock:
        # 'old_completed' (> 2.0s) and 'abandoned' (> 10.0s) were purged
        assert "old_completed" not in service._items
        assert "abandoned" not in service._items
        assert "active" in service._items


def test_search_progress_redis_fallback():
    # Pass an unreachable Redis URL
    service = SearchProgressService(redis_url="redis://127.0.0.1:59999/0")

    # Should gracefully fall back to in-memory store without raising an exception
    p = service.start("prog_fallback")
    assert p.progress_id == "prog_fallback"
    assert p.status == "running"

    service.update("prog_fallback", 8)
    fetched = service.get("prog_fallback")
    assert fetched.offer_count == 8

    # Circuit breaker is active
    assert not service._is_redis_available()


# =========================================================================
# TASK 3: HTTPX CONNECTION REUSE AND LIFECYCLE
# =========================================================================

@pytest.mark.asyncio
async def test_httpx_shared_client_reuse():
    loop = asyncio.get_running_loop()
    client1 = get_shared_client()
    client2 = get_shared_client()

    # Reuses the exact same AsyncClient instance on the current loop
    assert client1 is client2
    assert not client1.is_closed

    # Cleanup closes all connections
    await close_shared_clients()
    assert client1.is_closed


@pytest.mark.asyncio
async def test_httpx_fetch_functions_use_custom_headers_and_reuse_client():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "<html><body>Test</body></html>"
    mock_response.json.return_value = {"message": "success"}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.post.return_value = mock_response

    # fetch_html with custom client
    html = await fetch_html("https://example.com/test", user_agent="CustomAgent", client=mock_client)
    assert html == "<html><body>Test</body></html>"
    mock_client.get.assert_called_once()
    assert mock_client.get.call_args[1]["headers"]["user-agent"] == "CustomAgent"

    # fetch_json with custom client
    mock_client.get.reset_mock()
    data = await fetch_json("https://example.com/api", extra_headers={"X-Custom": "val"}, client=mock_client)
    assert data == {"message": "success"}
    assert mock_client.get.call_args[1]["headers"]["X-Custom"] == "val"

    # post_json with custom client
    mock_client.post.reset_mock()
    res = await post_json("https://example.com/api", payload={"key": "val"}, client=mock_client)
    assert res == {"message": "success"}
    assert mock_client.post.call_args[1]["json"] == {"key": "val"}


# =========================================================================
# TASK 4: BROWSER AND BACKGROUND TASK CLEANUP
# =========================================================================

@pytest.mark.asyncio
async def test_live_browser_lock_is_loop_safe():
    current_loop = asyncio.get_running_loop()
    lock1 = _get_browser_lock()
    lock2 = _get_browser_lock()
    assert lock1 is lock2

    # Closing browser resets the lock
    await close_live_browser()
    lock3 = _get_browser_lock()
    assert lock3 is not None


@pytest.mark.asyncio
async def test_scrape_service_active_task_cleanup():
    service = ScrapeService(
        scrapers_by_source={},
        primary_sources=[],
        background_sources=[],
        sentiment_service=MagicMock(),
        query_cache_store=MagicMock(),
    )

    async def dummy_coro():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            pass

    t1 = asyncio.create_task(dummy_coro())
    t2 = asyncio.create_task(dummy_coro())
    service._track_scraper_tasks([t1, t2])

    assert len(service._active_scraper_tasks) == 2
    assert not t1.cancelled() and not t2.cancelled()

    # Shutdown cancels all tracked tasks
    await service.close_background_tasks()
    assert t1.cancelled()
    assert t2.cancelled()
    assert len(service._active_scraper_tasks) == 0
