from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.config import get_settings
from app.db.models.product import Product
from app.db.session import configure_session, init_db, session_scope
from app.services.dependencies import configure_services, scrape_service, search_context_service


def main() -> None:
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

    refresh_location = (
        settings.scheduled_refresh_location.strip()
        if settings.scheduled_refresh_location
        else None
    )
    refresh_pincode = (
        settings.scheduled_refresh_pincode.strip()
        if settings.scheduled_refresh_pincode
        else None
    )
    context = asyncio.run(
        search_context_service.build(
            location=refresh_location,
            pincode=refresh_pincode,
        )
    )

    with session_scope() as db:
        queries = list(
            db.scalars(
                select(Product.canonical_name)
                .order_by(Product.created_at.desc())
                .limit(settings.scheduled_refresh_limit)
            ).all()
        )

        for query in queries:
            asyncio.run(
                scrape_service.scrape_query(
                    db,
                    query,
                    context=context,
                    source_profile="background",
                    force=True,
                )
            )


if __name__ == "__main__":
    main()
