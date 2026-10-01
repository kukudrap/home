"""End to end scrape against a real local HTTP server: real urllib transport, real robots.txt over HTTP."""
import gzip
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dopamine_king.ingest.pipeline import Scraper
from dopamine_king.ingest.polite import PoliteFetcher
from dopamine_king.ingest.robots import RobotsPolicy
from dopamine_king.models import Brand
from dopamine_king.net import HttpFetcher
from dopamine_king.store import Store

LONG_LEAD = "By Ana Novakova. " + "word " * 80   # a byline lead that must not leak into the excerpt


def build_site(port: int) -> dict:
    base = f"http://127.0.0.1:{port}"
    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:slash="http://purl.org/rss/1.0/modules/slash/" xmlns:dc="http://purl.org/dc/elements/1.1/">
<channel><title>Acme blog</title><link>{base}/</link>
<item><title>7 mistakes new runners make</title><link>{base}/blog/mistakes?utm_source=rss</link>
<pubDate>Tue, 15 Sep 2026 09:00:00 +0000</pubDate><dc:creator>Ana Novakova</dc:creator><slash:comments>12</slash:comments>
<description>&lt;p&gt;{LONG_LEAD}&lt;/p&gt;</description></item>
<item><title>Members only roadmap</title><link>{base}/private/roadmap</link><pubDate>Tue, 15 Sep 2026 10:00:00 +0000</pubDate>
<description>secret</description></item>
<item><title>Reserved for miners</title><link>{base}/blog/tdm-reserved</link><pubDate>Tue, 15 Sep 2026 11:00:00 +0000</pubDate>
<description>rights reserved</description></item>
</channel></rss>"""
    robots = f"User-agent: *\nDisallow: /private/\nSitemap: {base}/sitemap.xml\n"
    return {"/robots.txt": ("text/plain", robots), "/feed.xml": ("application/rss+xml", rss)}


class SiteHandler(BaseHTTPRequestHandler):
    site: dict = {}
    hits: list = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        type(self).hits.append(self.path)
        if path == "/blog/tdm-reserved":
            body = b"<html><title>Reserved</title><p>text</p></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("tdm-reservation", "1")
        elif path in self.site:
            ctype, text = self.site[path]
            body = gzip.compress(text.encode())
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Encoding", "gzip")
        else:
            body = b"not found"
            self.send_response(404)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class LocalScrapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), SiteHandler)
        cls.port = cls.httpd.server_address[1]
        SiteHandler.site = build_site(cls.port)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self):
        SiteHandler.hits = []
        self.store = Store()
        self.brand = Brand(id="acme", name="Acme", cohort="sport", homepage=f"http://127.0.0.1:{self.port}/",
                           feeds=[f"http://127.0.0.1:{self.port}/feed.xml"])
        self.store.upsert_brand(self.brand)
        inner = HttpFetcher("DopamineKing-test/0.1", min_interval=0, max_retries=0)
        self.polite = PoliteFetcher(inner, RobotsPolicy(inner, "DopamineKing-test/0.1"), self.store)

    def tearDown(self):
        self.store.close()

    def run_scrape(self):
        return Scraper(self.store, self.polite, max_items_per_brand=10, since_days=3650,
                       now=lambda: __import__("datetime").datetime(2026, 9, 20, tzinfo=__import__("datetime").timezone.utc)
                       ).scrape_brand(self.brand)

    def test_feed_scrape_honours_robots_and_stores_only_minimal_data(self):
        report = self.run_scrape()
        items = list(self.store.iter_items())
        titles = {i.title for i in items}
        self.assertIn("7 mistakes new runners make", titles)
        self.assertNotIn("Members only roadmap", titles)           # robots.txt disallows /private/
        self.assertFalse(any("/private/" in h for h in SiteHandler.hits if h != "/robots.txt"))
        item = next(i for i in items if i.title.startswith("7 mistakes"))
        self.assertLessEqual(len(item.excerpt), 300)
        self.assertNotIn("Novakova", item.excerpt)                  # no author name in the excerpt
        self.assertNotIn("Novakova", str(item.meta))                # nor anywhere else
        self.assertTrue(item.meta["has_byline"])
        self.assertEqual(item.signals.get("comments"), 12.0)
        self.assertIn("/blog/mistakes", item.url)
        self.assertNotIn("utm_", item.url)                          # tracking parameters stripped
        self.assertEqual(report.new, len(items))
        self.assertTrue(self.store.recent_fetches(5))               # every request is logged

    def test_page_fetching_mode_honours_the_tdm_reservation_header(self):
        report = Scraper(self.store, self.polite, max_items_per_brand=10, since_days=3650, fetch_pages=True,
                         now=lambda: __import__("datetime").datetime(2026, 9, 20, tzinfo=__import__("datetime").timezone.utc)
                         ).scrape_brand(self.brand)
        titles = {i.title for i in self.store.iter_items()}
        self.assertNotIn("Reserved for miners", titles)
        self.assertNotIn("Members only roadmap", titles)
        self.assertTrue(any("tdm-reservation" in r for r in report.blocked_reasons), report.blocked_reasons)
        self.assertGreaterEqual(report.blocked, 2)

    def test_second_run_deduplicates(self):
        first = self.run_scrape()
        second = self.run_scrape()
        self.assertGreater(first.new, 0)
        self.assertEqual(second.new, 0)
        self.assertGreaterEqual(second.skipped_existing, first.new)

    def test_robots_is_fetched_over_http_and_cached(self):
        self.run_scrape()
        self.assertEqual(SiteHandler.hits.count("/robots.txt"), 1)


if __name__ == "__main__":
    unittest.main()
