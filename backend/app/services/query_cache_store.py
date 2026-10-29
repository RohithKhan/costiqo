from __future__ import annotations

from time import monotonic

from redis import Redis
from redis.exceptions import RedisError


class QueryCacheStore:
    def __init__(self, redis_url: str | None, namespace: str = "costiqo:query") -> None:
        self.namespace = namespace
        self._memory_fresh_until: dict[str, float] = {}
        self._memory_locks: dict[str, float] = {}
        self._redis: Redis | None = None
        self._redis_unreachable_until: float = 0.0
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

    def _is_redis_available(self) -> bool:
        if self._redis is None:
            return False
        if monotonic() < self._redis_unreachable_until:
            return False
        return True

    def _mark_redis_failure(self) -> None:
        self._redis_unreachable_until = monotonic() + 30.0

    def clear(self) -> None:
        self._memory_fresh_until.clear()
        self._memory_locks.clear()
        if self._is_redis_available():
            try:
                keys = list(self._redis.scan_iter(f"{self.namespace}:*"))
                if keys:
                    self._redis.delete(*keys)
            except RedisError:
                self._mark_redis_failure()

    def is_fresh(self, key: str) -> bool:
        redis_key = self._fresh_key(key)
        if self._is_redis_available():
            try:
                return bool(self._redis.exists(redis_key))
            except RedisError:
                self._mark_redis_failure()
        expires_at = self._memory_fresh_until.get(redis_key)
        return expires_at is not None and expires_at > monotonic()

    def mark_fresh(self, key: str, ttl_seconds: int) -> None:
        redis_key = self._fresh_key(key)
        if self._is_redis_available():
            try:
                self._redis.set(redis_key, "1", ex=max(ttl_seconds, 1))
                return
            except RedisError:
                self._mark_redis_failure()
        self._memory_fresh_until[redis_key] = monotonic() + max(ttl_seconds, 1)

    def acquire_lock(self, key: str, ttl_seconds: int) -> bool:
        redis_key = self._lock_key(key)
        ttl = max(ttl_seconds, 1)
        if self._is_redis_available():
            try:
                return bool(self._redis.set(redis_key, "1", ex=ttl, nx=True))
            except RedisError:
                self._mark_redis_failure()
        expires_at = self._memory_locks.get(redis_key)
        now = monotonic()
        if expires_at is not None and expires_at > now:
            return False
        self._memory_locks[redis_key] = now + ttl
        return True

    def release_lock(self, key: str) -> None:
        redis_key = self._lock_key(key)
        if self._is_redis_available():
            try:
                self._redis.delete(redis_key)
                return
            except RedisError:
                self._mark_redis_failure()
        self._memory_locks.pop(redis_key, None)

    def _fresh_key(self, key: str) -> str:
        return f"{self.namespace}:fresh:{key}"

    def _lock_key(self, key: str) -> str:
        return f"{self.namespace}:lock:{key}"
