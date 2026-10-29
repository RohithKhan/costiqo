from __future__ import annotations

import asyncio
import logging

from redis import Redis

from app.db.session import session_scope
from app.scrapers.base import SearchContext
from app.services.query_cache_store import QueryCacheStore
from app.services.scrape_service import ScrapeService


logger = logging.getLogger(__name__)


class QueueService:
    def __init__(
        self,
        *,
        queue_backend: str,
        queue_name: str,
        queue_job_timeout_seconds: int,
        queue_result_ttl_seconds: int,
        queue_lock_ttl_seconds: int,
        redis_url: str,
        scrape_service: ScrapeService,
        query_cache_store: QueryCacheStore,
    ) -> None:
        self.scrape_service = scrape_service
        self.query_cache_store = query_cache_store
        self.queue_backend = "inline"
        self.queue_name = queue_name
        self.queue_job_timeout_seconds = queue_job_timeout_seconds
        self.queue_result_ttl_seconds = queue_result_ttl_seconds
        self.queue_lock_ttl_seconds = queue_lock_ttl_seconds
        self.redis_url = redis_url
        self._redis: Redis | None = None
        self._queue = None
        self._background_tasks: set[asyncio.Task[None]] = set()
        self.configure(
            queue_backend=queue_backend,
            queue_name=queue_name,
            queue_job_timeout_seconds=queue_job_timeout_seconds,
            queue_result_ttl_seconds=queue_result_ttl_seconds,
            queue_lock_ttl_seconds=queue_lock_ttl_seconds,
            redis_url=redis_url,
            scrape_service=scrape_service,
            query_cache_store=query_cache_store,
        )

    def configure(
        self,
        *,
        queue_backend: str,
        queue_name: str,
        queue_job_timeout_seconds: int,
        queue_result_ttl_seconds: int,
        queue_lock_ttl_seconds: int,
        redis_url: str,
        scrape_service: ScrapeService,
        query_cache_store: QueryCacheStore,
    ) -> None:
        self.queue_backend = queue_backend.strip().lower()
        self.queue_name = queue_name
        self.queue_job_timeout_seconds = queue_job_timeout_seconds
        self.queue_result_ttl_seconds = queue_result_ttl_seconds
        self.queue_lock_ttl_seconds = queue_lock_ttl_seconds
        self.redis_url = redis_url
        self.scrape_service = scrape_service
        self.query_cache_store = query_cache_store
        self._redis = None
        self._queue = None

    async def trigger_admin_scrape(
        self,
        db,
        query: str,
        *,
        context: SearchContext | None = None,
        source_profile: str = "all",
    ):
        if self.queue_backend != "rq":
            return await self.scrape_service.run_job(
                db,
                query,
                context=context,
                source_profile=source_profile,
            )

        job = self.scrape_service.create_job(db, query)
        self._get_queue().enqueue(
            "app.tasks.scrape_tasks.run_scrape_job_task",
            job.id,
            context.location if context else None,
            context.pincode if context else None,
            source_profile,
            job_timeout=self.queue_job_timeout_seconds,
            result_ttl=self.queue_result_ttl_seconds,
        )
        return job

    def enqueue_background_refresh(
        self,
        query: str,
        *,
        context: SearchContext | None = None,
        source_profile: str = "background",
    ) -> str | None:
        if not self.scrape_service.has_sources(source_profile):
            return None

        queue_key = self.scrape_service.build_cache_key(
            query,
            context,
            source_profile=source_profile,
        )
        if not self.query_cache_store.acquire_lock(queue_key, self.queue_lock_ttl_seconds):
            return None

        if self.queue_backend != "rq":
            self._track_background_task(
                asyncio.create_task(
                    self._run_inline_background_refresh(
                        query,
                        context=context,
                        source_profile=source_profile,
                        queue_key=queue_key,
                    )
                )
            )
            return queue_key

        queued_job = self._get_queue().enqueue(
            "app.tasks.scrape_tasks.run_background_refresh_task",
            query,
            context.location if context else None,
            context.pincode if context else None,
            source_profile,
            job_timeout=self.queue_job_timeout_seconds,
            result_ttl=self.queue_result_ttl_seconds,
        )
        return queued_job.id

    async def _run_inline_background_refresh(
        self,
        query: str,
        *,
        context: SearchContext | None,
        source_profile: str,
        queue_key: str,
    ) -> None:
        try:
            with session_scope() as db:
                await self.scrape_service.scrape_query(
                    db,
                    query,
                    context=context,
                    source_profile=source_profile,
                    force=True,
                )
        except Exception as exc:
            logger.warning(
                "inline_background_refresh_failed query=%s source_profile=%s error_type=%s error=%s",
                query,
                source_profile,
                type(exc).__name__,
                exc,
            )
        finally:
            self.query_cache_store.release_lock(queue_key)

    def _track_background_task(self, task: asyncio.Task[None]) -> None:
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def close_background_tasks(self) -> None:
        tasks = tuple(self._background_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._background_tasks.difference_update(tasks)

    def _get_queue(self):
        try:
            from rq import Queue
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "QUEUE_BACKEND=rq requires the 'rq' package to be installed."
            ) from exc
        if self._queue is None:
            self._redis = Redis.from_url(self.redis_url, decode_responses=True)
            self._queue = Queue(self.queue_name, connection=self._redis)
        return self._queue
