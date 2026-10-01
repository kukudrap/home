import tempfile
import unittest

from dopamine_king.ingest.errors import BlockedByPolicy
from dopamine_king.ingest.polite import PoliteFetcher, ensure_polite, has_tdm_meta, parse_tdmrep
from dopamine_king.ingest.robots import RobotsPolicy, parse_robots
from dopamine_king.net import FakeFetcher, FetchError, HttpFetcher, Response
from dopamine_king.store import Store

UA = "DopamineKing/0.1 (+https://example.test/bot)"

ROBOTS = """\
# comment line
User-agent: *
Disallow: /private
Disallow: /search?
Crawl-delay: 5

User-agent: DopamineKing
User-agent: OtherBot
Allow: /private/press
Disallow: /private
Disallow: /*.pdf$
Crawl-delay: 2

Sitemap: https://a.test/sitemap.xml
Sitemap: https://a.test/news-sitemap.xml
Sitemap: ftp://a.test/ignored.xml
"""


def policy(routes, **kw):
    fetcher = FakeFetcher(routes)
    return RobotsPolicy(fetcher, UA, **kw), fetcher


class RobotsRuleTests(unittest.TestCase):
    def setUp(self):
        self.robots, self.fetcher = policy({"https://a.test/robots.txt": ROBOTS})

    def test_allow_and_disallow_by_prefix(self):
        self.assertTrue(self.robots.allowed("https://a.test/"))
        self.assertTrue(self.robots.allowed("https://a.test/blog/post"))
        self.assertFalse(self.robots.allowed("https://a.test/private"))
        self.assertFalse(self.robots.allowed("https://a.test/private/area"))

    def test_product_token_group_wins_over_wildcard_group(self):
        # the wildcard group disallows /search? but the DopamineKing group says nothing about it
        self.assertTrue(self.robots.allowed("https://a.test/search?q=x"))
        wildcard_only, _ = policy({"https://b.test/robots.txt": ROBOTS.replace("DopamineKing", "SomeoneElse")})
        self.assertFalse(wildcard_only.allowed("https://b.test/search?q=x"))

    def test_wildcard_group_is_the_fallback(self):
        text = "User-agent: *\nDisallow: /secret\n\nUser-agent: Googlebot\nDisallow: /\n"
        robots, _ = policy({"https://c.test/robots.txt": text})
        self.assertFalse(robots.allowed("https://c.test/secret/a"))
        self.assertTrue(robots.allowed("https://c.test/open"))

    def test_product_token_match_ignores_case_and_version(self):
        text = "User-agent: dopamineking/0.9\nDisallow: /x\n\nUser-agent: *\nDisallow:\n"
        robots, _ = policy({"https://c.test/robots.txt": text})
        self.assertFalse(robots.allowed("https://c.test/x"))
        self.assertTrue(robots.allowed("https://c.test/y"))

    def test_groups_naming_the_same_agent_are_merged(self):
        text = "User-agent: DopamineKing\nDisallow: /a\n\nUser-agent: Other\nDisallow: /z\n\nUser-agent: DopamineKing\nDisallow: /b\n"
        robots, _ = policy({"https://c.test/robots.txt": text})
        self.assertFalse(robots.allowed("https://c.test/a"))
        self.assertFalse(robots.allowed("https://c.test/b"))
        self.assertTrue(robots.allowed("https://c.test/z"))

    def test_longest_match_wins_and_allow_wins_ties(self):
        self.assertTrue(self.robots.allowed("https://a.test/private/press/launch"))
        text = "User-agent: *\nDisallow: /same\nAllow: /same\n"
        robots, _ = policy({"https://c.test/robots.txt": text})
        self.assertTrue(robots.allowed("https://c.test/same"))

    def test_star_and_dollar_wildcards(self):
        self.assertFalse(self.robots.allowed("https://a.test/files/report.pdf"))
        self.assertTrue(self.robots.allowed("https://a.test/files/report.pdf?download=1"))
        self.assertTrue(self.robots.allowed("https://a.test/files/report.html"))

    def test_empty_disallow_allows_everything(self):
        robots, _ = policy({"https://c.test/robots.txt": "User-agent: *\nDisallow:\n"})
        self.assertTrue(robots.allowed("https://c.test/anything"))

    def test_query_string_is_part_of_the_matched_path(self):
        robots, _ = policy({"https://c.test/robots.txt": "User-agent: *\nDisallow: /search?\n"})
        self.assertFalse(robots.allowed("https://c.test/search?q=1"))
        self.assertTrue(robots.allowed("https://c.test/search"))

    def test_percent_encoding_and_non_ascii_paths_compare_equal(self):
        text = "User-agent: *\nDisallow: /čl%C3%A1nky/tajne\n"
        robots, _ = policy({"https://c.test/robots.txt": text})
        self.assertFalse(robots.allowed("https://c.test/%C4%8Dl%C3%A1nky/tajne"))
        self.assertFalse(robots.allowed("https://c.test/články/tajne/x"))

    def test_bom_crlf_comments_and_unknown_lines(self):
        text = chr(0xFEFF) + "User-agent: *\r\nDisallow: /x # trailing comment\r\nNoise line without colon\r\nHost: a.test\r\n"
        parsed = parse_robots(text)
        self.assertEqual(len(parsed.groups), 1)
        robots, _ = policy({"https://c.test/robots.txt": text})
        self.assertFalse(robots.allowed("https://c.test/x"))

    def test_robots_txt_itself_is_always_fetchable(self):
        robots, _ = policy({"https://c.test/robots.txt": "User-agent: *\nDisallow: /\n"})
        self.assertTrue(robots.allowed("https://c.test/robots.txt"))
        self.assertFalse(robots.allowed("https://c.test/page"))

    def test_non_http_urls_are_not_allowed(self):
        self.assertFalse(self.robots.allowed("ftp://a.test/file"))
        self.assertFalse(self.robots.allowed("mailto:someone@a.test"))


