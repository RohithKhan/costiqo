from __future__ import annotations

from redis import Redis

from app.core.config import get_settings
from app.db.session import configure_session, init_db, session_scope
from app.services.dependencies import configure_services, scrape_service


def main() -> None:
    try:
        from rq import Connection, Worker
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "The worker requires the 'rq' package. Install backend dependencies before running it."
        ) from exc

    settings = get_settings()
    configure_services(settings)
    configure_session(
        settings.active_database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_recycle_seconds=settings.database_pool_recycle_seconds,
    )
    if settings.effective_auto_create_schema:
        init_db()
    if settings.bootstrap_vendors_on_startup:
        with session_scope() as db:
            scrape_service.bootstrap_vendors(db)

    connection = Redis.from_url(settings.redis_url, decode_responses=True)
    with Connection(connection):
        Worker([settings.queue_name]).work()


if __name__ == "__main__":
    main()
