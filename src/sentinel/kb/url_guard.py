"""
SSRF guard for KB URL inputs.

Resolves the hostname before crawling and blocks loopback, RFC1918,
link-local (cloud metadata endpoint), and unspecified addresses.
Applied at form-submit time so invalid URLs are never persisted or crawled.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

_BLOCKED_NETS = [
    ipaddress.ip_network("127.0.0.0/8"),    # loopback
    ipaddress.ip_network("::1/128"),         # IPv6 loopback
    ipaddress.ip_network("169.254.0.0/16"),  # link-local — blocks cloud metadata (AWS/GCP/Azure)
    ipaddress.ip_network("10.0.0.0/8"),      # RFC1918
    ipaddress.ip_network("172.16.0.0/12"),   # RFC1918
    ipaddress.ip_network("192.168.0.0/16"),  # RFC1918
    ipaddress.ip_network("0.0.0.0/8"),       # unspecified
    ipaddress.ip_network("fc00::/7"),        # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),       # IPv6 link-local
]


def _is_blocked(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
        return any(ip in net for net in _BLOCKED_NETS)
    except ValueError:
        return True


def validate_crawl_url(url: str) -> str:
    """
    Validate a URL is safe to crawl. Returns the URL unchanged if safe.
    Raises ValueError with a user-facing message if the URL is invalid or SSRF-risky.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL must use http or https (got {parsed.scheme!r})")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL has no hostname")

    try:
        results = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"Cannot resolve {hostname!r}: {exc}") from exc

    for _, _, _, _, sockaddr in results:
        addr = sockaddr[0]
        if _is_blocked(addr):
            raise ValueError(
                f"URL resolves to a blocked address ({addr}) — "
                "internal, private, and link-local hosts are not allowed"
            )

    return url


def safe_href(url: str) -> str | None:
    """
    Return the URL only if the scheme is http or https.
    Returns None for javascript:, data:, or any other scheme.
    Used in HTML rendering to prevent javascript: URI XSS.
    """
    if not url:
        return None
    scheme = urlparse(url).scheme.lower()
    return url if scheme in ("http", "https") else None
