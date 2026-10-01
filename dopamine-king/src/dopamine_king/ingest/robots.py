"""robots.txt policy following RFC 9309, with an in-memory cache per origin.

The stdlib ``urllib.robotparser`` applies the first matching rule where RFC 9309 asks for the longest
match, so matching is implemented here instead:

* 2xx: parse the file. The group naming our product token wins, otherwise the ``*`` group. Several
  groups naming the same agent are merged. The longest matching pattern wins and Allow wins a tie.
  ``*`` and ``$`` wildcards are supported.
* 3xx: followed (at most five hops) when the fetcher did not already do so.
* 4xx except 429: there is no robots.txt, so everything is allowed.
* 5xx, 429, unresolvable redirects and network errors: everything is disallowed for the lifetime of
  this policy object (one run). 429 is a deliberate, conservative reading of "unavailable".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import quote, urljoin, urlsplit

from ..net import Fetcher

MAX_ROBOTS_BYTES = 512 * 1024
MAX_REDIRECTS = 5
_REDIRECTS = frozenset({301, 302, 303, 307, 308})
_USER_AGENT_KEYS = frozenset({"user-agent", "useragent", "user agent"})
_DISALLOW_KEYS = frozenset({"disallow", "dissallow", "dissalow", "disalow", "diasllow", "disallaw"})
_MAX_REMEMBERED_REASONS = 2000
_BOM = chr(0xFEFF)


def _norm(text: str) -> str:
    """Percent-encode non-ASCII characters and upper-case escapes so both sides compare equal."""
    encoded = quote(text, safe="/%?&=:@!$'()*+,;~-._[]")
    return re.sub(r"%[0-9a-fA-F]{2}", lambda m: m.group(0).upper(), encoded)


def compile_pattern(pattern: str) -> re.Pattern[str]:
    """Compile a robots.txt style path pattern (``*`` wildcard, trailing ``$`` anchor) for ``match``."""
    norm = _norm(pattern)
    anchored = norm.endswith("$")
    if anchored:
        norm = norm[:-1]
    body = ".*".join(re.escape(part) for part in norm.split("*"))
    return re.compile(body + ("$" if anchored else ""), re.S)


@dataclass
class _Rule:
    allow: bool
    pattern: str
    regex: re.Pattern[str]

    def text(self) -> str:
        return f"{'Allow' if self.allow else 'Disallow'}: {self.pattern}"


@dataclass
class _Group:
    agents: list[str] = field(default_factory=list)
    rules: list[_Rule] = field(default_factory=list)
    crawl_delay: float | None = None
    has_body: bool = False  # once a rule was seen, the next user-agent line opens a new group


@dataclass
class ParsedRobots:
    groups: list[_Group] = field(default_factory=list)
    sitemaps: list[str] = field(default_factory=list)

    def select(self, token: str) -> tuple[list[_Group], str]:
        """Groups that apply to a lower-cased product token, plus the label of the matched group."""
        specific = [g for g in self.groups if token in g.agents]
        if specific:
            return specific, token
        return [g for g in self.groups if "*" in g.agents], "*"

    def decide(self, token: str, path: str, label: str) -> tuple[bool, str]:
        groups, matched = self.select(token)
        shown = label if matched == token else "*"
        if not groups:
            return True, "no applicable group in robots.txt"
        target = _norm(path)
        hits = [r for g in groups for r in g.rules if r.regex.match(target)]
        if not hits:
            return True, f"no matching rule in group {shown}"
        best = max(hits, key=lambda r: (len(r.pattern), r.allow))
        verb = "allowed" if best.allow else "disallowed"
        return best.allow, f"{verb} by '{best.text()}' in group {shown}"

    def crawl_delay(self, token: str) -> float | None:
        groups, _ = self.select(token)
        delays = [g.crawl_delay for g in groups if g.crawl_delay is not None]
        return max(delays) if delays else None


def parse_robots(text: str) -> ParsedRobots:
    """Parse robots.txt text. Unknown lines and rules before the first user-agent are ignored."""
    parsed = ParsedRobots()
    group: _Group | None = None
    for raw in text.lstrip(_BOM).splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key in _USER_AGENT_KEYS:
            if group is None or group.has_body:
                group = _Group()
                parsed.groups.append(group)
            group.agents.append(value.split("/")[0].strip().lower())
        elif key in _DISALLOW_KEYS or key == "allow":
            if group is None:
                continue
            group.has_body = True
            if value:
                group.rules.append(_Rule(key == "allow", value, compile_pattern(value)))
        elif key == "crawl-delay":
            match = re.match(r"\d+(?:\.\d+)?", value)
            if group is not None and match:
                group.has_body = True
                group.crawl_delay = float(match.group(0))
        elif key == "sitemap" and re.match(r"https?://", value, re.I):
            parsed.sitemaps.append(value)
    return parsed


@dataclass
class _Entry:
    kind: str                       # "parsed", "missing" (4xx) or "unavailable" (5xx, errors)
    detail: str
    parsed: ParsedRobots | None = None


def origin_of(value: str) -> tuple[str, str] | None:
    """(scheme, netloc) of a URL or bare host name; None for anything that is not http(s)."""
    if "://" not in value:
        if not re.fullmatch(r"[^/:@\s]+(?::\d+)?(?:/.*)?", value):  # not a bare host: mailto:, javascript:, ...
            return None
        value = f"https://{value}"
    parts = urlsplit(value)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not host:
        return None
    if ":" in host:
        host = f"[{host}]"
    try:
        port = parts.port
    except ValueError:
        port = None
    if port and not ((parts.scheme == "http" and port == 80) or (parts.scheme == "https" and port == 443)):
        host = f"{host}:{port}"
    return parts.scheme, host


class RobotsPolicy:
    def __init__(self, fetcher: Fetcher, user_agent: str, product_token: str = "DopamineKing") -> None:
        self.fetcher = fetcher
        self.user_agent = user_agent
        self.product_token = product_token
        self._token = product_token.lower()
        self._entries: dict[tuple[str, str], _Entry] = {}
        self._reasons: dict[str, str] = {}

    # -- loading --------------------------------------------------------------------
    def _entry(self, origin: tuple[str, str]) -> _Entry:
        entry = self._entries.get(origin)
        if entry is None:
            entry = self._entries[origin] = self._load(*origin)
        return entry

    def _load(self, scheme: str, netloc: str) -> _Entry:
        url = f"{scheme}://{netloc}/robots.txt"
        headers = {"User-Agent": self.user_agent}
        hops = 0
        try:
            while True:
                resp = self.fetcher.get(url, headers=headers)
                location = resp.header("location")
                if resp.status in _REDIRECTS and location:
                    hops += 1
                    if hops > MAX_REDIRECTS:
                        return _Entry("unavailable", "robots.txt redirects too often: everything disallowed this run")
                    url = urljoin(url, location)
                    continue
                break
        except Exception as err:  # FetchError or anything a custom fetcher raises: fail closed
            return _Entry("unavailable", f"robots.txt unreachable ({err}): everything disallowed this run")
        if resp.ok:
            text = resp.body[:MAX_ROBOTS_BYTES].decode("utf-8-sig", errors="replace")
            return _Entry("parsed", "robots.txt parsed", parse_robots(text))
        if 400 <= resp.status < 500 and resp.status != 429:
            return _Entry("missing", f"robots.txt not found (HTTP {resp.status}): everything allowed")
        return _Entry("unavailable", f"robots.txt unavailable (HTTP {resp.status}): everything disallowed this run")

    # -- public API -----------------------------------------------------------------
    def allowed(self, url: str) -> bool:
        origin = origin_of(url)
        if origin is None:
            return self._remember(url, False, "not an http(s) URL")
        parts = urlsplit(url)
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        if (parts.path or "/") == "/robots.txt":
            return self._remember(url, True, "robots.txt itself is always fetchable")
        entry = self._entry(origin)
        if entry.kind == "missing":
            return self._remember(url, True, entry.detail)
        if entry.kind == "unavailable" or entry.parsed is None:
            return self._remember(url, False, entry.detail)
        ok, why = entry.parsed.decide(self._token, path, self.product_token)
        return self._remember(url, ok, why)

    def crawl_delay(self, host: str) -> float | None:
        origin = origin_of(host)
        entry = self._entry(origin) if origin else None
        if entry is None or entry.parsed is None:
            return None
        return entry.parsed.crawl_delay(self._token)

    def sitemaps(self, host_or_url: str) -> list[str]:
        origin = origin_of(host_or_url)
        entry = self._entry(origin) if origin else None
        if entry is None or entry.parsed is None:
            return []
        return list(entry.parsed.sitemaps)

    def reason(self, url: str) -> str:
        if url not in self._reasons:
            self.allowed(url)
        return self._reasons[url]

    # -- helpers --------------------------------------------------------------------
    def _remember(self, url: str, ok: bool, why: str) -> bool:
        if len(self._reasons) >= _MAX_REMEMBERED_REASONS:
            self._reasons.pop(next(iter(self._reasons)))
        self._reasons[url] = why
        return ok
