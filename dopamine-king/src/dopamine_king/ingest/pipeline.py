"""Scrape pipeline: feeds first, sitemaps second, single pages only when metadata is missing.

Everything goes through a ``PoliteFetcher`` (robots.txt, crawl-delay, TDM reservation), so no code path
here can bypass the policy. Stored per item: metadata, an excerpt of at most 300 characters and derived
numeric features. Never the full text, never author names (only ``has_byline``).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, Iterator
from urllib.parse import urlsplit

from ..config import user_agent as default_user_agent
from ..models import Brand, ContentItem, Serializable, canonical_url, item_id_for_url
from ..net import Fetcher
from ..store import Store
from .errors import BlockedByPolicy
from .extract import extract_page, guess_lang, parse_datetime, same_site, shorten, strip_byline_lead, to_iso
from .feeds import FeedEntry, discover_feeds, parse_feed
from .polite import PoliteFetcher
from .robots import RobotsPolicy
from .sitemaps import SitemapEntry, content_pattern, iter_sitemap_urls

EXCERPT_LIMIT = 300
MAX_FEEDS_PER_BRAND = 3
MAX_SITEMAP_SOURCES = 3
MAX_FEED_ENTRIES = 500
MAX_REMEMBERED_BLOCKS = 10
_NEWS_TOKENS = frozenset({"news", "press", "newsroom", "stories", "story"})
_PRESS_TOKENS = frozenset({"press", "newsroom"})


@dataclass
class ScrapeReport(Serializable):
    brand_id: str
    candidates: int = 0           # distinct candidate URLs found (sitemap sources are already cut to the cap)
    new: int = 0
    skipped_existing: int = 0
    blocked: int = 0
    errors: list[str] = field(default_factory=list)
    used: list[str] = field(default_factory=list)            # "feed:<url>" or "sitemap:<url>"
    blocked_reasons: list[str] = field(default_factory=list)  # first few, "<url>: <reason>"


@dataclass
class _Candidate:
    url: str                      # canonical
    fetch_url: str                # as listed by the site
    published_at: str | None
    source: str                   # "feed" or "sitemap"
    entry: FeedEntry | None = None
    sitemap: SitemapEntry | None = None


def _err(err: BaseException) -> str:
    text = " ".join(str(err).split()) or type(err).__name__
    return text[:200]


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _classify(url: str, has_video: bool = False) -> tuple[str, str]:
    """(platform, format) from the URL: newsroom and press paths, YouTube watch links, else blog article."""
    parts = urlsplit(url)
    host, path = _host(url), parts.path.lower()
    if host == "youtu.be" or (host.endswith("youtube.com") and path.startswith(("/watch", "/shorts/"))):
        return "youtube", "short" if path.startswith("/shorts/") else "video"
    segments = [s for s in path.split("/") if s]
    tokens = {t for label in host.split(".")[:-1] for t in re.split(r"[-_]", label)}
    tokens |= {t for seg in segments[:-1] for t in re.split(r"[-_]", seg)}
    platform = "newsroom" if tokens & _NEWS_TOKENS else "blog"
    if has_video:
        return platform, "video"
    return platform, "press" if tokens & _PRESS_TOKENS else "article"


def _recency(candidate: _Candidate) -> float:
    stamp = parse_datetime(candidate.published_at)
    return -stamp.timestamp() if stamp else float("inf")


class Scraper:
    """Collects content metadata for brands.

    Sources in order of preference: the brand's feeds, feeds advertised on its homepage, sitemaps.
    Sitemaps are a fallback for brands without a usable feed unless ``sitemap_topup`` asks for deeper
    history. ``max_items_per_brand`` caps how many of the newest candidates are looked at per run, so
    the work (and the load on a site) is bounded.
    """

    def __init__(
        self,
        store: Store,
        fetcher: Fetcher,
        *,
        max_items_per_brand: int = 50,
        since_days: int = 365,
        fetch_pages: bool = False,
        sitemap_topup: bool = False,
        now: Callable[[], datetime] | None = None,
        progress: Callable[[str], None] | None = None,
        user_agent: str | None = None,
    ) -> None:
        self.store = store
        if isinstance(fetcher, PoliteFetcher):
            self.fetcher = fetcher
        else:  # policy cannot be bypassed: a raw fetcher is always wrapped
            self.fetcher = PoliteFetcher(fetcher, RobotsPolicy(fetcher, user_agent or default_user_agent()), store)
        self.max_items = max(1, max_items_per_brand)
        self.since_days = since_days
        self.fetch_pages = fetch_pages
        self.sitemap_topup = sitemap_topup
        self._clock = now or (lambda: datetime.now(timezone.utc))
        self._progress = progress

    # -- public API -----------------------------------------------------------------
    def scrape_all(self, brands: Iterable[Brand]) -> Iterator[ScrapeReport]:
        for brand in brands:
            yield self.scrape_brand(brand)

    def scrape_brand(self, brand: Brand) -> ScrapeReport:
        report = ScrapeReport(brand.id)
        self._say(f"{brand.id}: start")
        try:
            if self.store.get_brand(brand.id) is None:
                self.store.upsert_brand(brand)
            self._scrape(brand, report)
        except Exception as err:  # one brand must never abort a batch
            report.errors.append(f"unexpected: {_err(err)}")
        self._say(f"{brand.id}: {report.new} new, {report.skipped_existing} known, {report.blocked} blocked")
        return report

    # -- orchestration --------------------------------------------------------------
    def _scrape(self, brand: Brand, report: ScrapeReport) -> None:
        cutoff = self._now() - timedelta(days=self.since_days)
        # hosts that sitemap URLs may live on
        sites = {_host(u) for u in [brand.homepage, *brand.feeds, *brand.sitemaps] if u}
        candidates: dict[str, _Candidate] = {}
        tried: list[str] = []

        def read(feed_url: str) -> int:
            """Add one feed's entries to the candidates and return how many were added."""
            tried.append(feed_url)
            entries = self._read_feed(feed_url, report)
            if entries is None:
                return 0
            sites.add(_host(feed_url))
            added = 0
            for entry in entries:
                url = canonical_url(entry.url)
                if url in candidates or not self._fresh(entry.published_at, cutoff):
                    continue
                candidates[url] = _Candidate(url, entry.url, entry.published_at, "feed", entry=entry)
                added += 1
            return added

        for feed_url in dict.fromkeys(brand.feeds):  # registry hints first
            if len(tried) < MAX_FEEDS_PER_BRAND:
                read(feed_url)
        if not candidates and brand.homepage:  # no hinted feed worked: use what the homepage advertises
            for feed_url in self._discover(brand, report):
                if feed_url not in tried and len(tried) < MAX_FEEDS_PER_BRAND and read(feed_url):
                    break

        if (not candidates or self.sitemap_topup) and len(candidates) < self.max_items:
            self._add_sitemap_candidates(brand, report, candidates, sites, cutoff)

        if not candidates and not report.used and not report.blocked and not report.errors:
            report.errors.append("no usable source (no feed or sitemap found)")
        ordered = sorted(candidates.values(), key=_recency)
        report.candidates = len(ordered)
        created: set[str] = set()
        for candidate in ordered[: self.max_items]:
            self._process(brand, candidate, report, cutoff, created)

    def _discover(self, brand: Brand, report: ScrapeReport) -> list[str]:
        try:
            resp = self.fetcher.get(brand.homepage or "")
            if resp.ok:
                return discover_feeds(resp.text, resp.url or brand.homepage or "")
        except BlockedByPolicy as err:
            self._blocked(report, err)
        except Exception:
            pass  # discovery is best effort
        return []

    def _read_feed(self, url: str, report: ScrapeReport) -> list[FeedEntry] | None:
        try:
            resp = self.fetcher.get(url)
            if not resp.ok:
                report.errors.append(f"feed {url}: HTTP {resp.status}")
                return None
            entries = parse_feed(resp.body, resp.url or url)
        except BlockedByPolicy as err:
            self._blocked(report, err)
            return None
        except Exception as err:  # includes ValueError for documents that are not feeds
            report.errors.append(f"feed {url}: {_err(err)}")
            return None
        report.used.append(f"feed:{url}")
        return entries[:MAX_FEED_ENTRIES]

    def _add_sitemap_candidates(self, brand: Brand, report: ScrapeReport, candidates: dict[str, _Candidate],
                                sites: set[str], cutoff: datetime) -> None:
        urls = list(brand.sitemaps)
        base = brand.homepage or next(iter(brand.feeds), None)
        if base:
            urls += self.fetcher.robots.sitemaps(base)
        pattern = content_pattern(brand.content_paths)

        def on_error(url: str, err: Exception) -> None:
            if isinstance(err, BlockedByPolicy):
                self._blocked(report, err)
            else:
                report.errors.append(f"sitemap {url}: {_err(err)}")

        for sitemap_url in list(dict.fromkeys(urls))[:MAX_SITEMAP_SOURCES]:
            found = iter_sitemap_urls(self.fetcher, sitemap_url, pattern=pattern, since=cutoff.isoformat(),
                                      max_urls=self.max_items, on_error=on_error)
            if not found:
                continue
            report.used.append(f"sitemap:{sitemap_url}")
            sites.add(_host(sitemap_url))
            for entry in found:
                url = canonical_url(entry.loc)
                if url not in candidates and self._on_site(url, sites):
                    candidates[url] = _Candidate(url, entry.loc, to_iso(entry.lastmod), "sitemap", sitemap=entry)
        if urls and not candidates and not report.blocked and not report.errors:
            report.errors.append(
                f"{len(urls)} sitemap(s) found but no content URLs matched within the crawl limits; "
                "add feeds, sitemaps or content_paths hints for this brand")

    # -- one candidate --------------------------------------------------------------
    def _process(self, brand: Brand, candidate: _Candidate, report: ScrapeReport, cutoff: datetime,
                 created: set[str]) -> None:
        if self.store.get_item(item_id_for_url(candidate.url)) is not None:
            report.skipped_existing += 1
            return
        if candidate.source == "feed" and not self.fetch_pages:
            # The page is not fetched, but a URL the site disallows for crawlers is not collected either.
            robots = self.fetcher.robots
            if not robots.allowed(candidate.fetch_url):
                self._blocked(report, BlockedByPolicy(candidate.fetch_url, f"robots: {robots.reason(candidate.fetch_url)}"))
                return
            if self.fetcher.tdmrep_reserved(candidate.fetch_url):
                self._blocked(report, BlockedByPolicy(candidate.fetch_url, "tdm-reservation"))
                return
            item = self._item_from_feed(brand, candidate)
        else:
            item = self._item_from_page(brand, candidate, report, cutoff)
        if item is None or item.id in created:
            return
        created.add(item.id)
        if self.store.get_item(item.id) is not None:  # the page's canonical URL was already known
            report.skipped_existing += 1
        elif self.store.upsert_item(item):
            report.new += 1

    def _item_from_feed(self, brand: Brand, candidate: _Candidate) -> ContentItem:
        entry = candidate.entry
        assert entry is not None
        excerpt = shorten(strip_byline_lead(entry.summary), EXCERPT_LIMIT)
        platform, fmt = _classify(candidate.url)
        return ContentItem(
            id=item_id_for_url(candidate.url), brand_id=brand.id, platform=platform, format=fmt,
            title=shorten(entry.title, EXCERPT_LIMIT), url=candidate.url, excerpt=excerpt,
            lang=guess_lang(f"{entry.title} {excerpt}"), published_at=entry.published_at,
            signals={"comments": float(entry.comments)} if entry.comments is not None else {},
            meta={"has_byline": entry.has_byline, "categories": entry.categories[:5], "source": "feed",
                  "first_party": False, "page_fetched": False},
            fetched_at=self._stamp(),
        )

    def _item_from_page(self, brand: Brand, candidate: _Candidate, report: ScrapeReport,
                        cutoff: datetime) -> ContentItem | None:
        try:
            resp = self.fetcher.get(candidate.fetch_url)
        except BlockedByPolicy as err:
            self._blocked(report, err)
            return None
        except Exception as err:
            report.errors.append(f"page {candidate.fetch_url}: {_err(err)}")
            return None
        if not resp.ok:
            report.errors.append(f"page {candidate.fetch_url}: HTTP {resp.status}")
            return None
        page = extract_page(resp.text, resp.url or candidate.fetch_url)
        if page.tdm_reservation:
            self._blocked(report, BlockedByPolicy(candidate.fetch_url, "tdm-reservation"))
            return None
        entry = candidate.entry
        published = page.published_at or (entry.published_at if entry else None) or candidate.published_at
        if not self._fresh(published, cutoff):
            return None
        url = page.canonical_url or candidate.url
        title = page.title or (entry.title if entry else "") or url
        excerpt = shorten(page.description or page.first_paragraph or (entry.summary if entry else ""), EXCERPT_LIMIT)
        platform, fmt = _classify(url, page.has_video)
        meta = {
            "schema_types": page.schema_types, "h1": page.h1_count, "h2": page.h2_count, "h3": page.h3_count,
            "list_items": page.list_items, "images": page.image_count, "has_video": page.has_video,
            "has_faq": page.has_faq, "has_byline": page.has_byline or bool(entry and entry.has_byline),
            "links_internal": page.links_internal, "links_external": page.links_external,
            "og_type": page.og_type, "modified_at": page.modified_at, "source": candidate.source,
            "first_party": False, "page_fetched": True,
        }
        if entry:
            meta["categories"] = entry.categories[:5]
        if candidate.sitemap and (candidate.sitemap.image_count or candidate.sitemap.video_count):
            meta["sitemap_images"] = candidate.sitemap.image_count
            meta["sitemap_videos"] = candidate.sitemap.video_count
        signals = {"comments": float(entry.comments)} if entry and entry.comments is not None else {}
        return ContentItem(
            id=item_id_for_url(url), brand_id=brand.id, platform=platform, format=fmt,
            title=shorten(title, EXCERPT_LIMIT), url=url, excerpt=excerpt,
            lang=page.lang or guess_lang(f"{title} {excerpt}"), published_at=published,
            word_count=page.word_count, signals=signals, meta=meta, fetched_at=self._stamp(),
        )

    # -- small helpers --------------------------------------------------------------
    @staticmethod
    def _on_site(url: str, sites: set[str]) -> bool:
        host = _host(url)
        return any(same_site(host, site) for site in sites if site)

    @staticmethod
    def _fresh(published_at: str | None, cutoff: datetime) -> bool:
        stamp = parse_datetime(published_at)
        return stamp is None or stamp >= cutoff

    def _blocked(self, report: ScrapeReport, err: BlockedByPolicy) -> None:
        report.blocked += 1
        if len(report.blocked_reasons) < MAX_REMEMBERED_BLOCKS:
            report.blocked_reasons.append(f"{err.url}: {err.reason}")

    def _now(self) -> datetime:
        stamp = self._clock()
        return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)

    def _stamp(self) -> str:
        return self._now().astimezone(timezone.utc).isoformat(timespec="seconds")

    def _say(self, message: str) -> None:
        if self._progress:
            self._progress(message)
