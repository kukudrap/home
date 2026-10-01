import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit

from dopamine_king.ingest.polite import PoliteFetcher
from dopamine_king.ingest.registry import (
    VerifyReport,
    apply_verification,
    default_registry_path,
    load_registry,
    save_registry,
    seed_store,
    validate_brands,
    verify_all,
    verify_brand,
)
from dopamine_king.ingest.robots import RobotsPolicy
from dopamine_king.models import COHORTS, Brand
from dopamine_king.net import FakeFetcher, FetchError
from dopamine_king.store import Store

FX = Path(__file__).parent / "fixtures" / "ingest"
UA = "DopamineKing/0.1 (test)"
HOME = "https://acme.example/"
HOME_WITH_FEED = '<html><head><link rel="alternate" type="application/rss+xml" href="/blog/feed"></head><body>hi</body></html>'
PLAIN_HOME = "<html><head><title>Acme</title></head><body>no feeds advertised</body></html>"
ROBOTS = "User-agent: *\nDisallow: /private\nSitemap: https://acme.example/sitemap.xml\n"
FEED = (FX / "rss2.xml").read_bytes()


def brand(**kw) -> Brand:
    return Brand(id="acme", name="Acme", cohort="tech", country="US", homepage=HOME, **kw)


def write(tmp: str, payload) -> Path:
    path = Path(tmp) / "registry.json"
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload), "utf-8")
    return path


class SeedFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.brands = load_registry()

    def test_seed_loads_and_validates(self):
        self.assertGreaterEqual(len(self.brands), 100)
        self.assertEqual(validate_brands(self.brands), [])
        self.assertEqual(len({b.id for b in self.brands}), len(self.brands))

    def test_every_cohort_is_represented(self):
        by_cohort = {c: [b for b in self.brands if b.cohort == c] for c in COHORTS}
        for cohort, rows in by_cohort.items():
            with self.subTest(cohort=cohort):
                self.assertGreaterEqual(len(rows), 5)
        self.assertGreaterEqual(len(by_cohort["cz-local"]), 10)
        self.assertGreaterEqual(len(self.brands) - len(by_cohort["cz-local"]), 90)

    def test_czech_brands_are_present(self):
        ids = {b.id for b in self.brands if b.cohort == "cz-local"}
        for expected in ("skoda-auto", "kofola", "rohlik", "alza", "notino", "kiwi-com", "livesport", "productboard",
                         "seznam", "avast"):
            self.assertIn(expected, ids)

    def test_entries_are_hints_only(self):
        for b in self.brands:
            with self.subTest(brand=b.id):
                self.assertFalse(b.verified)
                self.assertFalse(b.synthetic)
                self.assertTrue(b.homepage and b.homepage.startswith("https://"))
                self.assertRegex(b.country or "", r"^[A-Z]{2}$")
                self.assertEqual(b.sitemaps, [])  # sitemaps come from robots.txt, never guessed

    def test_endpoints_are_absolute_and_on_a_plausible_host(self):
        for b in self.brands:
            for url in b.feeds:
                self.assertTrue(urlsplit(url).scheme in ("http", "https") and urlsplit(url).hostname, url)
            for path in b.content_paths:
                self.assertTrue(path.startswith("/"), path)

    def test_file_shape_and_note(self):
        data = json.loads(default_registry_path().read_text("utf-8"))
        self.assertEqual(data["version"], 1)
        self.assertIn("kingctl sources verify", data["note"])
        self.assertIn("hint", data["note"])

    def test_seed_file_has_no_em_dash(self):
        self.assertNotIn(chr(0x2014), default_registry_path().read_text("utf-8"))


