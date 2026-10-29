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

