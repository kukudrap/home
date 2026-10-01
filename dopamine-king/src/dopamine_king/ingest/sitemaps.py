"""Sitemap parsing and polite, capped traversal of sitemap indexes.

Sitemaps are the second choice after feeds: they list URLs and dates but no titles, so pages must be
fetched afterwards. Traversal is breadth first, newest first, and bounded in depth, files and URLs.
"""
from __future__ import annotations

import re
import zlib
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Iterable

from ..models import Serializable, canonical_url
from ..net import Fetcher, maybe_gunzip
from .extract import parse_datetime
from .feeds import load_xml, qname


@dataclass
class SitemapEntry(Serializable):
    loc: str
    lastmod: str | None = None
    image_count: int = 0
    video_count: int = 0


@dataclass
class SitemapDoc:
    kind: str                                   # "index" or "urlset"
    entries: list[SitemapEntry] = field(default_factory=list)


# Content-ish URLs: a content term as a host label (blog.example.com/x) or as a directory segment
# (example.com/news/x, example.com/press-releases/2026/x), never the last segment (index pages) and
# never a word inside a product slug. Pagination, archives, taxonomies, accounts and legal pages lose.
_TERMS = (
    r"(?:blogs?|news(?:room)?|press(?:-releases?)?|stor(?:y|ies)|insights?|articles?|magazine|resources?|journal"
    r"|updates?|learn|case-stud(?:y|ies)|inspiration|ideas|guides?|announcements?|editorial|perspectives)"
)
_JUNK = (
    r"(?:(?:^|/)(?:tags?|category|categories|author|authors|feed|search|cart|checkout|login|signin|sign-in|signup"
    r"|sign-up|register|accounts?|careers?|jobs|comments?|wp-json|wp-admin|wp-content|wp-includes|unsubscribe"
    r"|subscribe|privacy[a-z-]*|terms[a-z-]*|legal[a-z-]*|cookies?[a-z-]*)(?:/|$|\?|#)"
    r"|/page/\d+|[?&](?:page|paged|s|q|search|replytocom)="
    r"|/(?:19|20)\d{2}(?:/\d{1,2})?/?(?:[?#]|$)"
    r"|\.(?:jpe?g|png|gif|webp|svg|pdf|xml|json|js|css|zip|mp4|mp3)(?:[?#]|$))"
)
_HOST_TERM = r"https?://(?:[^/?#]*\.)?" + _TERMS + r"\.[^/?#]*/[^/?#]"
_PATH_TERM = r"/(?:[^/?#]*[^a-z0-9/?#])?" + _TERMS + r"(?:[^a-z0-9/?#][^/?#]*)?/[^/?#]"
DEFAULT_CONTENT_PATTERN = re.compile(rf"^(?!.*{_JUNK})(?=.*(?:{_HOST_TERM}|{_PATH_TERM}))", re.I)

def content_pattern(paths: Iterable[str] = ()) -> re.Pattern[str]:
    """The default content pattern, widened with brand specific content paths such as ``["/blog"]``."""
    prefixes = [re.escape(p.rstrip("/")) for p in paths if isinstance(p, str) and p.startswith("/") and p.strip("/")]
    if not prefixes:
        return DEFAULT_CONTENT_PATTERN
    brand = rf"^(?!.*{_JUNK})https?://[^/?#]+(?:{'|'.join(prefixes)})/[^/?#]"
    return re.compile(f"(?:{DEFAULT_CONTENT_PATTERN.pattern})|(?:{brand})", re.I)


_CONTENT_SITEMAP = re.compile(r"(?<![a-z0-9])(?:posts?|blogs?|news|articles?|stories|story|press|insights?|journal"
                              r"|magazine|resources|updates|learn|editorial)(?![a-z0-9])", re.I)
_JUNK_SITEMAP = re.compile(r"(?<![a-z0-9])(?:products?|categor(?:y|ies)|tags?|authors?|pages?|images?|videos?"
                           r"|attachments?|media|stores?|shops?|collections?|locations?)(?![a-z0-9])", re.I)


def _child_text(el, local: str) -> str:
    for child in el:
        if qname(child)[1] == local:
            return "".join(child.itertext()).strip()
    return ""


