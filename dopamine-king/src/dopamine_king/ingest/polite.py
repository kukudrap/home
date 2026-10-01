"""Policy enforcing fetcher: robots.txt, crawl-delay and TDM reservation in one place.

``PoliteFetcher`` wraps any ``Fetcher``. A URL that robots.txt disallows never reaches the inner
fetcher. Content that reserves its text and data mining rights (TDMRep: ``tdm-reservation: 1`` header,
``<meta name="tdm-reservation" content="1">`` or a matching rule in ``/.well-known/tdmrep.json``) is
refused with ``BlockedByPolicy`` so callers cannot store it by accident.
"""
from __future__ import annotations

import json
import re
from typing import Any, Mapping
from urllib.parse import urlsplit

from ..config import user_agent as default_user_agent
from ..net import Fetcher, Response
from ..store import Store
from .errors import BlockedByPolicy
from .robots import RobotsPolicy, compile_pattern, origin_of

_META_TAG = re.compile(r"<meta\b[^>]*>", re.I)
_ATTR = re.compile(r"""([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))""")
_HEAD_CHARS = 300_000
WELL_KNOWN_TDM = "/.well-known/tdmrep.json"


def has_tdm_meta(html: str) -> bool:
    """True when the HTML carries ``<meta name="tdm-reservation" content="1">``."""
    for tag in _META_TAG.findall(html[:_HEAD_CHARS]):
        attrs = {
            m.group(1).lower(): m.group(2) or m.group(3) or (m.group(4) or "").rstrip("/") for m in _ATTR.finditer(tag)
        }
        if attrs.get("name", "").strip().lower() == "tdm-reservation" and attrs.get("content", "").strip() == "1":
            return True
    return False


def tdm_reservation_source(resp: Response) -> str | None:
    """``"header"`` or ``"meta"`` when a successful response reserves TDM rights, else None."""
    if not resp.ok:
        return None
    if (resp.header("tdm-reservation") or "").strip() == "1":
        return "header"
    ctype = (resp.header("content-type") or "").lower()
    sniffed = not ctype and resp.body[:512].lstrip().lower().startswith((b"<!doctype html", b"<html"))
    if ("html" in ctype or sniffed) and has_tdm_meta(resp.text):
        return "meta"
    return None


def parse_tdmrep(data: Any) -> list[tuple[re.Pattern[str], bool]]:
    """Rules of a tdmrep.json document as (location pattern, reserved) pairs, in file order."""
    if isinstance(data, dict):
        data = [data]
    rules: list[tuple[re.Pattern[str], bool]] = []
    for rule in data if isinstance(data, list) else []:
        if not isinstance(rule, dict) or not isinstance(rule.get("location"), str):
            continue
        rules.append((compile_pattern(rule["location"]), str(rule.get("tdm-reservation", "")).strip() == "1"))
    return rules


def _is_robots_url(url: str) -> bool:
    parts = urlsplit(url)
    return parts.path == "/robots.txt" and not parts.query


class PoliteFetcher:
    """Implements the ``Fetcher`` protocol on top of an inner fetcher."""

    def __init__(
        self,
        inner: Fetcher,
        robots: RobotsPolicy,
        store: Store | None = None,
        *,
        max_crawl_delay: float = 60.0,
        check_tdmrep: bool = True,
    ) -> None:
        self.inner = inner
        self.robots = robots
        self.store = store
        self.max_crawl_delay = max_crawl_delay
        self.check_tdmrep = check_tdmrep
        self._tdmrep: dict[tuple[str, str], list[tuple[re.Pattern[str], bool]]] = {}
        self._delays: dict[str, float] = {}

    # -- Fetcher protocol -----------------------------------------------------------
    def get(self, url: str, *, headers: Mapping[str, str] | None = None) -> Response:
        if _is_robots_url(url):
            return self._fetch(url, headers)
        if not self.robots.allowed(url):
            reason = f"robots: {self.robots.reason(url)}"
            self._log(url, None, None, f"blocked: {reason}")
            raise BlockedByPolicy(url, reason)
        self._apply_crawl_delay(url)
        if self.tdmrep_reserved(url):
            self._log(url, None, None, "blocked: tdm-reservation (tdmrep.json)")
            raise BlockedByPolicy(url, "tdm-reservation")
        resp = self._fetch(url, headers, log=False)
        source = tdm_reservation_source(resp)
        if source:
            self._log(url, resp.status, len(resp.body), f"blocked: tdm-reservation ({source})")
            raise BlockedByPolicy(url, "tdm-reservation")
        self._log(url, resp.status, len(resp.body), "cache" if resp.from_cache else "")
        return resp

    # -- internals ------------------------------------------------------------------
    def _fetch(self, url: str, headers: Mapping[str, str] | None, log: bool = True) -> Response:
        merged = dict(headers or {})
        if not any(key.lower() == "user-agent" for key in merged):
            merged["User-Agent"] = self.robots.user_agent
        try:
            resp = self.inner.get(url, headers=merged)
        except Exception as err:
            self._log(url, None, None, f"error: {err}")
            raise
        if log:
            self._log(url, resp.status, len(resp.body), "cache" if resp.from_cache else "")
        return resp

    def _apply_crawl_delay(self, url: str) -> None:
        delay = self.robots.crawl_delay(url)
        if delay is None:
            return
        if delay > self.max_crawl_delay:
            self._log(url, None, None, f"blocked: crawl-delay {delay:g}s exceeds {self.max_crawl_delay:g}s")
            raise BlockedByPolicy(url, "crawl-delay-too-long")
        host = (urlsplit(url).hostname or "").lower()
        setter = getattr(self.inner, "set_host_delay", None)
        if setter is not None and self._delays.get(host) != delay:
            setter(host, delay)
            self._delays[host] = delay

    def tdmrep_reserved(self, url: str) -> bool:
        """True when the host's tdmrep.json reserves this URL. Used for items built without fetching the page."""
        if not self.check_tdmrep:
            return False
        origin = origin_of(url)
        if origin is None:
            return False
        if origin not in self._tdmrep:
            self._tdmrep[origin] = self._load_tdmrep(*origin)
        parts = urlsplit(url)
        target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        for pattern, reserved in self._tdmrep[origin]:
            if pattern.match(target):
                return reserved
        return False

    def _load_tdmrep(self, scheme: str, netloc: str) -> list[tuple[re.Pattern[str], bool]]:
        url = f"{scheme}://{netloc}{WELL_KNOWN_TDM}"
        if not self.robots.allowed(url):
            return []
        try:
            resp = self._fetch(url, None)
            return parse_tdmrep(json.loads(resp.text)) if resp.ok else []
        except Exception:  # absent or malformed file: no reservation announced
            return []

    def _log(self, url: str, status: int | None, size: int | None, note: str) -> None:
        if self.store is not None:
            self.store.log_fetch(url, status, size, note)


def ensure_polite(fetcher: Fetcher, robots: RobotsPolicy | None = None, store: Store | None = None) -> PoliteFetcher:
    """Return ``fetcher`` when it already enforces policy, else wrap it. Policy cannot be bypassed."""
    if isinstance(fetcher, PoliteFetcher):
        return fetcher
    return PoliteFetcher(fetcher, robots or RobotsPolicy(fetcher, default_user_agent()), store)
