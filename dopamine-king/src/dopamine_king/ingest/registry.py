"""Brand registry: validated seed file, store seeding and polite endpoint verification.

Every endpoint in the seed file is only a hint. ``verify_brand`` confirms what a site really offers
(feeds advertised on the homepage, robots.txt Sitemap lines) with a handful of requests and never
guesses more than three feed URLs.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Iterable, Iterator
from urllib.parse import urljoin, urlsplit

from ..models import COHORTS, Brand, Serializable
from ..net import Fetcher
from ..store import Store
from .errors import BlockedByPolicy
from .feeds import discover_feeds, parse_feed
from .polite import PoliteFetcher, ensure_polite
from .robots import RobotsPolicy
from .sitemaps import DEFAULT_CONTENT_PATTERN, iter_sitemap_urls

REGISTRY_NOTE = (
    "Every endpoint in this file is a hint that must be confirmed by `kingctl sources verify` before "
    "scraping. Entries stay verified=false until that check passed."
)
MAX_FEED_FETCHES = 3
DEFAULT_FEED_PATHS = ("/feed", "/rss.xml", "/feed.xml")
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def default_registry_path() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "sources.seed.json"


def _is_url(value: object, *, https_only: bool = False) -> bool:
    if not isinstance(value, str) or any(ch.isspace() for ch in value):
        return False
    parts = urlsplit(value)
    return bool(parts.hostname) and (parts.scheme == "https" if https_only else parts.scheme in ("http", "https"))


def validate_brands(brands: Iterable[Brand]) -> list[str]:
    """Every problem found in a list of brands, one readable line each."""
    problems: list[str] = []
    seen: set[str] = set()
    for brand in brands:
        where = f"brand '{brand.id}'"
        if not isinstance(brand.id, str) or not _SLUG.match(brand.id):
            problems.append(f"{where}: id must be a lowercase slug")
        if brand.id in seen:
            problems.append(f"{where}: duplicate id")
        seen.add(brand.id)
        if not isinstance(brand.name, str) or not brand.name.strip():
            problems.append(f"{where}: name is empty")
        if brand.cohort not in COHORTS:
            problems.append(f"{where}: unknown cohort '{brand.cohort}'")
        if brand.country is not None and not re.fullmatch(r"[A-Z]{2}", str(brand.country)):
            problems.append(f"{where}: country must be an ISO alpha-2 code, got '{brand.country}'")
        if brand.homepage is not None and not _is_url(brand.homepage, https_only=True):
            problems.append(f"{where}: homepage must be an https URL, got '{brand.homepage}'")
        for label, values in (("feeds", brand.feeds), ("sitemaps", brand.sitemaps), ("content_paths", brand.content_paths)):
            if not isinstance(values, list):
                problems.append(f"{where}: {label} must be a list")
                continue
            for value in values:
                if label == "content_paths" and not (isinstance(value, str) and value.startswith("/")):
                    problems.append(f"{where}: content_paths entry must start with '/': '{value}'")
                elif label != "content_paths" and not _is_url(value):
                    problems.append(f"{where}: {label} entry is not an absolute http(s) URL: '{value}'")
    return problems


def load_registry(path: str | Path | None = None) -> list[Brand]:
    """Load and validate a registry file (default: the packaged seed). Raises ValueError listing all problems."""
    source = Path(path) if path else default_registry_path()
    try:
        data = json.loads(source.read_text("utf-8-sig"))
    except json.JSONDecodeError as err:
        raise ValueError(f"{source}: invalid JSON: {err}") from err
    rows = data.get("brands") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError(f"{source}: expected a list of brands under 'brands'")
    brands: list[Brand] = []
    problems: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not {"id", "name", "cohort"} <= set(row):
            problems.append(f"entry {index}: must be an object with id, name and cohort")
            continue
        row = {k: ([] if v is None and k in ("feeds", "sitemaps", "content_paths") else v) for k, v in row.items()}
        brands.append(Brand.from_dict(row))
    problems += validate_brands(brands)
    if problems:
        raise ValueError(f"{source}: {len(problems)} problem(s):\n" + "\n".join(f"- {p}" for p in problems))
    return brands


def save_registry(brands: list[Brand], path: str | Path, note: str = REGISTRY_NOTE) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "note": note, "brands": [b.to_dict() for b in brands]}
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")


def seed_store(store: Store, brands: list[Brand] | None = None) -> int:
    """Upsert brands (default: the packaged seed). A brand already verified in the store is not downgraded."""
    rows = brands if brands is not None else load_registry()
    for brand in rows:
        existing = store.get_brand(brand.id)
        if existing is not None and existing.verified and not brand.verified:
            continue
        store.upsert_brand(brand)
    return len(rows)


# -- verification ---------------------------------------------------------------------
@dataclass
class VerifyReport(Serializable):
    brand_id: str
    homepage_ok: bool = False
    robots_ok: bool = False
    feeds: list[str] = field(default_factory=list)
    sitemaps: list[str] = field(default_factory=list)
    sample_urls: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _probe_feed(fetcher: Fetcher, url: str) -> list[str] | None:
    """Entry URLs when ``url`` serves a real feed, None otherwise. Never raises."""
    try:
        resp = fetcher.get(url)
        if not resp.ok:
            return None
        return [entry.url for entry in parse_feed(resp.body, url)]
    except Exception:
        return None


def verify_brand(brand: Brand, fetcher: Fetcher, robots: RobotsPolicy | None = None) -> VerifyReport:
    polite: PoliteFetcher = ensure_polite(fetcher, robots)
    robots = robots or polite.robots
    report = VerifyReport(brand.id)
    if not brand.homepage:
        report.errors.append("no homepage in the registry")
        return report

    report.robots_ok = robots.allowed(brand.homepage)
    if not report.robots_ok:
        report.errors.append(f"robots.txt: {robots.reason(brand.homepage)}")
        return report
    report.sitemaps = robots.sitemaps(brand.homepage)[:5]

    html, base = "", brand.homepage
    try:
        resp = polite.get(brand.homepage)
        if resp.ok:
            report.homepage_ok = True
            html, base = resp.text, resp.url or brand.homepage
        else:
            report.errors.append(f"homepage returned HTTP {resp.status}")
    except BlockedByPolicy as err:
        report.errors.append(f"homepage blocked: {err.reason}")
    except Exception as err:
        report.errors.append(f"homepage unreachable: {err}")
    if not report.homepage_ok:
        return report

    report.feeds = discover_feeds(html, base)[:5]
    budget = MAX_FEED_FETCHES
    if report.feeds:
        samples = _probe_feed(polite, report.feeds[0])  # best effort, only to show what would be scraped
        budget -= 1
        report.sample_urls = (samples or [])[:3]
    else:
        candidates = list(brand.feeds)
        candidates += [urljoin(brand.homepage, f"{p.rstrip('/')}/feed") for p in brand.content_paths[:1]]
        candidates += [urljoin(brand.homepage, p) for p in DEFAULT_FEED_PATHS]
        tried: list[str] = []
        for url in candidates:
            if budget <= 0:
                break
            if url in tried:
                continue
            tried.append(url)
            budget -= 1
            entries = _probe_feed(polite, url)
            if entries is not None:
                report.feeds = [url]
                report.sample_urls = entries[:3]
                break

    if not report.sitemaps:
        for url in brand.sitemaps[:2]:
            found = iter_sitemap_urls(polite, url, max_urls=3, max_depth=1, max_sitemaps=2, pattern=None)
            if found:
                report.sitemaps.append(url)
                content = [e.loc for e in found if DEFAULT_CONTENT_PATTERN.search(e.loc)]
                report.sample_urls = report.sample_urls or content[:3]
    return report


def verify_all(
    brands: Iterable[Brand],
    fetcher: Fetcher,
    robots: RobotsPolicy | None = None,
    progress: Callable[[str], None] | None = None,
) -> Iterator[VerifyReport]:
    polite = ensure_polite(fetcher, robots)
    for brand in brands:
        if progress:
            progress(f"verifying {brand.id}")
        yield verify_brand(brand, polite, robots or polite.robots)


def apply_verification(brand: Brand, report: VerifyReport) -> Brand:
    """Copy of ``brand`` with confirmed endpoints. Unverified brands keep their hints and stay unverified."""
    ok = bool(report.homepage_ok and report.robots_ok and (report.feeds or report.sitemaps))
    if not ok:
        return replace(brand, feeds=list(brand.feeds), sitemaps=list(brand.sitemaps), verified=False)
    return replace(brand, feeds=list(report.feeds), sitemaps=list(report.sitemaps), verified=True)