class RobotsAvailabilityTests(unittest.TestCase):
    def test_404_means_allow_all(self):
        robots, _ = policy({"https://a.test/robots.txt": (404, "nope")})
        self.assertTrue(robots.allowed("https://a.test/anything"))
        self.assertIn("404", robots.reason("https://a.test/anything"))

    def test_other_4xx_also_means_allow_all(self):
        robots, _ = policy({"https://a.test/robots.txt": (403, "forbidden")})
        self.assertTrue(robots.allowed("https://a.test/anything"))

    def test_503_means_disallow_all(self):
        robots, _ = policy({"https://a.test/robots.txt": (503, "down")})
        self.assertFalse(robots.allowed("https://a.test/anything"))
        self.assertIn("503", robots.reason("https://a.test/anything"))

    def test_429_is_treated_like_a_server_error(self):
        robots, _ = policy({"https://a.test/robots.txt": (429, "slow down")})
        self.assertFalse(robots.allowed("https://a.test/anything"))

    def test_unreachable_means_disallow_all(self):
        robots, _ = policy({"https://a.test/robots.txt": FetchError("connection reset")})
        self.assertFalse(robots.allowed("https://a.test/anything"))
        self.assertIn("unreachable", robots.reason("https://a.test/anything"))
        self.assertEqual(robots.sitemaps("https://a.test/"), [])
        self.assertIsNone(robots.crawl_delay("a.test"))

    def test_robots_txt_is_fetched_once_per_host(self):
        robots, fetcher = policy({"https://a.test/robots.txt": ROBOTS, "https://b.test/robots.txt": "User-agent: *\nDisallow:\n"})
        for path in ("/", "/blog", "/private", "/x.pdf"):
            robots.allowed("https://a.test" + path)
        robots.crawl_delay("a.test")
        robots.sitemaps("https://a.test/whatever")
        robots.reason("https://a.test/blog")
        self.assertEqual(fetcher.calls, ["https://a.test/robots.txt"])
        robots.allowed("https://b.test/")
        self.assertEqual(fetcher.calls, ["https://a.test/robots.txt", "https://b.test/robots.txt"])

    def test_failure_is_cached_for_the_run(self):
        state = {"n": 0}

        def flaky(url, headers):
            state["n"] += 1
            return (503, "down") if state["n"] == 1 else (200, "User-agent: *\nDisallow:\n")

        robots, fetcher = policy({"https://a.test/robots.txt": flaky})
        self.assertFalse(robots.allowed("https://a.test/a"))
        self.assertFalse(robots.allowed("https://a.test/b"))
        self.assertEqual(len(fetcher.calls), 1)

    def test_redirects_are_followed_and_loops_fail_closed(self):
        ok, _ = policy({
            "https://a.test/robots.txt": (301, "", {"Location": "/real-robots.txt"}),
            "https://a.test/real-robots.txt": "User-agent: *\nDisallow: /x\n",
        })
        self.assertFalse(ok.allowed("https://a.test/x"))
        self.assertTrue(ok.allowed("https://a.test/y"))
        loop, fetcher = policy({"https://a.test/robots.txt": (302, "", {"Location": "https://a.test/robots.txt"})})
        self.assertFalse(loop.allowed("https://a.test/y"))
        self.assertLessEqual(len(fetcher.calls), 7)

    def test_sends_the_configured_user_agent(self):
        seen = []

        def capture(url, headers):
            seen.append(headers)
            return "User-agent: *\nDisallow:\n"

        robots, _ = policy({"https://a.test/robots.txt": capture})
        robots.allowed("https://a.test/")
        self.assertEqual(seen[0]["User-Agent"], UA)


