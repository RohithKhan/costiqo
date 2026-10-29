from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.db.session import configure_session, session_scope
from app.services.dependencies import configure_services, scrape_service, search_context_service


def run_scrape_job_task(
    job_id: str,
    location: str | None = None,
    pincode: str | None = None,
    source_profile: str = "all",
) -> None:
    settings = get_settings()
    configure_services(settings)
    configure_session(
        settings.active_database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_recycle_seconds=settings.database_pool_recycle_seconds,
    )

    with session_scope() as db:
        job = scrape_service.mark_job_running(db, job_id)
        if job is None:
            raise RuntimeError(f"Scrape job {job_id} was not found.")
        try:
            context = asyncio.run(
                search_context_service.build(location=location, pincode=pincode)
            )
            results = asyncio.run(
                scrape_service.scrape_query(
                    db,
                    job.query,
                    context=context,
                    source_profile=source_profile,
                    force=True,
                )
            )
            scrape_service.mark_job_completed(db, job_id, len(results))
        except Exception as exc:
            scrape_service.mark_job_failed(db, job_id, str(exc))
            raise


def run_background_refresh_task(
    query: str,
    location: str | None = None,
    pincode: str | None = None,
    source_profile: str = "background",
) -> None:
    settings = get_settings()
    configure_services(settings)
    configure_session(
        settings.active_database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_recycle_seconds=settings.database_pool_recycle_seconds,
    )

    context = asyncio.run(search_context_service.build(location=location, pincode=pincode))
    cache_key = scrape_service.build_cache_key(
        query,
        context,
        source_profile=source_profile,
    )
    try:
        with session_scope() as db:
            asyncio.run(
                scrape_service.scrape_query(
                    db,
                    query,
                    context=context,
                    source_profile=source_profile,
                    force=True,
                )
            )
    finally:
        scrape_service.query_cache_store.release_lock(cache_key)
