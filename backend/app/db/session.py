from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings, normalize_database_url
from app.db.base import Base


engine: Engine | None = None
SessionLocal: sessionmaker[Session] | None = None


def configure_session(
    database_url: str,
    *,
    pool_size: int = 5,
    max_overflow: int = 10,
    pool_recycle_seconds: int = 1800,
) -> Engine:
    global engine, SessionLocal

    normalized_url = normalize_database_url(database_url)
    connect_args = {"check_same_thread": False} if normalized_url.startswith("sqlite") else {}
    engine_kwargs = {
        "future": True,
        "connect_args": connect_args,
    }
    if not normalized_url.startswith("sqlite"):
        engine_kwargs.update(
            {
                "pool_pre_ping": True,
                "pool_size": pool_size,
                "max_overflow": max_overflow,
                "pool_recycle": pool_recycle_seconds,
            }
        )
    engine = create_engine(normalized_url, **engine_kwargs)
    SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )
    return engine


def get_engine() -> Engine:
    global engine
    if engine is None:
        settings = get_settings()
        engine = configure_session(
            settings.active_database_url,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_recycle_seconds=settings.database_pool_recycle_seconds,
        )
    return engine


def get_session_factory() -> sessionmaker[Session]:
    global SessionLocal
    if SessionLocal is None:
        settings = get_settings()
        configure_session(
            settings.active_database_url,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_recycle_seconds=settings.database_pool_recycle_seconds,
        )
    assert SessionLocal is not None
    return SessionLocal


def init_db() -> None:
    from app.db.models import (  # noqa: F401
        alert_rule,
        offline_quote,
        price_snapshot,
        product,
        purchase_record,
        purchase_record_quote,
        review,
        saved_product,
        saved_search,
        scrape_job,
        search_audit_log,
        sentiment_summary,
        user,
        vendor,
        vendor_product,
    )

    Base.metadata.create_all(bind=get_engine())


def get_db() -> Generator[Session, None, None]:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    db = get_session_factory()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