class RegistryIoTests(unittest.TestCase):
    def test_round_trip_through_a_file(self):
        brands = [brand(feeds=["https://acme.example/feed"], content_paths=["/blog"]),
                  Brand(id="skoda", name="Škoda Auto", cohort="cz-local", country="CZ", homepage="https://www.skoda-auto.com/")]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "out.json"
            save_registry(brands, path)
            self.assertEqual(load_registry(path), brands)
            self.assertIn("Škoda Auto", path.read_text("utf-8"))  # unicode is not escaped
            self.assertTrue(path.read_text("utf-8").endswith("\n"))

    def test_minimal_brands_without_homepage_are_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.json"
            save_registry([Brand("a", "A", "tech")], path)
            self.assertEqual(load_registry(path)[0].homepage, None)

    def test_a_plain_list_and_null_lists_are_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, [{"id": "a", "name": "A", "cohort": "tech", "feeds": None, "extra": 1}])
            self.assertEqual(load_registry(path)[0].feeds, [])

    def test_duplicate_id_and_bad_cohort_are_rejected_and_all_problems_are_listed(self):
        rows = [
            {"id": "dup", "name": "One", "cohort": "tech", "homepage": "https://one.example/"},
            {"id": "dup", "name": "Two", "cohort": "tech", "homepage": "https://two.example/"},
            {"id": "other", "name": "Three", "cohort": "not-a-cohort", "homepage": "https://three.example/"},
        ]
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError) as ctx:
            load_registry(write(tmp, {"brands": rows}))
        message = str(ctx.exception)
        self.assertIn("duplicate id", message)
        self.assertIn("unknown cohort 'not-a-cohort'", message)
        self.assertIn("2 problem(s)", message)

    def test_url_slug_country_and_path_problems(self):
        rows = [
            {"id": "Bad Slug", "name": "A", "cohort": "tech"},
            {"id": "b", "name": "B", "cohort": "tech", "homepage": "http://insecure.example/"},
            {"id": "c", "name": "C", "cohort": "tech", "feeds": ["/relative/feed"], "sitemaps": ["ftp://x.example/s.xml"]},
            {"id": "d", "name": "D", "cohort": "tech", "country": "usa", "content_paths": ["blog"]},
            {"id": "e", "name": "", "cohort": "tech"},
            {"id": "f", "name": "F", "cohort": "tech", "feeds": "https://x.example/feed"},
            {"name": "no id", "cohort": "tech"},
            "not an object",
        ]
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError) as ctx:
            load_registry(write(tmp, {"brands": rows}))
        message = str(ctx.exception)
        for fragment in ("lowercase slug", "https URL", "feeds entry is not an absolute", "sitemaps entry is not an absolute",
                         "ISO alpha-2", "must start with '/'", "name is empty", "feeds must be a list",
                         "entry 6", "entry 7"):
            self.assertIn(fragment, message)

    def test_invalid_json_and_wrong_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                load_registry(write(tmp, "{not json"))
            with self.assertRaises(ValueError):
                load_registry(write(tmp, {"brands": "nope"}))


class SeedStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()

    def tearDown(self):
        self.store.close()

    def test_seed_default_registry_is_idempotent(self):
        count = seed_store(self.store)
        self.assertEqual(count, len(load_registry()))
        self.assertEqual(len(self.store.list_brands()), count)
        self.assertEqual(seed_store(self.store), count)
        self.assertEqual(len(self.store.list_brands()), count)
        self.assertEqual(self.store.cohort_of("kofola"), "cz-local")

    def test_custom_brands(self):
        self.assertEqual(seed_store(self.store, [brand()]), 1)
        self.assertEqual(self.store.get_brand("acme").homepage, HOME)

    def test_reseeding_does_not_downgrade_a_verified_brand(self):
        verified = brand(feeds=["https://acme.example/blog/feed"], verified=True)
        self.store.upsert_brand(verified)
        seed_store(self.store, [brand(feeds=["https://stale.example/feed"])])
        self.assertEqual(self.store.get_brand("acme").feeds, ["https://acme.example/blog/feed"])
        self.assertTrue(self.store.get_brand("acme").verified)


