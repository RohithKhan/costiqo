from __future__ import annotations

from urllib.parse import urlparse


def normalize_hostname(hostname: str | None) -> str | None:
    if not hostname:
        return None
    normalized = hostname.strip().lower().removeprefix("www.")
    return normalized or None


def hostname_from_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return normalize_hostname(urlparse(url).hostname)
    except ValueError:
        return None


def hostname_matches_domain(hostname: str | None, configured_domain: str) -> bool:
    normalized_hostname = normalize_hostname(hostname)
    normalized_domain = normalize_hostname(configured_domain)
    if not normalized_hostname or not normalized_domain:
        return False
    return (
        normalized_hostname == normalized_domain
        or normalized_hostname.endswith(f".{normalized_domain}")
    )


def is_trusted_domain(hostname: str | None, trusted_domains: tuple[str, ...]) -> bool:
    return any(
        hostname_matches_domain(hostname, trusted_domain)
        for trusted_domain in trusted_domains
    )


def is_trusted_url(url: str | None, trusted_domains: tuple[str, ...]) -> bool:
    return is_trusted_domain(hostname_from_url(url), trusted_domains)
