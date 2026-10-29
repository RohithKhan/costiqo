from __future__ import annotations

import time
from collections import deque
from threading import Lock

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        request_limit: int,
        window_seconds: int,
        max_tracked_clients: int = 10_000,
        cleanup_interval_seconds: float = 30.0,
    ) -> None:
        super().__init__(app)
        self.request_limit = max(1, request_limit)
        self.window_seconds = max(1, window_seconds)
        self.max_tracked_clients = max(1, max_tracked_clients)
        self.cleanup_interval_seconds = max(1.0, cleanup_interval_seconds)
        self._requests: dict[str, deque[float]] = {}
        self._last_cleanup = time.monotonic()
        self._lock = Lock()

    @property
    def tracked_client_count(self) -> int:
        with self._lock:
            return len(self._requests)

    def clear(self) -> None:
        with self._lock:
            self._requests.clear()
            self._last_cleanup = time.monotonic()

    def cleanup(self, now: float | None = None) -> int:
        with self._lock:
            return self._cleanup_locked(now or time.monotonic())

    def _cleanup_locked(self, now: float) -> int:
        evicted = 0
        to_remove = []
        for key, bucket in self._requests.items():
            while bucket and now - bucket[0] >= self.window_seconds:
                bucket.popleft()
            if not bucket:
                to_remove.append(key)
        for key in to_remove:
            del self._requests[key]
            evicted += 1
        self._last_cleanup = now
        return evicted

    def _enforce_capacity_locked(self, now: float) -> None:
        if len(self._requests) < self.max_tracked_clients:
            return
        # Run expired cleanup first
        self._cleanup_locked(now)
        if len(self._requests) < self.max_tracked_clients:
            return
        # Evict oldest idle clients if still at or over capacity
        excess = len(self._requests) - self.max_tracked_clients + 1
        sorted_clients = sorted(
            self._requests.items(),
            key=lambda item: item[1][-1] if item[1] else 0.0,
        )
        for key, _ in sorted_clients[:excess]:
            self._requests.pop(key, None)

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in {"/", "/health"}:
            return await call_next(request)

        now = time.monotonic()
        key = self._rate_limit_key(request)
        with self._lock:
            if now - self._last_cleanup >= self.cleanup_interval_seconds:
                self._cleanup_locked(now)

            bucket = self._requests.get(key)
            if bucket is None:
                self._enforce_capacity_locked(now)
                bucket = deque()
                self._requests[key] = bucket
            else:
                while bucket and now - bucket[0] >= self.window_seconds:
                    bucket.popleft()

            remaining = self.request_limit - len(bucket)
            if remaining <= 0:
                retry_after = max(1, int(self.window_seconds - (now - bucket[0]))) if bucket else self.window_seconds
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please try again shortly."},
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(self.request_limit),
                        "X-RateLimit-Remaining": "0",
                    },
                )
            bucket.append(now)
            remaining -= 1

        response = await call_next(request)
        response.headers.setdefault("X-RateLimit-Limit", str(self.request_limit))
        response.headers.setdefault("X-RateLimit-Remaining", str(max(0, remaining)))
        return response

    def _rate_limit_key(self, request: Request) -> str:
        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            return f"token:{authorization[-32:]}"
        host = request.client.host if request.client else "unknown"
        return f"ip:{host}"


def add_security_headers(app: FastAPI) -> None:
    @app.middleware("http")
    async def security_headers(request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'",
        )
        return response
