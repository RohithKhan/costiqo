from __future__ import annotations

from collections.abc import Sequence
import ipaddress
import logging
import socket
from urllib.parse import urlparse


logger = logging.getLogger(__name__)

PROHIBITED_IP_NETWORKS = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.88.99.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
    ipaddress.ip_network("2001:db8::/32"),
)

BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "broadcasthost",
    "local",
}

_RFC6052_NAT64_PREFIX = ipaddress.ip_network("64:ff9b::/96")


def is_prohibited_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped:
            return is_prohibited_ip(ip.ipv4_mapped)
        # RFC 6052 Well-Known Prefix (64:ff9b::/96) embeds an IPv4 address in the last 32 bits.
        # Python's ipaddress module treats 64:ff9b::/96 as reserved=True, but when used in NAT64,
        # it routes to the global internet unless the embedded IPv4 address itself is prohibited.
        if ip in _RFC6052_NAT64_PREFIX:
            embedded_ipv4 = ipaddress.IPv4Address(ip.packed[-4:])
            return is_prohibited_ip(embedded_ipv4)

    if (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True

    return any(ip in network for network in PROHIBITED_IP_NETWORKS)


def matches_allowed_domain(
    hostname: str,
    allowed_domains: Sequence[str],
    *,
    allow_subdomains: bool = True,
) -> bool:
    clean_host = hostname.strip().lower().rstrip(".")
    if not clean_host:
        return False

    for domain in allowed_domains:
        clean_domain = domain.strip().lower().rstrip(".")
        if not clean_domain:
            continue

        if clean_host == clean_domain:
            return True

        clean_host_no_www = clean_host.removeprefix("www.")
        clean_domain_no_www = clean_domain.removeprefix("www.")

        if clean_host_no_www == clean_domain_no_www:
            return True

        if allow_subdomains:
            if clean_host.endswith(f".{clean_domain}") or clean_host.endswith(f".{clean_domain_no_www}"):
                return True

    return False


def resolve_and_validate_host(hostname: str) -> tuple[bool, str | None]:
    clean_host = hostname.strip().lower().rstrip(".")
    if not clean_host:
        return False, "Host is empty"

    if clean_host in BLOCKED_HOSTNAMES or any(
        clean_host.endswith(f".{suffix}")
        for suffix in ("local", "localhost", "internal", "lan", "home", "corp")
    ):
        return False, "Host is blocked"

    try:
        ip = ipaddress.ip_address(clean_host)
        if is_prohibited_ip(ip):
            return False, "IP address is reserved or non-routable"
        return True, None
    except ValueError:
        pass

    try:
        addr_infos = socket.getaddrinfo(clean_host, None)
    except (socket.gaierror, socket.herror) as exc:
        logger.debug("dns_resolution_failed host=%s error=%s", clean_host, exc)
        return False, "Host resolution failed"
    except Exception as exc:
        logger.warning("dns_resolution_unexpected_error host=%s error=%s", clean_host, exc)
        return False, "Host resolution failed"

    if not addr_infos:
        return False, "Host did not resolve to any addresses"

    for addr_info in addr_infos:
        sockaddr = addr_info[4]
        ip_str = sockaddr[0]
        try:
            resolved_ip = ipaddress.ip_address(ip_str)
            if is_prohibited_ip(resolved_ip):
                return False, "Resolved address is reserved or non-routable"
        except ValueError:
            return False, "Invalid address returned by resolver"

    return True, None


def validate_safe_url(
    url: str,
    allowed_domains: Sequence[str] | None = None,
    *,
    allow_subdomains: bool = True,
    resolve_dns: bool = True,
) -> tuple[bool, str | None]:
    if not url or not isinstance(url, str):
        return False, "URL is empty or invalid"

    trimmed_url = url.strip()
    if not trimmed_url or trimmed_url.startswith("#"):
        return False, "URL is empty or an anchor"

    try:
        parsed = urlparse(trimmed_url)
    except Exception:
        return False, "URL could not be parsed"

    if parsed.scheme.lower() not in {"http", "https"}:
        return False, "URL scheme must be http or https"

    if parsed.username or parsed.password or "@" in (parsed.netloc or ""):
        return False, "Credentials in URL are not permitted"

    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if not hostname:
        return False, "Hostname is missing"

    if any(ch in hostname for ch in (" ", "\t", "\r", "\n", "\\", "/", ":")):
        return False, "Hostname contains invalid characters"

    if allowed_domains:
        if not matches_allowed_domain(
            hostname,
            allowed_domains,
            allow_subdomains=allow_subdomains,
        ):
            return False, "Hostname is not in trusted vendor domains"

    if resolve_dns:
        valid_host, host_reason = resolve_and_validate_host(hostname)
        if not valid_host:
            return False, host_reason

    return True, None


def is_safe_url(
    url: str,
    allowed_domains: Sequence[str] | None = None,
    *,
    allow_subdomains: bool = True,
    resolve_dns: bool = True,
) -> bool:
    safe, _ = validate_safe_url(
        url,
        allowed_domains=allowed_domains,
        allow_subdomains=allow_subdomains,
        resolve_dns=resolve_dns,
    )
    return safe
