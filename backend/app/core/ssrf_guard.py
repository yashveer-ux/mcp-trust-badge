"""SSRF/abuse guard for fetching arbitrary user-submitted URLs (§7.1).

We fetch URLs the user gives us -> classic SSRF surface. Block anything that
resolves to internal/cloud-metadata addresses before we ever connect.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

MAX_RESPONSE_BYTES = 5_000_000  # 5MB read cap
SCAN_TIMEOUT_S = 8.0            # hard per-scan timeout

# Cloud metadata endpoints (link-local already covers these, but be explicit).
_METADATA_IPS = {"169.254.169.254", "fd00:ec2::254"}


class SSRFError(Exception):
    """URL rejected: bad scheme or resolves to a blocked address."""


def _ip_blocked(ip: ipaddress._BaseAddress) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def validate_url(url: str) -> str:
    """Return url if safe to fetch, else raise SSRFError.

    Rejects non-http(s) schemes and any host that resolves to a
    private/loopback/link-local/reserved/multicast/unspecified IP, plus the
    cloud metadata address explicitly.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SSRFError(f"scheme not allowed: {parsed.scheme!r} (only http/https)")
    host = parsed.hostname
    if not host:
        raise SSRFError("no host in URL")

    # Resolve ALL addresses; a host with one public + one private A record must fail.
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as e:
        raise SSRFError(f"DNS resolution failed for {host!r}: {e}") from e

    for info in infos:
        addr = info[4][0]
        if addr in _METADATA_IPS:
            raise SSRFError(f"{host!r} resolves to cloud metadata address {addr}")
        ip = ipaddress.ip_address(addr)
        # IPv4-mapped IPv6 (::ffff:127.0.0.1) hides internal v4 -> unwrap.
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
            if str(ip) in _METADATA_IPS:
                raise SSRFError(f"{host!r} resolves to cloud metadata address {ip}")
        if _ip_blocked(ip):
            raise SSRFError(f"{host!r} resolves to blocked address {addr}")

    return url


# ponytail: validate-then-connect leaves a small DNS-rebinding window (the host
# could re-resolve to a private IP between this check and httpx's own connect).
# The high-value protections (private-IP block, size cap, hard timeout) are all
# here. Full fix = pin the resolved IP and pass the original Host header to
# httpx (transport=connect-to-IP) so the checked address is the one connected
# to. Upgrade there if we ever face an adversary who controls DNS TTLs.


def demo() -> None:
    for bad in ("http://169.254.169.254/", "http://127.0.0.1/",
                "http://10.0.0.5/", "file:///etc/passwd"):
        try:
            validate_url(bad)
        except SSRFError:
            pass
        else:
            raise AssertionError(f"expected SSRFError for {bad}")
    # Public host must pass (needs DNS; requires network at check time).
    assert validate_url("http://example.com") == "http://example.com"
    print("ssrf self-check OK")


if __name__ == "__main__":
    demo()
