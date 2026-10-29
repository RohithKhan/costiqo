from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import logging
from threading import Lock
from time import monotonic

from redis import Redis
from redis.exceptions import RedisError


logger = logging.getLogger(__name__)


@dataclass
class SearchProgress:
    progress_id: str
    offer_count: int = 0
    status: str = "running"
    updated_at: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> SearchProgress:
        return cls(
            progress_id=str(data.get("progress_id", "")),
            offer_count=int(data.get("offer_count", 0)),
            status=str(data.get("status", "running")),
            updated_at=float(data.get("updated_at", 0.0)),
        )


class SearchProgressService:
    def __init__(
        self,
        redis_url: str | None = None,
        *,
        ttl_seconds: float = 180.0,
        completed_ttl_seconds: float = 60.0,
        max_items: int = 5_000,
        namespace: str = "costiqo:progress",
    ) -> None:
        self.ttl_seconds = max(5.0, ttl_seconds)
        self.completed_ttl_seconds = max(1.0, completed_ttl_seconds)
        self.max_items = max(100, max_items)
        self.namespace = namespace
        self._items: dict[str, SearchProgress] = {}
        self._lock = Lock()
        self._redis: Redis | None = None
        self._redis_unreachable_until: float = 0.0
        self.configure(redis_url)

    def configure(self, redis_url: str | None) -> None:
        with self._lock:
            self._redis_unreachable_until = 0.0
            if redis_url:
                try:
                    self._redis = Redis.from_url(
                        redis_url,
                        decode_responses=True,
                        socket_connect_timeout=0.2,
                        socket_timeout=0.2,
                    )
                except RedisError:
                    self._redis = None
            else:
                self._redis = None

    def _is_redis_available(self) -> bool:
        if self._redis is None:
            return False
        if monotonic() < self._redis_unreachable_until:
            return False
        return True

    def _mark_redis_failure(self) -> None:
        self._redis_unreachable_until = monotonic() + 30.0

    def _redis_key(self, progress_id: str) -> str:
        return f"{self.namespace}:{progress_id}"

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            if self._is_redis_available():
                try:
                    keys = list(self._redis.scan_iter(f"{self.namespace}:*"))
                    if keys:
                        self._redis.delete(*keys)
                except RedisError:
                    self._mark_redis_failure()

    def start(self, progress_id: str) -> SearchProgress:
        now = monotonic()
        progress = SearchProgress(
            progress_id=progress_id,
            offer_count=0,
            status="running",
            updated_at=now,
        )
        self._persist_progress(progress, ttl=int(self.ttl_seconds))
        return progress

    def update(self, progress_id: str, offer_count: int) -> SearchProgress:
        now = monotonic()
        existing = self._fetch_progress(progress_id)
        if existing is None:
            existing = SearchProgress(progress_id=progress_id, offer_count=offer_count, status="running", updated_at=now)
        else:
            existing.offer_count = max(existing.offer_count, offer_count)
            existing.status = "running"
            existing.updated_at = now
        self._persist_progress(existing, ttl=int(self.ttl_seconds))
        return existing

    def complete(self, progress_id: str, offer_count: int) -> SearchProgress:
        now = monotonic()
        existing = self._fetch_progress(progress_id)
        if existing is None:
            existing = SearchProgress(progress_id=progress_id, offer_count=offer_count, status="complete", updated_at=now)
        else:
            existing.offer_count = offer_count
            existing.status = "complete"
            existing.updated_at = now
        self._persist_progress(existing, ttl=int(self.completed_ttl_seconds))
        return existing

    def fail(self, progress_id: str) -> SearchProgress:
        now = monotonic()
        existing = self._fetch_progress(progress_id)
        if existing is None:
            existing = SearchProgress(progress_id=progress_id, offer_count=0, status="failed", updated_at=now)
        else:
            existing.status = "failed"
            existing.updated_at = now
        self._persist_progress(existing, ttl=int(self.completed_ttl_seconds))
        return existing

    def get(self, progress_id: str) -> SearchProgress:
        progress = self._fetch_progress(progress_id)
        if progress is None:
            return SearchProgress(
                progress_id=progress_id,
                offer_count=0,
                status="missing",
                updated_at=monotonic(),
            )
        return progress

    def _fetch_progress(self, progress_id: str) -> SearchProgress | None:
        if self._is_redis_available():
            try:
                raw = self._redis.get(self._redis_key(progress_id))
                if raw:
                    return SearchProgress.from_dict(json.loads(raw))
            except (RedisError, ValueError):
                self._mark_redis_failure()

        with self._lock:
            self._cleanup_in_memory_locked()
            return self._items.get(progress_id)

    def _persist_progress(self, progress: SearchProgress, *, ttl: int) -> None:
        if self._is_redis_available():
            try:
                key = self._redis_key(progress.progress_id)
                self._redis.set(key, json.dumps(progress.to_dict()), ex=max(ttl, 1))
            except RedisError:
                self._mark_redis_failure()

        with self._lock:
            self._cleanup_in_memory_locked()
            if len(self._items) >= self.max_items and progress.progress_id not in self._items:
                # Evict oldest item
                oldest_id = min(self._items, key=lambda pid: self._items[pid].updated_at)
                self._items.pop(oldest_id, None)
            self._items[progress.progress_id] = progress

    def _cleanup_in_memory_locked(self) -> None:
        now = monotonic()
        expired: list[str] = []
        for progress_id, progress in self._items.items():
            threshold = self.completed_ttl_seconds if progress.status in {"complete", "failed"} else self.ttl_seconds
            if now - progress.updated_at > threshold:
                expired.append(progress_id)
        for progress_id in expired:
            self._items.pop(progress_id, None)