class RobotsMetadataTests(unittest.TestCase):
    def setUp(self):
        self.robots, _ = policy({"https://a.test/robots.txt": ROBOTS})

    def test_crawl_delay_prefers_the_product_group(self):
        self.assertEqual(self.robots.crawl_delay("a.test"), 2.0)

    def test_crawl_delay_falls_back_to_wildcard_group_and_none(self):
        text = "User-agent: *\nCrawl-delay: 7.5\n"
        robots, _ = policy({"https://c.test/robots.txt": text, "https://d.test/robots.txt": "User-agent: *\nDisallow:\n"})
        self.assertEqual(robots.crawl_delay("c.test"), 7.5)
        self.assertIsNone(robots.crawl_delay("d.test"))

    def test_sitemap_lines_are_collected_and_filtered(self):
        self.assertEqual(
            self.robots.sitemaps("a.test"), ["https://a.test/sitemap.xml", "https://a.test/news-sitemap.xml"]
        )
        self.assertEqual(self.robots.sitemaps("https://a.test/some/page"), self.robots.sitemaps("a.test"))

    def test_reason_explains_the_deciding_rule(self):
        self.assertIn("Disallow: /private", self.robots.reason("https://a.test/private/x"))
        self.assertIn("DopamineKing", self.robots.reason("https://a.test/private/x"))
        self.assertIn("Allow: /private/press", self.robots.reason("https://a.test/private/press/a"))
        self.assertIn("no matching rule", self.robots.reason("https://a.test/blog"))


class PoliteFetcherTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.inner = FakeFetcher({
            "https://a.test/robots.txt": ROBOTS,
            "https://a.test/blog/post": ("<html><body>hello</body></html>"),
            "https://a.test/private/x": "secret",
        })
        self.robots = RobotsPolicy(self.inner, UA)
        self.polite = PoliteFetcher(self.inner, self.robots, self.store)

    def tearDown(self):
        self.store.close()

    def test_blocked_url_never_reaches_the_inner_fetcher(self):
        with self.assertRaises(BlockedByPolicy) as ctx:
            self.polite.get("https://a.test/private/x")
        self.assertNotIn("https://a.test/private/x", self.inner.calls)
        self.assertEqual(ctx.exception.url, "https://a.test/private/x")
        self.assertTrue(ctx.exception.reason.startswith("robots"))
        self.assertIsInstance(ctx.exception, FetchError)

    def test_allowed_url_passes_through_with_user_agent(self):
        seen = []
        self.inner.routes["https://a.test/blog/ua"] = lambda url, headers: (seen.append(headers), "ok")[1]
        resp = self.polite.get("https://a.test/blog/ua")
        self.assertEqual(resp.text, "ok")
        self.assertEqual(seen[0]["User-Agent"], UA)
        self.polite.get("https://a.test/blog/ua", headers={"user-agent": "custom"})
        self.assertEqual(seen[1], {"user-agent": "custom"})

    def test_fetches_are_logged_to_the_store(self):
        self.polite.get("https://a.test/blog/post")
        with self.assertRaises(BlockedByPolicy):
            self.polite.get("https://a.test/private/x")
        log = {row["url"]: row for row in self.store.recent_fetches()}
        self.assertEqual(log["https://a.test/blog/post"]["status"], 200)
        self.assertIsNone(log["https://a.test/private/x"]["status"])
        self.assertIn("blocked", log["https://a.test/private/x"]["note"])

    def test_works_without_a_store(self):
        polite = PoliteFetcher(self.inner, self.robots)
        self.assertTrue(polite.get("https://a.test/blog/post").ok)

    def test_robots_txt_fetch_bypasses_the_policy_checks(self):
        everything_blocked = FakeFetcher({"https://z.test/robots.txt": "User-agent: *\nDisallow: /\n"})
        polite = PoliteFetcher(everything_blocked, RobotsPolicy(everything_blocked, UA), self.store)
        self.assertTrue(polite.get("https://z.test/robots.txt").ok)

    def test_network_errors_are_logged_and_reraised(self):
        self.inner.routes["https://a.test/blog/down"] = FetchError("boom")
        with self.assertRaises(FetchError):
            self.polite.get("https://a.test/blog/down")
        self.assertIn("error", self.store.recent_fetches(1)[0]["note"])

    def test_crawl_delay_is_applied_when_the_inner_fetcher_supports_it(self):
        class Recording(FakeFetcher):
            delays: dict = {}

            def set_host_delay(self, host, seconds):
                self.delays = {**self.delays, host: seconds}

        inner = Recording({"https://a.test/robots.txt": ROBOTS, "https://a.test/blog/post": "x"})
        polite = PoliteFetcher(inner, RobotsPolicy(inner, UA))
        polite.get("https://a.test/blog/post")
        self.assertEqual(inner.delays, {"a.test": 2.0})
        PoliteFetcher(self.inner, self.robots).get("https://a.test/blog/post")  # no set_host_delay: no error

    def test_crawl_delay_is_honoured_by_the_real_http_fetcher(self):
        sleeps, clock = [], [0.0]

        def sleep(seconds):
            sleeps.append(seconds)
            clock[0] += seconds

        def transport(url, headers, timeout, max_bytes):
            body = ROBOTS if url.endswith("/robots.txt") else "page"
            return Response(url, 200, {}, body.encode())

        http = HttpFetcher(UA, transport=transport, sleep=sleep, clock=lambda: clock[0], min_interval=1.0)
        polite = PoliteFetcher(http, RobotsPolicy(http, UA))
        polite.get("https://a.test/blog/1")
        polite.get("https://a.test/blog/2")
        self.assertTrue(sleeps)
        self.assertTrue(all(seconds >= 2.0 for seconds in sleeps))  # Crawl-delay: 2 beats the 1 second default

    def test_absurd_crawl_delay_blocks_instead_of_hanging(self):
        inner = FakeFetcher({"https://s.test/robots.txt": "User-agent: *\nCrawl-delay: 86400\n", "https://s.test/p": "x"})
        polite = PoliteFetcher(inner, RobotsPolicy(inner, UA))
        with self.assertRaises(BlockedByPolicy) as ctx:
            polite.get("https://s.test/p")
        self.assertEqual(ctx.exception.reason, "crawl-delay-too-long")
        self.assertNotIn("https://s.test/p", inner.calls)


