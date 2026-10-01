"""Small, dependency-free HTTP layer shared by scrapers and API clients.

Everything that touches the network goes through a ``Fetcher`` so tests can inject
``FakeFetcher`` and production code gets retries, per-host rate limiting and an on-disk
conditional-GET cache for free.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
import socket
import ssl
import time
import urllib.error
import urllib.request
import zlib
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import urlsplit

from .config import DEFAULT_USER_AGENT

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class FetchError(Exception):
    """Network level failure (DNS, TLS, timeout, proxy denial). HTTP error codes are not errors."""


class FetchDenied(FetchError):
    """The egress proxy or network policy refused the host. A policy decision, so it is never retried."""


@dataclass
class Response:
    url: str
    status: int
    headers: dict[str, str] = field(default_factory=dict)  # lower-cased keys
    body: bytes = b""
    from_cache: bool = False
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def header(self, name: str, default: str | None = None) -> str | None:
        return self.headers.get(name.lower(), default)

    @property
    def text(self) -> str:
        charset = "utf-8"
        match = re.search(r"charset=([\w-]+)", self.headers.get("content-type", ""), re.I)
        if match:
            charset = match.group(1)
        try:
            return self.body.decode(charset if charset.lower() != "utf-8" else "utf-8-sig", errors="replace")
        except LookupError:
            return self.body.decode("utf-8-sig", errors="replace")

    def json(self) -> Any:
        return json.loads(self.text)


class Fetcher(Protocol):
    def get(self, url: str, *, headers: Mapping[str, str] | None = None) -> Response: ...


Transport = Callable[[str, dict[str, str], float, int], Response]


def maybe_gunzip(body: bytes, limit: int = 50_000_000) -> bytes:
    """Decompress gzip payloads (for example sitemap.xml.gz) detected by magic bytes."""
    if body[:2] == b"\x1f\x8b":
        dec = zlib.decompressobj(16 + zlib.MAX_WBITS)
        return dec.decompress(body, limit)
    return body


def _decode_content(body: bytes, encoding: str, limit: int) -> bytes:
    enc = encoding.lower().strip()
    try:
        if enc in ("gzip", "x-gzip"):
            return zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(body, limit)
        if enc == "deflate":
            try:
                return zlib.decompressobj().decompress(body, limit)
            except zlib.error:
                return zlib.decompressobj(-zlib.MAX_WBITS).decompress(body, limit)
    except (zlib.error, EOFError, gzip.BadGzipFile):
        return body
    return body


def urllib_transport(url: str, headers: dict[str, str], timeout: float, max_bytes: int) -> Response:
    """Default transport. Honours HTTPS_PROXY and the system CA bundle through urllib."""
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            raw = resp.read(max_bytes + 1)
            hdrs = {k.lower(): v for k, v in resp.headers.items()}
            status = resp.status
            final_url = resp.geturl()
    except urllib.error.HTTPError as err:
        raw = err.read(max_bytes + 1) if err.fp else b""
        hdrs = {k.lower(): v for k, v in err.headers.items()} if err.headers else {}
        status = err.code
        final_url = url
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, ssl.SSLError, OSError) as err:
        message = str(getattr(err, "reason", err))
        if "Tunnel connection failed" in message:
            message += " (the egress proxy denied this host: check the environment network policy)"
            raise FetchDenied(f"{url}: {message}") from err
        raise FetchError(f"{url}: {message}") from err
    truncated = len(raw) > max_bytes
    raw = raw[:max_bytes]
    if "content-encoding" in hdrs:
        raw = _decode_content(raw, hdrs["content-encoding"], max_bytes * 4)
    return Response(final_url, status, hdrs, raw, truncated=truncated)


class HttpFetcher:
    """GET client with retries, per-host rate limit and a conditional-GET disk cache."""

    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        *,
        timeout: float = 20.0,
        min_interval: float = 1.0,
        max_retries: int = 3,
        backoff: float = 1.5,
        max_retry_after: float = 60.0,
        max_bytes: int = 5_000_000,
        cache_dir: str | Path | None = None,
        cache_ttl: float = 3600.0,
        transport: Transport = urllib_transport,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.backoff = backoff
        self.max_retry_after = max_retry_after
        self.max_bytes = max_bytes
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.cache_ttl = cache_ttl
        self._transport = transport
        self._sleep = sleep
        self._clock = clock
        self._now = now
        self._last_hit: dict[str, float] = {}
        self._host_delay: dict[str, float] = {}
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    # -- politeness -----------------------------------------------------------------
    def set_host_delay(self, host: str, seconds: float) -> None:
        """Raise the minimum interval for one host (for example from robots.txt Crawl-delay)."""
        self._host_delay[host.lower()] = max(0.0, seconds)

    def _throttle(self, host: str) -> None:
        interval = max(self.min_interval, self._host_delay.get(host, 0.0))
        last = self._last_hit.get(host)
        if last is not None:
            wait = interval - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)
        self._last_hit[host] = self._clock()

    # -- cache ----------------------------------------------------------------------
    def _cache_paths(self, url: str) -> tuple[Path, Path] | None:
        if not self.cache_dir:
            return None
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{key}.json", self.cache_dir / f"{key}.body"

    def _cache_load(self, url: str) -> tuple[dict[str, Any], bytes] | None:
        paths = self._cache_paths(url)
        if not paths or not paths[0].exists() or not paths[1].exists():
            return None
        try:
            return json.loads(paths[0].read_text("utf-8")), paths[1].read_bytes()
        except (OSError, ValueError):
            return None

    def _cache_store(self, url: str, resp: Response, fetched_at: float) -> None:
        paths = self._cache_paths(url)
        if not paths or resp.status != 200:
            return
        meta = {
            "url": url,
            "fetched_at": fetched_at,
            "etag": resp.header("etag"),
            "last_modified": resp.header("last-modified"),
            "content_type": resp.header("content-type"),
            "tdm_reservation": resp.header("tdm-reservation"),
        }
        try:
            paths[1].write_bytes(resp.body)
            paths[0].write_text(json.dumps(meta), "utf-8")
        except OSError:
            pass

    # -- main entry -----------------------------------------------------------------
    def get(self, url: str, *, headers: Mapping[str, str] | None = None) -> Response:
        host = (urlsplit(url).hostname or "").lower()
        req_headers = {
            "User-Agent": self.user_agent,
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
        }
        req_headers.update(headers or {})

        cached = self._cache_load(url)
        if cached:
            meta, body = cached
            age = self._now() - float(meta.get("fetched_at", 0))
            replay = Response(
                url, 200,
                {k: v for k, v in {
                    "content-type": meta.get("content_type"),
                    "etag": meta.get("etag"),
                    "last-modified": meta.get("last_modified"),
                    "tdm-reservation": meta.get("tdm_reservation"),
                }.items() if v},
                body, from_cache=True,
            )
            if age <= self.cache_ttl:
                return replay
            if meta.get("etag"):
                req_headers["If-None-Match"] = meta["etag"]
            if meta.get("last_modified"):
                req_headers["If-Modified-Since"] = meta["last_modified"]
        else:
            replay = None

        last_error: FetchError | None = None
        for attempt in range(self.max_retries + 1):
            self._throttle(host)
            try:
                resp = self._transport(url, req_headers, self.timeout, self.max_bytes)
            except FetchDenied:
                raise                       # a policy denial will not change by waiting
            except FetchError as err:
                last_error = err
                if attempt >= self.max_retries:
                    break
                self._sleep(self.backoff * (2 ** attempt))
                continue
            if resp.status == 304 and replay is not None:
                self._cache_store(url, replay, self._now())
                return replay
            if resp.status in RETRY_STATUSES and attempt < self.max_retries:
                self._sleep(self._retry_delay(resp, attempt))
                continue
            self._cache_store(url, resp, self._now())
            return resp
        raise last_error or FetchError(f"{url}: giving up after {self.max_retries + 1} attempts")

    def _retry_delay(self, resp: Response, attempt: int) -> float:
        raw = resp.header("retry-after")
        if raw:
            try:
                return min(float(raw), self.max_retry_after)
            except ValueError:
                try:
                    delta = parsedate_to_datetime(raw).timestamp() - self._now()
                    return min(max(delta, 0.0), self.max_retry_after)
                except (TypeError, ValueError):
                    pass
        return min(self.backoff * (2 ** attempt), self.max_retry_after)


class FakeFetcher:
    """In-memory fetcher for tests.

    ``routes`` maps a URL (or a prefix ending in ``*``) to one of: ``Response``, ``bytes``/``str``
    body (status 200), ``(status, body)``, ``(status, body, headers)``, an ``Exception`` instance to
    raise, or a callable ``(url, headers) -> any of the above``. Unknown URLs return 404.
    """

    def __init__(self, routes: Mapping[str, Any] | None = None) -> None:
        self.routes: dict[str, Any] = dict(routes or {})
        self.calls: list[str] = []

    def add(self, url: str, body: Any, status: int = 200, headers: Mapping[str, str] | None = None) -> None:
        self.routes[url] = (status, body, dict(headers or {}))

    def _lookup(self, url: str) -> Any:
        if url in self.routes:
            return self.routes[url]
        for key, value in self.routes.items():
            if key.endswith("*") and url.startswith(key[:-1]):
                return value
        return None

    def get(self, url: str, *, headers: Mapping[str, str] | None = None) -> Response:
        self.calls.append(url)
        route = self._lookup(url)
        if callable(route):
            route = route(url, dict(headers or {}))
        if isinstance(route, Exception):
            raise route
        if route is None:
            return Response(url, 404, {}, b"not found")
        if isinstance(route, Response):
            return route
        status, hdrs = 200, {}
        if isinstance(route, tuple):
            status = route[0]
            body = route[1]
            hdrs = {k.lower(): v for k, v in (route[2] if len(route) > 2 else {}).items()}
        else:
            body = route
        if isinstance(body, str):
            body = body.encode("utf-8")
        return Response(url, status, hdrs, body)