class VerifyBrandTests(unittest.TestCase):
    def fetcher(self, **routes) -> FakeFetcher:
        base = {"https://acme.example/robots.txt": ROBOTS, "https://acme.example/": HOME_WITH_FEED,
                "https://acme.example/blog/feed": FEED}
        base.update(routes)
        return FakeFetcher(base)

    def test_advertised_feed_and_robots_sitemap(self):
        fetcher = self.fetcher()
        report = verify_brand(brand(), PoliteFetcher(fetcher, RobotsPolicy(fetcher, UA)))
        self.assertIsInstance(report, VerifyReport)
        self.assertTrue(report.homepage_ok and report.robots_ok)
        self.assertEqual(report.feeds, ["https://acme.example/blog/feed"])
        self.assertEqual(report.sitemaps, ["https://acme.example/sitemap.xml"])
        self.assertEqual(len(report.sample_urls), 3)
        self.assertEqual(report.errors, [])
        self.assertEqual(set(report.to_dict()), {"brand_id", "homepage_ok", "robots_ok", "feeds", "sitemaps", "sample_urls", "errors"})

    def test_no_probing_when_a_feed_is_advertised(self):
        fetcher = self.fetcher()
        verify_brand(brand(), PoliteFetcher(fetcher, RobotsPolicy(fetcher, UA)))
        for guess in ("/feed", "/rss.xml", "/feed.xml", "/atom.xml"):
            self.assertNotIn("https://acme.example" + guess, fetcher.calls)

    def test_at_most_three_feed_probes_when_nothing_is_discovered(self):
        fetcher = self.fetcher(**{"https://acme.example/": PLAIN_HOME, "https://acme.example/blog/feed": (404, "")})
        report = verify_brand(brand(content_paths=["/blog"], feeds=["https://acme.example/old-feed"]),
                              PoliteFetcher(fetcher, RobotsPolicy(fetcher, UA)))
        probes = [c for c in fetcher.calls if c not in ("https://acme.example/robots.txt", HOME)
                  and "tdmrep" not in c and "sitemap" not in c]
        self.assertEqual(probes, ["https://acme.example/old-feed",   # the registry hint is tried first
                                  "https://acme.example/blog/feed",  # then the content path hint
                                  "https://acme.example/feed"])      # then one well-known path, and that is all
        self.assertNotIn("https://acme.example/rss.xml", fetcher.calls)
        self.assertEqual(report.feeds, [])
        self.assertTrue(report.homepage_ok)

    def test_probing_stops_at_the_first_real_feed(self):
        fetcher = self.fetcher(**{"https://acme.example/": PLAIN_HOME, "https://acme.example/feed": "<html>soft 404</html>",
                                  "https://acme.example/rss.xml": FEED})
        report = verify_brand(brand(), PoliteFetcher(fetcher, RobotsPolicy(fetcher, UA)))
        self.assertEqual(report.feeds, ["https://acme.example/rss.xml"])
        self.assertNotIn("https://acme.example/feed.xml", fetcher.calls)
        self.assertEqual(len(report.sample_urls), 3)

    def test_robots_disallowing_the_homepage_stops_everything(self):
        fetcher = self.fetcher(**{"https://acme.example/robots.txt": "User-agent: *\nDisallow: /\n"})
        report = verify_brand(brand(), PoliteFetcher(fetcher, RobotsPolicy(fetcher, UA)))
        self.assertFalse(report.robots_ok)
        self.assertFalse(report.homepage_ok)
        self.assertIn("robots.txt", report.errors[0])
        self.assertEqual(fetcher.calls, ["https://acme.example/robots.txt"])

    def test_homepage_failures_are_reported_not_raised(self):
        cases = {
            "http error": ((503, "down"), "HTTP 503"),
            "network": (FetchError("dns failure"), "unreachable"),
            "tdm": ((200, "<html></html>", {"tdm-reservation": "1"}), "tdm-reservation"),
        }
        for label, (route, fragment) in cases.items():
            with self.subTest(label):
                fetcher = self.fetcher(**{"https://acme.example/": route})
                report = verify_brand(brand(), PoliteFetcher(fetcher, RobotsPolicy(fetcher, UA)))
                self.assertFalse(report.homepage_ok)
                self.assertTrue(report.robots_ok)
                self.assertIn(fragment, " ".join(report.errors))
                self.assertEqual(report.feeds, [])

    def test_brand_without_homepage(self):
        report = verify_brand(Brand("x", "X", "tech"), FakeFetcher())
        self.assertFalse(report.homepage_ok)
        self.assertIn("no homepage", report.errors[0])

    def test_hinted_sitemap_is_confirmed_only_when_robots_lists_none(self):
        routes = {"https://acme.example/robots.txt": "User-agent: *\nDisallow:\n", "https://acme.example/": PLAIN_HOME,
                  "https://acme.example/good.xml": '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                                                  "<url><loc>https://acme.example/blog/a</loc></url></urlset>"}
        fetcher = FakeFetcher(routes)
        report = verify_brand(brand(sitemaps=["https://acme.example/good.xml", "https://acme.example/dead.xml"]),
                              PoliteFetcher(fetcher, RobotsPolicy(fetcher, UA)))
        self.assertEqual(report.sitemaps, ["https://acme.example/good.xml"])
        self.assertEqual(report.sample_urls, ["https://acme.example/blog/a"])

    def test_raw_fetchers_are_wrapped_so_robots_still_applies(self):
        fetcher = self.fetcher(**{"https://acme.example/robots.txt": "User-agent: *\nDisallow: /\n"})
        self.assertFalse(verify_brand(brand(), fetcher).robots_ok)

    def test_verify_all_streams_reports_and_reports_progress(self):
        other = Brand("other", "Other", "tech", "US", "https://other.example/")
        fetcher = self.fetcher(**{"https://other.example/robots.txt": (404, ""), "https://other.example/": PLAIN_HOME})
        messages = []
        reports = list(verify_all([brand(), other], PoliteFetcher(fetcher, RobotsPolicy(fetcher, UA)), progress=messages.append))
        self.assertEqual([r.brand_id for r in reports], ["acme", "other"])
        self.assertEqual(messages, ["verifying acme", "verifying other"])
        self.assertEqual(fetcher.calls.count("https://acme.example/robots.txt"), 1)
        self.assertFalse(reports[1].feeds)


class ApplyVerificationTests(unittest.TestCase):
    def report(self, **kw) -> VerifyReport:
        base = dict(brand_id="acme", homepage_ok=True, robots_ok=True, feeds=["https://acme.example/feed"], sitemaps=[])
        base.update(kw)
        return VerifyReport(**base)

    def test_verified_when_everything_checks_out(self):
        original = brand(feeds=["https://stale.example/feed"], sitemaps=["https://stale.example/s.xml"])
        updated = apply_verification(original, self.report(sitemaps=["https://acme.example/sitemap.xml"]))
        self.assertTrue(updated.verified)
        self.assertEqual(updated.feeds, ["https://acme.example/feed"])
        self.assertEqual(updated.sitemaps, ["https://acme.example/sitemap.xml"])
        self.assertFalse(original.verified)  # a copy is returned
        self.assertEqual(original.feeds, ["https://stale.example/feed"])

    def test_sitemaps_alone_are_enough(self):
        updated = apply_verification(brand(), self.report(feeds=[], sitemaps=["https://acme.example/sitemap.xml"]))
        self.assertTrue(updated.verified)

    def test_each_missing_condition_blocks_verification(self):
        cases = {
            "homepage": self.report(homepage_ok=False),
            "robots": self.report(robots_ok=False),
            "nothing found": self.report(feeds=[], sitemaps=[]),
        }
        for label, report in cases.items():
            with self.subTest(label):
                original = brand(feeds=["https://hint.example/feed"], verified=True)
                updated = apply_verification(original, report)
                self.assertFalse(updated.verified)
                self.assertEqual(updated.feeds, ["https://hint.example/feed"])  # hints survive a failed check

    def test_content_paths_and_identity_are_preserved(self):
        updated = apply_verification(brand(content_paths=["/blog"]), self.report())
        self.assertEqual((updated.id, updated.name, updated.cohort, updated.content_paths), ("acme", "Acme", "tech", ["/blog"]))


if __name__ == "__main__":
    unittest.main()