def parse_sitemap(data: bytes | str) -> SitemapDoc:
    """Parse a sitemap, a sitemap index or a plain text URL list (gzip is detected by magic bytes)."""
    raw = data.encode("utf-8") if isinstance(data, str) else data
    try:
        raw = maybe_gunzip(raw).lstrip(b"\xef\xbb\xbf \t\r\n")
    except (zlib.error, EOFError, OSError) as err:
        raise ValueError(f"invalid gzip data: {err}") from err
    if raw[:1] != b"<":
        urls = [line.strip() for line in raw.decode("utf-8", errors="replace").splitlines()]
        urls = [u for u in urls if re.match(r"https?://\S+$", u)]
        if not urls:
            raise ValueError("not a sitemap")
        return SitemapDoc("urlset", [SitemapEntry(u) for u in urls])

    root = load_xml(raw)
    kind = qname(root)[1].lower()
    if kind not in ("sitemapindex", "urlset"):
        raise ValueError(f"not a sitemap: root element <{qname(root)[1]}>")
    wanted = "sitemap" if kind == "sitemapindex" else "url"
    entries: list[SitemapEntry] = []
    for node in root:
        if qname(node)[1] != wanted:
            continue
        loc = _child_text(node, "loc")
        if not re.match(r"https?://", loc, re.I) or len(loc) > 2048:  # 2048 is the protocol's limit
            continue
        images = sum(1 for c in node if qname(c)[1] == "image" and "image" in qname(c)[0])
        videos = sum(1 for c in node if qname(c)[1] == "video" and "video" in qname(c)[0])
        entries.append(SitemapEntry(loc, _child_text(node, "lastmod") or None, images, videos))
    return SitemapDoc("index" if kind == "sitemapindex" else "urlset", entries)


def _newest_first(entries: list[SitemapEntry]) -> list[SitemapEntry]:
    """Newest lastmod first; entries without a usable date keep their order after the dated ones."""
    def key(entry: SitemapEntry) -> float:
        parsed = parse_datetime(entry.lastmod)
        return -parsed.timestamp() if parsed else float("inf")
    return sorted(entries, key=key)


def _child_priority(entry: SitemapEntry) -> int:
    name = entry.loc.rsplit("/", 1)[-1]
    if _CONTENT_SITEMAP.search(name):
        return 0
    return 2 if _JUNK_SITEMAP.search(name) else 1


def iter_sitemap_urls(
    fetcher: Fetcher,
    sitemap_url: str,
    *,
    pattern: re.Pattern[str] | str | None = DEFAULT_CONTENT_PATTERN,
    since: str | None = None,
    max_urls: int = 200,
    max_depth: int = 2,
    max_sitemaps: int = 20,
    on_error: Callable[[str, Exception], None] | None = None,
) -> list[SitemapEntry]:
    """Content URLs reachable from a sitemap or sitemap index, newest first.

    Sub-sitemaps are visited breadth first, content-looking names before the rest and newest before
    oldest. A sitemap that cannot be fetched or parsed is reported through ``on_error(url, exc)`` and
    skipped, the traversal continues. At most ``max_sitemaps`` files are fetched.
    """
    rx = re.compile(pattern, re.I) if isinstance(pattern, str) else pattern
    cutoff: datetime | None = parse_datetime(since) if since else None
    queue: deque[tuple[str, int]] = deque([(sitemap_url, 0)])
    visited: set[str] = set()
    found: dict[str, SitemapEntry] = {}

    while queue and len(visited) < max_sitemaps:
        url, depth = queue.popleft()
        if url in visited:
            continue
        visited.add(url)
        try:
            resp = fetcher.get(url)
            if not resp.ok:
                raise ValueError(f"HTTP {resp.status}")
            doc = parse_sitemap(resp.body)
        except Exception as err:  # one broken sitemap must not abort the rest
            if on_error:
                on_error(url, err)
            continue
        if doc.kind == "index":
            if depth >= max_depth:
                continue
            children = _newest_first(doc.entries)
            children.sort(key=_child_priority)
            for child in children:
                stamp = parse_datetime(child.lastmod)
                if cutoff and stamp and stamp < cutoff:
                    continue
                queue.append((child.loc, depth + 1))
            continue
        for entry in doc.entries:
            stamp = parse_datetime(entry.lastmod)
            if cutoff and stamp and stamp < cutoff:
                continue
            if rx is not None and not rx.search(entry.loc):
                continue
            found.setdefault(canonical_url(entry.loc), entry)
    return _newest_first(list(found.values()))[:max_urls]
