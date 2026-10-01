import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from dopamine_king.ingest.pipeline import Scraper, ScrapeReport
from dopamine_king.ingest.polite import PoliteFetcher
from dopamine_king.ingest.robots import RobotsPolicy
from dopamine_king.models import Brand, item_id_for_url
from dopamine_king.net import FakeFetcher, FetchError
from dopamine_king.store import Store

FX = Path(__file__).parent / "fixtures" / "ingest"
NOW = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
HOME = "https://acme.example/"
ROBOTS = "User-agent: *\nDisallow: /private\nSitemap: https://acme.example/sitemap.xml\n"
PLAIN_HOME = "<html><head><title>Acme</title></head><body>welcome</body></html>"
SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
RSS = (FX / "rss2.xml").read_bytes()
SPRING = "https://acme.example/blog/spring-trail-shoes-2026"


def article(title, *, published="2026-03-01T09:30:00+00:00", desc="A short description of the article.",
            head="", lang="en", canonical="", author="Jane Doe", paragraph=None):
    canon = f'<link rel="canonical" href="{canonical}">' if canonical else ""
    date = f'<meta property="article:published_time" content="{published}">' if published else ""
    para = paragraph or f"This is the opening paragraph of the article about {title}, long enough to be the lead."
    return (
        f'<!doctype html><html lang="{lang}"><head><title>{title}</title>'
        f'<meta property="og:title" content="{title}"><meta name="description" content="{desc}">{date}{canon}{head}'
        f'<script type="application/ld+json">{{"@type":"Article","author":{{"@type":"Person","name":"{author}"}}}}</script>'
        f'</head><body><nav><a href="/">Home</a></nav><article><h1>{title}</h1><p class="byline">By {author}</p>'
        f"<p>{para}</p><h2>Section one</h2><ul><li>a</li><li>b</li></ul><h2>Section two</h2><h3>Detail</h3>"
        '<img src="/i/1.jpg"><img src="/i/2.jpg"></article><footer>footer words</footer></body></html>'
    )


def urlset(*entries) -> str:
    rows = "".join(f"<url><loc>{loc}</loc>" + (f"<lastmod>{mod}</lastmod>" if mod else "") + "</url>" for loc, mod in entries)
    return f'<urlset xmlns="{SITEMAP_NS}">{rows}</urlset>'


def rss(*items) -> str:
    body = "".join(
        f"<item><title>{t}</title><link>{u}</link><pubDate>{d}</pubDate><description>{s}</description></item>"
        for t, u, d, s in items
    )
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>c</title>{body}</channel></rss>'


