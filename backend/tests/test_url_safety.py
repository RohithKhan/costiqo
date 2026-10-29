import ipaddress
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.offer_verification_service import OfferVerificationService
from app.utils.url_safety import (
    is_prohibited_ip,
    is_safe_url,
    matches_allowed_domain,
    validate_safe_url,
)


TRUSTED_DOMAINS = ("amazon.in", "croma.com", "flipkart.com", "robu.in")


def test_allowed_domains_exact_and_subdomain_matching():
    assert matches_allowed_domain("amazon.in", TRUSTED_DOMAINS)
    assert matches_allowed_domain("www.amazon.in", TRUSTED_DOMAINS)
    assert matches_allowed_domain("store.croma.com", TRUSTED_DOMAINS)
    assert matches_allowed_domain("api.sub.flipkart.com", TRUSTED_DOMAINS)

    # Attack vectors: domain confusion / substring match
    assert not matches_allowed_domain("evilamazon.in", TRUSTED_DOMAINS)
    assert not matches_allowed_domain("amazon.in.attacker.com", TRUSTED_DOMAINS)
    assert not matches_allowed_domain("croma.com.evil.org", TRUSTED_DOMAINS)
    assert not matches_allowed_domain("notrobu.in", TRUSTED_DOMAINS)
    assert not matches_allowed_domain("example.com", TRUSTED_DOMAINS)


def test_validate_safe_url_accepts_valid_http_and_https():
    safe_http, _ = validate_safe_url("http://amazon.in/dp/B0123456", TRUSTED_DOMAINS)
    assert safe_http is True

    safe_https, _ = validate_safe_url("https://www.croma.com/product/123", TRUSTED_DOMAINS)
    assert safe_https is True


def test_validate_safe_url_rejects_unsupported_schemes():
    for bad_url in (
        "ftp://amazon.in/file",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html;base64,PHNjcmlwdD4=",
        "gopher://amazon.in/",
        "ws://amazon.in/feed",
    ):
        safe, reason = validate_safe_url(bad_url, TRUSTED_DOMAINS)
        assert safe is False
        assert "scheme" in (reason or "").lower()


def test_validate_safe_url_rejects_embedded_credentials():
    for bad_url in (
        "https://user:pass@amazon.in/product",
        "https://admin@amazon.in/page",
        "http://foo:bar@croma.com/test",
    ):
        safe, reason = validate_safe_url(bad_url, TRUSTED_DOMAINS)
        assert safe is False
        assert "credentials" in (reason or "").lower()


def test_prohibited_ips_detected():
    prohibited_ips = (
        "127.0.0.1",
        "127.0.1.1",
        "10.0.0.1",
        "10.254.254.1",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.1.1",
        "192.168.100.50",
        "169.254.169.254",  # AWS/GCP metadata
        "0.0.0.0",
        "255.255.255.255",
        "100.64.0.1",  # CGNAT
        "192.0.2.1",  # documentation
        "198.51.100.1",
        "203.0.113.1",
        "224.0.0.1",  # multicast
        "240.0.0.1",  # reserved
        "::1",  # IPv6 loopback
        "::",
        "fe80::1",  # IPv6 link-local
        "fc00::1",  # IPv6 private
        "::ffff:127.0.0.1",  # IPv4-mapped IPv6 loopback
        "::ffff:169.254.169.254",  # IPv4-mapped IPv6 link-local
    )
    for ip_str in prohibited_ips:
        ip = ipaddress.ip_address(ip_str)
        assert is_prohibited_ip(ip) is True, f"Expected {ip_str} to be prohibited"

    # Public routable IPs should NOT be prohibited
    public_ips = ("8.8.8.8", "1.1.1.1", "142.250.190.46", "2607:f8b0:4005:805::200e")
    for ip_str in public_ips:
        ip = ipaddress.ip_address(ip_str)
        assert is_prohibited_ip(ip) is False, f"Expected {ip_str} to be allowed"


def test_validate_safe_url_rejects_localhost_and_private_ips():
    for private_url in (
        "http://localhost/admin",
        "http://localhost:7070/api",
        "http://127.0.0.1:8000/metrics",
        "http://[::1]/secrets",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/internal",
        "http://192.168.1.254/router",
        "http://172.16.5.10/status",
    ):
        safe, _ = validate_safe_url(private_url)
        assert safe is False


def test_validate_safe_url_rejects_untrusted_domains():
    safe, reason = validate_safe_url("https://attacker.com/steal", allowed_domains=TRUSTED_DOMAINS)
    assert safe is False
    assert "trusted" in (reason or "").lower()

    safe_sub, _ = validate_safe_url("https://amazon.in.attacker.com/p", allowed_domains=TRUSTED_DOMAINS)
    assert safe_sub is False


@pytest.mark.asyncio
async def test_offer_verification_service_rejects_unsafe_initial_url():
    service = OfferVerificationService(trusted_vendor_domains=TRUSTED_DOMAINS)

    # Private IP
    html = await service._fetch_page_html("http://169.254.169.254/latest/meta-data/")
    assert html is None

    # Untrusted domain
    html_untrusted = await service._fetch_page_html("https://malicious-site.com/product")
    assert html_untrusted is None

    # Embedded credentials
    html_creds = await service._fetch_page_html("https://user:pass@amazon.in/dp/123")
    assert html_creds is None


@pytest.mark.asyncio
async def test_offer_verification_service_rejects_malicious_redirect():
    service = OfferVerificationService(trusted_vendor_domains=TRUSTED_DOMAINS)

    # Initial request to trusted domain returns 302 redirecting to private metadata IP
    mock_response_302 = MagicMock()
    mock_response_302.status_code = 302
    mock_response_302.headers = {"location": "http://169.254.169.254/latest/meta-data"}

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response_302

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        # Mock validate_safe_url to allow initial host (simulate amazon.in) but reject redirect
        result = await service._fetch_page_html("https://www.amazon.in/dp/B0123")
        assert result is None
        # Should NOT make request to 169.254.169.254
        assert mock_client.get.call_count == 1
        call_url = mock_client.get.call_args[0][0]
        assert "169.254" not in call_url


@pytest.mark.asyncio
async def test_offer_verification_service_accepts_safe_redirect():
    service = OfferVerificationService(trusted_vendor_domains=TRUSTED_DOMAINS)

    mock_response_302 = MagicMock()
    mock_response_302.status_code = 302
    mock_response_302.headers = {"location": "/samsung-galaxy/p"}

    mock_response_200 = MagicMock()
    mock_response_200.status_code = 200
    mock_response_200.headers = {"content-length": "100"}
    mock_response_200.text = "<html><body>Product price: ₹12,999</body></html>"

    mock_client = AsyncMock()
    mock_client.get.side_effect = [mock_response_302, mock_response_200]

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await service._fetch_page_html("https://www.amazon.in/dp/B0123")
        assert result is not None
        assert "₹12,999" in result
        assert mock_client.get.call_count == 2
