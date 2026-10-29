from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.http_middleware import RateLimitMiddleware, add_security_headers
from app.core.logging import configure_logging
from app.db.session import configure_session, init_db, session_scope
from app.scrapers.hardware_scraper_utils import close_shared_clients
from app.scrapers.live_utils import close_live_browser
from app.services.dependencies import configure_services, queue_service, scrape_service


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()
    active_settings = settings or get_settings()
    configure_services(active_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_session(
            active_settings.active_database_url,
            pool_size=active_settings.database_pool_size,
            max_overflow=active_settings.database_max_overflow,
            pool_recycle_seconds=active_settings.database_pool_recycle_seconds,
        )
        if active_settings.effective_auto_create_schema:
            init_db()
        if active_settings.bootstrap_vendors_on_startup:
            with session_scope() as db:
                scrape_service.bootstrap_vendors(db)
        try:
            yield
        finally:
            await queue_service.close_background_tasks()
            await scrape_service.close_background_tasks()
            await close_shared_clients()
            await close_live_browser()

    app = FastAPI(
        title=active_settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = active_settings
    if active_settings.effective_rate_limit_enabled:
        app.add_middleware(
            RateLimitMiddleware,
            request_limit=active_settings.rate_limit_requests,
            window_seconds=active_settings.rate_limit_window_seconds,
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    add_security_headers(app)
    app.include_router(api_router, prefix=active_settings.api_v1_prefix)

    @app.get("/")
    def root() -> dict[str, str]:
        return {"message": "Costiqo rewrite backend is running."}

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "environment": active_settings.environment,
        }

    return app


app = create_app()