class PipelineBase(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.fetcher = FakeFetcher({"https://acme.example/robots.txt": ROBOTS, HOME: PLAIN_HOME})
        self.brand = Brand(id="acme", name="Acme", cohort="sport", country="US", homepage=HOME)

    def tearDown(self):
        self.store.close()

    def scraper(self, **kw) -> Scraper:
        kw.setdefault("now", lambda: NOW)
        return Scraper(self.store, self.fetcher, **kw)

    def items(self):
        return list(self.store.iter_items(brand_id="acme"))

    def fetched(self, fragment: str) -> list[str]:
        return [c for c in self.fetcher.calls if fragment in c]

    def sitemap_brand(self, *pages, mods=None):
        """Route a sitemap with the given {path: html} pages and return the brand."""
        entries = [(f"https://acme.example{path}", (mods or {}).get(path, "2026-03-01")) for path in pages]
        self.fetcher.routes["https://acme.example/sitemap.xml"] = urlset(*entries)
        return self.brand


class FeedRunTests(PipelineBase):
    def test_feed_only_run_builds_items_without_fetching_pages(self):
        brand = Brand(id="acme", name="Acme", cohort="sport", homepage=HOME, feeds=["https://acme.example/blog/feed"])
        self.fetcher.routes["https://acme.example/blog/feed"] = RSS
        report = self.scraper().scrape_brand(brand)
        self.assertEqual((report.candidates, report.new, report.skipped_existing, report.blocked), (4, 4, 0, 0))
        self.assertEqual(report.errors, [])
        self.assertEqual(report.used, ["feed:https://acme.example/blog/feed"])
        self.assertEqual(len(self.items()), 4)
        self.assertEqual(self.fetched("/blog/spring"), [])  # article pages were never requested
        self.assertEqual(self.fetched("/blog/pack"), [])
        self.assertNotIn(HOME, self.fetcher.calls)  # a working feed makes homepage discovery unnecessary

    def test_item_fields_from_a_feed_entry(self):
        brand = Brand(id="acme", name="Acme", cohort="sport", homepage=HOME, feeds=["https://acme.example/blog/feed"])
        self.fetcher.routes["https://acme.example/blog/feed"] = RSS
        self.scraper().scrape_brand(brand)
        item = self.store.get_item(item_id_for_url(SPRING))
        self.assertEqual(item.brand_id, "acme")
        self.assertEqual((item.platform, item.format, item.lang), ("blog", "article", "en"))
        self.assertEqual(item.title, "Spring trail shoes: what changed in 2026")
        self.assertEqual(item.url, SPRING)  # canonical: tracking parameters dropped
        self.assertEqual(item.published_at, "2026-03-01T08:30:00+00:00")
        self.assertEqual(item.excerpt, "Lighter foams, wider lasts and a few surprises. Here is what we learned testing 14 pairs.")
        self.assertIsNone(item.word_count)
        self.assertEqual(item.signals, {"comments": 12.0})
        self.assertEqual(item.meta["source"], "feed")
        self.assertIs(item.meta["first_party"], False)
        self.assertIs(item.meta["has_byline"], True)
        self.assertEqual(item.fetched_at, "2026-03-10T12:00:00+00:00")
        self.assertFalse(item.synthetic)

    def test_brand_row_is_created_so_cohort_queries_work(self):
        self.fetcher.routes["https://acme.example/blog/feed"] = RSS
        brand = Brand(id="acme", name="Acme", cohort="sport", homepage=HOME, feeds=["https://acme.example/blog/feed"])
        self.scraper().scrape_brand(brand)
        self.assertEqual(self.store.count_items(cohort="sport"), 4)

    def test_second_run_dedupes_against_the_store(self):
        brand = Brand(id="acme", name="Acme", cohort="sport", homepage=HOME, feeds=["https://acme.example/blog/feed"])
        self.fetcher.routes["https://acme.example/blog/feed"] = RSS
        scraper = self.scraper()
        scraper.scrape_brand(brand)
        again = scraper.scrape_brand(brand)
        self.assertEqual((again.new, again.skipped_existing, again.candidates), (0, 4, 4))
        self.assertEqual(self.store.count_items(brand_id="acme"), 4)

    def test_per_brand_cap_keeps_the_newest_candidates(self):
        brand = Brand(id="acme", name="Acme", cohort="sport", homepage=HOME, feeds=["https://acme.example/blog/feed"])
        self.fetcher.routes["https://acme.example/blog/feed"] = RSS
        report = self.scraper(max_items_per_brand=2).scrape_brand(brand)
        self.assertEqual((report.candidates, report.new), (4, 2))
        self.assertEqual({i.url for i in self.items()},
                         {"https://acme.example/blog/guid-only", "https://acme.example/blog/pack-your-bag"})

    def test_since_days_skips_old_items_but_keeps_undated_ones(self):
        brand = Brand(id="acme", name="Acme", cohort="sport", homepage=HOME, feeds=["https://acme.example/blog/feed"])
        self.fetcher.routes["https://acme.example/blog/feed"] = RSS
        report = self.scraper(since_days=7).scrape_brand(brand)
        self.assertEqual(report.new, 3)
        self.assertNotIn(SPRING, {i.url for i in self.items()})  # published 2026-03-01, cutoff is 2026-03-03
        self.assertIn("https://acme.example/blog/odd-date", {i.url for i in self.items()})

    def test_excerpt_and_title_never_exceed_300_characters(self):
        long_text = "lorem ipsum " * 200
        feed = rss((long_text, "https://acme.example/blog/long", "Sun, 01 Mar 2026 09:30:00 GMT", long_text))
        self.fetcher.routes["https://acme.example/blog/feed"] = feed
        brand = Brand(id="acme", name="Acme", cohort="sport", homepage=HOME, feeds=["https://acme.example/blog/feed"])
        self.scraper().scrape_brand(brand)
        item = self.items()[0]
        self.assertLessEqual(len(item.excerpt), 300)
        self.assertLessEqual(len(item.title), 300)
        self.assertGreater(len(item.excerpt), 100)

    def test_no_author_name_is_stored(self):
        brand = Brand(id="acme", name="Acme", cohort="sport", homepage=HOME, feeds=["https://acme.example/blog/feed"])
        self.fetcher.routes["https://acme.example/blog/feed"] = RSS
        self.scraper().scrape_brand(brand)
        stored = json.dumps([i.to_dict() for i in self.items()], ensure_ascii=False)
        self.assertNotIn("Jane Doe", stored)
        self.assertNotIn("Acme Press", stored)
        self.assertTrue(any(i.meta["has_byline"] for i in self.items()))

    def test_czech_text_is_detected_for_feed_items(self):
        feed = rss(("Nová limonáda bez cukru", "https://acme.example/novinky/limonada", "Mon, 02 Mar 2026 07:00:00 +0100",
                    "Příliš žluťoučký kůň úpěl ďábelské ódy"),
                   ("A plain English post", "https://acme.example/blog/plain", "Mon, 02 Mar 2026 07:00:00 +0100", "Nothing special"))
        self.fetcher.routes["https://acme.example/feed"] = feed
        brand = Brand(id="acme", name="Acme", cohort="cz-local", homepage=HOME, feeds=["https://acme.example/feed"])
        self.scraper().scrape_brand(brand)
        langs = {i.title: i.lang for i in self.items()}
        self.assertEqual(langs, {"Nová limonáda bez cukru": "cs", "A plain English post": "en"})

    def test_platform_and_format_classification(self):
        feed = rss(
            ("n", "https://acme.example/newsroom/q1-results", "Mon, 02 Mar 2026 07:00:00 GMT", ""),
            ("p", "https://acme.example/press-releases/launch", "Mon, 02 Mar 2026 07:00:00 GMT", ""),
            ("s", "https://acme.example/stories/jane", "Mon, 02 Mar 2026 07:00:00 GMT", ""),
            ("b", "https://acme.example/blog/press-kit-tips", "Mon, 02 Mar 2026 07:00:00 GMT", ""),
        )
        self.fetcher.routes["https://acme.example/feed"] = feed
        brand = Brand(id="acme", name="Acme", cohort="sport", homepage=HOME, feeds=["https://acme.example/feed"])
        self.scraper().scrape_brand(brand)
        kinds = {i.title: (i.platform, i.format) for i in self.items()}
        self.assertEqual(kinds, {"n": ("newsroom", "press"), "p": ("newsroom", "press"),
                                 "s": ("newsroom", "article"), "b": ("blog", "article")})

    def test_youtube_entries(self):
        feed = rss(("Demo", "https://www.youtube.com/watch?v=abc123", "Mon, 02 Mar 2026 07:00:00 GMT", "video"),
                   ("Short", "https://www.youtube.com/shorts/xyz", "Mon, 02 Mar 2026 07:00:00 GMT", "short"))
        feed_url = "https://www.youtube.com/feeds/videos.xml?channel_id=UC123"
        self.fetcher.routes[feed_url] = feed
        self.fetcher.routes["https://www.youtube.com/robots.txt"] = (404, "")
        brand = Brand(id="acme", name="Acme", cohort="sport", homepage=HOME, feeds=[feed_url])
        self.scraper().scrape_brand(brand)
        kinds = {i.title: (i.platform, i.format) for i in self.items()}
        self.assertEqual(kinds, {"Demo": ("youtube", "video"), "Short": ("youtube", "short")})

    def test_entries_on_hosts_that_disallow_crawling_are_not_collected_even_from_a_feed(self):
        feed = rss(("Ours", "https://acme.example/blog/ours", "Mon, 02 Mar 2026 07:00:00 GMT", "own summary"),
                   ("Partner", "https://news.partner.example/post", "Mon, 02 Mar 2026 07:00:00 GMT", "partner summary"))
        self.fetcher.routes["https://acme.example/feed"] = feed
        self.fetcher.routes["https://news.partner.example/robots.txt"] = "User-agent: *\nDisallow: /\n"
        brand = Brand(id="acme", name="Acme", cohort="sport", homepage=HOME, feeds=["https://acme.example/feed"])
        report = self.scraper().scrape_brand(brand)
        # Policy: nothing is stored about a URL the site disallows for crawlers, page fetched or not.
        self.assertEqual(sorted(i.title for i in self.items()), ["Ours"])
        self.assertEqual(report.blocked, 1)
        self.assertIn("news.partner.example/post: robots", report.blocked_reasons[0])
        self.store.close()
        self.store = Store()
        blocked = self.scraper(fetch_pages=True).scrape_brand(brand)
        self.assertEqual(blocked.blocked, 1)
        self.assertEqual(self.fetched("news.partner.example/post"), [])
        self.assertEqual(self.items(), [])

    def test_naive_clock_values_are_treated_as_utc(self):
        self.fetcher.routes["https://acme.example/blog/feed"] = RSS
        brand = Brand(id="acme", name="Acme", cohort="sport", homepage=HOME, feeds=["https://acme.example/blog/feed"])
        report = Scraper(self.store, self.fetcher, now=lambda: datetime(2026, 3, 10, 12, 0)).scrape_brand(brand)
        self.assertEqual((report.new, report.errors), (4, []))


class DiscoveryTests(PipelineBase):
    def test_feed_is_discovered_from_the_homepage_when_there_are_no_hints(self):
        self.fetcher.routes[HOME] = (FX / "home_with_feeds.html").read_text()
        self.fetcher.routes["https://acme.example/blog/feed"] = RSS
        report = self.scraper().scrape_brand(self.brand)
        self.assertEqual(report.new, 4)
        self.assertEqual(report.used, ["feed:https://acme.example/blog/feed"])
        self.assertEqual(self.fetched("/atom.xml"), [])  # the first productive feed is enough

    def test_a_failing_hint_falls_back_to_discovery(self):
        self.fetcher.routes[HOME] = (FX / "home_with_feeds.html").read_text()
        self.fetcher.routes["https://acme.example/blog/feed"] = RSS
        brand = Brand(id="acme", name="Acme", cohort="sport", homepage=HOME, feeds=["https://acme.example/dead-feed"])
        report = self.scraper().scrape_brand(brand)
        self.assertEqual(report.new, 4)
        self.assertEqual(len(report.errors), 1)
        self.assertIn("HTTP 404", report.errors[0])

    def test_at_most_three_feeds_are_read_per_brand(self):
        self.fetcher.routes[HOME] = (FX / "home_with_feeds.html").read_text()
        brand = Brand(id="acme", name="Acme", cohort="sport", homepage=HOME,
                      feeds=[f"https://acme.example/dead-{n}" for n in range(5)])
        self.scraper().scrape_brand(brand)
        self.assertEqual(len(self.fetched("/dead-")), 3)
        self.assertEqual(self.fetched("/blog/feed"), [])

    def test_brand_without_any_source_reports_it(self):
        self.fetcher.routes["https://acme.example/robots.txt"] = "User-agent: *\nDisallow: /private\n"
        report = self.scraper().scrape_brand(self.brand)
        self.assertEqual(report.new, 0)
        self.assertEqual(report.errors, ["no usable source (no feed or sitemap found)"])

    def test_a_dead_robots_sitemap_line_is_reported_as_an_error(self):
        report = self.scraper().scrape_brand(self.brand)  # robots.txt names /sitemap.xml, which is a 404
        self.assertEqual(report.new, 0)
        self.assertEqual(len(report.errors), 1)
        self.assertTrue(report.errors[0].startswith("sitemap https://acme.example/sitemap.xml"))


class SitemapRunTests(PipelineBase):
    def setUp(self):
        super().setUp()
        self.pages = {
            "/blog/alpha": article("Alpha post", published="2026-03-05T10:00:00+00:00"),
            "/blog/beta": article("Beta post", published="2026-03-03T10:00:00+00:00"),
            "/blog/gamma": article("Gamma post", published="2026-03-01T10:00:00+00:00"),
        }
        self.fetcher.routes.update({f"https://acme.example{p}": html for p, html in self.pages.items()})
        self.sitemap_brand(*self.pages, mods={"/blog/alpha": "2026-03-05", "/blog/beta": "2026-03-03", "/blog/gamma": "2026-03-01"})

    def test_sitemap_only_run_fetches_pages_and_extracts_features(self):
        report = self.scraper().scrape_brand(self.brand)
        self.assertEqual((report.candidates, report.new, report.blocked), (3, 3, 0))
        self.assertEqual(report.errors, [])
        self.assertEqual(report.used, ["sitemap:https://acme.example/sitemap.xml"])
        self.assertEqual(len(self.fetched("/blog/")), 3)
        item = self.store.get_item(item_id_for_url("https://acme.example/blog/alpha"))
        self.assertEqual(item.title, "Alpha post")
        self.assertEqual(item.published_at, "2026-03-05T10:00:00+00:00")
        self.assertEqual(item.excerpt, "A short description of the article.")
        self.assertEqual((item.platform, item.format, item.lang), ("blog", "article", "en"))
        self.assertGreater(item.word_count, 10)
        meta = item.meta
        self.assertEqual((meta["h1"], meta["h2"], meta["h3"], meta["list_items"], meta["images"]), (1, 2, 1, 2, 2))
        self.assertEqual((meta["has_video"], meta["has_faq"], meta["has_byline"]), (False, False, True))
        self.assertEqual((meta["source"], meta["first_party"]), ("sitemap", False))
        self.assertIn("Article", meta["schema_types"])

    def test_cap_limits_page_fetches(self):
        report = self.scraper(max_items_per_brand=2).scrape_brand(self.brand)
        self.assertEqual((report.candidates, report.new), (2, 2))  # sitemap traversal already keeps only the newest 2
        self.assertEqual(len(self.fetched("/blog/")), 2)
        self.assertEqual(self.fetched("/blog/gamma"), [])  # the oldest one is beyond the cap

    def test_second_run_does_not_refetch_known_pages(self):
        scraper = self.scraper()
        scraper.scrape_brand(self.brand)
        before = len(self.fetched("/blog/"))
        again = scraper.scrape_brand(self.brand)
        self.assertEqual((again.new, again.skipped_existing), (0, 3))
        self.assertEqual(len(self.fetched("/blog/")), before)

    def test_one_failing_page_is_tolerated(self):
        self.fetcher.routes["https://acme.example/blog/beta"] = (500, "server error")
        self.fetcher.routes["https://acme.example/blog/gamma"] = FetchError("connection reset by peer")
        report = self.scraper().scrape_brand(self.brand)
        self.assertEqual(report.new, 1)
        self.assertEqual(len(report.errors), 2)
        self.assertTrue(all(isinstance(e, str) and "Traceback" not in e for e in report.errors))
        self.assertTrue(any("HTTP 500" in e and "/blog/beta" in e for e in report.errors))
        self.assertTrue(any("connection reset" in e for e in report.errors))

    def test_tdm_reserved_page_is_blocked_and_not_stored(self):
        reserved = article("Reserved post", head='<meta name="tdm-reservation" content="1">')
        self.fetcher.routes["https://acme.example/blog/beta"] = reserved
        self.fetcher.routes["https://acme.example/blog/gamma"] = (200, article("Header post"), {"tdm-reservation": "1"})
        report = self.scraper().scrape_brand(self.brand)
        self.assertEqual((report.new, report.blocked), (1, 2))
        self.assertEqual([i.title for i in self.items()], ["Alpha post"])
        self.assertTrue(all("tdm-reservation" in r for r in report.blocked_reasons))

    def test_robots_disallowed_page_is_blocked_without_a_request(self):
        self.fetcher.routes["https://acme.example/robots.txt"] = (
            "User-agent: *\nDisallow: /blog/beta\nSitemap: https://acme.example/sitemap.xml\n")
        report = self.scraper().scrape_brand(self.brand)
        self.assertEqual((report.new, report.blocked), (2, 1))
        self.assertEqual(self.fetched("/blog/beta"), [])

    def test_canonical_url_is_stored_and_found_again_on_the_next_run(self):
        self.fetcher.routes["https://acme.example/blog/alpha"] = article("Alpha post", canonical="https://acme.example/blog/alpha-canonical")
        scraper = self.scraper()
        scraper.scrape_brand(self.brand)
        urls = {i.url for i in self.items()}
        self.assertIn("https://acme.example/blog/alpha-canonical", urls)
        self.assertNotIn("https://acme.example/blog/alpha", urls)
        again = scraper.scrape_brand(self.brand)
        self.assertEqual((again.new, again.skipped_existing), (0, 3))

    def test_page_dates_older_than_the_window_are_skipped_after_fetching(self):
        self.fetcher.routes["https://acme.example/blog/gamma"] = article("Gamma post", published="2024-01-01T00:00:00+00:00")
        report = self.scraper().scrape_brand(self.brand)
        self.assertEqual(report.new, 2)

    def test_sitemap_lastmod_is_the_fallback_date_and_giant_text_is_capped(self):
        self.fetcher.routes["https://acme.example/blog/alpha"] = article(
            "Alpha post", published="", desc="d " * 500, paragraph="p " * 500)
        self.scraper().scrape_brand(self.brand)
        item = self.store.get_item(item_id_for_url("https://acme.example/blog/alpha"))
        self.assertEqual(item.published_at, "2026-03-05T00:00:00+00:00")
        self.assertLessEqual(len(item.excerpt), 300)

    def test_content_paths_hint_widens_the_url_filter(self):
        self.fetcher.routes["https://acme.example/sitemap.xml"] = urlset(("https://acme.example/our-world/story-one", "2026-03-02"))
        self.fetcher.routes["https://acme.example/our-world/story-one"] = article("Story one")
        plain = self.scraper().scrape_brand(self.brand)
        self.assertEqual(plain.new, 0)
        hinted = Brand(id="acme", name="Acme", cohort="sport", homepage=HOME, content_paths=["/our-world"])
        self.assertEqual(self.scraper().scrape_brand(hinted).new, 1)

    def test_no_author_name_is_stored_from_pages(self):
        self.scraper().scrape_brand(self.brand)
        stored = json.dumps([i.to_dict() for i in self.items()], ensure_ascii=False)
        self.assertNotIn("Jane Doe", stored)
        self.assertTrue(all(i.meta["has_byline"] for i in self.items()))

    def test_excerpt_falls_back_to_the_lead_paragraph_and_skips_bylines(self):
        page = article("Alpha post", desc="", author="Jane Doe",
                       paragraph="Posted by Jane Doe on March 3, 2026</p><p>The lead paragraph is what readers see first on this page")
        self.fetcher.routes["https://acme.example/blog/alpha"] = page
        self.scraper().scrape_brand(self.brand)
        item = self.store.get_item(item_id_for_url("https://acme.example/blog/alpha"))
        self.assertEqual(item.excerpt, "The lead paragraph is what readers see first on this page")
        self.assertNotIn("Jane Doe", json.dumps(item.to_dict()))

    def test_czech_page_language_comes_from_the_page(self):
        self.fetcher.routes["https://acme.example/blog/alpha"] = (FX / "page_cs.html").read_text(encoding="utf-8")
        self.scraper().scrape_brand(self.brand)
        item = self.store.get_item(item_id_for_url("https://acme.example/blog/alpha"))
        self.assertEqual(item.lang, "cs")
        self.assertEqual(item.title, "Jak vybrat běžecké boty")


class MixedSourceTests(PipelineBase):
    def setUp(self):
        super().setUp()
        self.fetcher.routes["https://acme.example/blog/feed"] = RSS
        self.brand = Brand(id="acme", name="Acme", cohort="sport", homepage=HOME, feeds=["https://acme.example/blog/feed"])
        extra = {
            "/blog/extra-one": article("Extra one", published="2026-02-01T10:00:00+00:00"),
            "/blog/extra-two": article("Extra two", published="2026-01-15T10:00:00+00:00"),
        }
        self.fetcher.routes.update({f"https://acme.example{p}": html for p, html in extra.items()})
        self.fetcher.routes[SPRING + "?utm_source=sitemap"] = article("Spring page", published="2026-03-01T08:30:00+00:00")
        self.fetcher.routes["https://acme.example/sitemap.xml"] = urlset(
            ("https://acme.example/blog/extra-one", "2026-02-01"), ("https://acme.example/blog/extra-two", "2026-01-15"),
            (SPRING + "?utm_source=sitemap", "2026-03-01"),
        )

    def test_sitemaps_are_a_fallback_by_default(self):
        report = self.scraper().scrape_brand(self.brand)
        self.assertEqual(report.new, 4)
        self.assertEqual(self.fetched("sitemap.xml"), [])
        self.assertEqual(report.used, ["feed:https://acme.example/blog/feed"])

    def test_topup_adds_sitemap_pages_and_dedupes_against_the_feed(self):
        report = self.scraper(sitemap_topup=True).scrape_brand(self.brand)
        self.assertEqual((report.candidates, report.new), (6, 6))  # the sitemap copy of SPRING is the same page
        self.assertEqual(sorted(self.fetched("/blog/extra")), ["https://acme.example/blog/extra-one", "https://acme.example/blog/extra-two"])
        self.assertEqual(self.fetched("spring-trail-shoes"), [])  # known from the feed, never fetched
        sources = {i.url: i.meta["source"] for i in self.items()}
        self.assertEqual(sources[SPRING], "feed")
        self.assertEqual(sources["https://acme.example/blog/extra-one"], "sitemap")

    def test_topup_is_skipped_when_the_feed_already_fills_the_window(self):
        self.scraper(sitemap_topup=True, max_items_per_brand=4).scrape_brand(self.brand)
        self.assertEqual(self.fetched("sitemap.xml"), [])

    def test_a_dead_feed_falls_back_to_the_sitemap(self):
        self.fetcher.routes["https://acme.example/blog/feed"] = (404, "gone")
        report = self.scraper().scrape_brand(self.brand)
        self.assertEqual(report.new, 3)  # extra-one, extra-two and the spring page
        self.assertEqual(report.used, ["sitemap:https://acme.example/sitemap.xml"])
        self.assertTrue(any("feed" in e and "404" in e for e in report.errors))

    def test_a_feed_with_only_stale_entries_falls_back_to_the_sitemap(self):
        self.fetcher.routes["https://acme.example/blog/feed"] = rss(
            ("Old", "https://acme.example/blog/old", "Mon, 02 Mar 2020 07:00:00 GMT", "old"))
        report = self.scraper().scrape_brand(self.brand)
        self.assertEqual(report.new, 3)
        self.assertEqual(report.used, ["feed:https://acme.example/blog/feed", "sitemap:https://acme.example/sitemap.xml"])


class PolicyTests(PipelineBase):
    def test_robots_blocked_brand(self):
        self.fetcher.routes["https://acme.example/robots.txt"] = "User-agent: *\nDisallow: /\n"
        self.fetcher.routes["https://acme.example/blog/feed"] = RSS
        brand = Brand(id="acme", name="Acme", cohort="sport", homepage=HOME, feeds=["https://acme.example/blog/feed"],
                      sitemaps=["https://acme.example/sitemap.xml"])
        report = self.scraper().scrape_brand(brand)
        self.assertGreaterEqual(report.blocked, 1)
        self.assertEqual(report.new, 0)
        self.assertEqual(self.items(), [])
        self.assertEqual(self.fetcher.calls, ["https://acme.example/robots.txt"])  # nothing else was requested
        self.assertTrue(report.blocked_reasons[0].startswith("https://acme.example/"))

    def test_unavailable_robots_txt_blocks_the_brand_for_the_run(self):
        self.fetcher.routes["https://acme.example/robots.txt"] = (503, "maintenance")
        self.fetcher.routes["https://acme.example/blog/feed"] = RSS
        brand = Brand(id="acme", name="Acme", cohort="sport", homepage=HOME, feeds=["https://acme.example/blog/feed"])
        report = self.scraper().scrape_brand(brand)
        self.assertEqual((report.new, report.blocked >= 1), (0, True))

    def test_tdm_header_on_the_feed_blocks_everything_it_lists(self):
        self.fetcher.routes["https://acme.example/blog/feed"] = (200, RSS, {"tdm-reservation": "1"})
        brand = Brand(id="acme", name="Acme", cohort="sport", homepage=HOME, feeds=["https://acme.example/blog/feed"])
        report = self.scraper().scrape_brand(brand)
        self.assertEqual((report.new, report.blocked), (0, 1))
        self.assertEqual(self.items(), [])

    def test_tdmrep_json_blocks_feed_items_without_fetching_their_pages(self):
        self.fetcher.routes["https://acme.example/.well-known/tdmrep.json"] = '[{"location": "/blog/pack*", "tdm-reservation": 1}]'
        self.fetcher.routes["https://acme.example/blog/feed"] = RSS
        brand = Brand(id="acme", name="Acme", cohort="sport", homepage=HOME, feeds=["https://acme.example/blog/feed"])
        report = self.scraper().scrape_brand(brand)
        self.assertEqual((report.new, report.blocked), (3, 1))
        self.assertNotIn("https://acme.example/blog/pack-your-bag", {i.url for i in self.items()})
        self.assertEqual(self.fetched("pack-your-bag"), [])

    def test_fetch_pages_reads_pages_of_feed_entries_and_honours_tdm(self):
        feed = rss(("Open", "https://acme.example/blog/open", "Sun, 01 Mar 2026 09:30:00 GMT", "feed summary"),
                   ("Shut", "https://acme.example/blog/shut", "Sun, 01 Mar 2026 09:30:00 GMT", "feed summary"))
        self.fetcher.routes["https://acme.example/feed"] = feed
        self.fetcher.routes["https://acme.example/blog/open"] = article("Open", desc="page description")
        self.fetcher.routes["https://acme.example/blog/shut"] = article("Shut", head='<meta name="tdm-reservation" content="1">')
        brand = Brand(id="acme", name="Acme", cohort="sport", homepage=HOME, feeds=["https://acme.example/feed"])
        report = self.scraper(fetch_pages=True).scrape_brand(brand)
        self.assertEqual((report.new, report.blocked), (1, 1))
        item = self.items()[0]
        self.assertEqual((item.title, item.excerpt, item.meta["source"]), ("Open", "page description", "feed"))
        self.assertEqual((item.meta["h2"], item.meta["images"]), (2, 2))
        self.assertGreater(item.word_count, 10)

    def test_a_raw_fetcher_cannot_bypass_robots(self):
        self.fetcher.routes["https://acme.example/robots.txt"] = "User-agent: *\nDisallow: /blog/\n"
        self.fetcher.routes["https://acme.example/blog/feed"] = RSS
        self.fetcher.routes["https://acme.example/sitemap.xml"] = urlset(("https://acme.example/blog/a", "2026-03-01"))
        brand = Brand(id="acme", name="Acme", cohort="sport", homepage=HOME, feeds=["https://acme.example/blog/feed"],
                      sitemaps=["https://acme.example/sitemap.xml"])
        report = self.scraper().scrape_brand(brand)
        self.assertEqual(report.new, 0)
        self.assertGreaterEqual(report.blocked, 2)  # the feed and the page listed by the sitemap
        self.assertEqual(self.fetched("/blog/"), [])

    def test_an_existing_polite_fetcher_is_used_as_is_and_logs_to_the_store(self):
        self.fetcher.routes["https://acme.example/blog/feed"] = RSS
        polite = PoliteFetcher(self.fetcher, RobotsPolicy(self.fetcher, "test-agent"), self.store)
        brand = Brand(id="acme", name="Acme", cohort="sport", homepage=HOME, feeds=["https://acme.example/blog/feed"])
        scraper = Scraper(self.store, polite, now=lambda: NOW)
        self.assertIs(scraper.fetcher, polite)
        scraper.scrape_brand(brand)
        self.assertTrue(any(row["url"].endswith("/blog/feed") for row in self.store.recent_fetches()))


class RobustnessTests(PipelineBase):
    def test_unexpected_errors_are_recorded_not_raised(self):
        self.fetcher.routes["https://acme.example/blog/feed"] = RSS
        brand = Brand(id="acme", name="Acme", cohort="sport", homepage=HOME, feeds=["https://acme.example/blog/feed"])
        with mock.patch.object(self.store, "get_item", side_effect=RuntimeError("database exploded")):
            report = self.scraper().scrape_brand(brand)
        self.assertEqual(report.errors, ["unexpected: database exploded"])

    def test_garbage_feed_and_sitemap_documents_are_reported(self):
        self.fetcher.routes["https://acme.example/feed"] = "<html>this is not a feed</html>"
        self.fetcher.routes["https://acme.example/sitemap.xml"] = "<<< garbage"
        brand = Brand(id="acme", name="Acme", cohort="sport", homepage=HOME, feeds=["https://acme.example/feed"])
        report = self.scraper().scrape_brand(brand)
        self.assertEqual(report.new, 0)
        self.assertTrue(any(e.startswith("feed https://acme.example/feed") for e in report.errors))
        self.assertTrue(any(e.startswith("sitemap https://acme.example/sitemap.xml") for e in report.errors))

    def test_scrape_all_yields_one_report_per_brand_and_reports_progress(self):
        self.fetcher.routes["https://acme.example/blog/feed"] = RSS
        good = Brand(id="acme", name="Acme", cohort="sport", homepage=HOME, feeds=["https://acme.example/blog/feed"])
        other = Brand(id="other", name="Other", cohort="tech", homepage="https://other.example/")
        messages = []
        reports = list(self.scraper(progress=messages.append).scrape_all([good, other]))
        self.assertEqual([r.brand_id for r in reports], ["acme", "other"])
        self.assertEqual((reports[0].new, reports[1].new), (4, 0))
        self.assertTrue(all(isinstance(r, ScrapeReport) for r in reports))
        self.assertEqual([m for m in messages if m.endswith(": start")], ["acme: start", "other: start"])

    def test_report_to_dict_is_json_friendly(self):
        data = ScrapeReport("x", errors=["e"], used=["feed:u"]).to_dict()
        self.assertEqual(set(data), {"brand_id", "candidates", "new", "skipped_existing", "blocked", "errors", "used",
                                     "blocked_reasons"})
        json.dumps(data)


if __name__ == "__main__":
    unittest.main()
