"""HTTP helpers for FanGraphs endpoints behind Cloudflare.

Plain ``requests`` gets 403 from GitHub Actions runners (and often from
datacenter IPs). ``curl_cffi`` impersonates Chrome's TLS fingerprint, which
is what ``scrape_2025_actuals.py`` already uses for leaderboards.
"""
import socket
import ssl
import time

from curl_cffi import requests as cffi_requests
from curl_cffi.requests.exceptions import HTTPError

DEFAULT_IMPERSONATE = 'chrome131'
DEFAULT_TIMEOUT = 60
IMPERSONATE_PROFILES = ('chrome131', 'chrome', 'chrome120', 'safari17_0', 'edge101')

# Do not retry 403 — FanGraphs/Cloudflare blocks are not helped by backoff; callers
# should fall back to another endpoint or cached CSV instead.
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_RETRY_EXC = (
    TimeoutError,
    socket.timeout,
    ssl.SSLError,
    ConnectionError,
    OSError,
)


def get(url, *, timeout=DEFAULT_TIMEOUT, impersonate=DEFAULT_IMPERSONATE, headers=None):
    """GET a FanGraphs URL once; raises on HTTP error."""
    response = cffi_requests.get(
        url,
        impersonate=impersonate,
        timeout=timeout,
        headers=headers,
    )
    response.raise_for_status()
    return response


def get_with_retry(
    url,
    *,
    timeout=DEFAULT_TIMEOUT,
    max_attempts=3,
    initial_backoff=2.0,
    headers=None,
    impersonate_profiles=IMPERSONATE_PROFILES,
):
    """GET with retries on transient errors and HTTP 403/429/5xx."""
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        impersonate = impersonate_profiles[(attempt - 1) % len(impersonate_profiles)]
        try:
            response = cffi_requests.get(
                url,
                impersonate=impersonate,
                timeout=timeout,
                headers=headers,
            )
            if response.status_code in _RETRYABLE_STATUS and attempt < max_attempts:
                sleep_for = initial_backoff * (2 ** (attempt - 1))
                print(
                    f"  FanGraphs HTTP {response.status_code}, retrying in {sleep_for:.0f}s "
                    f"(attempt {attempt}/{max_attempts}, profile={impersonate})"
                )
                time.sleep(sleep_for)
                continue
            response.raise_for_status()
            return response
        except HTTPError:
            raise
        except _RETRY_EXC as exc:
            last_exc = exc
            if attempt >= max_attempts:
                raise
            sleep_for = initial_backoff * (2 ** (attempt - 1))
            print(
                f"  FanGraphs transient error ({type(exc).__name__}: {exc}), "
                f"retrying in {sleep_for:.0f}s (attempt {attempt}/{max_attempts})"
            )
            time.sleep(sleep_for)
    if last_exc:
        raise last_exc
    raise RuntimeError(f"FanGraphs GET failed after {max_attempts} attempts: {url}")