class TdmTests(unittest.TestCase):
    def make(self, routes, **kw):
        routes = {"https://t.test/robots.txt": "User-agent: *\nDisallow:\n", **routes}
        inner = FakeFetcher(routes)
        return PoliteFetcher(inner, RobotsPolicy(inner, UA), Store(), **kw), inner

    def test_tdm_reservation_header_blocks(self):
        polite, _ = self.make({"https://t.test/page": (200, "<html>text</html>", {"TDM-Reservation": "1"})})
        with self.assertRaises(BlockedByPolicy) as ctx:
            polite.get("https://t.test/page")
        self.assertEqual(ctx.exception.reason, "tdm-reservation")
        self.assertIn("header", polite.store.recent_fetches(1)[0]["note"])

    def test_reservation_survives_the_http_cache(self):
        calls = []

        def transport(url, headers, timeout, max_bytes):
            calls.append(url)
            if url.endswith("/robots.txt"):
                return Response(url, 200, {}, b"User-agent: *\nDisallow:\n")
            return Response(url, 200, {"tdm-reservation": "1", "content-type": "text/html"}, b"<html>text</html>")

        with tempfile.TemporaryDirectory() as tmp:
            http = HttpFetcher(UA, transport=transport, cache_dir=tmp, min_interval=0, sleep=lambda s: None)
            polite = PoliteFetcher(http, RobotsPolicy(http, UA), check_tdmrep=False)
            for _ in range(2):
                with self.assertRaises(BlockedByPolicy):
                    polite.get("https://t.test/page")
        self.assertEqual(calls.count("https://t.test/page"), 1)  # the second block came from the cache replay

    def test_tdm_header_zero_does_not_block(self):
        polite, _ = self.make({"https://t.test/page": (200, "<html>text</html>", {"tdm-reservation": "0"})})
        self.assertTrue(polite.get("https://t.test/page").ok)

    def test_tdm_meta_tag_blocks_html_pages(self):
        html = '<html><head><meta name="tdm-reservation" content="1"></head><body>x</body></html>'
        polite, _ = self.make({"https://t.test/page": (200, html, {"content-type": "text/html; charset=utf-8"})})
        with self.assertRaises(BlockedByPolicy) as ctx:
            polite.get("https://t.test/page")
        self.assertEqual(ctx.exception.reason, "tdm-reservation")
        self.assertIn("meta", polite.store.recent_fetches(1)[0]["note"])

    def test_tdm_meta_tag_variants(self):
        for tag in ("<META CONTENT='1' NAME='TDM-Reservation'>", '<meta name=tdm-reservation content=1 />',
                    '<meta  content="1"\n name="tdm-reservation"/>'):
            self.assertTrue(has_tdm_meta(f"<head>{tag}</head>"), tag)
        for tag in ('<meta name="tdm-reservation" content="0">', '<meta name="robots" content="1">', "<p>tdm-reservation</p>"):
            self.assertFalse(has_tdm_meta(f"<head>{tag}</head>"), tag)

    def test_meta_text_inside_a_feed_body_is_not_a_reservation(self):
        body = '<rss><channel><item><description>&lt;meta name="tdm-reservation" content="1"&gt;</description></item></channel></rss>'
        polite, _ = self.make({"https://t.test/feed": (200, body, {"content-type": "application/rss+xml"})})
        self.assertTrue(polite.get("https://t.test/feed").ok)

    def test_html_without_content_type_is_sniffed(self):
        html = '<!DOCTYPE html><html><head><meta name="tdm-reservation" content="1"></head></html>'
        polite, _ = self.make({"https://t.test/page": html})
        with self.assertRaises(BlockedByPolicy):
            polite.get("https://t.test/page")

    def test_tdmrep_json_blocks_before_the_page_is_requested(self):
        rules = '[{"location": "/reserved/*", "tdm-reservation": 1}, {"location": "/*", "tdm-reservation": 0}]'
        polite, inner = self.make({
            "https://t.test/.well-known/tdmrep.json": rules,
            "https://t.test/reserved/a": "content", "https://t.test/open/a": "content",
        })
        with self.assertRaises(BlockedByPolicy) as ctx:
            polite.get("https://t.test/reserved/a")
        self.assertEqual(ctx.exception.reason, "tdm-reservation")
        self.assertNotIn("https://t.test/reserved/a", inner.calls)
        self.assertTrue(polite.get("https://t.test/open/a").ok)
        self.assertTrue(polite.tdmrep_reserved("https://t.test/reserved/zzz"))
        self.assertFalse(polite.tdmrep_reserved("https://t.test/open/zzz"))
        self.assertEqual(inner.calls.count("https://t.test/.well-known/tdmrep.json"), 1)

    def test_tdmrep_first_matching_rule_wins(self):
        rules = parse_tdmrep([{"location": "/open/*", "tdm-reservation": 0}, {"location": "/*", "tdm-reservation": 1}])
        self.assertFalse(next(r for p, r in rules if p.match("/open/a")))
        self.assertTrue(next(r for p, r in rules if p.match("/closed/a")))

    def test_malformed_tdmrep_is_ignored_and_can_be_switched_off(self):
        polite, _ = self.make({"https://t.test/.well-known/tdmrep.json": "{not json", "https://t.test/p": "x"})
        self.assertTrue(polite.get("https://t.test/p").ok)
        off, inner = self.make({"https://t.test/.well-known/tdmrep.json": '[{"location": "/*", "tdm-reservation": 1}]',
                                "https://t.test/p": "x"}, check_tdmrep=False)
        self.assertTrue(off.get("https://t.test/p").ok)
        self.assertNotIn("https://t.test/.well-known/tdmrep.json", inner.calls)

    def test_ensure_polite_wraps_raw_fetchers_only(self):
        raw = FakeFetcher({"https://t.test/robots.txt": "User-agent: *\nDisallow: /\n"})
        wrapped = ensure_polite(raw)
        self.assertIsInstance(wrapped, PoliteFetcher)
        with self.assertRaises(BlockedByPolicy):
            wrapped.get("https://t.test/x")
        self.assertIs(ensure_polite(wrapped), wrapped)


if __name__ == "__main__":
    unittest.main()
