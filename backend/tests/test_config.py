from app.core.config import Settings


def test_cors_origins_always_include_local_dev_defaults():
    settings = Settings(
        cors_origins_raw="https://costiqo.vercel.app",
        database_url="sqlite:///./test.db",
    )

    for port in ("5173", "5174", "5175", "5176", "5177", "5178", "5179"):
        assert f"http://localhost:{port}" in settings.cors_origins
        assert f"http://127.0.0.1:{port}" in settings.cors_origins
    assert "https://costiqo.vercel.app" in settings.cors_origins
    assert "https://costiqo.netlify.app" in settings.cors_origins


def test_cors_origins_strips_trailing_slashes():
    settings = Settings(
        cors_origins_raw="https://costiqo.netlify.app/, https://example.com/ ",
        database_url="sqlite:///./test.db",
    )
    assert "https://costiqo.netlify.app" in settings.cors_origins
    assert "https://costiqo.netlify.app/" not in settings.cors_origins
    assert "https://example.com" in settings.cors_origins
    assert "https://example.com/" not in settings.cors_origins


def test_trusted_vendor_domains_include_observed_live_merchants():
    settings = Settings(database_url="sqlite:///./test.db")

    assert "cashify.in" in settings.trusted_vendor_domains
    assert "myimaginestore.com" in settings.trusted_vendor_domains


def test_neon_database_url_overrides_default_database_url():
    settings = Settings(
        database_url="sqlite:///./test.db",
        neon_database_url="postgresql+psycopg://user:password@example.neon.tech/costiqo?sslmode=require",
    )

    assert settings.active_database_url.startswith("postgresql+psycopg://")
    assert settings.is_sqlite is False


def test_production_rejects_default_or_insecure_secret():
    import pytest

    with pytest.raises(ValueError) as excinfo:
        Settings(
            environment="production",
            secret_key="change-me-before-production",
            database_url="sqlite:///./test.db",
        )
    assert "Insecure secret_key configuration" in str(excinfo.value)
    assert "change-me-before-production" not in str(excinfo.value)

    with pytest.raises(ValueError) as excinfo_short:
        Settings(
            environment="production",
            secret_key="short-secret",
            database_url="sqlite:///./test.db",
        )
    assert "Insecure secret_key configuration" in str(excinfo_short.value)
    assert "short-secret" not in str(excinfo_short.value)


def test_production_accepts_strong_secret():
    strong_secret = "a" * 32
    settings = Settings(
        environment="production",
        secret_key=strong_secret,
        database_url="sqlite:///./test.db",
    )
    assert settings.secret_key == strong_secret


def test_development_and_test_allow_default_secret():
    dev_settings = Settings(
        environment="development",
        database_url="sqlite:///./test.db",
    )
    assert dev_settings.secret_key == "change-me-before-production"

    test_settings = Settings(
        environment="test",
        database_url="sqlite:///./test.db",
    )
    assert test_settings.secret_key == "change-me-before-production"


def test_normalize_database_url_converts_postgres_prefixes_and_preserves_sqlite():
    from app.core.config import normalize_database_url

    assert normalize_database_url("postgres://u:p@host/db") == "postgresql+psycopg://u:p@host/db"
    assert normalize_database_url("postgresql://u:p@host/db") == "postgresql+psycopg://u:p@host/db"
    assert normalize_database_url("sqlite:///./costiqo.db") == "sqlite:///./costiqo.db"
    assert normalize_database_url("") == ""
    assert normalize_database_url(None) == ""


def test_neon_unpooled_url_used_for_migrations_only():
    settings = Settings(
        database_url="postgresql://user:pass@ep-pooler.neon.tech/db?sslmode=require",
        database_url_unpooled="postgresql://user:pass@ep-direct.neon.tech/db?sslmode=require",
        neon_branch="production",
    )

    assert "ep-pooler.neon.tech" in settings.active_database_url
    assert settings.active_database_url.startswith("postgresql+psycopg://")
    assert "ep-direct.neon.tech" in settings.active_migration_database_url
    assert settings.active_migration_database_url.startswith("postgresql+psycopg://")
    assert settings.neon_branch == "production"


def test_production_disables_auto_create_schema_on_postgres():
    settings = Settings(
        environment="production",
        secret_key="x" * 32,
        database_url="postgresql+psycopg://user:pass@ep-pooler.neon.tech/db?sslmode=require",
        auto_create_schema=True,
    )
    assert settings.effective_auto_create_schema is False


def test_development_allows_auto_create_schema():
    settings = Settings(
        environment="development",
        auto_create_schema=True,
    )
    assert settings.effective_auto_create_schema is True



