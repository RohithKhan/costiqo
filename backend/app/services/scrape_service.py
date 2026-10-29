from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
import re

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.models.price_snapshot import PriceSnapshot
from app.db.models.product import Product
from app.db.models.review import Review
from app.db.models.scrape_job import ScrapeJob
from app.db.models.vendor import Vendor
from app.db.models.vendor_product import VendorProduct
from app.scrapers.base import BaseScraper, ScrapedListing, SearchContext
from app.scrapers.normalizers import listing_matches_query, match_score
from app.services.query_cache_store import QueryCacheStore
from app.services.search_diagnostics import SearchDiagnostics, SearchFilterDiagnostic
from app.services.sentiment_service import SentimentService
from app.utils.product_identity import are_model_keys_compatible
from app.utils.time_utils import utc_now


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ScraperResult:
    scraper: BaseScraper
    listings: list[ScrapedListing]
    error: Exception | None = None
    diagnostics: SearchDiagnostics | None = None


@dataclass(frozen=True, slots=True)
class SearchCoverageRequirement:
    key: str
    label: str
    vendors: tuple[str, ...]
    minimum_matched_offers: int = 1


class ScrapeService:
    def __init__(
        self,
        scrapers_by_source: dict[str, BaseScraper],
        primary_sources: list[str],
        background_sources: list[str],
        sentiment_service: SentimentService,
        query_cache_store: QueryCacheStore,
        *,
        cache_ttl_seconds: int = 900,
        background_cache_ttl_seconds: int = 3600,
        retry_attempts: int = 2,
        retry_backoff_seconds: float = 1.0,
    ) -> None:
        self.sentiment_service = sentiment_service
        self.query_cache_store = query_cache_store
        self.scrapers_by_source: dict[str, BaseScraper] = {}
        self.primary_sources: list[str] = []
        self.background_sources: list[str] = []
        self.cache_ttl_seconds = cache_ttl_seconds
        self.background_cache_ttl_seconds = background_cache_ttl_seconds
        self.retry_attempts = retry_attempts
        self.retry_backoff_seconds = retry_backoff_seconds
        self._background_tasks: set[asyncio.Task[None]] = set()
        self._active_scraper_tasks: set[asyncio.Task] = set()
        self._scraper_semaphore: asyncio.Semaphore | None = None
        self._inflight_scrapes: dict[tuple[str, str, str | None], asyncio.Task[ScraperResult]] = {}
        self.configure(
            scrapers_by_source=scrapers_by_source,
            primary_sources=primary_sources,
            background_sources=background_sources,
            query_cache_store=query_cache_store,
            cache_ttl_seconds=cache_ttl_seconds,
            background_cache_ttl_seconds=background_cache_ttl_seconds,
            retry_attempts=retry_attempts,
            retry_backoff_seconds=retry_backoff_seconds,
        )

    @property
    def scrapers(self) -> list[BaseScraper]:
        return list(self.scrapers_by_source.values())

    @scrapers.setter
    def scrapers(self, scrapers: list[BaseScraper]) -> None:
        scrapers_by_source = {
            self._derive_source_name(scraper): scraper
            for scraper in scrapers
        }
        source_names = list(scrapers_by_source)
        self.configure(
            scrapers_by_source=scrapers_by_source,
            primary_sources=source_names,
            background_sources=[],
        )

    def configure(
        self,
        *,
        scrapers_by_source: dict[str, BaseScraper] | None = None,
        primary_sources: list[str] | None = None,
        background_sources: list[str] | None = None,
        query_cache_store: QueryCacheStore | None = None,
        cache_ttl_seconds: int | None = None,
        background_cache_ttl_seconds: int | None = None,
        retry_attempts: int | None = None,
        retry_backoff_seconds: float | None = None,
    ) -> None:
        if scrapers_by_source is not None:
            self.scrapers_by_source = dict(scrapers_by_source)
        if primary_sources is not None:
            self.primary_sources = [
                source for source in primary_sources if source in self.scrapers_by_source
            ]
        if background_sources is not None:
            self.background_sources = [
                source for source in background_sources if source in self.scrapers_by_source
            ]
        if query_cache_store is not None:
            self.query_cache_store = query_cache_store
        if cache_ttl_seconds is not None:
            self.cache_ttl_seconds = cache_ttl_seconds
        if background_cache_ttl_seconds is not None:
            self.background_cache_ttl_seconds = background_cache_ttl_seconds
        if retry_attempts is not None:
            self.retry_attempts = retry_attempts
        if retry_backoff_seconds is not None:
            self.retry_backoff_seconds = retry_backoff_seconds

    def clear_cache(self) -> None:
        self.query_cache_store.clear()

    def bootstrap_vendors(self, db: Session) -> None:
        self._purge_legacy_catalog_records(db)
        for scraper in self.scrapers_by_source.values():
            vendor = db.scalar(select(Vendor).where(Vendor.name == scraper.vendor_name))
            if vendor is None:
                vendor = Vendor(
                    name=scraper.vendor_name,
                    base_url=scraper.base_url,
                    scrape_strategy=scraper.scrape_strategy,
                    last_status="idle",
                )
                db.add(vendor)
            else:
                vendor.base_url = scraper.base_url
                vendor.scrape_strategy = scraper.scrape_strategy
                vendor.is_active = True
        db.commit()

    async def scrape_query(
        self,
        db: Session,
        query: str,
        context: SearchContext | None = None,
        *,
        source_profile: str = "all",
        source_names: list[str] | None = None,
        force: bool = False,
    ) -> list[VendorProduct]:
        cache_key = self.build_cache_key(
            query,
            context,
            source_profile=source_profile,
            source_names=source_names,
        )
        scrapers = self._resolve_scrapers(source_profile, source_names=source_names)
        if not scrapers:
            logger.info(
                "provider_selection_empty query=%s source_profile=%s source_names=%s context=%s",
                query,
                source_profile,
                ",".join(source_names or []),
                context.cache_key() if context is not None else "none",
            )
            return self._load_existing_results(db, query)

        if not force and self.query_cache_store.is_fresh(cache_key):
            logger.info(
                "provider_cache_hit query=%s source_profile=%s cache_key=%s",
                query,
                source_profile,
                cache_key,
            )
            return self._load_existing_results(db, query)

        upserted_listings: list[VendorProduct] = []
        results = await asyncio.gather(
            *(self._search_with_retry(scraper, query, context) for scraper in scrapers)
        )
        any_success = False

        for result in results:
            source_vendor = self._ensure_vendor(
                db,
                result.scraper.vendor_name,
                result.scraper.base_url,
                result.scraper.scrape_strategy,
            )
            if result.error is not None:
                source_vendor.last_scraped_at = utc_now()
                source_vendor.last_status = f"error:{type(result.error).__name__}"
                logger.warning(
                    "provider_failure vendor=%s query=%s source_profile=%s context=%s error_type=%s error=%s",
                    result.scraper.vendor_name,
                    query,
                    source_profile,
                    context.cache_key() if context is not None else "none",
                    type(result.error).__name__,
                    result.error,
                )
                continue

            any_success = True
            for listing in result.listings:
                vendor = self._ensure_vendor(
                    db,
                    listing.vendor or result.scraper.vendor_name,
                    listing.base_url or result.scraper.base_url,
                    listing.scrape_strategy or result.scraper.scrape_strategy,
                )
                vendor_product = self._upsert_listing(db, vendor, listing)
                upserted_listings.append(vendor_product)

            source_vendor.last_scraped_at = utc_now()
            source_vendor.last_status = "ok" if result.listings else "no-match"

        db.commit()
        if any_success:
            self.query_cache_store.mark_fresh(
                cache_key,
                self._cache_ttl_for_profile(source_profile),
            )
        return upserted_listings

    async def fetch_live_listings(
        self,
        query: str,
        context: SearchContext | None = None,
        *,
        source_profile: str = "all",
        source_names: list[str] | None = None,
        foreground_timeout_seconds: float | None = None,
        source_foreground_timeout_seconds: dict[str, float] | None = None,
        progress_callback: Callable[[int], None] | None = None,
    ) -> list[ScrapedListing]:
        live_listings, _ = await self.fetch_live_listings_with_diagnostics(
            query,
            context,
            source_profile=source_profile,
            source_names=source_names,
            foreground_timeout_seconds=foreground_timeout_seconds,
            source_foreground_timeout_seconds=source_foreground_timeout_seconds,
            progress_callback=progress_callback,
        )
        return live_listings

    async def fetch_live_listings_with_diagnostics(
        self,
        query: str,
        context: SearchContext | None = None,
        *,
        source_profile: str = "all",
        source_names: list[str] | None = None,
        foreground_timeout_seconds: float | None = None,
        source_foreground_timeout_seconds: dict[str, float] | None = None,
        coverage_timeout_seconds: float | None = None,
        coverage_requirements: tuple[SearchCoverageRequirement, ...] = (),
        continue_timed_out_searches: bool = True,
        progress_callback: Callable[[int], None] | None = None,
    ) -> tuple[list[ScrapedListing], SearchDiagnostics]:
        scrapers = self._resolve_scrapers(source_profile, source_names=source_names)
        diagnostics = SearchDiagnostics(
            query=query,
            source_profile=source_profile,
            location=context.effective_location if context is not None else None,
            pincode=context.pincode if context is not None else None,
            sources_checked=[scraper.vendor_name for scraper in scrapers],
        )
        if not scrapers:
            logger.info(
                "provider_selection_empty query=%s source_profile=%s source_names=%s context=%s",
                query,
                source_profile,
                ",".join(source_names or []),
                context.cache_key() if context is not None else "none",
            )
            return [], diagnostics

        tasks = [
            asyncio.create_task(self._search_with_retry(scraper, query, context))
            for scraper in scrapers
        ]
        self._track_scraper_tasks(tasks)
        if foreground_timeout_seconds is None:
            results = []
            pending = set(tasks)
            while pending:
                next_done, pending = await asyncio.wait(
                    pending,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                results.extend(self._task_results(next_done))
                self._publish_progress(results, progress_callback)
        else:
            loop = asyncio.get_running_loop()
            started_at = loop.time()
            foreground_timeout = max(foreground_timeout_seconds, 0.01)
            coverage_timeout = max(
                coverage_timeout_seconds or foreground_timeout,
                foreground_timeout,
            )
            results = []
            pending = set(tasks)
            foreground_deadline = started_at + foreground_timeout
            while pending:
                remaining_seconds = foreground_deadline - loop.time()
                if remaining_seconds <= 0:
                    break
                next_done, pending = await asyncio.wait(
                    pending,
                    timeout=remaining_seconds,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not next_done:
                    break
                results.extend(self._task_results(next_done))
                self._publish_progress(results, progress_callback)

            unmet_requirements = self._unmet_coverage_requirements(
                query,
                results,
                coverage_requirements,
            )
            if unmet_requirements and pending and coverage_timeout > foreground_timeout:
                diagnostics.add_filter(
                    SearchFilterDiagnostic(
                        key="source_coverage_wait",
                        label="Required source coverage wait",
                        detail=(
                            "Waited past the fast search deadline for "
                            f"{self._format_coverage_labels(unmet_requirements)}."
                        ),
                        active=True,
                        removed_count=0,
                    )
                )
                hard_deadline = started_at + coverage_timeout
                while pending and unmet_requirements:
                    remaining_seconds = hard_deadline - loop.time()
                    if remaining_seconds <= 0:
                        break
                    next_done, pending = await asyncio.wait(
                        pending,
                        timeout=remaining_seconds,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if not next_done:
                        break
                    results.extend(self._task_results(next_done))
                    self._publish_progress(results, progress_callback)
                    unmet_requirements = self._unmet_coverage_requirements(
                        query,
                        results,
                        coverage_requirements,
                    )

            override_wait_sources: tuple[str, ...] = ()
            if pending and source_foreground_timeout_seconds:
                pending, override_wait_sources = await self._wait_for_source_foreground_overrides(
                    pending,
                    results,
                    source_foreground_timeout_seconds,
                    started_at=started_at,
                    loop=loop,
                )
                if override_wait_sources:
                    self._publish_progress(results, progress_callback)
                    unmet_requirements = self._unmet_coverage_requirements(
                        query,
                        results,
                        coverage_requirements,
                    )
                    diagnostics.add_filter(
                        SearchFilterDiagnostic(
                            key="source_specific_foreground_wait",
                            label="Source-specific foreground wait",
                            detail=(
                                "Waited longer for "
                                f"{', '.join(override_wait_sources)} before returning."
                            ),
                            active=True,
                            removed_count=0,
                        )
                    )

            if unmet_requirements:
                diagnostics.add_filter(
                    SearchFilterDiagnostic(
                        key="source_coverage_incomplete",
                        label="Incomplete source coverage",
                        detail=(
                            "Returned the best available offers, but did not receive "
                            f"{self._format_coverage_labels(unmet_requirements)} before the deadline."
                        ),
                        active=True,
                        removed_count=len(unmet_requirements),
                    )
                )

            if pending:
                pending_sources = [
                    self._task_scraper_name(task)
                    for task in pending
                ]
                elapsed_seconds = loop.time() - started_at
                logger.info(
                    "provider_foreground_timeout query=%s source_profile=%s completed=%s pending=%s timeout_seconds=%.2f pending_sources=%s",
                    query,
                    source_profile,
                    len(tasks) - len(pending),
                    len(pending),
                    elapsed_seconds,
                    ",".join(pending_sources),
                )
                diagnostics.add_filter(
                    SearchFilterDiagnostic(
                        key="foreground_timeout",
                        label="Foreground search deadline",
                        detail=(
                            f"Returned sources that finished within {elapsed_seconds:.1f}s; "
                            f"{len(pending)} source(s) continued in the background."
                        ),
                        active=True,
                        removed_count=len(pending),
                    )
                )
                if continue_timed_out_searches:
                    self._track_background_task(
                        asyncio.create_task(
                            self._drain_timed_out_searches(
                                pending,
                                query=query,
                                context=context,
                                source_profile=source_profile,
                            )
                        )
                    )
                else:
                    for task in pending:
                        task.cancel()

        live_listings: list[ScrapedListing] = []
        for result in results:
            if result.diagnostics is not None:
                self._merge_search_diagnostics(diagnostics, result.diagnostics)
            if result.error is not None:
                logger.warning(
                    "provider_failure vendor=%s query=%s source_profile=%s context=%s error_type=%s error=%s",
                    result.scraper.vendor_name,
                    query,
                    source_profile,
                    context.cache_key() if context is not None else "none",
                    type(result.error).__name__,
                    result.error,
                )
                continue

            live_listings.extend(result.listings)

        diagnostics.matched_offer_count = len(live_listings)
        return live_listings, diagnostics

    def _task_results(
        self,
        tasks: set[asyncio.Task[ScraperResult]],
    ) -> list[ScraperResult]:
        return [
            task.result()
            for task in tasks
            if not task.cancelled()
        ]

    def _publish_progress(
        self,
        results: list[ScraperResult],
        progress_callback: Callable[[int], None] | None,
    ) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(self._received_offer_count(results))
        except Exception:
            logger.exception("search_progress_update_failed")

    def _received_offer_count(self, results: list[ScraperResult]) -> int:
        return sum(
            len(result.listings)
            for result in results
            if result.error is None
        )

    async def _wait_for_source_foreground_overrides(
        self,
        pending: set[asyncio.Task[ScraperResult]],
        results: list[ScraperResult],
        source_timeouts: dict[str, float],
        *,
        started_at: float,
        loop: asyncio.AbstractEventLoop,
    ) -> tuple[set[asyncio.Task[ScraperResult]], tuple[str, ...]]:
        normalized_timeouts = {
            source_name.strip().lower(): max(timeout_seconds, 0.01)
            for source_name, timeout_seconds in source_timeouts.items()
            if source_name and source_name.strip()
        }
        waited_sources: set[str] = set()

        while pending:
            now = loop.time()
            eligible_deadlines: dict[asyncio.Task[ScraperResult], float] = {}
            for task in pending:
                scraper_name = self._task_scraper_name(task)
                timeout_seconds = normalized_timeouts.get(scraper_name.lower())
                if timeout_seconds is None:
                    continue
                deadline = started_at + timeout_seconds
                if deadline > now:
                    eligible_deadlines[task] = deadline
                    waited_sources.add(scraper_name)

            if not eligible_deadlines:
                break

            next_deadline = min(eligible_deadlines.values())
            next_done, _ = await asyncio.wait(
                set(eligible_deadlines),
                timeout=max(next_deadline - now, 0.0),
                return_when=asyncio.FIRST_COMPLETED,
            )
            completed = set(next_done) | {
                task
                for task in pending
                if task.done()
            }
            if not completed:
                break
            results.extend(self._task_results(completed))
            pending -= completed

        return pending, tuple(sorted(waited_sources))

    def _unmet_coverage_requirements(
        self,
        query: str,
        results: list[ScraperResult],
        requirements: tuple[SearchCoverageRequirement, ...],
    ) -> list[SearchCoverageRequirement]:
        return [
            requirement
            for requirement in requirements
            if self._matched_offer_count_for_requirement(
                query,
                results,
                requirement,
            ) < requirement.minimum_matched_offers
        ]

    def _matched_offer_count_for_requirement(
        self,
        query: str,
        results: list[ScraperResult],
        requirement: SearchCoverageRequirement,
    ) -> int:
        required_vendors = set(requirement.vendors)
        matched_count = 0
        for result in results:
            if result.error is not None:
                continue
            for listing in result.listings:
                if (
                    listing.vendor not in required_vendors
                    and result.scraper.vendor_name not in required_vendors
                ):
                    continue
                if listing_matches_query(
                    query,
                    listing.canonical_name,
                    listing.vendor_product_name,
                    listing.brand,
                    listing.model_number,
                ):
                    matched_count += 1
        return matched_count

    def _format_coverage_labels(
        self,
        requirements: list[SearchCoverageRequirement],
    ) -> str:
        return ", ".join(requirement.label for requirement in requirements)

    def _task_scraper_name(self, task: asyncio.Task[ScraperResult]) -> str:
        coro = task.get_coro()
        frame = getattr(coro, "cr_frame", None)
        scraper = frame.f_locals.get("scraper") if frame is not None else None
        return getattr(scraper, "vendor_name", "unknown")

    async def _drain_timed_out_searches(
        self,
        tasks: set[asyncio.Task[ScraperResult]],
        *,
        query: str,
        context: SearchContext | None,
        source_profile: str,
    ) -> None:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.warning(
                    "provider_background_drain_failure query=%s source_profile=%s context=%s error_type=%s error=%s",
                    query,
                    source_profile,
                    context.cache_key() if context is not None else "none",
                    type(result).__name__,
                    result,
                )
                continue
            if result.error is not None:
                logger.warning(
                    "provider_background_failure vendor=%s query=%s source_profile=%s context=%s error_type=%s error=%s",
                    result.scraper.vendor_name,
                    query,
                    source_profile,
                    context.cache_key() if context is not None else "none",
                    type(result.error).__name__,
                    result.error,
                )

    def _track_background_task(self, task: asyncio.Task[None]) -> None:
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _track_scraper_tasks(self, tasks: list[asyncio.Task]) -> None:
        if not hasattr(self, "_active_scraper_tasks"):
            self._active_scraper_tasks = set()
        for task in tasks:
            self._active_scraper_tasks.add(task)
            task.add_done_callback(self._active_scraper_tasks.discard)

    async def close_background_tasks(self) -> None:
        bg_tasks = getattr(self, "_background_tasks", set())
        active_tasks = getattr(self, "_active_scraper_tasks", set())
        inflight_dict = getattr(self, "_inflight_scrapes", {})
        inflight_tasks = set(inflight_dict.values())
        tasks = tuple(bg_tasks | active_tasks | inflight_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if hasattr(self, "_background_tasks"):
            self._background_tasks.difference_update(tasks)
        if hasattr(self, "_active_scraper_tasks"):
            self._active_scraper_tasks.difference_update(tasks)
        if hasattr(self, "_inflight_scrapes"):
            self._inflight_scrapes.clear()

    async def run_job(
        self,
        db: Session,
        query: str,
        *,
        context: SearchContext | None = None,
        source_profile: str = "all",
    ) -> ScrapeJob:
        job = ScrapeJob(query=query.strip(), status="running")
        db.add(job)
        db.commit()
        db.refresh(job)

        try:
            results = await self.scrape_query(
                db,
                job.query,
                context=context,
                source_profile=source_profile,
                force=True,
            )
        except Exception as exc:
            db.rollback()
            persisted_job = db.get(ScrapeJob, job.id)
            if persisted_job is not None:
                persisted_job.status = "failed"
                persisted_job.error_message = str(exc)
                persisted_job.finished_at = utc_now()
                db.commit()
                db.refresh(persisted_job)
                return persisted_job
            raise

        job.status = "completed"
        job.result_count = len(results)
        job.error_message = None
        job.finished_at = utc_now()
        db.commit()
        db.refresh(job)
        return job

    def create_job(self, db: Session, query: str) -> ScrapeJob:
        job = ScrapeJob(query=query.strip(), status="queued")
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    def mark_job_running(self, db: Session, job_id: str) -> ScrapeJob | None:
        job = db.get(ScrapeJob, job_id)
        if job is None:
            return None
        job.status = "running"
        job.error_message = None
        job.started_at = utc_now()
        job.finished_at = None
        db.commit()
        db.refresh(job)
        return job

    def mark_job_completed(self, db: Session, job_id: str, result_count: int) -> ScrapeJob | None:
        job = db.get(ScrapeJob, job_id)
        if job is None:
            return None
        job.status = "completed"
        job.result_count = result_count
        job.error_message = None
        job.finished_at = utc_now()
        db.commit()
        db.refresh(job)
        return job

    def mark_job_failed(self, db: Session, job_id: str, error_message: str) -> ScrapeJob | None:
        job = db.get(ScrapeJob, job_id)
        if job is None:
            return None
        job.status = "failed"
        job.error_message = error_message
        job.finished_at = utc_now()
        db.commit()
        db.refresh(job)
        return job

    def get_job(self, db: Session, job_id: str) -> ScrapeJob | None:
        return db.get(ScrapeJob, job_id)

    def list_vendors(self, db: Session) -> list[Vendor]:
        return list(db.scalars(select(Vendor).order_by(Vendor.name)).all())

    def has_sources(self, source_profile: str) -> bool:
        return bool(self._resolve_scrapers(source_profile))

    def _get_scraper_semaphore(self) -> asyncio.Semaphore:
        sem = getattr(self, "_scraper_semaphore", None)
        if sem is None:
            sem = asyncio.Semaphore(12)
            self._scraper_semaphore = sem
        return sem

    async def _search_with_retry(
        self,
        scraper: BaseScraper,
        query: str,
        context: SearchContext | None = None,
    ) -> ScraperResult:
        cache_context_key = context.cache_key() if context is not None else None
        inflight_key = (
            getattr(scraper, "vendor_name", str(type(scraper))),
            query.strip().lower(),
            cache_context_key,
        )

        inflight_dict = getattr(self, "_inflight_scrapes", None)
        if inflight_dict is not None and inflight_key in inflight_dict:
            existing_task = inflight_dict[inflight_key]
            if not existing_task.done():
                try:
                    # Reuse existing in-flight task without duplicating network/browser scrape
                    return await asyncio.shield(existing_task)
                except Exception:
                    pass

        current_task = asyncio.current_task()
        if inflight_dict is not None and current_task is not None:
            inflight_dict[inflight_key] = current_task

        try:
            sem = self._get_scraper_semaphore()
            async with sem:
                return await self._execute_search_with_retry(scraper, query, context)
        finally:
            if inflight_dict is not None and inflight_dict.get(inflight_key) is current_task:
                inflight_dict.pop(inflight_key, None)

    async def _execute_search_with_retry(
        self,
        scraper: BaseScraper,
        query: str,
        context: SearchContext | None = None,
    ) -> ScraperResult:
        last_error: Exception | None = None
        retry_attempts = getattr(self, "retry_attempts", 2)
        retry_backoff_seconds = getattr(self, "retry_backoff_seconds", 1.0)
        for attempt in range(1, retry_attempts + 1):
            try:
                return ScraperResult(
                    scraper=scraper,
                    listings=await scraper.search(query, context=context),
                    diagnostics=(
                        scraper.last_search_diagnostics.copy()
                        if getattr(scraper, "last_search_diagnostics", None) is not None
                        else None
                    ),
                )
            except Exception as exc:
                last_error = exc
                if attempt < retry_attempts:
                    logger.warning(
                        "provider_retry vendor=%s query=%s attempt=%s/%s error_type=%s error=%s",
                        getattr(scraper, "vendor_name", "unknown"),
                        query,
                        attempt,
                        retry_attempts,
                        type(exc).__name__,
                        exc,
                    )
                if attempt >= retry_attempts:
                    break
                await asyncio.sleep(retry_backoff_seconds * attempt)
        if last_error is not None:
            logger.warning(
                "provider_exhausted vendor=%s query=%s attempts=%s error_type=%s error=%s",
                getattr(scraper, "vendor_name", "unknown"),
                query,
                retry_attempts,
                type(last_error).__name__,
                last_error,
            )
        return ScraperResult(scraper=scraper, listings=[], error=last_error)

    def build_cache_key(
        self,
        query: str,
        context: SearchContext | None,
        *,
        source_profile: str,
        source_names: list[str] | None = None,
    ) -> str:
        normalized_query = query.strip().lower()
        normalized_profile = source_profile.strip().lower()
        if source_names:
            normalized_profile = ",".join(
                sorted({source_name.strip().lower() for source_name in source_names if source_name.strip()})
            )
        if context is None:
            return f"{normalized_profile}::{normalized_query}"
        return f"{normalized_profile}::{normalized_query}::{context.cache_key()}"

    def _merge_search_diagnostics(
        self,
        destination: SearchDiagnostics,
        source: SearchDiagnostics,
    ) -> None:
        destination.intent = destination.intent or source.intent
        destination.corrected_query = destination.corrected_query or source.corrected_query
        destination.coverage_status = destination.coverage_status or source.coverage_status
        destination.match_confidence = (
            max(destination.match_confidence or 0.0, source.match_confidence or 0.0)
            or None
        )
        for group_name in source.source_groups_checked:
            if group_name not in destination.source_groups_checked:
                destination.source_groups_checked.append(group_name)
        destination.observed_offer_count += source.observed_offer_count
        destination.matched_offer_count += source.matched_offer_count
        for source_name in source.sources_checked:
            if source_name not in destination.sources_checked:
                destination.sources_checked.append(source_name)
        for filter_item in source.filters:
            destination.add_filter(
                SearchFilterDiagnostic(
                    key=filter_item.key,
                    label=filter_item.label,
                    detail=filter_item.detail,
                    source=filter_item.source,
                    active=filter_item.active,
                    removed_count=filter_item.removed_count,
                )
            )

    def _resolve_scrapers(
        self,
        source_profile: str,
        *,
        source_names: list[str] | None = None,
    ) -> list[BaseScraper]:
        if source_names is not None:
            ordered_source_names: list[str] = []
            for source_name in source_names:
                normalized_source_name = source_name.strip().lower()
                if (
                    normalized_source_name
                    and normalized_source_name in self.scrapers_by_source
                    and normalized_source_name not in ordered_source_names
                ):
                    ordered_source_names.append(normalized_source_name)
            return [
                self.scrapers_by_source[source_name]
                for source_name in ordered_source_names
            ]

        normalized_profile = source_profile.strip().lower()
        if normalized_profile == "primary":
            source_names = self.primary_sources
        elif normalized_profile == "background":
            source_names = self.background_sources
        else:
            source_names = list(self.scrapers_by_source)
        return [
            self.scrapers_by_source[source_name]
            for source_name in source_names
            if source_name in self.scrapers_by_source
        ]

    def _cache_ttl_for_profile(self, source_profile: str) -> int:
        if source_profile.strip().lower() == "background":
            return self.background_cache_ttl_seconds
        return self.cache_ttl_seconds

    def _derive_source_name(self, scraper: BaseScraper) -> str:
        raw_name = getattr(scraper, "source_name", None) or scraper.vendor_name
        return (
            raw_name.strip()
            .lower()
            .replace("&", "and")
            .replace(" ", "-")
        )

    def _ensure_vendor(
        self,
        db: Session,
        vendor_name: str,
        base_url: str,
        scrape_strategy: str,
    ) -> Vendor:
        vendor = db.scalar(select(Vendor).where(Vendor.name == vendor_name))
        if vendor is None:
            vendor = Vendor(
                name=vendor_name,
                base_url=base_url,
                scrape_strategy=scrape_strategy,
                last_status="idle",
            )
            db.add(vendor)
            db.flush()
        else:
            vendor.base_url = base_url
            vendor.scrape_strategy = scrape_strategy
            vendor.is_active = True
        return vendor

    def _upsert_listing(self, db: Session, vendor: Vendor, listing: ScrapedListing) -> VendorProduct:
        product = self._ensure_product(db, listing)
        stmt = (
            select(VendorProduct)
            .options(
                selectinload(VendorProduct.price_snapshots),
                selectinload(VendorProduct.reviews),
                selectinload(VendorProduct.sentiment_summary),
            )
            .where(
                VendorProduct.vendor_id == vendor.id,
                VendorProduct.vendor_product_url == listing.product_url,
            )
        )
        vendor_product = db.scalar(stmt)

        if vendor_product is None:
            vendor_product = VendorProduct(
                product_id=product.id,
                vendor_id=vendor.id,
                vendor_product_name=listing.vendor_product_name,
                vendor_product_url=listing.product_url,
                current_price=listing.price,
                raw_price=listing.raw_price,
                currency=listing.currency,
                rating=listing.rating,
                review_count=listing.review_count,
                delivery_info=listing.delivery_info,
                availability_status=listing.availability_status,
                last_seen_at=utc_now(),
            )
            db.add(vendor_product)
            db.flush()
        else:
            vendor_product.product_id = product.id
            vendor_product.vendor_product_name = listing.vendor_product_name
            vendor_product.current_price = listing.price
            vendor_product.raw_price = listing.raw_price
            vendor_product.currency = listing.currency
            vendor_product.rating = listing.rating
            vendor_product.review_count = listing.review_count
            vendor_product.delivery_info = listing.delivery_info
            vendor_product.availability_status = listing.availability_status
            vendor_product.last_seen_at = utc_now()

        if not vendor_product.price_snapshots:
            for entry in listing.price_history:
                vendor_product.price_snapshots.append(
                    PriceSnapshot(
                        price=entry.price,
                        currency=listing.currency,
                        scraped_at=entry.scraped_at,
                    )
                )
        else:
            latest_snapshot = vendor_product.price_snapshots[-1]
            if float(latest_snapshot.price) != float(listing.price):
                vendor_product.price_snapshots.append(
                    PriceSnapshot(
                        price=listing.price,
                        currency=listing.currency,
                        scraped_at=utc_now(),
                    )
                )

        existing_reviews = {(review.title or "", review.body) for review in vendor_product.reviews}
        for review in listing.reviews:
            review_key = (review.title or "", review.body)
            if review_key in existing_reviews:
                continue
            vendor_product.reviews.append(
                Review(
                    title=review.title,
                    body=review.body,
                    rating=review.rating,
                    review_date=review.review_date,
                )
            )

        self.sentiment_service.upsert_summary(db, vendor_product)
        return vendor_product

    @staticmethod
    def _build_product_search_filter(query: str):
        if not query or not query.strip():
            return None
        raw_tokens = [tok.strip().lower() for tok in re.split(r"[\s\-_/]+", query) if len(tok.strip()) >= 2]
        compact = "".join(ch for ch in query.lower() if ch.isalnum())
        tokens: list[str] = []
        seen = set()
        for tok in raw_tokens:
            if tok not in seen:
                seen.add(tok)
                tokens.append(tok)
        if len(compact) >= 3 and compact not in seen:
            tokens.append(compact)

        if not tokens:
            return None

        clauses = []
        for tok in tokens[:8]:
            clean_tok = "".join(ch for ch in tok if ch.isalnum() or ch in ".-")
            if not clean_tok:
                continue
            pattern = f"%{clean_tok}%"
            clauses.extend(
                [
                    Product.canonical_name.ilike(pattern),
                    Product.brand.ilike(pattern),
                    Product.model_number.ilike(pattern),
                    Product.category.ilike(pattern),
                ]
            )
        return or_(*clauses) if clauses else None

    def _load_existing_results(self, db: Session, query: str) -> list[VendorProduct]:
        stmt = select(Product).options(
            selectinload(Product.vendor_products).selectinload(VendorProduct.vendor),
            selectinload(Product.vendor_products).selectinload(VendorProduct.price_snapshots),
            selectinload(Product.vendor_products).selectinload(VendorProduct.reviews),
            selectinload(Product.vendor_products).selectinload(VendorProduct.sentiment_summary),
        )
        if query:
            filter_clause = self._build_product_search_filter(query)
            if filter_clause is not None:
                stmt = stmt.where(filter_clause)
        products = list(
            db.scalars(stmt)
            .unique()
            .all()
        )
        matches: list[VendorProduct] = []
        for product in products:
            if not listing_matches_query(
                query,
                product.canonical_name,
                product.brand,
                product.category,
                product.model_number,
            ):
                continue
            matches.extend(product.vendor_products)
        return matches

    def _ensure_product(self, db: Session, listing: ScrapedListing) -> Product:
        product = None
        if listing.model_number:
            stmt = select(Product).where(Product.model_number == listing.model_number)
            product = db.scalar(stmt)

        if product is None:
            candidates = list(
                db.scalars(
                    select(Product).where(Product.category == listing.category)
                ).all()
            )
            best_candidate: Product | None = None
            best_score = 0.0
            for candidate in candidates:
                if (
                    listing.model_number
                    and candidate.model_number
                    and not are_model_keys_compatible(listing.model_number, candidate.model_number)
                ):
                    continue
                score = match_score(
                    listing.canonical_name,
                    candidate.canonical_name,
                    candidate.brand,
                    candidate.model_number,
                )
                if score > best_score:
                    best_score = score
                    best_candidate = candidate
            if best_candidate is not None and best_score >= 0.78:
                product = best_candidate

        if product is None:
            product = Product(
                canonical_name=listing.canonical_name,
                brand=listing.brand,
                category=listing.category,
                model_number=listing.model_number,
                image_url=listing.image_url,
            )
            db.add(product)
            db.flush()
            return product

        product.canonical_name = listing.canonical_name
        product.brand = listing.brand
        product.category = listing.category
        product.image_url = listing.image_url
        return product

    def _purge_legacy_catalog_records(self, db: Session) -> None:
        demo_vendor_products = list(
            db.scalars(
                select(VendorProduct).where(VendorProduct.vendor_product_url.contains("demo"))
            ).all()
        )
        for vendor_product in demo_vendor_products:
            db.delete(vendor_product)

        db.flush()

        orphan_products = list(
            db.scalars(
                select(Product).options(selectinload(Product.vendor_products))
            ).all()
        )
        for product in orphan_products:
            if not product.vendor_products:
                db.delete(product)

        if demo_vendor_products or orphan_products:
            db.commit()
