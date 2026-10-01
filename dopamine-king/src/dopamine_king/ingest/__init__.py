"""Ingest: polite, legal-minded collection of public brand content.

Order of preference is feeds, then sitemaps, then single pages. robots.txt (RFC 9309), Crawl-delay and
TDM reservations are enforced by ``PoliteFetcher``; only metadata, a short excerpt and derived numeric
features are stored.
"""
from .errors import BlockedByPolicy
from .extract import PageMeta, extract_page
from .feeds import FeedEntry, discover_feeds, parse_feed
from .pipeline import ScrapeReport, Scraper
from .polite import PoliteFetcher, ensure_polite
from .registry import (
    VerifyReport,
    apply_verification,
    load_registry,
    save_registry,
    seed_store,
    verify_all,
    verify_brand,
)
from .robots import RobotsPolicy
from .signals import enrich_signals, hn_signal, import_analytics_csv, parse_hn_response
from .sitemaps import DEFAULT_CONTENT_PATTERN, SitemapDoc, SitemapEntry, iter_sitemap_urls, parse_sitemap

__all__ = [
    "BlockedByPolicy", "DEFAULT_CONTENT_PATTERN", "FeedEntry", "PageMeta", "PoliteFetcher", "RobotsPolicy",
    "Scraper", "ScrapeReport", "SitemapDoc", "SitemapEntry", "VerifyReport", "apply_verification",
    "discover_feeds", "ensure_polite", "enrich_signals", "extract_page", "hn_signal", "import_analytics_csv",
    "iter_sitemap_urls", "load_registry", "parse_feed", "parse_hn_response", "parse_sitemap", "save_registry",
    "seed_store", "verify_all", "verify_brand",
]
