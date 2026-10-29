from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_cors_preflight_login_allowed_origin():
    settings = Settings(
        environment="test",
        cors_origins_raw="https://costiqo.netlify.app",
        database_url="sqlite:///./test.db",
    )
    app = create_app(settings)
    client = TestClient(app)

    headers = {
        "Origin": "https://costiqo.netlify.app",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }
    response = client.options("/api/v1/auth/login", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://costiqo.netlify.app"
    assert "POST" in response.headers.get("access-control-allow-methods", "")
    assert "content-type" in response.headers.get("access-control-allow-headers", "").lower()


def test_cors_preflight_register_allowed_origin():
    settings = Settings(
        environment="test",
        cors_origins_raw="https://costiqo.netlify.app",
        database_url="sqlite:///./test.db",
    )
    app = create_app(settings)
    client = TestClient(app)

    headers = {
        "Origin": "https://costiqo.netlify.app",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }
    response = client.options("/api/v1/auth/register", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://costiqo.netlify.app"


def test_cors_preflight_normalizes_trailing_slash_in_config():
    # If the user or env var specifies origin with trailing slash, browser Origin (without slash) must still match
    settings = Settings(
        environment="test",
        cors_origins_raw="https://costiqo.netlify.app/",
        database_url="sqlite:///./test.db",
    )
    app = create_app(settings)
    client = TestClient(app)

    headers = {
        "Origin": "https://costiqo.netlify.app",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,authorization",
    }
    response = client.options("/api/v1/auth/login", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://costiqo.netlify.app"


def test_cors_preflight_default_includes_production_netlify_origin():
    # Even if CORS_ORIGINS_RAW is omitted or empty, costiqo.netlify.app must be allowed
    settings = Settings(
        environment="test",
        cors_origins_raw="",
        database_url="sqlite:///./test.db",
    )
    app = create_app(settings)
    client = TestClient(app)

    headers = {
        "Origin": "https://costiqo.netlify.app",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }
    response = client.options("/api/v1/auth/login", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://costiqo.netlify.app"


def test_cors_preflight_disallowed_origin_returns_400():
    settings = Settings(
        environment="test",
        database_url="sqlite:///./test.db",
    )
    app = create_app(settings)
    client = TestClient(app)

    headers = {
        "Origin": "https://malicious-attacker.com",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }
    response = client.options("/api/v1/auth/login", headers=headers)
    assert response.status_code == 400
    assert "Disallowed CORS origin" in response.text


def test_cors_preflight_not_blocked_by_rate_limiting():
    settings = Settings(
        environment="development",  # allows rate limiting
        rate_limit_enabled=True,
        rate_limit_requests=2,
        rate_limit_window_seconds=60,
        database_url="sqlite:///./test.db",
    )
    app = create_app(settings)
    client = TestClient(app)

    headers = {
        "Origin": "https://costiqo.netlify.app",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }
    # Send multiple preflight requests in quick succession
    for _ in range(5):
        response = client.options("/api/v1/auth/login", headers=headers)
        assert response.status_code == 200
